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

// ---- the fake backend: the assistant PROPOSES, the order changes only on apply (BE migration 0029) ----
const state = { fail: { generate: false, apply: false, turn: false, limit: false }, sketchGone: false, available: true, created: false, order: null, sketch: null, msgs: [], consented: false, left: 30, turn: 0, nextMsg: 1, proposals: {}, bodies: [] }
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
const conversation = () => state.msgs.map((m) => ({ ...m, proposal: m.pid ? state.proposals[m.pid] : null }))

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
function answer(method, path, postData) {
  const body = postData ? JSON.parse(postData) : {}
  if (path === '/me') return [{ id: 17, email: 'test@example.test', full_name: 'Browser Test', role: 'CUSTOMER', status: 'ACTIVE', addresses: [], created_at: now }]
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
    return [{ consented_at: state.consented ? now : null, flags: [], messages: conversation(), proposals }]
  }
  if (path === '/orders/77/assistant/messages/stream') {
    if (state.fail.limit) return [{ error: { code: 'AI_DAILY_LIMIT', message: 'Daily limit' } }, 429]
    state.turn += 1
    state.bodies.push(body)
    assert.ok(body.ai_consent === true, 'the message carries the consent')
    assert.ok(body.client_ref, 'every message carries a client_ref')
    state.consented = true
    state.left -= 1
    const user = message(state.nextMsg++, 'USER', body.text)
    const id = state.nextMsg++
    // Turn 2 only answers (no proposal); every other turn proposes. The order is NOT changed by a turn.
    const failed = state.fail.turn
    const proposal = state.turn === 2 || failed ? null : makeProposal(30 + state.turn, id)
    if (proposal) state.proposals[proposal.id] = proposal
    const reply = message(id, 'ASSISTANT', failed ? '' : proposal ? 'I propose this. Have a look and apply it if you like it.' : 'The word is fine as it is.', proposal)
    if (failed) reply.status = 'FAILED'
    state.msgs.push(user, { ...reply, pid: proposal?.id ?? null })
    return [sse([
      ['user_saved', { id: user.id }], ['provider', { provider: 'test', model: 'test' }],
      ['tool', { name: 'update_text', ok: true, revision_id: null }], ['tool', { name: 'generate_sketch', ok: true, revision_id: 11 }],
      ...(proposal ? [['proposal', { id: proposal.id, sketch_revision_id: 11, fields: ['text'] }]] : []),
      ['reply', { user, reply, replayed: false, sketch_revision_id: state.sketch?.rev ?? null, proposal }], ['done', {}],
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
      const [data, code = 200, mime = 'application/json'] = answer(request.method, path, request.postData)
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
  const option = async (name) => { const find = `[...document.querySelectorAll('.co-opt')].find(b=>b.querySelector('.co-opt-name')?.textContent.trim()===${JSON.stringify(name)})`; await wait(`!!(${find}) && !(${find}).disabled`, `option "${name}"`); await evaluate(`(${find}).click()`); await sleep(100) }
  const open = async (path) => { await command('Page.navigate', { url: `http://127.0.0.1:${port}${path}` }); await wait(`!!document.querySelector('.co')`, `open ${path}`) }
  // A saved draft with content and materials opens on the review step: go back to the first one.
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
  await open('/create-order')
  await wait(`!!document.querySelector('.oa')`, 'assistant panel')
  assert.ok((await text('.co-body')).includes('Use the AI assistant'), 'AI choice is offered')
  assert.equal(await evaluate(`!!document.querySelector('.co-live') || !!document.querySelector('.co-sub textarea.co-text')`), false, 'the manual text form is hidden in AI mode')
  assert.equal(log.includes('POST /orders'), false, 'no draft is created before the first message')

  // 2. First message: the draft is created and the assistant answers with a PROPOSAL. The order and the sketch do not change.
  await typeInto('.oa textarea', 'Write a short birthday greeting for my mother')
  await evaluate(`document.querySelector('.oa-consent input').click()`)
  await click('Send')
  await wait(`!!document.querySelector('.oa-prop .oa-card-img')`, 'proposal card with its picture')
  const card = await text('.oa-prop')
  assert.match(card, /Proposal/)
  assert.match(card, /Happy birthday, Mom!/, 'the text change is listed')
  assert.match(card, /Paper A5/, 'the material change is listed with its name')
  assert.match(card, /10[.,]000/, 'the estimated price after applying is shown')
  assert.ok(await evaluate(`!!(${button('Apply to the order')}) && !!(${button('Skip')})`), 'Apply and Skip are offered')
  assert.ok(log.includes('GET /orders/77/assistant/proposals/31/preview'), 'the card loads the proposal preview, not the order sketch')
  assert.ok(await evaluate(`!!document.querySelector('.oa-prop .oa-pager')`), 'a two-page proposal preview has a pager')
  assert.ok(log.includes('POST /orders'), 'the draft is created with the first message')
  assert.ok(log.includes('POST /orders/77/assistant/messages/stream'), 'the message goes through the stream route')
  assert.equal(await evaluate(`!!document.querySelector('.co-preview .oa-view-img')`), false, 'the sketch beside the form does not show a proposal that is not applied')
  assert.equal(await locked(), true, 'the form is locked while a proposal waits')
  await evaluate(`document.querySelector('.oa-prop').scrollIntoView({ block: 'center' })`)
  await sleep(300)
  await shot('order-ai-proposal-1440.png')
  assert.match(await text('.co-lock-note'), /proposal is waiting/)
  assert.equal(await evaluate(`document.querySelector('.co-next').disabled`), true, 'nothing to continue with: the order has no content yet')
  await noOverflow('after the first turn')

  // 3. Apply: the order, the form and the sketch beside it change; the form is free again.
  await click('Apply to the order')
  await wait(`document.querySelector('.oa-prop')?.dataset.status === 'APPLIED'`, 'applied')
  assert.ok(log.includes('POST /orders/77/assistant/proposals/31/apply'), 'apply goes to the proposal route')
  await wait(`!!document.querySelector('.co-preview .oa-view-img')`, 'the applied sketch in the preview box')
  assert.equal(await locked(), false, 'the form is free after apply')
  assert.equal(await evaluate(`document.querySelector('.co-next').disabled`), false, 'the order can continue with the applied content')
  assert.ok(await evaluate(`!!document.querySelector('.oa-pager')`), 'a two-page sketch has a pager')
  await sleep(1200)
  assert.equal(log.filter((l) => l.startsWith('PUT /orders/77/inputs/text')).length, 0, 'what apply wrote is not saved again by the form')

  // 3b. Undo and redo of what was applied (the applied proposal is a normal sketch revision).
  assert.ok(await evaluate(`!!(${button('Undo')}) && !(${button('Undo')}).disabled && (${button('Redo')}).disabled`), 'Undo is offered, Redo is not yet')
  await click('Undo')
  await wait(`!(${button('Redo')}).disabled`, 'redo after undo')
  assert.ok(log.includes('POST /orders/77/sketch/undo'), 'undo goes to the sketch route')
  assert.equal(await evaluate(`(${button('Undo')}).disabled`), true)
  await click('Redo')
  await wait(`!(${button('Undo')}).disabled`, 'undo after redo')
  assert.ok(log.includes('POST /orders/77/sketch/redo'))

  // 4. Pick a word on the sketch: the next message carries the selection, then it is cleared.
  await click('Pick parts of the sketch')
  await wait(`!!document.querySelector('dialog.oa-pick[open]')`, 'picker dialog')
  await svgClick('.oa-pick rect[aria-label="Happy"]')
  await sleep(300)
  await shot('order-ai-picker-1440.png')
  await wait(`document.querySelector('.oa-pick rect[aria-label="Happy"]')?.getAttribute('aria-pressed') === 'true'`, 'word picked')
  await click('Done')
  await wait(`!document.querySelector('dialog.oa-pick[open]')`, 'picker closed')
  assert.match(await text('.oa-picked'), /1 picked on the sketch/)
  await typeInto('.oa textarea', 'Is the first word fine?')
  await click('Send')
  await wait(`document.querySelectorAll('.oa-msg--bot').length >= 3`, 'second answer')
  assert.deepEqual(state.bodies[1].selection?.word_ids, ['w11'], 'the picked word is sent as the selection')
  assert.equal(state.bodies[1].base_revision_id, 11, 'the message names the revision the customer sees')
  assert.equal(await evaluate(`!!document.querySelector('.oa-picked')`), false, 'the pick is cleared after the turn')
  assert.equal(await evaluate(`document.querySelectorAll('.oa-prop').length`), 1, 'an answer without a proposal has no card')

  // 5. "No AI": the manual form opens with the text the proposal wrote.
  await option('No AI, I will do it myself')
  await wait(`!!document.querySelector('textarea.co-text')`, 'manual text form')
  assert.equal(await evaluate(`document.querySelector('textarea.co-text').value`), REPLY_TEXT)
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), false)
  await option('Use the AI assistant')
  await wait(`!!document.querySelector('.oa .oa-prop')`, 'conversation comes back')

  // 6. A new proposal: the chat stays at every step, the form stays locked, the order cannot be sent.
  await typeInto('.oa textarea', 'Make it a little shorter')
  await click('Send')
  await wait(`document.querySelectorAll('.oa-prop[data-status="PENDING"]').length === 1`, 'second proposal')
  assert.equal(await locked(), true)
  assert.match(await text('.oa-foot'), /adds to the proposal above/)
  await clickSel('.co-next')
  await wait(`document.querySelector('.co-step.cur')?.textContent.includes('2')`, 'step 2')
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), true, 'the chat stays at the materials step')
  assert.equal(await locked(), true, 'the materials step is locked while a proposal waits')
  await clickSel('.co-next')
  await wait(`document.querySelector('.co-step.cur')?.textContent.includes('3')`, 'step 3')
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), true, 'the chat stays at the review step')
  assert.equal(await evaluate(`document.querySelector('.co-next').disabled`), true, 'the order is not sent while a proposal waits')
  assert.match(await text('.co-need'), /Apply or skip/)
  await clickSel('.co-back')
  await clickSel('.co-back')

  // 7. Start again from the order: the next message asks for it, and a skipped proposal frees the form.
  await click('Start again from the order')
  assert.match(await text('.oa-foot'), /starts again from the order/)
  await typeInto('.oa textarea', 'Start over with a longer greeting')
  await click('Send')
  await wait(`document.querySelectorAll('.oa-prop').length === 3`, 'third proposal')
  assert.equal(state.bodies.at(-1).from_order, true, 'start again sends from_order')
  assert.equal(state.bodies[2].from_order, undefined, 'a normal message does not send from_order')
  for (let n = 0; n < 2; n++) {
    await evaluate(`(${button('Skip')}).click()`)
    await sleep(300)
  }
  await wait(`document.querySelectorAll('.oa-prop[data-status="PENDING"]').length === 0`, 'both skipped')
  assert.equal(log.filter((l) => /proposals\/\d+\/reject$/.test(l)).length, 2)
  assert.equal(await locked(), false, 'the form is free after the proposals are skipped')

  // 7b. Failures the customer can meet. Each one shows a translated message and leaves the form usable.
  state.fail.limit = true
  await typeInto('.oa textarea', 'One more try')
  await click('Send')
  await wait(`!!document.querySelector('.oa .lg-error')`, 'daily limit message')
  assert.match(await text('.oa .lg-error'), /used all your assistant messages for today/)
  assert.equal(await evaluate(`document.querySelector('.oa textarea').value`), 'One more try', 'the typed message is kept after a refusal')
  state.fail.limit = false

  state.fail.turn = true
  await click('Send')
  await wait(`!!document.querySelector('.oa-msg--bot.failed')`, 'provider failure')
  assert.match(await text('.oa-msg--bot.failed'), /could not answer right now/)
  assert.equal(await evaluate(`document.querySelectorAll('.oa-prop[data-status="PENDING"]').length`), 0, 'a failed turn makes no proposal')
  assert.equal(await locked(), false, 'the form stays free after a failed turn')
  state.fail.turn = false

  // The order has text but no sketch and the file storage is down: drawing says so, and works again once storage is back.
  state.sketchGone = true
  state.fail.generate = true
  await open('/create-order/draft/77')
  await firstStep()
  await wait(`!!(${button('Draw the sketch')})`, 'draw button when there is no sketch')
  await click('Draw the sketch')
  await wait(`!!document.querySelector('.oa .lg-error')`, 'storage error')
  assert.match(await text('.oa .lg-error'), /File storage is not available/)
  state.fail.generate = false
  await click('Draw the sketch')
  await wait(`!!document.querySelector('.co-preview .oa-view-img')`, 'sketch after storage is back')
  assert.equal(await evaluate(`!!document.querySelector('.oa .lg-error')`), false, 'the error clears on the next try')

  // 8. A proposal waits again, then Vietnamese and Japanese, desktop and phone.
  await typeInto('.oa textarea', 'One more idea')
  await click('Send')
  await wait(`document.querySelectorAll('.oa-prop[data-status="PENDING"]').length === 1`, 'pending proposal')
  // The order changed after the proposal (another tab): Apply says why, stays off, and the form is free again.
  state.fail.apply = true
  await click('Apply to the order')
  await wait(`!!document.querySelector('.oa .lg-error') || !!document.querySelector('.oa-blocked')`, 'stale answer')
  assert.match(await text('.oa'), /order changed after this proposal/i)
  assert.equal(await evaluate(`(${button('Apply to the order')}).disabled`), true, 'Apply is off once the proposal is stale')
  assert.equal(await locked(), false, 'a stale proposal does not keep the form locked')
  state.fail.apply = false
  for (const [lang, ai, proposal, applyText] of [['vi', 'Dùng trợ lý AI', 'Đề xuất', 'Áp dụng vào đơn'], ['ja', 'AIアシスタントを使う', '提案', '注文に適用']]) {
    await evaluate(`localStorage.setItem('aivhrs-lang',${JSON.stringify(lang)})`)
    for (const width of [1440, 390]) {
      await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 600 })
      await open('/create-order/draft/77')
      await firstStep()
      await wait(`!!document.querySelector('.oa .oa-prop')`, `${lang} ${width} proposal card`)
      assert.ok((await text('.co-body')).includes(ai), `${lang}: ${ai}`)
      assert.ok((await text('.oa')).includes(proposal), `${lang}: ${proposal}`)
      assert.ok(await evaluate(`!!(${button(applyText)})`), `${lang}: ${applyText}`)
      await noOverflow(`${lang} ${width}`)
      if (lang === 'vi' && width === 1440) {
        const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
        const file = join(scratch, 'order-ai-vi-1440.png')
        await writeFile(file, Buffer.from(shot.data, 'base64'))
        console.log('Screenshot: ' + file)
      }
    }
  }

  // 9. The assistant is off: only the manual form, with a note.
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  state.available = false
  await open('/create-order/draft/77')
  await firstStep()
  await wait(`!!document.querySelector('textarea.co-text')`, 'manual form when the assistant is off')
  assert.equal(await evaluate(`!!document.querySelector('.oa')`), false)
  assert.match(await text('.co-body'), /The assistant is not available right now/)
  assert.equal(await evaluate(`document.querySelector('.co-opt[role=radio]').disabled`), true, 'the AI choice is disabled')

  assert.deepEqual(errors, [])
  console.log('PASS: AI choice, first turn (draft, proposal card, order and sketch unchanged), apply, undo and redo, pick on the sketch (selection sent and cleared), no AI, chat at every step, form locked and order not sendable while a proposal waits, start again (from_order), skip, errors (daily limit, provider failed, storage down then back, stale proposal), vi/ja at 1440 and 390, assistant off. All API calls intercepted.')
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close()
}
