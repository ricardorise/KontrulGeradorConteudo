export const MIN_CUT_SECONDS = 0.5
export const DEFAULT_CUT_SECONDS = 10

export interface Selection {
  start: number
  end: number
}

export const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max)
export const round1 = (value: number) => Math.round(value * 10) / 10

/** Converte a posição do ponteiro na barra (px) em segundos do vídeo. */
export function timeFromPointer(clientX: number, trackLeft: number, trackWidth: number, duration: number): number {
  if (trackWidth <= 0 || duration <= 0) return 0
  return round1(clamp((clientX - trackLeft) / trackWidth, 0, 1) * duration)
}

/** Move o início respeitando 0 e a duração mínima até o fim. */
export function withStart(sel: Selection, time: number): Selection {
  return { start: round1(clamp(time, 0, sel.end - MIN_CUT_SECONDS)), end: sel.end }
}

/** Move o fim respeitando a duração do vídeo e a duração mínima desde o início. */
export function withEnd(sel: Selection, time: number, duration: number): Selection {
  return { start: sel.start, end: round1(clamp(time, sel.start + MIN_CUT_SECONDS, duration)) }
}

/** Seleção inicial: a partir do trecho sugerido (ou 0), com 10 s, sempre dentro do vídeo. */
export function initialSelection(suggestedStart: number | null, duration: number): Selection {
  const start = clamp(suggestedStart ?? 0, 0, Math.max(duration - MIN_CUT_SECONDS, 0))
  return { start: round1(start), end: round1(Math.min(start + DEFAULT_CUT_SECONDS, duration)) }
}

export function formatClock(totalSeconds: number, decimals = 1): string {
  const factor = 10 ** decimals
  const safe = Math.round(Math.max(totalSeconds, 0) * factor) / factor // arredonda antes de dividir em h/m/s
  const h = Math.floor(safe / 3600)
  const m = Math.floor((safe % 3600) / 60)
  const s = safe - h * 3600 - m * 60
  const secs = s.toFixed(decimals).padStart(decimals ? decimals + 3 : 2, '0')
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${secs}` : `${m}:${secs}`
}
