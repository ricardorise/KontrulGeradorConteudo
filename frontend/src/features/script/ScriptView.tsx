import { useState } from 'react'
import { api } from '../../api/client'
import type { Broll, Script } from '../../api/types'
import type { TextRange } from './textSelection'
import { CutList } from './CutList'
import { ParagraphRow } from './ParagraphRow'

interface Props {
  onPublication?: (publicationId: string) => void
  script: Script | null
  error: string | null
  onChanged: (script: Script) => void
  onCutsChanged: (script: Script) => void // atualiza sem recarregar (não fecha os players abertos)
  onRetryScript: () => void
}

export function ScriptView({ script, error, onChanged, onCutsChanged, onRetryScript, onPublication }: Props) {
  const [selecting, setSelecting] = useState(false)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [autoOpenId, setAutoOpenId] = useState<string | null>(null)

  if (!script) {
    return error ? <p className="error">{error}</p> : <p className="empty">Escolha uma notícia para gerar o roteiro.</p>
  }
  if (script.status === 'running' || script.status === 'pending') {
    return (
      <div className="loading" role="status">
        <span className="spinner" /> Jules Verne está escrevendo o roteiro…
        <small>Depois dele, a Lumière busca o B-roll no YouTube.</small>
      </div>
    )
  }
  if (script.status === 'failed') {
    return (
      <div>
        <p className="error">Não foi possível gerar o roteiro: {script.error}</p>
        <button onClick={onRetryScript}>Tentar novamente</button>
      </div>
    )
  }

  const searching = script.broll_status === 'running' || script.broll_status === 'pending'
  const retryBroll = async (paragraphIds?: string[]) => {
    setSelecting(false)
    setSelected(new Set())
    onChanged(await api.retryBroll(script.id, paragraphIds))
  }
  const toggleSelected = (id: string) =>
    setSelected((current) => {
      const next = new Set(current)
      if (!next.delete(id)) next.add(id)
      return next
    })
  // B-roll escolhido por você: inserir, trocar e remover (o que você escolheu sobrevive a "rebuscar")
  const addBroll = async (paragraphId: string, url: string) => {
    const known = new Set(script.paragraphs.flatMap((p) => p.broll.map((b) => b.id)))
    const updated = await api.addBroll(script.id, paragraphId, url)
    setAutoOpenId(updated.paragraphs.flatMap((p) => p.broll).find((b) => !known.has(b.id))?.id ?? null) // abre já para recortar
    onCutsChanged(updated)
  }
  const replaceBroll = async (brollId: string, url: string) => onCutsChanged(await api.replaceBroll(script.id, brollId, url))
  const removeBroll = async (brollId: string) => onCutsChanged(await api.removeBroll(script.id, brollId))
  const addCut = async (paragraphId: string, b: Broll, start: number, end: number, text: TextRange | null) =>
    onCutsChanged(
      await api.addCut(script.id, {
        paragraph_id: paragraphId,
        video_url: b.video_url,
        start_seconds: start,
        end_seconds: end,
        video_title: b.title,
        ...(text ? { text_start: text.start, text_end: text.end } : {}),
      }),
    )
  const setCutExcerpt = async (cutId: string, range: TextRange) =>
    onCutsChanged(await api.setCutExcerpt(script.id, cutId, { text_start: range.start, text_end: range.end }))
  const deleteCut = async (cutId: string) => onCutsChanged(await api.deleteCut(script.id, cutId))

  return (
    <section>
      <header className="script-header">
        <h2>{script.title ?? 'Roteiro'}</h2>
        <div className="script-actions">
          {(script.broll_status === 'running' || script.broll_status === 'pending') && (
            <span className="badge">
              <span className="spinner" /> Buscando B-roll
            </span>
          )}
          {script.broll_status === 'failed' && (
            <span className="badge badge-error" title={script.broll_error ?? ''}>
              B-roll falhou
            </span>
          )}
          {script.broll_status === 'done' && <span className="badge badge-ok">B-roll pronto</span>}
          {selecting ? (
            <>
              <button onClick={() => void retryBroll([...selected])} disabled={searching || selected.size === 0}>
                Rebuscar selecionados ({selected.size})
              </button>
              <button className="secondary" onClick={() => setSelected(new Set(script.paragraphs.map((p) => p.id)))}>
                Marcar todos
              </button>
              <button
                className="secondary"
                onClick={() => {
                  setSelecting(false)
                  setSelected(new Set())
                }}
              >
                Cancelar
              </button>
            </>
          ) : (
            <>
              <button
                className="secondary"
                onClick={() => setSelecting(true)}
                disabled={searching}
                title="Marque os parágrafos cujo B-roll você quer buscar de novo; os demais ficam como estão"
              >
                Escolher parágrafos para rebuscar
              </button>
              <button
                className="secondary"
                onClick={() => void retryBroll()}
                disabled={searching}
                title="Troca as sugestões automáticas de todos os parágrafos (os vídeos que você escolheu ficam)"
              >
                Rebuscar todos
              </button>
              <button className="secondary" onClick={onRetryScript}>
                Gerar novo roteiro
              </button>
            </>
          )}
        </div>
      </header>
      {script.broll_status === 'failed' && <p className="error">{script.broll_error}</p>}
      <div className="script-columns-head" aria-hidden>
        <span>Roteiro</span>
        <span>B-roll sugerido (YouTube)</span>
      </div>
      {script.paragraphs.map((p) => (
        <ParagraphRow
          key={p.id}
          paragraph={p}
          brollStatus={script.broll_status}
          cuts={script.cuts.filter((c) => c.paragraph_id === p.id)}
          onAddCut={addCut}
          onDeleteCut={(id) => void deleteCut(id)}
          onSetCutExcerpt={setCutExcerpt}
          onAddBroll={addBroll}
          onReplaceBroll={replaceBroll}
          onRemoveBroll={(id) => void removeBroll(id)}
          onRetryParagraph={(id) => void retryBroll([id])}
          retryDisabled={searching}
          selecting={selecting}
          selected={selected.has(p.id)}
          onToggleSelect={toggleSelected}
          autoOpenBrollId={autoOpenId}
        />
      ))}
      <CutList script={script} onDelete={(id) => void deleteCut(id)} onPublication={onPublication} />
    </section>
  )
}
