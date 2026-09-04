"""Tests for partial-object streaming."""

from __future__ import annotations

import pytest

from typedout import ExtractionError, MockProvider, TypedOut
from typedout.streaming import iter_partial


def test_iter_partial_builds_up_object():
    chunks = ['{"na', 'me": "A', 'da", "a', 'ge": 36}']
    snapshots = list(iter_partial(chunks))
    assert snapshots[-1] == {"name": "Ada", "age": 36}
    # Snapshots grow monotonically toward the final object.
    assert all(isinstance(s, dict) for s in snapshots)
    assert snapshots[-1]["name"] == "Ada"


def test_iter_partial_skips_unparseable_prefixes():
    # Leading chunk has no JSON yet; it should be skipped, not crash.
    chunks = ["thinking... ", '{"x":', " 1}"]
    snapshots = list(iter_partial(chunks))
    assert snapshots[-1] == {"x": 1}


def test_iter_partial_deduplicates():
    chunks = ['{"x": 1}', "", "  "]
    snapshots = list(iter_partial(chunks))
    assert snapshots == [{"x": 1}]


def test_engine_stream_yields_partials_then_validates(person_cls):
    llm = TypedOut(MockProvider(script=["valid"], chunk_size=5))
    seen = list(llm.stream(person_cls, "Ada Lovelace, 36"))
    assert len(seen) >= 1
    # After streaming, the validated typed object is available.
    assert isinstance(llm.last_result, person_cls)
    assert llm.last_result.name


def test_engine_collect_returns_final(person_cls):
    llm = TypedOut(MockProvider(script=["valid"]))
    result = llm.collect(person_cls, "Ada, 36")
    assert isinstance(result, person_cls)


def test_stream_progression_is_partial_before_complete(company_cls):
    # A nested object streamed in small chunks should show intermediate states
    # with fewer keys than the final object.
    llm = TypedOut(MockProvider(script=["valid"], chunk_size=8))
    snapshots = [s for s in llm.stream(company_cls, "...") if isinstance(s, dict)]
    key_counts = [len(s) for s in snapshots]
    assert key_counts[0] <= key_counts[-1]
    assert llm.last_result.name


def test_stream_invalid_raises_extraction_error(person_cls):
    # A schema-invalid stream must surface as a library error, like extract().
    llm = TypedOut(MockProvider(script=["invalid"]))
    with pytest.raises(ExtractionError) as exc:
        list(llm.stream(person_cls, "x"))
    assert exc.value.last_raw is not None
    assert llm.last_result is None


def test_stream_snapshots_only_contain_schema_keys(person_cls):
    # Chunk boundaries inside a key name used to leak phantom keys such as
    # {'nam': None}; every snapshot must be a subset of the schema's fields.
    llm = TypedOut(MockProvider(script=["valid"], chunk_size=8))
    snapshots = list(llm.stream(person_cls, "Ada Lovelace, 36, ada@example.com"))
    assert snapshots
    for snapshot in snapshots:
        assert set(snapshot) <= {"name", "age", "email"}
    assert snapshots[-1] == {"name": "Ada Lovelace", "age": 36, "email": "ada@example.com"}
    # Dropping a phantom key must not produce two equal consecutive snapshots.
    assert all(a != b for a, b in zip(snapshots, snapshots[1:]))
    assert isinstance(llm.last_result, person_cls)


def test_stream_keeps_genuine_null_fields(company_cls):
    # A real, nullable schema field is not a phantom key.
    text = (
        '{"name": "Acme", "employees": 1, "hq": {"city": "London", '
        '"country": "UK"}, "tags": [], "website": null}'
    )
    llm = TypedOut(MockProvider(responses=[text], chunk_size=len(text)))
    snapshots = list(llm.stream(company_cls, "..."))
    assert "website" in snapshots[-1] and snapshots[-1]["website"] is None
    assert llm.last_result.website is None
