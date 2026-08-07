import { ChevronDown, Search } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { listCurrencies } from '@/api'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import type { Currency } from '@/types'

type CurrencyOption = Pick<Currency, 'id' | 'code' | 'name' | 'flag'>

interface CurrencySelectProps {
  value: number | ''
  onChange: (currencyId: number, currency?: CurrencyOption) => void
  disabled?: boolean
  selectedOption?: CurrencyOption | null
  label?: string
  description?: string
  placeholder?: string
}

function formatCurrencyLabel(currency: CurrencyOption) {
  return `${currency.flag} ${currency.code} — ${currency.name}`
}

export function CurrencySelect({
  value,
  onChange,
  disabled,
  selectedOption,
  label = 'Base currency',
  description = "Your company's reimbursement currency. Receipts in other currencies are converted to this for policy checks and payouts.",
  placeholder = 'Choose base currency…',
}: CurrencySelectProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [currencies, setCurrencies] = useState<Currency[]>([])
  const [selectedCurrency, setSelectedCurrency] = useState<CurrencyOption | null>(
    selectedOption ?? null,
  )
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (selectedOption) {
      setSelectedCurrency(selectedOption)
    }
  }, [selectedOption])

  useEffect(() => {
    if (!open) return

    const timer = window.setTimeout(() => {
      setLoading(true)
      listCurrencies({ search: search || undefined, page_size: 50, is_active: 'true' })
        .then((res) => setCurrencies(res.data.results))
        .catch(() => setCurrencies([]))
        .finally(() => setLoading(false))
    }, 200)

    return () => window.clearTimeout(timer)
  }, [search, open])

  useEffect(() => {
    if (!open) return

    const handlePointerDown = (event: MouseEvent) => {
      if (!containerRef.current?.contains(event.target as Node)) {
        setOpen(false)
        setSearch('')
      }
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
        setSearch('')
      }
    }

    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [open])

  useEffect(() => {
    if (open) {
      window.setTimeout(() => searchRef.current?.focus(), 0)
    }
  }, [open])

  const handleSelect = (currency: Currency) => {
    setSelectedCurrency(currency)
    onChange(currency.id, currency)
    setOpen(false)
    setSearch('')
  }

  const displayValue =
    selectedCurrency && value === selectedCurrency.id
      ? formatCurrencyLabel(selectedCurrency)
      : null

  return (
    <div className="space-y-2">
      <div>
        <Label>{label}</Label>
        {description ? <p className="mt-1 text-xs text-gray-500">{description}</p> : null}
      </div>

      <div ref={containerRef} className="relative">
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen((current) => !current)}
          className={cn(
            'flex h-10 w-full items-center justify-between rounded-md border border-gray-300 bg-white px-3 text-left text-sm',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
            disabled && 'cursor-not-allowed opacity-50',
            open && 'border-primary ring-2 ring-primary/20',
          )}
        >
          <span className={cn('truncate', !displayValue && 'text-gray-500')}>
            {displayValue || placeholder}
          </span>
          <ChevronDown
            className={cn('h-4 w-4 shrink-0 text-gray-500 transition-transform', open && 'rotate-180')}
          />
        </button>

        {open && (
          <div className="absolute z-50 mt-1 w-full overflow-hidden rounded-md border border-gray-200 bg-white shadow-lg">
            <div className="border-b border-gray-100 p-2">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
                <input
                  ref={searchRef}
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by code or country…"
                  className="h-9 w-full rounded-md border border-gray-200 bg-white pl-8 pr-3 text-sm outline-none focus:border-primary focus:ring-1 focus:ring-primary/30"
                />
              </div>
            </div>

            <ul className="max-h-52 overflow-y-auto py-1">
              {loading ? (
                <li className="px-3 py-2 text-sm text-gray-500">Loading currencies…</li>
              ) : currencies.length === 0 ? (
                <li className="px-3 py-2 text-sm text-gray-500">No currencies found.</li>
              ) : (
                currencies.map((currency) => (
                  <li key={currency.id}>
                    <button
                      type="button"
                      onClick={() => handleSelect(currency)}
                      className={cn(
                        'flex w-full px-3 py-2 text-left text-sm hover:bg-gray-50',
                        value === currency.id && 'bg-blue-50 font-medium text-blue-900',
                      )}
                    >
                      {formatCurrencyLabel(currency)}
                    </button>
                  </li>
                ))
              )}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
