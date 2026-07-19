import { Outlet } from 'react-router-dom'

export default function RootLayout() {
  return (
    <div className="min-h-screen bg-steel-900 text-white">
      <Outlet />
    </div>
  )
}
