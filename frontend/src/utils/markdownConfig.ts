import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import type Token from 'markdown-it/lib/token.mjs'
import type StateCore from 'markdown-it/lib/rules_core/state_core.mjs'

const STEP_RE = /Step\s*(\d{1,2})(?:\s*（[^）]*）|\s*\([^)]*\))?/g
const GAP_RE = /\[缺\]/g
const CITE_RE = /\[([SMDK])(\d{1,3})\]/g

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function transformText(raw: string): { html: string; changed: boolean } {
  let changed = false
  let out = ''
  let cursor = 0

  type Match = { start: number; end: number; replacement: string }
  const matches: Match[] = []

  let m: RegExpExecArray | null
  STEP_RE.lastIndex = 0
  while ((m = STEP_RE.exec(raw)) !== null) {
    const stepNum = m[1]
    const label = escapeHtml(m[0])
    matches.push({
      start: m.index,
      end: m.index + m[0].length,
      replacement: `<button type="button" data-ef-step="${stepNum}">${label}</button>`,
    })
  }

  GAP_RE.lastIndex = 0
  while ((m = GAP_RE.exec(raw)) !== null) {
    matches.push({
      start: m.index,
      end: m.index + m[0].length,
      replacement: '<span data-ef-gap-badge>缺</span>',
    })
  }

  CITE_RE.lastIndex = 0
  while ((m = CITE_RE.exec(raw)) !== null) {
    const refId = `${m[1]}${m[2]}`
    const label = escapeHtml(m[0])
    matches.push({
      start: m.index,
      end: m.index + m[0].length,
      replacement: `<span data-ef-cite="${refId}" tabindex="0">${label}</span>`,
    })
  }

  if (matches.length === 0) return { html: raw, changed: false }

  matches.sort((a, b) => a.start - b.start)
  const filtered: Match[] = []
  for (const item of matches) {
    if (filtered.length === 0 || item.start >= filtered[filtered.length - 1].end) {
      filtered.push(item)
    }
  }

  for (const item of filtered) {
    if (item.start > cursor) out += escapeHtml(raw.slice(cursor, item.start))
    out += item.replacement
    cursor = item.end
    changed = true
  }
  if (cursor < raw.length) out += escapeHtml(raw.slice(cursor))

  return { html: out, changed }
}

function efTagsRule(state: StateCore): void {
  const blockTokens = state.tokens
  for (const blockToken of blockTokens) {
    if (blockToken.type !== 'inline' || !blockToken.children) continue
    const children = blockToken.children
    const next: Token[] = []
    for (const child of children) {
      if (child.type !== 'text') {
        next.push(child)
        continue
      }
      const result = transformText(child.content)
      if (!result.changed) {
        next.push(child)
        continue
      }
      const html = new state.Token('html_inline', '', 0)
      html.content = result.html
      next.push(html)
    }
    blockToken.children = next
  }
}

export function createMarkdown(): MarkdownIt {
  const md = new MarkdownIt({ html: false, linkify: true, breaks: true })

  md.core.ruler.after('inline', 'ef-tags', efTagsRule)

  const defaultTableOpen =
    md.renderer.rules.table_open || ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))

  md.renderer.rules.table_open = (tokens, idx, options, env, self) => {
    const inner = defaultTableOpen(tokens, idx, options, env, self)
    return `<div class="ef-md-table-wrap">${inner}`
  }
  md.renderer.rules.table_close = (_tokens, _idx, _options, _env, _self) => {
    return `</table></div>`
  }

  return md
}

export function renderSafe(md: MarkdownIt, source: string): string {
  if (!source) return ''
  const raw = md.render(source)
  return DOMPurify.sanitize(raw, {
    ADD_ATTR: ['data-ef-step', 'data-ef-gap-badge', 'data-ef-cite', 'tabindex', 'class'],
    ADD_TAGS: ['button', 'span'],
  })
}
