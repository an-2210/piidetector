"""Tests for NER backend adapters: chunking, dedupe, and graceful fallback."""

import sys

import pytest

from src.pii import backends
from src.pii.backends import RawEntity, chunk_text, dedupe_entities, load_backends
from src.pii.config import P4Config


@pytest.fixture(autouse=True)
def _clean_cache():
    backends.clear_model_cache()
    yield
    backends.clear_model_cache()


def test_chunk_text_returns_whole_text_when_short():
    assert chunk_text("short", 100, 10) == [(0, "short")]


def test_chunk_text_offsets_reconstruct_the_source():
    text = "".join(str(i % 10) for i in range(500))
    chunks = chunk_text(text, size=120, overlap=20)

    for offset, chunk in chunks:
        assert text[offset : offset + len(chunk)] == chunk
    assert chunks[-1][0] + len(chunks[-1][1]) == len(text)
    assert all(len(c) <= 120 for _, c in chunks)


def test_dedupe_keeps_best_score_for_same_span_and_label():
    entities = [
        RawEntity(0, 4, "Jane", "PERSON", 0.6, "gliner"),
        RawEntity(0, 4, "Jane", "PERSON", 0.9, "gliner"),
        RawEntity(0, 4, "Jane", "ORG", 0.7, "gliner"),
    ]
    out = dedupe_entities(entities)
    assert [(e.label, e.score) for e in out] == [("ORG", 0.7), ("PERSON", 0.9)]


def test_load_backends_with_everything_disabled_returns_no_backends():
    config = P4Config(enable_spacy=False, enable_gliner=False)
    assert load_backends(config) == ([], [])


def test_missing_gliner_falls_back_with_warning(monkeypatch):
    monkeypatch.setitem(sys.modules, "gliner", None)  # forces ImportError
    config = P4Config(enable_spacy=False, enable_gliner=True)

    loaded, warnings = load_backends(config)

    assert loaded == []
    assert len(warnings) == 1
    assert "gliner" in warnings[0] and "skipped" in warnings[0]


def test_missing_spacy_model_falls_back_with_warning(monkeypatch):
    monkeypatch.setitem(sys.modules, "presidio_analyzer", None)
    config = P4Config(enable_spacy=True, enable_gliner=False)

    loaded, warnings = load_backends(config)

    assert loaded == []
    assert len(warnings) == 1
    assert "spacy" in warnings[0]


def test_location_label_is_discounted_relative_to_person(monkeypatch):
    """LOCATION maps to ADDRESS but at a lower score than the raw Presidio score."""
    class FakeResult:
        def __init__(self, entity_type, start, end, score):
            self.entity_type, self.start, self.end, self.score = entity_type, start, end, score

    text = "Jane lives Lagos on"
    lagos = text.index("Lagos")

    class FakeAnalyzer:
        def analyze(self, text, language, entities):
            return [
                FakeResult("PERSON", 0, 4, 0.85),
                FakeResult("LOCATION", lagos, lagos + 5, 0.85),
                FakeResult("UNKNOWN_KIND", 0, 4, 0.9),
            ]

    backend = backends.SpacyPresidioBackend.__new__(backends.SpacyPresidioBackend)
    backend._defer_structured = True
    backend._analyzer = FakeAnalyzer()

    out = backend.predict(text)

    by_label = {e.label: e for e in out}
    assert set(by_label) == {"PERSON", "ADDRESS"}
    assert by_label["PERSON"].score == pytest.approx(0.85)
    assert by_label["ADDRESS"].score == pytest.approx(0.85 * backends.LOCATION_SCORE_FACTOR)
    assert by_label["ADDRESS"].text == "Lagos"
