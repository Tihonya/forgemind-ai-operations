import { AlertTriangle } from 'lucide-react';

interface PartialFailurePlaceholderProps {
  label: string;
  error?: Error | null;
  onRetry?: () => void;
}

/**
 * Placeholder for enrichment panels that failed to load.
 * Shows an "unavailable" message with optional retry button.
 * Does not hide the whole page — only the failed panel.
 */
export function PartialFailurePlaceholder({
  label,
  error,
  onRetry,
}: PartialFailurePlaceholderProps) {
  const testId = `partial-failure-${label.toLowerCase().replace(/\s+/g, '-')}`;

  return (
    <div
      className="flex items-start gap-3 rounded-md border border-amber-600/30 bg-amber-600/10 px-4 py-3"
      data-testid={testId}
      role="status"
    >
      <AlertTriangle
        className="mt-0.5 h-5 w-5 flex-shrink-0 text-amber-500"
        aria-hidden="true"
      />
      <div className="flex-1">
        <p className="text-sm font-medium text-amber-300">
          {label} unavailable
        </p>
        {error && (
          <p className="mt-1 text-xs text-amber-400">{error.message}</p>
        )}
      </div>
      {onRetry && (
        <button
          type="button"
          className="rounded-md border border-amber-600/40 bg-amber-600/20 px-3 py-1 text-xs font-medium text-amber-300 hover:bg-amber-600/30"
          onClick={onRetry}
          data-testid={`retry-${label.toLowerCase().replace(/\s+/g, '-')}`}
        >
          Retry
        </button>
      )}
    </div>
  );
}
