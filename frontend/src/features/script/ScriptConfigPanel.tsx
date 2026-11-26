import { useEffect, useState } from 'react'
import { api } from '../../api/client'
import type { ScriptConfigInput, ScriptOptions } from '../../api/types'

interface Props {
  newsTitle?: string
  mergedTitles?: string[] // roteiro agregado: títulos das notícias juntadas (a principal primeiro)
  onGenerate: (config: ScriptConfigInput) => void
  onCancel?: () => void
  busy?: boolean
}

type Saved = { profile: string | null; minutes: number | null; two: boolean; names: [string, string]; solo: string }
const KEY = 'script-config'

const load = (): Saved => {
  try {
    return { profile: null, minutes: null, two: false, names: ['', ''], solo: '', ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch {
    return { profile: null, minutes: null, two: false, names: ['', ''], solo: '' }
  }
}

/** "Configuração do roteiro": perfil do roteirista, tempo e apresentadores, definidos antes de gerar. */
export function ScriptConfigPanel({ newsTitle, mergedTitles, onGenerate, onCancel, busy }: Props) {
  const [options, setOptions] = useState<ScriptOptions | null>(null)
  const [error, setError] = useState<string | null>(null)
  const saved = load()
  const [profileId, setProfileId] = useState<string | null>(saved.profile)
  const [minutes, setMinutes] = useState<number | null>(saved.minutes)
  const [two, setTwo] = useState(saved.two)
  const [names, setNames] = useState<[string, string]>(saved.names)
  const [solo, setSolo] = useState(saved.solo)
  const [theme, setTheme] = useState('')
  const [creating, setCreating] = useState(false)
  const [draft, setDraft] = useState({ name: '', description: '', instructions: '' })

  const reload = () =>
    api
      .scriptOptions()
      .then(setOptions)
      .catch((e) => setError(e instanceof Error ? e.message : 'Falha ao carregar as opções'))
  useEffect(() => {
    void reload()
  }, [])

  const profile = options?.profiles.find((p) => p.id === profileId) ?? null
  const duration = options?.durations.find((d) => d.minutes === minutes) ?? null
  const trimmed = names.map((n) => n.trim()) as [string, string]
  const namesOk = !two || (trimmed[0] !== '' && trimmed[1] !== '' && trimmed[0].toLowerCase() !== trimmed[1].toLowerCase())
  const ready = !!profile && !!duration && namesOk

  const generate = () => {
    if (!ready) return
    try {
      localStorage.setItem(KEY, JSON.stringify({ profile: profileId, minutes, two, names, solo }))
    } catch {
      /* sem armazenamento: só não lembra */
    }
    onGenerate({
      profile_id: profileId,
      duration_minutes: minutes,
      presenters: two ? trimmed : solo.trim() ? [solo.trim()] : [],
      theme: theme.trim() || null,
    })
  }

  const createProfile = async () => {
    setError(null)
    try {
      const created = await api.addScriptProfile(draft.name.trim(), draft.instructions.trim(), draft.description.trim())
      await reload()
      setProfileId(created.id)
      setCreating(false)
      setDraft({ name: '', description: '', instructions: '' })
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao salvar o perfil')
    }
  }

  const removeProfile = async (id: string) => {
    setError(null)
    try {
      await api.deleteScriptProfile(id)
      if (profileId === id) setProfileId(null)
      await reload()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Falha ao apagar o perfil')
    }
  }

  return (
    <section className="script-config" aria-label="Configuração do roteiro">
      <header className="publication-head">
        <h2>Configuração do roteiro</h2>
        {onCancel && (
          <button className="secondary" onClick={onCancel}>
            Cancelar
          </button>
        )}
      </header>
      {mergedTitles && mergedTitles.length > 1 ? (
        <div className="source" aria-label="Notícias agregadas">
          <strong>Roteiro agregado de {mergedTitles.length} notícias:</strong>
          <ol className="merged-list">
            {mergedTitles.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ol>
        </div>
      ) : (
        newsTitle && <p className="source">Notícia: {newsTitle}</p>
      )}
      <p className="muted">Defina como o roteiro deve ser escrito antes de gerá-lo.</p>
      {error && <p className="error">{error}</p>}
      {!options && !error && (
        <p className="loading">
          <span className="spinner" /> Carregando…
        </p>
      )}

      {options && (
        <>
          <label className="field">
            Assunto / tema do vídeo (opcional)
            <input
              value={theme}
              maxLength={200}
              onChange={(e) => setTheme(e.target.value)}
              placeholder={mergedTitles && mergedTitles.length > 1 ? 'Ex.: A corrida dos headsets de VR em 2026' : 'Ex.: o ângulo que o vídeo deve ter'}
            />
            <small className="muted">
              {mergedTitles && mergedTitles.length > 1
                ? 'Diz ao roteirista o fio condutor que une as notícias.'
                : 'Se preencher, o roteiro gira em torno deste tema.'}
            </small>
          </label>

          <fieldset className="cfg-group">
            <legend>Perfil do roteirista</legend>
            <div className="cfg-options" role="radiogroup" aria-label="Perfil do roteirista">
              {options.profiles.map((p) => (
                <label key={p.id} className={`cfg-option${profileId === p.id ? ' selected' : ''}`}>
                  <input type="radio" name="profile" checked={profileId === p.id} onChange={() => setProfileId(p.id)} />
                  <span>
                    <strong>{p.name}</strong>
                    {!p.builtin && <span className="badge"> seu perfil</span>}
                    <small className="muted">{p.description || p.instructions.slice(0, 90)}</small>
                  </span>
                  {!p.builtin && (
                    <button type="button" className="secondary" aria-label={`Apagar perfil ${p.name}`} onClick={() => void removeProfile(p.id)}>
                      ✕
                    </button>
                  )}
                </label>
              ))}
            </div>
            {profile && <p className="muted cfg-detail">{profile.instructions}</p>}
            {!creating ? (
              <button type="button" className="secondary" onClick={() => setCreating(true)}>
                + Cadastrar novo perfil
              </button>
            ) : (
              <div className="cfg-new">
                <label className="field">
                  Nome do perfil
                  <input value={draft.name} maxLength={60} onChange={(e) => setDraft({ ...draft, name: e.target.value })} />
                </label>
                <label className="field">
                  Resumo (opcional)
                  <input value={draft.description} maxLength={200} onChange={(e) => setDraft({ ...draft, description: e.target.value })} />
                </label>
                <label className="field">
                  Como o roteirista deve escrever (tom, estrutura, vocabulário…)
                  <textarea rows={4} value={draft.instructions} maxLength={1500} onChange={(e) => setDraft({ ...draft, instructions: e.target.value })} />
                </label>
                <div className="render-actions">
                  <button type="button" onClick={() => void createProfile()} disabled={!draft.name.trim() || draft.instructions.trim().length < 10}>
                    Salvar perfil
                  </button>
                  <button type="button" className="secondary" onClick={() => setCreating(false)}>
                    Cancelar
                  </button>
                </div>
              </div>
            )}
          </fieldset>

          <fieldset className="cfg-group">
            <legend>Tempo de roteiro</legend>
            <div className="cfg-options cfg-times" role="radiogroup" aria-label="Tempo de roteiro">
              {options.durations.map((d) => (
                <label key={d.minutes} className={`cfg-option${minutes === d.minutes ? ' selected' : ''}`}>
                  <input type="radio" name="minutes" checked={minutes === d.minutes} onChange={() => setMinutes(d.minutes)} />
                  <span>
                    <strong>Vídeo de {d.minutes} minutos</strong>
                    <small className="muted">até {d.max_chars.toLocaleString('pt-BR')} caracteres</small>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="cfg-group">
            <legend>Apresentadores</legend>
            <div className="cfg-options cfg-times" role="radiogroup" aria-label="Apresentadores">
              <label className={`cfg-option${!two ? ' selected' : ''}`}>
                <input type="radio" name="presenters" checked={!two} onChange={() => setTwo(false)} />
                <span>
                  <strong>Um apresentador</strong>
                  <small className="muted">um só lê o roteiro</small>
                </span>
              </label>
              <label className={`cfg-option${two ? ' selected' : ''}`}>
                <input type="radio" name="presenters" checked={two} onChange={() => setTwo(true)} />
                <span>
                  <strong>Dois apresentadores</strong>
                  <small className="muted">falas separadas para cada um</small>
                </span>
              </label>
            </div>
            {two ? (
              <div className="cfg-names">
                <label className="field">
                  Nome do apresentador 1
                  <input value={names[0]} maxLength={40} onChange={(e) => setNames([e.target.value, names[1]])} />
                </label>
                <label className="field">
                  Nome do apresentador 2
                  <input value={names[1]} maxLength={40} onChange={(e) => setNames([names[0], e.target.value])} />
                </label>
                {!namesOk && <small className="muted">Informe dois nomes diferentes.</small>}
              </div>
            ) : (
              <label className="field">
                Nome do apresentador (opcional)
                <input value={solo} maxLength={40} onChange={(e) => setSolo(e.target.value)} />
              </label>
            )}
          </fieldset>

          <div className="render-actions">
            <button onClick={generate} disabled={!ready || busy}>
              {busy ? 'Gerando…' : 'Gerar roteiro'}
            </button>
            {!ready && <span className="muted">Escolha o perfil e o tempo{two && !namesOk ? ' e informe os dois nomes' : ''} para gerar.</span>}
          </div>
        </>
      )}
    </section>
  )
}
