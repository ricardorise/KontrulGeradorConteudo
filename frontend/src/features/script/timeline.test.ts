import { clamp, formatClock, initialSelection, timeFromPointer, withEnd, withStart } from './timeline'

test('converte posição do ponteiro em segundos com limites', () => {
  expect(timeFromPointer(150, 100, 200, 100)).toBe(25)
  expect(timeFromPointer(50, 100, 200, 100)).toBe(0)
  expect(timeFromPointer(999, 100, 200, 100)).toBe(100)
  expect(timeFromPointer(150, 100, 0, 100)).toBe(0)
})

test('início e fim nunca se cruzam e respeitam a duração', () => {
  const sel = { start: 10, end: 20 }
  expect(withStart(sel, 25)).toEqual({ start: 19.5, end: 20 })
  expect(withStart(sel, -3)).toEqual({ start: 0, end: 20 })
  expect(withEnd(sel, 5, 60)).toEqual({ start: 10, end: 10.5 })
  expect(withEnd(sel, 999, 60)).toEqual({ start: 10, end: 60 })
})

test('seleção inicial fica dentro do vídeo', () => {
  expect(initialSelection(65, 600)).toEqual({ start: 65, end: 75 })
  expect(initialSelection(null, 600)).toEqual({ start: 0, end: 10 })
  expect(initialSelection(598, 600)).toEqual({ start: 598, end: 600 })
  expect(initialSelection(900, 600).end).toBe(600)
  expect(clamp(5, 0, 3)).toBe(3)
})

test('formata tempo', () => {
  expect(formatClock(65.5)).toBe('1:05.5')
  expect(formatClock(3725.04)).toBe('1:02:05.0')
  expect(formatClock(0.4)).toBe('0:00.4')
})
