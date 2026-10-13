/** Incremental SSE parser: CRLF may be split across arbitrary network chunks. */
export interface SseFrame { event: string; data: string }

export function createSseParser(emit: (frame: SseFrame) => void) {
  let line = ''
  let event = ''
  let data: string[] = []
  let skipNextLf = false
  const MAX_LINE_LENGTH = 128 * 1024

  function completeLine() {
    const current = line
    line = ''
    if (!current) {
      if (data.length) emit({ event: event || 'message', data: data.join('\n') })
      event = ''
      data = []
      return
    }
    if (current.startsWith(':')) return
    const separator = current.indexOf(':')
    const field = separator < 0 ? current : current.slice(0, separator)
    let value = separator < 0 ? '' : current.slice(separator + 1)
    if (value.startsWith(' ')) value = value.slice(1)
    if (field === 'event') event = value
    if (field === 'data') data.push(value)
  }

  return {
    feed(fragment: string) {
      for (const char of fragment) {
        if (skipNextLf) {
          skipNextLf = false
          if (char === '\n') continue
        }
        if (char === '\r') {
          completeLine()
          skipNextLf = true
        } else if (char === '\n') {
          completeLine()
        } else {
          line += char
          if (line.length > MAX_LINE_LENGTH) throw new Error('SSE event line too large')
        }
      }
    },
  }
}
