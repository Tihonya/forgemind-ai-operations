/**
 * Workflow-state label helpers — registry-backed (WP-UX-UA-04).
 *
 * Label expectations are resolved through the SAME i18n instance the app
 * uses, but the expected STRINGS are read from the committed catalogs (uk
 * and en), never copied from the implementation. Tone expectations pin the
 * semantic design-token vocabulary (neutral/info/success/warning/danger):
 * these are the WP-UX-UA-04 contract values for workflow states.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import i18n from '@/i18n';
import ukStatus from '@/i18n/locales/uk/status.json';
import enStatus from '@/i18n/locales/en/status.json';
import {
  getWorkflowStateLabel,
  getWorkflowStateTone,
  isNonterminalState,
  isFailedState,
  NONTERMINAL_STATES,
  FAILED_STATES,
} from '@/lib/workflow-state-labels';

function catalogLabel(locale: 'uk' | 'en', key: string): string {
  const catalog = locale === 'uk' ? ukStatus : enStatus;
  const bundle = (catalog as unknown as {
    workflowRun: Record<string, { label: string }>;
  }).workflowRun;
  return bundle[key].label;
}

const WORKFLOW_KEYS: Record<string, string> = {
  PENDING: 'pending',
  RUNNING: 'running',
  AWAITING_VALIDATION: 'awaitingValidation',
  COMPLETED: 'completed',
  FAILED_PROVIDER: 'failedProvider',
  FAILED_VALIDATION: 'failedValidation',
  FAILED_RETRIEVAL: 'failedRetrieval',
  FAILED_INTERNAL: 'failedInternal',
};

describe('workflow-state-labels (registry-backed)', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('uk');
  });

  afterEach(async () => {
    await i18n.changeLanguage('uk');
  });

  describe('getWorkflowStateLabel', () => {
    it('returns the Ukrainian registry label for every known state', async () => {
      for (const [code, key] of Object.entries(WORKFLOW_KEYS)) {
        expect(getWorkflowStateLabel(code), code).toBe(catalogLabel('uk', key));
      }
    });

    it('returns the English registry label under the en locale', async () => {
      await i18n.changeLanguage('en');
      for (const [code, key] of Object.entries(WORKFLOW_KEYS)) {
        expect(getWorkflowStateLabel(code), code).toBe(catalogLabel('en', key));
      }
    });

    it('returns Unknown for null/undefined/empty', () => {
      expect(getWorkflowStateLabel(null)).toBe('Unknown');
      expect(getWorkflowStateLabel(undefined)).toBe('Unknown');
      expect(getWorkflowStateLabel('')).toBe('Unknown');
    });

    it('preserves the raw value for unknown states', async () => {
      expect(getWorkflowStateLabel('SOME_NEW_STATE')).toBe('SOME_NEW_STATE');
      await i18n.changeLanguage('en');
      expect(getWorkflowStateLabel('SOME_NEW_STATE')).toBe('SOME_NEW_STATE');
    });
  });

  describe('getWorkflowStateTone', () => {
    it('maps nonterminal states to the registry info tone', () => {
      expect(getWorkflowStateTone('PENDING')).toBe('info');
      expect(getWorkflowStateTone('RUNNING')).toBe('info');
      expect(getWorkflowStateTone('AWAITING_VALIDATION')).toBe('warning');
    });

    it('maps COMPLETED to success', () => {
      expect(getWorkflowStateTone('COMPLETED')).toBe('success');
    });

    it('maps failed states to danger', () => {
      for (const code of ['FAILED_PROVIDER', 'FAILED_VALIDATION', 'FAILED_RETRIEVAL', 'FAILED_INTERNAL']) {
        expect(getWorkflowStateTone(code), code).toBe('danger');
      }
    });

    it('returns neutral for unknown/null', () => {
      expect(getWorkflowStateTone(null)).toBe('neutral');
      expect(getWorkflowStateTone('UNKNOWN_STATE')).toBe('neutral');
    });
  });

  describe('isNonterminalState', () => {
    it('returns true for PENDING, RUNNING, AWAITING_VALIDATION', () => {
      expect(isNonterminalState('PENDING')).toBe(true);
      expect(isNonterminalState('RUNNING')).toBe(true);
      expect(isNonterminalState('AWAITING_VALIDATION')).toBe(true);
    });

    it('returns false for COMPLETED and failed states', () => {
      expect(isNonterminalState('COMPLETED')).toBe(false);
      expect(isNonterminalState('FAILED_PROVIDER')).toBe(false);
    });

    it('returns false for null/undefined', () => {
      expect(isNonterminalState(null)).toBe(false);
      expect(isNonterminalState(undefined)).toBe(false);
    });
  });

  describe('isFailedState', () => {
    it('returns true for all FAILED_* states', () => {
      for (const code of ['FAILED_PROVIDER', 'FAILED_VALIDATION', 'FAILED_RETRIEVAL', 'FAILED_INTERNAL']) {
        expect(isFailedState(code), code).toBe(true);
      }
    });

    it('returns false for COMPLETED and nonterminal', () => {
      expect(isFailedState('COMPLETED')).toBe(false);
      expect(isFailedState('PENDING')).toBe(false);
    });

    it('returns false for null/undefined', () => {
      expect(isFailedState(null)).toBe(false);
      expect(isFailedState(undefined)).toBe(false);
    });
  });

  describe('state-set invariants', () => {
    it('keeps the canonical set sizes', () => {
      expect(NONTERMINAL_STATES.size).toBe(3);
      expect(FAILED_STATES.size).toBe(4);
    });
  });
});