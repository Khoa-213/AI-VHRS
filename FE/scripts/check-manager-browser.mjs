// Real Edge/Chromium DOM smoke test of the Manager screens in the Staff frame, with every API call answered by fixtures.
// No production data. Run after `npm run build`. Set TECH_BROWSER_PATH outside Windows; MANAGER_SHOTS=<dir> saves screenshots.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, writeFile, mkdtemp, mkdir } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const edge = [
  process.env.TECH_BROWSER_PATH,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
  '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
].filter(Boolean).find((p) => existsSync(p))
assert.ok(edge, 'Set TECH_BROWSER_PATH to an installed Chromium/Edge executable')
assert.ok(existsSync(join(root, 'dist/index.html')), 'Run npm run build first')
const shots = process.env.MANAGER_SHOTS
if (shots) await mkdir(shots, { recursive: true })
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-manager-browser-'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const now = new Date().toISOString()
const today = now.slice(0, 10)

// ---------- fixtures, shaped like the backend's answers ----------
const alert = (id, level, code, extra = {}) => ({
  id, robot_id: 1, robot_code: 'FR3-01', job_id: 291, run_id: 35, code, level,
  title_vi: 'Robot báo lỗi an toàn hoặc va chạm trong lúc di chuyển.', action_vi: 'BẤM NÚT E-STOP NGAY nếu robot chưa đứng yên, rồi gọi Manager.',
  estop_advised: level >= 4, details: null, occurrences: 2, raised_at: now, last_raised_at: now, emailed_at: now,
  acknowledged_by: null, acknowledged_at: null, resolved_by: null, resolved_at: null, resolution_note: null, ...extra,
})
const alerts = [alert(12, 4, 'CONTROLLER_SAFETY_FAULT'), alert(13, 2, 'CALIBRATION_OLD', { acknowledged_at: now, acknowledged_by: 4 })]
const status = [
  { robot_id: 1, robot_code: 'FR3-01', state: 'DANGER', headline_vi: 'BẤM NÚT E-STOP NGAY', level: 4, mode: 'REAL', connection_state: 'ONLINE', last_seen_at: now, seconds_since_seen: 3, controller_version: null, firmware_version: null, sdk_version: null, agent_version: '0.1.0', job_id: 291, job_status: 'PAUSED', open_run: { id: 1, run_id: 'r1', job_id: 291, robot_id: 1, mode: 'REAL', dry_run: false, started_at: now, ended_at: null, result: null, completed_strokes: 12, total_strokes: 34, plan_digest: null, authorized_by: null, authorized_at: null, agent_version: null, robot_info: null, summary: null }, open_alerts: alerts, calibration_age_minutes: 95 },
  { robot_id: 2, robot_code: 'FR3-02', state: 'OFFLINE', headline_vi: 'Mất kết nối máy trạm', level: 1, mode: null, connection_state: 'OFFLINE', last_seen_at: null, seconds_since_seen: null, controller_version: null, firmware_version: null, sdk_version: null, agent_version: null, job_id: null, job_status: null, open_run: null, open_alerts: [], calibration_age_minutes: null },
]
const page = (items, extra = {}) => ({ items, total: items.length, page: 1, page_size: 50, ...extra })
const work = [1, 2, 3].map((i) => ({ id: 100 + i, code: `VHRS-T${i}`, order_type: 'OT3_TEMPLATE', order_status: i === 1 ? 'SUBMITTED' : 'CONFIRMED', quantity: 1, total_amount: 120000, created_at: now, submitted_at: now, updated_at: now, customer_name: 'Khách thử', assigned_staff_id: i === 1 ? null : 3, title: null, eta: today }))
const review = (id, hidden) => ({ id, order_id: 104, order_code: 'VHRS-T4', customer_name: 'Nguyễn V. A.', rating: hidden ? 1 : 5, comment: hidden ? 'Nội dung vi phạm' : 'Chữ đẹp, giao nhanh.', photos: [], hidden, hidden_at: hidden ? now : null, created_at: now, updated_at: now, editable_until: now })
let meRole = 'MANAGER'

function answer(method, path, search) {
  if (path === '/me') return { id: 4, email: 'manager@example.test', full_name: 'Manager Thử', role: meRole, status: 'ACTIVE', addresses: [], created_at: now }
  if (path === '/manager/dashboard') return {
    date: today, orders_by_status: { CONFIRMED: 31, ACCEPTED: 7, SUBMITTED: 4, AWAITING_DEPOSIT: 4, DELIVERING: 1, AWAITING_FINAL_PAYMENT: 1 },
    jobs_today: [{ job_id: 291, order_id: 101, order_code: 'VHRS-T1', robot_id: 1, robot_code: 'FR3-01', technician_id: 5, status: 'SCHEDULED', slot_start: now, slot_end: now, is_rewrite: false }],
    jobs_next_7_days: 4,
    late_orders: [{ order_id: 102, code: 'VHRS-T2', status: 'CONFIRMED', eta: '2026-10-24', days_late: 19, assigned_staff_id: 3 }],
    due_in_2_days: [{ order_id: 103, code: 'VHRS-T3', status: 'CONFIRMED', eta: today, assigned_staff_id: 3 }],
    low_stock: [{ kind: 'PAPER', id: 1, name: 'Giấy dó A4', stock_qty: 4 }, { kind: 'INK', id: 2, name: 'Mực đen', stock_qty: 0 }],
    pending: { unclaimed_orders: 1, price_adjustments: 1, orders_to_schedule: 2, open_incidents: 1, refunds_to_confirm: 0 },
  }
  if (path === '/manager/reports') return {
    from: '2026-10-14', to: today, group: search.get('group') || 'day',
    revenue: { series: [{ bucket: '2026-10-19', received: 104400, refunded: 0, payments: 10, net: 104400 }, { bucket: '2026-11-02', received: 15500, refunded: 4200, payments: 2, net: 11300 }], received: 119900, refunded: 4200, net: 115700 },
    output_by_type: [{ order_type: 'OT3_TEMPLATE', orders: 3, quantity: 5, total_amount: 360000 }],
    rates: { submitted: 58, rejected: 2, reject_rate: 0.0345, jobs_written: 2, rewrites: 0, rewrite_rate: 0 },
    robots: [{ robot_id: 1, robot_code: 'FR3-01', jobs_written: 2, writing_minutes: 16, incidents: 0 }],
    late_completed: { count: 1, of_completed: 3, late_rate: 0.3333, orders: [{ order_id: 104, code: 'VHRS-T4', eta: '2026-10-20', completed_on: '2026-10-22', days_late: 2, eta_postponed_days: 0 }] },
  }
  if (path === '/manager/robot-status') return status
  if (/^\/manager\/robots\/\d+\/health$/.test(path)) return { robot: status[0], since: now, runs_by_result: { DONE: 6, STOPPED: 12, FAULT: 4 }, runs_by_mode: { REAL: 22 }, run_seconds: 10214.9, safety_stops: 14, alerts_by_level: { 4: 6, 2: 3 }, in_band_pct_avg: null, open_incidents: 1, unresolved_red: 1 }
  if (path === '/manager/alerts') return page(alerts)
  if (/^\/manager\/alerts\/\d+\/(ack|resolve)$/.test(path)) return { ...alerts[0], acknowledged_at: now, resolved_at: path.endsWith('resolve') ? now : null }
  if (path === '/manager/alert-catalog') return [
    { code: 'CONTROLLER_SAFETY_FAULT', level: 4, title_vi: 'Robot báo lỗi an toàn.', action_vi: 'BẤM NÚT E-STOP NGAY.', estop_advised: true, notify_roles: ['TECHNICAL_STAFF', 'MANAGER'], send_email: true, threshold: null, is_active: true, updated_at: now },
    { code: 'CALIBRATION_OLD', level: 2, title_vi: 'Hiệu chuẩn đã cũ.', action_vi: 'Hiệu chuẩn lại trước khi viết.', estop_advised: false, notify_roles: ['TECHNICAL_STAFF'], send_email: false, threshold: null, is_active: true, updated_at: now },
  ]
  if (/^\/manager\/alert-catalog\/[A-Z_]+$/.test(path)) return {}
  if (path === '/manager/runs') return page([{ id: 38, run_id: 'r38', job_id: 291, robot_id: 1, mode: 'REAL', dry_run: false, started_at: now, ended_at: now, result: 'DONE', completed_strokes: 34, total_strokes: 34, plan_digest: null, authorized_by: null, authorized_at: null, agent_version: null, robot_info: null, summary: null }])
  if (/^\/manager\/jobs\/\d+\/compliance$/.test(path)) return { job_id: 291, order_code: 'VHRS-T1', robot_code: 'FR3-01', job_status: 'PAUSED', steps: [{ key: 'package', label_vi: 'Gói job khớp mã hash', status: 'PASS', at: now, detail: null }, { key: 'dry_run', label_vi: 'Chạy thử pen-up', status: 'FAIL', at: null, detail: 'Có lần viết thật mà chưa có chạy thử' }], exceptions: ['Có lần viết thật mà chưa có chạy thử'], followed_process: false }
  if (/^\/manager\/jobs\/\d+\/events$/.test(path)) return page([{ id: 1, job_id: 291, event_type: 'DOWNLOADED', actor_id: 5, incident_id: null, stroke_index: null, force_summary: null, payload: null, occurred_at: now }, { id: 2, job_id: 291, event_type: 'PAUSE', actor_id: 5, incident_id: null, stroke_index: 12, force_summary: null, payload: null, occurred_at: now }])
  if (/^\/manager\/jobs\/\d+\/quality$/.test(path)) return [{ id: 7, photo_id: 3, job_id: 291, page: 1, method: 'contour', verdict: 'NEEDS_REVIEW', metrics: {}, overlay_url: null, created_at: now, advisory: 'Ngưỡng mặc định chưa kiểm chứng.' }]
  if (/^\/manager\/jobs\/\d+$/.test(path)) return { id: 291, order_id: 101, order_code: 'VHRS-T1', robot_id: 1, robot_code: 'FR3-01', technician_id: 5, technician_name: 'Kỹ thuật viên A', status: 'PAUSED', is_rewrite: false, slot_start: now, slot_end: now, estimated_duration_min: 40, package_hash: null, progress_pct: 35, downloaded_at: now, started_at: now, finished_at: null, simulation_passed: true }
  if (path === '/manager/incidents') return page([{ id: 3, job_id: 291, robot_id: 1, reported_by: 5, type: 'ROBOT', description: 'Cánh tay dừng giữa chừng.', robot_status_after: 'MAINTENANCE', resolved_by: null, resolved_at: null, resolution_note: null, created_at: now }])
  if (/^\/manager\/incidents\/\d+\/resolve$/.test(path)) return {}
  if (path === '/manager/reviews') return page(search.get('hidden') === 'true' ? [review(9, true)] : [review(8, false), review(9, true)], { page_size: 20 })
  if (/^\/manager\/reviews\/\d+\/(hide|unhide)$/.test(path)) return review(8, path.endsWith('hide') && !path.endsWith('unhide'))
  if (path === '/workshop/orders') return { items: work, total: work.length, page: 1, page_size: 100 }
  if (path === '/manager/staff') return [{ id: 3, full_name: 'Nhân viên A', email: 'a@example.test', open_orders: 3 }, { id: 6, full_name: 'Nhân viên B', email: 'b@example.test', open_orders: 0 }]
  if (path === '/manager/quotations/pending-approval') return page([{ id: 9, order_id: 101, version: 2, sketch_id: 1, status: 'DRAFT', adjustment_status: 'PENDING_MANAGER', line_items: [], options: [], chosen_option: null, char_count: 40, quantity: 1, complexity: 'SIMPLE', computed_total: '100000', adjusted_total: '130000', adjustment_pct: '30', adjustment_reason: 'Giấy đặc biệt', final_total: '130000', min_deposit_pct: '50', eta: null, sent_at: null, valid_until: null, customer_note: null, created_at: now }])
  if (path === '/manager/schedule/queue') return page([])
  if (path === '/manager/schedule/config') return { working_hours: { days: [1, 2, 3, 4, 5], start: '08:00', end: '17:00', utc_offset_min: 420 }, eta_buffer_days: 2, lead_min: 30, slot_step_min: 15 }
  if (path === '/workshop/refunds') return { refunds: [], orphans: [] }
  if (/^\/manager\/(papers|pens|inks|compatibility|templates|styles|robots|technicians|pricing-config\/versions)$/.test(path)) return []
  if (path.endsWith('/notifications')) return { items: [], unread_count: 0, next_before_id: null }
  if (path.endsWith('/unread-count')) return { unread: 0, unread_count: 0 }
  if (path.includes('conversations')) return { items: [] }
  if (path === '/manager/jobs') return page([])
  return { items: [], total: 0, page: 1, page_size: 50 }
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
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const port = server.address().port
let browser, ws
const errors = []
const calls = []

try {
  browser = spawn(edge, ['--headless=new', '--no-sandbox', '--disable-extensions', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort, 'Browser did not expose a debugging port')
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((v) => v.type === 'page').webSocketDebuggerUrl)
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j })
  let nextId = 0
  const pending = new Map()
  const command = (method, params = {}) => new Promise((r, j) => { const id = ++nextId; const timer = setTimeout(() => { pending.delete(id); j(new Error('CDP timeout: ' + method)) }, 20000); pending.set(id, { method, resolve: (v) => { clearTimeout(timer); r(v) }, reject: (e) => { clearTimeout(timer); j(e) } }); ws.send(JSON.stringify({ id, method, params })) })
  const headers = (mime, extra = []) => [{ name: 'Content-Type', value: mime }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET,POST,PATCH,PUT,DELETE,OPTIONS' }, { name: 'Access-Control-Expose-Headers', value: 'Content-Disposition' }, ...extra]
  const fulfill = (id, data, code = 200, mime = 'application/json', extra = []) => command('Fetch.fulfillRequest', { requestId: id, responseCode: code, responseHeaders: headers(mime, extra), body: (Buffer.isBuffer(data) ? data : Buffer.from(JSON.stringify(data))).toString('base64') })

  ws.onmessage = async (message) => {
    const msg = JSON.parse(message.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) {
      // Route changes can cancel a paused request before its fixture response arrives.
      if (p.method.startsWith('Fetch.') && msg.error?.message === 'Invalid InterceptionId.') p.resolve({})
      else if (msg.error) p.reject(new Error(JSON.stringify(msg.error)))
      else p.resolve(msg.result)
    } return }
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text)
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (u.hostname === '127.0.0.1') return void command('Fetch.continueRequest', { requestId })
    if (request.method === 'OPTIONS') return void fulfill(requestId, {})
    const path = u.pathname.replace(/^.*\/api\/v1/, '')
    calls.push(`${request.method} ${path}${u.search}`)
    try {
      if (path.endsWith('/stream')) return void fulfill(requestId, Buffer.from('event: ready\ndata: {"unread_count":0}\n\n'), 200, 'text/event-stream')
      if (path === '/manager/reports/export') {
        const pdf = u.searchParams.get('format') === 'pdf'
        return void fulfill(requestId, Buffer.from('fixture'), 200, pdf ? 'application/pdf' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', [{ name: 'Content-Disposition', value: `attachment; filename="bao-cao_fixture.${pdf ? 'pdf' : 'xlsx'}"` }])
      }
      if (path === '/manager/reports' && u.searchParams.get('from') > u.searchParams.get('to')) return void fulfill(requestId, { error: { code: 'INVALID_PERIOD', message: 'x', details: null } }, 422)
      await fulfill(requestId, answer(request.method, path, u.searchParams))
    } catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  const asRole = (role) => command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:4,name:'Manager Thử',role:'staff',apiRole:'${role}'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');` })
  let script = (await asRole('MANAGER')).identifier
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 150; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${(await evaluate('document.body.innerText')).slice(0, 500)}`) }
  const go = async (route, ready = '.ws-manager .hd h1') => { await command('Page.navigate', { url: `http://127.0.0.1:${port}${route}` }); await wait(`!!document.querySelector(${JSON.stringify(ready)})`, `${route} ready`) }
  const shot = async (name) => {
    if (!shots) return
    await sleep(250)
    const { data } = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
    await writeFile(join(shots, `${name}.png`), Buffer.from(data, 'base64'))
  }
  const setInput = (selector, value) => evaluate(`(()=>{const i=document.querySelector(${JSON.stringify(selector)});const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(i,${JSON.stringify(value)});i.dispatchEvent(new Event('input',{bubbles:true}))})()`)

  const routes = [
    ['/staff', '.staff-kpis'],
    ['/staff/reports', '.mgr-table'],
    ['/staff/robots', '.mgr-robot'],
    ['/staff/reviews', '.mgr-alert'],
    ['/staff/approvals', '.ws-manager .panel'],
    ['/staff/schedule', '.ws-manager .main2'],
    ['/staff/catalog', '.ws-manager .main2'],
    ['/staff/pricing', '.ws-manager .main2'],
    ['/staff/refunds', '.ws-manager .main2'],
    ['/staff/review', '.ws-manager .main2'],
  ]
  for (const theme of ['light', 'dark']) for (const lang of ['vi', 'ja', 'en']) for (const width of [1440, 768, 360]) {
    await command('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 500 })
    await go('/staff')
    await evaluate(`localStorage.setItem('aivhrs-theme','${theme}');localStorage.setItem('aivhrs-lang','${lang}')`)
    for (const [route, ready] of routes) {
      await go(route, ready)
      assert.equal(await evaluate(`document.documentElement.getAttribute('data-theme')`), theme, 'Shared appearance preference')
      assert.ok(await evaluate(`!!document.querySelector('.staff-sidebar .staff-nav a.on[aria-current=page]')`), `Active sidebar item on ${route}`)
      assert.equal(await evaluate(`document.querySelectorAll('.staff-sidebar .staff-nav a').length`), 11, 'Manager destinations in the sidebar')
      if (route !== '/staff') assert.equal(await evaluate(`document.querySelector('.staff-back')?.getAttribute('href')`), '/staff', `Back link on ${route}`)
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), `No horizontal overflow: ${route} ${theme} ${lang} ${width}`)
      assert.equal(await evaluate(`/\\b(mgr|adm|err|os|js|rb|td)\\.[a-zA-Z]+\\.?[A-Za-z0-9_]*\\b/.test(document.querySelector('.ws-manager .main2').innerText.replace(/[\\w.-]+@[\\w.-]+/g,''))`), false, `No raw translation keys: ${route} ${lang}`)
      if (route === '/staff/review') {
        await wait(`!!document.querySelector('.ol-filter .adm-select-trigger')`, 'Manager stage selector')
        assert.equal(await evaluate(`document.querySelectorAll('.ol-stages button').length`),0,'No wrapping stage pills')
        await evaluate(`document.querySelector('.ol-filter .adm-select-trigger').click()`)
        await wait(`!!document.querySelector('[role=listbox]')`, 'Manager filter menu')
        assert.equal(await evaluate(`document.querySelectorAll('[role=option]').length`),6,'All stage filters retained')
        assert.ok(await evaluate(`(()=>{const r=document.querySelector('[role=listbox]').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight})()`),'Stage menu stays inside viewport')
        await evaluate(`document.querySelector('[role=option]:last-child').click()`)
        await wait(`!document.querySelector('[role=listbox]')`, 'Stage selection closes menu')
        assert.ok(await evaluate(`document.querySelector('.ol-filter .adm-select-trigger').textContent.includes('(0)')`),'Closed stage count shown')
        await evaluate(`document.querySelector('.ol-filter .adm-select-trigger').click()`)
        await wait(`!!document.querySelector('[role=listbox]')`, 'Reopen stage menu')
        await evaluate(`document.querySelector('[role=option]').click()`)
        await wait(`document.querySelectorAll('.ol-row').length===3`, 'Open stage restores orders')
      }
      if (lang !== 'en' && width !== 768) await shot(`${theme}-${lang}-${width}${route.replaceAll('/', '_')}`)
    }
    if (width === 360) {
      await go('/staff')
      await evaluate(`document.querySelector('.staff-sidebar-menu').click()`)
      await wait(`document.querySelector('.ws-manager').classList.contains('staff-sidebar-open')`, 'drawer opens')
      await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape'}))`)
      await wait(`!document.querySelector('.ws-manager').classList.contains('staff-sidebar-open')`, 'drawer closes on Escape')
    }
  }

  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false })
  await evaluate(`localStorage.setItem('aivhrs-lang','en');localStorage.setItem('aivhrs-theme','light')`)

  // Dashboard numbers come from /manager/dashboard.
  await go('/staff', '.staff-kpis')
  await wait(`document.querySelector('.staff-kpis').innerText.includes('48')`, 'open orders total from the dashboard API')
  assert.ok(await evaluate(`document.body.innerText.includes('VHRS-T2')`), 'Late order listed')
  assert.ok(await evaluate(`document.body.innerText.includes('Giấy dó A4')`), 'Low stock listed')

  // Reports: group switch reloads, a reversed period shows the translated 422, Excel/PDF export through the Bearer fetch.
  await go('/staff/reports', '.mgr-table')
  calls.length = 0
  await evaluate(`[...document.querySelectorAll('.staff-period button')].find(b=>b.textContent==='Week').click()`)
  await sleep(400)
  assert.ok(calls.some((c) => c.startsWith('GET /manager/reports?') && c.includes('group=week')), 'Group change reloads the report')
  await setInput('input[type=date]', '2026-12-31')
  await wait(`document.body.innerText.includes('The start date must be on or before the end date.')`, 'INVALID_PERIOD translated')
  await evaluate(`document.querySelector('.ph .vh-link').click()`)
  await wait(`!document.body.innerText.includes('The start date must be on or before the end date.')`, 'reset period')
  calls.length = 0
  await evaluate(`[...document.querySelectorAll('.staff-page-actions button')].at(-1).click()`)
  await sleep(500)
  assert.ok(calls.some((c) => c.startsWith('GET /manager/reports/export?') && c.includes('format=xlsx')), 'Excel export')
  calls.length = 0
  await evaluate(`[...document.querySelectorAll('.staff-page-actions button')][0].click()`)
  await sleep(500)
  assert.ok(calls.some((c) => c.includes('/manager/reports/export?') && c.includes('format=pdf')), 'PDF export')

  // Robots: red banner, ack, red close with a note after confirming, job detail with process check, events and quality, incident close, catalogue.
  await go('/staff/robots', '.mgr-alert')
  assert.ok(await evaluate(`!!document.querySelector('.mgr-alert.red')`), 'Red alert stands out')
  calls.length = 0
  await evaluate(`[...document.querySelectorAll('.mgr-alert button')].find(b=>b.textContent.includes('Seen')).click()`)
  await sleep(400)
  assert.ok(calls.includes('POST /manager/alerts/12/ack'), 'Acknowledge calls the Manager route')
  const resolveBtn = `[...document.querySelectorAll('.mgr-alert.red button')].find(b=>b.textContent.includes('Close'))`
  assert.equal(await evaluate(`${resolveBtn}.disabled`), true, 'Close needs a note')
  await setInput('.mgr-alert.red input', 'Robot checked, stopped and safe')
  await evaluate(`window.confirm=()=>true`)
  calls.length = 0
  await evaluate(`${resolveBtn}.click()`)
  await sleep(400)
  assert.ok(calls.includes('POST /manager/alerts/12/resolve'), 'Manager closes a red alert')
  await evaluate(`[...document.querySelectorAll('button')].find(b=>b.textContent==='Process check').click()`)
  await wait(`document.body.innerText.includes('Process not followed') && document.body.innerText.includes('Package downloaded') && document.body.innerText.includes('Needs review') && document.body.innerText.includes('Kỹ thuật viên A')`, 'Job detail, compliance, events and quality')
  calls.length = 0
  await evaluate(`(()=>{const a=[...document.querySelectorAll('.mgr-alert')].find(x=>x.innerText.includes('Cánh tay dừng'));const i=a.querySelector('input');const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;set.call(i,'Đã thay dây');i.dispatchEvent(new Event('input',{bubbles:true}));setTimeout(()=>[...a.querySelectorAll('button')].at(-1).click(),50)})()`)
  await sleep(500)
  assert.ok(calls.includes('POST /manager/incidents/3/resolve'), 'Incident closed')
  await evaluate(`document.querySelector('details.mgr-more').open=true`)
  calls.length = 0
  await evaluate(`[...document.querySelectorAll('details.mgr-more tbody tr')][1].querySelectorAll('input[type=checkbox]')[3].click()`)
  await sleep(400)
  assert.ok(calls.includes('PATCH /manager/alert-catalog/CALIBRATION_OLD'), 'Catalogue entry changed')
  assert.equal(await evaluate(`[...document.querySelectorAll('details.mgr-more tbody tr')][0].querySelectorAll('input[type=checkbox]')[3].disabled`), true, 'Red entry e-mail is locked')

  // Opening a job from the dashboard (?job=) shows its detail directly.
  await go('/staff/robots?job=291', '.mgr-robot')
  await wait(`document.body.innerText.includes('Job #291')`, 'job opened from the URL')

  // Reviews: hide needs a reason of five characters; filters reload.
  await go('/staff/reviews', '.mgr-alert')
  const hideBtn = `[...document.querySelectorAll('.mgr-alert')][0].querySelector('button')`
  assert.equal(await evaluate(`${hideBtn}.disabled`), true, 'Hide needs a reason')
  await setInput('.mgr-alert input', 'Spam link')
  calls.length = 0
  await evaluate(`${hideBtn}.click()`)
  await sleep(400)
  assert.ok(calls.includes('POST /manager/reviews/8/hide'), 'Review hidden with a reason')
  calls.length = 0
  await evaluate(`[...document.querySelectorAll('.staff-period button')].find(b=>b.textContent==='Hidden').click()`)
  await sleep(400)
  assert.ok(calls.some((c) => c.startsWith('GET /manager/reviews?') && c.includes('hidden=true')), 'Visibility filter reloads')

  // Role gate: a Staff account cannot open the Manager-only screens by URL and keeps the Staff sidebar.
  await command('Page.removeScriptToEvaluateOnNewDocument', { identifier: script })
  script = (await asRole('STAFF')).identifier
  meRole = 'STAFF'
  for (const route of ['/staff/reports', '/staff/robots', '/staff/reviews', '/staff/approvals']) {
    await command('Page.navigate', { url: `http://127.0.0.1:${port}${route}` })
    await wait(`!!document.querySelector('.vh-h1')`, `${route} blocked for Staff`)
    assert.equal(await evaluate(`!!document.querySelector('.ws-manager')`), false, `${route} hidden from Staff`)
  }
  await go('/staff', '.ws-staff .hd h1')
  assert.equal(await evaluate(`!!document.querySelector('.ws-manager')`), false, 'Staff keeps the Staff frame')
  assert.equal(await evaluate(`document.querySelectorAll('.staff-sidebar .staff-nav a').length`), 4, 'Staff keeps its four destinations')

  assert.deepEqual(errors, [])
  console.log('PASS: Manager in the Staff frame, 10 screens × light/dark × vi/ja/en × 1440/768/360 (no overflow, no raw keys, active sidebar item, back links, drawer); dashboard from /manager/dashboard; reports reload, translated 422, Excel/PDF export; robots ack, red close with note, job detail/compliance/events/quality, incident close, catalogue rules; reviews hide with reason and filters; Staff blocked from Manager screens. API fixtures only.')
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close()
}
