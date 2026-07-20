import { Info } from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface PlaceholderWidgetProps {
  title: string;
  message: string;
  icon?: React.ReactNode;
}

/**
 * Placeholder widget for future-phase features.
 *
 * Renders a static informational card with no network calls.
 * Visually distinct from live widgets (muted styling, dashed border).
 */
export default function PlaceholderWidget({
  title,
  message,
  icon,
}: PlaceholderWidgetProps) {
  return (
    <Card
      className="border-dashed border-steel-700 bg-steel-900/40 opacity-60"
      data-testid="placeholder-widget"
    >
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-steel-400">
          {icon ?? <Info className="h-4 w-4" aria-hidden="true" />}
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-steel-500">{message}</p>
      </CardContent>
    </Card>
  );
}
