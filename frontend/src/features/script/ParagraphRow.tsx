import { useRef, useState } from 'react'
import type { Broll, Cut, JobStatus, Paragraph } from '../../api/types'
import { BrollCard } from './BrollCard'
import { buildSegments, overlaps, rangeFromSelection, type TextRange } from './textSelection'
import { formatClock } from './timeline'

interface Props {
  paragraph: Paragraph
  brollStatus: JobStatus
  cuts: Cut[]
  onAddCut: (paragraphId: string, broll: Broll, start: number, end: number, text: TextRange | null) => Promise<void>
  onDeleteCut: (cutId: string) => void
  onSetCutExcerpt: (cutId: string, range: TextRange) => Promise<void>
}

export function ParagraphRow({ paragraph, brollStatus, cuts, onAddCut, onDeleteCut, onSetCutExcerpt }: Props) {
  const searching = brollStatus === 'running' || brollStatus === 'pending'
  const body = useRef<HTMLSpanElement>(null)
  const [pending, setPending] = useState<TextRange | null>(null)
  const [selectionError, setSelectionError] = useState<string | null>(null)

  const linked = cuts.flatMap((c) =>
    c.excerpt
      ? [{ start: c.excerpt.start, end: c.excerpt.end, title: `Corte ${formatClock(c.start_seconds)} → ${formatClock(c.end_seconds)}` }]
      : [],
  )

  // Seleção do texto com o mouse/teclado: vira o trecho ligado ao próximo corte.
  const captureSelection = () => {
    const selection = window.getSelection()
    const range = body.current ? rangeFromSelection(body.current, selection) : null
    if (!range) return
    selection?.removeAllRanges() // o destaque próprio substitui a seleção nativa
    if (linked.some((l) => overlaps(l, range))) {
      setSelectionError('Esse trecho já está ligado a outro corte. Escolha um trecho diferente.')
      return
    }
    setSelectionError(null)
    setPending(range)
  }

  // Aplica o trecho de texto selecionado a um corte já existente (troca o anterior, se houver).
  const applyToCut = async (cutId: string) => {
    if (!pending) return
    try {
      await onSetCutExcerpt(cutId, pending)
      setPending(null)
      setSelectionError(null)
    } catch (e) {
      setSelectionError(e instanceof Error ? e.message : 'Não foi possível trocar o trecho.')
    }
  }

  const segments = buildSegments(paragraph.text, linked, pending)
  const pendingText = pending ? paragraph.text.slice(pending.start, pending.end) : null

  return (
    <div className="paragraph-row">
      <div className="paragraph-block">
        <p className="paragraph-text">
          <span className="paragraph-number">{paragraph.position + 1}</span>
          <span ref={body} className="paragraph-body" onMouseUp={captureSelection} onKeyUp={captureSelection}>
            {segments.map((s, i) =>
              s.kind === 'plain' ? (
                s.text
              ) : (
                <mark key={i} className={`excerpt ${s.kind}`} title={s.title}>
                  {s.text}
                </mark>
              ),
            )}
          </span>
        </p>
        {pending && (
          <p className="excerpt-bar">
            Trecho selecionado: <strong>“{pendingText}”</strong> — agora dê duplo clique no intervalo do vídeo.
            <button className="secondary" onClick={() => setPending(null)}>
              Limpar
            </button>
          </p>
        )}
        {selectionError && <p className="error excerpt-bar">{selectionError}</p>}
        {!pending && !selectionError && paragraph.broll.length > 0 && cuts.every((c) => !c.excerpt) && (
          <p className="muted excerpt-hint">Dica: selecione um trecho deste texto para ligá-lo ao corte do vídeo.</p>
        )}
      </div>
      <div className="broll-column" aria-label={`B-roll do parágrafo ${paragraph.position + 1}`}>
        {paragraph.broll.map((b) => (
          <BrollCard
            key={b.id}
            broll={b}
            excerptText={pendingText}
            onAddCut={async (broll, start, end) => {
              await onAddCut(paragraph.id, broll, start, end, pending)
              setPending(null)
            }}
          />
        ))}
        {paragraph.broll.length === 0 && (
          <div className="broll-empty">
            {searching ? (
              <>
                <span className="spinner" /> Lumière buscando cenas…
              </>
            ) : brollStatus === 'done' ? (
              'Nenhuma cena confiável encontrada para este trecho.'
            ) : null}
          </div>
        )}
        {cuts.length > 0 && (
          <ul className="cut-chips" aria-label="Cortes deste parágrafo">
            {cuts.map((c) => (
              <li key={c.id} className={c.excerpt ? '' : 'no-excerpt'} title={c.excerpt ? `Trecho: ${c.excerpt.text}` : 'Sem trecho de texto'}>
                ✂ {formatClock(c.start_seconds)} → {formatClock(c.end_seconds)}
                {!c.excerpt && <em> sem trecho</em>}
                <button
                  aria-label="Usar o texto selecionado neste corte"
                  title={pending ? 'Vincular o texto selecionado a este corte' : 'Primeiro selecione um trecho no texto do parágrafo'}
                  disabled={!pending}
                  onClick={() => void applyToCut(c.id)}
                >
                  ✎
                </button>
                <button aria-label="Remover corte" onClick={() => onDeleteCut(c.id)}>
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
