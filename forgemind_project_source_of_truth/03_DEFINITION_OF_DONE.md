# 03. Definition of Done

## 1. Головне правило

Проєкт не оцінюється відсотком “майже готово”.

Статус **Portfolio Ready** надається лише після проходження всіх обов’язкових gates.

## 2. Gate A — Product completeness

Усі пункти обов’язкові:

- [ ] Golden Scenario реалізований end-to-end.
- [ ] В UI немає кнопок основного сценарію, які нічого не роблять.
- [ ] Risk Engine повертає рівно три очікувані ризики.
- [ ] Є пояснення числового розрахунку кожного ризику.
- [ ] Є RAG sources.
- [ ] Є approval flow.
- [ ] Є audit trace.
- [ ] Є demo reset.

## 3. Gate B — Engineering quality

- [ ] Репозиторій має зрозумілу структуру.
- [ ] Міграції створюють БД із чистого стану.
- [ ] Seed command створює Golden Dataset.
- [ ] Backend unit/integration tests проходять.
- [ ] Frontend tests проходять.
- [ ] End-to-end Golden Scenario test проходить.
- [ ] Лінтери та type checks проходять.
- [ ] Немає committed secrets.
- [ ] Немає критичних dependency vulnerabilities, відомих на момент релізу.
- [ ] Немає hardcoded Golden Scenario results у UI.

## 4. Gate C — AI quality

- [ ] AI output проходить Pydantic/JSON Schema validation.
- [ ] RAG citations ведуть до фактичних synthetic document chunks.
- [ ] Мінімум 90% контрольних запитів evaluation set мають коректні citations.
- [ ] Модель не виконує write action без approval.
- [ ] При недоступності моделі система показує контрольований failure state.
- [ ] Усі model calls мають run ID, latency та model metadata.
- [ ] Детерміновані числа не генеруються LLM.

## 5. Gate D — Security and governance

- [ ] Є authentication.
- [ ] Є щонайменше чотири ролі.
- [ ] Auditor не може виконувати write actions.
- [ ] Користувач не може отримати через RAG документ, до якого не має доступу.
- [ ] Approval містить actor, timestamp і comment.
- [ ] Audit events неможливо змінити через звичайний UI.
- [ ] Rate limiting захищає public demo.
- [ ] Demo credentials не мають адміністративного доступу до VPS.

## 6. Gate E — Deployment

- [ ] Система розгорнута на наявному VPS.
- [ ] Є стабільний публічний URL.
- [ ] HTTPS certificate валідний.
- [ ] `docker compose up -d --build` є документованим способом запуску.
- [ ] Після reboot сервіси відновлюються.
- [ ] Є health checks.
- [ ] Є basic backup для PostgreSQL.
- [ ] Є log rotation.
- [ ] Є environment-specific configuration.
- [ ] Demo не залежить від увімкненого ноутбука автора, окрім явно задокументованого optional local-model mode.

## 7. Gate F — Portfolio presentation

- [ ] README пояснює проблему, рішення й архітектуру.
- [ ] Є architecture diagram.
- [ ] Є screenshots.
- [ ] Є 3–5 хвилинне demo video.
- [ ] Є demo credentials.
- [ ] Є опис AI-assisted delivery workflow.
- [ ] Є список trade-offs та обмежень.
- [ ] Є посилання на live demo.
- [ ] Є CV-ready project description українською та англійською.
- [ ] Сторонній користувач пройшов сценарій без пояснень автора.

## 8. Release metric

### MVP Done
Усі acceptance tests AT-001…AT-015 мають `PASS` локально та в CI.

### Portfolio Ready
Виконано `MVP Done` плюс:

- публічний HTTPS deployment;
- три послідовні успішні проходження Golden Scenario у чистій browser session;
- 24 години без P1/P2 помилок після release;
- demo video;
- актуальний README;
- external smoke test сторонньою людиною.

## 9. Заборонені підміни завершеності

Не вважається завершенням:

- красивий frontend із mock data;
- agent, який повертає заздалегідь записану відповідь;
- RAG без citations;
- Docker Compose, що працює лише на машині автора;
- “тести не запускали, але код виглядає правильно”;
- deployment без HTTPS;
- approval, який фактично не блокує write action;
- README, що описує функції, яких немає;
- десять напівготових модулів замість одного завершеного сценарію.
