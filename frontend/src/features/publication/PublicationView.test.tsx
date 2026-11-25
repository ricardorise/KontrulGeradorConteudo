import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { api } from '../../api/client'
import type { Publication } from '../../api/types'
import { PublicationView, parseTags } from './PublicationView'

vi.mock('../../api/client', () => ({
  api: {
    getPublication: vi.fn(), editPublication: vi.fn(), revisePublication: vi.fn(),
    regeneratePublication: vi.fn(), publishPublication: vi.fn(),
  },
}))

const pub = (over: Partial<Publication> = {}): Publication => ({
  id: 'p1', render_id: 'r1', script_id: 's1', status: 'ready', title: 'Steam Frame no top 5', title_alternatives: ['Outro título'],
  description: 'Resumo do vídeo.', tags: ['vr', 'steam'], links: [
    { label: 'UploadVR', url: 'https://uploadvr.com/a', kind: 'source' },
    { label: 'Review no YouTube', url: 'https://www.youtube.com/watch?v=abcdefghijk', kind: 'broll' },
  ],
  full_description: 'Resumo do vídeo.\n\nFontes:\nhttps://uploadvr.com/a', description_chars: 40, privacy: 'private',
  allowed_privacies: ['private', 'unlisted'], notify_subscribers: false, rationale: 'Fiel ao conteúdo', error: null,
  error_stage: null, problems: [], can_publish: true, video_id: null, video_url: null,
  limits: { title: 100, description: 5000 }, updated_at: '', published_at: null, ...over,
})

beforeEach(() => vi.resetAllMocks())

test('mostra o resumo completo: título, descrição, tags, links e texto final', async () => {
  vi.mocked(api.getPublication).mockResolvedValue(pub())
  render(<PublicationView publicationId="p1" onClose={() => {}} />)
  expect(await screen.findByDisplayValue('Steam Frame no top 5')).toBeInTheDocument()
  expect(screen.getByDisplayValue('Resumo do vídeo.')).toBeInTheDocument()
  expect(screen.getByLabelText('Tags')).toHaveTextContent('steam')
  expect(screen.getByText('UploadVR')).toHaveAttribute('href', 'https://uploadvr.com/a')
  expect(screen.getByText('Review no YouTube')).toBeInTheDocument()
  expect(screen.getByLabelText('Descrição final')).toHaveTextContent('Fontes:')
  expect(screen.getByText(/Fiel ao conteúdo/)).toBeInTheDocument()
})

test('edições manuais ficam pendentes e são salvas', async () => {
  vi.mocked(api.getPublication).mockResolvedValue(pub())
  vi.mocked(api.editPublication).mockResolvedValue(pub({ title: 'Novo' }))
  render(<PublicationView publicationId="p1" onClose={() => {}} />)
  fireEvent.change(await screen.findByDisplayValue('Steam Frame no top 5'), { target: { value: 'Novo' } })
  expect(screen.getByRole('button', { name: 'Publicar no YouTube' })).toBeDisabled() // não publica com edição sem salvar
  fireEvent.click(screen.getByRole('button', { name: 'Salvar edições' }))
  await waitFor(() => expect(api.editPublication).toHaveBeenCalledWith('p1', { title: 'Novo', description: 'Resumo do vídeo.', tags: ['vr', 'steam'] }))
})

test('pedido de alteração vai ao especialista certo', async () => {
  vi.mocked(api.getPublication).mockResolvedValue(pub())
  vi.mocked(api.revisePublication).mockResolvedValue(pub({ status: 'drafting' }))
  render(<PublicationView publicationId="p1" onClose={() => {}} />)
  await screen.findByDisplayValue('Steam Frame no top 5')
  fireEvent.change(screen.getByLabelText('O que alterar'), { target: { value: 'title' } })
  fireEvent.change(screen.getByLabelText('Instruções'), { target: { value: 'mais curto' } })
  fireEvent.click(screen.getByRole('button', { name: 'Revisar' }))
  await waitFor(() => expect(api.revisePublication).toHaveBeenCalledWith('p1', 'title', 'mais curto'))
})

test('publicar exige confirmação e só então chama a API', async () => {
  vi.mocked(api.getPublication).mockResolvedValue(pub())
  vi.mocked(api.publishPublication).mockResolvedValue(pub({ status: 'publishing' }))
  render(<PublicationView publicationId="p1" onClose={() => {}} />)
  fireEvent.click(await screen.findByRole('button', { name: 'Publicar no YouTube' }))
  expect(api.publishPublication).not.toHaveBeenCalled()
  expect(screen.getByRole('dialog', { name: 'Confirmar publicação' })).toHaveTextContent('Privado')
  fireEvent.click(screen.getByRole('button', { name: 'Confirmar e publicar' }))
  await waitFor(() => expect(api.publishPublication).toHaveBeenCalledWith('p1'))
})

test('com problemas o botão Publicar fica bloqueado e os motivos aparecem', async () => {
  vi.mocked(api.getPublication).mockResolvedValue(pub({ can_publish: false, problems: ['Título vazio'] }))
  render(<PublicationView publicationId="p1" onClose={() => {}} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Título vazio')
  expect(screen.getByRole('button', { name: 'Publicar no YouTube' })).toBeDisabled()
})

test('publicado mostra o link do vídeo; falha de publicação aparece com o motivo', async () => {
  vi.mocked(api.getPublication).mockResolvedValue(pub({ status: 'published', video_url: 'https://youtu.be/abcdefghijk' }))
  const { unmount } = render(<PublicationView publicationId="p1" onClose={() => {}} />)
  expect(await screen.findByText('https://youtu.be/abcdefghijk')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'Publicar no YouTube' })).toBeNull()
  unmount()
  vi.mocked(api.getPublication).mockResolvedValue(pub({ error: 'quota', error_stage: 'publish' }))
  render(<PublicationView publicationId="p1" onClose={() => {}} />)
  expect(await screen.findByText(/Não publicou: quota/)).toBeInTheDocument()
})

test('parseTags normaliza como o servidor', () => {
  expect(parseTags('#VR, vr, Steam,\n  , quest')).toEqual(['VR', 'Steam', 'quest'])
})
