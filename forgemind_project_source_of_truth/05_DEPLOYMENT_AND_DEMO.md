# 05. Deployment and Demo Plan

## 1. Цільове середовище

Публічна демонстрація розгортається на вже наявному VPS користувача.

Базове припущення:

- Linux VPS;
- Docker Engine;
- Docker Compose;
- domain або subdomain;
- HTTPS;
- обмежені ресурси;
- відсутність постійної GPU на VPS.

## 2. Deployment topology

```text
Internet
   |
HTTPS
   |
Caddy/Nginx
   |
   +-- Frontend
   +-- FastAPI
   +-- Worker
   +-- PostgreSQL + pgvector
   +-- Optional Redis
   |
AI Provider Adapter
   +-- hosted OpenAI-compatible endpoint
   +-- optional remote/local endpoint
```

## 3. Вимога незалежності demo

Публічний demo не повинен ламатися через вимкнений домашній workstation.

Рекомендовані режими:

### Hosted Demo Mode
Використовує доступний API endpoint із жорсткими quota, rate limit і synthetic data only.

### Local Model Mode
Документований окремо та демонструє сумісність із OpenAI-compatible локальним inference server. Не є єдиним способом роботи публічного demo.

### Controlled Fallback
Якщо model endpoint недоступний:

- deterministic risk analysis продовжує працювати;
- AI explanation позначається unavailable;
- користувач бачить retry;
- система не видає fake successful result.

## 4. Domain and HTTPS

Потрібен окремий subdomain, наприклад:

`forgemind.example.com`

Обов’язково:

- валідний TLS;
- redirect HTTP → HTTPS;
- secure cookies;
- secrets в environment variables;
- закриті database ports;
- firewall;
- SSH key authentication;
- fail2ban або еквівалентний захист.

## 5. Demo accounts

Створити окремі readonly/limited demo users:

- `manager.demo`;
- `procurement.demo`;
- `auditor.demo`.

Адміністративний reset не повинен бути доступним анонімному користувачеві.

Credentials можна показувати на login page, якщо вони мають лише synthetic demo permissions.

## 6. Public demo protections

- rate limit;
- request timeout;
- AI token quota;
- max upload size;
- uploads disabled або tightly controlled;
- no arbitrary URL ingestion;
- no shell/code execution tools;
- no access to VPS filesystem;
- scheduled data reset;
- resource limits для контейнерів;
- health monitoring;
- log rotation.

## 7. Deployment acceptance

Deployment вважається готовим, коли:

1. домен відкривається через HTTPS;
2. login працює;
3. Golden Scenario проходить;
4. restart/reboot не вимагає ручного виправлення;
5. база має backup procedure;
6. demo reset працює;
7. секрети відсутні в Git;
8. public smoke test задокументовано;
9. протягом 24 годин після релізу немає P1/P2 failures.

## 8. Demo script на 5 хвилин

### 0:00–0:30 — Problem
Пояснити розподіленість ERP, BOM, inventory та documentation.

### 0:30–1:15 — Dashboard
Показати план і три ризики.

### 1:15–2:15 — Deterministic evidence
Відкрити деталізацію quantities, reservations, incoming supply та dates.

### 2:15–3:00 — RAG
Показати джерела й статус документа.

### 3:00–3:45 — Human approval
Створити draft action, підтвердити її та показати procurement task.

### 3:45–4:30 — Audit trace
Показати всі workflow steps, model call і correlation ID.

### 4:30–5:00 — Architecture
Коротко показати Docker, FastAPI, React, PostgreSQL/pgvector та model adapter.

## 9. Operational minimum

Необхідні runbooks:

- deploy;
- rollback;
- database backup;
- database restore;
- reset demo data;
- rotate secrets;
- inspect logs;
- verify health;
- disable AI provider in emergency.

## 10. Актуальний стан публічного портфоліо-демо (станом на 2026-08-29)

Публічний портфоліо-демо розгорнуто, незалежно перевірено та працює: `https://demo.forgemind-ai.tech/`. Це ізольоване одноразове демонстраційне середовище (DEC-056) — воно не є formal production deployment: Release 1 залишається NOT READY / NOT DEPLOYED, staging і production — NOT STARTED, формальне production acceptance не оголошено, SLA не завершено, і жоден acceptance-тест, що залежить від deployment evidence, не позначено PASS лише на підставі демо.

Що перевірено на публічному демо:

- працює українськомовний рекрутерський сценарій (менеджер → фахівець із закупівель → аудитор) із role boundaries; існують три demo-ролі (`manager.demo`, `procurement.demo`, `auditor.demo`);
- український рекрутерський гайд існує й опубліковано в репозиторії (`docs/demo-guide.uk.md`, PR #137);
- health-перевірка проходить: HTTPS доступний, `/` і `/login` повертають 200, `/health` — 200 із перевірками backend/postgresql/redis/worker = ok; HTTP перенаправляється на HTTPS (redirect 308); валідний TLS;
- первинний демо-маршрут (Golden Scenario walkthrough) пройдено під час незалежної живої верифікації (WP-DPR1-03A);
- O2 закрито на публічному демо: дії в Журналі аудиту відображають `Слід`, діалог лише для читання має заголовок `Слід аудиту`, i18next-діагностика об'єкта більше не відтворюється (WP-DPR1-05, PR #138, merge commit `7b8af58db8ed9a953fb5e7cbcdcbba7fdb30d8ad`);
- стабільна live Compose-команда (base + override) утримує виправлений фронтенд — пін фронтенду в override узгоджено з розгорнутим образом (WP-DPR1-06); rollback-тег зберігається та не використовується.

Точне змішане походження образів (mixed provenance): The public Demo retains the previously verified backend and worker images from candidate edbbc938 and runs the WP-DPR1-05 frontend built from 7b8af58. Увесь запущений стек НЕ було перезібрано з `7b8af58`. Точні ідентифікатори образів: backend `sha256:7e1b21c263b710beecc13028f357adf030d2605568266f4873a5c29f6056ef51`; worker `sha256:58d156b611c9b478fd3a59d41c1a5714dc002363ea3f19b700004bef4796c730`; frontend `sha256:ecae3e2f60f81c31487a3764c05303a0af29adc4dbb966612166f5f7e064b19d`; Alembic-ревізія `d00f71c78f67`. Жодних даних застосунку або персистентних сервісів не змінено (WP-DPR1-05/06). Повний підсумок: `docs/reviews/wp_dpr1_05_06_demo_frontend_closure.md`.

Не задекларовано й не зроблено: credential rotation (відкладено до однієї обмеженої консерваційної дії, DEC-060), автоматичний reset перед кожним відвідуванням рекрутера, staging/production розгортання, GitHub Release або тег для цього чекпоінту. Портфоліо-реліз `v0.1.0` готується як окрема обмежена дія (WP-DPR1-08) після незалежного рев'ю та злиття WP-DPR1-07.
