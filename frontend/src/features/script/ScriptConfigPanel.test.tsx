import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { api } from '../../api/client'
import type { ScriptOptions } from '../../api/types'
import { ScriptConfigPanel } from './ScriptConfigPanel'

vi.mock('../../api/client', () => ({
  api: { scriptOptions: vi.fn(), addScriptProfile: vi.fn(), deleteScriptProfile: vi.fn() },
}))

const options = (extra: ScriptOptions['profiles'] = []): ScriptOptions => ({
  profiles: [
    { id: 'jornalistico', name: 'Jornalístico & Investigativo', description: 'Factual', instructions: 'Tom sério e factual.', builtin: true },
    { id: 'tech', name: 'Tech & Analítico', description: 'Técnico', instructions: 'Explique tecnicamente.', builtin: true },
    ...extra,
  ],
  durations: [
    { minutes: 5, max_chars: 630 }, { minutes: 8, max_chars: 800 }, { minutes: 12, max_chars: 1200 }, { minutes: 20, max_chars: 2000 },
  ],
})

beforeEach(() => {
  vi.resetAllMocks()
  localStorage.clear()
  vi.mocked(api.scriptOptions).mockResolvedValue(options())
})

test('só libera "Gerar roteiro" com perfil e tempo escolhidos e envia a configuração', async () => {
  const onGenerate = vi.fn()
  render(<ScriptConfigPanel onGenerate={onGenerate} />)
  const generate = await screen.findByRole('button', { name: 'Gerar roteiro' })
  expect(generate).toBeDisabled()
  expect(screen.getByText('até 630 caracteres')).toBeInTheDocument()
  expect(screen.getByText('até 2.000 caracteres')).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText(/Tech & Analítico/))
  expect(screen.getByText('Explique tecnicamente.')).toBeInTheDocument()
  expect(generate).toBeDisabled() // falta o tempo
  fireEvent.click(screen.getByLabelText(/Vídeo de 12 minutos/))
  expect(generate).toBeEnabled()
  fireEvent.click(generate)
  expect(onGenerate).toHaveBeenCalledWith({ profile_id: 'tech', duration_minutes: 12, presenters: [], theme: null })
})

test('dois apresentadores exigem dois nomes diferentes e vão na ordem digitada', async () => {
  const onGenerate = vi.fn()
  render(<ScriptConfigPanel onGenerate={onGenerate} />)
  await screen.findByRole('button', { name: 'Gerar roteiro' })
  fireEvent.click(screen.getByLabelText(/Jornalístico/))
  fireEvent.click(screen.getByLabelText(/Vídeo de 5 minutos/))
  fireEvent.click(screen.getByLabelText(/Dois apresentadores/))
  const generate = screen.getByRole('button', { name: 'Gerar roteiro' })
  expect(generate).toBeDisabled()
  fireEvent.change(screen.getByLabelText('Nome do apresentador 1'), { target: { value: 'Ana' } })
  fireEvent.change(screen.getByLabelText('Nome do apresentador 2'), { target: { value: 'ana' } })
  expect(generate).toBeDisabled() // iguais
  fireEvent.change(screen.getByLabelText('Nome do apresentador 2'), { target: { value: 'Beto' } })
  fireEvent.click(generate)
  expect(onGenerate).toHaveBeenCalledWith({ profile_id: 'jornalistico', duration_minutes: 5, presenters: ['Ana', 'Beto'], theme: null })
})

test('um apresentador: nome opcional', async () => {
  const onGenerate = vi.fn()
  render(<ScriptConfigPanel onGenerate={onGenerate} />)
  await screen.findByRole('button', { name: 'Gerar roteiro' })
  fireEvent.click(screen.getByLabelText(/Jornalístico/))
  fireEvent.click(screen.getByLabelText(/Vídeo de 8 minutos/))
  fireEvent.change(screen.getByLabelText(/Nome do apresentador \(opcional\)/), { target: { value: ' Ricardo ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gerar roteiro' }))
  expect(onGenerate).toHaveBeenCalledWith({ profile_id: 'jornalistico', duration_minutes: 8, presenters: ['Ricardo'], theme: null })
})

test('lembra a última escolha na próxima vez', async () => {
  const first = render(<ScriptConfigPanel onGenerate={() => {}} />)
  await screen.findByRole('button', { name: 'Gerar roteiro' })
  fireEvent.click(screen.getByLabelText(/Tech & Analítico/))
  fireEvent.click(screen.getByLabelText(/Vídeo de 20 minutos/))
  fireEvent.click(screen.getByRole('button', { name: 'Gerar roteiro' }))
  first.unmount()
  render(<ScriptConfigPanel onGenerate={() => {}} />)
  expect(await screen.findByRole('button', { name: 'Gerar roteiro' })).toBeEnabled()
})

test('cadastra um perfil novo e já o seleciona; só perfis próprios podem ser apagados', async () => {
  const mine = { id: 'u1', name: 'Humor ácido', description: '', instructions: 'Tom bem-humorado e sarcástico.', builtin: false }
  vi.mocked(api.addScriptProfile).mockResolvedValue(mine)
  render(<ScriptConfigPanel onGenerate={() => {}} />)
  await screen.findByRole('button', { name: 'Gerar roteiro' })
  expect(screen.queryByRole('button', { name: /Apagar perfil/ })).toBeNull()
  fireEvent.click(screen.getByRole('button', { name: '+ Cadastrar novo perfil' }))
  fireEvent.change(screen.getByLabelText('Nome do perfil'), { target: { value: 'Humor ácido' } })
  const save = screen.getByRole('button', { name: 'Salvar perfil' })
  expect(save).toBeDisabled() // falta a descrição do estilo
  fireEvent.change(screen.getByLabelText(/Como o roteirista deve escrever/), { target: { value: 'Tom bem-humorado e sarcástico.' } })
  vi.mocked(api.scriptOptions).mockResolvedValue(options([mine]))
  fireEvent.click(save)
  await waitFor(() => expect(api.addScriptProfile).toHaveBeenCalledWith('Humor ácido', 'Tom bem-humorado e sarcástico.', ''))
  expect(await screen.findByRole('button', { name: 'Apagar perfil Humor ácido' })).toBeInTheDocument()
  expect(screen.getByRole('radio', { name: /Humor ácido/ })).toBeChecked()
  vi.mocked(api.deleteScriptProfile).mockResolvedValue()
  vi.mocked(api.scriptOptions).mockResolvedValue(options())
  fireEvent.click(screen.getByRole('button', { name: 'Apagar perfil Humor ácido' }))
  await waitFor(() => expect(api.deleteScriptProfile).toHaveBeenCalledWith('u1'))
})

test('assunto/tema opcional vai na configuração e o roteiro agregado lista as notícias', async () => {
  const onGenerate = vi.fn()
  render(<ScriptConfigPanel mergedTitles={['Quest 3S em promoção', 'Steam Frame vaza']} onGenerate={onGenerate} />)
  await screen.findByRole('button', { name: 'Gerar roteiro' })
  expect(screen.getByLabelText('Notícias agregadas')).toHaveTextContent('Roteiro agregado de 2 notícias')
  expect(screen.getByText('Steam Frame vaza')).toBeInTheDocument()
  fireEvent.click(screen.getByLabelText(/Tech & Analítico/))
  fireEvent.click(screen.getByLabelText(/Vídeo de 8 minutos/))
  fireEvent.change(screen.getByLabelText(/Assunto \/ tema do vídeo/), { target: { value: ' A corrida dos headsets ' } })
  fireEvent.click(screen.getByRole('button', { name: 'Gerar roteiro' }))
  expect(onGenerate).toHaveBeenCalledWith({ profile_id: 'tech', duration_minutes: 8, presenters: [], theme: 'A corrida dos headsets' })
})
