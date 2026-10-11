
"""Tesseract OCR adapter with word-box grouping and fallback modes."""

from __future__ import annotations

import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image
import pytesseract
from pytesseract import Output


# Configure Tesseract automatically on Windows.
WINDOWS_TESSERACT = Path(
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)

if WINDOWS_TESSERACT.is_file():
    pytesseract.pytesseract.tesseract_cmd = str(
        WINDOWS_TESSERACT
    )
else:
    discovered = shutil.which("tesseract")
    if discovered:
        pytesseract.pytesseract.tesseract_cmd = discovered


def _recognize_with_mode(
    image: Image.Image,
    confidence_threshold: float,
    language: str,
    psm: int,
) -> list[dict[str, Any]]:
    """Recognize text using one Tesseract segmentation mode."""

    data = pytesseract.image_to_data(
        image,
        lang=language,
        output_type=Output.DICT,
        config=f"--oem 3 --psm {psm}",
    )

    lines: dict[
        tuple[int, int, int],
        list[dict[str, Any]],
    ] = defaultdict(list)

    for index, raw_text in enumerate(data["text"]):
        text = raw_text.strip()

        if not text:
            continue

        try:
            confidence = float(data["conf"][index])
        except (TypeError, ValueError):
            continue

        if confidence < confidence_threshold:
            continue

        key = (
            int(data["block_num"][index]),
            int(data["par_num"][index]),
            int(data["line_num"][index]),
        )

        x = int(data["left"][index])
        y = int(data["top"][index])
        width = int(data["width"][index])
        height = int(data["height"][index])

        lines[key].append(
            {
                "text": text,
                "confidence": confidence / 100.0,
                "bbox": [
                    x,
                    y,
                    x + width,
                    y + height,
                ],
            }
        )

    detections = []

    for words in lines.values():
        if not words:
            continue

        detections.append(
            {
                "text": " ".join(
                    word["text"] for word in words
                ),
                "confidence": sum(
                    word["confidence"] for word in words
                ) / len(words),
                "bbox": [
                    min(word["bbox"][0] for word in words),
                    min(word["bbox"][1] for word in words),
                    max(word["bbox"][2] for word in words),
                    max(word["bbox"][3] for word in words),
                ],
            }
        )

    return detections


def recognize_text(
    image: Image.Image,
    confidence_threshold: float = 30.0,
    language: str = "eng",
) -> list[dict[str, Any]]:
    """
    Recognize text in an image.

    Tries multiple segmentation modes to handle scanned pages,
    cropped images, and images containing sparse text.

    Each detection contains:
        text: recognized text line
        confidence: confidence from 0.0 to 1.0
        bbox: [x1, y1, x2, y2] in image pixels
    """

    executable = pytesseract.pytesseract.tesseract_cmd

    if not executable:
        raise RuntimeError(
            "Tesseract was not found. Check the installation path."
        )

    if (
        not Path(executable).is_file()
        and shutil.which(str(executable)) is None
    ):
        raise RuntimeError(
            f"Tesseract executable not found: {executable}"
        )

    # Ensure OCR receives a supported, consistent image mode.
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    # PSM 3: automatic layout.
    # PSM 6: one uniform text block.
    # PSM 11: sparse text distributed across an image.
    modes = (3, 6, 11)

    best_detections: list[dict[str, Any]] = []

    for psm in modes:
        detections = _recognize_with_mode(
            image=image,
            confidence_threshold=confidence_threshold,
            language=language,
            psm=psm,
        )

        # Keep the result with the most recognized text.
        current_score = sum(
            len(item["text"]) for item in detections
        )
        best_score = sum(
            len(item["text"]) for item in best_detections
        )

        if current_score > best_score:
            best_detections = detections

        # A successful recognition result needs no fallback.
        if detections and psm == 3:
            break

    # Retry with a lower threshold if all modes returned nothing.
    if not best_detections and confidence_threshold > 15:
        for psm in modes:
            detections = _recognize_with_mode(
                image=image,
                confidence_threshold=15.0,
                language=language,
                psm=psm,
            )

            current_score = sum(
                len(item["text"]) for item in detections
            )
            best_score = sum(
                len(item["text"]) for item in best_detections
            )

            if current_score > best_score:
                best_detections = detections

    return best_detections
