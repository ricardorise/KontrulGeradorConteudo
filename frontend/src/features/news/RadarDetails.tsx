import { useEffect, useRef, useState } from 'react'
import type { NewsItem } from '../../api/types'

const safeUrl = (url: string) => /^https?:\/\//i.test(url)

export function RadarDetails({ item }: { item: NewsItem }) {
  const [open, setOpen] = useState(false)
  const dialog = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    if (!dialog.current) return
    if (open) {
      if (dialog.current.showModal) dialog.current.showModal()
      else dialog.current.setAttribute('open', '')
    } else {
      dialog.current.close?.()
      dialog.current.removeAttribute('open')
    }
  }, [open])
  const radar = item.radar
  const fields = [
    ['Justificativa do ranking', radar?.ranking_reason], ['Validação da janela', radar?.temporal_note], ['Natureza', radar?.nature], ['Quando começou', radar?.started_at],
    ['Potencial para conteúdo', radar?.content_potential], ['Divergências e limitações', radar?.divergences],
  ].filter(([, value]) => value)
  const lists: [string, string[] | undefined][] = [
    ['Onde cresce', radar?.where_growing], ['Evidências', radar?.evidence], ['Possíveis pautas', radar?.angles],
  ]
  const sources = Array.from(new Set([item.source_url, ...(radar?.sources ?? [])].filter((v): v is string => !!v && safeUrl(v))))
  if (!item.details && !radar && !sources.length) return null
  return (
    <>
      <button className="radar-open" onClick={() => setOpen(true)} aria-haspopup="dialog">Ver análise, evidências e fontes</button>
      <dialog ref={dialog} className="modal radar-modal" aria-label={`Análise: ${item.title}`} onCancel={() => setOpen(false)} onClose={() => setOpen(false)}>
        {open && <><div className="modal-head"><h2>#{item.position + 1} · {item.title}</h2><button className="secondary" onClick={() => setOpen(false)} autoFocus>Fechar</button></div>
        <p className="radar-report-summary">{item.summary}</p>
        {radar?.status && <span className="badge">{radar.status}</span>}
        {radar?.velocity && <p><strong>Velocidade:</strong> {radar.velocity}</p>}
        {radar?.why_now && <p><strong>Por que chamou atenção:</strong> {radar.why_now}</p>}
      {item.details && <p className="radar-context">{item.details}</p>}
      <dl>{fields.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
      {lists.map(([label, values]) => values?.length ? <section key={label}><h4>{label}</h4><ul>{values.map((value, i) => <li key={i}>{value}</li>)}</ul></section> : null)}
      {!!sources.length && <section><h4>Fontes</h4><ul>{sources.map(url => <li key={url}><a href={url} target="_blank" rel="noreferrer noopener">{url}</a></li>)}</ul></section>}
        </>}
      </dialog>
    </>
  )
}
