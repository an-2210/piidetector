
"""Preprocess document images before OCR."""

from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image, ImageOps


def preprocess_image(
    image: Image.Image,
    upscale_factor: float = 1.5,
    denoise: bool = True,
    deskew: bool = True,
) -> Image.Image:
    """Improve image readability before OCR.

    Converts the input to grayscale, enhances contrast, optionally upscales,
    denoises, and corrects moderate skew.

    Args:
        image: Source image to preprocess.
        upscale_factor: Positive scale factor for image resizing.
        denoise: Whether to apply non-local means denoising.
        deskew: Whether to estimate and correct image skew.

    Returns:
        A grayscale PIL image suitable for OCR.

    Raises:
        TypeError: If the input is not a PIL image.
        ValueError: If the image has invalid dimensions or the upscale
            factor is not a positive finite number.
    """
    if not isinstance(image, Image.Image):
        raise TypeError("image must be a PIL Image.Image instance.")

    width, height = image.size

    if width <= 0 or height <= 0:
        raise ValueError(
            f"Image dimensions must be positive; received {width}x{height}."
        )

    if (
        not isinstance(upscale_factor, (int, float))
        or isinstance(upscale_factor, bool)
        or not math.isfinite(upscale_factor)
        or upscale_factor <= 0
    ):
        raise ValueError(
            "upscale_factor must be a positive, finite number."
        )

    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray)

    array = np.array(gray)

    if upscale_factor > 1:
        height, width = array.shape
        new_width = max(1, int(width * upscale_factor))
        new_height = max(1, int(height * upscale_factor))

        array = cv2.resize(
            array,
            (new_width, new_height),
            interpolation=cv2.INTER_CUBIC,
        )

    if denoise:
        array = cv2.fastNlMeansDenoising(
            array,
            None,
            h=10,
            templateWindowSize=7,
            searchWindowSize=21,
        )

    if deskew:
        # Estimate skew from foreground pixels.
        _, binary = cv2.threshold(
            array,
            0,
            255,
            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
        )
        points = cv2.findNonZero(binary)

        if points is not None and len(points) >= 10:
            angle = cv2.minAreaRect(points)[-1]

            # Normalize OpenCV's rectangle angle convention.
            if angle < -45:
                angle = -(90 + angle)
            else:
                angle = -angle

            # Avoid rotating images due to noisy estimates.
            if 0.5 <= abs(angle) <= 15:
                height, width = array.shape
                center = (width / 2, height / 2)
                matrix = cv2.getRotationMatrix2D(
                    center,
                    angle,
                    1.0,
                )

                array = cv2.warpAffine(
                    array,
                    matrix,
                    (width, height),
                    flags=cv2.INTER_CUBIC,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=255,
                )

    return Image.fromarray(array)
