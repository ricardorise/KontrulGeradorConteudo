import { useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { RenderAsset, VignetteKind } from '../../api/types'
import { VolumeSlider } from './VolumeSlider'

const COPY: Record<VignetteKind, { title: string; hint: string }> = {
  intro: { title: 'Vinheta de abertura', hint: 'Toca inteira no início. A fala só começa depois dela.' },
  outro: { title: 'Vinheta final', hint: 'Entra logo depois do fim da fala.' },
  background: { title: 'Vídeo de background', hint: 'Fica em loop sob a fala quando não há B-roll. Arquivos grandes demoram para enviar.' },
  music: { title: 'Áudio de fundo', hint: 'Se repete até o fim. Com vinhetas, toca desde o início da abertura até o fim do vídeo (fade-out nos últimos 2 s); sem vinhetas, toca sob a fala.' },
}

export const formatSeconds = (s: number) => `${s.toFixed(1).replace('.', ',')} s`
export const ACCEPT: Record<VignetteKind, string> = { intro: 'video/*,.mkv', outro: 'video/*,.mkv', background: 'video/*,.mkv', music: 'audio/*,.m4a,.opus,.flac' }
const megabytes = (bytes: number) => `${(bytes / (1024 * 1024)).toFixed(1).replace('.', ',')} MB`

interface Props {
  kind: VignetteKind
  selectedId: string | null
  onSelect: (asset: RenderAsset | null) => void
  volume?: number // se informado, mostra o controle de volume quando há vídeo escolhido
  onVolume?: (value: number) => void
}

export function VignettePicker({ kind, selectedId, onSelect, volume, onVolume }: Props) {
  const [assets, setAssets] = useState<RenderAsset[]>([])
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const { title, hint } = COPY[kind]

  useEffect(() => {
    let cancelled = false
    api
      .listRenderAssets(kind)
      .then((list) => {
        if (cancelled) return
        setAssets(list)
        // a escolha lembrada só vale se o arquivo ainda existe
        if (selectedId && !list.some((a) => a.id === selectedId)) onSelect(null)
      })
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : 'Falha ao listar'))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind])

  const upload = async (file: File) => {
    setUploading(true)
    setError(null)
    try {
      const asset = await api.uploadRenderAsset(kind, file)
      setAssets((list) => [asset, ...list])
      onSelect(asset)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha no envio do vídeo')
    } finally {
      setUploading(false)
      if (input.current) input.current.value = ''
    }
  }

  const remove = async (asset: RenderAsset) => {
    await api.deleteRenderAsset(asset.id)
    setAssets((list) => list.filter((a) => a.id !== asset.id))
    if (asset.id === selectedId) onSelect(null)
  }

  const selected = assets.find((a) => a.id === selectedId) ?? null

  return (
    <fieldset className="vignette">
      <legend>{title}</legend>
      <p className="muted">{hint}</p>
      <div className="vignette-row">
        <select aria-label={title} value={selectedId ?? ''} onChange={(e) => onSelect(assets.find((a) => a.id === e.target.value) ?? null)}>
          <option value="">{kind === 'music' ? 'Sem áudio de fundo' : kind === 'background' ? 'Usar o caminho do servidor' : 'Sem vinheta'}</option>
          {assets.map((a) => (
            <option key={a.id} value={a.id}>
              {a.filename} · {formatSeconds(a.duration)}
              {a.width ? ` · ${a.width}×${a.height}` : ''}
            </option>
          ))}
        </select>
        <label className={`file-button${uploading ? ' disabled' : ''}`}>
          {uploading ? 'Enviando…' : kind === 'music' ? 'Enviar áudio' : 'Enviar vídeo'}
          <input
            ref={input}
            type="file"
            accept={ACCEPT[kind]}
            disabled={uploading}
            aria-label={`${kind === 'music' ? 'Enviar áudio de' : 'Enviar vídeo de'} ${title.toLowerCase()}`}
            onChange={(e) => e.target.files?.[0] && void upload(e.target.files[0])}
          />
        </label>
        {selected && (
          <button className="secondary" onClick={() => void remove(selected)} aria-label={`Apagar ${selected.filename}`}>
            Apagar
          </button>
        )}
      </div>
      {selected && (
        <p className="muted">
          {formatSeconds(selected.duration)} · {megabytes(selected.size_bytes)} · {kind === 'music' ? 'trilha' : kind === 'background' ? 'background' : selected.has_audio ? 'com áudio' : 'sem áudio (fica em silêncio)'}
        </p>
      )}
      {selected && volume !== undefined && onVolume && (
        <details className="own-audio">
          <summary>
            Som original da vinheta: {!selected.has_audio || selected.audio_silent ? 'sem som' : `${Math.round(volume * 100)}%`}
          </summary>
          <VolumeSlider
            label={`Volume ${kind === 'intro' ? 'da abertura' : 'do final'}`}
            value={volume}
            disabled={!selected.has_audio || selected.audio_silent}
            hint={
              !selected.has_audio
                ? 'Esta vinheta não tem áudio.'
                : selected.audio_silent
                  ? 'A faixa de áudio deste arquivo está muda (sem som), então o volume não muda nada.'
                  : undefined
            }
            onChange={onVolume}
          />
        </details>
      )}
      {error && <p className="error">{error}</p>}
    </fieldset>
  )
}
