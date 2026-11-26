import { useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { ScriptEntry } from '../../api/types'

interface Props {
  onOpen: (entry: ScriptEntry) => void
  onClose: () => void
}

const PUBLICATION: Record<string, string> = {
  drafting: 'publicação em preparo',
  ready: 'publicação em rascunho',
  publishing: 'publicando…',
  published: 'publicado no YouTube',
  failed: 'publicação falhou',
}
const STATUS: Record<string, string> = { running: 'gerando…', pending: 'gerando…', failed: 'falhou' }

const fmt = (iso: string) =>
  new Date(iso).toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })

/** Histórico: todos os assuntos que já tiveram roteiro, para abrir direto sem procurar nas buscas. */
export function ScriptHistory({ onOpen, onClose }: Props) {
  const [items, setItems] = useState<ScriptEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [query, setQuery] = useState('')

  useEffect(() => {
    api
      .listScripts()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : 'Falha ao carregar'))
  }, [])

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!items) return []
    return q ? items.filter((i) => `${i.news_title} ${i.script_title ?? ''} ${i.topic}`.toLowerCase().includes(q)) : items
  }, [items, query])

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Roteiros criados" onClick={onClose}>
      <div className="modal render-modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>Roteiros criados {items ? `(${items.length})` : ''}</h2>
          <button className="secondary" onClick={onClose}>
            Fechar
          </button>
        </header>
        <label className="field">
          Filtrar por assunto
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ex.: Quest, Black Friday…" autoFocus />
        </label>
        {error && <p className="error">{error}</p>}
        {!items && !error && (
          <p className="loading">
            <span className="spinner" /> Carregando…
          </p>
        )}
        {items && shown.length === 0 && <p className="muted">{items.length ? 'Nenhum roteiro com esse filtro.' : 'Nenhum roteiro criado ainda.'}</p>}
        <ul className="history-list">
          {shown.map((e) => (
            <li key={e.script_id}>
              <button className="history-item" onClick={() => onOpen(e)}>
                <strong>{e.news_title}</strong>
                <span className="muted">{e.script_title ?? 'Sem título'}</span>
                <span className="history-meta">
                  <span>{fmt(e.created_at)}</span>
                  <span>{e.paragraphs} parágrafos</span>
                  {STATUS[e.status] && <span className="badge badge-error">{STATUS[e.status]}</span>}
                  {e.profile_name && <span>{e.profile_name}</span>}
                  {e.duration_minutes && <span>{e.duration_minutes} min</span>}
                  {e.presenters.length === 2 && <span>{e.presenters.join(' e ')}</span>}
                  {e.videos_done > 0 && <span className="badge badge-ok">vídeo pronto</span>}
                  {e.publication_status && <span className="badge">{PUBLICATION[e.publication_status] ?? e.publication_status}</span>}
                </span>
                <small className="muted">Busca: {e.topic}</small>
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
