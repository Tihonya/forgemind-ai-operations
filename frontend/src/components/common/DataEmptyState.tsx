import { Package } from 'lucide-react';

interface DataEmptyStateProps {
  primaryText: string;
  secondaryText?: string;
  icon?: React.ReactNode;
  testId?: string;
}

/**
 * Shared empty state component for when no data is available.
 * Displays a centered message with optional icon and secondary text.
 */
export function DataEmptyState({
  primaryText,
  secondaryText,
  icon = <Package className="mb-3 h-10 w-10 text-steel-500" aria-hidden="true" />,
  testId = 'data-empty-state',
}: DataEmptyStateProps) {
  return (
    <div
      className="flex flex-col items-center justify-center rounded-md border border-steel-700 bg-steel-800/40 px-6 py-12 text-center"
      data-testid={testId}
    >
      {icon}
      <p className="text-sm font-medium text-steel-300">{primaryText}</p>
      {secondaryText && (
        <p className="mt-1 text-xs text-steel-500">{secondaryText}</p>
      )}
    </div>
  );
}
