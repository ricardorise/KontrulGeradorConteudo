import { fireEvent, render, screen } from '@testing-library/react'
import { api } from '../../api/client'
import type { ScriptEntry } from '../../api/types'
import { ScriptHistory } from './ScriptHistory'

vi.mock('../../api/client', () => ({ api: { listScripts: vi.fn() } }))

const entry = (over: Partial<ScriptEntry> = {}): ScriptEntry => ({
  script_id: 's1', news_item_id: 'n1', search_id: 'q1', news_title: 'Quest 3S em promoção', topic: 'Radar VR', script_title: 'Quest em oferta',
  status: 'done', created_at: '2026-11-26T14:00:00Z', paragraphs: 8, profile_name: null, duration_minutes: null, presenters: [],
  videos_done: 0, publication_status: null, ...over,
})

test('lista os assuntos com roteiro, filtra e abre o escolhido', async () => {
  vi.mocked(api.listScripts).mockResolvedValue([
    entry(),
    entry({ script_id: 's2', news_item_id: 'n2', search_id: 'q2', news_title: 'Sunstone of Time', script_title: 'Jogo de VR', profile_name: 'Tech & Analítico', duration_minutes: 5, presenters: ['Ana', 'Beto'], videos_done: 1, publication_status: 'published' }),
  ])
  const onOpen = vi.fn()
  render(<ScriptHistory onOpen={onOpen} onClose={() => {}} />)
  expect(await screen.findByText('Quest 3S em promoção')).toBeInTheDocument()
  expect(screen.getByText('Roteiros criados (2)')).toBeInTheDocument()
  expect(screen.getByText('publicado no YouTube')).toBeInTheDocument()
  expect(screen.getByText('Ana e Beto')).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Filtrar por assunto'), { target: { value: 'sunstone' } })
  expect(screen.queryByText('Quest 3S em promoção')).toBeNull()
  fireEvent.click(screen.getByText('Sunstone of Time'))
  expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ script_id: 's2', search_id: 'q2', news_item_id: 'n2' }))
})

test('sem roteiros mostra aviso', async () => {
  vi.mocked(api.listScripts).mockResolvedValue([])
  render(<ScriptHistory onOpen={() => {}} onClose={() => {}} />)
  expect(await screen.findByText('Nenhum roteiro criado ainda.')).toBeInTheDocument()
})
