// Real Edge DOM test of the AI assistant inside Create Order, with every API call intercepted (no backend, no model, no data).
// Covers: the AI / no-AI choice, a turn that creates the draft and comes back as a PROPOSAL (order and sketch unchanged),
// apply and skip, the form locked and the order not sendable while a proposal waits, the chat at every step, picking a word on
// the sketch for the assistant (selection), "start again from the order" (from_order), the unavailable assistant, and the three
// languages. Run `npm run build` first.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const edge = process.env.TECH_BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
assert.ok(existsSync(edge), 'Set TECH_BROWSER_PATH to an installed Chromium/Edge executable')
assert.ok(existsSync(join(root, 'dist/index.html')), 'Run npm.cmd run build first')
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-order-ai-browser-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-11-21T00:00:00Z'
// A 1x1 PNG stands for every picture (template preview and sketch preview).
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
const REPLY_TEXT = 'Happy birthday, Mom!'

// ---- the fake backend: the assistant PROPOSES (BE migration 0029); the FE applies each proposal at once ----
const state = { fail: { generate: false, apply: false, turn: false, limit: false }, sketchGone: false, available: true, created: false, order: null, sketch: null, msgs: [], consented: false, left: 30, turn: 0, nextMsg: 1, proposals: {}, bodies: [], sessions: [], nextSid: 1, consents: [] }
const log = []
const newOrder = () => ({
  id: 77, code: 'VH-AI-1', order_type: 'OT3_TEMPLATE', order_status: 'DRAFT', production_status: 'NOT_STARTED',
  paper_type_id: null, pen_type_id: null, ink_color_id: null, workshop_suggest_materials: false, quantity: 1, char_count: null,
  estimated_price_min: null, estimated_price_max: null, customer_note: null, info_request_note: null, reject_reason: null, reject_note: null,
  eta: null, last_saved_at: now, submitted_at: null, created_at: now, inputs: [], warnings: [],
})
const textInput = () => ({
  id: 5, kind: 'TEXT_CONTENT', sort_order: 0, mime_type: null, file_size_bytes: null, quality_result: null, is_quality_warning: false,
  text_content: REPLY_TEXT, template_id: 1, font_size_mm: null, alignment: null, canvas_data: null,
})
const page = (no) => ({
  no, width_mm: 210, height_mm: 297,
  strokes: [{ id: `s${no}1`, kind: 'base', points: [[20, 30], [60, 32]], word: `w${no}1` }, { id: `s${no}2`, kind: 'base', points: [[70, 30], [110, 31]], word: `w${no}2` }],
  words: [
    { id: `w${no}1`, stroke_ids: [`s${no}1`], bbox: [18, 27, 62, 35], text: 'Happy' },
    { id: `w${no}2`, stroke_ids: [`s${no}2`], bbox: [68, 27, 112, 35], text: 'birthday' },
  ],
  lines: [{ id: `l${no}1`, word_ids: [`w${no}1`, `w${no}2`], bbox: [18, 27, 112, 35], paragraph: `p${no}1` }],
  paragraphs: [{ id: `p${no}1`, line_ids: [`l${no}1`], bbox: [18, 27, 112, 35] }],
})
const sketchOut = () => ({
  revision: { id: state.sketch.rev, seq: state.sketch.rev, parent_id: null, author: 'AI', note: null, created_at: now },
  is_current: true, can_undo: state.sketch.canUndo, can_redo: state.sketch.canRedo, inputs_changed: false, limits: {}, document: { pages: [page(1), page(2)] },
})
const message = (id, role, content, proposal = null) => ({ id, role, content, status: 'OK', provider: 'test', model: 'test', tool_calls: [], created_at: now, proposal })
const CHANGES = [
  { field: 'text', before: null, after: REPLY_TEXT },
  { field: 'paper_type_id', before: null, after: { id: 1, name: 'Paper A5' } },
  { field: 'ink_color_id', before: null, after: { id: 1, name: 'Black ink' } },
  { field: 'sketch', before: null, after: 11 },
]
const makeProposal = (id, messageId) => ({
  id, message_id: messageId, parent_proposal_id: null, status: 'PENDING', applicable: true, blocked_reason: null, changes: CHANGES,
  estimate: { price_min: 10000, price_max: 12000, currency: 'VND', is_estimate: true }, sketch_revision_id: 11, created_at: now, decided_at: null,
  preview: { revision_id: 11, pages: 2, preview_url: `/api/v1/orders/77/assistant/proposals/${id}/preview`, sketch_changed: true, sketch_outdated: false },
})
/** What the conversation returns: every assistant message carries its proposal as it is now. */
const conversation = (sid) => state.msgs.filter((m) => m.sid === sid).map((m) => ({ ...m, proposal: m.pid ? state.proposals[m.pid] : null }))
/** Conversations (migration 0031), the one used last first. */
const latestSession = () => [...state.sessions].sort((a, b) => b.last - a.last)[0] ?? null
const sessionItem = (x) => {
  const msgs = state.msgs.filter((m) => m.sid === x.id)
  return { id: x.id, order_id: 77, order_code: 'VH-AI-1', order_type: 'OT3_TEMPLATE', order_status: 'DRAFT', title: msgs.find((m) => m.role === 'USER')?.content ?? null,
    title_is_custom: false, preview: msgs.at(-1)?.content?.slice(0, 140) ?? null, message_count: msgs.length, created_at: now, last_message_at: now, can_chat: true, can_delete: true }
}

const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://localhost').pathname
    const target = path.startsWith('/assets/') ? join(root, 'dist', path) : join(root, 'dist/index.html')
    assert.ok(resolve(target).startsWith(resolve(root, 'dist')))
    res.setHeader('Content-Type', ({ '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' })[extname(target)] || 'text/html')
    res.end(await readFile(target))
  } catch { res.statusCode = 404; res.end() }
})
await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
const port = server.address().port
let browser, ws
const errors = []

const sse = (events) => events.map(([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`).join('')

/** The answer of the fake backend: [body, status, mime]. */
function answer(method, path, postData, search = '') {
  const body = postData ? JSON.parse(postData) : {}
  if (path === '/me') return [{ id: 17, email: 'test@example.test', full_name: 'Browser Test', role: 'CUSTOMER', status: 'ACTIVE', addresses: [], created_at: now }]
  if (path === '/privacy-policy/ai-chat') return [{ title: 'QUYỀN RIÊNG TƯ KHI SỬ DỤNG TRỢ LÝ AI', version: 'AI-1.0', body: 'Toàn văn', sections: [{ title: '1. Phạm vi hỗ trợ', body: 'Trợ lý hỗ trợ soạn nội dung.' }, { title: '2. Dữ liệu được gửi', body: 'Hệ thống gửi:\n\n- Tin nhắn\n- Nội dung đơn' }], providers: ['Anthropic (Claude)', 'Google (Gemini)'], retention_days: 90, retention_enforced: false, is_draft: false }]
  if (path === '/me/assistant/consent' && method === 'POST') { state.consents.push(body.policy_version); state.consented = true; return [{ policy_version: 'AI-1.0', accepted: true, accepted_at: now }] }
  if (path === '/studio/assistant/status') return [{ enabled: state.available, available: state.available, providers: ['test'], messages_left_today: state.left, daily_message_limit: 30, sends_photos: false }]
  if (path === '/catalog/papers') return [[{ id: 1, code: 'P1', name: 'Paper A5', gsm: 100, surface: 'SMOOTH', size: 'A5', unit_price: '1000' }]]
  if (path === '/catalog/pens') return [[{ id: 1, code: 'G1', name: 'Gel pen', category: 'GEL', stroke_width_mm: '0.5', surcharge: '0' }]]
  if (path === '/catalog/pens/1/inks') return [[{ id: 1, pen_type_id: 1, name: 'Black ink', hex_code: '#111111', unit_price: '0' }]]
  if (path === '/catalog/templates') return [[{ id: 1, code: 'T1', name: 'Style one', kind: 'FONT' }]]
  if (path.includes('/preview') && !path.startsWith('/orders/')) return [PNG, 200, 'image/png']
  if (path === '/pricing/estimate') return [{ chars_min: 20, chars_max: 20, price_min: '10000', price_max: '12000', min_deposit_pct: '50', basis: 'TEXT', materials_priced: true }]
  if (path.includes('notifications')) return [{ items: [], total: 0, unread_count: 0 }]
  if (path.includes('conversations')) return [path.endsWith('unread-count') ? { unread_count: 0 } : { items: [], total: 0 }]
  if (path === '/orders' && method === 'POST') { state.created = true; state.order = newOrder(); return [state.order, 201] }
  if (path === '/orders') return [{ items: state.order ? [state.order] : [], total: state.order ? 1 : 0, page: 1, page_size: 20 }]
  if (path === '/orders/77' && method === 'GET') return state.order ? [state.order] : [{ error: { code: 'ORDER_NOT_FOUND', message: 'No order' } }, 404]
  if (path === '/orders/77' && method === 'PATCH') return [state.order]
  if (path === '/orders/77/assistant/messages') {
    const proposals = Object.values(state.proposals)
    const asked = Number(new URLSearchParams(search).get('session_id')) || null
    const sess = asked ? state.sessions.find((x) => x.id === asked) : latestSession()
    if (asked && !sess) return [{ error: { code: 'SESSION_NOT_FOUND', message: 'No chat' } }, 404]
    return [{ consented_at: state.consented ? now : null, policy_version: 'AI-1.0', policy_accepted: state.consented, session: sess ? { id: sess.id, title: null, title_is_custom: false, created_at: now, last_message_at: now } : null, flags: [], messages: sess ? conversation(sess.id) : [], proposals }]
  }
  if (path === '/orders/77/assistant/sessions') return [[...state.sessions].sort((a, b) => b.last - a.last).map(sessionItem)]
  const delSession = /^\/orders\/77\/assistant\/sessions\/(\d+)$/.exec(path)
  if (delSession && method === 'DELETE') {
    const id = Number(delSession[1])
    state.sessions = state.sessions.filter((x) => x.id !== id)
    state.msgs = state.msgs.filter((m) => m.sid !== id)
    return ['', 204]
  }
  if (path === '/orders/77/assistant/messages/stream') {
    if (state.fail.limit) return [{ error: { code: 'AI_DAILY_LIMIT', message: 'Daily limit' } }, 429]
    assert.equal(body.ai_consent, undefined, 'consent is given in the policy dialog, not with the message')
    if (!state.consented) return [{ error: { code: 'AI_CONSENT_REQUIRED', message: 'Consent first', details: { policy_version: 'AI-1.0' } } }, 422]
    state.turn += 1
    state.bodies.push(body)
    assert.ok(body.client_ref, 'every message carries a client_ref')
    assert.ok(!(body.new_session && body.session_id), 'never new_session together with session_id')
    let sess = body.session_id ? state.sessions.find((x) => x.id === body.session_id) : body.new_session ? null : latestSession()
    if (!sess) { sess = { id: state.nextSid++, last: 0 }; state.sessions.push(sess) }
    sess.last = state.turn
    state.left -= 1
    const user = message(state.nextMsg++, 'USER', body.text)
    const id = state.nextMsg++
    // Turn 2 only answers (no proposal); every other turn proposes. The order is NOT changed by a turn.
    const failed = state.fail.turn
    const proposal = state.turn === 2 || failed ? null : makeProposal(30 + state.turn, id)
    if (proposal) state.proposals[proposal.id] = proposal
    const reply = message(id, 'ASSISTANT', failed ? '' : proposal ? 'I wrote it for you:\n- **Style:** Style one\n- **Paper:** Paper A5' : 'The word is fine as it is.', proposal)
    if (failed) reply.status = 'FAILED'
    state.msgs.push({ ...user, sid: sess.id }, { ...reply, pid: proposal?.id ?? null, sid: sess.id })
    return [sse([
      ['user_saved', { id: user.id }], ['provider', { provider: 'test', model: 'test' }],
      ['tool', { name: 'update_text', ok: true, revision_id: null }], ['tool', { name: 'generate_sketch', ok: true, revision_id: 11 }],
      ...(proposal ? [['proposal', { id: proposal.id, sketch_revision_id: 11, fields: ['text'] }]] : []),
      ['reply', { user, reply, replayed: false, session_id: sess.id, sketch_revision_id: state.sketch?.rev ?? null, proposal }], ['done', {}],
    ]), 200, 'text/event-stream']
  }
  const decide = /^\/orders\/77\/assistant\/proposals\/(\d+)\/(apply|reject)$/.exec(path)
  if (decide) {
    const p = state.proposals[Number(decide[1])]
    if (decide[2] === 'apply' && state.fail.apply) {
      Object.assign(p, { applicable: false, blocked_reason: 'ORDER_CHANGED' })
      return [{ error: { code: 'PROPOSAL_STALE', message: 'stale', details: { reason: 'ORDER_CHANGED' } } }, 409]
    }
    if (decide[2] === 'reject') { Object.assign(p, { status: 'REJECTED', applicable: false, blocked_reason: 'REJECTED' }); return [p] }
    // Applying writes the proposal onto the order.
    Object.assign(state.order, { paper_type_id: 1, pen_type_id: 1, ink_color_id: 1, inputs: [textInput()], estimated_price_min: '10000', estimated_price_max: '12000' })
    state.sketch = { rev: 11, canUndo: true, canRedo: false }
    Object.assign(p, { status: 'APPLIED', applicable: false, blocked_reason: 'APPLIED' })
    return [{ proposal: p, current_sketch_revision_id: 11, estimate: p.estimate }]
  }
  if (path === '/orders/77/sketch/generate') {
    if (state.fail.generate) return [{ error: { code: 'STORAGE_UNAVAILABLE', message: 'Storage down' } }, 503]
    state.sketch = { rev: 12, canUndo: true, canRedo: false }
    state.sketchGone = false
    return [sketchOut(), 201]
  }
  if (path === '/orders/77/sketch' && method === 'GET') return state.sketch && !state.sketchGone ? [sketchOut()] : [{ error: { code: 'SKETCH_NOT_GENERATED', message: 'No sketch' } }, 404]
  if (path === '/orders/77/sketch/preview' || /^\/orders\/77\/assistant\/proposals\/\d+\/preview$/.test(path)) return [PNG, 200, 'image/png']
  if (path === '/orders/77/sketch/undo') { state.sketch = { rev: 10, canUndo: false, canRedo: true }; return [sketchOut()] }
  if (path === '/orders/77/sketch/redo') { state.sketch = { rev: 11, canUndo: true, canRedo: false }; return [sketchOut()] }
  return [{}]
}

try {
  browser = spawn(edge, ['--headless=new', '--no-sandbox', '--disable-extensions', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort, 'Browser did not expose a debugging port')
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((v) => v.type === 'page').webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let nextId = 0
  const pending = new Map()
  const command = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout: ' + method)) }, 15000); pending.set(id, { resolve: (value) => { clearTimeout(timer); resolve(value) }, reject: (error) => { clearTimeout(timer); reject(error) } }); ws.send(JSON.stringify({ id, method, params })) })
  const fulfill = (id, data, code = 200, mime = 'application/json') => command('Fetch.fulfillRequest', { requestId: id, responseCode: code, responseHeaders: [{ name: 'Content-Type', value: mime }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET,POST,PATCH,PUT,DELETE,OPTIONS' }], body: (Buffer.isBuffer(data) ? data : Buffer.from(typeof data === 'string' ? data : JSON.stringify(data))).toString('base64') })

  ws.onmessage = async (message) => {
    const msg = JSON.parse(message.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) msg.error ? p.reject(new Error(JSON.stringify(msg.error))) : p.resolve(msg.result); return }
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text)
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (u.hostname === '127.0.0.1') return void command('Fetch.continueRequest', { requestId })
    if (request.method === 'OPTIONS') return void fulfill(requestId, {})
    const path = u.pathname.replace('/api/v1', '')
    log.push(`${request.method} ${path}`)
    try {
      const [data, code = 200, mime = 'application/json'] = answer(request.method, path, request.postData, u.search)
      await fulfill(requestId, data, code, mime)
    } catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:'customer',apiRole:'CUSTOMER'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}\n${log.slice(-12).join('\n')}\n${await evaluate('document.body.innerText')}`) }
  const button = (text) => `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`
  const click = async (text) => { await wait(`!!(${button(text)}) && !(${button(text)}).disabled`, `button "${text}"`); await evaluate(`(${button(text)}).click()`); await sleep(100) }
  const option = async (name) => { const find = `[...document.querySelectorAll('.co-seg--how button')].find(b=>b.textContent.trim()===${JSON.stringify(name)})`; await wait(`!!(${find}) && !(${find}).disabled`, `option "${name}"`); await evaluate(`(${find}).click()`); await sleep(100) }
  const open = async (path) => { await command('Page.navigate', { url: `http://127.0.0.1:${port}${path}` }); await wait(`!!document.querySelector('.co')`, `open ${path}`) }
  // A saved draft with content and materials opens on the review step: go back to the first one.
  /** "AI assistant", then the data policy dialog: tick the box and the chat opens. */
  const enterAi = async (shotName) => {
    await wait(`!!document.querySelector('.co-how-ai') && !document.querySelector('.co-how-ai').disabled`, 'AI choice')
    await evaluate(`document.querySelector('.co-how-ai').click()`)
    await wait(`!!document.querySelector('.oap[open] .oap-agree input:not(:disabled)')`, 'policy dialog')
    if (shotName) { await noOverflow(shotName); await shot(shotName) }
    await evaluate(`document.querySelector('.oap-agree input').click()`)
    await wait(`!document.querySelector('.oap') && !!document.querySelector('.oa')`, 'the chat opens after the tick')
  }
  const firstStep = async () => { await wait(`!!document.querySelector('.co-step')`, 'steps'); await evaluate(`document.querySelector('.co-step').click()`); await sleep(100) }
  const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.innerText ?? ''`)
  const noOverflow = async (label) => assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth + 1'), false, `horizontal overflow: ${label}`)
  const typeInto = (selector, value) => evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); const set = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set; set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })) })()`)

  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })

  const clickSel = async (sel) => { await wait(`!!document.querySelector('${sel}') && !document.querySelector('${sel}').disabled`, sel); await evaluate(`document.querySelector('${sel}').click()`); await sleep(150) }
  const shot = async (name) => { const r = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); const f = join(scratch, name); await writeFile(f, Buffer.from(r.data, 'base64')); console.log('Screenshot: ' + f) }
  const locked = () => evaluate(`document.querySelector('.co-lock').disabled`)
  const svgClick = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)}).dispatchEvent(new MouseEvent('click', { bubbles: true }))`)

  // 1. The assistant is offered and chosen; the manual text form is not shown beside it.
  // Create Order opens on "By myself"; "AI assistant" first shows the AI chat data policy from the backend.
  await open('/create-order')
  await wait(`!!document.querySelector('.co-tray--3')`, 'manual by default')
  assert.ok((await text('.co-body')).includes('AI assistant'), 'AI choice is offered')
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), false, 'no chat before the customer picks the assistant')
  assert.equal(await evaluate(`document.querySelector('.co-how-ai').getAttribute('aria-checked')`), 'false', '"By myself" is the default')
  await evaluate(`document.querySelector('.co-how-ai').click()`)
  await wait(`!!document.querySelector('.oap[open] .oap-sec')`, 'the policy dialog with the backend text')
  assert.match(await text('.oap'), /QUYỀN RIÊNG TƯ KHI SỬ DỤNG TRỢ LÝ AI/)
  assert.match(await text('.oap'), /Version AI-1\.0/)
  assert.match(await text('.oap'), /Anthropic \(Claude\), Google \(Gemini\)/)
  assert.match(await text('.oap'), /only available in Vietnamese/)
  assert.equal(await evaluate(`document.querySelectorAll('.oap-sec').length`), 2)
  assert.equal(await evaluate(`document.querySelectorAll('.oap-sec li').length`), 2, 'bullets of the policy are a list')
  await shot('order-ai-policy-1440.png')
  await click('Make it myself')
  await wait(`!document.querySelector('.oap')`, 'declining closes the dialog')
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), false, 'declining keeps "By myself"')
  assert.equal(state.consents.length, 0, 'nothing is recorded without the tick')
  await enterAi()
  assert.deepEqual(state.consents, ['AI-1.0'], 'the tick records the consent to the version read')
  assert.equal(await evaluate(`!!document.querySelector('.co-tray--3')`), false, 'the input modes are hidden while the assistant is picked')
  assert.equal(await evaluate(`!!document.querySelector('.co-side .oa') && !document.querySelector('.oa .oa-est')`), true, 'the chat sits on the right, without the price')
  assert.equal(await evaluate(`!!document.querySelector('.co-sketch .co-sketch-head .oa-est')`), true, 'the estimated price sits in the sketch box head')
  assert.equal(await evaluate(`!!document.querySelector('.oa-hero') && !document.querySelector('.oa-hero .oa-avatar')`), true, 'no logo above "What would you like to write today?"')
  assert.equal(await evaluate(`!!document.querySelector('.co-rail')`), false, 'the estimate box gives way to the chat')
  assert.equal(await evaluate(`!!document.querySelector('.co-main .co-sketch')`), true, 'the sketch takes the chat\'s old place under the form')
  assert.equal(await evaluate(`!!document.querySelector('.co-live') || !!document.querySelector('.co-sub textarea.co-text')`), false, 'the manual text form is hidden in AI mode')
  assert.equal(log.includes('POST /orders'), false, 'no draft is created before the first message')

  // 2. First message: the draft is created, the assistant answers with a proposal and the FE applies it at once, so the sketch
  //    box shows the new sketch without any Apply button. The chat keeps a one-line summary of what changed.
  const composerH = await evaluate(`document.querySelector('.oa-input textarea').getBoundingClientRect().height`)
  assert.ok(composerH < 60, `the message box starts as one line (${composerH}px)`)
  await typeInto('.oa textarea', 'Write a short birthday greeting for my mother')
  await clickSel('.oa-send')
  await wait(`document.querySelector('.oa-prop')?.dataset.status === 'APPLIED'`, 'the answer is applied')
  assert.ok(log.includes('POST /orders'), 'the draft is created with the first message')
  assert.ok(log.includes('POST /orders/77/assistant/messages/stream'), 'the message goes through the stream route')
  assert.ok(log.includes('POST /orders/77/assistant/proposals/31/apply'), 'the FE applies the proposal itself')
  assert.equal(state.bodies[0].from_order, true, 'every message starts from the order as it is')
  await wait(`!!document.querySelector('.co-sketch .oa-view-img')`, 'the new sketch shows in the sketch box at once')
  assert.ok(await evaluate(`!!document.querySelector('.co-sketch .oa-pager')`), 'a two-page sketch has a pager')
  assert.equal(await evaluate(`!!(${button('Apply to the order')}) || !!(${button('Skip')})`), false, 'there is no Apply or Skip button')
  assert.equal(await evaluate(`!!document.querySelector('.oa .oa-card-img')`), false, 'the chat does not repeat the sketch picture')
  const card = await text('.oa-prop summary')
  assert.match(card, /Applied/)
  assert.match(card, /4 changes/)
  assert.match(card, /10[.,]000/, 'the estimated price after the answer is shown')
  await evaluate(`document.querySelector('.oa-prop summary').click()`)
  assert.match(await text('.oa-prop'), /Happy birthday, Mom!/, 'the changes open from the summary')
  assert.match(await text('.oa-prop'), /Paper A5/, 'a material change is listed with its name')
  assert.ok(await evaluate(`!!document.querySelector('.oa-msg--bot strong') && !!document.querySelector('.oa-msg--bot li')`), 'bold and list items are rendered')
  assert.equal((await text('.oa-list')).includes('**'), false, 'no raw Markdown is shown')
  assert.equal(await locked(), false, 'the form is free after the answer')
  assert.equal(await evaluate(`document.querySelector('.co-next').disabled`), false, 'the order can continue with what the assistant wrote')
  await sleep(1200)
  assert.equal(log.filter((l) => l.startsWith('PUT /orders/77/inputs/text')).length, 0, 'what the answer wrote is not saved again by the form')
  await evaluate('scrollTo(0, 220)')
  await sleep(200)
  await shot('order-ai-proposal-1440.png')
  await noOverflow('after the first turn')

  // 3. Undo and redo of what the answer changed (an applied proposal is a normal sketch revision).
  assert.ok(await evaluate(`!!(${button('Undo')}) && !(${button('Undo')}).disabled && (${button('Redo')}).disabled`), 'Undo is offered, Redo is not yet')
  await click('Undo')
  await wait(`!(${button('Redo')}).disabled`, 'redo after undo')
  assert.ok(log.includes('POST /orders/77/sketch/undo'), 'undo goes to the sketch route')
  assert.equal(await evaluate(`(${button('Undo')}).disabled`), true)
  await click('Redo')
  await wait(`!(${button('Undo')}).disabled`, 'undo after redo')
  assert.ok(log.includes('POST /orders/77/sketch/redo'))

  // 4. Pick a word on the sketch: the next message carries the selection (a chip in the composer), then it is cleared.
  await click('Pick parts of the sketch')
  await wait(`!!document.querySelector('dialog.oa-pick[open]')`, 'picker dialog')
  await svgClick('.oa-pick rect[aria-label="Happy"]')
  await sleep(300)
  await shot('order-ai-picker-1440.png')
  await wait(`document.querySelector('.oa-pick rect[aria-label="Happy"]')?.getAttribute('aria-pressed') === 'true'`, 'word picked')
  await click('Done')
  await wait(`!document.querySelector('dialog.oa-pick[open]')`, 'picker closed')
  assert.match(await text('.oa-chip'), /1 picked on the sketch/)
  await typeInto('.oa textarea', 'Is the first word fine?')
  await clickSel('.oa-send')
  await wait(`document.querySelectorAll('.oa-msg--bot').length >= 3`, 'second answer')
  assert.deepEqual(state.bodies[1].selection?.word_ids, ['w11'], 'the picked word is sent as the selection')
  assert.equal(state.bodies[1].base_revision_id, 11, 'the message names the revision the customer sees')
  assert.equal(await evaluate(`!!document.querySelector('.oa-chip')`), false, 'the pick is cleared after the turn')
  assert.equal(await evaluate(`document.querySelectorAll('.oa-prop').length`), 1, 'an answer without a proposal has no summary')

  // 5. "By myself": the manual form opens with the text the assistant wrote.
  await option('By myself')
  await wait(`!!document.querySelector('textarea.co-text')`, 'manual text form')
  assert.equal(await evaluate(`document.querySelector('textarea.co-text').value`), REPLY_TEXT)
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), false)
  await option('AI assistant')
  await wait(`!!document.querySelector('.oa .oa-prop')`, 'conversation comes back')
  assert.equal(await evaluate(`!!document.querySelector('.oap')`), false, 'accepted once on this page: no second dialog')

  // 6. Another answer is applied too; the chat stays at every step and the order can go on.
  await typeInto('.oa textarea', 'Make it a little shorter')
  await clickSel('.oa-send')
  await wait(`document.querySelectorAll('.oa-prop[data-status="APPLIED"]').length === 2`, 'second answer applied')
  assert.equal(await locked(), false)
  await clickSel('.co-next')
  await wait(`document.querySelector('.co-step.cur')?.textContent.includes('2')`, 'step 2')
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), true, 'the chat stays at the materials step')
  await clickSel('.co-next')
  await wait(`document.querySelector('.co-step.cur')?.textContent.includes('3')`, 'step 3')
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), true, 'the chat stays at the review step')
  assert.equal(await evaluate(`document.querySelector('.co-next').disabled`), false, 'the order can be sent')
  await clickSel('.co-back')
  await clickSel('.co-back')
  assert.ok(state.bodies.every((b) => b.from_order === true), 'no message builds on a proposal left over from earlier')

  // 7. Failures the customer can meet. Each one shows a translated message and leaves the form usable.
  state.fail.limit = true
  await typeInto('.oa textarea', 'One more try')
  await clickSel('.oa-send')
  await wait(`!!document.querySelector('.oa .lg-error')`, 'daily limit message')
  assert.match(await text('.oa .lg-error'), /used all your assistant messages for today/)
  assert.equal(await evaluate(`document.querySelector('.oa textarea').value`), 'One more try', 'the typed message is kept after a refusal')
  state.fail.limit = false

  state.fail.turn = true
  const before = await evaluate(`document.querySelectorAll('.oa-prop').length`)
  await clickSel('.oa-send')
  await wait(`!!document.querySelector('.oa-msg--bot.failed')`, 'provider failure')
  assert.match(await text('.oa-msg--bot.failed'), /could not answer right now/)
  assert.equal(await evaluate(`document.querySelectorAll('.oa-prop').length`), before, 'a failed turn changes nothing')
  assert.equal(await locked(), false, 'the form stays free after a failed turn')
  state.fail.turn = false

  // The order has text but no sketch: the chat shows no "draw the sketch" prompt (removed 2026-11-24, the assistant draws it).
  state.sketchGone = true
  await open('/create-order/draft/77')
  await firstStep()
  await enterAi()
  await wait(`!!document.querySelector('.oa-foot')`, 'chat without a sketch')
  assert.equal(await evaluate(`!!document.querySelector('.oa-foot .oa-note')`), false, 'no draw prompt when there is no sketch')
  state.sketchGone = false
  await open('/create-order/draft/77')
  await firstStep()
  await enterAi()
  await wait(`!!document.querySelector('.co-sketch .oa-view-img')`, 'the sketch is back')

  // 8. The order changed while the assistant answered (another tab): applying is refused, the chat says why and marks the
  //    answer as not applied, and the form stays free.
  state.fail.apply = true
  await typeInto('.oa textarea', 'One more idea')
  await clickSel('.oa-send')
  await wait(`!!document.querySelector('.oa .lg-error')`, 'stale answer')
  assert.match(await text('.oa .lg-error'), /order changed after this proposal/i)
  await wait(`!!document.querySelector('.oa-prop[data-status="PENDING"]')`, 'the answer is marked as not applied')
  assert.match(await text('.oa-prop[data-status="PENDING"] summary'), /Not applied/)
  assert.equal(await locked(), false, 'a refused answer does not lock the form')
  state.fail.apply = false

  // Vietnamese and Japanese, desktop and phone.
  for (const [lang, ai, applied] of [['vi', 'Trợ lý AI', 'Đã áp dụng'], ['ja', 'AIアシスタント', '適用済み']]) {
    await evaluate(`localStorage.setItem('aivhrs-lang',${JSON.stringify(lang)})`)
    for (const width of [1440, 390]) {
      await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 600 })
      await open('/create-order/draft/77')
      await firstStep()
      await enterAi(width === 390 ? `order-ai-policy-${lang}-390.png` : undefined)
      await wait(`!!document.querySelector('.oa .oa-prop')`, `${lang} ${width} answer summary`)
      assert.ok((await text('.co-body')).includes(ai), `${lang}: ${ai}`)
      assert.ok((await text('.oa')).includes(applied), `${lang}: ${applied}`)
      await noOverflow(`${lang} ${width}`)
      if (lang === 'vi' && width === 1440) await shot('order-ai-vi-1440.png')
      if (lang === 'vi' && width === 390) await shot('order-ai-vi-390.png')
    }
  }

  // 10. Conversations (migration 0031): New chat clears the panel, its first message goes with new_session and the next ones
  //     with its session_id; the history lists both chats, opens the old one and deletes the new one after a confirmation.
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await open('/create-order/draft/77')
  await firstStep()
  await enterAi()
  await wait(`!!document.querySelector('.oa .oa-prop')`, 'the last chat is loaded')
  const oldMine = await evaluate(`document.querySelectorAll('.oa-msg--me').length`)
  const sent = state.bodies.length
  await click('New chat')
  assert.equal(await evaluate(`document.querySelectorAll('.oa-list .oa-prop, .oa-list .oa-msg--me').length`), 0, 'a new chat clears the panel')
  assert.match(await text('.oa-head'), /New chat/)
  assert.equal(log.includes('POST /orders/77/assistant/sessions'), false, 'a new chat calls nothing before its first message')
  await typeInto('.oa textarea', 'Start over please')
  await clickSel('.oa-send')
  await wait(`document.querySelectorAll('.oa-msg--me').length === 1 && !document.querySelector('.oa-wait')`, 'first answer of the new chat')
  assert.equal(state.bodies[sent].new_session, true, 'the first message of a new chat starts a session')
  assert.equal(state.bodies[sent].session_id, undefined)
  await typeInto('.oa textarea', 'And once more')
  await clickSel('.oa-send')
  await wait(`document.querySelectorAll('.oa-msg--me').length === 2 && !document.querySelector('.oa-wait')`, 'second answer of the new chat')
  assert.equal(state.bodies[sent + 1].session_id, 2, 'the next messages continue that session')
  assert.equal(state.bodies[sent + 1].new_session, undefined)
  await clickSel('.oa-tool[aria-expanded]')
  await wait(`document.querySelectorAll('.oa-session').length === 2`, 'both chats are listed')
  assert.match(await text('.oa-session.on'), /Start over please/, 'the open chat is marked')
  await shot('order-ai-history-1440.png')
  await evaluate(`[...document.querySelectorAll('.oa-session')].find((li) => !li.classList.contains('on')).querySelector('.oa-session-open').click()`)
  await wait(`!document.querySelector('.oa-history') && document.querySelectorAll('.oa-msg--me').length === ${oldMine}`, 'the old chat opens')
  await clickSel('.oa-tool[aria-expanded]')
  await wait(`document.querySelectorAll('.oa-session').length === 2`, 'history again')
  await evaluate(`[...document.querySelectorAll('.oa-session')].find((li) => li.textContent.includes('Start over please')).querySelector('button[title="Delete chat"]').click()`)
  await wait(`!!document.querySelector('.oa-session-ask')`, 'delete asks first')
  assert.match(await text('.oa-session-ask'), /cannot be restored/)
  await click('Delete')
  await wait(`document.querySelectorAll('.oa-session').length === 1`, 'the chat is deleted')
  assert.ok(log.includes('DELETE /orders/77/assistant/sessions/2'))
  await shot('order-ai-light-1440.png')

  // Consent withdrawn elsewhere: the backend refuses the message, the dialog asks again and the typed text stays.
  state.consented = false
  await typeInto('.oa textarea', 'After the withdrawal')
  await clickSel('.oa-send')
  await wait(`!!document.querySelector('.oap[open] .oap-agree input:not(:disabled)')`, 'the dialog comes back on AI_CONSENT_REQUIRED')
  assert.equal(await evaluate(`document.querySelector('.oa textarea').value`), 'After the withdrawal')
  await evaluate(`document.querySelector('.oap-agree input').click()`)
  await wait(`!document.querySelector('.oap') && !!document.querySelector('.oa')`, 'the chat stays after the new tick')
  assert.equal(state.consented, true)

  // 9. The assistant is off: only the manual form, with a note.
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  state.available = false
  await open('/create-order/draft/77')
  await firstStep()
  await wait(`!!document.querySelector('textarea.co-text')`, 'manual form when the assistant is off')
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), false)
  assert.match(await text('.co-body'), /The assistant is not available right now/)
  assert.equal(await evaluate(`document.querySelector('.co-seg--how .co-how-ai').disabled`), true, 'the AI choice is disabled')
  assert.equal(await evaluate(`!!document.querySelector('.co-tray--3')`), true, 'the input modes are shown without the assistant')
  assert.equal(await evaluate(`!!document.querySelector('.co-rail') && !document.querySelector('.co-sketch')`), true, 'without the assistant the estimate box is back')

  assert.deepEqual(errors, [])
  console.log('PASS: AI choice, layout (chat with price on the right, sketch on the left), first turn (draft, proposal applied at once, sketch box updated, no Apply/Skip, compact summary, Markdown), one-line composer, undo and redo, pick on the sketch (chip, selection sent and cleared), by myself, chat at every step, from_order on every message, errors (daily limit, provider failed, apply refused), no draw prompt without a sketch, default "By myself", policy dialog (backend text, decline, tick records the version, asked again on AI_CONSENT_REQUIRED), vi/ja at 1440 and 390, new chat and history (new_session, session_id, open, delete), assistant off. All API calls intercepted.')
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close()
}
