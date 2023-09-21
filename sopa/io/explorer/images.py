import logging

import numpy as np
import tifffile as tf
from multiscale_spatial_image import MultiscaleSpatialImage, to_multiscale

from ._constants import image_metadata, image_options

log = logging.getLogger(__name__)


def _astype_uint8(arr: np.ndarray) -> np.ndarray:
    log.info(f"   Image of shape {arr.shape}")
    assert np.issubdtype(
        arr.dtype, np.integer
    ), f"The image dtype has to be an integer dtype. Found {arr.dtype}"

    if arr.dtype == np.uint8:
        return arr

    factor = np.iinfo(np.uint8).max / np.iinfo(arr.dtype).max
    return (arr * factor).astype(np.uint8)


def write_image(
    path: str,
    image: MultiscaleSpatialImage,
    image_key: str,
    pixelsize: float = 0.2125,
):
    log.info("Writing multiscale image")

    if not isinstance(image, MultiscaleSpatialImage):
        image = to_multiscale(image, [2, 2, 2, 2, 2])

    scale_names = list(image.children)
    channel_names = list(image[scale_names[0]].c.values)

    metadata = image_metadata(channel_names, pixelsize)

    # TODO : make it memory efficient
    with tf.TiffWriter(path, bigtiff=True) as tif:
        tif.write(
            _astype_uint8(image[scale_names[0]][image_key].values),
            subifds=len(scale_names) - 1,
            resolution=(1e4 / pixelsize, 1e4 / pixelsize),
            metadata=metadata,
            **image_options(),
        )

        for i, scale in enumerate(scale_names[1:]):
            tif.write(
                _astype_uint8(image[scale][image_key].values),
                subfiletype=1,
                resolution=(
                    1e4 * 2 ** (i + 1) / pixelsize,
                    1e4 * 2 ** (i + 1) / pixelsize,
                ),
                **image_options(),
            )
