import { useEffect, useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import type { Guideline, GuidelineScope } from '../../api/types'

const SCOPES: { id: GuidelineScope; label: string }[] = [
  { id: 'all', label: 'Tudo' },
  { id: 'news', label: 'Busca de notícias (Tonton)' },
  { id: 'script', label: 'Roteiro (Jules Verne)' },
  { id: 'broll', label: 'B-roll (Lumière)' },
]
const scopeLabel = (s: GuidelineScope) => SCOPES.find((x) => x.id === s)?.label ?? s

interface Props {
  refreshKey: number
  onClose: () => void
}

export function GuidelinesPanel({ refreshKey, onClose }: Props) {
  const [items, setItems] = useState<Guideline[]>([])
  const [scope, setScope] = useState<GuidelineScope>('all')
  const [text, setText] = useState('')
  const [error, setError] = useState<string | null>(null)

  const load = () =>
    api
      .listGuidelines()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : 'Falha ao carregar'))

  useEffect(() => {
    void load()
  }, [refreshKey])

  const add = async (e: FormEvent) => {
    e.preventDefault()
    if (!text.trim()) return
    try {
      await api.addGuideline(scope, text.trim())
      setText('')
      setError(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Falha ao salvar')
    }
  }

  const toggle = async (g: Guideline) => {
    await api.setGuidelineActive(g.id, !g.active)
    await load()
  }
  const remove = async (g: Guideline) => {
    await api.deleteGuideline(g.id)
    await load()
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Orientações" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>Orientações aprendidas</h2>
          <button className="secondary" onClick={onClose}>
            Fechar
          </button>
        </header>
        <p className="muted">
          São aplicadas automaticamente nos próximos pedidos aos bots. Você pode criá-las aqui ou pedir no chat (ex.: “a partir de
          agora, roteiros mais informais”).
        </p>
        <form className="guideline-form" onSubmit={add}>
          <select aria-label="Escopo" value={scope} onChange={(e) => setScope(e.target.value as GuidelineScope)}>
            {SCOPES.map((s) => (
              <option key={s.id} value={s.id}>
                {s.label}
              </option>
            ))}
          </select>
          <input aria-label="Nova orientação" placeholder="Ex.: Prefira fontes oficiais" maxLength={300} value={text} onChange={(e) => setText(e.target.value)} />
          <button type="submit" disabled={!text.trim()}>
            Adicionar
          </button>
        </form>
        {error && <p className="error">{error}</p>}
        <ul className="guideline-list">
          {items.length === 0 && <li className="empty">Nenhuma orientação ainda.</li>}
          {items.map((g) => (
            <li key={g.id} className={g.active ? '' : 'inactive'}>
              <label>
                <input type="checkbox" checked={g.active} onChange={() => void toggle(g)} aria-label={`Ativar: ${g.text}`} />
                <span>
                  {g.text}
                  <small>
                    {scopeLabel(g.scope)} · {g.source === 'chat' ? 'aprendida no chat' : 'manual'}
                  </small>
                </span>
              </label>
              <button className="secondary" onClick={() => void remove(g)} aria-label={`Apagar: ${g.text}`}>
                Apagar
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
