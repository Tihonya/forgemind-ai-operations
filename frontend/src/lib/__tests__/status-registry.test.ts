/**
 * WP-UX-UA-04 status registry contract tests.
 *
 * PINNED tables below were generated once from the reviewed committed
 * catalogs (uk/en status namespaces) and the registry seed table, then
 * frozen into this file. They are INDEPENDENT of the production code path:
 * tests resolve values through the real i18n instance and compare against
 * the frozen pins, so a catalog or registry drift fails loudly. Nothing at
 * runtime reads PINNED_.
 *
 * Regenerate ONLY deliberately (see recovery notes) — never to "fix" a red
 * test by re-pinning.
 */
import { describe, expect, it, beforeEach } from 'vitest';

import i18n from '@/i18n';
import ukCatalog from '@/i18n/locales/uk/status.json';
import enCatalog from '@/i18n/locales/en/status.json';
import {
  STATUS_CATALOG_NS,
  STATUS_ENTRY_COUNT,
  allStatusEntries,
  isKnownStatus,
  resolveStatus,
  statusDomains,
  type StatusTone,
} from '@/lib/status-registry';
import {
  translateStatusDescription,
  translateStatusLabel,
} from '@/lib/status-i18n';

type Pinned = {
  tone: StatusTone;
  ukLabel: string;
  enLabel: string;
  ukDescription: string;
  enDescription: string;
};

/** Frozen (id -> pin) table; ids are `${domain}.${code}`. */
const PINNED: Record<string, Pinned> = {
    'workflowRun.PENDING': {
      tone: 'info',
      ukLabel: 'У черзі',
      enLabel: 'Queued',
      ukDescription: 'Аналіз створено, і він очікує запуску. Система почне виконання автоматично, щойно звільниться виконавець.',
      enDescription: 'The analysis has been created and is waiting to start. The system will begin execution automatically once a worker is available.',
    },
    'workflowRun.RUNNING': {
      tone: 'info',
      ukLabel: 'Аналіз триває',
      enLabel: 'Analysis in progress',
      ukDescription: 'Система зараз виконує цей процес. Дочекайтеся завершення або перевірте деталі виконання.',
      enDescription: 'The system is executing this process right now. Wait for completion or review the execution details.',
    },
    'workflowRun.AWAITING_VALIDATION': {
      tone: 'warning',
      ukLabel: 'Перевірка результату',
      enLabel: 'Validating result',
      ukDescription: 'Відповідь моделі отримано. Система перевіряє, чи відповідає результат установленим вимогам структури.',
      enDescription: 'The model response has been received. The system is checking whether the result satisfies the required structure.',
    },
    'workflowRun.COMPLETED': {
      tone: 'success',
      ukLabel: 'Завершено',
      enLabel: 'Completed',
      ukDescription: 'Процес успішно завершено. Результати доступні для перегляду та подальших рішень.',
      enDescription: 'The process finished successfully. Results are available for review and further decisions.',
    },
    'workflowRun.FAILED_VALIDATION': {
      tone: 'danger',
      ukLabel: 'Помилка перевірки',
      enLabel: 'Validation failed',
      ukDescription: 'Результат не пройшов перевірку структури і не може бути використаний. Запустіть аналіз повторно.',
      enDescription: 'The result failed structural validation and cannot be used. Run the analysis again.',
    },
    'workflowRun.FAILED_PROVIDER': {
      tone: 'danger',
      ukLabel: 'Сервіс ШІ недоступний',
      enLabel: 'AI service unavailable',
      ukDescription: 'Постачальник ШІ не відповів або відхилив запит. Спробуйте ще раз трохи пізніше.',
      enDescription: 'The AI provider did not respond or rejected the request. Try again later.',
    },
    'workflowRun.FAILED_INTERNAL': {
      tone: 'danger',
      ukLabel: 'Помилка аналізу',
      enLabel: 'Analysis failed',
      ukDescription: 'Під час аналізу сталася внутрішня помилка. Повторіть запуск; якщо помилка повторюється, зверніться до адміністратора.',
      enDescription: 'An internal error occurred during the analysis. Retry; if the error persists, contact an administrator.',
    },
    'workflowRun.FAILED_RETRIEVAL': {
      tone: 'danger',
      ukLabel: 'Помилка пошуку даних',
      enLabel: 'Evidence retrieval failed',
      ukDescription: 'Системі не вдалося знайти потрібні документи для аналізу. Спробуйте ще раз.',
      enDescription: 'The system could not retrieve the documents needed for the analysis. Try again.',
    },
    'workflowStep.started': {
      tone: 'info',
      ukLabel: 'Розпочато',
      enLabel: 'Started',
      ukDescription: 'Крок зараз виконується.',
      enDescription: 'This step is currently executing.',
    },
    'workflowStep.completed': {
      tone: 'success',
      ukLabel: 'Виконано',
      enLabel: 'Completed',
      ukDescription: 'Крок успішно завершено.',
      enDescription: 'The step finished successfully.',
    },
    'workflowStep.failed': {
      tone: 'danger',
      ukLabel: 'Помилка',
      enLabel: 'Failed',
      ukDescription: 'Крок завершився з помилкою. Деталі наведено нижче.',
      enDescription: 'The step finished with an error. Details are shown below.',
    },
    'approval.PENDING': {
      tone: 'warning',
      ukLabel: 'Очікує рішення',
      enLabel: 'Awaiting decision',
      ukDescription: 'Запит очікує погодження або відхилення уповноваженим користувачем.',
      enDescription: 'The request is waiting for an authorized user to approve or reject it.',
    },
    'approval.APPROVED': {
      tone: 'success',
      ukLabel: 'Погоджено',
      enLabel: 'Approved',
      ukDescription: 'Уповноважений користувач погодив дію. Контрольована дія буде виконана.',
      enDescription: 'An authorized user approved the action. The controlled action will be executed.',
    },
    'approval.REJECTED': {
      tone: 'danger',
      ukLabel: 'Відхилено',
      enLabel: 'Rejected',
      ukDescription: 'Уповноважений користувач відхилив запит. Дію не буде виконано.',
      enDescription: 'An authorized user rejected the request. The action will not be executed.',
    },
    'severity.CRITICAL': {
      tone: 'danger',
      ukLabel: 'Критичний',
      enLabel: 'Critical',
      ukDescription: 'Потребує негайної уваги: дефіцит може зупинити виробництво.',
      enDescription: 'Requires immediate attention: the shortage may stop production.',
    },
    'severity.HIGH': {
      tone: 'warning',
      ukLabel: 'Високий',
      enLabel: 'High',
      ukDescription: 'Значний ризик, який потребує термінових дій.',
      enDescription: 'A significant risk that requires urgent action.',
    },
    'severity.MEDIUM': {
      tone: 'info',
      ukLabel: 'Середній',
      enLabel: 'Medium',
      ukDescription: 'Помірний ризик, який потребує уваги відповідальних осіб.',
      enDescription: 'A moderate risk that requires attention from the responsible people.',
    },
    'severity.LOW': {
      tone: 'neutral',
      ukLabel: 'Низький',
      enLabel: 'Low',
      ukDescription: 'Незначний ризик; регулярного моніторингу достатньо.',
      enDescription: 'A minor risk; regular monitoring is sufficient.',
    },
    'dataset.valid': {
      tone: 'success',
      ukLabel: 'Дані коректні',
      enLabel: 'Data valid',
      ukDescription: 'Набір даних збігається із затвердженим еталонним зразком.',
      enDescription: 'The dataset matches the approved Golden Dataset fixture.',
    },
    'dataset.invalid': {
      tone: 'danger',
      ukLabel: 'Дані некоректні',
      enLabel: 'Data invalid',
      ukDescription: 'Набір даних відрізняється від затвердженого еталонного зразка.',
      enDescription: 'The dataset differs from the approved Golden Dataset fixture.',
    },
    'dataset.not_loaded': {
      tone: 'neutral',
      ukLabel: 'Дані не завантажено',
      enLabel: 'Not loaded',
      ukDescription: 'Еталонний набір даних ще не завантажено в систему.',
      enDescription: 'No Golden Dataset has been loaded into the system.',
    },
    'health.healthy': {
      tone: 'success',
      ukLabel: 'Система справна',
      enLabel: 'Healthy',
      ukDescription: 'Усі служби працюють у межах норми.',
      enDescription: 'All services are operating within normal limits.',
    },
    'health.degraded': {
      tone: 'warning',
      ukLabel: 'Погіршена робота',
      enLabel: 'Degraded',
      ukDescription: 'Частина служб працює з відхиленнями; основні функції залишаються доступними.',
      enDescription: 'Some services are operating with deviations; core functions remain available.',
    },
    'health.unhealthy': {
      tone: 'danger',
      ukLabel: 'Порушення роботи',
      enLabel: 'Unhealthy',
      ukDescription: 'Одна або кілька служб недоступні. Дії користувача можуть бути обмежені.',
      enDescription: 'One or more services are unavailable. User actions may be limited.',
    },
    'healthCheck.ok': {
      tone: 'success',
      ukLabel: 'Доступно',
      enLabel: 'Available',
      ukDescription: 'Компонент працює нормально.',
      enDescription: 'The component is operating normally.',
    },
    'healthCheck.error': {
      tone: 'danger',
      ukLabel: 'Помилка',
      enLabel: 'Error',
      ukDescription: 'Компонент повідомив про помилку.',
      enDescription: 'The component reported an error.',
    },
    'healthCheck.unknown': {
      tone: 'neutral',
      ukLabel: 'Невідомо',
      enLabel: 'Unknown',
      ukDescription: 'Стан компонента не вдалося визначити.',
      enDescription: 'The component state could not be determined.',
    },
    'plan.DRAFT': {
      tone: 'neutral',
      ukLabel: 'Чернетка',
      enLabel: 'Draft',
      ukDescription: 'План ще не готовий до виконання.',
      enDescription: 'The plan is not yet ready for execution.',
    },
    'plan.APPROVED': {
      tone: 'success',
      ukLabel: 'Затверджено',
      enLabel: 'Approved',
      ukDescription: 'План затверджено до виконання.',
      enDescription: 'The plan has been approved for execution.',
    },
    'plan.EXECUTING': {
      tone: 'info',
      ukLabel: 'Виконується',
      enLabel: 'Executing',
      ukDescription: 'Система зараз виконує цей план: замовлення активно обробляються.',
      enDescription: 'The system is executing this plan right now: orders are actively being processed.',
    },
    'plan.COMPLETED': {
      tone: 'success',
      ukLabel: 'Завершено',
      enLabel: 'Completed',
      ukDescription: 'Виробничий план виконано повністю.',
      enDescription: 'The production plan has been fully executed.',
    },
    'plan.CLOSED': {
      tone: 'neutral',
      ukLabel: 'Закрито',
      enLabel: 'Closed',
      ukDescription: 'План закрито; подальші зміни недоступні.',
      enDescription: 'The plan has been closed; no further changes are available.',
    },
    'purchaseOrder.PLACED': {
      tone: 'neutral',
      ukLabel: 'Розміщено',
      enLabel: 'Placed',
      ukDescription: 'Замовлення створено та передано постачальнику.',
      enDescription: 'The order has been created and sent to the supplier.',
    },
    'purchaseOrder.CONFIRMED': {
      tone: 'info',
      ukLabel: 'Підтверджено',
      enLabel: 'Confirmed',
      ukDescription: 'Постачальник підтвердив замовлення.',
      enDescription: 'The supplier confirmed the order.',
    },
    'purchaseOrder.CANCELLED': {
      tone: 'danger',
      ukLabel: 'Скасовано',
      enLabel: 'Cancelled',
      ukDescription: 'Замовлення скасовано і не буде виконано.',
      enDescription: 'The order has been cancelled and will not be fulfilled.',
    },
    'purchaseOrder.RECEIVED': {
      tone: 'success',
      ukLabel: 'Отримано',
      enLabel: 'Received',
      ukDescription: 'Замовлення отримано повністю.',
      enDescription: 'The order has been fully received.',
    },
    'purchaseOrderLine.PENDING': {
      tone: 'warning',
      ukLabel: 'Очікує підтвердження',
      enLabel: 'Pending',
      ukDescription: 'Постачальник ще не підтвердив постачання за цим рядком.',
      enDescription: 'The supplier has not yet confirmed supply for this line.',
    },
    'purchaseOrderLine.CONFIRMED': {
      tone: 'info',
      ukLabel: 'Підтверджено',
      enLabel: 'Confirmed',
      ukDescription: 'Постачальник підтвердив постачання за цим рядком.',
      enDescription: 'The supplier confirmed supply for this line.',
    },
    'purchaseOrderLine.IN_TRANSIT': {
      tone: 'info',
      ukLabel: 'У дорозі',
      enLabel: 'In transit',
      ukDescription: 'Вантаж за цим рядком у процесі доставки.',
      enDescription: 'The shipment for this line is in delivery.',
    },
    'purchaseOrderLine.DELIVERED': {
      tone: 'success',
      ukLabel: 'Доставлено',
      enLabel: 'Delivered',
      ukDescription: 'Позицію доставлено та отримано.',
      enDescription: 'The item has been delivered and received.',
    },
    'purchaseOrderLine.CANCELLED': {
      tone: 'danger',
      ukLabel: 'Скасовано',
      enLabel: 'Cancelled',
      ukDescription: 'Рядок замовлення скасовано.',
      enDescription: 'The order line has been cancelled.',
    },
    'procurementTask.CREATED': {
      tone: 'success',
      ukLabel: 'Створено',
      enLabel: 'Created',
      ukDescription: 'Контрольовану дію закупівлі створено в системі на основі погодженої заявки.',
      enDescription: 'The controlled procurement action has been created in the system based on the approved request.',
    },
    'recommendation.VALIDATED': {
      tone: 'success',
      ukLabel: 'Перевірено',
      enLabel: 'Validated',
      ukDescription: 'Рекомендація пройшла перевірку структури та готова до розгляду.',
      enDescription: 'The recommendation passed structural validation and is ready for review.',
    },
    'productionOrder.PLANNED': {
      tone: 'neutral',
      ukLabel: 'Заплановано',
      enLabel: 'Planned',
      ukDescription: 'Замовлення заплановано; виконання ще не розпочато.',
      enDescription: 'The order is planned; execution has not started.',
    },
    'productionOrder.RELEASED': {
      tone: 'info',
      ukLabel: 'Випущено у виробництво',
      enLabel: 'Released',
      ukDescription: 'Замовлення передано на виробництво.',
      enDescription: 'The order has been released to production.',
    },
    'productionOrder.IN_PROGRESS': {
      tone: 'info',
      ukLabel: 'Триває',
      enLabel: 'In progress',
      ukDescription: 'Замовлення у процесі виконання.',
      enDescription: 'The order is being executed.',
    },
    'productionOrder.COMPLETED': {
      tone: 'success',
      ukLabel: 'Завершено',
      enLabel: 'Completed',
      ukDescription: 'Замовлення виконано.',
      enDescription: 'The order has been completed.',
    },
    'productionOrder.CANCELLED': {
      tone: 'danger',
      ukLabel: 'Скасовано',
      enLabel: 'Cancelled',
      ukDescription: 'Замовлення скасовано.',
      enDescription: 'The order has been cancelled.',
    },
    'alternative.PROPOSED': {
      tone: 'info',
      ukLabel: 'Запропоновано',
      enLabel: 'Proposed',
      ukDescription: 'Альтернативу запропоновано; рішення ще не прийнято.',
      enDescription: 'The alternative has been proposed; no decision has been made yet.',
    },
    'alternative.APPROVED': {
      tone: 'success',
      ukLabel: 'Погоджено',
      enLabel: 'Approved',
      ukDescription: 'Альтернативу погоджено для використання.',
      enDescription: 'The alternative has been approved for use.',
    },
    'alternative.REJECTED': {
      tone: 'danger',
      ukLabel: 'Відхилено',
      enLabel: 'Rejected',
      ukDescription: 'Альтернативу відхилено.',
      enDescription: 'The alternative has been rejected.',
    },
    'auditEvent.APPROVAL_REQUEST_CREATED': {
      tone: 'neutral',
      ukLabel: 'Створено запит на погодження',
      enLabel: 'Approval request created',
      ukDescription: 'Користувач створив заявку на погодження контрольованої дії.',
      enDescription: 'A user created an approval request for a controlled action.',
    },
    'auditEvent.APPROVAL_APPROVED': {
      tone: 'neutral',
      ukLabel: 'Запит на погодження схвалено',
      enLabel: 'Approval approved',
      ukDescription: 'Уповноважений користувач погодив заявку.',
      enDescription: 'An authorized user approved the request.',
    },
    'auditEvent.APPROVAL_REJECTED': {
      tone: 'neutral',
      ukLabel: 'Запит на погодження відхилено',
      enLabel: 'Approval rejected',
      ukDescription: 'Уповноважений користувач відхилив заявку.',
      enDescription: 'An authorized user rejected the request.',
    },
    'auditEvent.PROCUREMENT_TASK_CREATION_ATTEMPTED': {
      tone: 'neutral',
      ukLabel: 'Спроба створення дії закупівлі',
      enLabel: 'Procurement action creation attempted',
      ukDescription: 'Система почала створення контрольованої дії закупівлі.',
      enDescription: 'The system began creating the controlled procurement action.',
    },
    'auditEvent.PROCUREMENT_TASK_CREATED': {
      tone: 'neutral',
      ukLabel: 'Дію закупівлі створено',
      enLabel: 'Procurement action created',
      ukDescription: 'Контрольовану дію закупівлі успішно створено.',
      enDescription: 'The controlled procurement action was created successfully.',
    },
    'auditEvent.PROCUREMENT_TASK_CREATION_FAILED': {
      tone: 'neutral',
      ukLabel: 'Помилка створення дії закупівлі',
      enLabel: 'Procurement action creation failed',
      ukDescription: 'Спроба створення контрольної дії завершилася помилкою.',
      enDescription: 'The attempt to create the controlled action ended with an error.',
    },
    'auditEntity.APPROVAL_REQUEST': {
      tone: 'neutral',
      ukLabel: 'Запит на погодження',
      enLabel: 'Approval request',
      ukDescription: 'Сутність, пов\'язана із запитом на погодження.',
      enDescription: 'An entity associated with an approval request.',
    },
    'auditEntity.PROCUREMENT_TASK': {
      tone: 'neutral',
      ukLabel: 'Дія закупівлі',
      enLabel: 'Procurement action',
      ukDescription: 'Сутність, пов\'язана з контрольованою дією закупівлі.',
      enDescription: 'An entity associated with a controlled procurement action.',
    },
    'traceCategory.user_action': {
      tone: 'neutral',
      ukLabel: 'Дія користувача',
      enLabel: 'User action',
      ukDescription: 'Крок, виконаний користувачем в інтерфейсі.',
      enDescription: 'A step performed by a user in the interface.',
    },
    'traceCategory.deterministic_calculation': {
      tone: 'neutral',
      ukLabel: 'Детермінований розрахунок',
      enLabel: 'Deterministic calculation',
      ukDescription: 'Результат обчислено детермінованим механізмом без участі моделі ШІ.',
      enDescription: 'A result computed by the deterministic engine without an AI model.',
    },
    'traceCategory.retrieval': {
      tone: 'neutral',
      ukLabel: 'Пошук даних',
      enLabel: 'Retrieval',
      ukDescription: 'Пошук релевантних документів у базі знань.',
      enDescription: 'Searching the knowledge base for relevant documents.',
    },
    'traceCategory.model_call': {
      tone: 'neutral',
      ukLabel: 'Виклик моделі ШІ',
      enLabel: 'Model call',
      ukDescription: 'Запит до мовної моделі та отримана відповідь.',
      enDescription: 'A request to the language model and its response.',
    },
    'traceCategory.structured_validation': {
      tone: 'neutral',
      ukLabel: 'Перевірка структури',
      enLabel: 'Structured validation',
      ukDescription: 'Перевірка відповіді моделі на відповідність визначеній схемі.',
      enDescription: 'Checking the model response against a defined schema.',
    },
    'traceCategory.recommendation': {
      tone: 'neutral',
      ukLabel: 'Рекомендація',
      enLabel: 'Recommendation',
      ukDescription: 'Сформована та збережена рекомендація щодо ризику.',
      enDescription: 'The generated and persisted recommendation about the risk.',
    },
    'traceCategory.approval_request': {
      tone: 'neutral',
      ukLabel: 'Запит на погодження',
      enLabel: 'Approval request',
      ukDescription: 'Створена заявка на погодження контрольованої дії.',
      enDescription: 'The created approval request for a controlled action.',
    },
    'traceCategory.human_decision': {
      tone: 'neutral',
      ukLabel: 'Рішення людини',
      enLabel: 'Human decision',
      ukDescription: 'Уповноважений користувач ухвалив рішення.',
      enDescription: 'An authorized user made a decision.',
    },
    'traceCategory.write_action': {
      tone: 'neutral',
      ukLabel: 'Контрольована дія',
      enLabel: 'Write action',
      ukDescription: 'Виконання контрольованої дії запису в системі.',
      enDescription: 'The execution of a controlled write action in the system.',
    },
};

/** Frozen per-domain machine-code lists (backend-support exhaustiveness). */
const DOMAIN_CODES: Record<string, readonly string[]> = {
  'workflowRun': ['PENDING', 'RUNNING', 'AWAITING_VALIDATION', 'COMPLETED', 'FAILED_VALIDATION', 'FAILED_PROVIDER', 'FAILED_INTERNAL', 'FAILED_RETRIEVAL'],
  'workflowStep': ['started', 'completed', 'failed'],
  'approval': ['PENDING', 'APPROVED', 'REJECTED'],
  'severity': ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
  'dataset': ['valid', 'invalid', 'not_loaded'],
  'health': ['healthy', 'degraded', 'unhealthy'],
  'healthCheck': ['ok', 'error', 'unknown'],
  'plan': ['DRAFT', 'APPROVED', 'EXECUTING', 'COMPLETED', 'CLOSED'],
  'purchaseOrder': ['PLACED', 'CONFIRMED', 'CANCELLED', 'RECEIVED'],
  'purchaseOrderLine': ['PENDING', 'CONFIRMED', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED'],
  'procurementTask': ['CREATED'],
  'recommendation': ['VALIDATED'],
  'productionOrder': ['PLANNED', 'RELEASED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'],
  'alternative': ['PROPOSED', 'APPROVED', 'REJECTED'],
  'auditEvent': ['APPROVAL_REQUEST_CREATED', 'APPROVAL_APPROVED', 'APPROVAL_REJECTED', 'PROCUREMENT_TASK_CREATION_ATTEMPTED', 'PROCUREMENT_TASK_CREATED', 'PROCUREMENT_TASK_CREATION_FAILED'],
  'auditEntity': ['APPROVAL_REQUEST', 'PROCUREMENT_TASK'],
  'traceCategory': ['user_action', 'deterministic_calculation', 'retrieval', 'model_call', 'structured_validation', 'recommendation', 'approval_request', 'human_decision', 'write_action'],
};

function ukLabel(id: string): string {
  return PINNED[id].ukLabel;
}
function enLabel(id: string): string {
  return PINNED[id].enLabel;
}

describe('status registry — registered pairs', () => {
  it('pins every registered (domain, code) pair exactly once', () => {
    const entries = allStatusEntries();
    expect(entries).toHaveLength(STATUS_ENTRY_COUNT);
    for (const entry of entries) {
      expect(PINNED[entry.id], entry.id).toBeDefined();
    }
    expect(Object.keys(PINNED)).toHaveLength(STATUS_ENTRY_COUNT);
  });

  it('registry code sets match the frozen backend-evidence domain lists', () => {
    const byDomain: Record<string, string[]> = {};
    for (const entry of allStatusEntries()) {
      (byDomain[entry.domain] ||= []).push(entry.code);
    }
    expect(Object.keys(byDomain).sort()).toEqual(Object.keys(DOMAIN_CODES).sort());
    for (const [domain, codes] of Object.entries(byDomain)) {
      expect(codes.sort(), domain).toEqual([...DOMAIN_CODES[domain]].sort());
    }
  });

  it('exports all 17 domains with at least one entry', () => {
    expect(statusDomains()).toHaveLength(17);
    for (const domain of statusDomains()) {
      expect(Object.keys(DOMAIN_CODES), domain).toContain(domain);
    }
  });

  it('resolves every pair as known with the exact machine code', () => {
    for (const entry of allStatusEntries()) {
      const resolved = resolveStatus(entry.domain, entry.code);
      expect(isKnownStatus(resolved), entry.id).toBe(true);
      expect(resolved.code, entry.id).toBe(entry.code);
      expect(resolved.domain, entry.id).toBe(entry.domain);
    }
  });
});

describe('status registry — exact Ukrainian labels', () => {
  it('produces every pinned Ukrainian label through the real i18n layer', async () => {
    await i18n.changeLanguage('uk');
    for (const entry of allStatusEntries()) {
      const resolved = resolveStatus(entry.domain, entry.code);
      expect(translateStatusLabel(resolved), entry.id).toBe(ukLabel(entry.id));
    }
  });
});

describe('status registry — exact English labels', () => {
  it('produces every pinned English label through the real i18n layer', async () => {
    await i18n.changeLanguage('en');
    for (const entry of allStatusEntries()) {
      const resolved = resolveStatus(entry.domain, entry.code);
      expect(translateStatusLabel(resolved), entry.id).toBe(enLabel(entry.id));
    }
  });
});

describe('status registry — exact Ukrainian descriptions', () => {
  it('produces every pinned Ukrainian description through the real i18n layer', async () => {
    await i18n.changeLanguage('uk');
    for (const entry of allStatusEntries()) {
      const resolved = resolveStatus(entry.domain, entry.code);
      expect(translateStatusDescription(resolved), entry.id).toBe(
        PINNED[entry.id].ukDescription,
      );
    }
  });
});

describe('status registry — exact English descriptions', () => {
  it('produces every pinned English description through the real i18n layer', async () => {
    await i18n.changeLanguage('en');
    for (const entry of allStatusEntries()) {
      const resolved = resolveStatus(entry.domain, entry.code);
      expect(translateStatusDescription(resolved), entry.id).toBe(
        PINNED[entry.id].enDescription,
      );
    }
  });

  it('no pinned label or description is empty', () => {
    for (const [id, pin] of Object.entries(PINNED)) {
      expect(pin.ukLabel.trim(), id).not.toBe('');
      expect(pin.enLabel.trim(), id).not.toBe('');
      expect(pin.ukDescription.trim(), id).not.toBe('');
      expect(pin.enDescription.trim(), id).not.toBe('');
    }
  });
});

describe('status registry — semantic tone mapping', () => {
  it('maps every pair to its frozen WP-UX-UA-02 tone', () => {
    for (const entry of allStatusEntries()) {
      expect(entry.tone, entry.id).toBe(PINNED[entry.id].tone);
    }
  });

  it('uses only the five design-token tones', () => {
    const allowed: StatusTone[] = ['neutral', 'info', 'success', 'warning', 'danger'];
    for (const entry of allStatusEntries()) {
      expect(allowed, entry.id).toContain(entry.tone);
    }
  });

  it('keeps the established workflow/risk semantics', () => {
    const toneOf = (id: string) => PINNED[id].tone;
    // workflowRun
    expect(toneOf('workflowRun.PENDING')).toBe('info');
    expect(toneOf('workflowRun.RUNNING')).toBe('info');
    expect(toneOf('workflowRun.AWAITING_VALIDATION')).toBe('warning');
    expect(toneOf('workflowRun.COMPLETED')).toBe('success');
    expect(toneOf('workflowRun.FAILED_PROVIDER')).toBe('danger');
    expect(toneOf('workflowRun.FAILED_VALIDATION')).toBe('danger');
    expect(toneOf('workflowRun.FAILED_INTERNAL')).toBe('danger');
    expect(toneOf('workflowRun.FAILED_RETRIEVAL')).toBe('danger');
    // severity
    expect(toneOf('severity.CRITICAL')).toBe('danger');
    expect(toneOf('severity.HIGH')).toBe('warning');
    expect(toneOf('severity.MEDIUM')).toBe('info');
    expect(toneOf('severity.LOW')).toBe('neutral');
    // audit classifications stay neutral
    expect(toneOf('auditEvent.APPROVAL_APPROVED')).toBe('neutral');
    expect(toneOf('auditEntity.APPROVAL_REQUEST')).toBe('neutral');
    expect(toneOf('traceCategory.model_call')).toBe('neutral');
  });
});

describe('status registry — unknown code behavior', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('uk');
  });

  it('returns the non-known fallback preserving the raw code', () => {
    const resolved = resolveStatus('plan', 'SOME_FUTURE_CODE');
    expect(resolved.known).toBe(false);
    expect(resolved.code).toBe('SOME_FUTURE_CODE');
    expect(resolved.tone).toBe('neutral');
  });

  it('labels the unknown fallback as Невідомий стан in Ukrainian', async () => {
    await i18n.changeLanguage('uk');
    const resolved = resolveStatus('plan', 'SOME_FUTURE_CODE');
    expect(translateStatusLabel(resolved)).toBe('Невідомий стан');
    expect(translateStatusDescription(resolved)).toBe('Система не має пояснення для цього значення. Технічний код збережено для діагностики.');
  });

  it('labels the unknown fallback as Unknown status in English', async () => {
    await i18n.changeLanguage('en');
    const resolved = resolveStatus('plan', 'SOME_FUTURE_CODE');
    expect(translateStatusLabel(resolved)).toBe('Unknown status');
    expect(translateStatusDescription(resolved)).toBe('The system has no explanation for this value. The technical code has been preserved for diagnosis.');
  });

  it('treats empty and null/undefined codes as unknown without throwing', () => {
    expect(resolveStatus('plan', '').known).toBe(false);
    expect(resolveStatus('plan', null).known).toBe(false);
    expect(resolveStatus('plan', undefined).known).toBe(false);
    expect(resolveStatus('plan', '').code).toBe('');
  });

  it('never throws for arbitrary strings in any domain', () => {
    for (const domain of statusDomains()) {
      expect(
        () => resolveStatus(domain, '%% some junk \\'),
        domain,
      ).not.toThrow();
    }
  });
});

describe('status registry — domain separation', () => {
  it('does not conflate identical codes across state machines', () => {
    const planCompleted = resolveStatus('plan', 'COMPLETED');
    const runCompleted = resolveStatus('workflowRun', 'COMPLETED');
    const poCompleted = resolveStatus('productionOrder', 'COMPLETED');
    expect(planCompleted.known).toBe(true);
    expect(runCompleted.known).toBe(true);
    expect(poCompleted.known).toBe(true);
    expect(
      planCompleted.known && planCompleted.labelKey !==
        (runCompleted.known ? runCompleted.labelKey : ''),
    ).toBe(true);
    expect(
      runCompleted.known &&
        runCompleted.labelKey !==
          (poCompleted.known ? poCompleted.labelKey : ''),
    ).toBe(true);
  });

  it('resolves a code known in one domain as unknown in another', () => {
    // EXECUTING exists only in plan — not in workflowRun.
    expect(resolveStatus('plan', 'EXECUTING').known).toBe(true);
    expect(resolveStatus('workflowRun', 'EXECUTING').known).toBe(false);
    // PENDING in approval vs purchaseOrderLine are distinct entries.
    expect(resolveStatus('approval', 'PENDING').known).toBe(true);
    expect(resolveStatus('purchaseOrderLine', 'PENDING').known).toBe(true);
    const a = resolveStatus('approval', 'PENDING');
    const l = resolveStatus('purchaseOrderLine', 'PENDING');
    expect(a.known && l.known && a.labelKey !== l.labelKey).toBe(true);
  });

  it('is case-sensitive like machine codes', () => {
    expect(resolveStatus('workflowStep', 'completed').known).toBe(true);
    expect(resolveStatus('workflowStep', 'COMPLETED').known).toBe(false);
  });
});

describe('status catalog — committed JSON parity and integrity', () => {
  it('uk and en status catalogs share the exact leaf-key set', () => {
    const leafs = (obj: object, prefix = ''): string[] =>
      Object.entries(obj).flatMap(([k, v]) =>
        typeof v === 'object' && v !== null
          ? leafs(v, `${prefix}${k}.`)
          : [`${prefix}${k}`],
      );
    const ukLeafs = leafs(ukCatalog).sort();
    const enLeafs = leafs(enCatalog).sort();
    expect(ukLeafs).toEqual(enLeafs);
    expect(ukLeafs.length).toBeGreaterThan(0);
  });

  it('contains no empty label/description values in either locale', () => {
    const walk = (obj: object, path: string, violations: string[]) => {
      for (const [k, v] of Object.entries(obj)) {
        const p = `${path}${k}`;
        if (typeof v === 'string') {
          if (v.trim() === '') violations.push(p);
        } else if (typeof v === 'object' && v !== null) {
          walk(v, `${p}.`, violations);
        }
      }
    };
    const v: string[] = [];
    walk(ukCatalog, '', v);
    walk(enCatalog, '', v);
    expect(v).toEqual([]);
  });

  it('STATUS_CATALOG_NS matches the registered i18n namespace', () => {
    expect(STATUS_CATALOG_NS).toBe('status');
    expect(i18n.hasResourceBundle('uk', 'status')).toBe(true);
    expect(i18n.hasResourceBundle('en', 'status')).toBe(true);
  });
});
