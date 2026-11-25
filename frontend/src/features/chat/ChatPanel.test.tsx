import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { api } from '../../api/client'
import type { Conversation } from '../../api/types'
import { ChatPanel } from './ChatPanel'

vi.mock('../../api/client', () => ({
  api: { listConversations: vi.fn(), getConversation: vi.fn(), openConversation: vi.fn(), sendMessage: vi.fn() },
}))

const done = (id: string, actions: Conversation['messages'][number]['actions']): Conversation => ({
  id: 'c1', bot: 'baru', title: 't', created_at: '', updated_at: '',
  messages: [{ id, role: 'assistant', content: 'Buscando!', status: 'done', error: null, created_at: '', actions }],
})

test('mostra chips das ações executadas e não reaplica ações de conversas antigas', async () => {
  const actions = [{ type: 'search_news', status: 'done' as const, label: 'Busca iniciada: IA', error: null, refs: { search_id: 's1' } }]
  vi.mocked(api.listConversations).mockResolvedValue([done('m1', actions)])
  vi.mocked(api.getConversation).mockResolvedValue(done('m1', actions))
  const onActions = vi.fn()
  render(<ChatPanel context={{ search_id: null, script_id: null }} onActions={onActions} />)

  await waitFor(() => expect(api.listConversations).toHaveBeenCalled())
  await screen.findByRole('option', { name: 't' })
  fireEvent.change(screen.getByLabelText('Conversas anteriores'), { target: { value: 'c1' } })
  expect(await screen.findByText('✔ Busca iniciada: IA')).toBeInTheDocument()
  expect(onActions).not.toHaveBeenCalled() // histórico não dispara ações na tela
})

test('aba Lumière permite conversar e enviar instruções com o roteiro aberto', async () => {
  vi.clearAllMocks()
  vi.mocked(api.listConversations).mockResolvedValue([])
  const conversation: Conversation = { id: 'l1', bot: 'lumiere', title: 'Instruções', created_at: '', updated_at: '', messages: [] }
  vi.mocked(api.openConversation).mockResolvedValue(conversation)
  vi.mocked(api.sendMessage).mockResolvedValue(conversation)
  vi.mocked(api.getConversation).mockResolvedValue(conversation)
  const context = { search_id: 's1', script_id: 'r1' }
  render(<ChatPanel context={context} onActions={vi.fn()} />)
  fireEvent.click(screen.getByRole('tab', { name: /Lumière/ }))
  await waitFor(() => expect(api.listConversations).toHaveBeenCalledWith('lumiere'))
  expect(screen.getByRole('tab', { name: /Lumière/ })).toHaveAttribute('aria-selected', 'true')
  fireEvent.change(screen.getByLabelText('Mensagem'), { target: { value: 'Refaça os B-rolls com horários confirmados' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
  await waitFor(() => expect(api.openConversation).toHaveBeenCalledWith('lumiere'))
  await waitFor(() => expect(api.sendMessage).toHaveBeenCalledWith('l1', 'Refaça os B-rolls com horários confirmados', context))
})

test('segunda mensagem na mesma conversa volta a consultar e mostra a resposta (regressão: ficava "respondendo…" para sempre)', async () => {
  const msg = (id: string, role: 'user' | 'assistant', content: string, status: 'done' | 'running') => ({
    id, role, content, status, error: null, created_at: '', actions: [],
  })
  const first = { ...done('m1', []), messages: [msg('m1', 'assistant', 'Primeira resposta', 'done')] }
  const pending = { ...first, messages: [...first.messages, msg('u2', 'user', 'e agora?', 'done'), msg('m2', 'assistant', '', 'running')] }
  const answered = { ...pending, messages: [...first.messages, msg('u2', 'user', 'e agora?', 'done'), msg('m2', 'assistant', 'Segunda resposta', 'done')] }
  vi.mocked(api.listConversations).mockResolvedValue([first])
  vi.mocked(api.getConversation).mockResolvedValueOnce(first).mockResolvedValue(answered)
  vi.mocked(api.sendMessage).mockResolvedValue(pending)

  render(<ChatPanel context={{ search_id: null, script_id: null }} onActions={() => {}} />)
  await screen.findByRole('option', { name: 't' })
  fireEvent.change(screen.getByLabelText('Conversas anteriores'), { target: { value: 'c1' } })
  await screen.findByText('Primeira resposta')

  fireEvent.change(screen.getByLabelText('Mensagem'), { target: { value: 'e agora?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar' }))
  expect(await screen.findByText('Segunda resposta', {}, { timeout: 4000 })).toBeInTheDocument()
})
