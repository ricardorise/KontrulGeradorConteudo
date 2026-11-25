import { fireEvent, render, screen } from '@testing-library/react'
import type { NewsSearch } from '../../api/types'
import { NewsList } from './NewsList'

const base: NewsSearch = {
  id: 's1', topic: 'Meta Quest', status: 'done', error: null, instructions: null, created_at: '2026-11-23T00:00:00Z', finished_at: null,
  items: [
    { id: 'n1', position: 0, title: 'Quest em promoção', summary: 'Preço caiu.', details: null, source_url: null, published_at: '2026-11-20' },
    { id: 'n2', position: 1, title: 'Novo menu', summary: 'Navigator.', details: null, source_url: null, published_at: null },
  ],
}

test('lista título e descrição e dispara seleção ao clicar', () => {
  const onSelect = vi.fn()
  render(<NewsList search={base} error={null} selectedItemId={null} onSelect={onSelect} />)
  expect(screen.getByText('Preço caiu.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /Novo menu/ }))
  expect(onSelect).toHaveBeenCalledWith('n2')
})

test('mostra carregando enquanto o Tonton busca', () => {
  render(<NewsList search={{ ...base, status: 'running', items: [] }} error={null} selectedItemId={null} onSelect={() => {}} />)
  expect(screen.getByRole('status')).toHaveTextContent('Tonton')
})

test('mostra erro da busca', () => {
  render(<NewsList search={{ ...base, status: 'failed', error: 'timeout', items: [] }} error={null} selectedItemId={null} onSelect={() => {}} />)
  expect(screen.getByText(/timeout/)).toBeInTheDocument()
})

test('Radar mostra síntese e expande evidências sem disparar geração de roteiro', () => {
  const onSelect = vi.fn()
  const item = { ...base.items[0], details: 'Contexto para roteiro', radar: { status: 'EMERGING', velocity: 'Alta', why_now: 'Aceleração em duas fontes', evidence: ['Dado confirmado em 24h'], sources: ['https://example.com/fonte'], divergences: 'Views ainda não confirmadas' } }
  render(<NewsList search={{ ...base, items: [item] }} error={null} selectedItemId={null} onSelect={onSelect} />)
  expect(screen.getByText('EMERGING')).toBeInTheDocument()
  expect(screen.getByText('Aceleração em duas fontes')).toBeInTheDocument()
  fireEvent.click(screen.getByText('Ver análise, evidências e fontes'))
  expect(screen.getByText('Dado confirmado em 24h')).toBeInTheDocument()
  expect(screen.getByRole('link')).toHaveAttribute('href', 'https://example.com/fonte')
  expect(onSelect).not.toHaveBeenCalled()
})

test('mostra rank separado da classificação e a janela UTC registrada', () => {
  render(<NewsList search={{ ...base, report_context: {policy:'vrxr-cross-sources-v1',scope:'VR/XR',window_hours:72,window_start:'2026-11-20T14:30:00Z',window_end:'2026-11-23T14:30:00Z',coverage:{tonton:'respondeu',youtoba:'indisponível'}} }} error={null} selectedItemId={null} onSelect={() => {}} />)
  expect(screen.getByText('#1')).toBeInTheDocument()
  expect(screen.getByText(/RADAR DE TENDÊNCIAS — VR\/XR/)).toBeInTheDocument()
  expect(screen.getByText(/20\/11\/2026/)).toBeInTheDocument()
})
