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
