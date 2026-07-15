# 09. Master Task for Hermes

## Mission

Побудувати Portfolio Ready версію ForgeMind AI Operations відповідно до Source of Truth.

## Non-negotiable product scope

Реалізувати один end-to-end сценарій Supply Risk Intelligence:

1. synthetic production plan;
2. deterministic supply risk calculation;
3. RAG over synthetic engineering documents;
4. structured AI recommendation;
5. human approval;
6. controlled procurement task creation;
7. complete audit trace;
8. public HTTPS deployment.

## Definition of completion

Робота завершена лише після виконання `03_DEFINITION_OF_DONE.md` і проходження всіх тестів з `04_ACCEPTANCE_TESTS.md`.

## Initial instruction

Не починати масову реалізацію.

Спочатку:

1. прочитати всі Source of Truth files;
2. перевірити суперечності;
3. запропонувати repository structure;
4. запропонувати phase-by-phase implementation plan;
5. сформувати список assumptions і відкритих питань;
6. створити traceability matrix:
   - requirement;
   - implementation component;
   - test;
   - evidence;
7. зупинитися для approval Product Owner.

## Mandatory engineering rules

- не hardcode Golden Scenario;
- не використовувати LLM для арифметики;
- не додавати Post-MVP без Decision Log;
- кожна фаза має окремий branch/commit;
- кожна задача має acceptance criteria;
- кожне завершення має command/test evidence;
- docs повинні відображати фактичний стан;
- deployment не виконується без review конфігурації VPS;
- секрети не комітяться;
- небезпечні операції потребують confirmation.

## Required final deliverables

```text
frontend/
backend/
worker/                  # лише якщо обґрунтовано
infra/
docs/
tests/
scripts/
seed/
release-evidence/
docker-compose.yml
.env.example
README.md
```

## Final report format

```text
Project status:
Release version:
Public URL:
Branch:
Commit:
Files changed:
Services deployed:
Acceptance tests:
Security checks:
Known limitations:
Demo credentials:
Rollback procedure:
Working tree:
```
