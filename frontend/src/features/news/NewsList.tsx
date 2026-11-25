import type { NewsSearch } from '../../api/types'
import { RadarDetails } from './RadarDetails'

const utc = (value?: string) => value ? new Date(value).toLocaleString('pt-BR', {timeZone:'UTC', dateStyle:'short', timeStyle:'short'}) : 'não informado'

interface Props {
  search: NewsSearch | null
  error: string | null
  selectedItemId: string | null
  onSelect: (itemId: string) => void
}

export function NewsList({ search, error, selectedItemId, onSelect }: Props) {
  if (!search) {
    return <p className="empty">Pesquise um tema para o Tonton buscar notícias.</p>
  }
  if (search.status === 'running' || search.status === 'pending') {
    return (
      <div className="loading" role="status">
        <span className="spinner" /> O Tonton está buscando notícias sobre <strong>{search.topic}</strong>…
        <small>{search.report_context?.stage || "O Radar cruza fontes em etapas e pode levar alguns minutos."}</small>
      </div>
    )
  }
  if (search.status === 'failed') {
    return <p className="error">Não foi possível buscar: {search.error}</p>
  }
  return (
    <>
      {error && <p className="error">{error}</p>}
      <h2 className="section-title">
        {search.items.length} assuntos · <em>{search.topic}</em>
      </h2>
      {search.report_context?.policy && <section className="radar-context-card" aria-label="Regras desta execução">
        <strong>RADAR DE TENDÊNCIAS — {search.report_context.scope}</strong>
        <p>Janela: {utc(search.report_context.window_start)} → {utc(search.report_context.window_end)} ({search.report_context.window_hours}h, UTC)</p>
        <details><summary>Fontes e regra do ranking</summary>
          <p>{search.report_context.ranking_rule}</p>
          <ul>{Object.entries(search.report_context.coverage ?? {}).map(([name, state]) => <li key={name}>{name}: {state}</li>)}</ul>
          <p>{search.report_context.coverage_note}</p><p>{search.report_context.temporal_validation}</p><p>Google Trends: {search.report_context.google_trends_note}</p>
          {!!search.report_context.discarded?.length && <><strong>Descartados</strong><ul>{search.report_context.discarded.map((text, i) => <li key={i}>{text}</li>)}</ul></>}
        </details>
      </section>}
      <ul className="news-list">
        {search.items.map((item) => (
          <li key={item.id}>
            <button
              className={`news-card${item.id === selectedItemId ? ' selected' : ''}`}
              onClick={() => onSelect(item.id)}
              aria-pressed={item.id === selectedItemId}
            >
              <span className="news-title"><span className="radar-rank">#{item.position + 1}</span> {item.title}</span>
              <span className="radar-badges">
                {item.radar?.status && <span className="badge">{item.radar.status}</span>}
                {item.radar?.category && <span className="badge">{item.radar.category}</span>}
                {item.radar?.velocity && <span className="badge">Velocidade: {item.radar.velocity.split(/[—;]/)[0].trim()}</span>}
              </span>
              <span className="news-summary">{item.summary}</span>
              {item.radar?.why_now && <span className="radar-why">{item.radar.why_now}</span>}
              <span className="news-meta">
                {item.published_at && <span>{item.published_at}</span>}
                <span className="cta">Gerar roteiro →</span>
              </span>
            </button>
            <RadarDetails item={item} />
          </li>
        ))}
      </ul>
    </>
  )
}
