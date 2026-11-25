import type { Cut, Paragraph } from '../../api/types'
import { cutRows, toCsv, toJson, toText } from './exportCuts'

const paragraphs = [
  { id: 'p1', position: 0, text: 'a', broll: [] },
  { id: 'p2', position: 1, text: 'b', broll: [] },
] as Paragraph[]
const cut = (id: string, paragraph_id: string, start: number, end: number, created_at: string, title: string | null = null, excerpt: Cut['excerpt'] = null): Cut => ({
  id, paragraph_id, video_id: 'dQw4w9WgXcQ', video_url: 'https://youtu.be/dQw4w9WgXcQ', video_title: title,
  start_seconds: start, end_seconds: end, duration: end - start, created_at, excerpt,
})

const cuts = [cut('c2', 'p2', 65, 72.5, '2026-01-02', 'Review "3S"', { id: 'e', start: 3, end: 12, text: ' Ou seja: ' }), cut('c1', 'p1', 5, 9, '2026-01-03')]

test('ordena pelo roteiro e numera', () => {
  const rows = cutRows(cuts, paragraphs)
  expect(rows.map((r) => [r.order, r.paragraph])).toEqual([[1, 1], [2, 2]])
})

test('texto, csv (com escape) e json trazem url e intervalo', () => {
  const rows = cutRows(cuts, paragraphs)
  expect(toText(rows)).toContain('2. [parágrafo 2] https://youtu.be/dQw4w9WgXcQ | 1:05.0 → 1:12.5 (7.5s) | Review "3S" | trecho 3-12: «Ou seja:»')
  const csv = toCsv(rows).split('\n')
  expect(csv[0]).toMatch(/^ordem,paragrafo,url,inicio_s,fim_s/)
  expect(csv[2]).toContain('"https://youtu.be/dQw4w9WgXcQ?t=65"')
  expect(csv[2]).toContain('"Review ""3S"""')
  expect(csv[0]).toMatch(/trecho_inicio,trecho_fim,trecho$/)
  expect(csv[2]).toMatch(/"3","12","Ou seja:"$/)
  expect(csv[1]).toMatch(/"","",""$/) // corte sem trecho
  expect(JSON.parse(toJson(rows))[1]).toMatchObject({ start: 65, end: 72.5, duration: 7.5 })
})
