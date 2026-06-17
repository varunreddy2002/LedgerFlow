import { NavLink } from 'react-router-dom'
import { useBusiness } from '../../context/BusinessContext'

const links = [
  { to: '/dashboard',    label: 'Dashboard',    icon: '▦' },
  { to: '/documents',    label: 'Documents',    icon: '↑' },
  { to: '/transactions', label: 'Transactions', icon: '≡' },
  { to: '/review',       label: 'Review queue', icon: '!' },
]

export function Sidebar() {
  const { businesses, selected, select } = useBusiness()

  return (
    <aside className="flex w-52 shrink-0 flex-col border-r border-gray-200 bg-white">
      <div className="flex h-14 items-center gap-2 border-b border-gray-200 px-4">
        <span className="text-blue-600 text-lg font-bold">◈</span>
        <span className="text-sm font-semibold text-gray-900">LedgerFlow</span>
      </div>

      <nav className="flex-1 space-y-0.5 p-2 pt-3">
        <p className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-widest text-gray-400">
          Menu
        </p>
        {links.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-700 font-medium'
                  : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
              }`
            }
          >
            <span className="w-4 text-center text-base leading-none">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-gray-200 p-3">
        <p className="mb-1 px-1 text-[10px] font-semibold uppercase tracking-widest text-gray-400">
          Business
        </p>
        <select
          value={selected?.id ?? ''}
          onChange={e => {
            const b = businesses.find(x => x.id === Number(e.target.value))
            if (b) select(b)
          }}
          className="w-full rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-xs text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {businesses.map(b => (
            <option key={b.id} value={b.id}>{b.name}</option>
          ))}
        </select>
      </div>
    </aside>
  )
}
