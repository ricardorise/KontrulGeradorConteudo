import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { api } from '../../api/client'
import type { Script } from '../../api/types'
import { ScriptView } from './ScriptView'

vi.mock('../../api/client', () => ({
  api: { retryBroll: vi.fn(), addBroll: vi.fn(), replaceBroll: vi.fn(), removeBroll: vi.fn(), addCut: vi.fn(), deleteCut: vi.fn(), setCutExcerpt: vi.fn() },
}))

const scene = (id: string, source: 'lumiere' | 'manual' = 'lumiere') => ({
  id, video_url: `https://youtu.be/${id.padEnd(11, 'x')}`, video_id: id.padEnd(11, 'x'), start_seconds: null, title: `Vídeo ${id}`,
  description: `cena ${id}`, justification: null, source,
})
const script = (over: Partial<Script> = {}): Script => ({
  id: 's1', news_item_id: 'n1', title: 'Roteiro', status: 'done', error: null, broll_status: 'done', broll_error: null, instructions: null,
  created_at: '', cuts: [],
  paragraphs: [
    { id: 'p1', position: 0, text: 'Primeiro parágrafo.', broll: [scene('aaa')] },
    { id: 'p2', position: 1, text: 'Segundo parágrafo.', broll: [scene('bbb')] },
    { id: 'p3', position: 2, text: 'Terceiro parágrafo.', broll: [] },
  ],
  ...over,
})
const setup = (s = script()) => {
  const onChanged = vi.fn()
  const onCutsChanged = vi.fn()
  render(<ScriptView script={s} error={null} onChanged={onChanged} onCutsChanged={onCutsChanged} onRetryScript={() => {}} />)
  return { onChanged, onCutsChanged }
}

beforeEach(() => vi.resetAllMocks())

test('"Rebuscar todos" busca todos os parágrafos', async () => {
  vi.mocked(api.retryBroll).mockResolvedValue(script({ broll_status: 'running' }))
  const { onChanged } = setup()
  fireEvent.click(screen.getByRole('button', { name: 'Rebuscar todos' }))
  await waitFor(() => expect(api.retryBroll).toHaveBeenCalledWith('s1', undefined))
  expect(onChanged).toHaveBeenCalled()
})

test('escolher parágrafos: marca alguns e rebusca só esses', async () => {
  vi.mocked(api.retryBroll).mockResolvedValue(script({ broll_status: 'running' }))
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Escolher parágrafos para rebuscar' }))
  expect(screen.getByRole('button', { name: 'Rebuscar selecionados (0)' })).toBeDisabled()
  fireEvent.click(screen.getByLabelText('Rebuscar o parágrafo 1'))
  fireEvent.click(screen.getByLabelText('Rebuscar o parágrafo 3'))
  fireEvent.click(screen.getByRole('button', { name: 'Rebuscar selecionados (2)' }))
  await waitFor(() => expect(api.retryBroll).toHaveBeenCalledWith('s1', ['p1', 'p3']))
  expect(screen.queryByLabelText('Rebuscar o parágrafo 1')).not.toBeInTheDocument() // sai do modo de seleção
})

test('marcar todos e cancelar a seleção', () => {
  setup()
  fireEvent.click(screen.getByRole('button', { name: 'Escolher parágrafos para rebuscar' }))
  fireEvent.click(screen.getByRole('button', { name: 'Marcar todos' }))
  expect(screen.getByRole('button', { name: 'Rebuscar selecionados (3)' })).toBeEnabled()
  fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
  expect(screen.getByRole('button', { name: 'Rebuscar todos' })).toBeInTheDocument()
  expect(api.retryBroll).not.toHaveBeenCalled()
})

test('atalho por parágrafo rebusca só aquele', async () => {
  vi.mocked(api.retryBroll).mockResolvedValue(script({ broll_status: 'running' }))
  setup()
  fireEvent.click(screen.getAllByRole('button', { name: /↻ Rebuscar este/ })[1])
  await waitFor(() => expect(api.retryBroll).toHaveBeenCalledWith('s1', ['p2']))
})

test('com a busca em andamento os botões de rebuscar ficam desativados', () => {
  setup(script({ broll_status: 'running' }))
  expect(screen.getByRole('button', { name: 'Rebuscar todos' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Escolher parágrafos para rebuscar' })).toBeDisabled()
})

test('inserir um vídeo no parágrafo vazio chama a API e abre o novo vídeo para recortar', async () => {
  const updated = script()
  updated.paragraphs[2].broll = [scene('novo', 'manual')]
  vi.mocked(api.addBroll).mockResolvedValue(updated)
  const { onCutsChanged } = setup()
  fireEvent.click(screen.getAllByRole('button', { name: '+ Adicionar vídeo' })[2])
  fireEvent.change(screen.getByLabelText('Link do vídeo para este parágrafo'), { target: { value: 'https://youtu.be/novoxxxxxxx' } })
  fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
  await waitFor(() => expect(api.addBroll).toHaveBeenCalledWith('s1', 'p3', 'https://youtu.be/novoxxxxxxx'))
  expect(onCutsChanged).toHaveBeenCalledWith(updated) // atualiza sem fechar players
})

test('trocar e remover usam as rotas do vídeo', async () => {
  vi.mocked(api.replaceBroll).mockResolvedValue(script())
  vi.mocked(api.removeBroll).mockResolvedValue(script())
  const { onCutsChanged } = setup()
  fireEvent.click(screen.getAllByRole('button', { name: 'Trocar vídeo' })[0])
  fireEvent.change(screen.getByLabelText('Link do novo vídeo'), { target: { value: 'https://youtu.be/trocadoxxxx' } })
  fireEvent.click(screen.getByRole('button', { name: 'Trocar' }))
  await waitFor(() => expect(api.replaceBroll).toHaveBeenCalledWith('s1', 'aaa', 'https://youtu.be/trocadoxxxx'))
  fireEvent.click(screen.getAllByRole('button', { name: /Remover vídeo/ })[0])
  await waitFor(() => expect(api.removeBroll).toHaveBeenCalledWith('s1', 'aaa'))
  expect(onCutsChanged).toHaveBeenCalled()
})
