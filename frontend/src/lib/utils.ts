import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Format a quantity string (decimal with 4 places) for display.
 * Removes trailing zeros and formats with thousands separators.
 * 
 * Examples:
 *   "0.0000" → "0"
 *   "100.0000" → "100"
 *   "45.6789" → "45.68"
 *   "12.3000" → "12.3"
 *   "1234567.8900" → "1,234,567.89"
 */
export function formatQuantity(value: string): string {
  const num = parseFloat(value);
  if (isNaN(num)) return '0';
  
  // Format with up to 2 decimal places, removing trailing zeros
  const formatted = num.toFixed(2).replace(/\.?0+$/, '');
  
  // Add thousands separators
  const parts = formatted.split('.');
  parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  
  return parts.join('.');
}
