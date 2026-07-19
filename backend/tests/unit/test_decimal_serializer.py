"""Unit tests for Decimal serialization in RiskRecordWithId.

Tests the format_decimal_4 function and DecimalStr4 type to ensure:
- Exact 4 decimal places
- No float conversion (precision preserved)
- Edge cases handled correctly
"""

from __future__ import annotations

from decimal import Decimal

from app.schemas.risk_response import format_decimal_4


class TestFormatDecimal4:
    """Test the format_decimal_4 function directly."""

    def test_integer_input(self) -> None:
        """Decimal('20') -> '20.0000'"""
        result = format_decimal_4(Decimal("20"))
        assert result == "20.0000"

    def test_zero(self) -> None:
        """Decimal('0') -> '0.0000'"""
        result = format_decimal_4(Decimal("0"))
        assert result == "0.0000"

    def test_exact_four_decimals(self) -> None:
        """Decimal('10.0000') -> '10.0000'"""
        result = format_decimal_4(Decimal("10.0000"))
        assert result == "10.0000"

    def test_one_decimal_place(self) -> None:
        """Decimal('12.3') -> '12.3000'"""
        result = format_decimal_4(Decimal("12.3"))
        assert result == "12.3000"

    def test_two_decimal_places(self) -> None:
        """Decimal('12.34') -> '12.3400'"""
        result = format_decimal_4(Decimal("12.34"))
        assert result == "12.3400"

    def test_three_decimal_places(self) -> None:
        """Decimal('12.345') -> '12.3450'"""
        result = format_decimal_4(Decimal("12.345"))
        assert result == "12.3450"

    def test_four_decimal_places_exact(self) -> None:
        """Decimal('0.0001') -> '0.0001'"""
        result = format_decimal_4(Decimal("0.0001"))
        assert result == "0.0001"

    def test_five_decimal_places_rounds(self) -> None:
        """Decimal('12.34567') -> '12.3457' (rounds to 4 places)"""
        result = format_decimal_4(Decimal("12.34567"))
        assert result == "12.3457"

    def test_arbitrary_precision_large_integer(self) -> None:
        """Large integer: Decimal('12345678901234567890') -> '12345678901234567890.0000'"""
        result = format_decimal_4(Decimal("12345678901234567890"))
        assert result == "12345678901234567890.0000"

    def test_arbitrary_precision_large_decimal(self) -> None:
        """Large decimal: Decimal('12345678901234567890.1234') -> '12345678901234567890.1234'"""
        result = format_decimal_4(Decimal("12345678901234567890.1234"))
        assert result == "12345678901234567890.1234"

    def test_very_large_number(self) -> None:
        """Very large number: Decimal('99999999999999999999.9999') -> exact string"""
        result = format_decimal_4(Decimal("99999999999999999999.9999"))
        assert result == "99999999999999999999.9999"

    def test_negative_zero(self) -> None:
        """Decimal('-0') -> '-0.0000' or '0.0000' (implementation-dependent)"""
        result = format_decimal_4(Decimal("-0"))
        # Python's format() preserves sign for negative zero
        assert result in ("-0.0000", "0.0000")

    def test_negative_value(self) -> None:
        """Decimal('-12.34') -> '-12.3400'"""
        result = format_decimal_4(Decimal("-12.34"))
        assert result == "-12.3400"

    def test_scientific_notation_input(self) -> None:
        """Decimal('1E-4') -> '0.0001'"""
        result = format_decimal_4(Decimal("1E-4"))
        assert result == "0.0001"

    def test_scientific_notation_large(self) -> None:
        """Decimal('1E+10') -> '10000000000.0000'"""
        result = format_decimal_4(Decimal("1E+10"))
        assert result == "10000000000.0000"


class TestNoFloatConversion:
    """Prove that no float conversion occurs in the serializer."""

    def test_precision_beyond_float(self) -> None:
        """Decimal with more precision than float can represent:
        Decimal('0.12345678901234567890') should round to '0.1235' (4 decimal places)
        without ever going through float representation.

        If float() were used: Decimal('0.12345678901234567890') -> float(0.12345...) -> '0.1235'
        But the intermediate float would be 0.12345678901234568 (limited to ~17 sig digits)

        This test verifies the output is correct, but the real proof is in the source code.
        """
        # This value has 20 significant digits - more than float can represent
        value = Decimal("0.12345678901234567890")
        result = format_decimal_4(value)
        assert result == "0.1235"

    def test_large_value_precision_loss(self) -> None:
        """Test that large values don't lose precision through float conversion.

        Decimal('1234567890.123456789') has 19 significant digits.
        float can only represent ~15-17 significant digits.

        If format_decimal_4 used float():
          float(Decimal('1234567890.123456789')) = 1234567890.1234567 (loses precision)
          format(1234567890.1234567, '.4f') = '1234567890.1235'

        But with Decimal-native format():
          format(Decimal('1234567890.123456789'), '.4f') = '1234567890.1235'

        Both should give the same result when rounding to 4 places, but the
        Decimal path is correct by construction, not by accident.
        """
        value = Decimal("1234567890.123456789")
        result = format_decimal_4(value)
        assert result == "1234567890.1235"

    def test_source_code_has_no_float_call(self) -> None:
        """Verify the source code of format_decimal_4 doesn't call float().

        This is a meta-test that inspects the AST to prove no float()
        conversion is used in the actual code (not just in comments/docstrings).
        """
        import ast
        import inspect

        from app.schemas.risk_response import format_decimal_4

        def contains_float_call(tree: ast.AST) -> bool:
            """Check if the AST contains any float() function calls."""
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Check for direct float() call
                    if isinstance(node.func, ast.Name) and node.func.id == "float":
                        return True
                    # Check for float() call via attribute (e.g., builtins.float())
                    if isinstance(node.func, ast.Attribute) and node.func.attr == "float":
                        return True
            return False

        source = inspect.getsource(format_decimal_4)
        tree = ast.parse(source)
        # Check that the AST doesn't contain any float() calls
        assert not contains_float_call(tree), (
            "format_decimal_4 must not call float() - "
            "use format(value, '.4f') instead to preserve Decimal precision"
        )


class TestDecimalStr4Type:
    """Test the DecimalStr4 annotated type in Pydantic models."""

    def test_serialize_via_pydantic(self) -> None:
        """Verify DecimalStr4 serializes correctly through Pydantic."""
        from pydantic import BaseModel

        from app.schemas.risk_response import DecimalStr4

        class TestModel(BaseModel):
            value: DecimalStr4

        model = TestModel(value=Decimal("12.34"))
        serialized = model.model_dump(mode="json")
        assert serialized["value"] == "12.3400"

    def test_serialize_large_value_via_pydantic(self) -> None:
        """Verify DecimalStr4 preserves precision through Pydantic."""
        from pydantic import BaseModel

        from app.schemas.risk_response import DecimalStr4

        class TestModel(BaseModel):
            value: DecimalStr4

        model = TestModel(value=Decimal("12345678901234567890.1234"))
        serialized = model.model_dump(mode="json")
        assert serialized["value"] == "12345678901234567890.1234"
