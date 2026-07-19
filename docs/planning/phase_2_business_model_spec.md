# Phase 2 — Canonical Business Data Model Specification

**Scope:** Phase 2 entities only (Synthetic ERP Core + deterministic risk engine).  
**Purpose:** Define the conceptual business model before SQLAlchemy models or migrations.  
**Status:** Accepted (validated during Phase 2 planning review, 2026-07-17).  
**Date:** 2026-07-17  
**Reference:** Source of Truth `02_SYSTEM_BEHAVIOR_AND_DATA.md` §3 §4 §5.

---

## 1. Entities in Phase 2

Phase 2 implements the **Synthetic ERP Core** — every entity needed to compute RISK-001, RISK-002, RISK-003 deterministically, plus users/roles for authentication (DEC-009, DEC-028).

### 1.1 Business entities (ERP)

| Entity | Purpose | Phase |
|---|---|---|
| `products` | Top-level finished goods (e.g., "Industrial Pump MK-III") | 2 |
| `product_versions` | A distinct release of a product BOM (one product → many versions) | 2 |
| `components` | Discrete components (CTRL-X4, MOTOR-M2, SENSOR-L9) | 2 |
| `bom_items` | Link (product_version, component, quantity-per-unit) | 2 |
| `warehouses` | Named stock locations | 2 |
| `inventory_balances` | Per (component, warehouse) on-hand quantity | 2 |
| `inventory_reservations` | Per (component, warehouse, production_order) reserved quantity | 2 |
| `suppliers` | Named suppliers | 2 |
| `purchase_orders` | A purchase order header (supplier, order number, status) | 2 |
| `purchase_order_lines` | One line per (PO, component): ordered quantity, expected delivery date, status | 2 |
| `production_plans` | A plan header, e.g., `PLAN-2026-W31` | 2 |
| `production_orders` | A work order under a plan, with need date | 2 |
| `production_order_requirements` | A demand line: how many units of product_version are needed by when for a given WO | 2 |
| `component_alternatives` | Approved or draft alternative for a component (alternative_component_id, status) — **structural**, not tied to documents in Phase 2 | 2 |

### 1.2 Auth / RBAC entities

| Entity | Purpose | Phase |
|---|---|---|
| `users` | Demo account identity, hashed password (or demo token) | 2 |
| `roles` | Role definitions (enum): Production Manager, Procurement Specialist, Engineer, AI Administrator, Auditor | 2 |
| `user_roles` | Multi-role capable mapping (user_id, role_id); in Phase 2 each demo account receives exactly one (DEC-028). | 2 |

### 1.3 Entities explicitly deferred

| Entity | Deferred to | Reason |
|---|---|---|
| `document_versions`, `documents`, `document_permissions`, `knowledge_chunks` | Phase 4 | RAG / retrieval / document-level auth |
| `procurement_tasks` | Phase 6 | Approval + write-action flow |
| `approval_requests` | Phase 6 | Human approval loop |
| `audit_events` | Phase 6 | Audit trail |
| `workflow_runs`, `workflow_steps`, `retrieval_events`, `model_calls` | Phase 5 | AI workflow / LLM |
| `agent_definitions`, `agent_versions` | Phase 5 | AI workflow |

`component_alternatives` is kept in Phase 2 because severity rules (`02 §5`) require existence of a candidate alternative to compute RISK-003 (MEDIUM) — this is a structural property of the component catalog, not of document retrieval.

**Phase 2 boundary for `component_alternatives` (planning clarification, derived from DEC-004 + Phase 2 zero-LLM constraint + Phase 4 RAG scope):**

- `component_alternatives` is a deterministic business projection of an engineering alternative and its approval status.
- Phase 2 seed data contains an alternative candidate for `SENSOR-L9` with status `PROPOSED` (explicitly unapproved). This causes the relevant shortage risk to be `MEDIUM`.
- The Phase 2 risk engine reads only deterministic structured data from relational tables. No document retrieval, chunks, embeddings, or RAG.
- Phase 4 adds actual document entities (`documents`, `document_versions`, `document_permissions`, `knowledge_chunks`), document-level permissions, retrieval and citations. Phase 4 must verify the documentary evidence behind the structural alternative — it does not redefine the Phase 2 arithmetic.

---

## 2. Fields & data types (conceptual)

### `products`
- `id` PK (bigint surrogate)
- `code` UK (string, natural identifier, e.g. `PROD-PUMP-001`)
- `name` (string)
- `description` (text, optional)

### `product_versions`
- `id` PK
- `product_id` FK → `products`
- `version` UK (within product, e.g. `"2.1"`)
- `status` enum [`DRAFT`, `RELEASED`, `OBSOLETE`]

### `components`
- `id` PK
- `code` UK (string, natural — `CTRL-X4`, `MOTOR-M2`, `SENSOR-L9`)
- `name`
- `unit` enum [`PCS`, `KG`, `M`, `L`]
- `description` (optional)

### `bom_items`
- `id` PK
- `product_version_id` FK → `product_versions`
- `component_id` FK → `components`
- `quantity_per_unit` decimal(18,4) — number of this component required to build one unit of the product
- UK (product_version_id, component_id)

### `warehouses`
- `id` PK
- `code` UK (e.g. `WH-MAIN`)
- `name`

### `inventory_balances`
- `id` PK
- `component_id` FK → `components`
- `warehouse_id` FK → `warehouses`
- `quantity_on_hand` decimal(18,4)
- UK (component_id, warehouse_id)

### `inventory_reservations`
- `id` PK
- `component_id` FK → `components`
- `warehouse_id` FK → `warehouses`
- `production_order_id` FK → `production_orders`
- `quantity` decimal(18,4)

### `suppliers`
- `id` PK
- `code` UK
- `name`

### `purchase_orders`
- `id` PK
- `supplier_id` FK → `suppliers`
- `po_number` UK (string, e.g. `PO-2026-0421`)
- `status` enum [`PLACED`, `CONFIRMED`, `CANCELLED`, `RECEIVED`]
- `placed_at` timestamp

### `purchase_order_lines`
- `id` PK
- `purchase_order_id` FK → `purchase_orders`
- `component_id` FK → `components`
- `ordered_quantity` decimal(18,4)
- `received_quantity` decimal(18,4), default 0
- `expected_delivery_date` date
- `status` enum [`PENDING`, `CONFIRMED`, `IN_TRANSIT`, `DELIVERED`, `CANCELLED`]

### `production_plans`
- `id` PK
- `code` UK (string, e.g. `PLAN-2026-W31`)
- `status` enum [`DRAFT`, `APPROVED`, `EXECUTING`, `COMPLETED`, `CLOSED`]
- `created_at` timestamp
- `period_start` date
- `period_end` date

### `production_orders` (work orders)
- `id` PK
- `production_plan_id` FK → `production_plans`
- `code` UK (string, e.g. `WO-2026-0142`)
- `product_version_id` FK → `product_versions`
- `quantity` decimal(18,4) — number of finished units to produce
- `need_date` date
- `status` enum [`PLANNED`, `RELEASED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`]

### `production_order_requirements`
- `id` PK
- `production_order_id` FK → `production_orders`
- `component_id` FK → `components`
- `required_quantity` decimal(18,4) — denormalized for performance (derivable from BOM × WO.quantity)
- `reserved_quantity` decimal(18,4) — sum of inventory_reservations for this WO/component

### `component_alternatives`
- `id` PK
- `component_id` FK → `components`
- `alternative_component_id` FK → `components`
- `status` enum [`PROPOSED`, `APPROVED`, `REJECTED`]
- `rationale` (text, optional)
- UK (component_id, alternative_component_id)

### `users`
- `id` PK
- `username` UK (string, e.g. `manager.demo`)
- `hashed_password` text (or demo-equivalent credential)
- `display_name`
- `is_active` bool

### `roles`
- `id` PK
- `code` UK (`PRODUCTION_MANAGER`, `PROCUREMENT_SPECIALIST`, `ENGINEER`, `AI_ADMINISTRATOR`, `AUDITOR`)
- `name`

### `user_roles`
- `id` PK
- `user_id` FK → `users`
- `role_id` FK → `roles`
- UK (user_id, role_id)

---

## 3. Quantity & date semantics

- All quantities use decimal(18,4) to avoid floating-point drift in totals.
- All dates are calendar days (ISO 8601). Timestamps are UTC (Postgres `timestamp with time zone`).
- Comparisons across dates are performed as date ≤ date (not datetime).
- `need_date` is the latest day the component must be on the production floor.
- `expected_delivery_date` is the date a purchase-order line is expected to arrive at the warehouse.

## 4. Inventory & reservation semantics

- `inventory_balances.quantity_on_hand` = what is physically in the warehouse.
- `inventory_reservations.quantity` = what has been earmarked for a production order.
- `inventory_reservations` carries no independent status field; reservation validity is derived from the parent production order's status (cancelled/released orders' reservations are inactive).

**Reservation status derivation:**

| Parent production order status | Reservation status | Effect on availability |
|---|---|---|
| `PLANNED`, `RELEASED`, `IN_PROGRESS` | active | reduces available for OTHER orders |
| `COMPLETED`, `CANCELLED` | inactive | ignored in availability calculation |

**Canonical availability rule (single source of truth):**

For analysis of production order `WO-X` and component `C`:

```text
available_for_WO_X =
    quantity_on_hand(C)
    − sum(r.quantity for r in inventory_reservations
          where r.component_id == C
          and r.production_order_id != WO-X.id
          and parent_order(r.production_order_id).status in (PLANNED, RELEASED, IN_PROGRESS))
```

The current order's own reservation is NOT subtracted — the order being analysed is the one claiming this availability.

**Unit-of-measure consistency:** All quantities referencing the same component must use the same unit (`components.unit`). Cross-unit reservations are rejected at the schema layer. The Golden Dataset uses only `PCS` for all three risk components.

**No double subtraction:** The sum excludes the current WO's reservation to avoid counting the same demand twice.

## 5. Purchase-order delivery semantics

### 5.0 Status enums (canonical)

**`purchase_orders.status` (header):** `PLACED`, `CONFIRMED`, `CANCELLED`, `RECEIVED`

**`purchase_order_lines.status` (line):** `PENDING`, `CONFIRMED`, `IN_TRANSIT`, `DELIVERED`, `CANCELLED`

`RECEIVED` is a header status, not a line status.
`DELIVERED` is a line status, not a header status.

### 5.1 Quantity calculation (shortage reduction)

A purchase-order line contributes to confirmed incoming supply before the need date only when:

```text
purchase_order.status = CONFIRMED
AND purchase_order_line.status IN (CONFIRMED, IN_TRANSIT)
AND purchase_order_line.expected_delivery_date <= need_date
```

For component `C` and work order `WO-X` with `need_date`:

```text
confirmed_early_supply =
    sum(purchase_order_lines.ordered_quantity
        where component_id == C
        and purchase_order.status = CONFIRMED
        and purchase_order_line.status IN (CONFIRMED, IN_TRANSIT)
        and purchase_order_line.expected_delivery_date <= WO-X.need_date)

available_supply = inventory_available_for_WO_X + confirmed_early_supply

shortage = max(0, required_quantity - available_supply)
```

**Key rules:**
- Only lines with line status `CONFIRMED` or `IN_TRANSIT` (on a header with status `CONFIRMED`) contribute to `confirmed_early_supply`.
- The line must have `expected_delivery_date ≤ need_date` to reduce shortage.
- Excluded lines do NOT reduce shortage:
  - Header status `CANCELLED`: PO is cancelled.
  - Header status `PLACED`: PO not yet confirmed by supplier.
  - Line status `PENDING`: line not yet confirmed.
  - Line status `CANCELLED`: line cancelled by either party.
  - Line status `DELIVERED`: quantity already reflected in `inventory_balances.quantity_on_hand` (no double counting).

### 5.2 Lateness indicator (evidence for severity)

A purchase-order line is late supply evidence when:

```text
purchase_order.status = CONFIRMED
AND purchase_order_line.status IN (CONFIRMED, IN_TRANSIT)
AND purchase_order_line.expected_delivery_date > need_date
```

```text
confirmed_late_supply =
    sum(purchase_order_lines.ordered_quantity
        where component_id == C
        and purchase_order.status = CONFIRMED
        and purchase_order_line.status IN (CONFIRMED, IN_TRANSIT)
        and purchase_order_line.expected_delivery_date > WO-X.need_date)
```

Late supply does not reduce shortage at the need date, but it may trigger `HIGH` severity.

### 5.3 No double counting

The same quantity must never be counted both as inventory and incoming supply:
- If a PO line status is `DELIVERED`, its `received_quantity` is already in `inventory_balances.quantity_on_hand` (if the header status indicates receipt).
- Only lines with status `CONFIRMED` or `IN_TRANSIT` (expected but not yet received) on a `CONFIRMED` header contribute to `confirmed_early_supply` or `confirmed_late_supply`.

## 6. Production plan → order → requirement relationships

- 1 plan : N production orders
- 1 production order : 1 product_version
- 1 product_version : N bom_items
- 1 bom_item : 1 component
- 1 production order derives N production_order_requirements (one per bom_item × order.quantity)

## 7. Golden Dataset → field mapping

### RISK-001 (CTRL-X4, shortage 8, CRITICAL, affects WO-2026-0142)

Computation:

| Step | Source | Value |
|---|---|---|
| 1. WO.quantity × BOM.quantity_per_unit | `production_orders.quantity` (WO-2026-0142) × `bom_items.quantity_per_unit` (CTRL-X4) | 20 |
| 2. quantity_on_hand | `inventory_balances` (CTRL-X4, primary WH) | 12 |
| 3. reservations other than WO-2026-0142 | sum `inventory_reservations` | 0 (none) |
| 4. Available | 12 − 0 | 12 |
| 5. Confirmed PO arriving before need_date | sum `purchase_order_lines.ordered_quantity` where status confirmed and `expected_delivery_date ≤ WO.need_date` | 0 |
| 6. Shortage | required − available − confirmed_early | 20 − 12 − 0 = **8** |
| 7. No approved alternative | `component_alternatives` (CTRL-X4, status=APPROVED) → none | no mitigation |
| 8. Severity | shortage > 0, no alternative → `CRITICAL` | CRITICAL |

### RISK-002 (MOTOR-M2, effective shortage 6, HIGH, affects WO-2026-0150)

| Step | Source | Value |
|---|---|---|
| 1. required | WO.quantity × bom.quantity_per_unit | 16 |
| 2. available | on_hand − reservations | 10 |
| 3. Confirmed incoming *before* need_date(2026-08-03) | PO lines where `expected_delivery_date ≤ 2026-08-03` | 0 |
| 4. Confirmed incoming *after* need_date | PO lines where `expected_delivery_date = 2026-08-09` | 10 |
| 5. Shortage at need_date | 16 − 10 − 0 = **6** | 6 |
| 6. Severity | confirmed supply exists, but after need_date → `HIGH` | HIGH |

### RISK-003 (SENSOR-L9, shortage 5, MEDIUM, affects WO-2026-0156)

| Step | Source | Value |
|---|---|---|
| 1. required | WO.quantity × bom.quantity_per_unit | 12 |
| 2. available | on_hand − reservations | 7 |
| 3. Confirmed early | 0 | 0 |
| 4. Shortage | 12 − 7 = **5** | 5 |
| 5. Candidate alternative exists in `component_alternatives` (SENSOR-L9, status=PROPOSED) | yes, but not approved | unapproved mitigation |
| 6. Severity | shortage + unapproved alternative → `MEDIUM` | MEDIUM |

---

## 8. Severity rules (canonical)

Severity classification is deterministic, computed purely from the shortage and supply evidence, and evaluated by strict precedence (first rule that matches wins).

### 8.1 Severity precedence (deterministic, ordered)

| Priority | Condition | Severity |
|----------|-----------|----------|
| 1 | shortage <= 0 | (no risk emitted) |
| 2 | shortage > 0 AND `component_alternatives` with `status=PROPOSED` exists for this component | MEDIUM |
| 3 | shortage > 0 AND `confirmed_late_supply > 0` | HIGH |
| 4 | shortage > 0 AND no `component_alternatives` with `status=APPROVED` exists for this component | CRITICAL |
| 5 | shortage > 0 AND `component_alternatives` with `status=APPROVED` exists for this component | LOW |

### 8.2 LOW severity behavior (approved)

LOW severity is a fully exercised severity level in Phase 2:

- LOW is **emitted, not discarded**.
- A LOW risk is reported when the shortage is real but the component has an approved alternative on record.
- LOW indicates "mitigated but visible" — the shortage exists, the system has a known substitute, but the shortage is still recorded for governance and trace completeness.

### 8.3 Alternative-component role in severity (clarification)

Within Phase 2, `component_alternatives` is a **severity-only modifier**:

- An `APPROVED` alternative:
  - satisfies severity rule 5 (mitigates CRITICAL → LOW);
  - **does not** add the alternative component's inventory to `available`;
  - **does not** participate in shortage calculation;
  - substitution logic (e.g., consuming alternative stock instead of primary stock) is out of scope in Phase 2.
- A `PROPOSED` alternative:
  - satisfies severity rule 2 (MEDIUM);
  - otherwise has no arithmetic effect.
- A `REJECTED` alternative:
  - has no effect on severity or calculations (ignored).

No LLM influence on severity — pure Python/SQL.

---

## 9. Relationship cardinalities summary

- products 1 → N product_versions
- product_versions 1 → N bom_items
- bom_items N → 1 components
- product_versions 1 → N production_orders (many WOs can produce the same product version)
- production_plans 1 → N production_orders
- production_orders 1 → N production_order_requirements
- production_order_requirements N → 1 components
- components 1 → N inventory_balances (per warehouse)
- components 1 → N inventory_reservations
- components 1 → N purchase_order_lines
- components N → N component_alternatives (self-reference on components)
- suppliers 1 → N purchase_orders
- purchase_orders 1 → N purchase_order_lines

## 10. What this specification does NOT contain

- SQLAlchemy models, ORM mapping, or column lengths (Phase 2 WP-2.2).
- Alembic migrations (WP-2.2).
- Seed-generation strategy in detail (WP-2.3).
- API contracts (WP-2.7A, WP-2.7B).
- Risk engine code (WP-2.8).

---

**Status after PO review resolutions (2026-07-17):**
- All BLOCKING and MAJOR review findings resolved.
- WP-2.7 split into WP-2.7A and WP-2.7B for atomicity.

**Next step:** WP-2.2 translates this spec into SQLAlchemy 2 models and a single reversible Alembic migration.
