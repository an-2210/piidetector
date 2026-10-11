"""NER backends for P4: Presidio + spaCy, and optional GLiNER zero-shot.

Each backend turns a block's text into `RawEntity` spans with labels already
mapped to `PII_TYPES`. Backends are optional. A missing package or model is
reported as a warning and that backend is skipped, so P4 never crashes on a
machine without the models.

Loaded models are cached per process, so a multi-file run loads each once.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

from src.pii.config import P4Config

logger = logging.getLogger(__name__)

# Presidio entity name -> canonical PII label.
PRESIDIO_LABELS: Dict[str, str] = {
    "PERSON": "PERSON",
    "ORGANIZATION": "ORG",
    "LOCATION": "ADDRESS",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "PHONE",
    "US_SSN": "SSN",
    "CREDIT_CARD": "PAN",
    "US_PASSPORT": "PASSPORT",
}

# Presidio entities that come from spaCy NER rather than pattern recognizers.
PRESIDIO_NLP_ENTITIES = ("PERSON", "ORGANIZATION", "LOCATION")

# A location is a city or country far more often than a postal address, so its
# score is discounted before it is treated as ADDRESS.
LOCATION_SCORE_FACTOR = 0.5

GLINER_LABELS: Dict[str, str] = {
    "person": "PERSON",
    "address": "ADDRESS",
    "organization": "ORG",
}

# GLiNER has a short input window, so long blocks are scanned in overlapping chunks.
GLINER_CHUNK_CHARS = 1500
GLINER_CHUNK_OVERLAP = 200


class BackendUnavailable(RuntimeError):
    """Raised when a backend's package or model cannot be loaded."""


@dataclass(frozen=True)
class RawEntity:
    """One NER span from one backend, before disambiguation and fusion."""

    start: int
    end: int
    text: str
    label: str  # canonical PII label
    score: float
    backend: str  # "spacy" | "gliner"


class NERBackend(Protocol):
    """A NER model that labels spans in a string."""

    name: str

    def predict(self, text: str) -> List[RawEntity]:
        """Return labelled spans for `text`. Offsets are relative to `text`."""
        ...


def chunk_text(text: str, size: int, overlap: int) -> List[Tuple[int, str]]:
    """Split `text` into overlapping windows, returning `(offset, chunk)` pairs."""
    if len(text) <= size:
        return [(0, text)]
    step = max(1, size - overlap)
    chunks: List[Tuple[int, str]] = []
    offset = 0
    while True:
        chunks.append((offset, text[offset : offset + size]))
        if offset + size >= len(text):
            break
        offset += step
    return chunks


def dedupe_entities(entities: Sequence[RawEntity]) -> List[RawEntity]:
    """Drop exact (span, label) repeats from overlapping chunks, keeping the best score."""
    best: Dict[Tuple[int, int, str], RawEntity] = {}
    for entity in entities:
        key = (entity.start, entity.end, entity.label)
        current = best.get(key)
        if current is None or entity.score > current.score:
            best[key] = entity
    return sorted(best.values(), key=lambda e: (e.start, e.end, e.label))


_MODEL_CACHE: Dict[Tuple[str, ...], Any] = {}


class SpacyPresidioBackend:
    """Presidio AnalyzerEngine on top of a spaCy pipeline."""

    name = "spacy"

    def __init__(self, config: P4Config) -> None:
        self._defer_structured = config.defer_structured_to_rules
        key = ("presidio", config.spacy_model)
        if key not in _MODEL_CACHE:
            _MODEL_CACHE[key] = self._build_analyzer(config.spacy_model)
        self._analyzer = _MODEL_CACHE[key]

    @staticmethod
    def _build_analyzer(model_name: str) -> Any:
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
        except ImportError as exc:
            raise BackendUnavailable(
                "presidio-analyzer is not installed (pip install presidio-analyzer)"
            ) from exc
        try:
            import spacy

            spacy.load(model_name)
        except (ImportError, OSError) as exc:
            raise BackendUnavailable(
                f"spaCy model '{model_name}' is not installed "
                f"(python -m spacy download {model_name})"
            ) from exc
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": model_name}],
            }
        )
        return AnalyzerEngine(
            nlp_engine=provider.create_engine(),
            supported_languages=["en"],
        )

    def predict(self, text: str) -> List[RawEntity]:
        # With defer_structured_to_rules, only the spaCy-backed entities are
        # requested, so Presidio's pattern recognizers never run.
        entities = list(PRESIDIO_NLP_ENTITIES) if self._defer_structured else None
        results = self._analyzer.analyze(text=text, language="en", entities=entities)
        out: List[RawEntity] = []
        for result in results:
            label = PRESIDIO_LABELS.get(result.entity_type)
            if label is None:
                continue
            score = float(result.score)
            if result.entity_type == "LOCATION":
                score *= LOCATION_SCORE_FACTOR
            out.append(
                RawEntity(
                    start=int(result.start),
                    end=int(result.end),
                    text=text[result.start : result.end],
                    label=label,
                    score=score,
                    backend=self.name,
                )
            )
        return out


class GlinerBackend:
    """GLiNER zero-shot NER for person, address and organization."""

    name = "gliner"

    def __init__(self, config: P4Config) -> None:
        self._threshold = config.gliner_threshold
        key = ("gliner", config.gliner_model)
        if key not in _MODEL_CACHE:
            _MODEL_CACHE[key] = self._load(config.gliner_model)
        self._model = _MODEL_CACHE[key]

    @staticmethod
    def _load(model_name: str) -> Any:
        try:
            from gliner import GLiNER
        except ImportError as exc:
            raise BackendUnavailable(
                "gliner is not installed (pip install gliner)"
            ) from exc
        try:
            return GLiNER.from_pretrained(model_name)
        except Exception as exc:  # noqa: BLE001 - model download/load can fail many ways
            raise BackendUnavailable(
                f"GLiNER model '{model_name}' could not be loaded: {exc}"
            ) from exc

    def predict(self, text: str) -> List[RawEntity]:
        labels = list(GLINER_LABELS.keys())
        collected: List[RawEntity] = []
        for offset, chunk in chunk_text(text, GLINER_CHUNK_CHARS, GLINER_CHUNK_OVERLAP):
            for item in self._model.predict_entities(
                chunk, labels, threshold=self._threshold
            ):
                label = GLINER_LABELS.get(str(item["label"]).lower())
                if label is None:
                    continue
                start = offset + int(item["start"])
                end = offset + int(item["end"])
                collected.append(
                    RawEntity(
                        start=start,
                        end=end,
                        text=text[start:end],
                        label=label,
                        score=float(item["score"]),
                        backend=self.name,
                    )
                )
        return dedupe_entities(collected)


def load_backends(
    config: P4Config,
) -> Tuple[List[NERBackend], List[str]]:
    """Load every enabled backend that is available.

    Returns:
        (backends, warnings). Warnings name each backend that was skipped and
        why. An empty backend list is valid: P4 then runs on rule findings only.
    """
    backends: List[NERBackend] = []
    warnings: List[str] = []
    factories: List[Tuple[bool, str, Any]] = [
        (config.enable_spacy, "spacy", SpacyPresidioBackend),
        (config.enable_gliner, "gliner", GlinerBackend),
    ]
    for enabled, name, factory in factories:
        if not enabled:
            continue
        try:
            backends.append(factory(config))
        except BackendUnavailable as exc:
            message = f"NER backend '{name}' skipped: {exc}"
            logger.warning(message)
            warnings.append(message)
        except Exception as exc:  # noqa: BLE001 - never crash the pipeline on NER setup
            message = f"NER backend '{name}' failed to start: {exc}"
            logger.warning(message)
            warnings.append(message)
    return backends, warnings


def clear_model_cache() -> None:
    """Drop cached models (used by tests)."""
    _MODEL_CACHE.clear()
