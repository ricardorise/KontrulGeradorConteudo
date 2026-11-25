import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { Publication, PublicationEdit } from '../../api/types'
import { usePolling } from '../../hooks/usePolling'

interface Props {
  publicationId: string
  refreshKey?: number // muda quando o chat altera/revisa a publicação
  onClose: () => void
}

const busy = (p: Publication) => p.status === 'drafting' || p.status === 'publishing'
const PRIVACY_LABEL: Record<string, string> = { private: 'Privado', unlisted: 'Não listado' }

/** Normaliza como o servidor: sem "#", sem repetidos (ignora maiúsculas). */
export const parseTags = (raw: string): string[] => {
  const seen = new Set<string>()
  return raw
    .split(/[,\n]/)
    .map((t) => t.trim().replace(/^#+/, '').trim())
    .filter((t) => {
      const key = t.toLowerCase()
      if (!t || seen.has(key)) return false
      seen.add(key)
      return true
    })
}

export function PublicationView({ publicationId, refreshKey = 0, onClose }: Props) {
  const pub = usePolling(publicationId, () => api.getPublication(publicationId), busy, 2500, 8000)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [dirty, setDirty] = useState(false)
  const [instructions, setInstructions] = useState('')
  const [target, setTarget] = useState<'all' | 'title' | 'description' | 'tags'>('all')
  const [working, setWorking] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const p = pub.data

  // Mudanças vindas do chat/servidor entram no formulário, a não ser que o editor esteja no meio de uma edição.
  useEffect(() => {
    if (!p || dirty) return
    setTitle(p.title)
    setDescription(p.description)
    setTags(p.tags.join(', '))
  }, [p, dirty])
  useEffect(() => {
    if (refreshKey > 0) {
      setDirty(false)
      pub.refresh()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey])

  const run = async (fn: () => Promise<Publication>, after?: () => void) => {
    setWorking(true)
    setActionError(null)
    try {
      pub.setData(await fn())
      pub.refresh()
      after?.()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Falha na operação')
    } finally {
      setWorking(false)
    }
  }

  if (!p)
    return (
      <div className="publication">
        {pub.error ? <p className="error">{pub.error}</p> : <p className="loading"><span className="spinner" /> Carregando a publicação…</p>}
        <button className="secondary" onClick={onClose}>Voltar ao roteiro</button>
      </div>
    )

  const editable = p.status === 'ready'
  const tagList = parseTags(tags)
  const titleTooLong = title.length > p.limits.title
  const save = () => {
    const edit: PublicationEdit = { title, description, tags: tagList }
    return run(() => api.editPublication(p.id, edit), () => setDirty(false))
  }
  const setPrivacy = (privacy: string) => void run(() => api.editPublication(p.id, { privacy }))
  const removeLink = (url: string) => void run(() => api.editPublication(p.id, { links: p.links.filter((l) => l.url !== url) }))

  return (
    <div className="publication" aria-label="Publicação no YouTube">
      <header className="publication-head">
        <h2>Publicação no YouTube</h2>
        <button className="secondary" onClick={onClose}>Voltar ao roteiro</button>
      </header>

      {p.status === 'drafting' && (
        <p className="loading" role="status">
          <span className="spinner" /> {p.title ? 'Revisando com os especialistas (Jules Verne: descrição · Youtoba: título e tags)…' : 'Jules Verne está escrevendo a descrição e o Youtoba, o título e as tags…'}
        </p>
      )}
      {p.status === 'publishing' && (
        <p className="loading" role="status">
          <span className="spinner" /> Enviando o vídeo ao YouTube… pode levar alguns minutos. Não feche esta página.
        </p>
      )}
      {p.status === 'published' && (
        <p className="clip-ok" role="status">
          ✔ Enviado ao YouTube{p.privacy ? ` (${PRIVACY_LABEL[p.privacy] ?? p.privacy})` : ''}.{' '}
          {p.video_url && <a href={p.video_url} target="_blank" rel="noreferrer">{p.video_url}</a>}
        </p>
      )}
      {p.status === 'failed' && <p className="error" role="alert">Falhou: {p.error}</p>}
      {p.status === 'ready' && p.error && (
        <p className="error" role="alert">
          {p.error_stage === 'publish' ? 'Não publicou: ' : 'A última alteração não foi aplicada: '}
          {p.error}
        </p>
      )}
      {actionError && <p className="error">{actionError}</p>}

      {p.status !== 'failed' && p.title !== '' && (
        <>
          <label className="field">
            Título <span className={titleTooLong ? 'error' : 'muted'}>{title.length}/{p.limits.title}</span>
            <input value={title} disabled={!editable} onChange={(e) => { setTitle(e.target.value); setDirty(true) }} />
          </label>
          {p.title_alternatives.length > 0 && editable && (
            <div className="alternatives" aria-label="Títulos alternativos">
              <small className="muted">Alternativas do Youtoba:</small>
              {p.title_alternatives.map((t) => (
                <button key={t} className="secondary alt" onClick={() => { setTitle(t); setDirty(true) }}>{t}</button>
              ))}
            </div>
          )}

          <label className="field">
            Descrição (escrita pelo Jules Verne)
            <textarea rows={9} value={description} disabled={!editable} onChange={(e) => { setDescription(e.target.value); setDirty(true) }} />
          </label>

          <label className="field">
            Tags ({tagList.length}) — separe por vírgula
            <input value={tags} disabled={!editable} onChange={(e) => { setTags(e.target.value); setDirty(true) }} />
          </label>
          <div className="tag-chips" aria-label="Tags">
            {tagList.map((t) => <span key={t} className="chip">{t}</span>)}
          </div>

          <h3 className="render-h">Links que vão na descrição do vídeo ({p.links.length})</h3>
          {p.links.length === 0 && <p className="muted">Nenhum link.</p>}
          <ul className="pub-links">
            {p.links.map((l) => (
              <li key={l.url}>
                <span className="muted">{l.kind === 'broll' ? 'Vídeo usado' : 'Fonte'}:</span> <a href={l.url} target="_blank" rel="noreferrer">{l.label}</a>
                {editable && <button className="secondary" aria-label={`Remover link ${l.label}`} onClick={() => removeLink(l.url)}>✕</button>}
              </li>
            ))}
          </ul>

          <div className="pub-options">
            <label className="field">
              Visibilidade
              <select value={p.privacy} disabled={!editable} onChange={(e) => setPrivacy(e.target.value)}>
                {p.allowed_privacies.map((v) => <option key={v} value={v}>{PRIVACY_LABEL[v] ?? v}</option>)}
              </select>
            </label>
            <small className="muted">A tornar público, faça no YouTube Studio depois de conferir o vídeo.</small>
          </div>

          {p.rationale && <p className="muted"><b>Por que este título:</b> {p.rationale}</p>}

          <details>
            <summary>Texto final da descrição no YouTube ({p.description_chars}/{p.limits.description})</summary>
            <pre className="edit-list" aria-label="Descrição final">{p.full_description}</pre>
          </details>

          {p.problems.length > 0 && (
            <ul className="render-problems" role="alert">{p.problems.map((x) => <li key={x}>{x}</li>)}</ul>
          )}

          {editable && (
            <section className="revise" aria-label="Pedir alteração">
              <h3 className="render-h">Pedir uma alteração</h3>
              <p className="muted">Também dá para pedir pelo chat (Jules Verne ou Youtoba): a página atualiza sozinha.</p>
              <div className="revise-row">
                <select aria-label="O que alterar" value={target} onChange={(e) => setTarget(e.target.value as typeof target)}>
                  <option value="all">Tudo</option>
                  <option value="title">Só o título</option>
                  <option value="description">Só a descrição</option>
                  <option value="tags">Só as tags</option>
                </select>
                <input aria-label="Instruções" value={instructions} onChange={(e) => setInstructions(e.target.value)} placeholder="Ex.: título mais curto, descrição mais informal" />
                <button
                  className="secondary"
                  disabled={working || dirty || instructions.trim().length < 3}
                  onClick={() => void run(() => api.revisePublication(p.id, target, instructions.trim()), () => setInstructions(''))}
                >
                  Revisar
                </button>
              </div>
              {dirty && <small className="muted">Salve ou descarte suas edições manuais antes de pedir uma revisão.</small>}
            </section>
          )}
        </>
      )}

      <div className="render-actions">
        {editable && dirty && (
          <>
            <button onClick={() => void save()} disabled={working || titleTooLong}>Salvar edições</button>
            <button className="secondary" onClick={() => setDirty(false)}>Descartar</button>
          </>
        )}
        {(p.status === 'ready' || p.status === 'failed') && (
          <button className="secondary" onClick={() => void run(() => api.regeneratePublication(p.id))} disabled={working || dirty}>Regenerar tudo</button>
        )}
        {editable && (
          <button className="youtube-btn" disabled={working || dirty || !p.can_publish} onClick={() => setConfirming(true)}>
            Publicar no YouTube
          </button>
        )}
        {editable && dirty && <span className="muted">Salve as edições para publicar.</span>}
      </div>

      {confirming && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Confirmar publicação" onClick={() => setConfirming(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h2>Publicar no YouTube?</h2>
            <p><b>{p.title}</b></p>
            <p className="muted">O vídeo será enviado ao canal como <b>{PRIVACY_LABEL[p.privacy] ?? p.privacy}</b>, com {p.tags.length} tags e {p.links.length} links na descrição.</p>
            <div className="render-actions">
              <button className="youtube-btn" onClick={() => { setConfirming(false); void run(() => api.publishPublication(p.id)) }}>Confirmar e publicar</button>
              <button className="secondary" onClick={() => setConfirming(false)}>Cancelar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
