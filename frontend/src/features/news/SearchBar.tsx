import { useState, type FormEvent } from 'react'
import type { RadarSearchOptions } from '../../api/types'

interface Props {
  busy: boolean
  onSearch: (topic: string, options?: RadarSearchOptions) => void
}

export function SearchBar({ busy, onSearch }: Props) {
  const [topic, setTopic] = useState('')
  const [scope, setScope] = useState('VR/XR')
  const [hours, setHours] = useState(72)
  const [end, setEnd] = useState('')
  const radar = /radar/i.test(topic)

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const value = topic.trim()
    if (value && !busy) onSearch(value, radar ? { radar_scope: scope, window_hours: hours, ...(end ? { window_end: new Date(end + 'Z').toISOString() } : {}) } : undefined)
  }

  return (
    <form className="search-bar" onSubmit={submit} role="search">
      <input
        aria-label="Tema ou assunto"
        placeholder="Tema ou assunto (ex.: Meta Quest, Gemini, robôs humanoides)"
        value={topic}
        maxLength={200}
        onChange={(e) => setTopic(e.target.value)}
      />
      {radar && <details className="radar-settings"><summary>{scope} · {hours}h ⚙</summary><div>
        <label>Escopo<input aria-label="Escopo do Radar" value={scope} maxLength={100} required onChange={e => setScope(e.target.value)} /></label>
        <label>Janela<select aria-label="Janela do Radar" value={hours} onChange={e => setHours(Number(e.target.value))}><option value={24}>24 horas</option><option value={72}>72 horas</option><option value={168}>7 dias</option></select></label>
        <label>Fim da janela (UTC, opcional)<input aria-label="Fim da janela em UTC" type="datetime-local" value={end} onChange={e => setEnd(e.target.value)} /></label>
        <small>Vazio usa o momento da execução. Para comparar com o Telegram, use o mesmo escopo e fim de janela.</small>
      </div></details>}
      <button type="submit" disabled={busy || !topic.trim()}>
        {busy ? 'Tonton buscando…' : 'Buscar notícias'}
      </button>
    </form>
  )
}
