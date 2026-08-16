import { BrowserRouter, Route, Routes } from 'react-router-dom'
import NotFound from './routes/not-found'
import Login from './routes/login'
import Dashboard from './routes/dashboard'
import SupplyRisk from './routes/supply-risk'
import SupplyRiskDetail from './routes/supply-risk-detail'
import WorkflowRunDetail from './routes/workflow-run-detail'
import ApprovalCenter from './routes/approval-center'
import AuditLog from './routes/audit-log'
import ProtectedRoute from './routes/protected'
import AuthenticatedLayout from './components/layout/AuthenticatedLayout'
import { AuthProvider } from './contexts/auth.context'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,
      retry: false,
      refetchOnWindowFocus: false,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* Login is outside ProtectedRoute — unauthenticated access */}
            <Route path="/login" element={<Login />} />

            {/* All other routes require authentication */}
            <Route element={<ProtectedRoute />}>
              <Route element={<AuthenticatedLayout />}>
                <Route index element={<Dashboard />} />
                <Route path="supply-risk" element={<SupplyRisk />} />
                <Route path="supply-risk/:riskId" element={<SupplyRiskDetail />} />
                <Route path="workflow-runs/:runId" element={<WorkflowRunDetail />} />
                <Route path="approval-center" element={<ApprovalCenter />} />
                <Route path="audit-log" element={<AuditLog />} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
