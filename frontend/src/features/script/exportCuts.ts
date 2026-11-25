import type { Cut, Paragraph } from '../../api/types'
import { formatClock } from './timeline'

export interface CutRow {
  order: number
  paragraph: number
  url: string
  start: number
  end: number
  duration: number
  title: string | null
  excerpt: { start: number; end: number; text: string } | null
}

/** Cortes na ordem do roteiro (parágrafo e depois ordem de criação). */
export function cutRows(cuts: Cut[], paragraphs: Paragraph[]): CutRow[] {
  const position = new Map(paragraphs.map((p) => [p.id, p.position + 1]))
  return [...cuts]
    .sort((a, b) => (position.get(a.paragraph_id) ?? 0) - (position.get(b.paragraph_id) ?? 0) || a.created_at.localeCompare(b.created_at))
    .map((c, i) => ({
      order: i + 1,
      paragraph: position.get(c.paragraph_id) ?? 0,
      url: c.video_url,
      start: c.start_seconds,
      end: c.end_seconds,
      duration: c.duration,
      title: c.video_title,
      excerpt: c.excerpt ? { start: c.excerpt.start, end: c.excerpt.end, text: c.excerpt.text.trim() } : null,
    }))
}

const withStart = (r: CutRow) => `${r.url}?t=${Math.floor(r.start)}`

export const toText = (rows: CutRow[]) =>
  rows
    .map(
      (r) =>
        `${r.order}. [parágrafo ${r.paragraph}] ${r.url} | ${formatClock(r.start)} → ${formatClock(r.end)} (${r.duration.toFixed(1)}s)` +
        (r.title ? ` | ${r.title}` : '') +
        (r.excerpt ? ` | trecho ${r.excerpt.start}-${r.excerpt.end}: «${r.excerpt.text}»` : ''),
    )
    .join('\n')

const csvCell = (value: string | number) => `"${String(value).replace(/"/g, '""')}"`

export const toCsv = (rows: CutRow[]) =>
  [
    'ordem,paragrafo,url,inicio_s,fim_s,duracao_s,inicio,fim,url_com_inicio,titulo,trecho_inicio,trecho_fim,trecho',
    ...rows.map((r) =>
      [r.order, r.paragraph, r.url, r.start, r.end, r.duration, formatClock(r.start), formatClock(r.end), withStart(r), r.title ?? '', r.excerpt?.start ?? '', r.excerpt?.end ?? '', r.excerpt?.text ?? '']
        .map(csvCell)
        .join(','),
    ),
  ].join('\n')

export const toJson = (rows: CutRow[]) => JSON.stringify(rows, null, 2)

export function download(filename: string, content: string, mime: string) {
  const url = URL.createObjectURL(new Blob([content], { type: `${mime};charset=utf-8` }))
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
