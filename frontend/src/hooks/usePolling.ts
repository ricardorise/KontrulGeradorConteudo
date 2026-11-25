import { useEffect, useRef, useState } from 'react'

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b)

/**
 * Mantém `data` sempre atualizado a partir de `fetcher()`:
 * - repete a cada `intervalMs` enquanto `shouldContinue(dado)` for verdadeiro;
 * - depois disso continua a cada `idleMs` (se informado), para a tela nunca ficar desatualizada;
 * - pausa com a aba oculta e atualiza na hora quando ela volta ao foco;
 * - `refresh()` busca agora e retoma o ciclo, sem apagar o que já está na tela.
 * Recomeça do zero quando `key` muda; `key = null` desliga.
 */
export function usePolling<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  shouldContinue: (data: T) => boolean,
  intervalMs = 2500,
  idleMs?: number,
) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const latest = useRef({ fetcher, shouldContinue })
  latest.current = { fetcher, shouldContinue }
  const trigger = useRef<() => void>(() => undefined)

  useEffect(() => {
    setData(null)
    setError(null)
    trigger.current = () => undefined
    if (key === null) return
    let cancelled = false
    let inflight = false
    let timer: ReturnType<typeof setTimeout> | undefined

    const schedule = (ms: number | undefined) => {
      if (timer) clearTimeout(timer)
      timer = ms === undefined ? undefined : setTimeout(() => void run(), ms)
    }

    const run = async () => {
      if (cancelled || inflight) return
      if (document.hidden) return schedule(idleMs ?? intervalMs) // pausado em segundo plano
      inflight = true
      try {
        const next = await latest.current.fetcher()
        if (cancelled) return
        setData((prev) => (same(prev, next) ? prev : next)) // sem re-render à toa
        setError(null)
        schedule(latest.current.shouldContinue(next) ? intervalMs : idleMs)
      } catch (e) {
        if (cancelled) return
        setError(e instanceof Error ? e.message : 'Falha de rede')
        schedule(intervalMs * 2) // tolera queda momentânea do backend
      } finally {
        inflight = false
      }
    }

    const onVisible = () => {
      if (!document.hidden) void run()
    }
    trigger.current = () => void run()
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)
    void run()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [key, intervalMs, idleMs])

  return { data, error, setData, refresh: () => trigger.current() }
}
