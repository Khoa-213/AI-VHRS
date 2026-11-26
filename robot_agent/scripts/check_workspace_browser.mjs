// Real Edge/Chrome DOM test of the workstation workspace (vhrs_agent/static), every API call intercepted: the agent's own API,
// the technician API it proxies (/api/technician/*) and the signed storage URLs. No backend, no robot. It walks one job through
// the twelve steps of BE/docs/FE_TECH_WORKSPACE_HANDOFF.md 2.5, with REAL switched on by the button (before the REAL dry run).
// Run: TECH_BROWSER_PATH=<chrome or edge> node scripts/check_workspace_browser.mjs
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { createHash } from 'node:crypto'
import { readFile, mkdtemp, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'vhrs_agent', 'static')
const edge = process.env.TECH_BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
assert.ok(existsSync(edge), 'Set TECH_BROWSER_PATH to an installed Chromium/Edge executable')
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-workspace-'))
const photoFile = join(scratch, 'photo.png')
await writeFile(photoFile, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const now = new Date().toISOString()

// ─── The fake world ──────────────────────────────────────────────────
const trajectory = Buffer.from(JSON.stringify({ format: 'vhrs-trajectory-v1', pages: [{ paper: { width_mm: 148, height_mm: 210 }, strokes: [{ points: [[10, 10], [20, 20]] }] }] }))
const job = {
  id: 12, order_id: 900, order_code: 'VHRS-WS12', robot_id: null, robot_code: '', technician_id: 7, technician_name: 'Ky Thuat', status: 'SCHEDULED',
  is_rewrite: false, slot_start: now, slot_end: now, estimated_duration_min: 30, package_hash: createHash('sha256').update(trajectory).digest('hex'),
  progress_pct: 0, downloaded_at: null, started_at: null, finished_at: null, simulation_passed: null, order_type: 'OT3_TEMPLATE', quantity: 1,
  paper_name: 'A5', pen_name: 'Ballpoint', ink_name: 'Black', approach_note: null, calibration: null, can_start: false, incidents: [],
}
const robot = (id, code, link, status, extra = {}) => ({ robot_id: id, robot_code: code, state: link === 'ONLINE' ? 'IDLE' : 'OFFLINE', headline_vi: link === 'ONLINE' ? 'Sẵn sàng' : '',
  level: 1, mode: null, connection_state: link, last_seen_at: null, job_id: null, job_status: null, open_run: null, open_alerts: [], calibration_age_minutes: null,
  robot_status: status, station: 'Bàn ' + code.slice(-1), is_simulated: false, supported_pen_categories: ['BALLPOINT'], technician_id: 7, active: false,
  enabled_modes: link === 'ONLINE' ? ['MOCK', 'SIM', 'REAL'] : [], agent_busy: false, real_enabled: null, ...extra })
const robots = { total: 2, online: 1, active: 0, robots: [robot(46, 'FR3-01', 'ONLINE', 'AVAILABLE'), robot(47, 'FR3-02', 'OFFLINE', 'MAINTENANCE')] }
const agent = { version: 'test', auth_required: true, modes: ['mock', 'sim', 'real'], busy: false, current: null, last: null, real_enabled: null, robot_id: 46 }
const probes = [[0, 0, 19], [100, 0, 19], [0, 100, 19]]
let loaded = null
let robotAnswers = false                                  // the first 'Bật REAL' finds the robot switched off
const photos = []
const calls = []

function answer(method, path, body) {
  calls.push(method + ' ' + path)
  const err = (status, code, message = code) => [status, { error: { code, message, details: null } }]
  if (path === '/api/agent') return [200, agent]
  if (path === '/api/login') return [200, { access_token: 'tok', role: 'TECHNICAL_STAFF', name: 'Ky Thuat' }]
  if (path === '/api/model') return [200, { available: false, joints: [] }]
  if (path === '/api/job') return [200, {}]
  if (path === '/api/technician/robots') return [200, robots]
  if (path === '/api/technician/jobs') return [200, { items: [job], total: 1, page: 1, page_size: 200 }]
  if (path === '/api/technician/jobs/12') return [200, job]
  if (path === '/api/technician/jobs/12/package') { job.downloaded_at = now; return [200, { trajectory_url: 'https://storage.test/traj.json', package_hash: job.package_hash, snapshot: { v: 1 }, material_drift: [] }] }
  if (path === '/api/technician/jobs/12/robot' && method === 'PUT') { assert.equal(body.robot_id, 46, 'the robot of this machine is offered first'); job.robot_id = 46; job.robot_code = 'FR3-01'; return [200, job] }
  if (path === '/api/technician/jobs/12/prepare') { assert.ok(job.downloaded_at && job.robot_id); job.status = 'PREPARING'; return [200, job] }
  if (path === '/api/robot/identify') { const p = probes.shift(); return [200, { info: {}, healthy: true, tcp_mm: p, joints_deg: [] }] }
  if (path === '/api/technician/jobs/12/calibration') {
    assert.equal(body.probe_points.length, 3); assert.deepEqual(body.probe_points[1], { x: 100, y: 0, z: 19 }); assert.equal(body.force_zero_offset, 0.2)
    assert.ok(Object.values(body.checklist).every(Boolean)); job.calibration = { id: 1, is_valid: true, created_at: now }; job.simulation_passed = null; return [201, { id: 1, is_valid: true }]
  }
  if (path === '/api/jobs/12' && method === 'GET') return loaded ? [200, loaded] : err(409, 'JOB_NOT_LOADED')
  if (path === '/api/jobs/12/load') { loaded = { job_id: 12, robot_id: 46, pages: 1, strokes: 30, pen: 'Ballpoint', estimated_seconds: 600, validation: { passed: true }, authorization_token: 'AUTHORIZE-12-plan' }; return [200, loaded] }
  if (path === '/api/jobs/12/preflight') return [200, { ok: true, mode: body.mode, moves: 12 }]
  if (path === '/api/technician/jobs/12/simulation') { job.simulation_passed = true; job.can_start = true; return [200, job] }
  if (path === '/api/jobs/12/real-enable') {
    assert.equal(body.minutes, 30); assert.equal(body.waive_dry_run, undefined, 'no waiver unless ticked')
    if (!robotAnswers) return err(502, 'ROBOT_UNREACHABLE', 'ConnectionError: controller 192.168.58.2 did not answer')
    agent.real_enabled = { job_id: 12, expires_at: Date.now() / 1000 + 1800, enabled_by: 'desktop:Ky Thuat', waive_dry_run: false }
    return [200, { real_enabled: agent.real_enabled, minutes: 30, robot_check: { ok: true, controller: { mode: 'real', controller_version: 'V3.8.25-QX' }, tcp_mm: [1, 2, 3] } }]
  }
  if (path === '/api/jobs/12/dry-run') {
    if (body.mode === 'real' && !agent.real_enabled) return err(403, 'REAL_NOT_ENABLED_ON_SITE')
    assert.equal(body.authorization, 'AUTHORIZE-12-plan', 'a REAL dry run carries the plan token')
    agent.last = { job_id: 12, dry_run: true, mode: body.mode, result: { state: 'DRY_RUN_DONE' } }; return [202, { started: true }]
  }
  if (path === '/api/technician/jobs/12/start') { job.status = 'WRITING'; job.started_at = now; return [200, job] }
  if (path === '/api/jobs/12/run') { assert.equal(body.mode, 'real'); assert.equal(body.authorization, 'AUTHORIZE-12-plan'); job.progress_pct = 100; return [202, { started: true }] }
  if (path === '/api/technician/jobs/12/finish') { job.status = 'WRITTEN'; return [200, job] }
  if (path === '/api/technician/jobs/12/photos' && method === 'GET') return [200, photos]
  if (path === '/api/technician/jobs/12/photos/upload-url') return [200, { photo_key: 'k' + (photos.length + 1), upload_url: 'https://storage.test/up/' + (photos.length + 1), method: 'PUT', expires_in: 600 }]
  if (path === '/api/technician/jobs/12/photos' && method === 'POST') { photos.push({ id: photos.length + 1, kind: body.kind, qc_result: null, qc_note: null, url: null, url_expires_in: 0, created_at: now }); return [201, photos.at(-1)] }
  const qc = /^\/api\/technician\/jobs\/12\/photos\/(\d+)$/.exec(path)
  if (qc && method === 'PATCH') { const p = photos.find((x) => x.id === Number(qc[1])); p.qc_result = body.qc_result; return [200, p] }
  if (path === '/api/technician/jobs/12/photos/submit') { assert.equal(photos.length, 2); job.status = 'PHOTO_UPLOADED'; return [200, job] }
  return err(404, 'NOT_FOUND', path)
}

const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://localhost').pathname
    const file = path === '/' ? 'index.html' : path.slice(1)
    const target = resolve(root, file)
    assert.ok(target.startsWith(root))
    res.setHeader('Content-Type', ({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html' })[extname(target)] || 'application/octet-stream')
    res.end(await readFile(target))
  } catch { res.statusCode = 404; res.end() }
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const port = server.address().port
let browser, ws
const errors = []

try {
  browser = spawn(edge, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort, 'Browser did not expose a debugging port')
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((v) => v.type === 'page').webSocketDebuggerUrl)
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j })
  let nextId = 0
  const pending = new Map()
  const cdp = (method, params = {}) => new Promise((r, j) => { const id = ++nextId; const t = setTimeout(() => { pending.delete(id); j(new Error('CDP timeout: ' + method)) }, 15000); pending.set(id, { resolve: (v) => { clearTimeout(t); r(v) }, reject: (e) => { clearTimeout(t); j(e) } }); ws.send(JSON.stringify({ id, method, params })) })
  const headers = [{ name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET,POST,PUT,PATCH,DELETE,OPTIONS' }]
  const fulfill = (id, code, body, mime = 'application/json') => cdp('Fetch.fulfillRequest', { requestId: id, responseCode: code, responseHeaders: [{ name: 'Content-Type', value: mime }, ...headers],
    body: Buffer.from(Buffer.isBuffer(body) ? body : typeof body === 'string' ? body : JSON.stringify(body)).toString('base64') })
  ws.onmessage = async (message) => {
    const msg = JSON.parse(message.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) msg.error ? p.reject(new Error(JSON.stringify(msg.error))) : p.resolve(msg.result); return }
    if (msg.method === 'Page.javascriptDialogOpening') { void cdp('Page.handleJavaScriptDialog', { accept: true }); return }
    if (msg.method === 'Runtime.exceptionThrown') { errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text); return }
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (request.method === 'OPTIONS') return void fulfill(requestId, 204, '')
    if (u.hostname === 'storage.test') return void fulfill(requestId, 200, u.pathname === '/traj.json' ? trajectory : '', 'application/octet-stream')
    if (u.hostname === '127.0.0.1' && u.pathname.startsWith('/api/')) {
      try { const [code, data] = answer(request.method, u.pathname, JSON.parse(request.postData || '{}')); await fulfill(requestId, code, data) }
      catch (e) { errors.push(e.message); await fulfill(requestId, 500, { error: { code: 'TEST_ERROR', message: e.message } }) }
      return
    }
    void cdp('Fetch.continueRequest', { requestId })
  }
  await cdp('Page.enable'); await cdp('Runtime.enable'); await cdp('DOM.enable')
  await cdp('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await cdp('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  const evaluate = async (expression) => { const r = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text + ' ' + expression); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}\n${calls.slice(-8).join('\n')}`) }
  const text = (s) => `document.body.innerText.includes(${JSON.stringify(s)})`
  const act = async (name, label) => {
    const sel = `[...document.querySelectorAll('[data-act="${name}"]')].find(b=>!b.disabled${label ? ` && b.textContent.trim()===${JSON.stringify(label)}` : ''})`
    await wait(`!!(${sel})`, 'button ' + name + ' ' + (label || ''))
    await evaluate(`(${sel}).click()`)
  }
  const setField = (f, v) => evaluate(`(()=>{const e=document.querySelector('[data-f="${f}"]');if(e.type==='checkbox'){e.checked=${!!v};}else{e.value=${JSON.stringify(String(v))};}e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}))})()`)
  const openStep = (k) => evaluate(`(()=>{const b=document.querySelector('[data-act="step"][data-k="${k}"]');if(b.getAttribute('aria-expanded')!=='true')b.click()})()`)
  // WS_SHOTS=<dir> saves screenshots along the way.
  const shot = async (name) => { if (!process.env.WS_SHOTS) return; const r = await cdp('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true }); await writeFile(join(process.env.WS_SHOTS, name + '.png'), Buffer.from(r.data, 'base64')) }
  const stepDone = (k) => `!!document.querySelector('.step.done [data-k="${k}"]')`
  const doneSteps = () => evaluate(`document.querySelectorAll('.step.done').length`)

  // Sign in.
  await cdp('Page.navigate', { url: `http://127.0.0.1:${port}/` })
  await wait(`!document.getElementById('login').hidden`, 'login form')
  await evaluate(`document.getElementById('em').value='tech@x.test';document.getElementById('pw').value='x';document.getElementById('loginform').requestSubmit()`)
  // The strip: 1 of 2 connected, this machine marked, the other in maintenance.
  await wait(text('Đang kết nối 1 / 2 · Đang hoạt động 0'), 'robot strip summary')
  assert.equal(await evaluate(`getComputedStyle(document.getElementById('realbar')).display`), 'none', 'no REAL bar while REAL is off')
  assert.ok(await evaluate(text('máy này')) && await evaluate(text('Bảo trì')))
  assert.ok(await evaluate(text('Máy này: FR3-01 · MOCK / SIM / REAL')), 'the header names this machine')
  await act('open', null)
  await wait(`document.querySelectorAll('.step').length===12`, 'twelve steps')
  assert.ok(await evaluate(text('Hãy tải gói và kiểm hash trước.')), 'a locked step says why')

  // 1. Package and hash (crypto.subtle or the built-in SHA-256).
  await act('package'); await wait(`document.querySelector('.step').classList.contains('done')`, 'hash verified, step 1 done')
  await wait(`document.querySelector('.step.current [data-k="robot"]') && !!document.querySelector('input[data-f="robotpick"]')`, 'step 2 opens by itself')
  // 2. Robot: this machine's robot is preselected, the robot in maintenance cannot be picked.
  assert.equal(await evaluate(`document.querySelector('input[data-f="robotpick"][value="47"]').disabled`), true)
  await act('chooseRobot'); await wait(`document.querySelectorAll('.step.done').length>=2`, 'robot chosen')
  // 3. Prepare.
  await act('prepare'); await wait(`JSON.stringify([...document.querySelectorAll('.step.current .t')].map(e=>e.textContent)).includes('Hiệu chuẩn')`, 'prepared')
  // 4. Calibration measured with the robot: P0 to P2 from /api/robot/identify.
  for (const k of ['frame_mounted', 'paper_clamped', 'pen_installed', 'force_zeroed']) await setField('chk_' + k, true)
  await setField('offset', '0.2')
  await shot('1-calibration-1440')
  for (const i of [0, 1, 2]) { await act('probe', 'Lấy P' + i); await wait(`document.querySelector('[data-f="p${i}x"]') && document.querySelector('[data-f="p${i}x"]').value!==''`, 'probe ' + i) }
  await act('calSend'); await wait(`[...document.querySelectorAll('.step.done .t')].some(e=>e.textContent.includes('Hiệu chuẩn'))`, 'calibrated')
  // 5. Load here, 6. preflight, 7. simulation.
  await act('load'); await wait(stepDone('load'), 'loaded')
  await openStep('load')
  await wait(text('AUTHORIZE-12-pla'), 'the plan token is shown, shortened')
  await openStep('preflight')
  await act('preflight'); await wait(stepDone('preflight'), 'preflight ok')
  await act('simulate'); await wait(stepDone('simulate'), 'simulated')
  // 8 before 9 refused for REAL; 9 switches REAL on with the button; then the REAL dry run.
  await setField('mode', 'real')
  await act('dryRun'); await wait(text('Chưa bật REAL cho job này'), 'REAL dry run needs the switch')
  await openStep('real')
  // the switch first checks the real robot: no answer, REAL stays off and the step says so
  await act('realOn'); await wait(text('robot không phản hồi, REAL chưa bật'), 'REAL refused when the robot does not answer')
  assert.equal(agent.real_enabled, null)
  assert.equal(await evaluate(`getComputedStyle(document.getElementById('realbar')).display`), 'none', 'no REAL bar after a failed check')
  robotAnswers = true
  await act('realOn'); await wait(`!document.getElementById('realbar').hidden && document.getElementById('realtext').textContent.includes('job 12')`, 'REAL bar with countdown')
  await shot('2-real-on-1440')
  await openStep('dryRun')
  await act('dryRun'); await wait(stepDone('dryRun'), 'dry run done')
  // 10. Start and write (REAL), 11. finish.
  await openStep('write')
  await act('write'); await wait(text('Đang viết'), 'writing')
  await act('finish'); await wait(text('Đã viết xong'), 'written')
  // 12. Photos: one overall and one close-up, both pass, then send.
  for (const kind of ['OVERALL', 'CLOSE_UP']) {
    await wait(`!!document.querySelector('input[data-change="upload"]')`, 'upload field')
    await setField('pkind', kind)
    const { root: doc } = await cdp('DOM.getDocument')
    const { nodeId } = await cdp('DOM.querySelector', { nodeId: doc.nodeId, selector: 'input[data-change="upload"]' })
    await cdp('DOM.setFileInputFiles', { nodeId, files: [photoFile] })
    await wait(`document.querySelectorAll('.photo').length===${kind === 'OVERALL' ? 1 : 2}`, 'photo listed')
  }
  for (const id of [1, 2]) { await evaluate(`document.querySelector('[data-act="qc"][data-id="${id}"][data-v="PASS"]').click()`); await wait(`document.querySelectorAll('.photo .pill.ok').length>=${id}`, 'qc ' + id) }
  await shot('3-photos-1440')
  await act('submitPhotos'); await wait(text('Đã gửi ảnh'), 'sent to the customer')
  assert.equal(await doneSteps(), 12, 'every step done (the REAL step too, while REAL is on)')
  assert.ok(calls.includes('PUT /api/technician/jobs/12/robot') && calls.includes('POST /api/jobs/12/real-enable'))

  // Phone width: no sideways scroll; STOP stays on screen.
  await cdp('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await sleep(300)
  assert.ok(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth + 1`), 'no sideways scroll at phone width')
  assert.ok(await evaluate(`(()=>{const r=document.getElementById('stop').getBoundingClientRect();return r.bottom<=innerHeight && r.top>=0})()`), 'STOP visible')
  await shot('4-phone-390')

  assert.deepEqual(errors, [], errors.join('\n'))
  console.log('PASS: workstation workspace, steps 1 to 12 (package and SHA-256, robot of this machine, prepare, calibration from the robot, load, preflight, simulation, REAL refused then switched on by the button, REAL dry run, write, finish, photos and QC, send), strip 1 / 2, phone width. All calls intercepted.')
} finally {
  try { ws?.close() } catch { /* closing */ }
  browser?.kill()
  server.close()
}
