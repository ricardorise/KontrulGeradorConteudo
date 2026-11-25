import { useState } from 'react'
import type { Broll } from '../../api/types'
import { ClipEditor } from './ClipEditor'
import { formatTimestamp, thumbnailUrl, watchUrl } from './youtube'

interface Props {
  broll: Broll
  excerptText: string | null // trecho do texto que será ligado ao próximo corte (opcional)
  onAddCut: (broll: Broll, start: number, end: number) => Promise<void>
}

export function BrollCard({ broll, excerptText, onAddCut }: Props) {
  const [playing, setPlaying] = useState(false)
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
      </div>
    </article>
  )
}
