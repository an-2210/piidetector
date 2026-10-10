"""Base extractor interface for native document formats."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Tuple, Union

from src.models.text_block import ExtractionResult
from src.utils.helpers import validate_file_path


class BaseExtractor(ABC):
    """Abstract base class that all native document extractors must implement."""

    supported_extensions: Tuple[str, ...] = ()

    def validate_file(self, file_path: Union[str, Path]) -> Path:
        """Validate file existence, accessibility, and extension."""
        path = validate_file_path(file_path)
        ext = path.suffix.lower()
        if ext not in self.supported_extensions:
            raise ValueError(
                f"Unsupported file format '{ext}' for {self.__class__.__name__}. "
                f"Expected one of: {self.supported_extensions}"
            )
        return path

    @abstractmethod
    def extract(self, file_path: Union[str, Path], **kwargs: Any) -> ExtractionResult:
        """Extract structured TextBlocks and metadata from the given document file.

        Args:
            file_path: Path to the target file.
            **kwargs: Extractor-specific options (e.g. ocr_char_threshold).

        Returns:
            ExtractionResult container with blocks, OCR flags, and document metadata.
        """
        raise NotImplementedError
