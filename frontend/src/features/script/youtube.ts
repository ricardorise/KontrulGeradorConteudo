export function formatTimestamp(totalSeconds: number | null): string | null {
  if (totalSeconds === null || totalSeconds === undefined) return null
  const h = Math.floor(totalSeconds / 3600)
  const m = Math.floor((totalSeconds % 3600) / 60)
  const s = totalSeconds % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

export const thumbnailUrl = (videoId: string) => `https://i.ytimg.com/vi/${videoId}/mqdefault.jpg`

export const embedUrl = (videoId: string, startSeconds: number | null) =>
  `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1&rel=0${startSeconds != null ? `&start=${startSeconds}` : ''}`

export const watchUrl = (videoId: string, startSeconds: number | null) =>
  `https://youtu.be/${videoId}${startSeconds != null ? `?t=${startSeconds}` : ''}`
