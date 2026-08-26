/**
 * Localized status presentation registry (WP-UX-UA-04).
 *
 * The single deterministic frontend contract that maps every supported
 * repository machine code to localized product language, a plain-language
 * explanation, and a semantic tone — WITHOUT ever mutating the machine
 * value itself.
 *
 * Contract invariants:
 * - Lookup is always keyed by BOTH the status domain and the machine code.
 *   Identical strings in different state machines (e.g. workflow
 *   ``COMPLETED`` vs plan ``COMPLETED`` vs step ``completed``) are
 *   deliberately distinct registry entries and must never automatically
 *   share meaning, labels, or tones.
 * - Labels and descriptions come exclusively from the i18n catalogs
 *   (``status:`` namespaces, see the locale files). This registry stores
 *   i18n KEYS and structural facts only — no user-visible text lives here,
 *   so locale switches re-render every consumer reactively.
 * - Tones use only the WP-UX-UA-02 semantic design-token vocabulary:
 *   ``neutral``, ``info``, ``success``, ``warning``, ``danger``.
 * - Unknown codes fail safely: ``resolveStatus`` returns a deterministic
 *   unknown entry that preserves the original machine code (visible only as
 *   optional technical metadata) and never pretends to know its meaning.
 * - No persisted or transported machine value is translated or modified;
 *   data attributes like ``data-code`` preserve the original bytes.
 * - TypeScript exhaustiveness tests (see the sibling test file) pin the
 *   registry so a newly introduced repository code cannot silently bypass
 *   localization without a deliberate registry entry.
 */

const DOMAINS = [
  'workflowRun',
  'workflowStep',
  'approval',
  'severity',
  'dataset',
  'health',
  'healthCheck',
  'plan',
  'purchaseOrder',
  'purchaseOrderLine',
  'procurementTask',
  'recommendation',
  'productionOrder',
  'alternative',
  'auditEvent',
  'auditEntity',
  'traceCategory',
] as const

export type StatusDomain = (typeof DOMAINS)[number]

/**
 * Semantic tone vocabulary: repository-native WP-UX-UA-02 design tokens.
 * ``neutral`` / ``info`` / ``success`` / ``warning`` / ``danger``.
 */
export type StatusTone = 'neutral' | 'info' | 'success' | 'warning' | 'danger'

export interface StatusDefinition {
  /** Discriminant: a known registry entry. */
  known: true
  /** Registry id — ``${domain}.${CODE}`` (never rendered). */
  id: string
  domain: StatusDomain
  /** Original machine code, exactly as the backend transports it. */
  code: string
  /** i18n key for the localized short label. */
  labelKey: string
  /** i18n key for the localized plain-language explanation. */
  descriptionKey: string
  /** Semantic tone (WP-UX-UA-02 design tokens). */
  tone: StatusTone
  /** Optional machine-code prefix shown in diagnostics only. */
  codeDisplay?: string
}

/** The one deterministic unknown-status entry style, per domain. */
export interface UnknownStatus {
  known: false
  domain: StatusDomain
  /** The original machine code, preserved verbatim for diagnosis. */
  code: string
  labelKey: string
  descriptionKey: string
  tone: StatusTone
}

export type ResolvedStatus = StatusDefinition | UnknownStatus

/** i18n namespace that owns the localized registry labels/descriptions. */
export const STATUS_CATALOG_NS = 'status' as const

export type StatusBundleKey = never // placeholder — removed in favor of runtime keys

/** Entity-context keys — who owns a status, resolved via ``status:entity.<key>``. */
export type StatusEntityKey =
  | 'workflowRun'
  | 'workflowStep'
  | 'approval'
  | 'severity'
  | 'dataset'
  | 'health'
  | 'healthCheck'
  | 'plan'
  | 'purchaseOrder'
  | 'purchaseOrderLine'
  | 'procurementTask'
  | 'recommendation'
  | 'productionOrder'
  | 'alternative'
  | 'auditEvent'
  | 'auditEntity'
  | 'traceCategory'
  | 'unknown'

interface RegistryInternals {
  /** id → definition (known entries). */
  entries: Readonly<Record<string, StatusDefinition>>
  /** domain → definition list (stable presentation order). */
  byDomain: Readonly<Record<StatusDomain, readonly StatusDefinition[]>>
}

/** Same as ``StatusDefinition`` minus the discriminant, added centrally. */
type StatusSeed = Omit<StatusDefinition, 'known'>

function define(seeds: readonly StatusSeed[]): RegistryInternals {
  const byDomain: Record<StatusDomain, StatusDefinition[]> = {} as Record<
    StatusDomain,
    StatusDefinition[]
  >
  for (const domain of DOMAINS) byDomain[domain] = []
  const map: Record<string, StatusDefinition> = {}
  for (const seed of seeds) {
    const entry: StatusDefinition = { known: true, ...seed }
    map[entry.id] = entry
    byDomain[entry.domain].push(entry)
  }
  for (const domain of DOMAINS) Object.freeze(byDomain[domain])
  return { entries: Object.freeze(map), byDomain: Object.freeze(byDomain) }
}

const INTERNALS = define([
  // ── workflowRun ──────────────────────────────────────────────────────────
  {
    id: 'workflowRun.PENDING',
    domain: 'workflowRun',
    code: 'PENDING',
    labelKey: 'workflowRun.pending.label',
    descriptionKey: 'workflowRun.pending.description',
    tone: 'info',
  },
  {
    id: 'workflowRun.RUNNING',
    domain: 'workflowRun',
    code: 'RUNNING',
    labelKey: 'workflowRun.running.label',
    descriptionKey: 'workflowRun.running.description',
    tone: 'info',
  },
  {
    id: 'workflowRun.AWAITING_VALIDATION',
    domain: 'workflowRun',
    code: 'AWAITING_VALIDATION',
    labelKey: 'workflowRun.awaitingValidation.label',
    descriptionKey: 'workflowRun.awaitingValidation.description',
    tone: 'warning',
  },
  {
    id: 'workflowRun.COMPLETED',
    domain: 'workflowRun',
    code: 'COMPLETED',
    labelKey: 'workflowRun.completed.label',
    descriptionKey: 'workflowRun.completed.description',
    tone: 'success',
  },
  {
    id: 'workflowRun.FAILED_VALIDATION',
    domain: 'workflowRun',
    code: 'FAILED_VALIDATION',
    labelKey: 'workflowRun.failedValidation.label',
    descriptionKey: 'workflowRun.failedValidation.description',
    tone: 'danger',
  },
  {
    id: 'workflowRun.FAILED_PROVIDER',
    domain: 'workflowRun',
    code: 'FAILED_PROVIDER',
    labelKey: 'workflowRun.failedProvider.label',
    descriptionKey: 'workflowRun.failedProvider.description',
    tone: 'danger',
  },
  {
    id: 'workflowRun.FAILED_INTERNAL',
    domain: 'workflowRun',
    code: 'FAILED_INTERNAL',
    labelKey: 'workflowRun.failedInternal.label',
    descriptionKey: 'workflowRun.failedInternal.description',
    tone: 'danger',
  },
  {
    id: 'workflowRun.FAILED_RETRIEVAL',
    domain: 'workflowRun',
    code: 'FAILED_RETRIEVAL',
    labelKey: 'workflowRun.failedRetrieval.label',
    descriptionKey: 'workflowRun.failedRetrieval.description',
    tone: 'danger',
  },

  // ── workflowStep ─────────────────────────────────────────────────────────
  {
    id: 'workflowStep.started',
    domain: 'workflowStep',
    code: 'started',
    labelKey: 'workflowStep.started.label',
    descriptionKey: 'workflowStep.started.description',
    tone: 'info',
  },
  {
    id: 'workflowStep.completed',
    domain: 'workflowStep',
    code: 'completed',
    labelKey: 'workflowStep.completed.label',
    descriptionKey: 'workflowStep.completed.description',
    tone: 'success',
  },
  {
    id: 'workflowStep.failed',
    domain: 'workflowStep',
    code: 'failed',
    labelKey: 'workflowStep.failed.label',
    descriptionKey: 'workflowStep.failed.description',
    tone: 'danger',
  },

  // ── approval ─────────────────────────────────────────────────────────────
  {
    id: 'approval.PENDING',
    domain: 'approval',
    code: 'PENDING',
    labelKey: 'approval.pending.label',
    descriptionKey: 'approval.pending.description',
    tone: 'warning',
  },
  {
    id: 'approval.APPROVED',
    domain: 'approval',
    code: 'APPROVED',
    labelKey: 'approval.approved.label',
    descriptionKey: 'approval.approved.description',
    tone: 'success',
  },
  {
    id: 'approval.REJECTED',
    domain: 'approval',
    code: 'REJECTED',
    labelKey: 'approval.rejected.label',
    descriptionKey: 'approval.rejected.description',
    tone: 'danger',
  },

  // ── severity ─────────────────────────────────────────────────────────────
  {
    id: 'severity.CRITICAL',
    domain: 'severity',
    code: 'CRITICAL',
    labelKey: 'severity.critical.label',
    descriptionKey: 'severity.critical.description',
    tone: 'danger',
  },
  {
    id: 'severity.HIGH',
    domain: 'severity',
    code: 'HIGH',
    labelKey: 'severity.high.label',
    descriptionKey: 'severity.high.description',
    tone: 'warning',
  },
  {
    id: 'severity.MEDIUM',
    domain: 'severity',
    code: 'MEDIUM',
    labelKey: 'severity.medium.label',
    descriptionKey: 'severity.medium.description',
    tone: 'info',
  },
  {
    id: 'severity.LOW',
    domain: 'severity',
    code: 'LOW',
    labelKey: 'severity.low.label',
    descriptionKey: 'severity.low.description',
    tone: 'neutral',
  },

  // ── dataset ──────────────────────────────────────────────────────────────
  {
    id: 'dataset.valid',
    domain: 'dataset',
    code: 'valid',
    labelKey: 'dataset.valid.label',
    descriptionKey: 'dataset.valid.description',
    tone: 'success',
  },
  {
    id: 'dataset.invalid',
    domain: 'dataset',
    code: 'invalid',
    labelKey: 'dataset.invalid.label',
    descriptionKey: 'dataset.invalid.description',
    tone: 'danger',
  },
  {
    id: 'dataset.not_loaded',
    domain: 'dataset',
    code: 'not_loaded',
    labelKey: 'dataset.notLoaded.label',
    descriptionKey: 'dataset.notLoaded.description',
    tone: 'neutral',
  },

  // ── health ───────────────────────────────────────────────────────────────
  {
    id: 'health.healthy',
    domain: 'health',
    code: 'healthy',
    labelKey: 'health.healthy.label',
    descriptionKey: 'health.healthy.description',
    tone: 'success',
  },
  {
    id: 'health.degraded',
    domain: 'health',
    code: 'degraded',
    labelKey: 'health.degraded.label',
    descriptionKey: 'health.degraded.description',
    tone: 'warning',
  },
  {
    id: 'health.unhealthy',
    domain: 'health',
    code: 'unhealthy',
    labelKey: 'health.unhealthy.label',
    descriptionKey: 'health.unhealthy.description',
    tone: 'danger',
  },

  // ── healthCheck (dependency check values) ────────────────────────────────
  {
    id: 'healthCheck.ok',
    domain: 'healthCheck',
    code: 'ok',
    labelKey: 'healthCheck.ok.label',
    descriptionKey: 'healthCheck.ok.description',
    tone: 'success',
  },
  {
    id: 'healthCheck.error',
    domain: 'healthCheck',
    code: 'error',
    labelKey: 'healthCheck.error.label',
    descriptionKey: 'healthCheck.error.description',
    tone: 'danger',
  },
  {
    id: 'healthCheck.unknown',
    domain: 'healthCheck',
    code: 'unknown',
    labelKey: 'healthCheck.unknown.label',
    descriptionKey: 'healthCheck.unknown.description',
    tone: 'neutral',
  },

  // ── plan ─────────────────────────────────────────────────────────────────
  {
    id: 'plan.DRAFT',
    domain: 'plan',
    code: 'DRAFT',
    labelKey: 'plan.draft.label',
    descriptionKey: 'plan.draft.description',
    tone: 'neutral',
  },
  {
    id: 'plan.APPROVED',
    domain: 'plan',
    code: 'APPROVED',
    labelKey: 'plan.approved.label',
    descriptionKey: 'plan.approved.description',
    tone: 'success',
  },
  {
    id: 'plan.EXECUTING',
    domain: 'plan',
    code: 'EXECUTING',
    labelKey: 'plan.executing.label',
    descriptionKey: 'plan.executing.description',
    tone: 'info',
  },
  {
    id: 'plan.COMPLETED',
    domain: 'plan',
    code: 'COMPLETED',
    labelKey: 'plan.completed.label',
    descriptionKey: 'plan.completed.description',
    tone: 'success',
  },
  {
    id: 'plan.CLOSED',
    domain: 'plan',
    code: 'CLOSED',
    labelKey: 'plan.closed.label',
    descriptionKey: 'plan.closed.description',
    tone: 'neutral',
  },

  // ── purchaseOrder (header) ───────────────────────────────────────────────
  {
    id: 'purchaseOrder.PLACED',
    domain: 'purchaseOrder',
    code: 'PLACED',
    labelKey: 'purchaseOrder.placed.label',
    descriptionKey: 'purchaseOrder.placed.description',
    tone: 'neutral',
  },
  {
    id: 'purchaseOrder.CONFIRMED',
    domain: 'purchaseOrder',
    code: 'CONFIRMED',
    labelKey: 'purchaseOrder.confirmed.label',
    descriptionKey: 'purchaseOrder.confirmed.description',
    tone: 'info',
  },
  {
    id: 'purchaseOrder.CANCELLED',
    domain: 'purchaseOrder',
    code: 'CANCELLED',
    labelKey: 'purchaseOrder.cancelled.label',
    descriptionKey: 'purchaseOrder.cancelled.description',
    tone: 'danger',
  },
  {
    id: 'purchaseOrder.RECEIVED',
    domain: 'purchaseOrder',
    code: 'RECEIVED',
    labelKey: 'purchaseOrder.received.label',
    descriptionKey: 'purchaseOrder.received.description',
    tone: 'success',
  },

  // ── purchaseOrderLine ────────────────────────────────────────────────────
  {
    id: 'purchaseOrderLine.PENDING',
    domain: 'purchaseOrderLine',
    code: 'PENDING',
    labelKey: 'purchaseOrderLine.pending.label',
    descriptionKey: 'purchaseOrderLine.pending.description',
    tone: 'warning',
  },
  {
    id: 'purchaseOrderLine.CONFIRMED',
    domain: 'purchaseOrderLine',
    code: 'CONFIRMED',
    labelKey: 'purchaseOrderLine.confirmed.label',
    descriptionKey: 'purchaseOrderLine.confirmed.description',
    tone: 'info',
  },
  {
    id: 'purchaseOrderLine.IN_TRANSIT',
    domain: 'purchaseOrderLine',
    code: 'IN_TRANSIT',
    labelKey: 'purchaseOrderLine.inTransit.label',
    descriptionKey: 'purchaseOrderLine.inTransit.description',
    tone: 'info',
  },
  {
    id: 'purchaseOrderLine.DELIVERED',
    domain: 'purchaseOrderLine',
    code: 'DELIVERED',
    labelKey: 'purchaseOrderLine.delivered.label',
    descriptionKey: 'purchaseOrderLine.delivered.description',
    tone: 'success',
  },
  {
    id: 'purchaseOrderLine.CANCELLED',
    domain: 'purchaseOrderLine',
    code: 'CANCELLED',
    labelKey: 'purchaseOrderLine.cancelled.label',
    descriptionKey: 'purchaseOrderLine.cancelled.description',
    tone: 'danger',
  },

  // ── procurementTask ──────────────────────────────────────────────────────
  {
    id: 'procurementTask.CREATED',
    domain: 'procurementTask',
    code: 'CREATED',
    labelKey: 'procurementTask.created.label',
    descriptionKey: 'procurementTask.created.description',
    tone: 'success',
  },

  // ── recommendation ───────────────────────────────────────────────────────
  {
    id: 'recommendation.VALIDATED',
    domain: 'recommendation',
    code: 'VALIDATED',
    labelKey: 'recommendation.validated.label',
    descriptionKey: 'recommendation.validated.description',
    tone: 'success',
  },

  // ── productionOrder ──────────────────────────────────────────────────────
  {
    id: 'productionOrder.PLANNED',
    domain: 'productionOrder',
    code: 'PLANNED',
    labelKey: 'productionOrder.planned.label',
    descriptionKey: 'productionOrder.planned.description',
    tone: 'neutral',
  },
  {
    id: 'productionOrder.RELEASED',
    domain: 'productionOrder',
    code: 'RELEASED',
    labelKey: 'productionOrder.released.label',
    descriptionKey: 'productionOrder.released.description',
    tone: 'info',
  },
  {
    id: 'productionOrder.IN_PROGRESS',
    domain: 'productionOrder',
    code: 'IN_PROGRESS',
    labelKey: 'productionOrder.inProgress.label',
    descriptionKey: 'productionOrder.inProgress.description',
    tone: 'info',
  },
  {
    id: 'productionOrder.COMPLETED',
    domain: 'productionOrder',
    code: 'COMPLETED',
    labelKey: 'productionOrder.completed.label',
    descriptionKey: 'productionOrder.completed.description',
    tone: 'success',
  },
  {
    id: 'productionOrder.CANCELLED',
    domain: 'productionOrder',
    code: 'CANCELLED',
    labelKey: 'productionOrder.cancelled.label',
    descriptionKey: 'productionOrder.cancelled.description',
    tone: 'danger',
  },

  // ── alternative ──────────────────────────────────────────────────────────
  {
    id: 'alternative.PROPOSED',
    domain: 'alternative',
    code: 'PROPOSED',
    labelKey: 'alternative.proposed.label',
    descriptionKey: 'alternative.proposed.description',
    tone: 'info',
  },
  {
    id: 'alternative.APPROVED',
    domain: 'alternative',
    code: 'APPROVED',
    labelKey: 'alternative.approved.label',
    descriptionKey: 'alternative.approved.description',
    tone: 'success',
  },
  {
    id: 'alternative.REJECTED',
    domain: 'alternative',
    code: 'REJECTED',
    labelKey: 'alternative.rejected.label',
    descriptionKey: 'alternative.rejected.description',
    tone: 'danger',
  },

  // ── auditEvent (immutable event types, not states) ─────────────────────────
  {
    id: 'auditEvent.APPROVAL_REQUEST_CREATED',
    domain: 'auditEvent',
    code: 'APPROVAL_REQUEST_CREATED',
    labelKey: 'auditEvent.approvalRequestCreated.label',
    descriptionKey: 'auditEvent.approvalRequestCreated.description',
    tone: 'neutral',
  },
  {
    id: 'auditEvent.APPROVAL_APPROVED',
    domain: 'auditEvent',
    code: 'APPROVAL_APPROVED',
    labelKey: 'auditEvent.approvalApproved.label',
    descriptionKey: 'auditEvent.approvalApproved.description',
    tone: 'neutral',
  },
  {
    id: 'auditEvent.APPROVAL_REJECTED',
    domain: 'auditEvent',
    code: 'APPROVAL_REJECTED',
    labelKey: 'auditEvent.approvalRejected.label',
    descriptionKey: 'auditEvent.approvalRejected.description',
    tone: 'neutral',
  },
  {
    id: 'auditEvent.PROCUREMENT_TASK_CREATION_ATTEMPTED',
    domain: 'auditEvent',
    code: 'PROCUREMENT_TASK_CREATION_ATTEMPTED',
    labelKey: 'auditEvent.procurementTaskCreationAttempted.label',
    descriptionKey: 'auditEvent.procurementTaskCreationAttempted.description',
    tone: 'neutral',
  },
  {
    id: 'auditEvent.PROCUREMENT_TASK_CREATED',
    domain: 'auditEvent',
    code: 'PROCUREMENT_TASK_CREATED',
    labelKey: 'auditEvent.procurementTaskCreated.label',
    descriptionKey: 'auditEvent.procurementTaskCreated.description',
    tone: 'neutral',
  },
  {
    id: 'auditEvent.PROCUREMENT_TASK_CREATION_FAILED',
    domain: 'auditEvent',
    code: 'PROCUREMENT_TASK_CREATION_FAILED',
    labelKey: 'auditEvent.procurementTaskCreationFailed.label',
    descriptionKey: 'auditEvent.procurementTaskCreationFailed.description',
    tone: 'neutral',
  },

  // ── auditEntity (entity type labels) ──────────────────────────────────────
  {
    id: 'auditEntity.APPROVAL_REQUEST',
    domain: 'auditEntity',
    code: 'APPROVAL_REQUEST',
    labelKey: 'auditEntity.approvalRequest.label',
    descriptionKey: 'auditEntity.approvalRequest.description',
    tone: 'neutral',
  },
  {
    id: 'auditEntity.PROCUREMENT_TASK',
    domain: 'auditEntity',
    code: 'PROCUREMENT_TASK',
    labelKey: 'auditEntity.procurementTask.label',
    descriptionKey: 'auditEntity.procurementTask.description',
    tone: 'neutral',
  },

  // ── traceCategory (AT-012 nine-item trace categories) ─────────────────────
  {
    id: 'traceCategory.user_action',
    domain: 'traceCategory',
    code: 'user_action',
    labelKey: 'traceCategory.userAction.label',
    descriptionKey: 'traceCategory.userAction.description',
    tone: 'neutral',
  },
  {
    id: 'traceCategory.deterministic_calculation',
    domain: 'traceCategory',
    code: 'deterministic_calculation',
    labelKey: 'traceCategory.deterministicCalculation.label',
    descriptionKey: 'traceCategory.deterministicCalculation.description',
    tone: 'neutral',
  },
  {
    id: 'traceCategory.retrieval',
    domain: 'traceCategory',
    code: 'retrieval',
    labelKey: 'traceCategory.retrieval.label',
    descriptionKey: 'traceCategory.retrieval.description',
    tone: 'neutral',
  },
  {
    id: 'traceCategory.model_call',
    domain: 'traceCategory',
    code: 'model_call',
    labelKey: 'traceCategory.modelCall.label',
    descriptionKey: 'traceCategory.modelCall.description',
    tone: 'neutral',
  },
  {
    id: 'traceCategory.structured_validation',
    domain: 'traceCategory',
    code: 'structured_validation',
    labelKey: 'traceCategory.structuredValidation.label',
    descriptionKey: 'traceCategory.structuredValidation.description',
    tone: 'neutral',
  },
  {
    id: 'traceCategory.recommendation',
    domain: 'traceCategory',
    code: 'recommendation',
    labelKey: 'traceCategory.recommendation.label',
    descriptionKey: 'traceCategory.recommendation.description',
    tone: 'neutral',
  },
  {
    id: 'traceCategory.approval_request',
    domain: 'traceCategory',
    code: 'approval_request',
    labelKey: 'traceCategory.approvalRequest.label',
    descriptionKey: 'traceCategory.approvalRequest.description',
    tone: 'neutral',
  },
  {
    id: 'traceCategory.human_decision',
    domain: 'traceCategory',
    code: 'human_decision',
    labelKey: 'traceCategory.humanDecision.label',
    descriptionKey: 'traceCategory.humanDecision.description',
    tone: 'neutral',
  },
  {
    id: 'traceCategory.write_action',
    domain: 'traceCategory',
    code: 'write_action',
    labelKey: 'traceCategory.writeAction.label',
    descriptionKey: 'traceCategory.writeAction.description',
    tone: 'neutral',
  },
])

/** Number of registered known entries (test/oracle constant, no behavior). */
export const STATUS_ENTRY_COUNT = Object.keys(INTERNALS.entries).length

/**
 * Deterministic unknown-status result. Preserves the original machine code
 * verbatim so it remains diagnosable; the localized label/description are
 * the neutral "unknown value" wording from the catalogs.
 */
function unknownEntry(domain: StatusDomain, code: string): UnknownStatus {
  return {
    known: false,
    domain,
    code,
    labelKey: 'unknown.value.label',
    descriptionKey: 'unknown.value.description',
    tone: 'neutral',
  }
}

const EMPTY_CODE = ''

/**
 * Resolve a status presentation deterministically.
 *
 * @param domain   the status domain (state machine the value belongs to).
 * @param code     the raw machine code exactly as the backend transported it.
 *                 A falsy value resolves to the unknown entry with an empty
 *                 machine code.
 * @returns        known entry or the unknown fallback. Never throws.
 */
export function resolveStatus(
  domain: StatusDomain,
  code: string | null | undefined,
): ResolvedStatus {
  const raw = code ?? EMPTY_CODE
  // Odd/coerced codes are treated as raw strings; the exact code participates
  // in the lookup — case-sensitive, because machine codes are.
  return INTERNALS.entries[`${domain}.${raw}`] ?? unknownEntry(domain, raw)
}

/**
 * Every known registry entry (fixed order), for exhaustive tests, tables,
 * and the evidence inventory. Read-only.
 */
export function allStatusEntries(): readonly StatusDefinition[] {
  return Object.values(INTERNALS.entries)
}

/** All domains that have at least one known entry. */
export function statusDomains(): readonly StatusDomain[] {
  return Object.keys(INTERNALS.byDomain) as StatusDomain[]
}

/**
 * Whether the resolution is known (discriminates the types).
 */
export function isKnownStatus(
  entry: ResolvedStatus,
): entry is StatusDefinition {
  return entry.known !== false
}