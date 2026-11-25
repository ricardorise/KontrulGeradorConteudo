import { act, renderHook } from '@testing-library/react'
import { usePolling } from './usePolling'

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

const flush = async (ms = 0) => {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

test('continua consultando em ritmo lento depois de concluído (idle)', async () => {
  const fetcher = vi.fn().mockResolvedValue({ done: true })
  renderHook(() => usePolling('k', fetcher, () => false, 1000, 5000))
  await flush()
  expect(fetcher).toHaveBeenCalledTimes(1)
  await flush(5000)
  await flush(5000)
  expect(fetcher).toHaveBeenCalledTimes(3)
})

test('sem idle, para ao concluir; refresh() retoma e não apaga os dados da tela', async () => {
  let pending = false
  const fetcher = vi.fn(async () => ({ pending }))
  const { result } = renderHook(() => usePolling('k', fetcher, (d) => d.pending, 1000))
  await flush()
  expect(result.current.data).toEqual({ pending: false })
  await flush(5000)
  expect(fetcher).toHaveBeenCalledTimes(1) // parou

  pending = true
  await act(async () => result.current.refresh())
  await flush()
  expect(result.current.data).toEqual({ pending: true }) // dados nunca ficaram nulos no meio
  pending = false
  await flush(1000)
  expect(result.current.data).toEqual({ pending: false })
})

test('não consulta com a aba oculta e atualiza ao voltar ao foco', async () => {
  const fetcher = vi.fn().mockResolvedValue(1)
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
  renderHook(() => usePolling('k', fetcher, () => true, 1000))
  await flush(3000)
  expect(fetcher).not.toHaveBeenCalled()
  hidden.mockReturnValue(false)
  await act(async () => {
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await flush()
  expect(fetcher).toHaveBeenCalledTimes(1)
  hidden.mockRestore()
})

test('troca de key recomeça do zero e key nula desliga', async () => {
  const fetcher = vi.fn(async () => 'x')
  const { result, rerender } = renderHook(({ k }: { k: string | null }) => usePolling(k, fetcher, () => false, 1000), {
    initialProps: { k: 'a' as string | null },
  })
  await flush()
  expect(result.current.data).toBe('x')
  rerender({ k: null })
  expect(result.current.data).toBeNull()
  await flush(3000)
  expect(fetcher).toHaveBeenCalledTimes(1)
})
