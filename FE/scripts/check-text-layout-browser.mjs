// Real browser DOM test of the text placement controls and the writing-style cards of Create Order (2026-11-27), with every
// API call intercepted (no backend, no data). Covers: a card asks for the first line of the customer's words cut to the
// words (`fit=text`); when the live picture fails the template's stored sample is shown and the style can still be picked,
// a style with nothing to show is disabled; the placement (top / middle / bottom, four margins, line spacing) is saved in
// the text's `layout` and drawn by the styled preview on the sheet of the chosen paper; a stored placement comes back
// after a reload; styles of parts of the text follow the typing; the toolbar (select words, then italic, underline, double
// underline, strikethrough, a letter height, clear); paragraph settings made elsewhere survive (`keep_layout` first);
// the three languages at desktop and phone width. Run `npm run build` first.
// LAYOUT_REAL_API=http://127.0.0.1:8000 (a backend) with LAYOUT_REAL_TEMPLATE=<id> draws the pictures for the screenshots
// with real strokes instead of a one-pixel image; LAYOUT_SHOTS=<dir> keeps the screenshots.
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
assert.ok(existsSync(join(root, 'dist/index.html')), 'Run npm run build first')
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-text-layout-browser-'))
const shots = process.env.LAYOUT_SHOTS || scratch
const realApi = (process.env.LAYOUT_REAL_API || '').replace(/\/$/, '')
const realTemplate = process.env.LAYOUT_REAL_TEMPLATE || ''
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-11-27T00:00:00Z'
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
const STORED = 'https://media.test/fonts/dancing/preview.png'
const LETTER = 'Chúc mừng sinh nhật mẹ yêu\nCon chúc mẹ luôn mạnh khoẻ, vui vẻ và hạnh phúc bên gia đình mình. Con yêu mẹ nhiều lắm!'

const state = { order: null, input: null, puts: [], cards: [], previews: [], failLive: false }
const log = []
const TEMPLATES = [
  { id: 11, code: 'SINGLE', name: 'Single line', kind: 'SINGLE_LINE_FONT', preview_url: 'https://ai-vhrs.onrender.com/api/v1/catalog/templates/11/preview' },
  { id: 20, code: 'DANCING', name: 'Dancing Script', kind: 'TYPOGRAPHY', preview_url: STORED },
  { id: 30, code: 'NOTHING', name: 'No picture', kind: 'TYPOGRAPHY', preview_url: null },
]
const PAPERS = [
  { id: 1, code: 'P_A5', name: 'Plain A5', gsm: 100, surface: 'PLAIN', size: 'A5', unit_price: '1000', image_url: 'https://media.test/paper-a5.svg' },
  { id: 2, code: 'P_A4', name: 'Plain A4', gsm: 100, surface: 'PLAIN', size: 'A4', unit_price: '2000' },
  { id: 3, code: 'P_BROKEN', name: 'Unavailable photo A5', gsm: 100, surface: 'PLAIN', size: 'A5', unit_price: '1000', image_url: 'https://media.test/missing-paper.png' },
]
const newOrder = (type) => ({
  id: 88, code: 'VH-TL-1', order_type: type, order_status: 'DRAFT', production_status: 'NOT_STARTED',
  paper_type_id: null, pen_type_id: null, ink_color_id: null, workshop_suggest_materials: false, quantity: 1, char_count: null,
  estimated_price_min: null, estimated_price_max: null, customer_note: null, info_request_note: null, reject_reason: null, reject_note: null,
  eta: null, last_saved_at: now, submitted_at: null, created_at: now, inputs: [], warnings: [],
})
const orderOut = () => ({ ...state.order, inputs: state.input ? [state.input] : [] })

/** A picture: one pixel, or the real strokes from LAYOUT_REAL_API for the screenshots. */
async function picture(method, url, postData) {
  if (!realApi || !realTemplate) return [PNG, 200, 'image/png']
  const target = `${realApi}/api/v1/catalog/templates/${realTemplate}/preview${method === 'GET' ? url.search : ''}`
  const r = await fetch(target, method === 'GET' ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: postData })
  return [Buffer.from(await r.arrayBuffer()), r.status, r.headers.get('content-type') || 'image/png']
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

/** The fake backend: [body, status, mime]. */
async function answer(method, url, path, postData) {
  const host = url.hostname
  const body = postData && method !== 'GET' ? JSON.parse(postData) : {}
  if (host === 'media.test' && path === '/missing-paper.png') return ['', 404, 'image/png']
  if (host === 'media.test' && path === '/paper-a5.svg') return ['<svg xmlns="http://www.w3.org/2000/svg" width="420" height="594"><rect width="420" height="594" fill="#bc955e"/><path d="M40 60H380M40 100H380M40 140H380M40 180H380" stroke="#715b40"/></svg>', 200, 'image/svg+xml']
  if (host === 'media.test') return realApi && realTemplate ? picture('GET', new URL(`http://x/?fit=text&text=${encodeURIComponent('Xin chào Việt Nam')}`)) : [PNG, 200, 'image/png']
  if (path === '/me') return [{ id: 17, email: 'test@example.test', full_name: 'Browser Test', role: 'CUSTOMER', status: 'ACTIVE', addresses: [], created_at: now }]
  if (path === '/studio/assistant/status') return [{ enabled: false, available: false, providers: [], messages_left_today: 0, daily_message_limit: 30, sends_photos: false }]
  if (path === '/catalog/papers') return [PAPERS]
  if (path === '/catalog/templates') return [TEMPLATES]
  if (path.startsWith('/catalog/pens')) return [[]]
  const preview = /^\/catalog\/templates\/(\d+)\/preview$/.exec(path)
  if (preview && method === 'GET') {
    const id = Number(preview[1])
    state.cards.push({ id, fit: url.searchParams.get('fit'), text: url.searchParams.get('text') })
    if (id === 30 || (id === 20 && state.failLive)) return [{ error: { code: 'UNSUPPORTED_CHARS', message: 'x' } }, 422]
    return picture('GET', url)
  }
  if (preview && method === 'POST') { state.previews.push({ id: Number(preview[1]), ...body }); return picture('POST', url, postData) }
  if (path === '/pricing/estimate') return [{ chars_min: 10, chars_max: 10, price_min: '10000', price_max: '12000', min_deposit_pct: '50', basis: 'CHARS', materials_priced: false }]
  if (path.includes('notifications')) return [{ items: [], total: 0, unread_count: 0 }]
  if (path.includes('conversations')) return [path.endsWith('unread-count') ? { unread_count: 0 } : { items: [], total: 0 }]
  if (path === '/orders' && method === 'POST') { state.order = newOrder(body.order_type); return [orderOut(), 201] }
  if (path === '/orders') return [{ items: state.order ? [orderOut()] : [], total: state.order ? 1 : 0, page: 1, page_size: 20 }]
  if (path === '/orders/88' && (method === 'GET' || method === 'PATCH')) {
    if (method === 'PATCH') Object.assign(state.order, body)
    return [orderOut()]
  }
  if (path === '/orders/88/inputs/text' && method === 'PUT') {
    state.puts.push(body)
    // As the backend: a layout sent replaces the stored one; keep_layout carries the stored one over; nothing = the default.
    const layout = body.layout ?? (body.keep_layout && state.input?.layout ? state.input.layout : { version: 1, vertical_align: 'MIDDLE' })
    state.input = {
      id: 5, kind: 'TEXT_CONTENT', sort_order: 1, mime_type: null, file_size_bytes: null, quality_result: null, is_quality_warning: false,
      text_content: body.text_content, template_id: body.template_id ?? null, font_size_mm: body.font_size_mm ? String(body.font_size_mm) : null,
      alignment: body.alignment ?? 'CENTER', canvas_data: null, layout,
    }
    return [state.input]
  }
  if (path === '/orders/88/sketch' && method === 'GET') return [{ error: { code: 'SKETCH_NOT_GENERATED', message: 'No sketch' } }, 404]
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
      const [data, code = 200, mime = 'application/json'] = await answer(request.method, u, path, request.postData)
      await fulfill(requestId, data, code, mime)
    } catch (e) {
      // A preview the page gave up on (new words typed meanwhile) is gone by the time a real picture arrives: not a failure.
      if (String(e.message).includes('Invalid InterceptionId')) return
      errors.push(e.message)
      await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500).catch(() => undefined)
    }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:'customer',apiRole:'CUSTOMER'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}\n${log.slice(-12).join('\n')}\n${await evaluate('document.body.innerText')}`) }
  /** A screenshot of the page, or of one element (`selector`) wherever it is on the page. */
  const shot = async (name, selector) => {
    const clip = selector ? await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: r.left + scrollX, y: r.top + scrollY, width: r.width, height: r.height, scale: 1 } })()`) : undefined
    const r = await command('Page.captureScreenshot', { format: 'png', ...(clip ? { clip, captureBeyondViewport: true } : {}) })
    const f = join(shots, name); await writeFile(f, Buffer.from(r.data, 'base64')); console.log('Screenshot: ' + f)
  }
  const noOverflow = async (label) => assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth + 1'), false, `horizontal overflow: ${label}`)
  const until = async (ok, label) => { for (let i = 0; i < 120; i++) { if (ok()) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}\n${log.slice(-14).join('\n')}`) }
  const setLang = async (lang) => { await evaluate(`localStorage.setItem('aivhrs-lang', ${JSON.stringify(lang)})`) }
  /** Types into a React-controlled field (`node` is an expression giving the element). */
  const type = (node, value) => evaluate(`(() => { const el = ${node}; const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })) })()`)
  const card = (name) => `[...document.querySelectorAll('.co-tray--3 .co-font')].find((b) => b.textContent.includes(${JSON.stringify(name)}))`
  const seg = (group, n) => `document.querySelectorAll('.co-sub .co-group')[${group}].querySelectorAll('.co-seg button')[${n}]`
  const field = (n) => `document.querySelectorAll('.co-place-grid input')[${n}]`
  const lastPut = () => state.puts.at(-1)
  const lastView = () => state.previews.at(-1)

  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1500, deviceScaleFactor: 1, mobile: false })
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/create-order#mode=text` })
  await wait(`!!document.querySelector('textarea') && document.querySelectorAll('.co-tray--3 .co-font').length === 3`, 'the form and three writing styles')

  // ---- cards: the first line of the customer's words, cut to the words; a style with nothing to show is off
  await type(`document.querySelector('textarea')`, LETTER)
  await until(() => state.cards.some((c) => c.id === 20 && c.text === 'Chúc mừng sinh nhật mẹ yêu'), 'the card asks for the first line')
  // The same route without `fit` is the whole-sheet picture of the side preview; a card always asks with `fit=text`.
  const cut = () => state.cards.filter((c) => c.fit === 'text')
  for (const id of [11, 20, 30]) assert.ok(cut().some((c) => c.id === id), `the card of style ${id} asks for a picture cut to the words`)
  assert.ok(cut().every((c) => (c.text ?? '').length <= 40 && !c.text.includes('\n')), 'a card never sends more than the first 40 characters')
  await wait(`${card('No picture')}.disabled === true`, 'the style without any picture is off')
  assert.equal(await evaluate(`${card('Dancing Script')}.disabled || ${card('Single line')}.disabled`), false)
  assert.equal(await evaluate(`${card('Dancing Script')}.querySelector('img').src.includes('fit=text')`), true)

  // ---- live picture fails: the stored sample is shown and the style can still be picked
  state.failLive = true
  await type(`document.querySelector('textarea')`, LETTER + ' ♥')
  await type(`document.querySelector('textarea')`, 'Mẹ ơi\n' + LETTER)
  await wait(`${card('Dancing Script')}.querySelector('img')?.src === ${JSON.stringify(STORED)}`, 'the stored sample replaces the failed live picture')
  assert.equal(await evaluate(`${card('Dancing Script')}.disabled`), false, 'a failed live picture does not switch the style off')
  // the stored address of a template without a stored picture is the backend's own preview, asked cut to the words
  state.failLive = false

  // ---- pick the style: the text is saved with the default placement (middle, 15 mm, spacing 1)
  await evaluate(`${card('Dancing Script')}.click()`)
  await until(() => state.puts.length >= 1, 'the text is saved')
  assert.deepEqual(lastPut().layout, { version: 1, vertical_align: 'MIDDLE', margins_mm: { top: 15, bottom: 15, left: 15, right: 15 }, line_spacing: 1 })
  assert.equal(lastPut().keep_layout, undefined)
  await wait(`!!document.querySelector('.co-live-img')`, 'the styled preview')
  await until(() => lastView()?.paper_size === 'A5' && lastView().alignment === 'CENTER', 'the preview is drawn on A5, centred until an alignment is picked')
  await shot('layout-default-1440.png', '.co-root')

  // ---- placement: bottom, right aligned, margins and line spacing
  const before = state.puts.length
  await evaluate(`${seg(0, 3)}.click()`)                                    // alignment: right
  await evaluate(`${seg(1, 2)}.click()`)                                    // position: bottom
  await type(field(1), '30'); await type(field(3), '25'); await type(field(4), '1.4')
  await until(() => state.puts.length > before && lastPut().layout?.vertical_align === 'BOTTOM' && lastPut().layout.line_spacing === 1.4, 'the placement is saved')
  assert.deepEqual(lastPut().layout, { version: 1, vertical_align: 'BOTTOM', margins_mm: { top: 15, bottom: 30, left: 15, right: 25 }, line_spacing: 1.4 })
  assert.equal(lastPut().alignment, 'RIGHT')
  await until(() => lastView()?.layout?.vertical_align === 'BOTTOM' && lastView().alignment === 'RIGHT', 'the preview follows the placement')
  assert.deepEqual(lastView().layout.margins_mm, { top: 15, bottom: 30, left: 15, right: 25 })
  assert.ok(lastView().text.length > 80, 'the preview draws the whole text, not 80 characters')
  assert.equal(await evaluate(`${seg(1, 2)}.getAttribute('aria-pressed')`), 'true')
  await shot('layout-bottom-right-1440.png', '.co-root')
  // out of range values are brought into range before they are sent
  const b2 = state.puts.length
  await type(field(0), '200'); await type(field(4), '9')
  await until(() => state.puts.length > b2 && lastPut().layout.margins_mm.top === 80 && lastPut().layout.line_spacing === 2.5, 'limits are applied')
  await type(field(0), '15'); await type(field(4), '1.4')
  await until(() => lastPut().layout.margins_mm.top === 15 && lastPut().layout.line_spacing === 1.4, 'back in range')

  // ---- a reload reads the placement back; the sheet is the chosen paper's
  state.order.paper_type_id = 2
  state.input.layout = { ...state.input.layout, spans: [{ start: 0, end: 4, italic: true }] }      // styles made by the assistant
  state.previews.length = 0
  // A draft that already has its words opens on the next step: step 1 (the words) is one click back.
  const openDraft = async () => {
    await command('Page.navigate', { url: `http://127.0.0.1:${port}/create-order/draft/88` })
    await wait(`!!document.querySelector('.co-steps .co-step')`, 'the draft')
    await evaluate(`document.querySelector('.co-steps .co-step').click()`)
  }
  await openDraft()
  await wait(`document.querySelectorAll('.co-place-grid input').length === 5 && ${field(1)}.value === '30'`, 'the stored placement is back in the form')
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('.co-place-grid input')].map((i) => i.value)`), ['15', '30', '15', '25', '1.4'])
  assert.equal(await evaluate(`${seg(1, 2)}.getAttribute('aria-pressed')`), 'true')
  await until(() => lastView()?.paper_size === 'A4', 'the preview is drawn on the sheet of the chosen paper')
  assert.deepEqual(lastView().layout.spans, [{ start: 0, end: 4, italic: true }], 'stored styles are drawn while the text is the stored one')
  await wait(`document.body.innerText.includes('A4')`, 'the caption names the sheet')
  const settled = state.puts.length
  await sleep(1500)
  assert.equal(state.puts.length, settled, 'opening a draft saves nothing back')

  // ---- styles of parts of the text survive: a placement change carries them, and they follow the typing (one save, no keep_layout)
  await evaluate(`${seg(1, 0)}.click()`)                                    // position: top
  await until(() => state.puts.length === settled + 1, 'one save for a placement change')
  assert.equal(lastPut().layout.vertical_align, 'TOP')
  assert.deepEqual(lastPut().layout.spans, [{ start: 0, end: 4, italic: true }])
  const WORDS = 'Mẹ ơi\n' + LETTER + ' Thương mẹ.'
  let n = state.puts.length
  await type(`document.querySelector('textarea')`, WORDS)                   // typed after the styled part: it stays
  await until(() => state.puts.length === n + 1, 'one save when words are added after a styled part')
  assert.equal(lastPut().keep_layout, undefined)
  assert.deepEqual(lastPut().layout.spans, [{ start: 0, end: 4, italic: true }])
  await type(`document.querySelector('textarea')`, 'Ôi ' + WORDS)           // typed before it: it moves along
  await until(() => lastPut().layout.spans?.[0]?.start === 3, 'the styled part follows its characters')
  assert.deepEqual(lastPut().layout.spans, [{ start: 3, end: 7, italic: true }])

  // ---- the toolbar: select words in the box, then a style; the box itself never shows a style
  const select = (from, to) => evaluate(`(() => { const el = document.querySelector('textarea'); el.focus(); el.setSelectionRange(${from}, ${to}) })()`)
  const tool = (i) => `document.querySelectorAll('.co-fmt-row .co-fmt-btn')[${i}]`     // italic, underline, double, strike, apply height, clear
  const spansSaved = (want, label) => until(() => JSON.stringify(lastPut().layout.spans ?? []) === JSON.stringify(want), label)
  assert.equal(await evaluate(`document.querySelectorAll('.co-fmt-row .co-fmt-btn').length`), 6)
  n = state.puts.length
  await select(2, 2)
  await evaluate(`${tool(1)}.click()`)
  await wait(`!!document.querySelector('.co-fmt-note')`, 'a note asks for a selection')
  await sleep(1200)
  assert.equal(state.puts.length, n, 'nothing is saved without a selection')
  await select(0, 5)                                                        // "Ôi Mẹ": overlaps the italic part [3, 7)
  await evaluate(`${tool(1)}.click()`)
  await spansSaved([{ start: 0, end: 3, underline: 'single' }, { start: 3, end: 5, italic: true, underline: 'single' }, { start: 5, end: 7, italic: true }], 'underline over part of an italic part splits it')
  await select(8, 12)
  await type(`document.querySelector('.co-fmt-size input')`, '2')
  await evaluate(`${tool(4)}.click()`)
  await wait(`document.querySelector('.co-fmt-note')?.innerText.includes('4')`, 'a letter height out of range is refused')
  await type(`document.querySelector('.co-fmt-size input')`, '14')
  await evaluate(`${tool(4)}.click()`)
  await until(() => (lastPut().layout.spans ?? []).some((x) => x.start === 8 && x.end === 12 && x.size_mm === 14), 'a letter height of its own')
  await select(8, 12)
  await evaluate(`${tool(2)}.click()`)                                      // double underline on the same words
  await evaluate(`${tool(3)}.click()`)                                      // and strikethrough
  await until(() => (lastPut().layout.spans ?? []).some((x) => x.start === 8 && x.size_mm === 14 && x.underline === 'double' && x.strike === true), 'styles add up on the same words')
  assert.equal(await evaluate(`document.querySelectorAll('.co-fmt-list li').length`), 4)
  assert.equal(await evaluate(`document.querySelector('textarea').value`), 'Ôi ' + WORDS, 'the box keeps the plain words')
  await until(() => lastView()?.layout?.spans?.length === 4, 'the preview is asked with the styles')
  await shot('layout-styles-1440.png', '.co-root')
  await select(0, 5)
  await evaluate(`${tool(1)}.click()`)                                      // underline again: taken off
  await until(() => !(lastPut().layout.spans ?? []).some((x) => x.underline === 'single'), 'the same style again takes it off')
  await evaluate(`document.querySelector('.co-fmt-list li .co-fmt-part').click()`)   // a part in the list selects its words
  assert.deepEqual(await evaluate(`[document.querySelector('textarea').selectionStart, document.querySelector('textarea').selectionEnd]`), [3, 7])
  await evaluate(`document.querySelector('.co-fmt-list li .co-fmt-x').click()`)      // the cross removes that part
  await until(() => (lastPut().layout.spans ?? []).length === 1 && lastPut().layout.spans[0].start === 8, 'the cross removes one part')
  await select(8, 12)
  await evaluate(`${tool(5)}.click()`)                                      // clear formatting
  await until(() => lastPut().layout.spans === undefined, 'clearing leaves no spans in the layout')
  assert.equal(await evaluate(`document.querySelectorAll('.co-fmt-list li').length`), 0)

  // ---- settings of single paragraphs (made by the assistant) are carried by the backend: text first with keep_layout
  state.input.layout = { ...state.input.layout, paragraphs: [{ index: 0, alignment: 'LEFT' }] }
  await openDraft()
  await wait(`document.querySelectorAll('.co-place-grid input').length === 5`, 'the draft with paragraph settings')
  n = state.puts.length
  await type(`document.querySelector('textarea')`, 'Ôi ' + WORDS + ' Hết.')
  await until(() => state.puts.length === n + 2, 'two saves when the words change under paragraph settings')
  assert.equal(state.puts[n].keep_layout, true)
  assert.equal(state.puts[n].layout, undefined)
  assert.deepEqual(state.puts[n + 1].layout.paragraphs, [{ index: 0, alignment: 'LEFT' }])
  assert.equal(state.puts[n + 1].layout.vertical_align, 'TOP')

  // ---- paper photos: selection updates both previews, missing/broken photos remain selectable.
  await evaluate(`document.querySelectorAll('.co-steps .co-step')[1].click()`)
  await wait(`document.querySelectorAll('.co-opt .co-paper-thumb').length === 3`, 'paper thumbnails')
  const paperChoice = (name) => `[...document.querySelectorAll('.co-opt')].find((b) => b.textContent.includes(${JSON.stringify(name)}))`
  await evaluate(`${paperChoice('Plain A5')}.click()`)
  await wait(`document.querySelector('.co-rail .co-paper-photo summary')?.textContent.includes('Plain A5')`, 'selected paper beside the preview')
  await evaluate(`document.querySelector('.co-rail .co-paper-photo summary').click()`)
  await wait(`document.querySelector('.co-rail .co-paper-photo-full')?.naturalWidth === 420`, 'the full paper photo loads')
  await shot('paper-photo-materials-1440.png', '.co-root')
  await evaluate(`${paperChoice('Plain A4')}.click()`)
  await wait(`document.querySelector('.co-rail .co-paper-label')?.textContent.includes('Plain A4')`, 'paper without a photo')
  assert.equal(await evaluate(`!!document.querySelector('.co-rail .co-paper-photo-full')`), false, 'the previous photo is removed')
  await evaluate(`${paperChoice('Unavailable photo A5')}.click()`)
  await wait(`document.querySelector('.co-rail .co-paper-photo summary')?.textContent.includes('Unavailable photo A5')`, 'paper with a broken photo remains selectable')
  await evaluate(`document.querySelector('.co-rail .co-paper-photo summary').click()`)
  await wait(`document.querySelector('.co-rail .co-paper-photo [role="status"]')?.textContent.includes('could not be loaded')`, 'photo error fallback')
  await evaluate(`${paperChoice('Plain A5')}.click()`)
  await wait(`document.querySelector('.co-rail .co-paper-photo summary')?.textContent.includes('Plain A5')`, 'switching back to a working photo')
  await until(() => state.order.paper_type_id === 1, 'the chosen paper is saved before reloading')

  // ---- languages and widths
  for (const lang of ['vi', 'ja']) {
    await setLang(lang)
    for (const [w, h] of [[1440, 1500], [390, 1500]]) {
      await command('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 500 })
      await openDraft()
      await wait(`document.querySelectorAll('.co-place-grid input').length === 5`, `placement controls (${lang}, ${w})`)
      const paperLabel = lang === 'vi' ? 'Giấy:' : '用紙:'
      await wait(`document.querySelector('.co-body .co-paper-photo summary')?.textContent.includes(${JSON.stringify(paperLabel)})`, 'translated paper label')
      await evaluate(`document.querySelector('.co-body .co-paper-photo summary').click()`)
      await wait(`document.querySelector('.co-body .co-paper-photo-full')?.naturalWidth === 420`, 'paper photo at this viewport')
      const words = await evaluate(`[...document.querySelectorAll('.co-sub .co-group')].slice(1, 3).map((g) => g.innerText).join(' ')`)
      for (const en of ['Position on the sheet', 'Top', 'Middle', 'Bottom', 'Margins', 'Line spacing', 'Left', 'Right']) assert.ok(!words.includes(en), `English "${en}" left in ${lang}`)
      const bar = await evaluate(`document.querySelector('.co-fmt')?.innerText ?? ''`)
      for (const en of ['Format part', 'Italic', 'Underline', 'Strikethrough', 'Clear formatting', 'Letter height']) assert.ok(bar && !bar.includes(en), `English "${en}" left in the format bar (${lang})`)
      await noOverflow(`${lang} ${w}`)
      if (lang === 'vi') await shot(`layout-vi-${w}.png`, '.co-root')
    }
  }
  assert.deepEqual(errors, [], 'no page errors')
  console.log('PASS: writing-style cards (first line, cut to the words, stored sample when the live picture fails, nothing to show = off), placement (top / middle / bottom, margins, line spacing, limits) saved in the layout and drawn by the preview on the chosen sheet, reload, styles of parts of the text (follow the typing, toolbar, list, clear), paragraph settings kept (keep_layout first), vi/ja at 1440 and 390. All API calls intercepted.')
} finally {
  try { ws?.close() } catch { /* closing */ }
  browser?.kill()
  server.close()
}
