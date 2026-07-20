import { AlertTriangle } from 'lucide-react';

import { Button } from '@/components/ui/button';

interface DataErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  testId?: string;
}

/**
 * Shared error state component for data loading failures.
 * Displays an error message with optional retry button.
 * Uses role="alert" for accessibility.
 */
export function DataErrorState({
  title = 'Unable to load data',
  message,
  onRetry,
  testId = 'data-error-state',
}: DataErrorStateProps) {
  return (
    <div
      className="flex items-start gap-3 rounded-md border border-red-600/30 bg-red-600/10 px-4 py-3"
      data-testid={testId}
      role="alert"
    >
      <AlertTriangle
        className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500"
        aria-hidden="true"
      />
      <div className="flex-1">
        <p className="text-sm font-medium text-red-300">{title}</p>
        <p className="mt-1 text-xs text-red-400">{message}</p>
      </div>
      {onRetry && (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          data-testid={`${testId}-retry`}
          className="border-red-600/40 bg-red-600/20 text-red-300 hover:bg-red-600/30 hover:text-red-200"
        >
          Retry
        </Button>
      )}
    </div>
  );
}
