"""Unit tests for dataset integrity service and canonicalization."""
from collections import OrderedDict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from app.core.compute_expected_checksum import (
    canonicalize_dataset,
    compute_checksum,
)
from app.services.dataset_integrity import _serialize_value


class TestSerializeValue:
    """Test canonicalization of individual values."""

    def test_serialize_none(self) -> None:
        assert _serialize_value(None) is None

    def test_serialize_boolean_true(self) -> None:
        assert _serialize_value(True) is True

    def test_serialize_boolean_false(self) -> None:
        assert _serialize_value(False) is False

    def test_serialize_int(self) -> None:
        # int is returned as-is (json.dumps serializes it natively)
        assert _serialize_value(42) == 42

    def test_serialize_float(self) -> None:
        # float is returned as-is (json.dumps serializes it natively)
        assert _serialize_value(3.14) == 3.14

    def test_serialize_string(self) -> None:
        assert _serialize_value("test") == "test"

    def test_serialize_decimal_whole_number(self) -> None:
        """Decimal with no fractional part should serialize as integer string."""
        value = Decimal("20.0000")
        result = _serialize_value(value)
        assert result == "20"
        assert isinstance(result, str)

    def test_serialize_decimal_with_fraction(self) -> None:
        """Decimal with fractional part should preserve significant digits."""
        value = Decimal("10.5000")
        result = _serialize_value(value)
        assert result == "10.5"
        assert isinstance(result, str)

    def test_serialize_decimal_no_trailing_zeros(self) -> None:
        """Normalization should remove insignificant trailing zeros."""
        value = Decimal("100.000")
        result = _serialize_value(value)
        assert result == "100"

    def test_serialize_date(self) -> None:
        """Date should serialize as ISO-8601 string."""
        value = date(2026, 8, 3)
        result = _serialize_value(value)
        assert result == "2026-08-03"

    def test_serialize_datetime_utc(self) -> None:
        """Datetime with UTC timezone should serialize with Z suffix."""
        value = datetime(2026, 7, 28, 9, 0, 0, tzinfo=UTC)
        result = _serialize_value(value)
        assert result == "2026-07-28T09:00:00Z"

    def test_serialize_datetime_with_timezone(self) -> None:
        """Datetime with non-UTC timezone should convert to UTC."""
        from datetime import timedelta, timezone

        tz = timezone(timedelta(hours=2))
        # Create a datetime in UTC+2
        value = datetime(2026, 7, 28, 11, 0, 0, tzinfo=tz)
        result = _serialize_value(value)
        # Should convert to UTC (subtract 2 hours)
        assert result == "2026-07-28T09:00:00Z"

    def test_serialize_datetime_naive(self) -> None:
        """Naive datetime should be treated as UTC."""
        value = datetime(2026, 7, 28, 9, 0, 0)  # noqa: DTZ001
        result = _serialize_value(value)
        # Naive datetime is treated as UTC
        assert result == "2026-07-28T09:00:00Z"


def _full_dataset(**overrides: Any) -> OrderedDict[str, Any]:
    """Build a full empty dataset, optionally overriding specific keys."""
    base: OrderedDict[str, Any] = OrderedDict([
        ("products", []),
        ("product_versions", []),
        ("components", []),
        ("bom_items", []),
        ("warehouses", []),
        ("inventory_balances", []),
        ("suppliers", []),
        ("production_plans", []),
        ("production_orders", []),
        ("inventory_reservations", []),
        ("purchase_orders", []),
        ("purchase_order_lines", []),
        ("production_order_requirements", []),
        ("component_alternatives", []),
    ])
    base.update(overrides)
    return base


class TestCanonicalizeDataset:
    """Test canonicalization of complete dataset."""

    def test_deterministic_ordering(self) -> None:
        """Products should be sorted by code regardless of input order."""
        dataset = _full_dataset(
            products=[
                {"id": "uuid1", "code": "PROD-B", "name": "Product B", "description": None},
                {"id": "uuid2", "code": "PROD-A", "name": "Product A", "description": None},
            ]
        )
        result = canonicalize_dataset(dataset)
        assert result["products"][0]["code"] == "PROD-A"
        assert result["products"][1]["code"] == "PROD-B"

    def test_business_key_resolution(self) -> None:
        """Component alternatives should resolve IDs to business keys."""
        comp1_id = "comp1"
        comp2_id = "comp2"
        dataset = _full_dataset(
            components=[
                {"id": comp1_id, "code": "COMP-A", "name": "A", "unit": "PCS", "description": None},
                {"id": comp2_id, "code": "COMP-B", "name": "B", "unit": "PCS", "description": None},
            ],
            component_alternatives=[
                {
                    "id": "alt1",
                    "component_id": comp1_id,
                    "alternative_component_id": comp2_id,
                    "status": "PROPOSED",
                    "rationale": "Alternative rationale",
                }
            ],
        )
        result = canonicalize_dataset(dataset)
        alt = result["component_alternatives"][0]
        assert alt["component_code"] == "COMP-A"
        assert alt["alternative_component_code"] == "COMP-B"

    def test_excludes_surrogate_ids(self) -> None:
        """Canonical output for products should not contain surrogate primary keys."""
        dataset = _full_dataset(
            products=[
                {"id": "prod1", "code": "PROD-001", "name": "Product", "description": None}
            ]
        )
        result = canonicalize_dataset(dataset)
        product = result["products"][0]
        assert "id" not in product
        assert "code" in product

    def test_excludes_timestamps(self) -> None:
        """Canonical output should exclude created_at and other timestamps."""
        dataset = _full_dataset(
            production_plans=[
                {
                    "id": "plan1",
                    "code": "PLAN-001",
                    "status": "ACTIVE",
                    "period_start": date(2026, 1, 1),
                    "period_end": date(2026, 12, 31),
                    "created_at": datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
                }
            ]
        )
        result = canonicalize_dataset(dataset)
        plan = result["production_plans"][0]
        assert "created_at" not in plan
        assert "code" in plan


class TestComputeChecksum:
    """Test checksum computation."""

    def test_deterministic_checksum(self) -> None:
        """Same canonical data should produce same checksum."""
        canonical: OrderedDict[str, Any] = OrderedDict([
            ("products", [{"code": "PROD-001", "name": "Product", "description": None}]),
            ("product_versions", []),
            ("components", []),
            ("bom_items", []),
            ("warehouses", []),
            ("inventory_balances", []),
            ("suppliers", []),
            ("production_plans", []),
            ("production_orders", []),
            ("inventory_reservations", []),
            ("purchase_orders", []),
            ("purchase_order_lines", []),
            ("production_order_requirements", []),
            ("component_alternatives", []),
        ])
        checksum1 = compute_checksum(canonical)
        checksum2 = compute_checksum(canonical)
        assert checksum1 == checksum2
        assert checksum1.startswith("sha256:")
        assert len(checksum1) == 71  # "sha256:" (7) + 64 hex chars

    def test_checksum_changes_with_data(self) -> None:
        """Different data should produce different checksums."""
        canonical1: OrderedDict[str, Any] = OrderedDict([
            ("products", [{"code": "PROD-001", "name": "Product A", "description": None}]),
            ("product_versions", []),
            ("components", []),
            ("bom_items", []),
            ("warehouses", []),
            ("inventory_balances", []),
            ("suppliers", []),
            ("production_plans", []),
            ("production_orders", []),
            ("inventory_reservations", []),
            ("purchase_orders", []),
            ("purchase_order_lines", []),
            ("production_order_requirements", []),
            ("component_alternatives", []),
        ])
        canonical2: OrderedDict[str, Any] = OrderedDict([
            ("products", [{"code": "PROD-002", "name": "Product B", "description": None}]),
            ("product_versions", []),
            ("components", []),
            ("bom_items", []),
            ("warehouses", []),
            ("inventory_balances", []),
            ("suppliers", []),
            ("production_plans", []),
            ("production_orders", []),
            ("inventory_reservations", []),
            ("purchase_orders", []),
            ("purchase_order_lines", []),
            ("production_order_requirements", []),
            ("component_alternatives", []),
        ])
        checksum1 = compute_checksum(canonical1)
        checksum2 = compute_checksum(canonical2)
        assert checksum1 != checksum2


class TestGoldenDatasetChecksum:
    """Test that Golden Dataset produces expected checksum."""

    def test_golden_dataset_checksum(self) -> None:
        """Golden Dataset should produce the expected checksum."""
        from app.seed.generator.golden_dataset import generate_golden_dataset

        dataset = generate_golden_dataset()
        canonical = canonicalize_dataset(dataset)
        checksum = compute_checksum(canonical)

        # This is the checksum we computed and stored in dataset_metadata.py
        from app.core.dataset_metadata import EXPECTED_CHECKSUM

        assert checksum == EXPECTED_CHECKSUM
        assert checksum.startswith("sha256:")
