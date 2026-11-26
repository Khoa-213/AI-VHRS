// Real Edge DOM test of Robot control on a PAUSED job that was calibrated again after its simulation, with every API call
// intercepted (no backend, no robot). The backend then refuses RUN / RESUME (SIMULATION_STALE) until a new passed simulation is
// recorded, which it accepts on a PAUSED job. Covers: the stale notice, Write and Resume held, "Record simulation result" open on
// a PAUSED job, and both released once the new SIMULATED event is in the log. Run `npm run build` first.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const edge = process.env.TECH_BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
assert.ok(existsSync(edge), 'Set TECH_BROWSER_PATH to an installed Chromium/Edge executable')
assert.ok(existsSync(join(root, 'dist/index.html')), 'Run npm run build first')
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-tech-simstale-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-11-26T03:00:00Z'

const job = {
  id: 9, order_id: 42, order_code: 'VH-STALE', robot_id: 3, robot_code: 'FR3-03', technician_id: 17, technician_name: 'Browser Test',
  status: 'PAUSED', is_rewrite: false, slot_start: now, slot_end: now, estimated_duration_min: 30, package_hash: 'a'.repeat(64),
  progress_pct: 40, downloaded_at: now, started_at: now, finished_at: null, simulation_passed: true,
  order_type: 'OT3_TEMPLATE', quantity: 1, eta: null, paper_name: 'A5', pen_name: 'Pen', ink_name: 'Ink', approach_note: null,
  calibration: { id: 2, is_valid: true, created_at: now }, incidents: [], can_start: false,
}
// Oldest first, as the backend pages them: simulated, started, paused, then calibrated again (more than one page of history).
const events = []
const event = (type) => events.push({ id: events.length + 1, event_type: type, occurred_at: now, stroke_index: null, payload: null, force_summary: null, actor_id: 17, incident_id: null, job_id: 9 })
for (const t of ['DOWNLOADED', 'CALIBRATED', 'SIMULATED', 'START']) event(t)
for (let i = 0; i < 230; i++) event('PROGRESS')
event('PAUSE'); event('CALIBRATED')
const command = (kind, result) => ({ id: `c-${kind}`, robot_id: 3, job_id: 9, kind, params: { mode: 'REAL' }, status: 'DONE', result, error_code: null, error_message: null, created_at: now, expires_at: now, delivered_at: now, finished_at: now })
const commands = [command('PREFLIGHT', { ok: true, moves: 12, mode: 'real' }), command('LOAD', { pages: 1, strokes: 30, validation: { passed: true, errors: [] }, authorization_token: 'AUTHORIZE-9-abc' })]
const simulations = []
// PAUSE keeps the agent's run open (busy); after a STOP it is idle. Write needs an idle agent, Resume a busy one.
const agent = { busy: true }

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

function answer(method, path, search, body) {
  if (path === '/me') return { id: 17, email: 'test@example.test', full_name: 'Browser Test', phone: null, role: 'TECHNICAL_STAFF', status: 'ACTIVE', addresses: [], created_at: now }
  if (path === '/technician/jobs') return { items: [job], total: 1, page: 1, page_size: 50 }
  if (path === '/technician/jobs/9') return job
  if (path === '/technician/jobs/9/events') {
    const page = Number(search.get('page') || 1), size = Number(search.get('page_size') || 50)
    return { items: events.slice((page - 1) * size, page * size), total: events.length, page, page_size: size }
  }
  if (path === '/technician/jobs/9/robot-commands') return commands
  if (path === '/technician/jobs/9/simulation' && method === 'POST') {
    assert.equal(job.status, 'PAUSED', 'a PAUSED job records its simulation')
    simulations.push(body); job.simulation_passed = body.passed; event('SIMULATED'); return job
  }
  if (path === '/technician/robot-status') return [{ robot_id: 3, robot_code: 'FR3-03', state: 'PAUSED_SAFE', headline_vi: 'Đã dừng an toàn', level: 1, mode: 'REAL', connection_state: 'ONLINE', last_seen_at: now, job_id: 9, job_status: 'PAUSED', open_run: null, open_alerts: [], calibration_age_minutes: 3 }]
  if (path === '/technician/robots/3/live') return { robot_id: 3, robot_code: 'FR3-03', agent_online: true, age_s: 0.4, mode: 'REAL', status: { busy: agent.busy, state: agent.busy ? 'PAUSED' : 'STOPPED', enabled_modes: ['REAL'] }, last_seq: 0, frames: [] }
  if (path === '/technician/robots/3/view-ticket') return { ticket: 't', expires_in: 3600, viewer_path: '/viewer/robot.html?ticket=t' }
  if (path.includes('notifications')) return { items: [], total: 0, unread_count: 0 }
  if (path.endsWith('/photos')) return []
  return {}
}

try {
  browser = spawn(edge, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort, 'Browser did not expose a debugging port')
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((v) => v.type === 'page').webSocketDebuggerUrl)
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject })
  let nextId = 0
  const pending = new Map()
  const cdp = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout: ' + method)) }, 15000); pending.set(id, { resolve: (value) => { clearTimeout(timer); resolve(value) }, reject: (error) => { clearTimeout(timer); reject(error) } }); ws.send(JSON.stringify({ id, method, params })) })
  const fulfill = (id, data, code = 200, mime = 'application/json') => cdp('Fetch.fulfillRequest', { requestId: id, responseCode: code, responseHeaders: [{ name: 'Content-Type', value: mime }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET,POST,PATCH,PUT,DELETE,OPTIONS' }], body: Buffer.from(typeof data === 'string' ? data : JSON.stringify(data)).toString('base64') })
  ws.onmessage = async (message) => {
    const msg = JSON.parse(message.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) msg.error ? p.reject(new Error(JSON.stringify(msg.error))) : p.resolve(msg.result); return }
    if (msg.method === 'Page.javascriptDialogOpening') { void cdp('Page.handleJavaScriptDialog', { accept: true }); return }
    if (msg.method === 'Runtime.exceptionThrown') { errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text); return }
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (u.hostname === '127.0.0.1') return void cdp('Fetch.continueRequest', { requestId })
    if (request.method === 'OPTIONS') return void fulfill(requestId, {})
    if (!u.pathname.startsWith('/api/v1/')) return void fulfill(requestId, '<html></html>', 200, 'text/html')
    try { await fulfill(requestId, answer(request.method, u.pathname.slice(7), u.searchParams, JSON.parse(request.postData || '{}'))) }
    catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await cdp('Page.enable'); await cdp('Runtime.enable')
  await cdp('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await cdp('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:'technician',apiRole:'TECHNICAL_STAFF'}));localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}`) }
  const button = (text) => `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`
  await cdp('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })

  await cdp('Page.navigate', { url: `http://127.0.0.1:${port}/tech/jobs/9` })
  await wait(`!!document.querySelector('.rb-steps')`, 'robot control')
  // 1. The newest of CALIBRATED / SIMULATED (on the last page of the log) is CALIBRATED: stale.
  await wait(`document.body.innerText.includes('Calibrated again after the pause')`, 'stale notice')
  await evaluate(`(()=>{const e=document.querySelector('.rb-auth input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(e,'AUTHORIZE-9-abc');e.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  await sleep(150)
  assert.equal(await evaluate(`(${button('Resume')}).disabled`), true, 'Resume is held while the simulation is stale')
  agent.busy = false                                                       // the run was stopped: Write is the way on
  await wait(`document.body.innerText.includes('Write') && !(${button('Resume')})`, 'agent idle')
  await sleep(1500)
  assert.equal(await evaluate(`document.querySelector('.rb-go').disabled`), true, 'Write is held while the simulation is stale')
  // 2. "Record simulation result" is open on a PAUSED job and posts a passed result from the agent's check.
  // Robot control's own button (the manual form below has one with the same label).
  const record = `[...document.querySelectorAll('.rb-steps button')].find(b=>b.textContent.trim()==='Record simulation result')`
  await wait(`!!(${record}) && !(${record}).disabled`, 'record open on PAUSED')
  await evaluate(`(${record}).click()`)
  await wait(`!document.body.innerText.includes('Calibrated again after the pause')`, 'stale notice gone')
  assert.equal(simulations.length, 1)
  assert.equal(simulations[0].passed, true)
  assert.equal(simulations[0].report.calibration_id, 2)
  // 3. Write is released (idle agent); with the run paused again, Resume is released too.
  await wait(`!document.querySelector('.rb-go').disabled`, 'Write released')
  agent.busy = true
  await wait(`!!(${button('Resume')}) && !(${button('Resume')}).disabled`, 'Resume released')

  assert.deepEqual(errors, [], errors.join('\n'))
  console.log('PASS: stale simulation on a PAUSED job (notice from the event log across pages, Write and Resume held, record open on PAUSED, released after the new SIMULATED). All API calls intercepted.')
} finally {
  try { ws?.close() } catch { /* closing */ }
  browser?.kill()
  server.close()
}
