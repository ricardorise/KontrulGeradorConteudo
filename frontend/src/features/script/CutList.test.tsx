import { fireEvent, render, screen } from '@testing-library/react'
import type { Script } from '../../api/types'
import { CutList } from './CutList'

const script = {
  id: 's1', title: 'Quest em oferta',
  paragraphs: [{ id: 'p1', position: 0, text: 'a', broll: [] }, { id: 'p2', position: 1, text: 'b', broll: [] }],
  cuts: [
    { id: 'c1', paragraph_id: 'p2', video_id: 'dQw4w9WgXcQ', video_url: 'https://youtu.be/dQw4w9WgXcQ', video_title: 'Review', start_seconds: 65, end_seconds: 72.5, duration: 7.5, created_at: '2026-01-01', excerpt: { id: 'e1', start: 2, end: 6, text: 'texto ligado' } },
    { id: 'c2', paragraph_id: 'p1', video_id: 'abcdefghijk', video_url: 'https://youtu.be/abcdefghijk', video_title: null, start_seconds: 5, end_seconds: 9, duration: 4, created_at: '2026-01-02', excerpt: null },
  ],
} as unknown as Script

test('lista os cortes na ordem do roteiro e remove pelo id certo', () => {
  const onDelete = vi.fn()
  render(<CutList script={script} onDelete={onDelete} />)
  expect(screen.getByText('Lista de cortes (2)')).toBeInTheDocument()
  const items = screen.getAllByRole('listitem')
  expect(items[0]).toHaveTextContent('§1')
  expect(items[0]).toHaveTextContent('0:05.0 → 0:09.0')
  expect(items[1]).toHaveTextContent('1:05.0 → 1:12.5')
  expect(items[1]).toHaveTextContent('“texto ligado”')
  fireEvent.click(screen.getByRole('button', { name: 'Remover corte 2' }))
  expect(onDelete).toHaveBeenCalledWith('c1')
})

test('sem cortes, desativa exportação e orienta o uso', () => {
  render(<CutList script={{ ...script, cuts: [] }} onDelete={() => {}} />)
  expect(screen.getByText(/duplo clique/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Baixar CSV' })).toBeDisabled()
})
