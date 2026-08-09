"""Unit tests for the recommendation Pydantic wire schema (WP-REC-03C).

Tests cover:
- Valid schema accepted
- Required fields enforced
- Wrong types rejected
- Extra fields rejected (strict mode)
- Schema version "1.0" accepted
- Unsupported schema version rejected
- Valid source citation accepted
- Malformed chunk_id rejected
- Required sources field enforced
- Empty sources list structurally accepted without grounding claim
- Deterministic quantity fields are not in the AI-owned contract
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.recommendation import (
    RECOMMENDATION_SCHEMA_VERSION,
    RecommendationData,
    RiskItem,
    Source,
)

# A canonical valid UUID string for testing.
_VALID_RUN_ID = "12345678-1234-4000-8000-000000000001"
_VALID_CHUNK_ID = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"


def _valid_risk_item(**overrides: object) -> dict[str, object]:
    """Return a valid risk-item dict with optional field overrides."""
    item: dict[str, object] = {
        "risk_id": "RISK-001",
        "summary": "Critical shortage of CTRL-X4",
        "business_impact": "Production line stoppage",
        "recommended_actions": [
            {
                "action_type": "CREATE_PROCUREMENT_TASK",
                "title": "Emergency procurement of CTRL-X4",
                "rationale": "8-unit shortage blocks production order WO-2026-0142",
                "requires_approval": True,
            },
        ],
        "sources": [
            {
                "document_id": "DOC-001",
                "version": "2.1",
                "chunk_id": _VALID_CHUNK_ID,
            },
        ],
    }
    item.update(overrides)
    return item


def _valid_recommendation(**overrides: object) -> dict[str, object]:
    """Return a valid recommendation dict with optional field overrides."""
    rec: dict[str, object] = {
        "schema_version": "1.0",
        "run_id": _VALID_RUN_ID,
        "plan_id": "PLAN-2026-W31",
        "risks": [_valid_risk_item()],
    }
    rec.update(overrides)
    return rec


class TestRecommendationDataValid:
    """Verify that structurally valid recommendations are accepted."""

    def test_valid_recommendation_accepted(self) -> None:
        rec = RecommendationData.model_validate(_valid_recommendation())
        assert rec.schema_version == "1.0"
        assert str(rec.run_id) == _VALID_RUN_ID
        assert rec.plan_id == "PLAN-2026-W31"
        assert len(rec.risks) == 1
        risk = rec.risks[0]
        assert risk.risk_id == "RISK-001"
        assert risk.summary == "Critical shortage of CTRL-X4"
        assert risk.business_impact == "Production line stoppage"
        assert len(risk.recommended_actions) == 1
        action = risk.recommended_actions[0]
        assert action.action_type == "CREATE_PROCUREMENT_TASK"
        assert action.requires_approval is True
        assert len(risk.sources) == 1
        source = risk.sources[0]
        assert source.document_id == "DOC-001"
        assert source.version == "2.1"

    def test_schema_version_constant(self) -> None:
        assert RECOMMENDATION_SCHEMA_VERSION == "1.0"

    def test_multiple_risks_accepted(self) -> None:
        rec = RecommendationData.model_validate(
            _valid_recommendation(
                risks=[_valid_risk_item(risk_id="RISK-001"), _valid_risk_item(risk_id="RISK-002")],
            ),
        )
        assert len(rec.risks) == 2

    def test_empty_sources_structurally_accepted(self) -> None:
        """Empty sources are structurally valid but must not be grounded."""
        rec = RecommendationData.model_validate(
            _valid_recommendation(
                risks=[_valid_risk_item(sources=[])],
            ),
        )
        assert rec.risks[0].sources == []

    def test_empty_recommended_actions_accepted(self) -> None:
        """An empty actions list is structurally valid."""
        rec = RecommendationData.model_validate(
            _valid_recommendation(
                risks=[_valid_risk_item(recommended_actions=[])],
            ),
        )
        assert rec.risks[0].recommended_actions == []


class TestRequiredFieldsEnforced:
    """Verify that missing required fields are rejected."""

    def test_missing_schema_version_rejected(self) -> None:
        data = _valid_recommendation()
        del data["schema_version"]
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(data)

    def test_missing_run_id_rejected(self) -> None:
        data = _valid_recommendation()
        del data["run_id"]
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(data)

    def test_missing_plan_id_rejected(self) -> None:
        data = _valid_recommendation()
        del data["plan_id"]
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(data)

    def test_missing_risks_rejected(self) -> None:
        data = _valid_recommendation()
        del data["risks"]
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(data)

    def test_empty_risks_rejected(self) -> None:
        """risks must contain at least one item."""
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(_valid_recommendation(risks=[]))

    def test_missing_risk_id_in_item_rejected(self) -> None:
        item = _valid_risk_item()
        del item["risk_id"]
        with pytest.raises(ValidationError):
            RiskItem.model_validate(item)

    def test_missing_sources_in_item_rejected(self) -> None:
        """sources field is required even if empty."""
        item = _valid_risk_item()
        del item["sources"]
        with pytest.raises(ValidationError):
            RiskItem.model_validate(item)

    def test_missing_requires_approval_rejected(self) -> None:
        item = _valid_risk_item()
        del item["recommended_actions"][0]["requires_approval"]  # type: ignore[attr-defined]
        with pytest.raises(ValidationError):
            RiskItem.model_validate(item)


class TestWrongTypesRejected:
    """Verify that wrong types are rejected."""

    def test_run_id_wrong_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(
                _valid_recommendation(run_id="not-a-uuid"),
            )

    def test_requires_approval_wrong_type_rejected(self) -> None:
        item = _valid_risk_item()
        item["recommended_actions"][0]["requires_approval"] = []  # type: ignore[assignment]
        with pytest.raises(ValidationError):
            RiskItem.model_validate(item)

    def test_risks_wrong_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(
                _valid_recommendation(risks="not-a-list"),  # type: ignore[arg-type]
            )


class TestExtraFieldsRejected:
    """Verify that extra fields are rejected (strict mode)."""

    def test_extra_top_level_field_rejected(self) -> None:
        data = _valid_recommendation()
        data["unexpected_field"] = "surprise"
        with pytest.raises(ValidationError) as exc_info:
            RecommendationData.model_validate(data)
        assert "extra_forbidden" in str(exc_info.value)

    def test_extra_field_in_risk_item_rejected(self) -> None:
        item = _valid_risk_item()
        item["extra"] = "value"
        with pytest.raises(ValidationError) as exc_info:
            RiskItem.model_validate(item)
        assert "extra_forbidden" in str(exc_info.value)

    def test_extra_field_in_source_rejected(self) -> None:
        src = {
            "document_id": "DOC-001",
            "version": "2.1",
            "chunk_id": _VALID_CHUNK_ID,
            "extra": "no",
        }
        with pytest.raises(ValidationError) as exc_info:
            Source.model_validate(src)
        assert "extra_forbidden" in str(exc_info.value)


class TestSchemaVersionEnforcement:
    """Verify schema version constraints."""

    def test_version_1_0_accepted(self) -> None:
        rec = RecommendationData.model_validate(_valid_recommendation())
        assert rec.schema_version == "1.0"

    def test_unsupported_version_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(
                _valid_recommendation(schema_version="2.0"),
            )

    def test_unsupported_version_numeric_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationData.model_validate(
                _valid_recommendation(schema_version=1.0),  # type: ignore[arg-type]
            )


class TestSourceCitationValidation:
    """Verify source citation format validation."""

    def test_valid_source_accepted(self) -> None:
        src = Source.model_validate({
            "document_id": "DOC-001",
            "version": "2.1",
            "chunk_id": _VALID_CHUNK_ID,
        })
        assert src.document_id == "DOC-001"

    def test_malformed_chunk_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Source.model_validate({
                "document_id": "DOC-001",
                "version": "2.1",
                "chunk_id": "not-a-uuid",
            })

    def test_empty_document_id_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Source.model_validate({
                "document_id": "",
                "version": "2.1",
                "chunk_id": _VALID_CHUNK_ID,
            })

    def test_empty_version_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Source.model_validate({
                "document_id": "DOC-001",
                "version": "",
                "chunk_id": _VALID_CHUNK_ID,
            })


class TestDeterministicQuantityExclusion:
    """Verify that deterministic quantity fields are not in the AI-owned schema.

    DEC-004 and DEC-039 (TD-4): deterministic code owns quantities (shortage,
    available, severity). The AI recommendation schema must not include these
    fields — the AI enriches with explanations and recommendations only.

    This test verifies the schema contract by confirming that adding such
    fields is rejected as extra fields (strict mode).
    """

    def test_shortage_field_rejected_as_extra(self) -> None:
        item = _valid_risk_item()
        item["shortage"] = 8  # type: ignore[assignment]
        with pytest.raises(ValidationError) as exc_info:
            RiskItem.model_validate(item)
        assert "extra_forbidden" in str(exc_info.value)

    def test_severity_field_rejected_as_extra(self) -> None:
        item = _valid_risk_item()
        item["severity"] = "CRITICAL"  # type: ignore[assignment]
        with pytest.raises(ValidationError) as exc_info:
            RiskItem.model_validate(item)
        assert "extra_forbidden" in str(exc_info.value)

    def test_available_quantity_field_rejected_as_extra(self) -> None:
        item = _valid_risk_item()
        item["available"] = 12  # type: ignore[assignment]
        with pytest.raises(ValidationError) as exc_info:
            RiskItem.model_validate(item)
        assert "extra_forbidden" in str(exc_info.value)
