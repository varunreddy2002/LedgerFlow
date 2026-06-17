import { createContext, useContext, useEffect, useState } from 'react'
import type { Business } from '../types'

interface BusinessContextValue {
  businesses: Business[]
  selected: Business | null
  select: (b: Business) => void
  loading: boolean
}

const BusinessContext = createContext<BusinessContextValue | null>(null)

const STORAGE_KEY = 'ledgerflow_business_id'

export function BusinessProvider({ children }: { children: React.ReactNode }) {
  const [businesses, setBusinesses] = useState<Business[]>([])
  const [selected, setSelected] = useState<Business | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch('/api/businesses')
      .then(r => r.json())
      .then((data: Business[]) => {
        setBusinesses(data)
        const storedId = Number(localStorage.getItem(STORAGE_KEY))
        const match = data.find(b => b.id === storedId) ?? data[0] ?? null
        setSelected(match)
      })
      .finally(() => setLoading(false))
  }, [])

  function select(b: Business) {
    setSelected(b)
    localStorage.setItem(STORAGE_KEY, String(b.id))
  }

  return (
    <BusinessContext.Provider value={{ businesses, selected, select, loading }}>
      {children}
    </BusinessContext.Provider>
  )
}

export function useBusiness() {
  const ctx = useContext(BusinessContext)
  if (!ctx) throw new Error('useBusiness must be used inside BusinessProvider')
  return ctx
}
