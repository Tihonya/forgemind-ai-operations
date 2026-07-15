# 04. Acceptance Tests

Кожен тест має мати автоматичний або відтворюваний manual evidence.

## AT-001 — Clean deployment

**Given:** чисте середовище з Docker і Docker Compose  
**When:** виконано документовану команду розгортання  
**Then:** усі required services мають status healthy, міграції виконані, seed dataset доступний.

## AT-002 — Demo authentication

**Given:** demo credentials  
**When:** користувач входить  
**Then:** відкривається Dashboard відповідної ролі; неправильний пароль повертає контрольовану помилку.

## AT-003 — Golden Dataset integrity

**When:** виконано seed/reset  
**Then:** dataset version відповідає документації, а checksum або fixture version зафіксований.

## AT-004 — Deterministic risk calculation

**When:** запускається аналіз `PLAN-2026-W31` без LLM  
**Then:** engine повертає рівно:

- RISK-001: shortage 8, CRITICAL;
- RISK-002: effective shortage 6, HIGH;
- RISK-003: shortage 5, MEDIUM.

## AT-005 — No hidden UI mocks

**When:** змінити seed quantity компонента через test fixture  
**Then:** UI відображає новий backend result без зміни frontend code.

## AT-006 — RAG retrieval

**Given:** approved document про альтернативу компонента  
**When:** workflow шукає mitigation  
**Then:** відповідь містить valid document ID, version і chunk ID.

## AT-007 — Document access control

**Given:** користувач без доступу до restricted document  
**When:** він ставить запит, відповідь на який є лише в цьому документі  
**Then:** restricted chunk не потрапляє до retrieval context або response.

## AT-008 — Structured output validation

**Given:** модель повернула невалідну структуру  
**Then:** run отримує status `FAILED_VALIDATION`, write actions не створюються, помилка видима в trace.

## AT-009 — Human approval blocks write

**Given:** agent запропонував procurement task  
**When:** approval ще pending  
**Then:** procurement task відсутня.

## AT-010 — Approval executes controlled action

**When:** уповноважений користувач підтверджує approval  
**Then:** створено одну procurement task із посиланням на risk, run і approver.

## AT-011 — Reject path

**When:** approval відхилено  
**Then:** task не створюється, причина відмови збережена в audit log.

## AT-012 — Audit trace completeness

**For one completed run audit must contain:**

1. user action;
2. deterministic calculation;
3. retrieval;
4. model call;
5. structured validation;
6. recommendation;
7. approval request;
8. human decision;
9. write action або rejection.

## AT-013 — Model outage

**Given:** AI endpoint недоступний  
**Then:** risk engine result залишається доступним, workflow показує failed AI step, UI не зависає, користувач може retry.

## AT-014 — Public HTTPS smoke test

**When:** відкрити live URL у приватній browser session  
**Then:** certificate валідний, login працює, assets завантажуються, Golden Scenario завершується.

## AT-015 — Demo reset

**When:** authorized admin запускає reset  
**Then:** створені demo actions очищено, seed dataset відновлено, audit reset event зафіксовано.

---

# Release checklist evidence

Для кожного release створити:

```text
release-evidence/
  test-summary.md
  backend-tests.txt
  frontend-tests.txt
  e2e-tests.txt
  docker-health.txt
  public-smoke-test.md
  screenshots/
```

Release не приймається лише на основі усного звіту AI-агента.
