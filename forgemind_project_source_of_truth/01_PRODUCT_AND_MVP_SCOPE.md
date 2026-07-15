# 01. Product and MVP Scope

## 1. Product statement

ForgeMind AI Operations — web-платформа для контрольованого AI-assisted аналізу ризиків постачання в інженерно-виробничому середовищі.

Перша версія реалізує один вертикальний сценарій, а не набір непов’язаних AI-демо.

## 2. Golden Scenario

### Назва
**Production Plan Supply Risk Review**

### Передумова
У системі вже завантажено синтетичний виробничий план, BOM, залишки, відкриті поставки та набір технічних документів.

### Основний потік

1. Production Manager відкриває Dashboard.
2. Система показує новий план `PLAN-2026-W31`.
3. Користувач запускає `Analyze supply risks`.
4. Backend детерміновано:
   - розгортає BOM;
   - зіставляє потребу із залишками;
   - враховує зарезервовані запаси;
   - враховує підтверджені поставки та очікувані дати;
   - визначає дефіцити й часові конфлікти.
5. Agent workflow отримує структурований результат.
6. RAG шукає лише доступні користувачеві документи про альтернативні компоненти.
7. Модель формує пояснену рекомендацію у визначеній JSON-схемі.
8. UI показує:
   - ризик;
   - причину;
   - affected work orders;
   - числові докази;
   - джерела;
   - запропоновану дію;
   - confidence/status.
9. Користувач обирає одну рекомендацію.
10. Система створює `Approval Request`.
11. До approval жодна змінювальна дія не виконується.
12. Після підтвердження створюється синтетична procurement task.
13. Audit Log показує повний trace.

## 3. Обов’язкові екрани

### 3.1 Login
- demo credentials;
- повідомлення про synthetic data;
- зрозумілий error state.

### 3.2 Executive Dashboard
- active production plan;
- risk count by severity;
- latest agent runs;
- pending approvals;
- estimated time saved;
- system status.

### 3.3 Supply Risk Analysis
- таблиця ризиків;
- фільтри;
- деталізація розрахунку;
- evidence panel;
- source documents;
- action proposal.

### 3.4 Approval Center
- pending approvals;
- structured action preview;
- approve/reject;
- comment;
- audit metadata.

### 3.5 Knowledge Sources
- список synthetic documents;
- version;
- status;
- access level;
- indexed state;
- preview.

### 3.6 Workflow Run Details
- кроки виконання;
- duration;
- input/output summary;
- tool calls;
- retrieval sources;
- model metadata;
- errors/retries.

### 3.7 Audit Log
- actor;
- event;
- timestamp;
- entity;
- before/after summary;
- correlation ID.

### 3.8 Admin / Model Status
- active provider;
- endpoint type;
- health;
- model name;
- request count;
- fallback status;
- secrets never displayed.

## 4. Функціональні вимоги MVP

### FR-01 Authentication
Система повинна підтримувати demo users із ролями Production Manager, Procurement Specialist, AI Administrator та Auditor.

### FR-02 RBAC
Користувач бачить лише дозволені документи й дії.

### FR-03 Seed Data
Одна команда повинна створювати повний синтетичний dataset.

### FR-04 Deterministic Risk Engine
Ризики обчислюються кодом Python/SQL за формальною логікою.

### FR-05 RAG
Система індексує синтетичні технічні документи, виконує retrieval та повертає цитовані фрагменти.

### FR-06 Structured AI Output
Модель повертає результат за versioned JSON schema. Невалідний результат не записується як успішний.

### FR-07 Workflow Trace
Кожен запуск має correlation ID, status, timestamps, steps і errors.

### FR-08 Human Approval
Створення procurement task потребує явного підтвердження.

### FR-09 Audit
Критичні читання, agent runs, approval та write actions журналюються.

### FR-10 Dashboard
Dashboard відображає фактичні дані backend, а не hardcoded UI fixtures.

### FR-11 Public Demo
Система доступна через HTTPS на VPS.

### FR-12 Demo Reset
Адміністратор може безпечно повернути demo dataset до початкового стану.

## 5. Post-MVP backlog

- Requirements Analyst Agent;
- Incident Triage Agent;
- Process Discovery;
- document conflict detection;
- evaluation lab;
- n8n integration;
- ERP webhook simulator;
- local GPU inference deployment;
- advanced role policies;
- multi-language interface;
- richer analytics;
- automated report export.

Жоден пункт Post-MVP не може блокувати завершення MVP.
