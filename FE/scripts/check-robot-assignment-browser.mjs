// Real Edge DOM test, every API call intercepted (no backend). Covers the 2026-11-26 split (BE/docs/FE_TECH_WORKSPACE_HANDOFF.md):
// 1. a technician on the web (and an old /tech/jobs/:id link) gets the workstation notice with their jobs read only (no actions);
// 1b. the Manager sees a red "REAL on for job X until hh:mm" from robot-status real_enabled;
// 2. the Manager gives robots to technicians on /staff/robots (PUT / DELETE /manager/robots/{id}/technician), and a refusal
//    `409 ROBOT_HAS_ACTIVE_JOBS` lists the job ids with a link to the schedule. Run `npm run build` first.
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
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-robot-assign-'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const now = '2026-11-26T03:00:00Z'

const robots = [
  { id: 46, code: 'FR3-01', station: 'A1', status: 'AVAILABLE', is_simulated: false, supported_pen_categories: ['BALLPOINT'], technician_id: 5, technician_name: 'Kỹ thuật viên A' },
  { id: 47, code: 'FR3-02', station: 'A2', status: 'MAINTENANCE', is_simulated: true, supported_pen_categories: [], technician_id: null, technician_name: null },
]
const techs = [
  { id: 5, full_name: 'Kỹ thuật viên A', email: 'a@x.test', active_jobs: 1, robots: [{ id: 46, code: 'FR3-01', status: 'AVAILABLE' }] },
  { id: 6, full_name: 'Kỹ thuật viên B', email: 'b@x.test', active_jobs: 0, robots: [] },
]
const writes = []
const techCalls = []
let role = 'technician'

const server = createServer(async (req, res) => {
  try {
    const path = new URL(req.url, 'http://localhost').pathname
    const target = path.startsWith('/assets/') ? join(root, 'dist', path) : join(root, 'dist/index.html')
    assert.ok(resolve(target).startsWith(resolve(root, 'dist')))
    res.setHeader('Content-Type', ({ '.js': 'text/javascript', '.css': 'text/css', '.png': 'image/png', '.svg': 'image/svg+xml' })[extname(target)] || 'text/html')
    res.end(await readFile(target))
  } catch { res.statusCode = 404; res.end() }
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const port = server.address().port
let browser, ws
const errors = []

/** [status, body] */
function answer(method, path, body) {
  if (path.startsWith('/technician/')) {
    techCalls.push(method + ' ' + path)
    if (path === '/technician/jobs') return [200, { items: [{ id: 9, order_code: 'VHRS-T9', robot_id: null, robot_code: '', status: 'SCHEDULED', slot_start: now }], total: 1, page: 1, page_size: 50 }]
    return [404, { error: { code: 'NOT_FOUND', message: 'x' } }]
  }
  if (path === '/me') return [200, { id: 3, email: 'm@x.test', full_name: 'Manager', phone: null, role: role === 'technician' ? 'TECHNICAL_STAFF' : 'MANAGER', status: 'ACTIVE', addresses: [], created_at: now }]
  if (path === '/manager/robots') return [200, robots]
  if (path === '/manager/technicians') return [200, techs]
  const m = /^\/manager\/robots\/(\d+)\/technician$/.exec(path)
  if (m) {
    const r = robots.find((x) => x.id === Number(m[1]))
    writes.push([method, r.code, body.technician_id ?? null])
    if (method === 'DELETE' && r.id === 46) return [409, { error: { code: 'ROBOT_HAS_ACTIVE_JOBS', message: 'x', details: { job_ids: [291, 292] } } }]
    const t = techs.find((x) => x.id === body.technician_id)
    Object.assign(r, method === 'PUT' ? { technician_id: t.id, technician_name: t.full_name } : { technician_id: null, technician_name: null })
    return [200, r]
  }
  if (path === '/manager/alerts' || path === '/manager/incidents') return [200, { items: [], total: 0, page: 1, page_size: 50 }]
  if (path === '/manager/robot-status') return [200, [{ robot_id: 46, robot_code: 'FR3-01', state: 'PREPARING', headline_vi: 'Chuẩn bị', level: 1, mode: 'REAL', connection_state: 'ONLINE',
    last_seen_at: now, seconds_since_seen: 1, agent_version: '1', job_id: 9, job_status: 'PREPARING', open_run: null, open_alerts: [], calibration_age_minutes: 2,
    real_enabled: { job_id: 9, expires_at: Date.parse(now) / 1000 + 1800, enabled_by: 'desktop:A', waive_dry_run: false } }]]
  if (path === '/manager/alert-catalog') return [200, []]
  if (path.includes('notifications')) return [200, { items: [], total: 0, unread_count: 0 }]
  if (path.includes('unread-count')) return [200, { count: 0 }]
  if (path.includes('conversations')) return [200, { items: [], total: 0 }]
  return [200, { items: [], total: 0, page: 1, page_size: 1 }]
}

try {
  browser = spawn(edge, ['--headless=new', '--no-sandbox', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort, 'Browser did not expose a debugging port')
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((v) => v.type === 'page').webSocketDebuggerUrl)
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j })
  let nextId = 0
  const pending = new Map()
  const cdp = (method, params = {}) => new Promise((r, j) => { const id = ++nextId; const timer = setTimeout(() => { pending.delete(id); j(new Error('CDP timeout: ' + method)) }, 15000); pending.set(id, { resolve: (v) => { clearTimeout(timer); r(v) }, reject: (e) => { clearTimeout(timer); j(e) } }); ws.send(JSON.stringify({ id, method, params })) })
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
    try { const [code, data] = answer(request.method, u.pathname.slice(7), JSON.parse(request.postData || '{}')); await fulfill(requestId, data, code) }
    catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await cdp('Page.enable'); await cdp('Runtime.enable')
  await cdp('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  const signIn = (r, apiRole) => cdp('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:3,name:'Browser Test',role:'${r}',apiRole:'${apiRole}'}));localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await cdp('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}`) }
  const text = (s) => `document.body.innerText.includes(${JSON.stringify(s)})`
  await cdp('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1100, deviceScaleFactor: 1, mobile: false })

  // 1. A technician on the web, through an old job link.
  const tech = await signIn('technician', 'TECHNICAL_STAFF')
  await cdp('Page.navigate', { url: `http://127.0.0.1:${port}/tech/jobs/9` })
  await wait(text('Technicians work at the workstation screen') + ' && ' + text('VHRS-T9') + ' && ' + text('No robot chosen'), 'workstation notice with the read-only job list')
  await sleep(500)
  assert.ok(await evaluate(text('http://<workstation>:8765/')), 'the notice gives the workstation address')
  assert.ok(techCalls.every((c) => c === 'GET /technician/jobs'), 'the web only reads the job list: ' + techCalls.join(', '))
  assert.equal(await evaluate(`[...document.querySelectorAll('main button')].filter(b=>!b.closest('.lang')).length`), 1, 'no action but Sign out (and the language switch)')
  await cdp('Page.removeScriptToEvaluateOnNewDocument', { identifier: tech.identifier })

  // 2. The Manager gives FR3-02 to technician B, then tries to take FR3-01 back while it has unfinished jobs.
  role = 'staff'
  await signIn('staff', 'MANAGER')
  await cdp('Page.navigate', { url: `http://127.0.0.1:${port}/staff/robots` })
  await wait(`!!document.querySelector('.mgr-assign')`, 'assignment table')
  await wait(text('REAL on for job 9 until'), 'the Manager sees that REAL is on at the workstation')
  assert.ok(await evaluate(text('Kỹ thuật viên A')), 'the current owner is listed')
  await evaluate(`(()=>{const s=document.querySelector('select[aria-label="Technician for FR3-02"]');const set=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set;set.call(s,'6');s.dispatchEvent(new Event('change',{bubbles:true}))})()`)
  await sleep(150)
  await evaluate(`[...document.querySelectorAll('.mgr-assign tr')].find(r=>r.innerText.includes('FR3-02')).querySelector('.vh-btn--primary').click()`)
  await wait(text('FR3-02 assigned.'), 'assigned')
  assert.deepEqual(writes[0], ['PUT', 'FR3-02', 6])
  await wait(`[...document.querySelectorAll('.mgr-assign tr')].find(r=>r.innerText.includes('FR3-02')).innerText.includes('Kỹ thuật viên B')`, 'owner updated')

  await evaluate(`[...document.querySelectorAll('.mgr-assign tr')].find(r=>r.innerText.includes('FR3-01')).querySelector('.vh-btn--ghost').click()`)
  await wait(text('#291, #292'), 'blocking jobs listed')
  assert.deepEqual(writes[1], ['DELETE', 'FR3-01', null])
  assert.ok(await evaluate(`!![...document.querySelectorAll('.lg-error a')].find(a=>a.getAttribute('href')==='/staff/schedule')`), 'link to the schedule')

  // Phone width: no sideways scroll.
  await cdp('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await sleep(400)
  assert.ok(await evaluate(`document.documentElement.scrollWidth <= window.innerWidth + 1`), 'no sideways scroll at phone width')

  assert.deepEqual(errors, [], errors.join('\n'))
  console.log('PASS: technician gets the workstation notice (job list read only, no actions); Manager sees REAL on, assigns a robot and sees the jobs that block taking one back. All API calls intercepted.')
} finally {
  try { ws?.close() } catch { /* closing */ }
  browser?.kill()
  server.close()
}
