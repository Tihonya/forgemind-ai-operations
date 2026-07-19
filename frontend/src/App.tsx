import { BrowserRouter, Route, Routes } from 'react-router-dom'
import RootLayout from './routes/root'
import NotFound from './routes/not-found'
import Login from './routes/login'
import ProtectedRoute from './routes/protected'
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
              <Route element={<RootLayout />}>
                <Route index element={<HomePlaceholder />} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function HomePlaceholder() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-steel-900 to-steel-800 text-white flex items-center justify-center">
      <div className="text-center space-y-4">
        <h1 className="text-5xl font-bold text-primary-400">ForgeMind</h1>
        <p className="text-xl text-steel-300">Supply Risk Intelligence</p>
        <div className="mt-8 p-6 bg-steel-800/50 rounded-lg border border-steel-700">
          <p className="text-steel-400">Phase 3.1 scaffold ready</p>
          <p className="text-sm text-steel-500 mt-2">Design system initialized</p>
        </div>
      </div>
    </div>
  )
}

export default App
