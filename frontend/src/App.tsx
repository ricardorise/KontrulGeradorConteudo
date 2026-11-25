import { useEffect, useState } from 'react'
import { api } from './api/client'
import type { ChatAction, NewsSearch, RadarSearchOptions, Script } from './api/types'
import { ChatPanel } from './features/chat/ChatPanel'
import { GuidelinesPanel } from './features/guidance/GuidelinesPanel'
import { NewsList } from './features/news/NewsList'
import { SearchBar } from './features/news/SearchBar'
import { SearchHistory } from './features/news/SearchHistory'
import { ScriptView } from './features/script/ScriptView'
import { usePolling } from './hooks/usePolling'

const searchRunning = (s: NewsSearch) => s.status === 'running' || s.status === 'pending'
const scriptRunning = (s: Script) =>
  s.status === 'running' || s.status === 'pending' || s.broll_status === 'running' || s.broll_status === 'pending'

export function App() {
  const [searchId, setSearchId] = useState<string | null>(null)
  const [itemId, setItemId] = useState<string | null>(null)
  const [scriptId, setScriptId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [showGuidelines, setShowGuidelines] = useState(false)
  const [guidelinesVersion, setGuidelinesVersion] = useState(0)

  const [notice, setNotice] = useState<string | null>(null)

  // Nada fica "parado" na tela: depois de pronto, segue consultando devagar (cortes/B-roll mudados em outro lugar, etc.).
  const search = usePolling(searchId, () => api.getNewsSearch(searchId!), searchRunning, 2500, 10000)
  const script = usePolling(scriptId, () => api.getScript(scriptId!), (s) => scriptRunning(s) && s.status !== 'failed', 2500, 6000)

  // Se surgir um roteiro mais novo para a notícia aberta (pedido pelo chat, por outra aba...), a tela passa a mostrá-lo.
  const latest = usePolling(itemId, () => api.getLatestScript(itemId!), () => true, 6000)
  useEffect(() => {
    const newest = latest.data
    if (!newest || newest.id === scriptId) return
    if (script.data && newest.created_at <= script.data.created_at) return
    setScriptId(newest.id)
    setNotice('Roteiro atualizado: abrindo a versão mais recente.')
  }, [latest.data, scriptId, script.data])
  useEffect(() => {
    if (!notice) return
    const timer = setTimeout(() => setNotice(null), 6000)
    return () => clearTimeout(timer)
  }, [notice])

  const startSearch = async (topic: string, options?: RadarSearchOptions) => {
    setActionError(null)
    try {
      const created = await api.startNewsSearch(topic, options)
      setItemId(null)
      setScriptId(null)
      setSearchId(created.id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Falha ao iniciar a busca')
    }
  }

  const openSearch = (id: string) => {
    setItemId(null)
    setScriptId(null)
    setSearchId(id)
  }

  const generateScript = async (newsItemId: string, force = false) => {
    setActionError(null)
    setItemId(newsItemId)
    try {
      const created = await api.generateScript(newsItemId, force)
      setScriptId(created.id)
      script.refresh()
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Falha ao gerar o roteiro')
    }
  }

  // O chat pode executar ações (buscar, gerar roteiro, refazer B-roll, salvar orientação): a tela segue o resultado.
  const applyChatActions = (actions: ChatAction[]) => {
    for (const a of actions.filter((x) => x.status === 'done')) {
      const { search_id, news_item_id, script_id } = a.refs
      if (a.type === 'search_news') {
        setItemId(null)
        setScriptId(null)
        setSearchId(search_id)
      } else if (a.type === 'generate_script') {
        if (search_id && search_id !== searchId) setSearchId(search_id)
        setItemId(news_item_id)
        setScriptId(script_id)
        script.refresh()
      } else if (a.type === 'rebuild_broll') {
        script.refresh()
      } else if (a.type === 'save_guideline') {
        setGuidelinesVersion((v) => v + 1)
      }
    }
  }

  const selectedItem = search.data?.items.find((i) => i.id === itemId)

  return (
    <div className="app">
      <header className="topbar">
        <h1>Gerador de Conteúdo</h1>
        <SearchBar busy={!!search.data && searchRunning(search.data)} onSearch={startSearch} />
        <button className="secondary" onClick={() => setShowGuidelines(true)}>
          Orientações
        </button>
      </header>
      {actionError && <p className="error banner">{actionError}</p>}
      {notice && (
        <p className="notice banner" role="status">
          {notice}
        </p>
      )}

      <main className="workspace">
        <section className="column news-column" aria-label="Notícias">
          <SearchHistory
            activeSearchId={searchId}
            refreshKey={search.data ? `${search.data.id}:${search.data.status}` : null}
            onOpen={openSearch}
          />
          <NewsList search={search.data} error={search.error} selectedItemId={itemId} onSelect={(id) => void generateScript(id)} />
        </section>

        <section className="column script-column" aria-label="Roteiro">
          {selectedItem && <p className="source">Notícia: {selectedItem.title}</p>}
          {script.data?.instructions && <p className="source">Pedido aplicado: {script.data.instructions}</p>}
          <ScriptView
            script={script.data}
            error={script.error}
            onChanged={(s) => {
              script.setData(s)
              script.refresh()
            }}
            onCutsChanged={(s) => script.setData(s)}
            onRetryScript={() => itemId && void generateScript(itemId, true)}
          />
        </section>

        <ChatPanel context={{ search_id: searchId, script_id: scriptId }} onActions={applyChatActions} />
      </main>
      {showGuidelines && <GuidelinesPanel refreshKey={guidelinesVersion} onClose={() => setShowGuidelines(false)} />}
    </div>
  )
}
