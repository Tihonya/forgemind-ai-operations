import { describe, expect, it } from 'vitest';

import { formatQuantity } from '@/lib/utils';

describe('formatQuantity', () => {
  it('formats zero correctly', () => {
    expect(formatQuantity('0.0000')).toBe('0');
  });

  it('formats whole numbers without decimals', () => {
    expect(formatQuantity('100.0000')).toBe('100');
  });

  it('formats decimal numbers with up to 2 decimals', () => {
    expect(formatQuantity('45.6789')).toBe('45.68');
    expect(formatQuantity('12.3000')).toBe('12.3');
  });

  it('formats small decimals', () => {
    expect(formatQuantity('0.5000')).toBe('0.5');
    expect(formatQuantity('0.0100')).toBe('0.01');
  });

  it('preserves large numbers', () => {
    expect(formatQuantity('1234567.8900')).toBe('1,234,567.89');
  });

  it('handles negative numbers', () => {
    expect(formatQuantity('-25.0000')).toBe('-25');
    expect(formatQuantity('-0.5000')).toBe('-0.5');
  });
});
