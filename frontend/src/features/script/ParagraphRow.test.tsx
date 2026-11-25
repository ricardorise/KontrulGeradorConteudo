import { render, screen } from '@testing-library/react'
import type { Paragraph } from '../../api/types'
import { ParagraphRow } from './ParagraphRow'

const paragraph: Paragraph = {
  id: 'p1', position: 0, text: 'Abertura do vídeo.',
  broll: [{ id: 'b1', video_url: 'https://youtu.be/dQw4w9WgXcQ?t=65', video_id: 'dQw4w9WgXcQ', start_seconds: 65, title: 'Review', description: 'Headset em uso', justification: 'Mostra o produto', source: 'lumiere' as const }],
}

test('exibe o parágrafo ao lado do B-roll com link no timestamp', () => {
  render(<ParagraphRow paragraph={paragraph} cuts={[]} onAddCut={async () => {}} onDeleteCut={() => {}} onSetCutExcerpt={async () => {}} brollStatus="done" />)
  expect(screen.getByText(/Abertura do vídeo/)).toBeInTheDocument()
  expect(screen.getByText('Headset em uso')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /1:05/ })).toHaveAttribute('href', 'https://youtu.be/dQw4w9WgXcQ?t=65')
})

test('indica busca em andamento e ausência de cenas', () => {
  const empty = { ...paragraph, broll: [] }
  const { rerender } = render(<ParagraphRow paragraph={empty} cuts={[]} onAddCut={async () => {}} onDeleteCut={() => {}} onSetCutExcerpt={async () => {}} brollStatus="running" />)
  expect(screen.getByText(/Lumière buscando/)).toBeInTheDocument()
  rerender(<ParagraphRow paragraph={empty} cuts={[]} onAddCut={async () => {}} onDeleteCut={() => {}} onSetCutExcerpt={async () => {}} brollStatus="done" />)
  expect(screen.getByText(/Nenhuma cena confiável/)).toBeInTheDocument()
})

test('o clique usa o horário estruturado mesmo quando a URL original não o contém', async () => {
  const { fireEvent } = await import('@testing-library/react')
  render(<ParagraphRow paragraph={{ ...paragraph, broll: [{ ...paragraph.broll[0], video_url: 'https://youtu.be/dQw4w9WgXcQ' }] }} cuts={[]} onAddCut={async () => {}} onDeleteCut={() => {}} onSetCutExcerpt={async () => {}} brollStatus="done" />)
  expect(screen.getByRole('link', { name: /1:05/ })).toHaveAttribute('href', 'https://youtu.be/dQw4w9WgXcQ?t=65')
  fireEvent.click(screen.getByRole('button', { name: /Abrir player e cortar/ }))
  expect(screen.getByTestId('timeline')).toBeInTheDocument() // o player abre com a timeline de cortes
})

test('mostra trecho ligado a um corte e destaca no texto', () => {
  const cut = {
    id: 'c1', paragraph_id: 'p1', video_id: 'dQw4w9WgXcQ', video_url: 'https://youtu.be/dQw4w9WgXcQ', video_title: null,
    start_seconds: 5, end_seconds: 9, duration: 4, created_at: '', excerpt: { id: 'e1', start: 0, end: 8, text: 'Abertura' },
  }
  const { container } = render(<ParagraphRow paragraph={paragraph} cuts={[cut]} onAddCut={async () => {}} onDeleteCut={() => {}} onSetCutExcerpt={async () => {}} brollStatus="done" />)
  expect(container.querySelector('mark.excerpt.linked')).toHaveTextContent('Abertura')
  expect(screen.getByText(/✂/)).toHaveAttribute('title', 'Trecho: Abertura')
})

test('corte sem trecho mostra aviso e o ✎ só habilita com texto selecionado', () => {
  const cut = {
    id: 'c1', paragraph_id: 'p1', video_id: 'dQw4w9WgXcQ', video_url: 'https://youtu.be/dQw4w9WgXcQ', video_title: null,
    start_seconds: 5, end_seconds: 9, duration: 4, created_at: '', excerpt: null,
  }
  render(<ParagraphRow paragraph={paragraph} cuts={[cut]} onAddCut={async () => {}} onDeleteCut={() => {}} onSetCutExcerpt={async () => {}} brollStatus="done" />)
  expect(screen.getByText('sem trecho')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Usar o texto selecionado neste corte' })).toBeDisabled()
})
