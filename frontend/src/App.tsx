import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { BusinessProvider } from './context/BusinessContext'
import { Layout } from './components/layout/Layout'
import SelectBusiness from './pages/SelectBusiness'
import Dashboard from './pages/Dashboard'
import Documents from './pages/Documents'
import Transactions from './pages/Transactions'
import ReviewQueue from './pages/ReviewQueue'

export default function App() {
  return (
    <BusinessProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/select-business" element={<SelectBusiness />} />
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/transactions" element={<Transactions />} />
            <Route path="/review" element={<ReviewQueue />} />
          </Route>
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </BusinessProvider>
  )
}
