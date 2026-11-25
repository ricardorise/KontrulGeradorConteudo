import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ClipEditor } from './ClipEditor'

const player = { getCurrentTime: () => 30, getDuration: () => 100, seekTo: vi.fn(), playVideo: vi.fn(), pauseVideo: vi.fn(), destroy: vi.fn() }

vi.mock('./youtubeApi', () => ({
  loadYouTubeApi: () =>
    Promise.resolve({
      Player: class {
        constructor(_el: HTMLElement, opts: { events: { onReady: (e: { target: typeof player }) => void } }) {
          queueMicrotask(() => opts.events.onReady({ target: player }))
          return player as never
        }
      },
    }),
}))

test('seleção começa no trecho sugerido; duplo clique na seleção adiciona o corte', async () => {
  const onAddCut = vi.fn().mockResolvedValue(undefined)
  render(<ClipEditor videoId="dQw4w9WgXcQ" title="Review" suggestedStart={20} onAddCut={onAddCut} />)

  const start = await screen.findByRole('slider', { name: 'Início do corte' })
  expect(start).toHaveAttribute('aria-valuenow', '20')
  expect(screen.getByRole('slider', { name: 'Fim do corte' })).toHaveAttribute('aria-valuenow', '30')

  fireEvent.doubleClick(screen.getByTestId('selection'))
  await waitFor(() => expect(onAddCut).toHaveBeenCalledWith(20, 30))
  expect(await screen.findByText(/Corte adicionado/)).toBeInTheDocument()
})

test('setas ajustam as alças e o botão "agora" usa a posição do player', async () => {
  const onAddCut = vi.fn().mockResolvedValue(undefined)
  render(<ClipEditor videoId="dQw4w9WgXcQ" title="Review" suggestedStart={20} onAddCut={onAddCut} />)
  const end = await screen.findByRole('slider', { name: 'Fim do corte' })
  fireEvent.keyDown(end, { key: 'ArrowRight' })
  expect(end).toHaveAttribute('aria-valuenow', '30.5')
  fireEvent.keyDown(end, { key: 'ArrowRight', shiftKey: true })
  expect(end).toHaveAttribute('aria-valuenow', '35.5')

  await waitFor(() => expect(screen.getByText(/0:30\.0 \/ 1:40/)).toBeInTheDocument()) // posição atual vinda do player
  fireEvent.click(screen.getByRole('button', { name: /início = agora/ }))
  expect(screen.getByRole('slider', { name: 'Início do corte' })).toHaveAttribute('aria-valuenow', '30')
})

test('mostra erro do servidor ao adicionar', async () => {
  render(<ClipEditor videoId="dQw4w9WgXcQ" title="t" suggestedStart={null} onAddCut={() => Promise.reject(new Error('Este corte já está na lista.'))} />)
  await screen.findByRole('slider', { name: 'Início do corte' })
  fireEvent.click(screen.getByRole('button', { name: '+ Adicionar corte' }))
  expect(await screen.findByText('Este corte já está na lista.')).toBeInTheDocument()
})

test('duplo clique fora da seleção não adiciona corte', async () => {
  const onAddCut = vi.fn().mockResolvedValue(undefined)
  render(<ClipEditor videoId="dQw4w9WgXcQ" title="t" suggestedStart={20} onAddCut={onAddCut} />)
  await screen.findByRole('slider', { name: 'Início do corte' })
  fireEvent.doubleClick(screen.getByTestId('timeline')) // jsdom: posição 0s, fora de 20–30s
  expect(onAddCut).not.toHaveBeenCalled()
})
