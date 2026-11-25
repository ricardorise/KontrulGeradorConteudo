import { embedUrl, formatTimestamp } from './youtube'

test('formata timestamps', () => {
  expect(formatTimestamp(null)).toBeNull()
  expect(formatTimestamp(5)).toBe('0:05')
  expect(formatTimestamp(125)).toBe('2:05')
  expect(formatTimestamp(3725)).toBe('1:02:05')
})

test('embed usa youtube-nocookie e o início', () => {
  expect(embedUrl('abc', 30)).toContain('youtube-nocookie.com/embed/abc')
  expect(embedUrl('abc', 30)).toContain('start=30')
  expect(embedUrl('abc', null)).not.toContain('start=')
})
