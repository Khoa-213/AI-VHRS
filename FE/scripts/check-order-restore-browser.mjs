// Real Edge DOM test of the restored preview in Create Order's upload mode, with every API call intercepted (no backend, no data).
// Covers: the panel appears once a photo is uploaded, "Preview restoration" calls POST /orders/{id}/sketch/generate with
// discard_edits and shows the restored sketch under the photos (the right-hand box keeps the original photo), the engine's notes,
// "Restore again" and the stale notice after a rotation, the PDF case (button off), an engine error, a reload that reads the
// saved restoration back, and the three languages at desktop and phone width. Run `npm run build` first.
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
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-order-restore-browser-'))
const shots = process.env.RESTORE_SHOTS || scratch
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-11-26T00:00:00Z'
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64')
const NOTE = 'Ảnh hơi nghiêng; đã nắn lại trước khi dò nét.'

const state = { order: null, sketch: null, inputs: [], nextInput: 1, generate: [], failGenerate: false, notes: [NOTE] }
const log = []
const newOrder = () => ({
  id: 88, code: 'VH-RS-1', order_type: 'OT1_COPY_RESTORE', order_status: 'DRAFT', production_status: 'NOT_STARTED',
  paper_type_id: null, pen_type_id: null, ink_color_id: null, workshop_suggest_materials: false, quantity: 1, char_count: null,
  estimated_price_min: null, estimated_price_max: null, customer_note: null, info_request_note: null, reject_reason: null, reject_note: null,
  eta: null, last_saved_at: now, submitted_at: null, created_at: now, inputs: [], warnings: [],
})
const photo = (id, mime) => ({
  id, kind: 'ORIGINAL_IMAGE', sort_order: id, mime_type: mime, file_size_bytes: 1000, quality_result: null, is_quality_warning: false,
  rotation_deg: 0, crop_box: null, text_content: null, template_id: null, font_size_mm: null, alignment: null, canvas_data: null,
})
const orderOut = () => ({ ...state.order, inputs: state.inputs })
const sketchOut = (warnings = []) => ({
  revision: { id: state.sketch.rev, seq: state.sketch.rev, parent_id: null, author: 'ENGINE', note: null, created_at: now },
  is_current: true, can_undo: false, can_redo: false, inputs_changed: state.sketch.changed, limits: {}, warnings,
  document: { pages: [{ no: 1, width_mm: 210, height_mm: 297, strokes: [{ id: 's1', kind: 'base', points: [[20, 30], [60, 32]] }], words: [], lines: [], paragraphs: [] }] },
})

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
function answer(method, host, path, postData) {
  const body = postData ? JSON.parse(postData) : {}
  if (host === 'storage.test') return ['', 200, 'text/plain']                       // the signed PUT of the photo itself
  if (path === '/me') return [{ id: 17, email: 'test@example.test', full_name: 'Browser Test', role: 'CUSTOMER', status: 'ACTIVE', addresses: [], created_at: now }]
  if (path === '/studio/assistant/status') return [{ enabled: false, available: false, providers: [], messages_left_today: 0, daily_message_limit: 30, sends_photos: false }]
  if (path === '/catalog/papers' || path === '/catalog/templates' || path.startsWith('/catalog/pens')) return [[]]
  if (path === '/pricing/estimate') return [{ chars_min: 0, chars_max: 0, price_min: '10000', price_max: '12000', min_deposit_pct: '50', basis: 'IMAGE_ESTIMATE', materials_priced: false }]
  if (path.includes('notifications')) return [{ items: [], total: 0, unread_count: 0 }]
  if (path.includes('conversations')) return [path.endsWith('unread-count') ? { unread_count: 0 } : { items: [], total: 0 }]
  if (path === '/orders' && method === 'POST') { state.order = newOrder(); return [orderOut(), 201] }
  if (path === '/orders') return [{ items: state.order ? [orderOut()] : [], total: state.order ? 1 : 0, page: 1, page_size: 20 }]
  if (path === '/orders/88' && method === 'GET') return [orderOut()]
  if (path === '/orders/88' && method === 'PATCH') return [orderOut()]
  if (path === '/orders/88/inputs/upload-url') {
    const p = photo(state.nextInput++, body.mime_type)
    state.inputs.push(p)
    return [{ input_id: p.id, upload_url: `https://storage.test/up/${p.id}`, method: 'PUT' }, 201]
  }
  const confirm = /^\/orders\/88\/inputs\/(\d+)\/confirm$/.exec(path)
  if (confirm) {
    const p = state.inputs.find((i) => i.id === Number(confirm[1]))
    p.quality_result = { ok: true }
    if (state.sketch) state.sketch.changed = true
    return [p]
  }
  const one = /^\/orders\/88\/inputs\/(\d+)$/.exec(path)
  if (one && method === 'PATCH') {
    const p = state.inputs.find((i) => i.id === Number(one[1]))
    Object.assign(p, body)
    if (state.sketch) state.sketch.changed = true
    return [p]
  }
  if (one && method === 'DELETE') { state.inputs = state.inputs.filter((i) => i.id !== Number(one[1])); if (state.sketch) state.sketch.changed = true; return ['', 204] }
  if (/^\/orders\/88\/inputs\/\d+\/file$/.test(path)) return [{ url: 'https://storage.test/photo.png' }]
  if (path === '/photo.png') return [PNG, 200, 'image/png']
  if (path === '/orders/88/sketch/generate') {
    state.generate.push(body)
    if (state.inputs.some((i) => i.mime_type === 'application/pdf')) return [{ error: { code: 'PDF_NOT_SUPPORTED_AI', message: 'PDF' } }, 422]
    if (state.failGenerate) return [{ error: { code: 'STORAGE_UNAVAILABLE', message: 'Kho lưu trữ đang lỗi.' } }, 503]
    state.sketch = { rev: (state.sketch?.rev ?? 40) + 1, changed: false }
    return [sketchOut(state.notes), 201]
  }
  if (path === '/orders/88/sketch' && method === 'GET') return state.sketch ? [sketchOut()] : [{ error: { code: 'SKETCH_NOT_GENERATED', message: 'No sketch' } }, 404]
  if (path === '/orders/88/sketch/preview') return [PNG, 200, 'image/png']
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
      const [data, code = 200, mime = 'application/json'] = answer(request.method, u.hostname, path, request.method === 'PUT' && u.hostname === 'storage.test' ? null : request.postData)
      await fulfill(requestId, data, code, mime)
    } catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
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
  const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.innerText ?? ''`)
  const restoreBtn = `document.querySelector('.co-restore-head button')`
  const upload = (name, mime) => evaluate(`(() => { const input = document.querySelector('.co-drop input[type=file]'); const dt = new DataTransfer(); dt.items.add(new File([new Uint8Array([1,2,3])], ${JSON.stringify(name)}, { type: ${JSON.stringify(mime)} })); input.files = dt.files; input.dispatchEvent(new Event('change', { bubbles: true })) })()`)
  // A saved draft with content opens on the materials step: go back to the first one.
  const firstStep = async () => { await wait(`!!document.querySelector('.co-step')`, 'steps'); await evaluate(`document.querySelector('.co-step').click()`); await sleep(150) }
  const setLang = async (lang) => { await evaluate(`localStorage.setItem('aivhrs-lang', ${JSON.stringify(lang)})`) }

  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })

  // 1. Upload mode, no photo yet: no restoration panel.
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/create-order#mode=upload` })
  await wait(`!!document.querySelector('.co-drop')`, 'upload mode')
  assert.equal(await evaluate(`!!document.querySelector('.co-restore')`), false, 'no panel before a photo')

  // 2. One JPG: the panel offers "Preview restoration"; the right box shows the original photo, not a sketch.
  await upload('letter.jpg', 'image/jpeg')
  await wait(`!!document.querySelector('.co-restore') && !!${restoreBtn} && !${restoreBtn}.disabled`, 'restore button on')
  assert.equal((await text('.co-restore-head button')).trim(), 'Preview restoration')
  assert.equal(await evaluate(`!!document.querySelector('.co-restore .oa-view')`), false, 'nothing restored yet')
  await shot('restore-1-before.png')

  // 3. Restore: generate with discard_edits, the sketch under the photos, the engine's note, the button turns to "Restore again".
  await evaluate(`${restoreBtn}.click()`)
  await wait(`!!document.querySelector('.co-restore .oa-view img.oa-view-img')`, 'restored sketch shown')
  assert.deepEqual(state.generate.at(-1), { discard_edits: true })
  assert.ok((await text('.co-restore-notes')).includes(NOTE), 'engine note shown as received')
  assert.equal((await text('.co-restore-head button')).trim(), 'Restore again')
  assert.equal(await evaluate(`!!document.querySelector('.co-rail .co-preview .oa-view')`), false, 'right box keeps the original, not the sketch')
  assert.equal(await evaluate(`!!document.querySelector('.co-restore .oa-stale')`), false, 'fresh restoration is not stale')
  await noOverflow('restored 1440'); await shot('restore-2-restored.png', '.co-restore')

  // 4. Rotating a photo makes the restoration stale until it is drawn again.
  await evaluate(`[...document.querySelectorAll('.co-file-row button, .co-photo button')].find(b => /rotat/i.test(b.getAttribute('aria-label') || b.title || b.textContent))?.click()`)
  await wait(`!!document.querySelector('.co-restore .oa-stale')`, 'stale notice after rotation')
  await evaluate(`${restoreBtn}.click()`)
  await wait(`!document.querySelector('.co-restore .oa-stale') && document.querySelector('.co-restore-head button').textContent.trim() === 'Restore again'`, 'fresh again')
  assert.equal(state.generate.length, 2)

  // 5. A reload reads the saved restoration back (GET /sketch), without the notes of the drawing.
  assert.equal(await evaluate('location.pathname'), '/create-order/draft/88')
  await command('Page.reload')
  await firstStep()
  await wait(`!!document.querySelector('.co-restore .oa-view img.oa-view-img')`, 'restoration after reload')
  assert.equal(await evaluate(`!!document.querySelector('.co-restore-notes')`), false, 'notes only for a drawing just made')
  assert.equal(state.generate.length, 2, 'a reload does not draw again')

  // 6. An engine failure shows the error and keeps the button.
  state.failGenerate = true
  await evaluate(`${restoreBtn}.click()`)
  await wait(`!!document.querySelector('.lg-error')`, 'engine error shown')
  assert.equal(await evaluate(`${restoreBtn}.disabled`), false, 'can try again')
  state.failGenerate = false

  // 7. A PDF among the photos: the button is off and the PDF note says why; the server is not asked.
  const before = state.generate.length
  await upload('scan.pdf', 'application/pdf')
  await wait(`${restoreBtn}.disabled && document.querySelector('.co-restore').innerText.includes('PDF')`, 'PDF disables restore')
  assert.equal(state.generate.length, before)

  // 8. Vietnamese and Japanese, desktop and phone width.
  for (const lang of ['vi', 'ja']) {
    await setLang(lang)
    for (const [w, h] of [[1440, 1100], [390, 900]]) {
      await command('Emulation.setDeviceMetricsOverride', { width: w, height: h, deviceScaleFactor: 1, mobile: w < 500 })
      await command('Page.reload')
      await firstStep()
      await wait(`!!document.querySelector('.co-restore-title')`, `${lang} ${w}`)
      const title = await text('.co-restore-title')
      assert.notEqual(title.trim(), 'Restored preview', `${lang}: title translated`)
      await noOverflow(`${lang} ${w}`)
      await evaluate(`document.querySelector('.co-restore').scrollIntoView({ block: 'center' })`)
      await shot(`restore-3-${lang}-${w}.png`, '.co-restore')
    }
  }

  assert.deepEqual(errors, [], errors.join('\n'))
  console.log('PASS: upload-mode restoration (panel after upload, generate with discard_edits, sketch under the photos, original kept on the right, engine notes, stale after rotation, restore again, reload reads it back, engine error, PDF disables it, vi/ja at 1440 and 390). All API calls intercepted.')
} finally {
  try { ws?.close() } catch { /* closing */ }
  browser?.kill()
  server.close()
}
