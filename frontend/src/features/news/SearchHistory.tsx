import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { NewsSearch } from '../../api/types'

interface Props {
  activeSearchId: string | null
  refreshKey: string | null
  onOpen: (searchId: string) => void
}

export function SearchHistory({ activeSearchId, refreshKey, onOpen }: Props) {
  const [searches, setSearches] = useState<NewsSearch[]>([])
  const [tick, setTick] = useState(0)

  // Mantém a lista de buscas em dia (buscas criadas pelo chat ou em outra aba aparecem sozinhas).
  useEffect(() => {
    const timer = setInterval(() => !document.hidden && setTick((t) => t + 1), 10000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    let cancelled = false
    api
      .listNewsSearches()
      .then((list) => !cancelled && setSearches(list))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [refreshKey, tick])

  if (searches.length === 0) return null
  return (
    <div className="history">
      <label htmlFor="history-select">Buscas anteriores</label>
      <select id="history-select" value={activeSearchId ?? ''} onChange={(e) => e.target.value && onOpen(e.target.value)}>
        <option value="">Selecione…</option>
        {searches.map((s) => (
          <option key={s.id} value={s.id}>
            {s.topic} · {new Date(s.created_at).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })}
            {s.status === 'done' ? ` (${s.items.length})` : s.status === 'failed' ? ' (falhou)' : ' (…)'}
          </option>
        ))}
      </select>
    </div>
  )
}
