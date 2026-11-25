import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Render, RenderAsset, RenderPreview, VignetteKind } from '../../api/types'
import { usePolling } from '../../hooks/usePolling'
import { VignettePicker, formatSeconds } from './VignettePicker'
import { VolumeSlider } from './VolumeSlider'

interface Props {
  scriptId: string
  onClose: () => void
}

const active = (r: Render) => r.status === 'pending' || r.status === 'running'
export const videoUrl = (id: string, download = false) => `/api/renders/${id}/video${download ? '?download=true' : ''}`

const remembered = (kind: VignetteKind): string | null => {
  try {
    return localStorage.getItem(`vignette:${kind}`)
  } catch {
    return null
  }
}
const remember = (kind: VignetteKind, id: string | null) => {
  try {
    if (id) localStorage.setItem(`vignette:${kind}`, id)
    else localStorage.removeItem(`vignette:${kind}`)
  } catch {
    /* sem armazenamento: só não lembra */
  }
}

function Status({ render }: { render: Render }) {
  if (render.status === 'failed') return <p className="error">Falhou: {render.error}</p>
  if (render.status === 'done')
    return (
      <div className="render-done">
        <p className="clip-ok">✔ Vídeo pronto: {render.video_name}</p>
        <video controls preload="metadata" src={videoUrl(render.id)} />
        <a className="download" href={videoUrl(render.id, true)}>
          Baixar MP4
        </a>
      </div>
    )
  return (
    <p className="loading" role="status">
      <span className="spinner" />
      {render.stage === 'composing'
        ? 'Montando o vídeo final: abertura → vídeo com a fala → final (ffmpeg)…'
        : render.queued
        ? 'Na fila do ComfyUI…'
        : 'Renderizando no ComfyUI (narração, alinhamento por frase, B-rolls e montagem). Pode levar vários minutos.'}
    </p>
  )
}

export function RenderDialog({ scriptId, onClose }: Props) {
  const [preview, setPreview] = useState<RenderPreview | null>(null)
  const [background, setBackground] = useState('')
  const [renderId, setRenderId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [intro, setIntro] = useState<RenderAsset | null>(null)
  const [outro, setOutro] = useState<RenderAsset | null>(null)
  const [introId, setIntroId] = useState<string | null>(() => remembered('intro'))
  const [outroId, setOutroId] = useState<string | null>(() => remembered('outro'))
  const [backgroundId, setBackgroundId] = useState<string | null>(() => remembered('background'))
  const [musicId, setMusicId] = useState<string | null>(() => remembered('music'))
  const [volume, setVolume] = useState<number | null>(null) // null = padrão do workflow (vem da prévia)
  const [musicIntro, setMusicIntro] = useState<number | null>(null) // null = igual ao da fala
  const [musicOutro, setMusicOutro] = useState<number | null>(null)
  const [introVolume, setIntroVolume] = useState(1)
  const [outroVolume, setOutroVolume] = useState(1)
  const [backgroundVolume, setBackgroundVolume] = useState(0) // 0 = sem o áudio do vídeo de background
  const [normalize, setNormalize] = useState(true)
  const [remixing, setRemixing] = useState(false)

  const render = usePolling(renderId, () => api.getRender(renderId!), active, 4000)

  useEffect(() => {
    let cancelled = false
    Promise.all([api.renderPreview(scriptId), api.listRenders(scriptId)])
      .then(([p, renders]) => {
        if (cancelled) return
        setPreview(p)
        setBackground(p.background)
        if (renders[0]) {
          setRenderId(renders[0].id) // mostra o último envio (e segue acompanhando se ainda roda)
          setIntroVolume(renders[0].intro_volume)
          setMusicIntro(renders[0].music_intro_volume)
          setMusicOutro(renders[0].music_outro_volume)
          setOutroVolume(renders[0].outro_volume)
          setBackgroundVolume(renders[0].background_volume)
          setNormalize(renders[0].normalize_vignettes)
        }
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Falha ao carregar'))
    return () => {
      cancelled = true
    }
  }, [scriptId])

  const send = async () => {
    setSending(true)
    setError(null)
    try {
      const created = await api.startRender(scriptId, background.trim(), introId, outroId, musicId, musicId ? (volume ?? preview?.music_volume ?? null) : null, backgroundId, {
        introVolume,
        outroVolume,
        backgroundVolume,
        normalize,
        musicIntroVolume: musicIntro,
        musicOutroVolume: musicOutro,
      })
      setRenderId(created.id)
      render.setData(created)
      render.refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao enviar')
    } finally {
      setSending(false)
    }
  }

  const running = !!render.data && active(render.data)

  // Remixar: refaz só a montagem final com as vinhetas/volumes de agora, sem rodar o ComfyUI de novo.
  const remixMusic = render.data?.music_baked ? null : musicId
  const canRemix = !!render.data?.can_remix && !!(introId || outroId || remixMusic || render.data?.music_baked)
  const remix = async () => {
    if (!render.data) return
    setRemixing(true)
    setError(null)
    try {
      const created = await api.remixRender(render.data.id, {
        introAssetId: introId,
        outroAssetId: outroId,
        musicAssetId: remixMusic,
        musicVolume: volume ?? preview?.music_volume ?? null,
        musicIntroVolume: musicIntro,
        musicOutroVolume: musicOutro,
        introVolume,
        outroVolume,
        normalize,
      })
      setRenderId(created.id)
      render.setData(created)
      render.refresh()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao remixar')
    } finally {
      setRemixing(false)
    }
  }

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Enviar para o ComfyUI" onClick={onClose}>
      <div className="modal render-modal" onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>Gerar vídeo no ComfyUI</h2>
          <button className="secondary" onClick={onClose}>
            Fechar
          </button>
        </header>
        <p className="muted">
          Envia o roteiro e a lista de cortes ao workflow “videos do papotechcast”. Os vídeos do YouTube são baixados e recortados durante a
          execução. Voz e renderização seguem como estão no workflow.
        </p>

        {!preview && !error && (
          <p className="loading">
            <span className="spinner" /> Montando o envio…
          </p>
        )}
        {error && <pre className="error render-error">{error}</pre>}

        {preview && (
          <>
            <VignettePicker
              kind="background"
              selectedId={backgroundId}
              onSelect={(a) => {
                setBackgroundId(a?.id ?? null)
                remember('background', a?.id ?? null)
              }}
            />
            <VolumeSlider
              label="Volume do áudio do background"
              value={backgroundVolume}
              disabled={!preview.background_volume_supported}
              hint={
                preview.background_volume_supported
                  ? 'Som do próprio vídeo de background, em loop sob a fala. 0% = sem som. Mudar isto exige novo envio ao ComfyUI.'
                  : 'O workflow atual do ComfyUI não tem este controle.'
              }
              onChange={setBackgroundVolume}
            />
            <label className="field">
              Ou o caminho do vídeo já existente no servidor (input do ComfyUI)
              <input
                value={background}
                disabled={!!backgroundId}
                onChange={(e) => setBackground(e.target.value)}
                placeholder="papotechcast/Background2.mp4"
              />
            </label>
            <p className="muted">Roteiro: {preview.roteiro_chars.toLocaleString('pt-BR')} caracteres de narração.</p>

            <div className="vignettes">
              <VignettePicker
                kind="intro"
                selectedId={introId}
                volume={introVolume}
                onVolume={setIntroVolume}
                onSelect={(a) => {
                  setIntro(a)
                  setIntroId(a?.id ?? null)
                  remember('intro', a?.id ?? null)
                }}
              />
              <VignettePicker
                kind="outro"
                selectedId={outroId}
                volume={outroVolume}
                onVolume={setOutroVolume}
                onSelect={(a) => {
                  setOutro(a)
                  setOutroId(a?.id ?? null)
                  remember('outro', a?.id ?? null)
                }}
              />
            </div>
            <VignettePicker
              kind="music"
              selectedId={musicId}
              onSelect={(a) => {
                setMusicId(a?.id ?? null)
                remember('music', a?.id ?? null)
              }}
            />
            {musicId && (
              <fieldset className="vignette music-levels">
                <legend>Nível do áudio de fundo em cada etapa</legend>
                {introId && (
                  <VolumeSlider
                    label="Áudio de fundo na abertura"
                    value={musicIntro ?? volume ?? preview.music_volume}
                    max={1}
                    hint={musicIntro === null ? 'Igual ao da fala. Mexa para mudar só na abertura.' : undefined}
                    onChange={setMusicIntro}
                  />
                )}
                <VolumeSlider
                  label="Áudio de fundo na fala"
                  value={volume ?? preview.music_volume}
                  max={1}
                  onChange={setVolume}
                />
                {outroId && (
                  <VolumeSlider
                    label="Áudio de fundo no final"
                    value={musicOutro ?? volume ?? preview.music_volume}
                    max={1}
                    hint={musicOutro === null ? 'Igual ao da fala. Mexa para mudar só no final.' : undefined}
                    onChange={setMusicOutro}
                  />
                )}
                <small className="muted">
                  {introId || outroId
                    ? 'É uma única trilha do começo ao fim; o nível muda suavemente entre as etapas.'
                    : 'Sem vinhetas, a trilha toca só sob a fala.'}
                </small>
              </fieldset>
            )}
            {(introId || outroId) && (
              <label className="check">
                <input type="checkbox" checked={normalize} onChange={(e) => setNormalize(e.target.checked)} />
                Nivelar o volume das vinhetas com a fala (evita abertura muito mais alta)
              </label>
            )}
            <p className="muted" aria-label="Ordem do vídeo final">
              Ordem final: {introId ? `Abertura${intro ? ` (${formatSeconds(intro.duration)})` : ''} → ` : ''}vídeo com a fala
              {outroId ? ` → Final${outro ? ` (${formatSeconds(outro.duration)})` : ''}` : ''}
              {introId ? '. A fala começa só depois da abertura.' : '.'}
              {musicId ? (introId || outroId ? ' O áudio de fundo toca do início ao fim do vídeo.' : ' O áudio de fundo toca sob a fala.') : ''}
            </p>

            <h3 className="render-h">Lista de edição ({preview.lines.length})</h3>
            {preview.lines.length > 0 && (
              <pre className="edit-list" aria-label="Lista de edição">
                {preview.edit_list}
              </pre>
            )}
            {preview.problems.length > 0 && (
              <ul className="render-problems" role="alert">
                {preview.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            )}

            <div className="render-actions">
              <button onClick={() => void send()} disabled={!preview.can_send || sending || running || (!background.trim() && !backgroundId)}>
                {sending ? 'Enviando…' : running ? 'Em andamento…' : 'Enviar para o ComfyUI'}
              </button>
              {!preview.can_send && <span className="muted">Corrija os pontos acima para liberar o envio.</span>}
            </div>
          </>
        )}

        {render.data && (
          <section className="render-status" aria-label="Status da renderização">
            <h3 className="render-h">Última renderização</h3>
            <Status render={render.data} />
            {render.data.can_remix && (
              <div className="remix">
                <button className="secondary" onClick={() => void remix()} disabled={!canRemix || remixing || running}>
                  {remixing ? 'Remixando…' : 'Remixar com estes volumes e vinhetas'}
                </button>
                <small className="muted">
                  Refaz só a montagem final, em segundos, sem rodar o ComfyUI. O volume do background não muda aqui.
                  {render.data.music_baked ? ' Este vídeo já tem a trilha embutida; ela não pode ser trocada.' : ''}
                </small>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  )
}
