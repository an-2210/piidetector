"""Utility helpers for text formatting, geometry, and table serialization."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union


def validate_file_path(file_path: Union[str, Path]) -> Path:
    """Validate that the file exists and is accessible.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If path points to a directory or is empty.
    """
    if not file_path:
        raise ValueError("File path cannot be empty.")
    path = Path(file_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if not path.is_file():
        raise ValueError(f"Path is not a regular file: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"File is empty (0 bytes): {path}")
    return path


def clean_text(text: Optional[str]) -> str:
    """Normalize whitespace and strip extraneous leading/trailing spaces."""
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def format_table_as_markdown(rows: List[List[str]]) -> str:
    """Convert a 2D list of cell strings into a clean Markdown table representation.

    Args:
        rows: List of rows, where each row is a list of cell string values.

    Returns:
        Markdown-formatted string representing the table.
    """
    if not rows:
        return ""
    # Normalize row lengths to match max column count
    max_cols = max(len(row) for row in rows)
    if max_cols == 0:
        return ""

    normalized_rows = []
    for row in rows:
        cleaned_cells = [str(c).replace("\n", " ").replace("|", "\\|").strip() if c is not None else "" for c in row]
        if len(cleaned_cells) < max_cols:
            cleaned_cells.extend([""] * (max_cols - len(cleaned_cells)))
        normalized_rows.append(cleaned_cells)

    header = normalized_rows[0]
    separator = ["---"] * max_cols
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in normalized_rows[1:]:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def rect_overlaps_bbox(
    r1: Tuple[float, float, float, float],
    r2: Tuple[float, float, float, float],
    threshold: float = 0.5,
) -> bool:
    """Determine whether two bounding boxes (x0, y0, x1, y1) have substantial overlap.

    Args:
        r1: (x0, y0, x1, y1)
        r2: (x0, y0, x1, y1)
        threshold: Overlap intersection ratio relative to r1 area.
    """
    x0 = max(r1[0], r2[0])
    y0 = max(r1[1], r2[1])
    x1 = min(r1[2], r2[2])
    y1 = min(r1[3], r2[3])

    if x1 <= x0 or y1 <= y0:
        return False

    intersection = (x1 - x0) * (y1 - y0)
    area1 = (r1[2] - r1[0]) * (r1[3] - r1[1])
    if area1 <= 0:
        return False
    return (intersection / area1) >= threshold
