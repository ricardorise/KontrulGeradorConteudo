import { useState, type FormEvent } from 'react'

interface Props {
  label: string // ex.: "Link do novo vídeo"
  submitLabel: string
  onSubmit: (url: string) => Promise<void>
  onCancel: () => void
}

/** Campo para colar um link do YouTube escolhido pelo editor (inserir ou trocar um vídeo do B-roll). */
export function BrollUrlForm({ label, submitLabel, onSubmit, onCancel }: Props) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!url.trim() || busy) return
    setBusy(true)
    setError(null)
    try {
      await onSubmit(url.trim())
      onCancel() // sucesso: fecha o formulário
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Não foi possível usar este vídeo.')
      setBusy(false)
    }
  }

  return (
    <form className="broll-url-form" onSubmit={submit}>
      <input
        autoFocus
        type="url"
        aria-label={label}
        placeholder="https://www.youtube.com/watch?v=… (aceita &t=90 para começar no instante)"
        value={url}
        maxLength={300}
        onChange={(e) => setUrl(e.target.value)}
      />
      <button type="submit" disabled={busy || !url.trim()}>
        {busy ? 'Buscando…' : submitLabel}
      </button>
      <button type="button" className="secondary" onClick={onCancel} disabled={busy}>
        Cancelar
      </button>
      {error && <p className="error">{error}</p>}
    </form>
  )
}
