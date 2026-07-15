# 06. AI Agent Execution Rules

## 1. Призначення

Цей документ визначає, як Hermes та моделі під його керуванням повинні працювати з репозиторієм.

Сила моделі не замінює acceptance criteria.

## 2. Ролі моделей

### Architect / Critic
Відповідає за:

- аналіз scope;
- product and architecture review;
- виявлення overengineering;
- перевірку відповідності Source of Truth;
- UX review за screenshots;
- фінальне gap analysis.

### Implementation Engineer
Відповідає за:

- backend;
- frontend;
- database;
- Docker;
- tests;
- migrations;
- bug fixing;
- documentation sync.

Модель не повинна одночасно реалізовувати великий етап і самостійно приймати його без незалежного review.

## 3. Формат кожного завдання

Кожний task повинен містити:

```text
Goal
Business reason
In scope
Out of scope
Files allowed to change
Files forbidden to change
Acceptance criteria
Commands to run
Expected evidence
Required documentation updates
Commit requirement
Stop conditions
```

## 4. Обов’язковий цикл

```text
inspect repository
→ restate current state
→ propose smallest change
→ implement
→ run checks
→ inspect failures
→ fix
→ run checks again
→ update docs
→ commit
→ provide evidence
```

## 5. Заборонена поведінка

AI-агент не має права:

- оголошувати етап завершеним без запуску перевірок;
- hardcode Golden Scenario result;
- змінювати Definition of Done без рішення Product Owner;
- додавати Post-MVP функції без рішення в Decision Log;
- приховувати failing tests;
- замінювати функціональність моками без явного маркування;
- видаляти тести, щоб “усе стало зеленим”;
- змінювати public contracts без migration note;
- записувати secrets у репозиторій;
- робити небезпечні production actions без explicit approval.

## 6. Розмір задач

Один task має створювати один перевірюваний increment.

Поганий task:

> Реалізуй всю ForgeMind platform.

Хороший task:

> Створи deterministic shortage calculation для одного production plan, додай unit tests для трьох Golden Dataset ризиків, не підключай LLM і не змінюй frontend.

## 7. Evidence contract

Фінальна відповідь агента повинна містити:

- branch;
- commit hash;
- files changed;
- commands run;
- test results;
- screenshots або API evidence, якщо релевантно;
- known limitations;
- working tree status;
- наступний рекомендований task.

Текст “готово” без evidence не має сили.

## 8. Architecture discipline

Перед додаванням dependency агент повинен пояснити:

- навіщо вона потрібна;
- чому стандартних засобів недостатньо;
- operational cost;
- чи входить вона в MVP.

Один клас задач — один основний framework. Не використовувати одночасно кілька agent frameworks без явної причини.

## 9. Prompt and model versioning

- system prompts зберігаються у versioned files;
- prompt version записується в workflow run;
- model name та endpoint type записуються;
- зміна prompt, що впливає на результат, має окремий test/evaluation;
- production prompt не редагується лише через UI без audit.

## 10. Stop conditions

Агент повинен зупинитися і запросити рішення, якщо:

- вимоги суперечать Source of Truth;
- потрібна зміна scope;
- необхідні credentials відсутні;
- migration може знищити дані;
- acceptance criteria неможливо перевірити;
- зовнішній API має невідому ліцензію або вартість;
- deployment action може порушити роботу іншого сервісу на VPS.
