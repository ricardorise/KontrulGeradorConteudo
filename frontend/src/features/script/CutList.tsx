import { useState } from 'react'
import type { Script } from '../../api/types'
import { RenderDialog } from '../render/RenderDialog'
import { cutRows, download, toCsv, toJson, toText } from './exportCuts'
import { formatClock } from './timeline'

interface Props {
  onPublication?: (publicationId: string) => void
  script: Script
  onDelete: (cutId: string) => void
}

export function CutList({ script, onDelete, onPublication }: Props) {
  const [copied, setCopied] = useState(false)
  const [rendering, setRendering] = useState(false)
  const rows = cutRows(script.cuts, script.paragraphs)
  const byId = new Map(script.cuts.map((c) => [c.video_url + c.start_seconds + c.end_seconds, c.id]))
  const base = (script.title ?? 'roteiro').toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40) || 'roteiro'

  const copy = async () => {
    await navigator.clipboard.writeText(toText(rows))
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  return (
    <section className="cut-list" aria-label="Lista de cortes">
      <header className="cut-list-head">
        <h3>Lista de cortes ({rows.length})</h3>
        <div className="script-actions">
          <button className="secondary" disabled={!rows.length} onClick={() => void copy()}>
            {copied ? 'Copiado ✔' : 'Copiar'}
          </button>
          <button className="secondary" disabled={!rows.length} onClick={() => download(`${base}-cortes.csv`, toCsv(rows), 'text/csv')}>
            Baixar CSV
          </button>
          <button className="secondary" disabled={!rows.length} onClick={() => download(`${base}-cortes.json`, toJson(rows), 'application/json')}>
            Baixar JSON
          </button>
        </div>
      </header>
      {rows.length === 0 ? (
        <p className="empty">Abra um vídeo do B-roll, selecione o intervalo na timeline e dê duplo clique para adicionar.</p>
      ) : (
        <ol className="cut-rows">
          {rows.map((r) => (
            <li key={r.order}>
              <span className="cut-para">§{r.paragraph}</span>
              <a href={`${r.url}?t=${Math.floor(r.start)}`} target="_blank" rel="noreferrer noopener">
                {r.url.replace('https://', '')}
              </a>
              <span className="cut-range">
                {formatClock(r.start)} → {formatClock(r.end)} <small>({r.duration.toFixed(1)}s)</small>
              </span>
              {r.title && <span className="cut-title">{r.title}</span>}
              {r.excerpt && <span className="cut-excerpt">“{r.excerpt.text}”</span>}
              <button
                className="secondary"
                aria-label={`Remover corte ${r.order}`}
                onClick={() => onDelete(byId.get(r.url + r.start + r.end)!)}
              >
                Remover
              </button>
            </li>
          ))}
        </ol>
      )}
      <footer className="cut-list-foot">
        <button disabled={!rows.length} onClick={() => setRendering(true)}>
          Enviar para o ComfyUI (gerar vídeo)
        </button>
        <span className="muted">Envia roteiro + cortes ao workflow “videos do papotechcast”.</span>
      </footer>
      {rendering && <RenderDialog scriptId={script.id} onClose={() => setRendering(false)} onPublication={onPublication} />}
    </section>
  )
}
