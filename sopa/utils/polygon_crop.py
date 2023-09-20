import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import zarr
from matplotlib.widgets import PolygonSelector
from shapely.geometry import Polygon
from spatialdata import SpatialData
from spatialdata.models import ShapesModel

from .._constants import ROI
from .image import resize
from .utils import _get_spatial_image

HELPER = """Enclose cells within a polygon. Helper:
    - Click on the plot to add a polygon vertex
    - Press the 'esc' key to start a new polygon
    - Try holding the 'ctrl' key to move a single vertex
    - Once the polygon is finished and overlaid in red, you can close the window
"""

VALID_N_CHANNELS = [1, 3]


def _prepare(sdata: SpatialData, channels: list[str], scale_factor: float):
    image_key, spatial_image = _get_spatial_image(sdata)
    image = spatial_image.transpose("y", "x", "c")

    if len(channels):
        assert (
            len(channels) in VALID_N_CHANNELS
        ), f"Number of channels provided must be in: {', '.join(VALID_N_CHANNELS)}"
        image = image.sel(c=channels)
    else:
        assert (
            len(image.coords["c"]) in VALID_N_CHANNELS
        ), f"Choose one or three channels among {image.c.values} by using the -c argument"

    return image_key, resize(image, scale_factor).compute()


class _Selector:
    def __init__(self, ax):
        self.poly = PolygonSelector(ax, self.onselect, draw_bounding_box=True)
        print(HELPER)
        plt.show()

    def onselect(self, vertices):
        self.vertices = np.array(vertices)
        print(f"Selected polygon with {len(self.vertices)} vertices.")

    def disconnect(self):
        self.poly.disconnect_events()


def _draw_polygon(image: np.ndarray, scale_factor: float, margin_ratio: float):
    _, ax = plt.subplots()
    ax.imshow(image)

    dy, dx, *_ = image.shape
    plt.xlim(-margin_ratio * dx, dx + margin_ratio * dx)
    plt.ylim(dy + margin_ratio * dy, -margin_ratio * dy)

    selector = _Selector(ax)

    return Polygon(selector.vertices * scale_factor)


def intermediate_selection(
    intermediate_image: str, intermediate_polygon: str, margin_ratio: float = 0.1
):
    z = zarr.open(intermediate_image, mode="r")

    image = z[ROI.IMAGE_ARRAY_KEY][:]

    polygon = _draw_polygon(image, z.attrs[ROI.SCALE_FACTOR], margin_ratio)

    with zarr.ZipStore(intermediate_polygon, mode="w") as store:
        g = zarr.group(store=store)
        g.attrs.put({ROI.IMAGE_KEY: z.attrs[ROI.IMAGE_KEY], ROI.ELEMENT_TYPE: "images"})

        coords = np.array(polygon.exterior.coords)
        g.array(ROI.POLYGON_ARRAY_KEY, coords, dtype=coords.dtype, chunks=coords.shape)


def polygon_selection(
    sdata: SpatialData,
    intermediate_image: str | None = None,
    intermediate_polygon: str | None = None,
    channels: list[str] | None = None,
    scale_factor: float = 10,
    margin_ratio: float = 0.1,
):
    if intermediate_polygon is None:
        image_key, image = _prepare(sdata, channels, scale_factor)

        if intermediate_image is not None:
            print(f"Resized image will be saved to {intermediate_image}")
            with zarr.ZipStore(intermediate_image, mode="w") as store:
                g = zarr.group(store=store)
                g.attrs.put({ROI.SCALE_FACTOR: scale_factor, ROI.IMAGE_KEY: image_key})
                g.array(ROI.IMAGE_ARRAY_KEY, image, dtype=image.dtype, chunks=image.shape)
            return

        polygon = _draw_polygon(image, scale_factor, margin_ratio)
    else:
        print(f"Reading polygon at path {intermediate_polygon}")
        z = zarr.open(intermediate_polygon, mode="r")
        polygon = Polygon(z[ROI.POLYGON_ARRAY_KEY][:])

        _, image = _get_spatial_image(sdata, z.attrs[ROI.IMAGE_KEY])

    geo_df = gpd.GeoDataFrame({"geometry": [polygon]})
    geo_df = ShapesModel.parse(geo_df, transformations=image.transform)
    sdata.add_shapes(ROI.KEY, geo_df)
