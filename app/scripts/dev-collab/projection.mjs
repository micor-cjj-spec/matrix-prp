import { renderBoard } from './board.mjs'

const ACTOR = 'github-actions[bot]'
const REQ = /^REQ-[0-9]{8}-[0-9]{3}$/

export function renderProjection(snapshot, stateSha) {
  if (!REQ.test(snapshot?.requirement_id)) throw new Error('INVALID_REQUIREMENT_ID')
  if (!/^[a-f0-9]{40}$/.test(stateSha)) throw new Error('INVALID_STATE_SHA')
  return `<!-- prp-collab-board:${snapshot.requirement_id} -->
<!-- prp-collab-version:${snapshot.version} -->
${renderBoard(snapshot,{state_sha:stateSha})}
_This automated GitHub comment is a read-only projection. The protected state ref, not the Issue comment, is authoritative._
`
}

export function chooseProjection(comments, requirementId, version, body) {
  if (!REQ.test(requirementId)) throw new Error('INVALID_REQUIREMENT_ID')
  if (!Array.isArray(comments)) throw new Error('INVALID_COMMENTS')
  const marker = `<!-- prp-collab-board:${requirementId} -->`
  const matching = comments.filter(c => c && c.user?.login === ACTOR &&
    typeof c.body === 'string' && c.body.startsWith(marker))
  if (matching.length > 1) throw new Error('AMBIGUOUS_PROJECTION_COMMENTS')
  if (!matching.length) return { action: 'create' }
  const item=matching[0]
  if (!Number.isSafeInteger(item.id) || item.id<=0) throw new Error('INVALID_PROJECTION_ID')
  const match=item.body.match(/<!-- prp-collab-version:(\d+) -->/)
  if (!match) throw new Error('INVALID_PROJECTION_VERSION')
  if (Number(match[1])>version) throw new Error('STALE_PROJECTION_ATTEMPT')
  if (item.body===body) return { action:'unchanged', id:item.id }
  return { action:'update', id:item.id }
}
