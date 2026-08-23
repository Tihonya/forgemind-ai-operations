import { describe, it, expect } from 'vitest';
import {
  WORKFLOW_STATE_LABELS,
  getWorkflowStateLabel,
  getWorkflowStateTone,
  isNonterminalState,
  isFailedState,
  NONTERMINAL_STATES,
  FAILED_STATES,
} from '@/lib/workflow-state-labels';

describe('workflow-state-labels', () => {
  describe('getWorkflowStateLabel', () => {
    it('maps all known nonterminal states', () => {
      expect(getWorkflowStateLabel('PENDING')).toBe('Queued');
      expect(getWorkflowStateLabel('RUNNING')).toBe('Analysis in progress');
      expect(getWorkflowStateLabel('AWAITING_VALIDATION')).toBe('Validating result');
    });

    it('maps COMPLETED', () => {
      expect(getWorkflowStateLabel('COMPLETED')).toBe('Completed');
    });

    it('maps all known failed states', () => {
      expect(getWorkflowStateLabel('FAILED_PROVIDER')).toBe('AI service unavailable');
      expect(getWorkflowStateLabel('FAILED_VALIDATION')).toBe('Validation failed');
      expect(getWorkflowStateLabel('FAILED_RETRIEVAL')).toBe('Evidence retrieval failed');
      expect(getWorkflowStateLabel('FAILED_INTERNAL')).toBe('Analysis failed');
    });

    it('returns Unknown for null/undefined/empty', () => {
      expect(getWorkflowStateLabel(null)).toBe('Unknown');
      expect(getWorkflowStateLabel(undefined)).toBe('Unknown');
      expect(getWorkflowStateLabel('')).toBe('Unknown');
    });

    it('returns the raw value for unknown states', () => {
      expect(getWorkflowStateLabel('SOME_NEW_STATE')).toBe('SOME_NEW_STATE');
    });
  });

  describe('getWorkflowStateTone', () => {
    it('returns active for nonterminal states', () => {
      expect(getWorkflowStateTone('PENDING')).toBe('neutral');
      expect(getWorkflowStateTone('RUNNING')).toBe('active');
      expect(getWorkflowStateTone('AWAITING_VALIDATION')).toBe('active');
    });

    it('returns success for COMPLETED', () => {
      expect(getWorkflowStateTone('COMPLETED')).toBe('success');
    });

    it('returns error for failed states', () => {
      expect(getWorkflowStateTone('FAILED_PROVIDER')).toBe('error');
      expect(getWorkflowStateTone('FAILED_VALIDATION')).toBe('error');
      expect(getWorkflowStateTone('FAILED_RETRIEVAL')).toBe('error');
      expect(getWorkflowStateTone('FAILED_INTERNAL')).toBe('error');
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
      expect(isFailedState('FAILED_PROVIDER')).toBe(true);
      expect(isFailedState('FAILED_VALIDATION')).toBe(true);
      expect(isFailedState('FAILED_RETRIEVAL')).toBe(true);
      expect(isFailedState('FAILED_INTERNAL')).toBe(true);
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

  describe('canonical mapping completeness', () => {
    it('covers all known workflow states', () => {
      const knownStates = [
        'PENDING',
        'RUNNING',
        'AWAITING_VALIDATION',
        'COMPLETED',
        'FAILED_PROVIDER',
        'FAILED_VALIDATION',
        'FAILED_RETRIEVAL',
        'FAILED_INTERNAL',
      ];
      for (const state of knownStates) {
        expect(WORKFLOW_STATE_LABELS[state]).toBeDefined();
      }
      expect(NONTERMINAL_STATES.size).toBe(3);
      expect(FAILED_STATES.size).toBe(4);
    });
  });
});
