import { useState } from 'react'
import type { Broll } from '../../api/types'
import { BrollUrlForm } from './BrollUrlForm'
import { ClipEditor } from './ClipEditor'
import { formatTimestamp, thumbnailUrl, watchUrl } from './youtube'

interface Props {
  broll: Broll
  excerptText: string | null // trecho do texto que será ligado ao próximo corte (opcional)
  onAddCut: (broll: Broll, start: number, end: number) => Promise<void>
  onReplace?: (brollId: string, url: string) => Promise<void> // troca o vídeo por um link que você escolhe
  onRemove?: (brollId: string) => void
  defaultOpen?: boolean // abre já no player de corte (ex.: vídeo recém-inserido)
}

export function BrollCard({ broll, excerptText, onAddCut, onReplace, onRemove, defaultOpen = false }: Props) {
  const [playing, setPlaying] = useState(defaultOpen)
  const [swapping, setSwapping] = useState(false)
  const stamp = formatTimestamp(broll.start_seconds)

  return (
    <article className={`broll-card${playing ? ' editing' : ''}`}>
      {playing ? (
        <ClipEditor
          videoId={broll.video_id}
          title={broll.title ?? broll.description}
          suggestedStart={broll.start_seconds}
          excerptText={excerptText}
          onAddCut={(start, end) => onAddCut(broll, start, end)}
        />
      ) : (
        <button className="thumb" onClick={() => setPlaying(true)} aria-label={`Abrir player e cortar: ${broll.description}`}>
          <img src={thumbnailUrl(broll.video_id)} alt="" loading="lazy" />
          <span className="play">▶</span>
          {stamp && <span className="stamp">{stamp}</span>}
        </button>
      )}
      <div className="broll-info">
        {broll.source === 'manual' && <span className="badge badge-manual">escolhido por você</span>}
        {broll.title && <strong>{broll.title}</strong>}
        <p>{broll.description}</p>
        {!stamp && <p className="why">Trecho não confirmado — o vídeo abre no início.</p>}
        {broll.justification && <p className="why">{broll.justification}</p>}
        {playing && (
          <button className="secondary" onClick={() => setPlaying(false)}>
            Fechar player
          </button>
        )}
        <a href={watchUrl(broll.video_id, broll.start_seconds)} target="_blank" rel="noreferrer noopener">
          Abrir no YouTube{stamp ? ` em ${stamp}` : ''} ↗
        </a>
        {(onReplace || onRemove) && !swapping && (
          <div className="broll-actions">
            {onReplace && (
              <button className="secondary small" onClick={() => setSwapping(true)}>
                Trocar vídeo
              </button>
            )}
            {onRemove && (
              <button className="secondary small" onClick={() => onRemove(broll.id)} aria-label={`Remover vídeo: ${broll.title ?? broll.description}`}>
                Remover
              </button>
            )}
          </div>
        )}
        {swapping && onReplace && (
          <BrollUrlForm
            label="Link do novo vídeo"
            submitLabel="Trocar"
            onSubmit={async (url) => {
              await onReplace(broll.id, url)
              setPlaying(true) // já abre para recortar o vídeo novo
            }}
            onCancel={() => setSwapping(false)}
          />
        )}
      </div>
    </article>
  )
}
