/**
 * Small, dependency-free Markdown subset for model output.
 * All content is HTML escaped before any of our own static markup is inserted.
 * Raw HTML, embedded images and arbitrary URLs are deliberately unsupported.
 */
export function escapeHtml(value: string): string {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;').replace(/'/g, '&#39;')
}

function inline(text: string): string {
  return escapeHtml(text)
    .replace(/\x60([^\x60]+)\x60/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, '<em>$1</em>')
}

export function renderSafeMarkdown(input: string): string {
  const lines = input.replace(/\r\n?/g, '\n').split('\n')
  const html: string[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i] ?? ''
    if (!line.trim()) { i++; continue }
    const fence = line.match(/^\s*\x60{3}([\w+#.-]*)/)
    if (fence) {
      const code: string[] = []
      i++
      while (i < lines.length && !/^\s*\x60{3}\s*$/.test(lines[i] ?? '')) {
        code.push(lines[i] ?? ''); i++
      }
      if (i < lines.length) i++
      html.push('<pre class="markdown-code"><code>' + escapeHtml(code.join('\n')) + '</code></pre>')
      continue
    }
    const heading = line.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      const level = Math.min(heading[1]!.length + 1, 5)
      html.push('<h' + level + '>' + inline(heading[2]!) + '</h' + level + '>')
      i++; continue
    }
    if (/^\s*\|/.test(line) && i + 1 < lines.length &&
        /^\s*\|?[\s:|-]+\|?\s*$/.test(lines[i + 1] ?? '') &&
        (lines[i + 1] ?? '').includes('-')) {
      const cells = (row: string) => row.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim())
      html.push('<div class="markdown-table-wrap"><table><thead><tr>' + cells(line).map(c => '<th>' + inline(c) + '</th>').join('') + '</tr></thead><tbody>')
      i += 2
      while (i < lines.length && /^\s*\|/.test(lines[i] ?? '')) {
        html.push('<tr>' + cells(lines[i]!).map(c => '<td>' + inline(c) + '</td>').join('') + '</tr>')
        i++
      }
      html.push('</tbody></table></div>')
      continue
    }
    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
      const ordered = /^\s*\d+[.)]\s+/.test(line)
      const tag = ordered ? 'ol' : 'ul'
      html.push('<' + tag + '>')
      while (i < lines.length && (ordered ? /^\s*\d+[.)]\s+/.test(lines[i] ?? '') : /^\s*[-*]\s+/.test(lines[i] ?? ''))) {
        html.push('<li>' + inline((lines[i] ?? '').replace(/^\s*(?:[-*]|\d+[.)])\s+/, '')) + '</li>')
        i++
      }
      html.push('</' + tag + '>')
      continue
    }
    if (/^\s*>\s?/.test(line)) {
      html.push('<blockquote>' + inline(line.replace(/^\s*>\s?/, '')) + '</blockquote>')
      i++; continue
    }
    const paragraph: string[] = []
    while (i < lines.length && (lines[i] ?? '').trim() &&
      !/^(#{1,4})\s+/.test(lines[i] ?? '') && !/^\s*\x60{3}/.test(lines[i] ?? '') &&
      !/^\s*[-*]\s+/.test(lines[i] ?? '') && !/^\s*\d+[.)]\s+/.test(lines[i] ?? '')) {
      paragraph.push(inline(lines[i] ?? '')); i++
    }
    if (paragraph.length) html.push('<p>' + paragraph.join('<br>') + '</p>')
  }
  return html.join('')
}
