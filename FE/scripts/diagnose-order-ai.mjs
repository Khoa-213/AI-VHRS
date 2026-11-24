// Step-by-step check of the order assistant against a REAL backend, to tell WHICH part fails (no browser, no UI).
//
//   VHRS_EMAIL=you@example.com VHRS_PASSWORD=... node scripts/diagnose-order-ai.mjs
//
// Optional:
//   VHRS_API=https://ai-vhrs.onrender.com/api/v1   backend to test (default: the Render deployment)
//   VHRS_WITH_LLM=1                                also sends ONE chat message (calls the real AI provider, uses today's quota)
//
// It signs in as a customer, creates a throw-away DRAFT, runs the steps below, then deletes the draft.
// The password is read from the environment only and is never printed; tokens are never printed.
// Each step prints PASS / FAIL with the HTTP status, the backend error code and message, so the output can be pasted for help.
import assert from 'node:assert/strict'
import { randomUUID } from 'node:crypto'

const API = (process.env.VHRS_API || 'https://ai-vhrs.onrender.com/api/v1').replace(/\/$/, '')
const EMAIL = process.env.VHRS_EMAIL
const PASSWORD = process.env.VHRS_PASSWORD
const WITH_LLM = process.env.VHRS_WITH_LLM === '1'
assert.ok(EMAIL && PASSWORD, 'Set VHRS_EMAIL and VHRS_PASSWORD (a customer account)')

let token = ''
let failures = 0
const started = Date.now()

/** One request. Returns { status, ok, data, bytes, rid } and never throws on an HTTP error. */
async function call(method, path, body, { raw = false } = {}) {
  const t0 = Date.now()
  let res
  try {
    res = await fetch(API + path, {
      method,
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(120_000),
    })
  } catch (e) {
    return { status: 0, ok: false, data: { error: { code: 'NETWORK', message: String(e.cause?.message || e.message) } }, ms: Date.now() - t0 }
  }
  const rid = res.headers.get('x-request-id') || res.headers.get('x-render-request-id') || ''
  if (raw) {
    const buf = Buffer.from(await res.arrayBuffer())
    return { status: res.status, ok: res.ok, bytes: buf.length, type: res.headers.get('content-type'), data: res.ok ? null : safeJson(buf.toString('utf8')), rid, ms: Date.now() - t0 }
  }
  const text = await res.text()
  return { status: res.status, ok: res.ok, data: safeJson(text), rid, ms: Date.now() - t0 }
}
const safeJson = (s) => { try { return s ? JSON.parse(s) : null } catch { return { error: { code: 'NOT_JSON', message: String(s).slice(0, 200) } } } }

function show(name, r, extra = '') {
  const err = r.data?.error
  const line = `${r.ok ? 'PASS' : 'FAIL'}  ${name}  [${r.status || 'no response'}] ${r.ms}ms${extra ? '  ' + extra : ''}`
  console.log(line)
  if (!r.ok) {
    failures += 1
    console.log(`      code=${err?.code ?? '?'}  message=${err?.message ?? JSON.stringify(r.data)?.slice(0, 200)}`)
    if (err?.details) console.log(`      details=${JSON.stringify(err.details).slice(0, 300)}`)
    if (r.rid) console.log(`      request-id=${r.rid}  (give this to the backend owner to find the server log)`)
    const hint = HINTS[err?.code]
    if (hint) console.log(`      => ${hint}`)
  }
}

// What a backend code usually means, so the output points at the owner of the problem.
const HINTS = {
  NETWORK: 'No answer: wrong VHRS_API, no internet, or the free Render plan is waking up (retry in a minute).',
  INVALID_CREDENTIALS: 'Wrong email or password.',
  STORAGE_UNAVAILABLE: 'BACKEND/RENDER: Supabase Storage cannot be reached or refuses the key (SUPABASE_URL, SUPABASE_SERVICE_KEY, bucket).',
  STORAGE_NOT_CONFIGURED: 'BACKEND/RENDER: SUPABASE_URL / SUPABASE_SERVICE_KEY are not set.',
  AI_UNAVAILABLE: 'BACKEND/RENDER: no AI provider has both its API key and its model name set.',
  AI_DISABLED: 'BACKEND: the admin setting ai_assistant_enabled is off.',
  AI_BUDGET_EXHAUSTED: 'BACKEND: the daily model-call or cost cap is used up (admin settings).',
  AI_DAILY_LIMIT: 'This customer used all of today\'s messages.',
  AI_CONSENT_REQUIRED: 'FE bug if it appears: the first message must carry ai_consent=true.',
  ORDER_TYPE_SUSPENDED: 'BACKEND: this order type is switched off by the workshop.',
  PRIVACY_REQUIRED: 'The account has not accepted the privacy policy yet (do it once in the web app).',
  SKETCH_OUTDATED: 'The text changed after drawing; draw again.',
  RATE_LIMITED: 'Too many requests; wait a minute.',
}

let orderId = null
try {
  console.log(`Backend: ${API}\n`)

  // 1. Is the backend up? (a sleeping Render instance may need up to a minute)
  let r = await call('GET', '/health')
  show('1  backend answers', r)
  if (!r.ok) throw new Error('Backend is not reachable: stopping.')

  // 2. Sign in.
  r = await call('POST', '/auth/login', { email: EMAIL, password: PASSWORD })
  show('2  sign in as a customer', r, r.ok ? `role=${r.data.account?.role}` : '')
  if (!r.ok) throw new Error('Cannot sign in: stopping.')
  token = r.data.access_token
  assert.equal(r.data.account?.role, 'CUSTOMER', 'The account must be a CUSTOMER')

  // 3. The assistant status (this is what turns the "Use the AI assistant" choice on).
  r = await call('GET', '/studio/assistant/status')
  const st = r.data || {}
  show('3  assistant status', r, r.ok ? `enabled=${st.enabled} available=${st.available} providers=[${(st.providers || []).join(', ')}] left=${st.messages_left_today}/${st.daily_message_limit}` : '')
  if (r.ok && !st.enabled) console.log('      => BACKEND: ai_assistant_enabled is off (admin setting).')
  if (r.ok && st.enabled && !st.available) console.log('      => BACKEND/RENDER: no provider has key AND model set.')

  // 4. The catalog the draft needs.
  r = await call('GET', '/catalog/templates')
  const tpl = Array.isArray(r.data) ? r.data[0] : null
  show('4  catalog: handwriting styles', r, tpl ? `first style id=${tpl.id}` : 'none')
  if (!tpl) throw new Error('No handwriting style: stopping.')

  // 5. A throw-away draft.
  r = await call('POST', '/orders', { order_type: 'OT3_TEMPLATE', quantity: 1 })
  show('5  create a draft order', r, r.ok ? `id=${r.data.id}` : '')
  if (!r.ok) throw new Error('Cannot create a draft: stopping.')
  orderId = r.data.id

  // 6. Text (needed before a sketch).
  r = await call('PUT', `/orders/${orderId}/inputs/text`, { text_content: 'Chúc mừng sinh nhật mẹ', template_id: tpl.id })
  show('6  save the text', r)

  // 7. THE STORAGE CHECK: drawing the sketch writes files to Supabase Storage. No AI is used here.
  r = await call('POST', `/orders/${orderId}/sketch/generate`, {})
  show('7  draw the sketch (needs file storage, no AI)', r, r.ok ? `revision=${r.data.revision?.id} pages=${r.data.document?.pages?.length}` : '')
  const drawn = r.ok

  if (drawn) {
    r = await call('GET', `/orders/${orderId}/sketch`)
    const words = (r.data?.document?.pages || []).reduce((n, p) => n + (p.words?.length || 0), 0)
    show('8  read the sketch (document for the picker)', r, r.ok ? `words=${words} lines=${r.data.document.pages[0]?.lines?.length ?? 'missing'} paragraphs=${r.data.document.pages[0]?.paragraphs?.length ?? 'missing'}` : '')

    r = await call('GET', `/orders/${orderId}/sketch/preview?page=1`, undefined, { raw: true })
    show('9  sketch picture (JPEG)', r, r.ok ? `${r.bytes} bytes, ${r.type}` : '')
  } else {
    console.log('SKIP  8, 9  (no sketch to read)')
  }

  // 10. The conversation endpoint (empty before the first message).
  r = await call('GET', `/orders/${orderId}/assistant/messages`)
  show('10 read the conversation', r, r.ok ? `messages=${r.data.messages?.length} proposals=${r.data.proposals?.length}` : '')

  // 11. One real chat turn (calls the AI provider).
  if (!WITH_LLM) {
    console.log('SKIP  11 chat turn  (set VHRS_WITH_LLM=1 to send ONE real message; it calls the AI provider)')
  } else {
    r = await call('POST', `/orders/${orderId}/assistant/messages`, {
      text: 'Viết lời chúc sinh nhật ngắn cho mẹ', ai_consent: true, client_ref: randomUUID(),
    })
    const reply = r.data?.reply
    const p = r.data?.proposal
    show('11 chat turn', r, r.ok ? `reply.status=${reply?.status} tools=[${(reply?.tool_calls || []).map((c) => `${c.name}${c.ok ? '' : '(failed)'}`).join(', ')}]` : '')
    if (r.ok && reply?.status === 'FAILED') {
      failures += 1
      console.log('      => FAIL: every AI provider failed (bad key, wrong model name, quota or timeout). The BE answers 200 with status FAILED.')
    }
    if (r.ok && reply?.status !== 'FAILED') {
      console.log(`      proposal: ${p ? `id=${p.id} fields=[${p.changes.map((c) => c.field).join(', ')}] estimate=${JSON.stringify(p.estimate)} preview=${p.preview ? `pages=${p.preview.pages}` : 'null'}` : 'none'}`)
      if (p && !p.preview) console.log('      => the proposal has NO picture (BE could not draw: check step 7 / storage).')
      if (p && !p.changes.some((c) => c.field === 'sketch')) console.log('      => the proposal does not draw a new sketch (fine if the sketch of step 7 is current).')
      if (p?.preview) {
        const pr = await call('GET', `${p.preview.preview_url.replace(/^\/api\/v1/, '')}?page=1`, undefined, { raw: true })
        show('12 proposal picture', pr, pr.ok ? `${pr.bytes} bytes, ${pr.type}` : '')
      }
      if (p) {
        const rj = await call('POST', `/orders/${orderId}/assistant/proposals/${p.id}/reject`, {})
        show('13 skip the proposal (reject)', rj, rj.ok ? `status=${rj.data.status}` : '')
      }
    }
  }
} catch (e) {
  console.log(`\nStopped: ${e.message}`)
  failures += 1
} finally {
  if (orderId !== null) {
    const r = await call('DELETE', `/orders/${orderId}`)
    console.log(`\ncleanup: delete draft ${orderId} -> ${r.status}`)
  }
  console.log(`\n${failures ? `${failures} step(s) failed` : 'All steps passed'} in ${Math.round((Date.now() - started) / 1000)}s`)
  process.exitCode = failures ? 1 : 0
}
