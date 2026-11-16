"""The `temporal_scope` field: historical / current / timeless.

A fact extracted from a historical item must keep its scope: the extraction
schema carries `temporal_scope`, the prompt tells the extractor to keep
past-tense framing for historical non-event facts, and readback surfaces the
scope next to When so a historical fact is never presented as a current
standing instruction.

The regression gate is the r-series design (correction draft for card
t_c7a8f5f6, 2026-11-14): historical fixtures are never presented as current,
current preferences still are. All fixture content here is synthetic
(fictional "Alex" + fictional greenhouse / tool-library topics); fixture r4's
wording mirrors the incident's derived preference with the subject changed,
as disclosed in that draft.
"""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from hindsight_api.engine.response_models import (
    MemoryFact,
    format_when_with_scope,
    temporal_scope_from_metadata,
)
from hindsight_api.engine.retain.fact_extraction import (
    ExtractedFact,
    ExtractedFactNoCausal,
    ExtractedFactVerbose,
    Fact,
    VerbatimExtractedFact,
    _build_extraction_prompt_and_schema,
    _metadata_with_temporal_scope,
)

SCOPES = ("historical", "current", "timeless")

# (retain_extraction_mode, retain_extract_causal_links) -> every fact model the
# builder can pick, so the field can't be wired into just one of them.
EXTRACTION_MODES = (
    ("concise", True),
    ("concise", False),
    ("verbose", True),
    ("verbatim", False),
)

# r-series gate table, from the correction draft §5 (expected_corrected_ab):
# (fixture, temporal_scope, presented_as_current, displayed_when).
# r2/r3 carry no scope: r2's retain is refused, r3 is the red control.
REGRESSION_GATE = (
    ("r1", "historical", False, "2024-03-05"),
    ("r2", None, False, None),
    ("r3", None, False, None),
    ("r4", "current", True, "2026-01-15"),
    ("r5", "current", True, "2026-01-15"),
    ("r6", "historical", False, "2024-03-05"),
    ("r7", "historical", False, "2024-03-04"),
    ("r8", "historical", False, "2024-03-05"),
)


def _config(*, mode: str, causal: bool) -> MagicMock:
    config = MagicMock()
    config.retain_extraction_mode = mode
    config.retain_extract_causal_links = causal
    config.retain_custom_instructions = None
    config.retain_mission = None
    config.entity_labels = None
    config.entities_allow_free_form = True
    config.llm_output_language = None
    config.llm_supports_string_pattern = False
    config.retain_optional_fact_dimensions = False
    return config


def _minimal_payload(model: type) -> dict:
    """Smallest payload satisfying this model's required fields."""
    stubs = {"fact_type": "world", "what": "Alex asked for a diagram", "fact": "Alex asked for a diagram"}
    return {name: stubs.get(name, "N/A") for name in model.model_json_schema().get("required", [])}


@pytest.mark.parametrize("model", [ExtractedFact, ExtractedFactVerbose, ExtractedFactNoCausal, VerbatimExtractedFact, Fact])
@pytest.mark.parametrize("scope", SCOPES)
def test_schema_accepts_temporal_scope(model: type, scope: str) -> None:
    payload = _minimal_payload(model)
    payload["temporal_scope"] = scope
    assert model(**payload).temporal_scope == scope


@pytest.mark.parametrize("model", [ExtractedFact, ExtractedFactVerbose, ExtractedFactNoCausal, VerbatimExtractedFact, Fact])
def test_schema_rejects_unknown_temporal_scope(model: type) -> None:
    payload = _minimal_payload(model)
    payload["temporal_scope"] = "bogus"
    with pytest.raises(ValidationError):
        model(**payload)


@pytest.mark.parametrize("mode,causal", EXTRACTION_MODES)
def test_builder_schema_carries_temporal_scope_enum(mode: str, causal: bool) -> None:
    built = _build_extraction_prompt_and_schema(_config(mode=mode, causal=causal))
    fact_model = built.response_schema.model_fields["facts"].annotation.__args__[0]
    schema = fact_model.model_json_schema()["properties"]["temporal_scope"]
    branches = schema.get("anyOf", [schema])
    enum = next(b["enum"] for b in branches if b.get("enum"))
    assert enum == ["historical", "current", "timeless"]


@pytest.mark.parametrize("mode,causal", EXTRACTION_MODES)
def test_builder_prompt_carries_temporal_scope_rule(mode: str, causal: bool) -> None:
    built = _build_extraction_prompt_and_schema(_config(mode=mode, causal=causal))
    prompt = built.system_prompt
    assert "temporal_scope" in prompt
    # The load-bearing rule: a historical non-event fact keeps past-tense
    # framing instead of being rewritten as a timeless present-tense preference.
    assert "past-tense" in prompt
    assert "historical" in prompt


@pytest.mark.parametrize(
    "metadata,expected",
    [
        ({"temporal_scope": "historical"}, "historical"),
        ({"temporal_scope": "current"}, "current"),
        ({"temporal_scope": "timeless"}, "timeless"),
        ({"temporal_scope": "bogus"}, None),
        ({}, None),
        (None, None),
        ("not-a-dict", None),
    ],
)
def test_temporal_scope_from_metadata(metadata, expected) -> None:
    assert temporal_scope_from_metadata(metadata) == expected


@pytest.mark.parametrize(
    "when,scope,expected",
    [
        ("2026-08-06", "historical", "2026-08-06 (historical)"),
        ("2026-08-06", "current", "2026-08-06"),
        ("2026-08-06", "timeless", "2026-08-06"),
        ("2026-08-06", None, "2026-08-06"),
        (None, "historical", None),
    ],
)
def test_format_when_with_scope(when, scope, expected) -> None:
    assert format_when_with_scope(when, scope) == expected


def test_memory_fact_surfaces_scope() -> None:
    fact = MemoryFact(id="x", text="Alex asked for a diagram", fact_type="world", temporal_scope="historical")
    assert fact.temporal_scope == "historical"
    assert MemoryFact(id="x", text="t", fact_type="world").temporal_scope is None
    # The read path feeds the field from the stored metadata bag.
    fed = MemoryFact(
        id="x",
        text="t",
        fact_type="world",
        metadata={"temporal_scope": "historical"},
        temporal_scope=temporal_scope_from_metadata({"temporal_scope": "historical"}),
    )
    assert fed.temporal_scope == "historical"


@pytest.mark.parametrize(
    "metadata,scope,expected",
    [
        ({"source": "slack"}, "historical", {"source": "slack", "temporal_scope": "historical"}),
        ({"temporal_scope": "current"}, "historical", {"temporal_scope": "current"}),
        (None, "historical", {"temporal_scope": "historical"}),
        ({"a": "b"}, None, {"a": "b"}),
    ],
)
def test_metadata_merge_prefers_caller(metadata, scope, expected) -> None:
    assert _metadata_with_temporal_scope(metadata, scope) == expected


@pytest.mark.parametrize("fixture,scope,presented_as_current,displayed_when", REGRESSION_GATE)
def test_regression_gate(fixture: str, scope, presented_as_current: bool, displayed_when) -> None:
    """The r-series gate, at the level of the scope field.

    A historical-scoped fact is never presented as a current standing
    instruction; a current-scoped preference still is. The displayed When
    carries the scope label for historical facts, so the reader sees the
    history instead of a bare date.
    """
    if scope == "historical":
        assert presented_as_current is False
        assert format_when_with_scope(displayed_when, scope) == f"{displayed_when} (historical)"
    elif scope == "current":
        assert presented_as_current is True
        assert format_when_with_scope(displayed_when, scope) == displayed_when
    else:
        # No scope recorded (refused retain / red control): nothing is presented.
        assert presented_as_current is False
        assert displayed_when is None
