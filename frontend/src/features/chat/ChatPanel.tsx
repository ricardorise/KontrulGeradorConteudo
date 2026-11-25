import { useEffect, useRef, useState, type FormEvent } from 'react'
import { api } from '../../api/client'
import type { ChatAction, ChatBot, Conversation, ScreenContext } from '../../api/types'
import { usePolling } from '../../hooks/usePolling'

const BOTS: { id: ChatBot; label: string; role: string }[] = [
  { id: 'tonton', label: 'Tonton', role: 'notícias' },
  { id: 'julesverne', label: 'Jules Verne', role: 'roteiro' },
  { id: 'lumiere', label: 'Lumière', role: 'B-rolls' },
  { id: 'baru', label: 'Baru', role: 'supervisor' },
]

const hasPending = (c: Conversation) => c.messages.some((m) => m.role === 'assistant' && (m.status === 'running' || m.status === 'pending'))

interface Props {
  context: ScreenContext
  onActions: (actions: ChatAction[]) => void
}

export function ChatPanel({ context, onActions }: Props) {
  const [bot, setBot] = useState<ChatBot>('baru')
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [past, setPast] = useState<Conversation[]>([])
  const [draft, setDraft] = useState('')
  const [sendError, setSendError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const awaiting = useRef(new Set<string>()) // respostas pendentes desta sessão (ações só rodam na tela uma vez)

  const lastByBot = useRef<Partial<Record<ChatBot, string>>>({}) // volta à conversa do bot ao alternar abas

  const { data: conversation, error, setData, refresh } = usePolling(
    conversationId,
    () => api.getConversation(conversationId!),
    hasPending,
    1500,
    8000, // segue atualizando mesmo sem resposta pendente (outra aba/sessão pode ter mexido)
  )

  useEffect(() => {
    let cancelled = false
    setConversationId(lastByBot.current[bot] ?? null)
    setSendError(null)
    api
      .listConversations(bot)
      .then((list) => !cancelled && setPast(list))
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [bot])

  useEffect(() => {
    for (const m of conversation?.messages ?? []) {
      const waiting = m.role === 'assistant' && (m.status === 'running' || m.status === 'pending')
      if (waiting) awaiting.current.add(m.id)
      else if (awaiting.current.delete(m.id) && m.actions.length) onActions(m.actions)
    }
  }, [conversation?.messages])

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [conversation?.messages])

  const pending = conversation ? hasPending(conversation) : false

  const send = async (e: FormEvent) => {
    e.preventDefault()
    const content = draft.trim()
    if (!content || pending) return
    setSendError(null)
    try {
      const id = conversationId ?? (await api.openConversation(bot)).id
      const updated = await api.sendMessage(id, content, context)
      setDraft('')
      setData(updated)
      lastByBot.current[bot] = id
      refresh() // a conversa já existia: sem isto o polling não voltava e a resposta nunca aparecia
      if (!conversationId) {
        setConversationId(id)
        setPast((p) => [updated, ...p])
      } else {
        setPast((p) => p.map((c) => (c.id === id ? { ...c, title: updated.title } : c)))
      }
    } catch (err) {
      setSendError(err instanceof Error ? err.message : 'Falha ao enviar')
    }
  }

  const botInfo = BOTS.find((b) => b.id === bot)!

  return (
    <aside className="chat" aria-label="Chat com os bots">
      <div className="chat-tabs" role="tablist">
        {BOTS.map((b) => (
          <button key={b.id} role="tab" aria-selected={b.id === bot} className={b.id === bot ? 'active' : ''} onClick={() => setBot(b.id)}>
            {b.label}
            <small>{b.role}</small>
          </button>
        ))}
      </div>

      <div className="chat-toolbar">
        <select
          aria-label="Conversas anteriores"
          value={conversationId ?? ''}
          onChange={(e) => setConversationId(e.target.value || null)}
        >
          <option value="">Nova conversa</option>
          {past.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
        <button className="secondary" onClick={() => setConversationId(null)}>
          Nova
        </button>
      </div>

      <div className="chat-messages" aria-live="polite">
        {!conversation && <p className="empty">Converse com {botInfo.label} ({botInfo.role}).</p>}
        {conversation?.messages.map((m) => (
          <div key={m.id} className={`bubble ${m.role}${m.status === 'failed' ? ' failed' : ''}`}>
            {m.status === 'running' || m.status === 'pending' ? (
              <span className="typing">
                <span className="spinner" /> {botInfo.label} está respondendo…
              </span>
            ) : m.status === 'failed' ? (
              <>Falha: {m.error}</>
            ) : (
              m.content
            )}
            {m.actions.length > 0 && (
              <ul className="action-chips">
                {m.actions.map((a, i) => (
                  <li key={i} className={a.status === 'failed' ? 'chip failed' : 'chip'}>
                    {a.status === 'failed' ? `✖ ${a.error ?? a.label}` : `✔ ${a.label}`}
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
        {error && <p className="error">{error}</p>}
        <div ref={endRef} />
      </div>

      {sendError && <p className="error">{sendError}</p>}
      <form className="chat-input" onSubmit={send}>
        <textarea
          aria-label="Mensagem"
          placeholder={`Mensagem para ${botInfo.label}…`}
          value={draft}
          rows={2}
          maxLength={4000}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) void send(e)
          }}
        />
        <button type="submit" disabled={pending || !draft.trim()}>
          Enviar
        </button>
      </form>
    </aside>
  )
}
