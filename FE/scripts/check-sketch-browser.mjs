// Browser check of the create-order "Sketch" step: the canvas, the manual tools and the AI assistant's
// proposal cards ("Keep editing" / "Apply edit"). The backend is a stateful fixture: a revision tree with a cursor,
// undo / redo, edits and an assistant stream, so the applied-revision logic in services/sketch.ts runs for real.
// Run after `npm run build`; set TECH_BROWSER_PATH to a Chromium or Edge executable.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp, readdir } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const edge = process.env.TECH_BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
assert.ok(existsSync(edge), 'Set TECH_BROWSER_PATH to an installed Chromium/Edge executable')
assert.ok(existsSync(join(root, 'dist/index.html')), 'Run npm run build first')
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-sketch-'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const now = new Date().toISOString()
const png = await readFile(join(root, 'dist/assets', (await readdir(join(root, 'dist/assets'))).find((f) => f.endsWith('.png'))))

// ---------- fixture backend ----------
const ORDER = 77
const order = {
  id: ORDER, code: 'VH-SKETCH-TEST', order_type: 'OT3_TEMPLATE', order_status: 'DRAFT', production_status: 'NOT_STARTED',
  paper_type_id: 1, pen_type_id: 2, ink_color_id: 3, workshop_suggest_materials: false, quantity: 1, char_count: 18,
  estimated_price_min: '180000', estimated_price_max: '220000', customer_note: null, info_request_note: null,
  reject_reason: null, reject_note: null, eta: null, last_saved_at: now, submitted_at: null, created_at: now, warnings: [],
  inputs: [{ id: 5, kind: 'TEXT_CONTENT', sort_order: 0, text_content: 'Gửi mẹ yêu,\nCon nhớ mẹ.', template_id: 11, font_size_mm: null, alignment: null }],
}
const LINES = [['Gửi', 'mẹ', 'yêu,'], ['Con', 'nhớ', 'mẹ.']]
function makeDoc(shift = {}) {
  const strokes = [], words = [], lines = [], paragraphs = []
  let w = 0, s = 0
  LINES.forEach((ln, li) => {
    const wordIds = []
    let x = 20
    const y = 60 + li * 16
    for (const text of ln) {
      const id = `w${++w}`
      const dx = shift[id] ?? 0
      const width = text.length * 4
      const ids = []
      for (let k = 0; k < 2; k++) {
        const sid = `s${++s}`
        ids.push(sid)
        const x0 = x + dx + k * (width / 2)
        strokes.push({ id: sid, kind: 'base', word: id, provenance: 'ENGINE', points: [[x0, y], [x0 + width / 4, y - 6], [x0 + width / 2 - 1, y]] })
      }
      words.push({ id, stroke_ids: ids, bbox: [x + dx, y - 6, x + dx + width, y], text })
      wordIds.push(id)
      x += width + 4
    }
    lines.push({ id: `l${li + 1}`, word_ids: wordIds, bbox: [20, y - 6, x, y], paragraph: `p${li + 1}` })
    paragraphs.push({ id: `p${li + 1}`, line_ids: [`l${li + 1}`], bbox: [20, y - 6, x, y], source: 'TEXT' })
  })
  return { format: 'vhrs-sketch/2', pages: [{ no: 1, paper_size: 'A5', width_mm: 148, height_mm: 210, strokes, words, lines, paragraphs }] }
}
const revs = new Map()
let seq = 0
let cursor = null
const log = []
function addRev(parent, author, shift) {
  const id = ++seq
  revs.set(id, { id, seq: id, parent, author, shift: { ...shift } })
  cursor = id
  return id
}
const children = (id) => [...revs.values()].filter((r) => r.parent === id).sort((a, b) => b.seq - a.seq)
const sketchOut = (id) => {
  const r = revs.get(id)
  return {
    revision: { id: r.id, seq: r.seq, parent_id: r.parent, author: r.author, tool_name: null, provider: null, model: null, note: null, operation: null, geometry_hash: 'x', metrics: {}, validation: null, created_at: now },
    is_current: id === cursor, can_undo: r.parent !== null, can_redo: children(id).length > 0, inputs_changed: false, inputs_restored: false,
    limits: { name: 'TEXT', max_shift_mm: 3, max_rotate_deg: 15, scale_range: [0.8, 1.25], max_slant_deg: 15, curvature_range: [0.5, 1.5], max_extend_mm: 3, max_join_gap_mm: 2 },
    document: makeDoc(r.shift), warnings: [], report: null, redraw: null, text_hints: null,
  }
}
addRev(null, 'ENGINE', {})
const messages = []
let consented = false
let msgId = 0
let submittedAt = null

function handle(method, path, query, body) {
  if (path === '/me') return { id: 9, email: 'customer@example.test', full_name: 'Sketch Test', role: 'CUSTOMER', status: 'ACTIVE', phone: null, addresses: [], created_at: now }
  if (path === `/orders/${ORDER}` && method === 'GET') return order
  if (path === '/catalog/papers') return [{ id: 1, code: 'P1', name: 'Croquis A5', gsm: 120, surface: 'SMOOTH', size: 'A5', unit_price: '2000' }]
  if (path === '/catalog/pens') return [{ id: 2, code: 'G1', name: 'Gel 0.5', category: 'GEL', stroke_width_mm: '0.5', surcharge: '0' }]
  if (path === '/catalog/pens/2/inks') return [{ id: 3, pen_type_id: 2, name: 'Black', hex_code: '#111111', unit_price: '0' }]
  if (path === '/catalog/templates') return [{ id: 11, code: 'T11', name: 'Single line', kind: 'SINGLE_LINE_FONT' }]
  if (path === '/pricing/estimate') return { chars_min: 18, chars_max: 18, price_min: '180000', price_max: '220000', min_deposit_pct: '50', basis: 'TEXT', materials_priced: true }
  if (path === '/studio/assistant/status') return { enabled: true, available: true, providers: ['gemini'], messages_left_today: 29, daily_message_limit: 30, sends_photos: false }
  if (path === `/orders/${ORDER}/assistant/messages` && method === 'GET') return { consented_at: consented ? now : null, flags: [], messages }
  if (path === `/orders/${ORDER}/sketch` && method === 'GET') return sketchOut(query.get('revision_id') ? Number(query.get('revision_id')) : cursor)
  if (path === `/orders/${ORDER}/sketch/revisions`) return [...revs.values()].map((r) => sketchOut(r.id).revision)
  if (path === `/orders/${ORDER}/sketch/undo`) {
    const r = revs.get(cursor)
    if (!r.parent) return [409, { error: { code: 'NOTHING_TO_UNDO', message: 'x' } }]
    log.push(`undo ${cursor}->${r.parent}`)
    cursor = r.parent
    return sketchOut(cursor)
  }
  if (path === `/orders/${ORDER}/sketch/redo`) {
    const c = children(cursor)[0]
    if (!c) return [409, { error: { code: 'NOTHING_TO_REDO', message: 'x' } }]
    log.push(`redo ${cursor}->${c.id}`)
    cursor = c.id
    return sketchOut(cursor)
  }
  if (path === `/orders/${ORDER}/sketch/edit`) {
    if (body.base_revision_id !== cursor) return [409, { error: { code: 'STALE_REVISION', message: 'stale', details: { current_revision_id: cursor } } }]
    const shift = { ...revs.get(cursor).shift }
    for (const w of body.word_ids ?? []) shift[w] = (shift[w] ?? 0) + Number(body.params.dx_mm ?? 0)
    const id = addRev(cursor, 'CUSTOMER', shift)
    log.push(`edit base ${body.base_revision_id} -> ${id}`)
    return sketchOut(id)
  }
  if (path === `/orders/${ORDER}/submit`) {
    submittedAt = cursor
    return { ...order, order_status: 'SUBMITTED', submitted_at: now }
  }
  if (path.endsWith('/notifications')) return { items: [], unread_count: 0, next_before_id: null }
  if (path.endsWith('unread-count')) return { unread_count: 0 }
  if (path.includes('conversations')) return { items: [], total: 0 }
  return null
}

function stream(body) {
  if (body.base_revision_id !== cursor) return [409, { error: { code: 'STALE_REVISION', message: 'stale' } }]
  if (!consented && !body.ai_consent) return [422, { error: { code: 'AI_CONSENT_REQUIRED', message: 'consent' } }]
  consented = true
  log.push(`ai base ${body.base_revision_id} sel ${JSON.stringify(body.selection ?? null)}`)
  const shift = { ...revs.get(cursor).shift, w1: (revs.get(cursor).shift.w1 ?? 0) + 1 }
  const id = addRev(cursor, 'AI', shift)
  const user = { id: ++msgId, role: 'user', content: body.text, status: 'OK', provider: null, model: null, tool_calls: [], created_at: now }
  const reply = { id: ++msgId, role: 'assistant', content: `Proposal from revision ${body.base_revision_id}.`, status: 'OK', provider: 'gemini', model: 'm', tool_calls: [{ name: 'edit_strokes', ok: true, revision_id: id }], created_at: now }
  messages.push(user, reply)
  const ev = (name, data) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`
  return 'retry: 5000\n\n' + ev('user_saved', { id: user.id }) + ev('provider', { provider: 'gemini', model: 'm' }) +
    ev('tool', { name: 'edit_strokes', ok: true, revision_id: id }) + ev('reply', { user, reply, replayed: false, sketch_revision_id: id }) + ev('done', {})
}

// ---------- static server + browser ----------
const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://localhost').pathname
    const target = path.startsWith('/assets/') ? join(root, 'dist', path) : join(root, 'dist/index.html')
    assert.ok(resolve(target).startsWith(resolve(root, 'dist')))
    res.setHeader('Content-Type', ({ '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' })[extname(target)] || 'text/html')
    res.end(await readFile(target))
  } catch { res.statusCode = 404; res.end() }
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const port = server.address().port
let browser, ws
const errors = []
try {
  browser = spawn(edge, ['--headless=new', '--no-sandbox', '--disable-extensions', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort, 'Browser did not expose a debugging port')
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((v) => v.type === 'page').webSocketDebuggerUrl)
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j })
  let nextId = 0
  const pending = new Map()
  const command = (method, params = {}) => new Promise((res, rej) => { const id = ++nextId; const timer = setTimeout(() => { pending.delete(id); rej(new Error('CDP timeout: ' + method)) }, 15000); pending.set(id, { method, resolve: (v) => { clearTimeout(timer); res(v) }, reject: (e) => { clearTimeout(timer); rej(e) } }); ws.send(JSON.stringify({ id, method, params })) })
  const headers = (mime) => [{ name: 'Content-Type', value: mime }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET,POST,PATCH,PUT,DELETE,OPTIONS' }]
  const fulfill = (id, data, code = 200, mime = 'application/json') => command('Fetch.fulfillRequest', { requestId: id, responseCode: code, responseHeaders: headers(mime), body: (Buffer.isBuffer(data) ? data : Buffer.from(typeof data === 'string' ? data : JSON.stringify(data))).toString('base64') })

  ws.onmessage = async (message) => {
    const msg = JSON.parse(message.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) { if (p.method.startsWith('Fetch.') && msg.error?.message === 'Invalid InterceptionId.') p.resolve({}); else if (msg.error) p.reject(new Error(JSON.stringify(msg.error))); else p.resolve(msg.result) } return }
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description ?? msg.params.exceptionDetails.text)
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (u.hostname === '127.0.0.1') return void command('Fetch.continueRequest', { requestId })
    if (request.method === 'OPTIONS') return void fulfill(requestId, {})
    if (u.hostname.includes('fonts.')) return void fulfill(requestId, '', 200, 'text/css')
    const path = u.pathname.replace('/api/v1', '')
    const body = request.postData ? JSON.parse(request.postData) : {}
    try {
      if (path.endsWith('/stream') && path.includes('notifications')) return void fulfill(requestId, 'event: ready\ndata: {"unread_count":0}\n\n', 200, 'text/event-stream')
      if (path === `/orders/${ORDER}/assistant/messages/stream`) {
        const out = stream(body)
        return void (Array.isArray(out) ? fulfill(requestId, out[1], out[0]) : fulfill(requestId, out, 200, 'text/event-stream'))
      }
      if (path.includes('/preview')) return void fulfill(requestId, png, 200, 'image/png')
      const out = handle(request.method, path, u.searchParams, body)
      if (out === null) return void fulfill(requestId, { error: { code: 'NOT_FOUND', message: 'Fixture not found: ' + path } }, 404)
      if (Array.isArray(out) && typeof out[0] === 'number' && out.length === 2 && out[1]?.error) return void fulfill(requestId, out[1], out[0])
      await fulfill(requestId, out)
    } catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:9,name:'Sketch Test',email:'customer@example.test',role:'customer',apiRole:'CUSTOMER'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description ?? r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\nlog: ${log.join(' | ')}\nerrors: ${errors.join(' | ')}`) }
  const click = (selector, text) => evaluate(`(()=>{const el=[...document.querySelectorAll(${JSON.stringify(selector)})].find(e=>${text ? `e.textContent.includes(${JSON.stringify(text)})` : 'true'});if(!el)throw new Error('no element ${selector} ${text ?? ''}');el.click();return true})()`)
  const shot = async (name) => {
    if (!process.env.SKETCH_SHOTS) return
    const { data } = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
    const { writeFile } = await import('node:fs/promises')
    await writeFile(join(process.env.SKETCH_SHOTS, name + '.png'), Buffer.from(data, 'base64'))
  }
  const badge = () => evaluate(`document.querySelector('.sk-version .sk-badge')?.textContent`)
  const sendText = async (text) => {
    await evaluate(`(()=>{const ta=document.querySelector('.sk-ai-input textarea');const set=Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set;set.call(ta,${JSON.stringify(text)});ta.dispatchEvent(new Event('input',{bubbles:true}));return true})()`)
    await sleep(100)
    await click('.sk-ai-input .sk-btn--solid')
  }

  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/create-order/draft/${ORDER}` })
  await wait(`!!document.querySelector('.sk-svg')`, 'sketch canvas')
  assert.equal(await badge(), 'Original', 'canvas starts on the engine drawing')
  assert.equal(await evaluate(`document.querySelectorAll('.sk-tools .sk-tool').length`), 6, 'four quick tools, More and Delete')
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), 'no horizontal overflow at 1440')

  // Select a word on the canvas, then ask the assistant.
  await evaluate(`(()=>{const g=document.querySelector('.sk-svg g');g.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true})()`)
  await wait(`!!document.querySelector('.sk-box')`, 'word selected')
  await click('.sk-consent .sk-btn')
  await sendText('Move this word right 1 mm')
  await wait(`document.querySelectorAll('.sk-card:not(.sk-card--wait)').length===1`, 'proposal card 1')
  assert.equal(await badge(), 'Original', 'a proposal does not change the canvas')
  assert.equal(cursor, 2)
  assert.ok(log.some((l) => l.startsWith('ai base 1 sel {"word_ids":["w1"]}')), 'selection sent with the message: ' + log.join(' | '))
  await wait(`!!document.querySelector('.sk-card img')`, 'proposal picture')

  // Keep editing from version 1 -> version 2 built on it.
  await click('.sk-card-actions .sk-btn', 'Keep editing')
  await wait(`[...document.querySelectorAll('.sk-chip')].some(c=>c.textContent.includes('Version 1'))`, 'editing-from chip')
  await sendText('And a bit more')
  await wait(`document.querySelectorAll('.sk-card:not(.sk-card--wait)').length===2`, 'proposal card 2')
  assert.ok(log.includes('ai base 2 sel {"word_ids":["w1"]}'), 'second message built on version 1: ' + log.join(' | '))

  // Apply version 2, then go back to version 1.
  await evaluate(`document.querySelector('.sk-ai-list').scrollTo({top:99999})`)
  await sleep(300)
  await shot('1-proposals')
  await click('.sk-card-actions .sk-btn--solid', 'Apply edit')
  await wait(`document.querySelector('.sk-version .sk-badge').textContent==='Version 2'`, 'version 2 applied')
  assert.equal(await evaluate(`document.querySelectorAll('.sk-card.applied').length`), 1)
  await click('.sk-card .sk-btn--sm', 'Apply this version')
  await wait(`document.querySelector('.sk-version .sk-badge').textContent==='Version 1'`, 'version 1 applied again')

  // A manual edit starts from the applied version: the cursor goes back first.
  await evaluate(`(()=>{const g=document.querySelector('.sk-svg g');g.dispatchEvent(new MouseEvent('click',{bubbles:true}));return true})()`)
  await wait(`!!document.querySelector('.sk-box')`, 'word selected again')
  await click('.sk-params .sk-btn--solid', 'Apply')
  await wait(`document.querySelector('.sk-version .sk-badge').textContent==='Your version'`, 'manual edit applied')
  assert.ok(log.includes('undo 3->2') && log.includes('edit base 2 -> 4'), 'manual edit synced the cursor: ' + log.join(' | '))
  await wait(`[...document.querySelectorAll('.sk-card .sk-fine')].some(e=>e.textContent.includes('no longer'))`, 'version 2 is now out of reach')

  // Apply version 1 again (an ancestor), then submit: the workshop must get the applied version.
  await click('.sk-card .sk-btn--sm', 'Apply this version')
  await wait(`document.querySelector('.sk-version .sk-badge').textContent==='Version 1'`, 'version 1 applied before submit')
  await click('.co-next')
  await wait(`!!document.querySelector('.co-sum')`, 'review step')
  await click('.co-next')
  for (let i = 0; i < 100 && submittedAt === null; i++) await sleep(100)
  assert.equal(submittedAt, 2, 'submitted with the applied version current: ' + log.join(' | '))

  // Layout in the other languages and on a phone.
  for (const [lang, width] of [['vi', 1440], ['ja', 1024], ['vi', 390]]) {
    await evaluate(`localStorage.setItem('aivhrs-lang','${lang}')`)
    await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 500 })
    await command('Page.navigate', { url: `http://127.0.0.1:${port}/create-order/draft/${ORDER}` })
    await wait(`!!document.querySelector('.sk-svg')`, `canvas ${lang} ${width}`)
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), `overflow ${lang} ${width}`)
    await sleep(500)
    await shot(`2-${lang}-${width}`)
  }
  assert.deepEqual(errors, [], 'no page errors')
  console.log('sketch browser check ok')
  console.log(log.join('\n'))
} finally {
  try { ws?.close() } catch { /* closed */ }
  browser?.kill()
  server.close()
}
