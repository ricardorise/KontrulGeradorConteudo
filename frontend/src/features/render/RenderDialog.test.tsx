import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { api } from '../../api/client'
import type { Render, RenderAsset, RenderPreview } from '../../api/types'
import { RenderDialog } from './RenderDialog'

vi.mock('../../api/client', () => ({
  api: {
    renderPreview: vi.fn(), listRenders: vi.fn(), startRender: vi.fn(), getRender: vi.fn(),
    listRenderAssets: vi.fn(), uploadRenderAsset: vi.fn(), deleteRenderAsset: vi.fn(), remixRender: vi.fn(),
  },
}))

const preview = (over: Partial<RenderPreview> = {}): RenderPreview => ({
  background: 'papotechcast/Background2.mp4', roteiro_chars: 1500, can_send: true, problems: [],
  music_volume: 0.08, background_volume_supported: true, edit_list: 'https://www.youtube.com/watch?v=abc#t=1,5 | frase:Abertura | 4',
  lines: [{ order: 1, paragraph: 1, text: 'x', phrase: 'Abertura' }], ...over,
})
const job = (over: Partial<Render> = {}): Render => ({
  id: 'r1', script_id: 's1', status: 'running', queued: false, prompt_id: 'p', background: 'b', edit_list: 'e', error: null,
  has_video: false, video_name: null, stage: 'comfyui', intro_asset_id: null, outro_asset_id: null,
  music_asset_id: null, music_volume: null, music_intro_volume: null, music_outro_volume: null, intro_volume: 1, outro_volume: 1, background_volume: 0, normalize_vignettes: true,
  can_remix: false, music_baked: false,
  created_at: '', finished_at: null, ...over,
})
const asset = (over: Partial<RenderAsset> = {}): RenderAsset => ({
  id: 'a1', kind: 'intro', filename: 'Intro.mp4', size_bytes: 23_000_000, duration: 6, width: 1920, height: 1080,
  has_audio: true, audio_silent: false, mean_volume_db: -20, available: true, created_at: '', ...over,
})

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(api.listRenderAssets).mockResolvedValue([])
  localStorage.clear()
})

test('mostra a lista de edição e envia com o background informado', async () => {
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.startRender).mockResolvedValue(job({ queued: true }))
  vi.mocked(api.getRender).mockResolvedValue(job({ queued: true }))
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)

  expect(await screen.findByLabelText('Lista de edição')).toHaveTextContent('frase:Abertura | 4')
  fireEvent.change(screen.getByLabelText(/caminho do vídeo já existente/), { target: { value: 'papotechcast/Outro.mp4' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar para o ComfyUI' }))
  await waitFor(() => expect(api.startRender).toHaveBeenCalledWith('s1', 'papotechcast/Outro.mp4', null, null, null, null, null, { introVolume: 1, outroVolume: 1, backgroundVolume: 0, normalize: true, musicIntroVolume: null, musicOutroVolume: null }))
  expect(await screen.findByText(/Na fila do ComfyUI/)).toBeInTheDocument()
})

test('com problemas, lista os motivos e bloqueia o envio', async () => {
  vi.mocked(api.renderPreview).mockResolvedValue(preview({ can_send: false, lines: [], edit_list: '', problems: ['Corte 1 não tem trecho do texto'] }))
  vi.mocked(api.listRenders).mockResolvedValue([])
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Corte 1 não tem trecho do texto')
  expect(screen.getByRole('button', { name: 'Enviar para o ComfyUI' })).toBeDisabled()
})

test('mostra o vídeo pronto com download do MP4', async () => {
  const done = job({ status: 'done', has_video: true, video_name: 'final.mp4' })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([done])
  vi.mocked(api.getRender).mockResolvedValue(done)
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  expect(await screen.findByText(/Vídeo pronto: final.mp4/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Baixar MP4' })).toHaveAttribute('href', '/api/renders/r1/video?download=true')
})

test('mostra falha da renderização', async () => {
  const failed = job({ status: 'failed', error: 'Erro no ComfyUI em nó 5' })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([failed])
  vi.mocked(api.getRender).mockResolvedValue(failed)
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  expect(await screen.findByText(/Erro no ComfyUI em nó 5/)).toBeInTheDocument()
})


test('envia a abertura e o final, escolhe os vídeos e manda os ids ao ComfyUI', async () => {
  const intro = asset()
  const outro = asset({ id: 'a2', kind: 'outro', filename: 'Saida.mp4', duration: 5, has_audio: false })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.listRenderAssets).mockImplementation(async (kind) => (kind === 'outro' ? [outro] : []))
  vi.mocked(api.uploadRenderAsset).mockResolvedValue(intro)
  vi.mocked(api.startRender).mockResolvedValue(job({ queued: true }))
  vi.mocked(api.getRender).mockResolvedValue(job({ queued: true }))
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)

  await screen.findByLabelText('Lista de edição')
  const file = new File(['x'], 'Intro.mp4', { type: 'video/mp4' })
  fireEvent.change(screen.getByLabelText('Enviar vídeo de vinheta de abertura'), { target: { files: [file] } })
  await waitFor(() => expect(api.uploadRenderAsset).toHaveBeenCalledWith('intro', file))
  fireEvent.change(await screen.findByLabelText('Vinheta final'), { target: { value: 'a2' } })

  expect(screen.getByLabelText('Ordem do vídeo final')).toHaveTextContent('Abertura (6,0 s) → vídeo com a fala → Final (5,0 s)')
  expect(screen.getByLabelText('Ordem do vídeo final')).toHaveTextContent('A fala começa só depois da abertura')
  fireEvent.click(screen.getByRole('button', { name: 'Enviar para o ComfyUI' }))
  await waitFor(() => expect(api.startRender).toHaveBeenCalledWith('s1', 'papotechcast/Background2.mp4', 'a1', 'a2', null, null, null, { introVolume: 1, outroVolume: 1, backgroundVolume: 0, normalize: true, musicIntroVolume: null, musicOutroVolume: null }))
  expect(localStorage.getItem('vignette:intro')).toBe('a1') // lembra a escolha para a próxima vez
})

test('mostra a etapa de montagem das vinhetas e erro de upload', async () => {
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([job({ stage: 'composing' })])
  vi.mocked(api.getRender).mockResolvedValue(job({ stage: 'composing' }))
  vi.mocked(api.uploadRenderAsset).mockRejectedValue(new Error('Formato não suportado (.exe).'))
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  expect(await screen.findByText(/Montando o vídeo final: abertura/)).toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('Enviar vídeo de vinheta final'), { target: { files: [new File(['x'], 'a.exe')] } })
  expect(await screen.findByText('Formato não suportado (.exe).')).toBeInTheDocument()
})

test('vinheta lembrada que não existe mais é descartada', async () => {
  localStorage.setItem('vignette:intro', 'apagada')
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  await screen.findByLabelText('Lista de edição')
  await waitFor(() => expect(localStorage.getItem('vignette:intro')).toBeNull())
})


test('áudio de fundo: envia o áudio, ajusta o volume e manda tudo ao ComfyUI', async () => {
  const song = asset({ id: 'm1', kind: 'music', filename: 'Calma.mp3', duration: 180, width: 0, height: 0 })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.listRenderAssets).mockImplementation(async (kind) => (kind === 'music' ? [] : []))
  vi.mocked(api.uploadRenderAsset).mockResolvedValue(song)
  vi.mocked(api.startRender).mockResolvedValue(job({ queued: true }))
  vi.mocked(api.getRender).mockResolvedValue(job({ queued: true }))
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  await screen.findByLabelText('Lista de edição')
  expect(screen.queryByLabelText('Áudio de fundo na fala')).not.toBeInTheDocument() // só aparece com áudio escolhido

  const file = new File(['x'], 'Calma.mp3', { type: 'audio/mpeg' })
  fireEvent.change(screen.getByLabelText('Enviar áudio de áudio de fundo'), { target: { files: [file] } })
  await waitFor(() => expect(api.uploadRenderAsset).toHaveBeenCalledWith('music', file))
  const slider = await screen.findByLabelText('Áudio de fundo na fala')
  expect(slider).toHaveValue('8') // padrão do workflow
  fireEvent.change(slider, { target: { value: '20' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar para o ComfyUI' }))
  await waitFor(() => expect(api.startRender).toHaveBeenCalledWith('s1', 'papotechcast/Background2.mp4', null, null, 'm1', 0.2, null, { introVolume: 1, outroVolume: 1, backgroundVolume: 0, normalize: true, musicIntroVolume: null, musicOutroVolume: null }))
})


test('background: envia o vídeo, o campo de caminho fica desativado e o id vai ao ComfyUI', async () => {
  const bg = asset({ id: 'b1', kind: 'background', filename: 'Fundo.mp4', duration: 600, size_bytes: 800_000_000 })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.uploadRenderAsset).mockResolvedValue(bg)
  vi.mocked(api.startRender).mockResolvedValue(job({ queued: true }))
  vi.mocked(api.getRender).mockResolvedValue(job({ queued: true }))
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  await screen.findByLabelText('Lista de edição')
  expect(screen.getByLabelText(/caminho do vídeo já existente/)).toBeEnabled()

  const file = new File(['x'], 'Fundo.mp4', { type: 'video/mp4' })
  fireEvent.change(screen.getByLabelText('Enviar vídeo de vídeo de background'), { target: { files: [file] } })
  await waitFor(() => expect(api.uploadRenderAsset).toHaveBeenCalledWith('background', file))
  await waitFor(() => expect(screen.getByLabelText(/caminho do vídeo já existente/)).toBeDisabled())
  fireEvent.click(screen.getByRole('button', { name: 'Enviar para o ComfyUI' }))
  await waitFor(() => expect(api.startRender).toHaveBeenCalledWith('s1', 'papotechcast/Background2.mp4', null, null, null, null, 'b1', { introVolume: 1, outroVolume: 1, backgroundVolume: 0, normalize: true, musicIntroVolume: null, musicOutroVolume: null }))
})

test('volumes da abertura, do final e do background e o nivelamento vão no envio', async () => {
  const intro = asset()
  const outro = asset({ id: 'a2', kind: 'outro', filename: 'Saida.mp4', duration: 5 })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.listRenderAssets).mockImplementation(async (kind) => (kind === 'intro' ? [intro] : kind === 'outro' ? [outro] : []))
  vi.mocked(api.startRender).mockResolvedValue(job({ queued: true }))
  vi.mocked(api.getRender).mockResolvedValue(job({ queued: true }))
  localStorage.setItem('vignette:intro', 'a1')
  localStorage.setItem('vignette:outro', 'a2')
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)

  fireEvent.change(await screen.findByLabelText('Volume da abertura'), { target: { value: '60' } })
  fireEvent.change(screen.getByLabelText('Volume do final'), { target: { value: '0' } })
  expect(screen.getAllByText('mudo')).toHaveLength(2) // final em 0% e o background, que começa mudo
  fireEvent.change(screen.getByLabelText('Volume do áudio do background'), { target: { value: '25' } })
  fireEvent.click(screen.getByLabelText(/Nivelar o volume das vinhetas/)) // desliga
  fireEvent.click(screen.getByRole('button', { name: 'Enviar para o ComfyUI' }))
  await waitFor(() =>
    expect(api.startRender).toHaveBeenCalledWith('s1', 'papotechcast/Background2.mp4', 'a1', 'a2', null, null, null, {
      introVolume: 0.6, outroVolume: 0, backgroundVolume: 0.25, normalize: false, musicIntroVolume: null, musicOutroVolume: null,
    }),
  )
})

test('workflow sem volume do background desativa o controle', async () => {
  vi.mocked(api.renderPreview).mockResolvedValue(preview({ background_volume_supported: false }))
  vi.mocked(api.listRenders).mockResolvedValue([])
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  expect(await screen.findByLabelText('Volume do áudio do background')).toBeDisabled()
  expect(screen.getByText(/não tem este controle/)).toBeInTheDocument()
})

test('remixar refaz só a montagem com os volumes de agora e acompanha o novo job', async () => {
  const intro = asset()
  const done = job({ status: 'done', has_video: true, video_name: 'final.mp4', can_remix: true, intro_volume: 0.5, outro_volume: 1.2, normalize_vignettes: false })
  const remixed = job({ id: 'r2', status: 'running', stage: 'composing' })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([done])
  vi.mocked(api.getRender).mockImplementation(async (id) => (id === 'r2' ? remixed : done))
  vi.mocked(api.listRenderAssets).mockImplementation(async (kind) => (kind === 'intro' ? [intro] : []))
  vi.mocked(api.remixRender).mockResolvedValue(remixed)
  localStorage.setItem('vignette:intro', 'a1')
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)

  expect(await screen.findByLabelText('Volume da abertura')).toHaveValue('50') // preenchido a partir do último envio
  const slider = screen.getByLabelText('Volume da abertura')
  fireEvent.change(slider, { target: { value: '80' } })
  fireEvent.click(await screen.findByRole('button', { name: 'Remixar com estes volumes e vinhetas' }))
  await waitFor(() =>
    expect(api.remixRender).toHaveBeenCalledWith('r1', {
      introAssetId: 'a1', outroAssetId: null, musicAssetId: null, musicVolume: 0.08, musicIntroVolume: null, musicOutroVolume: null, introVolume: 0.8, outroVolume: 1.2, normalize: false,
    }),
  )
  expect(await screen.findByText(/Montando o vídeo final/)).toBeInTheDocument()
  expect(api.startRender).not.toHaveBeenCalled() // não reenviou ao ComfyUI
})

test('sem vinheta nem trilha escolhida, remixar fica desativado', async () => {
  const done = job({ status: 'done', has_video: true, video_name: 'final.mp4', can_remix: true })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([done])
  vi.mocked(api.getRender).mockResolvedValue(done)
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  expect(await screen.findByRole('button', { name: 'Remixar com estes volumes e vinhetas' })).toBeDisabled()
})


test('vinheta com faixa de áudio muda avisa e desativa o volume', async () => {
  const mute = asset({ audio_silent: true, mean_volume_db: -91 })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.listRenderAssets).mockImplementation(async (kind) => (kind === 'intro' ? [mute] : []))
  localStorage.setItem('vignette:intro', 'a1')
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  expect(await screen.findByLabelText('Volume da abertura')).toBeDisabled()
  expect(screen.getByText(/está muda/)).toBeInTheDocument()
})


test('um áudio de fundo, três níveis: abertura, fala e final', async () => {
  const intro = asset()
  const outro = asset({ id: 'a2', kind: 'outro', filename: 'Saida.mp4', duration: 5, has_audio: false })
  const song = asset({ id: 'm1', kind: 'music', filename: 'Calma.mp3', duration: 180, width: 0, height: 0 })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.listRenderAssets).mockImplementation(async (kind) => (kind === 'intro' ? [intro] : kind === 'outro' ? [outro] : kind === 'music' ? [song] : []))
  vi.mocked(api.startRender).mockResolvedValue(job({ queued: true }))
  vi.mocked(api.getRender).mockResolvedValue(job({ queued: true }))
  for (const [k, v] of [['intro', 'a1'], ['outro', 'a2'], ['music', 'm1']]) localStorage.setItem(`vignette:${k}`, v)
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)

  const onIntro = await screen.findByLabelText('Áudio de fundo na abertura')
  expect(onIntro).toHaveValue('8') // sem mexer: igual ao da fala (8%)
  fireEvent.change(onIntro, { target: { value: '50' } })
  fireEvent.change(screen.getByLabelText('Áudio de fundo na fala'), { target: { value: '5' } })
  fireEvent.change(screen.getByLabelText('Áudio de fundo no final'), { target: { value: '30' } })
  fireEvent.click(screen.getByRole('button', { name: 'Enviar para o ComfyUI' }))
  await waitFor(() =>
    expect(api.startRender).toHaveBeenCalledWith('s1', 'papotechcast/Background2.mp4', 'a1', 'a2', 'm1', 0.05, null, {
      introVolume: 1, outroVolume: 1, backgroundVolume: 0, normalize: true, musicIntroVolume: 0.5, musicOutroVolume: 0.3,
    }),
  )
})

test('sem vinhetas só existe o nível da fala', async () => {
  const song = asset({ id: 'm1', kind: 'music', filename: 'Calma.mp3', duration: 180, width: 0, height: 0 })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.listRenderAssets).mockImplementation(async (kind) => (kind === 'music' ? [song] : []))
  localStorage.setItem('vignette:music', 'm1')
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  await screen.findByLabelText('Áudio de fundo na fala')
  expect(screen.queryByLabelText('Áudio de fundo na abertura')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('Áudio de fundo no final')).not.toBeInTheDocument()
})


test('mídia sem arquivo neste ambiente aparece desativada e a escolha lembrada é descartada', async () => {
  const gone = asset({ available: false })
  vi.mocked(api.renderPreview).mockResolvedValue(preview())
  vi.mocked(api.listRenders).mockResolvedValue([])
  vi.mocked(api.listRenderAssets).mockImplementation(async (kind) => (kind === 'intro' ? [gone] : []))
  localStorage.setItem('vignette:intro', 'a1')
  render(<RenderDialog scriptId="s1" onClose={() => {}} />)
  const option = await screen.findByRole('option', { name: /⚠.*Intro\.mp4/ })
  expect(option).toBeDisabled()
  expect(screen.getByText(/não têm o arquivo neste ambiente/)).toBeInTheDocument()
  await waitFor(() => expect(localStorage.getItem('vignette:intro')).toBeNull())
})
