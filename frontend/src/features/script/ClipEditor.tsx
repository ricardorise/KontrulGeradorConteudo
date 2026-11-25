import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type MouseEvent, type PointerEvent } from 'react'
import {
  MIN_CUT_SECONDS,
  clamp,
  formatClock,
  initialSelection,
  round1,
  timeFromPointer,
  withEnd,
  withStart,
  type Selection,
} from './timeline'
import { loadYouTubeApi, type YTPlayer } from './youtubeApi'

interface Props {
  videoId: string
  title: string
  suggestedStart: number | null
  excerptText?: string | null
  onAddCut: (start: number, end: number) => Promise<void>
}

const STEP = 0.5

/** Player do YouTube + timeline: arraste o cursor, ajuste início/fim e dê duplo clique na seleção para cortar. */
export function ClipEditor({ videoId, title, suggestedStart, excerptText = null, onAddCut }: Props) {
  const mount = useRef<HTMLDivElement>(null)
  const track = useRef<HTMLDivElement>(null)
  const player = useRef<YTPlayer | null>(null)
  const [duration, setDuration] = useState(0)
  const [current, setCurrent] = useState(0)
  const [sel, setSel] = useState<Selection | null>(null)
  const [previewing, setPreviewing] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const previewEnd = useRef<number | null>(null)

  useEffect(() => {
    let cancelled = false
    loadYouTubeApi()
      .then((YT) => {
        if (cancelled || !mount.current) return
        const holder = document.createElement('div')
        mount.current.replaceChildren(holder)
        player.current = new YT.Player(holder, {
          videoId,
          host: 'https://www.youtube-nocookie.com',
          playerVars: { start: Math.floor(suggestedStart ?? 0), rel: 0, playsinline: 1 },
          events: {
            onReady: (e) => setDuration(e.target.getDuration()),
            onError: () => setLoadError('O YouTube não permite reproduzir este vídeo aqui.'),
          },
        })
      })
      .catch((e: Error) => !cancelled && setLoadError(e.message))
    return () => {
      cancelled = true
      player.current?.destroy()
      player.current = null
    }
  }, [videoId, suggestedStart])

  // Acompanha o cursor; encerra a prévia ao chegar no fim da seleção.
  useEffect(() => {
    const timer = setInterval(() => {
      const p = player.current
      if (!p?.getCurrentTime) return
      const now = p.getCurrentTime()
      setCurrent(now)
      const total = p.getDuration()
      if (total > 0) setDuration((d) => (d === total ? d : total))
      if (previewEnd.current !== null && now >= previewEnd.current) {
        p.pauseVideo()
        previewEnd.current = null
        setPreviewing(false)
      }
    }, 150)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    if (duration > 0) setSel((s) => s ?? initialSelection(suggestedStart, duration))
  }, [duration, suggestedStart])

  const seek = useCallback((time: number) => {
    player.current?.seekTo(time, true)
    setCurrent(time)
  }, [])

  const pointerTime = (e: PointerEvent) => {
    const rect = track.current!.getBoundingClientRect()
    return timeFromPointer(e.clientX, rect.left, rect.width, duration)
  }

  const onTrackDown = (e: PointerEvent<HTMLDivElement>) => {
    if (duration <= 0) return
    e.currentTarget.setPointerCapture(e.pointerId)
    previewEnd.current = null
    setPreviewing(false)
    seek(pointerTime(e))
  }
  const onTrackMove = (e: PointerEvent<HTMLDivElement>) => {
    if (e.currentTarget.hasPointerCapture(e.pointerId)) seek(pointerTime(e))
  }

  // Com pointer capture na trilha o dblclick chega nela (não na faixa); decide pela posição do clique.
  const onTrackDoubleClick = (e: MouseEvent<HTMLDivElement>) => {
    if (!sel || duration <= 0) return
    const onSelection = (e.target as HTMLElement).closest('.tl-selection') !== null
    const rect = track.current!.getBoundingClientRect()
    const time = timeFromPointer(e.clientX, rect.left, rect.width, duration)
    if (onSelection || (time >= sel.start && time <= sel.end)) void commit()
  }

  const dragHandle = (which: 'start' | 'end') => ({
    onPointerDown: (e: PointerEvent<HTMLDivElement>) => {
      e.stopPropagation()
      e.currentTarget.setPointerCapture(e.pointerId)
    },
    onPointerMove: (e: PointerEvent<HTMLDivElement>) => {
      if (!e.currentTarget.hasPointerCapture(e.pointerId) || !sel) return
      const t = pointerTime(e)
      setSel(which === 'start' ? withStart(sel, t) : withEnd(sel, t, duration))
      seek(t)
    },
    onKeyDown: (e: KeyboardEvent) => {
      if (!sel || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return
      e.preventDefault()
      const delta = (e.key === 'ArrowLeft' ? -STEP : STEP) * (e.shiftKey ? 10 : 1)
      setSel(which === 'start' ? withStart(sel, sel.start + delta) : withEnd(sel, sel.end + delta, duration))
    },
  })

  const preview = () => {
    if (!sel || !player.current) return
    previewEnd.current = sel.end
    seek(sel.start)
    player.current.playVideo()
    setPreviewing(true)
  }

  const commit = async () => {
    if (!sel || busy) return
    setBusy(true)
    try {
      await onAddCut(sel.start, sel.end)
      setFeedback({ ok: true, text: `Corte adicionado: ${formatClock(sel.start)} → ${formatClock(sel.end)}` })
    } catch (err) {
      setFeedback({ ok: false, text: err instanceof Error ? err.message : 'Falha ao adicionar o corte' })
    } finally {
      setBusy(false)
    }
  }

  const pct = (t: number) => `${duration > 0 ? clamp((t / duration) * 100, 0, 100) : 0}%`

  return (
    <div className="clip-editor">
      <div className="clip-player" ref={mount} aria-label={`Vídeo: ${title}`} />
      {loadError && <p className="error">{loadError}</p>}

      <div className="timeline" ref={track} onPointerDown={onTrackDown} onPointerMove={onTrackMove} onDoubleClick={onTrackDoubleClick} data-testid="timeline">
        {sel && (
          <div
            className="tl-selection"
            style={{ left: pct(sel.start), width: `${duration > 0 ? ((sel.end - sel.start) / duration) * 100 : 0}%` }}
            title="Duplo clique para adicionar este corte à lista"
            data-testid="selection"
          />
        )}
        <div className="tl-playhead" style={{ left: pct(current) }} />
        {sel && (
          <>
            <div
              className="tl-handle start"
              role="slider"
              tabIndex={0}
              aria-label="Início do corte"
              aria-valuemin={0}
              aria-valuemax={duration}
              aria-valuenow={sel.start}
              aria-valuetext={formatClock(sel.start)}
              style={{ left: pct(sel.start) }}
              {...dragHandle('start')}
            />
            <div
              className="tl-handle end"
              role="slider"
              tabIndex={0}
              aria-label="Fim do corte"
              aria-valuemin={0}
              aria-valuemax={duration}
              aria-valuenow={sel.end}
              aria-valuetext={formatClock(sel.end)}
              style={{ left: pct(sel.end) }}
              {...dragHandle('end')}
            />
          </>
        )}
      </div>

      <div className="clip-controls">
        <span className="clip-time" aria-live="polite">
          {formatClock(current)} / {duration > 0 ? formatClock(duration, 0) : '--:--'}
        </span>
        <button className="secondary" disabled={!sel} onClick={() => sel && setSel(withStart(sel, round1(current)))}>
          [ início = agora
        </button>
        <button className="secondary" disabled={!sel} onClick={() => sel && setSel(withEnd(sel, round1(current), duration))}>
          fim = agora ]
        </button>
        <button className="secondary" disabled={!sel || previewing} onClick={preview}>
          ▶ Prévia
        </button>
        <button disabled={!sel || busy || (sel !== null && sel.end - sel.start < MIN_CUT_SECONDS)} onClick={() => void commit()}>
          + Adicionar corte
        </button>
      </div>
      {sel && (
        <p className="clip-range">
          Seleção: <strong>{formatClock(sel.start)}</strong> → <strong>{formatClock(sel.end)}</strong> ({round1(sel.end - sel.start)}s) · duplo
          clique na faixa azul adiciona · setas ajustam as alças (Shift = 5s)
        </p>
      )}
      <p className="clip-excerpt">
        {excerptText ? (
          <>
            Trecho do texto ligado a este corte: <mark className="excerpt pending">{excerptText}</mark>
          </>
        ) : (
          'Sem trecho do texto: o corte vale para o parágrafo inteiro. Para ligar a um trecho, selecione-o no texto à esquerda.'
        )}
      </p>
      {feedback && <p className={feedback.ok ? 'clip-ok' : 'error'}>{feedback.text}</p>}
    </div>
  )
}
