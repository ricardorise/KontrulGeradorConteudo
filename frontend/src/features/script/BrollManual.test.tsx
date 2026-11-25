import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { Broll, Paragraph } from '../../api/types'
import { BrollCard } from './BrollCard'
import { ParagraphRow } from './ParagraphRow'

const broll = (over: Partial<Broll> = {}): Broll => ({
  id: 'b1', video_url: 'https://youtu.be/dQw4w9WgXcQ', video_id: 'dQw4w9WgXcQ', start_seconds: null, title: 'Review',
  description: 'Headset em uso', justification: null, source: 'lumiere', ...over,
})
const paragraph = (broll: Broll[] = []): Paragraph => ({ id: 'p1', position: 0, text: 'Abertura do vídeo.', broll })
const rowProps = { cuts: [], onAddCut: async () => {}, onDeleteCut: () => {}, onSetCutExcerpt: async () => {}, brollStatus: 'done' as const }

describe('BrollCard: trocar e remover', () => {
  test('trocar o vídeo manda o link, abre o player para recortar e mostra o selo "escolhido por você"', async () => {
    const onReplace = vi.fn().mockResolvedValue(undefined)
    const { rerender } = render(<BrollCard broll={broll()} excerptText={null} onAddCut={async () => {}} onReplace={onReplace} />)
    expect(screen.queryByText('escolhido por você')).not.toBeInTheDocument()
    expect(screen.queryByTestId('timeline')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Trocar vídeo' }))
    fireEvent.change(screen.getByLabelText('Link do novo vídeo'), { target: { value: 'https://youtu.be/abcdefghijk?t=40' } })
    fireEvent.click(screen.getByRole('button', { name: 'Trocar' }))
    await waitFor(() => expect(onReplace).toHaveBeenCalledWith('b1', 'https://youtu.be/abcdefghijk?t=40'))
    expect(await screen.findByTestId('timeline')).toBeInTheDocument() // já abre o editor de corte

    rerender(<BrollCard broll={broll({ source: 'manual', video_id: 'abcdefghijk' })} excerptText={null} onAddCut={async () => {}} onReplace={onReplace} />)
    expect(screen.getByText('escolhido por você')).toBeInTheDocument()
  })

  test('link recusado pelo servidor mostra o motivo e mantém o formulário', async () => {
    const onReplace = vi.fn().mockRejectedValue(new Error('Cole um link válido de vídeo do YouTube'))
    render(<BrollCard broll={broll()} excerptText={null} onAddCut={async () => {}} onReplace={onReplace} />)
    fireEvent.click(screen.getByRole('button', { name: 'Trocar vídeo' }))
    fireEvent.change(screen.getByLabelText('Link do novo vídeo'), { target: { value: 'https://evil.com/x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Trocar' }))
    expect(await screen.findByText(/link válido/)).toBeInTheDocument()
    expect(screen.getByLabelText('Link do novo vídeo')).toBeInTheDocument()
    expect(screen.queryByTestId('timeline')).not.toBeInTheDocument()
  })

  test('remover chama o callback com o id; sem callbacks os botões não aparecem', () => {
    const onRemove = vi.fn()
    const { rerender } = render(<BrollCard broll={broll()} excerptText={null} onAddCut={async () => {}} onReplace={async () => {}} onRemove={onRemove} />)
    fireEvent.click(screen.getByRole('button', { name: /Remover vídeo/ }))
    expect(onRemove).toHaveBeenCalledWith('b1')
    rerender(<BrollCard broll={broll()} excerptText={null} onAddCut={async () => {}} />)
    expect(screen.queryByRole('button', { name: 'Trocar vídeo' })).not.toBeInTheDocument()
  })
})

describe('ParagraphRow: inserir vídeo e rebuscar', () => {
  test('+ Adicionar vídeo abre o campo, envia o link do parágrafo e fecha', async () => {
    const onAddBroll = vi.fn().mockResolvedValue(undefined)
    render(<ParagraphRow paragraph={paragraph()} {...rowProps} onAddBroll={onAddBroll} />)
    fireEvent.click(screen.getByRole('button', { name: '+ Adicionar vídeo' }))
    fireEvent.change(screen.getByLabelText('Link do vídeo para este parágrafo'), { target: { value: 'https://youtu.be/abcdefghijk' } })
    fireEvent.click(screen.getByRole('button', { name: 'Adicionar' }))
    await waitFor(() => expect(onAddBroll).toHaveBeenCalledWith('p1', 'https://youtu.be/abcdefghijk'))
    await waitFor(() => expect(screen.queryByLabelText('Link do vídeo para este parágrafo')).not.toBeInTheDocument())
  })

  test('vídeo recém-inserido abre direto no player de corte', () => {
    render(<ParagraphRow paragraph={paragraph([broll({ id: 'novo', source: 'manual' })])} {...rowProps} autoOpenBrollId="novo" />)
    expect(screen.getByTestId('timeline')).toBeInTheDocument()
  })

  test('rebuscar só este parágrafo; no modo de seleção vira uma caixa de marcação', () => {
    const onRetry = vi.fn()
    const onToggle = vi.fn()
    const { rerender } = render(<ParagraphRow paragraph={paragraph()} {...rowProps} onRetryParagraph={onRetry} />)
    fireEvent.click(screen.getByRole('button', { name: /Rebuscar este/ }))
    expect(onRetry).toHaveBeenCalledWith('p1')

    rerender(<ParagraphRow paragraph={paragraph()} {...rowProps} onRetryParagraph={onRetry} selecting selected={false} onToggleSelect={onToggle} />)
    expect(screen.queryByRole('button', { name: /Rebuscar este/ })).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Rebuscar o parágrafo 1'))
    expect(onToggle).toHaveBeenCalledWith('p1')
  })

  test('com a busca em andamento o atalho "rebuscar este" fica desativado', () => {
    render(<ParagraphRow paragraph={paragraph()} {...rowProps} onRetryParagraph={() => {}} retryDisabled />)
    expect(screen.getByRole('button', { name: /Rebuscar este/ })).toBeDisabled()
  })
})
