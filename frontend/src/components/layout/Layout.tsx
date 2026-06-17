import { Outlet, Navigate } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { useBusiness } from '../../context/BusinessContext'
import { PageSpinner } from '../ui/Spinner'

export function Layout() {
  const { loading, selected } = useBusiness()

  if (loading) return <PageSpinner />
  if (!selected) return <Navigate to="/select-business" replace />

  return (
    <div className="flex h-screen bg-gray-50">
      <Sidebar />
      <main className="flex flex-1 flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
