import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import DatasetStatusWidget from '../DatasetStatusWidget';
import { useDatasetStatus } from '@/hooks/useDatasetStatus';

const user = userEvent.setup();

vi.mock('@/hooks/useDatasetStatus');

function renderWithQuery(ui: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  );
}

describe('DatasetStatusWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    vi.mocked(useDatasetStatus).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetStatus>);

    renderWithQuery(<DatasetStatusWidget />);
    expect(screen.getByTestId('dataset-status-widget')).toBeInTheDocument();
    expect(screen.getByTestId('dataset-status-loading')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.mocked(useDatasetStatus).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
    } as ReturnType<typeof useDatasetStatus>);

    renderWithQuery(<DatasetStatusWidget />);
    expect(screen.getByTestId('dataset-status-error')).toBeInTheDocument();
    expect(screen.getByText('Dataset status unavailable')).toBeInTheDocument();
  });

  it('renders valid status', () => {
    vi.mocked(useDatasetStatus).mockReturnValue({
      data: {
        status: 'valid',
        dataset_version: 'v1.0',
        checksum_algorithm: 'sha256',
        expected_checksum: 'abc123',
        actual_checksum: 'abc123',
      },
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetStatus>);

    renderWithQuery(<DatasetStatusWidget />);
    expect(screen.getByTestId('dataset-content')).toBeInTheDocument();
    expect(screen.getByText('Valid')).toBeInTheDocument();
    expect(screen.getByTestId('dataset-status-valid')).toBeInTheDocument();
  });

  it('renders invalid status', () => {
    vi.mocked(useDatasetStatus).mockReturnValue({
      data: {
        status: 'invalid',
        dataset_version: 'v1.0',
        checksum_algorithm: 'sha256',
        expected_checksum: 'abc123',
        actual_checksum: 'def456',
      },
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetStatus>);

    renderWithQuery(<DatasetStatusWidget />);
    expect(screen.getByText('Invalid')).toBeInTheDocument();
    expect(screen.getByTestId('dataset-status-invalid')).toBeInTheDocument();
  });

  it('renders not_loaded status', () => {
    vi.mocked(useDatasetStatus).mockReturnValue({
      data: {
        status: 'not_loaded',
        dataset_version: 'v1.0',
        checksum_algorithm: 'sha256',
        expected_checksum: 'abc123',
        actual_checksum: null,
      },
      isLoading: false,
      isError: false,
      error: null,
    } as ReturnType<typeof useDatasetStatus>);

    renderWithQuery(<DatasetStatusWidget />);
    expect(screen.getByText('Not Loaded')).toBeInTheDocument();
    expect(screen.getByTestId('dataset-status-not-loaded')).toBeInTheDocument();
  });

  it('calls refetch when retry button is clicked', async () => {
    const refetchSpy = vi.fn();
    vi.mocked(useDatasetStatus).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      error: new Error('Network error'),
      refetch: refetchSpy,
    } as unknown as ReturnType<typeof useDatasetStatus>);

    renderWithQuery(<DatasetStatusWidget />);
    const retryButton = screen.getByTestId('dataset-status-retry');
    await user.click(retryButton);
    expect(refetchSpy).toHaveBeenCalledTimes(1);
  });
});
