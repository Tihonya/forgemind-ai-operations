"""Dataset metadata and expected entity counts for Golden Dataset verification.

This module defines the canonical dataset version, checksum algorithm, and
expected entity counts for each collection in Golden Dataset V1.0.

These constants are used by the dataset integrity service to verify that the
database contains the exact expected dataset after seeding.
"""

# Dataset version identifier
DATASET_VERSION: str = "GOLDEN_DATASET_V1.0"

# Checksum algorithm identifier
CHECKSUM_ALGORITHM: str = "sha256:v1"

# Expected entity counts for Golden Dataset V1.0
# These counts must match exactly what generate_golden_dataset() produces
EXPECTED_ENTITY_COUNTS = {
    "products": 1,
    "product_versions": 3,
    "components": 5,
    "bom_items": 9,
    "warehouses": 1,
    "inventory_balances": 5,
    "suppliers": 3,
    "production_plans": 1,
    "production_orders": 3,
    "inventory_reservations": 0,
    "purchase_orders": 3,
    "purchase_order_lines": 3,
    "production_order_requirements": 9,
    "component_alternatives": 1,
}

# Expected checksum placeholder - will be computed and set after implementation
EXPECTED_CHECKSUM: str = "sha256:840c235cb9a431b2906471270b2d1b8c7e487b9912c64d72a5fff773039172dc"

# Canonicalization v1 specification:
#
# Entity ordering (must match this exact sequence):
#   1. products (sorted by code)
#   2. product_versions (sorted by product_code, version)
#   3. components (sorted by code)
#   4. bom_items (sorted by product_code, product_version, component_code)
#   5. warehouses (sorted by code)
#   6. inventory_balances (sorted by component_code, warehouse_code)
#   7. suppliers (sorted by code)
#   8. production_plans (sorted by code)
#   9. production_orders (sorted by code)
#   10. inventory_reservations (sorted by production_order_code, component_code, warehouse_code)
#   11. purchase_orders (sorted by po_number)
#   12. purchase_order_lines (sorted by po_number, component_code)
#   13. production_order_requirements (sorted by production_order_code, component_code)
#   14. component_alternatives (sorted by component_code, alternative_component_code)
#
# Field ordering (alphabetical within each entity)
# JSON serialization: compact separators (",",":"), no trailing newline, UTF-8
# Null handling: JSON null
# Enum handling: string values
# Date handling: ISO 8601 format (YYYY-MM-DD)
# Datetime handling: ISO 8601 with timezone (YYYY-MM-DDTHH:MM:SS+00:00)
# Decimal handling: string representation, normalized (no trailing zeros)
# Boolean handling: JSON booleans (true/false)
# UUID handling: lowercase string with hyphens
#
# Relationship handling:
#   All foreign key relationships are represented using business keys:
#   - product_version: product_code + version
#   - bom_item: product_code + product_version + component_code
#   - inventory_balance: component_code + warehouse_code
#   - inventory_reservation: production_order_code + component_code + warehouse_code
#   - purchase_order: po_number + supplier_code
#   - purchase_order_line: po_number + component_code
#   - production_order: production_order_code + product_code + product_version
#   - production_order_requirement: production_order_code + component_code
#   - component_alternative: component_code + alternative_component_code
#
# Excluded fields:
#   - created_at, updated_at (volatile, not part of fixture semantics)
#   - id (surrogate primary key, not business-meaningful)
#   - database-generated values not part of fixture semantics
