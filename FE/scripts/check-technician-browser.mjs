// Real Edge DOM smoke test, with all API/storage calls intercepted. No production credentials or data.
import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { createServer } from 'node:http'
import { readFile, mkdtemp, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'
import { deflateSync } from 'node:zlib'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const edge = process.env.TECH_BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
assert.ok(existsSync(edge), 'Set TECH_BROWSER_PATH to an installed Chromium/Edge executable')
assert.ok(existsSync(join(root, 'dist/index.html')), 'Run npm.cmd run build first')
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-tech-browser-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-10-23T03:00:00Z'
const bytes = Buffer.from(JSON.stringify({ format: 'vhrs-trajectory-v1', pages: [{ paper: { width_mm: 148, height_mm: 210 }, strokes: [{ points: [[10, 10], [100, 80]] }] }] }))
const hash = createHash('sha256').update(bytes).digest('hex')
const job = { id: 9, order_id: 42, order_code: 'VH-BROWSER-TEST', robot_id: 3, robot_code: 'FR3-03', technician_id: 17, technician_name: 'Browser Test', status: 'SCHEDULED', is_rewrite: false,
  slot_start: now, slot_end: now, estimated_duration_min: 30, package_hash: hash, progress_pct: null, downloaded_at: null, started_at: null, finished_at: null, simulation_passed: null,
  order_type: 'OT3_TEMPLATE', quantity: 1, eta: null, paper_name: 'A5', pen_name: 'Test pen', ink_name: 'Test ink', approach_note: null, calibration: null, incidents: [] }
const events = [], photos = [], writes = []
let lastPhoto = 0, failRegisterOnce = false, badHash = true, incidentCount = 0, conflictOnce = true
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

// Minimal PNG fixture at the production photo resolution, generated locally for this test.
function crc32(data) { let c = 0xffffffff; for (const b of data) { c ^= b; for (let i = 0; i < 8; i++) c = (c >>> 1) ^ ((c & 1) ? 0xedb88320 : 0) } return (c ^ 0xffffffff) >>> 0 }
function chunk(type, data) { const name = Buffer.from(type); const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([name, data]))); return Buffer.concat([len, name, data, crc]) }
const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(1280); ihdr.writeUInt32BE(720, 4); ihdr[8] = 8; ihdr[9] = 2
const png = Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(Buffer.alloc((1280 * 3 + 1) * 720, 0))), chunk('IEND', Buffer.alloc(0))])
const photoFile = join(scratch, 'product.png'); await writeFile(photoFile, png)

try {
  browser = spawn(edge, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort, 'Browser did not expose a debugging port')
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((v) => v.type === 'page').webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let nextId = 0
  const pending = new Map()
  const command = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout: ' + method)) }, 15000); pending.set(id, { resolve: (value) => { clearTimeout(timer); resolve(value) }, reject: (error) => { clearTimeout(timer); reject(error) } }); ws.send(JSON.stringify({ id, method, params })) })
  const fulfill = (id, data, code = 200, mime = 'application/json') => command('Fetch.fulfillRequest', { requestId: id, responseCode: code, responseHeaders: [{ name: 'Content-Type', value: mime }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET,POST,PATCH,PUT,DELETE,OPTIONS' }], body: (Buffer.isBuffer(data) ? data : Buffer.from(JSON.stringify(data))).toString('base64') })
  const event = (type) => events.push({ id: events.length + 1, event_type: type, occurred_at: now, stroke_index: null, payload: null, force_summary: null })
  ws.onmessage = async (message) => {
    const msg = JSON.parse(message.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) msg.error ? p.reject(new Error(JSON.stringify(msg.error))) : p.resolve(msg.result); return }
    if (msg.method === 'Page.javascriptDialogOpening') { void command('Page.handleJavaScriptDialog', { accept: true }); return }
    if (msg.method === 'Runtime.exceptionThrown') { errors.push(msg.params.exceptionDetails.text); return }
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    try {
      const u = new URL(request.url)
      if (u.hostname === '127.0.0.1') { await command('Fetch.continueRequest', { requestId }); return }
      if (request.method === 'OPTIONS') { await fulfill(requestId, {}, 200); return }
      if (u.hostname === 'storage.test') {
        assert.ok(!request.headers.Authorization, 'Storage request leaked a bearer token')
        await fulfill(requestId, u.pathname === '/trajectory' ? (badHash ? Buffer.from('tampered') : bytes) : png, 200, u.pathname === '/trajectory' ? 'application/json' : 'image/png'); return
      }
      if (!u.pathname.startsWith('/api/v1/')) { await fulfill(requestId, {}, 200); return }
      const path = u.pathname.slice('/api/v1'.length), body = JSON.parse(request.postData || '{}')
      if (request.method !== 'GET') writes.push(path)
      let data
      if (path === '/me') data = { id: 17, email: 'test@example.test', full_name: 'Browser Test', phone: null, role: 'TECHNICAL_STAFF', status: 'ACTIVE', addresses: [], created_at: now }
      else if (path === '/technician/jobs') data = { items: u.searchParams.has('status') && !u.searchParams.getAll('status').includes(job.status) ? [] : [job], total: u.searchParams.has('status') && !u.searchParams.getAll('status').includes(job.status) ? 0 : 1, page: 1, page_size: Number(u.searchParams.get('page_size') || 50) }
      else if (path === '/technician/jobs/9') data = { ...job, can_start: job.status === 'PREPARING' && !!job.calibration && job.simulation_passed === true }
      else if (path === '/technician/jobs/9/package') { job.downloaded_at = now; event('DOWNLOADED'); data = { job_id: 9, order_code: job.order_code, package_hash: hash, trajectory_format: 'vhrs-trajectory-v1', pages: 1, hash_algorithm: 'SHA-256', trajectory_url: 'https://storage.test/trajectory', trajectory_url_expires_in: 1800, pen: null, paper: null, preview_url: null } }
      else if (path.endsWith('/prepare')) { assert.equal(job.status, 'SCHEDULED'); job.status = 'PREPARING'; data = job }
      else if (path.endsWith('/calibration')) { assert.equal(job.status, 'PREPARING'); assert.equal(body.checklist.force_zeroed, true); job.calibration = { id: 1, is_valid: true, created_at: now }; job.simulation_passed = null; event('CALIBRATED'); data = job.calibration }
      else if (path.endsWith('/simulation')) { assert.ok(job.calibration); job.simulation_passed = body.passed; event('SIMULATED'); data = job }
      else if (path.endsWith('/start')) { assert.equal(job.simulation_passed, true); job.status = 'WRITING'; job.progress_pct = 0; job.started_at = now; event('START'); data = job }
      else if (path.endsWith('/events') && request.method === 'POST') {
        if (body.event_type === 'PROGRESS' && conflictOnce) { conflictOnce = false; job.status = 'PAUSED'; await fulfill(requestId, { error: { code: 'JOB_STATE_CONFLICT', message: 'Another workstation paused the job' } }, 409); return }
        if (['PAUSE', 'ESTOP', 'OVER_FORCE', 'STROKE_LOST', 'SENSOR_LOST'].includes(body.event_type)) job.status = 'PAUSED'
        if (body.event_type === 'RESUME') job.status = 'WRITING'
        if (body.event_type === 'PROGRESS') job.progress_pct = body.progress_pct
        event(body.event_type); data = events.at(-1)
      }
      else if (path.endsWith('/events')) data = { items: events, total: events.length, page: 1, page_size: 50 }
      else if (path.endsWith('/finish')) { assert.equal(job.status, 'WRITING'); job.status = 'WRITTEN'; job.progress_pct = 100; job.finished_at = now; event('WRITTEN'); data = job }
      else if (path.endsWith('/photos/upload-url')) data = { photo_key: `${String(++lastPhoto).padStart(32, '0')}.png`, upload_url: `https://storage.test/upload/${lastPhoto}`, method: 'PUT', expires_in: 1800 }
      else if (path.endsWith('/photos') && request.method === 'POST') {
        if (failRegisterOnce) { failRegisterOnce = false; await fulfill(requestId, { error: { code: 'NETWORK', message: 'Registration not confirmed' } }, 503); return }
        data = photos.find((p) => p.key === body.photo_key)
        if (!data) { data = { id: photos.length + 1, key: body.photo_key, kind: body.kind, qc_result: null, qc_note: null, url: 'https://storage.test/product.png', created_at: now }; photos.push(data) }
      } else if (/\/photos\/\d+$/.test(path)) { data = photos.find((p) => p.id === Number(path.split('/').at(-1))); data.qc_result = body.qc_result; data.qc_note = body.qc_note }
      else if (path.endsWith('/photos/submit')) { assert.equal(photos.length, 2); assert.ok(photos.every((p) => p.qc_result === 'PASS')); job.status = 'PHOTO_UPLOADED'; data = job }
      else if (path.endsWith('/photos')) data = photos
      else if (path.endsWith('/qc-fail')) { assert.equal(job.status, 'WRITTEN'); assert.ok(body.note.trim().length >= 3); job.status = 'REWRITE_REQUIRED'; data = job }
      else if (path.endsWith('/incidents')) { incidentCount++; job.status = 'FAILED'; job.incidents.push({ id: incidentCount, type: body.type, description: body.description, created_at: now, resolved_at: null }); data = job.incidents.at(-1) }
      else { await fulfill(requestId, { error: { code: 'JOB_NOT_FOUND', message: 'Not found' } }, 404); return }
      await fulfill(requestId, data)
    } catch (e) { errors.push(e.stack); await fulfill(requestId, { error: { code: 'TEST_FIXTURE_ERROR', message: e.message } }, 500) }
  }
  console.log('Browser connected; installing isolated fixtures');
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:'technician',apiRole:'TECHNICAL_STAFF'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}`) }
  const button = (text) => `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`
  const click = async (text) => { await wait(`!!(${button(text)}) && !(${button(text)}).disabled && !(${button(text)}).closest('fieldset:disabled')`, text); await evaluate(`(${button(text)}).click()`); await sleep(100) }
  const field = async (selector, value) => evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});const p=e.tagName==='SELECT'?HTMLSelectElement.prototype:e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`)
  await command('Emulation.setDeviceMetricsOverride', { width: 1365, height: 1000, deviceScaleFactor: 1, mobile: false })
  await command('Page.navigate', { url: `http://127.0.0.1:${port}/tech/jobs/9` })
  await wait(`document.body.textContent.includes('Job for VH-BROWSER-TEST')`, 'job detail')
  console.log('Job detail loaded');
  assert.equal(writes.length, 0, 'Viewing a job must not write production data')
  await click('Download and verify')
  await wait(`document.body.textContent.includes('Package hash mismatch.')`, 'hash mismatch feedback')
  assert.ok(await evaluate(`(${button('Begin preparation')}).disabled`))
  badHash = false
  await click('Download and verify')
  await wait(`document.body.textContent.includes('Hash verified')`, 'verified hash')
  await click('Begin preparation')
  await wait(`document.querySelectorAll('.tech-probe-row').length===3`, 'preparation form')
  await evaluate(`document.querySelectorAll('.wk-check input').forEach(e=>e.click())`)
  await field('input[min="-1000"]', '0')
  for (let i = 0; i < 9; i++) { const values = ['0', '0', '0', '100', '0', '0', '0', '100', '0']; await evaluate(`(()=>{let e=document.querySelectorAll('.tech-probe-row input')[${i}];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,${JSON.stringify(values[i])});e.dispatchEvent(new Event('input',{bubbles:true}));})()`) }
  console.log('Preparation form populated');
  await click('Save calibration')
  await wait(`document.querySelector('fieldset:not(:disabled) select option[value="pass"]')!==null`, 'simulation enabled')
  await field('select:has(option[value="pass"])', 'pass')
  await click('Record simulation result')
  await wait(`!(${button('Record writing start')}).disabled`, 'start enabled')
  await click('Save calibration') // Recalibration must invalidate the old passing result.
  await wait(`(${button('Record writing start')}).disabled`, 'recalibration invalidates simulation')
  await field('select:has(option[value="pass"])', 'pass')
  await click('Record simulation result')
  await click('Record writing start')
  await wait(`document.querySelector('option[value="PAUSE"]')!==null`, 'writing events')
  await field('.tech-form input[max="100"]', '25')
  await click('Record event')
  await wait(`document.querySelector('option[value="RESUME"]')!==null`, '409 refetches the paused job')
  assert.equal(job.progress_pct, 0)
  await field('select:has(option[value="RESUME"])', 'RESUME')
  await click('Record event')
  await wait(`document.querySelector('option[value="PAUSE"]')!==null`, 'resumed after conflict')
  await field('select:has(option[value="PAUSE"])', 'PAUSE')
  await click('Record event')
  await wait(`document.querySelector('option[value="RESUME"]')!==null`, 'paused')
  await field('select:has(option[value="RESUME"])', 'RESUME')
  await click('Record event')
  await wait(`document.querySelector('option[value="PAUSE"]')!==null`, 'resumed')
  console.log('Writing and pause/resume verified');
  await click('Record writing completion')
  await wait(`document.querySelector('input[type=file]')!==null`, 'photo step')
  assert.ok(await evaluate(`(${button('Submit photos to customer')}).disabled`))
  for (const kind of ['OVERALL', 'CLOSE_UP']) {
    await field('select:has(option[value="OVERALL"])', kind)
    const { root: dom } = await command('DOM.getDocument')
    const { nodeId } = await command('DOM.querySelector', { nodeId: dom.nodeId, selector: 'input[type=file]' })
    await command('DOM.setFileInputFiles', { nodeId, files: [photoFile] })
    if (kind === 'OVERALL') failRegisterOnce = true
    await click('Upload and register photo')
    if (kind === 'OVERALL') { await wait(`!!(${button('Retry registration')})`, 'retryable registration'); await click('Retry registration') }
    await wait(`document.querySelectorAll('.tech-photo').length===${kind === 'OVERALL' ? 1 : 2}`, 'registered photo')
  }
  for (let i = 0; i < 2; i++) {
    await field(`.tech-photo:nth-child(${i + 1}) select`, 'PASS')
    await evaluate(`document.querySelectorAll('.tech-photo')[${i}].querySelector('button[type=submit]').click()`)
    await wait(`document.querySelectorAll('.tech-photo')[${i}].querySelector('.chip').textContent.trim()==='Passed'`, 'QC pass')
  }
  await click('Submit photos to customer')
  await wait(`document.body.textContent.includes('Photos submitted. Waiting for customer acceptance.')`, 'submitted')
  assert.equal(job.status, 'PHOTO_UPLOADED')
  // Inspect translated rendering and small-screen overflow on the same actual DOM.
  for (const lang of ['vi', 'ja']) {
    await evaluate(`localStorage.setItem('aivhrs-lang',${JSON.stringify(lang)})`)
    await command('Page.reload')
    await wait(`document.documentElement.lang===${JSON.stringify(lang)} && !!document.querySelector('.tech-photo')`, `locale ${lang}`)
    assert.equal(await evaluate(`document.body.textContent.includes('td.flow.')`), false)
    await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
    assert.ok(await evaluate('document.documentElement.scrollWidth <= 391'), 'Mobile horizontal overflow')
    assert.ok(await evaluate('document.querySelector(".main2").getBoundingClientRect().top < 250'), 'Technical mobile toolbar must not leave a viewport-sized blank gap')
  }
  // Exercise the two branches which return work to Manager without a customer acceptance action.
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  job.status = 'WRITTEN'
  await command('Page.reload')
  await wait(`!!(${button('Product failed QC')})`, 'QC-fail branch')
  await evaluate(`(()=>{const f=[...document.querySelectorAll('fieldset')].find(f=>f.querySelector('legend')?.textContent==='Product failed QC');const e=f.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,'Ink defect in test product');e.dispatchEvent(new Event('input',{bubbles:true}));})()`)
  await click('Product failed QC')
  await wait(`!(${button('Product failed QC')})`, 'QC failure transitions to rewrite required')
  assert.equal(job.status, 'REWRITE_REQUIRED')
  job.status = 'PREPARING'; job.calibration = null; job.simulation_passed = null
  await command('Page.reload')
  await wait(`!!(${button('Submit incident')})`, 'incident branch')
  await evaluate(`(()=>{const f=[...document.querySelectorAll('fieldset')].find(f=>f.querySelector('legend')?.textContent==='Report an incident');const e=f.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,'Motor fault reported in isolated test');e.dispatchEvent(new Event('input',{bubbles:true}));})()`)
  await click('Submit incident')
  await wait(`document.body.textContent.includes('Reported incidents')`, 'incident appears in detail')
  assert.equal(job.status, 'FAILED')
  assert.deepEqual(errors, [])
  const screen = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
  await writeFile(join(scratch, 'technical-staff.png'), Buffer.from(screen.data, 'base64'))
  console.log('PASS: browser hash mismatch, preparation, recalibration invalidation, simulation, start, 409 refetch, pause/resume, finish, upload retry, QC, submit, QC fail, incident, Vietnamese/Japanese and mobile overflow.')
  console.log('All API/storage responses were local fixtures; production E2E is not claimed.')
} finally {
  ws?.close()
  browser?.kill()
  server.closeAllConnections(); server.close()
}
