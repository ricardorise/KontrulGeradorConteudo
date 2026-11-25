import { buildSegments, overlaps, trimRange } from './textSelection'

test('detecta sobreposição (trechos adjacentes não conflitam)', () => {
  expect(overlaps({ start: 0, end: 5 }, { start: 3, end: 8 })).toBe(true)
  expect(overlaps({ start: 0, end: 5 }, { start: 5, end: 9 })).toBe(false)
})

test('remove espaços das pontas da seleção', () => {
  expect(trimRange('abc  def ghi', { start: 3, end: 9 })).toEqual({ start: 5, end: 8 })
  expect(trimRange('a   b', { start: 1, end: 4 })).toBeNull()
})

test('divide o texto em pedaços normal, ligado e pendente', () => {
  const segs = buildSegments('Se você segurou a carteira', [{ start: 0, end: 2, title: 'corte 1' }], { start: 3, end: 7 })
  expect(segs.map((s) => [s.kind, s.text])).toEqual([
    ['linked', 'Se'],
    ['plain', ' '],
    ['pending', 'você'],
    ['plain', ' segurou a carteira'],
  ])
})

test('seleção pendente que sobrepõe um trecho ligado é ignorada', () => {
  const segs = buildSegments('abcdefghij', [{ start: 0, end: 5 }], { start: 3, end: 8 })
  expect(segs.some((s) => s.kind === 'pending')).toBe(false)
})
