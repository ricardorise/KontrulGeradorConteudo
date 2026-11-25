export interface TextRange {
  start: number
  end: number
}

export type SegmentKind = 'plain' | 'linked' | 'pending'
export interface Segment {
  text: string
  kind: SegmentKind
  title?: string
}

export const overlaps = (a: TextRange, b: TextRange) => a.start < b.end && b.start < a.end

/** Encolhe o intervalo para não incluir espaços nas pontas; devolve null se sobrar nada. */
export function trimRange(text: string, range: TextRange): TextRange | null {
  let { start, end } = range
  while (start < end && /\s/.test(text[start])) start++
  while (end > start && /\s/.test(text[end - 1])) end--
  return end > start ? { start, end } : null
}

/**
 * Divide o texto do parágrafo em pedaços (normal / ligado a um corte / seleção pendente).
 * Os trechos ligados nunca se sobrepõem (o backend garante); o pendente é ignorado se sobrepuser algum.
 */
export function buildSegments(
  text: string,
  linked: (TextRange & { title?: string })[],
  pending: TextRange | null,
): Segment[] {
  const marks = [
    ...linked.map((l) => ({ ...l, kind: 'linked' as const })),
    ...(pending && !linked.some((l) => overlaps(l, pending)) ? [{ ...pending, kind: 'pending' as const, title: undefined }] : []),
  ].sort((a, b) => a.start - b.start)

  const segments: Segment[] = []
  let cursor = 0
  for (const m of marks) {
    if (m.start > cursor) segments.push({ text: text.slice(cursor, m.start), kind: 'plain' })
    segments.push({ text: text.slice(m.start, m.end), kind: m.kind, title: m.title })
    cursor = m.end
  }
  if (cursor < text.length) segments.push({ text: text.slice(cursor), kind: 'plain' })
  return segments
}

/** Offsets (em caracteres) da seleção do navegador em relação ao texto de `container`. */
export function rangeFromSelection(container: HTMLElement, selection: Selection | null): TextRange | null {
  if (!selection || selection.rangeCount === 0 || selection.isCollapsed) return null
  const range = selection.getRangeAt(0)
  if (!container.contains(range.startContainer) || !container.contains(range.endContainer)) return null
  const offsetOf = (node: Node, offset: number) => {
    const before = document.createRange()
    before.selectNodeContents(container)
    before.setEnd(node, offset)
    return before.toString().length
  }
  const full = container.textContent ?? ''
  return trimRange(full, { start: offsetOf(range.startContainer, range.startOffset), end: offsetOf(range.endContainer, range.endOffset) })
}
