# 02. System Behavior and Data Contract

## 1. Архітектурний принцип

LLM не є джерелом істини для арифметики, статусів ERP або прав доступу.

### Детермінований код відповідає за

- розрахунок потреби;
- BOM explosion;
- залишки;
- резерви;
- строки поставок;
- severity rules;
- права доступу;
- запис дій;
- validation;
- audit.

### LLM відповідає за

- пояснення структурованого результату;
- узагальнення документів;
- пошук і зіставлення альтернатив;
- формування зрозумілої рекомендації;
- створення чернетки тексту задачі.

## 2. Рекомендований стек

### Frontend
- React;
- TypeScript;
- Vite;
- React Router;
- TanStack Query;
- Zustand або мінімальний state layer;
- React Flow лише для workflow trace, якщо виправдано;
- ECharts або Recharts;
- component library із послідовною design system.

### Backend
- Python 3.12+;
- FastAPI;
- Pydantic;
- SQLAlchemy 2;
- Alembic;
- background jobs через ARQ, Dramatiq або Celery — обрати один;
- REST API;
- WebSocket або polling для run progress — обрати найпростішу надійну реалізацію.

### Data
- PostgreSQL;
- pgvector;
- Redis лише за наявності реальної потреби в queue/cache;
- object storage опціонально.

### AI
- OpenAI-compatible provider interface;
- один основний chat/reasoning model;
- одна embedding model;
- optional reranker;
- LangGraph або власна explicit state machine;
- cloud та local endpoint мають підключатися через однаковий adapter contract.

### Infrastructure
- Docker Compose;
- Caddy або Nginx як reverse proxy;
- HTTPS;
- GitHub Actions;
- structured logs;
- health endpoints.

## 3. Мінімальна модель даних

### Business entities
- `products`
- `product_versions`
- `components`
- `bom_items`
- `warehouses`
- `inventory_balances`
- `inventory_reservations`
- `suppliers`
- `purchase_orders`
- `purchase_order_lines`
- `production_plans`
- `production_orders`
- `production_order_requirements`
- `procurement_tasks`

### Knowledge entities
- `documents`
- `document_versions`
- `document_permissions`
- `knowledge_chunks`
- `component_alternatives`

### AI and governance entities
- `agent_definitions`
- `agent_versions`
- `workflow_runs`
- `workflow_steps`
- `retrieval_events`
- `model_calls`
- `approval_requests`
- `audit_events`
- `users`
- `roles`
- `user_roles`

## 4. Golden Seed Dataset

Dataset повинен бути стабільним і versioned.

### Production plan
`PLAN-2026-W31`

### Очікувані ризики

#### RISK-001 — Critical shortage
- Component: `CTRL-X4`
- Required: 20
- Available after reservations: 12
- Confirmed supply before need date: 0
- Shortage: 8
- Severity: `CRITICAL`
- Affected order: `WO-2026-0142`

#### RISK-002 — Late confirmed delivery
- Component: `MOTOR-M2`
- Required: 16
- Available after reservations: 10
- Incoming: 10
- Need date: `2026-08-03`
- Expected delivery: `2026-08-09`
- Effective shortage at need date: 6
- Severity: `HIGH`
- Affected order: `WO-2026-0150`

#### RISK-003 — Unapproved alternative
- Component: `SENSOR-L9`
- Required: 12
- Available after reservations: 7
- Shortage: 5
- Candidate alternative exists in draft document but is not approved
- Severity: `MEDIUM`
- Affected order: `WO-2026-0156`

### Обов’язкова умова
Golden Scenario має повертати **рівно ці три ризики** з правильними quantities та severity.

Результати не можна hardcode у frontend або agent prompt. Вони мають виникати з seed data та risk rules.

## 5. Risk rules

### CRITICAL
Наявний дефіцит на need date і немає затвердженої поставки або дозволеної альтернативи.

### HIGH
Поставка підтверджена, але очікується після need date, або дефіцит блокує початок production order.

### MEDIUM
Є потенційна альтернатива чи mitigation, але вона не затверджена або потребує інженерного рішення.

### LOW
Є достатній mitigation, але потрібен моніторинг.

## 6. Structured recommendation schema

Модель повинна повертати versioned structure приблизно такого вигляду:

```json
{
  "schema_version": "1.0",
  "run_id": "uuid",
  "plan_id": "PLAN-2026-W31",
  "risks": [
    {
      "risk_id": "RISK-001",
      "summary": "string",
      "business_impact": "string",
      "recommended_actions": [
        {
          "action_type": "CREATE_PROCUREMENT_TASK",
          "title": "string",
          "rationale": "string",
          "requires_approval": true
        }
      ],
      "sources": [
        {
          "document_id": "DOC-...",
          "version": "2.1",
          "chunk_id": "uuid"
        }
      ]
    }
  ]
}
```

Backend зобов’язаний валідувати schema до збереження.

## 7. RAG rules

- відповіді без джерел не вважаються grounded;
- retrieval фільтрується за роллю;
- draft/obsolete documents позначаються;
- новіша версія не завжди означає approved;
- UI показує document status;
- model prompt не може приховувати від користувача суперечності;
- відсутність доказів повинна повертати `insufficient evidence`.

## 8. Write-action rules

AI не може напряму створити фінальну закупівлю.

Дозволений ланцюжок:

`recommendation → draft action → approval request → human decision → procurement task → audit event`

Reject також журналюється.
