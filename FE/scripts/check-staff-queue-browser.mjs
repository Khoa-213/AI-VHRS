// Real Chromium DOM, 100 fixture orders, no external API mutations.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, mkdtemp, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, extname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { spawn } from 'node:child_process'

const root = fileURLToPath(new URL('../', import.meta.url))
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-intake-'))
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const now = Date.now()
const orders = Array.from({ length: 100 }, (_, i) => ({
  id: i + 1, code: `VHRS-${String(i + 1).padStart(3, '0')}`, customer_name: i === 74 ? 'Outside first page' : `Customer ${i + 1}`,
  assigned_staff_id: i < 80 ? null : i < 90 ? 17 : 18, order_status: i < 85 || i >= 90 ? 'SUBMITTED' : 'ACCEPTED',
  order_type: 'OT3_TEMPLATE', production_status: 'NOT_STARTED', quantity: 1, workshop_suggest_materials: true,
  submitted_at: new Date(now - (101 - i) * 60000).toISOString(), created_at: new Date(now).toISOString(), inputs: [],
}))
const notifications = Array.from({ length: 12 }, (_, i) => ({ id: i + 1, order_id: i + 1, msg_code: 'NEW_ORDER', type: 'ORDER_STATUS_CHANGED', title: `New order ${i + 1}`, body: 'Open order', is_read: false, created_at: new Date(Math.floor(now / 60000) * 60000).toISOString() }))
notifications.push({ ...notifications[0], id: 13, order_id: 75, msg_code: 'ASSIGNED', title: 'Assigned order 75' })
let actor = 17
let competing = false
const requests = []
const legacy = process.env.STAFF_QUEUE_LEGACY === '1'
const counts = () => ({ pool: orders.filter((o) => o.assigned_staff_id === null && o.order_status === 'SUBMITTED').length,
  mine: orders.filter((o) => o.assigned_staff_id === actor).reduce((n, o) => ({ ...n, [o.order_status]: (n[o.order_status] || 0) + 1 }), {}) })
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
try {
  browser = spawn(process.env.TECH_BROWSER_PATH || 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', ['--headless=new', '--no-sandbox', '--disable-extensions', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { windowsHide: true, stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort)
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl)
  await new Promise((r, reject) => { ws.onopen = r; ws.onerror = reject })
  let next = 0
  const pending = new Map()
  const command = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++next
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout ' + method)) }, 15000)
    pending.set(id, { method, resolve: (v) => { clearTimeout(timer); resolve(v) }, reject: (e) => { clearTimeout(timer); reject(e) } })
    ws.send(JSON.stringify({ id, method, params }))
  })
  const fulfill = (id, data, status = 200, type = 'application/json') => command('Fetch.fulfillRequest', { requestId: id, responseCode: status, responseHeaders: [{ name: 'Content-Type', value: type }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: '*' }], body: Buffer.from(typeof data === 'string' ? data : JSON.stringify(data)).toString('base64') })
  ws.onmessage = async (event) => {
    const msg = JSON.parse(event.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) msg.error && !(p.method.startsWith('Fetch.') && msg.error.message === 'Invalid InterceptionId.') ? p.reject(new Error(JSON.stringify(msg.error))) : p.resolve(msg.result); return }
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text)
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (u.hostname === '127.0.0.1') return void command('Fetch.continueRequest', { requestId })
    if (request.method === 'OPTIONS') return void fulfill(requestId, {})
    const path = u.pathname.replace('/api/v1', '')
    requests.push(path + u.search)
    try {
      let data = {}
      if (path === '/me') data = { id: actor, full_name: `Staff ${actor}`, email: 'staff@example.test', role: 'STAFF', status: 'ACTIVE', addresses: [], created_at: new Date(now).toISOString() }
      else if (path === '/workshop/queue-counts') {
        if (legacy) return void fulfill(requestId, { detail: 'Not Found' }, 404)
        data = counts()
      }
      else if (path === '/workshop/orders') {
        let rows = orders.filter((o) => o.assigned_staff_id === actor || o.assigned_staff_id === null && o.order_status === 'SUBMITTED')
        const s = new URLSearchParams(u.search), statuses = s.getAll('status')
        if (legacy) { s.delete('mine'); s.delete('order_ids'); s.delete('q') }
        const ids = s.getAll('order_ids').map(Number), q = (s.get('q') || '').toLowerCase()
        rows = rows.filter((o) => (!s.has('mine') || o.assigned_staff_id === actor) && (!s.has('unassigned') || o.assigned_staff_id === null && o.order_status === 'SUBMITTED') && (!statuses.length || statuses.includes(o.order_status)) && (!ids.length || ids.includes(o.id)) && (!q || o.code.toLowerCase().includes(q) || o.customer_name.toLowerCase().includes(q))).sort((a, b) => a.submitted_at.localeCompare(b.submitted_at))
        const page = Number(s.get('page') || 1), size = Number(s.get('page_size') || 20)
        data = { items: rows.slice((page - 1) * size, page * size), total: rows.length, page, page_size: size }
      } else if (/^\/workshop\/orders\/\d+\/accept$/.test(path)) {
        const o = orders[Number(path.split('/')[3]) - 1]
        if (competing) { o.assigned_staff_id = 18; o.order_status = 'ACCEPTED'; competing = false; return void fulfill(requestId, { error: { code: 'ORDER_NOT_FOUND', message: 'Not found' } }, 404) }
        o.assigned_staff_id = actor; o.order_status = 'ACCEPTED'; data = o
      } else if (/^\/workshop\/orders\/\d+$/.test(path)) data = orders[Number(path.split('/')[3]) - 1]
      else if (path === '/me/notifications') data = { items: notifications.slice().reverse(), unread_count: notifications.filter((n) => !n.is_read).length, next_before_id: null }
      else if (/\/notifications\/\d+\/read$/.test(path)) { data = notifications.find((n) => n.id === Number(path.split('/')[3])); data.is_read = true }
      else if (path.endsWith('/stream')) return void fulfill(requestId, 'event: ready\ndata: {"unread_count":13}\n\n', 200, 'text/event-stream')
      else if (path.includes('conversations')) data = path.endsWith('unread-count') ? { unread_count: 0 } : { items: [], total: 0 }
      else if (path === '/workshop/refunds') data = { refunds: [], orphans: [] }
      else if (path.startsWith('/catalog/') || path.endsWith('/sketches') || path.endsWith('/change-requests') || path.endsWith('/quotations')) data = []
      await fulfill(requestId, data)
    } catch (error) { errors.push(error.stack); await fulfill(requestId, { error: { code: 'FIXTURE', message: error.message } }, 500) }
  }
  await command('Page.enable'); await command('Runtime.enable'); await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'fixture',refresh:'fixture'}));if(!localStorage.getItem('aivhrs-user'))localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Staff A',role:'staff',apiRole:'STAFF'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','vi');` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${await evaluate('document.body.innerText')}`) }
  const goto = async (path) => { await command('Page.navigate', { url: `http://127.0.0.1:${port}${path}` }); await sleep(200); await wait(`!!document.querySelector('.ws-staff')`, 'Staff frame') }
  const setSearch = async (value) => evaluate(`(()=>{const el=document.querySelector('.ol-search input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,${JSON.stringify(value)});el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
  const click = async (selector) => { await wait(`!!document.querySelector(${JSON.stringify(selector)})`, selector); await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`) }

  await goto('/staff')
  await wait(`document.querySelector('.k-whole-link').textContent.includes('85')`, '80 pool plus 5 assigned')
  assert.match(await evaluate(`document.querySelector('.k-whole-link').textContent`), /80.*5/)
  assert.equal(await evaluate(`(()=>{const k=document.querySelector('.k-whole-link'),r=k.getBoundingClientRect(),e=document.elementFromPoint(r.left+20,r.top+r.height-15);return e.closest('a')?.getAttribute('href')})()`), '/staff/review?scope=pool', 'Whole KPI is clickable')
  await click('.k-whole-link a')
  await wait(`document.querySelectorAll('.ol-row').length===20`, '20 rows')
  assert.equal(await evaluate(`document.querySelectorAll('.ol-filter').length`), 0)
  assert.match(await evaluate(`document.querySelector('.ol-row').textContent`), /VHRS-001/)
  await click('.staff-queue-pages button:last-child')
  await wait(`document.querySelector('.ol-row')?.textContent.includes('VHRS-021')`, 'second page')
  await setSearch('Outside first page')
  await wait(`document.querySelectorAll('.ol-row').length===1 && document.querySelector('.ol-row').textContent.includes('075')`, 'server searches beyond page one')
  await click('.ol-row')
  await wait(`document.querySelector('.wk-order-head')?.textContent.includes('VHRS-075')`, 'correct detail')
  await click('.wk-actions .vh-btn--primary')
  await wait(`!!document.querySelector('.staff-intake-success')`, 'intake success')
  await click('.staff-intake-success a')
  await wait(`location.pathname==='/staff/review' && document.querySelectorAll('.ol-row').length===0`, 'return retains search and removes received order')
  await evaluate(`document.querySelectorAll('.ol-scope button')[1].click()`)
  await wait(`!!document.querySelector('.ol-filter') && document.querySelector('.ol-scroll').textContent.includes('075')`, 'received order in my workflow')
  await click('button[aria-controls="staff-queue-sketch"]')
  assert.equal(await evaluate(`document.querySelector('#staff-queue-sketch').hidden`), true, 'Sketch group collapses')
  assert.equal(await evaluate(`document.querySelector('#staff-queue-customer').hidden`), false, 'Other groups stay open')
  await click('button[aria-controls="staff-queue-sketch"]')
  assert.equal(await evaluate(`document.querySelector('#staff-queue-sketch').hidden`), false, 'Sketch group reopens')

  await goto('/staff/review?scope=pool&page=2')
  await wait(`document.querySelectorAll('.ol-row').length===20`, 'page two restored')
  await evaluate(`document.querySelector('.ws-staff>.app2').scrollTo({top:500})`)
  await click('.ol-row')
  competing = true
  await click('.wk-actions .vh-btn--primary')
  await wait(`document.body.textContent.includes('Đơn đã được nhân viên khác tiếp nhận')`, 'clear conflict message')
  await click('.wk-order>a.vh-btn')
  await wait(`location.pathname==='/staff/review' && location.search.includes('page=2')`, 'conflict returns to same page')
  await sleep(100)
  assert.ok(await evaluate(`document.querySelector('.ws-staff>.app2').scrollTop>450`), 'Return restores content scroll position')

  await click('.nbell-btn')
  await wait(`document.querySelector('.nbell-pop')?.textContent.includes('12 đơn mới')`, 'burst grouped')
  const before = counts().pool
  await evaluate(`[...document.querySelectorAll('.nbell-pop li button')].find(b=>b.textContent.includes('12 đơn mới')).click()`)
  await wait(`document.querySelectorAll('.ol-row').length===12 && location.search.includes('ids=')`, 'exact notification batch')
  assert.equal(counts().pool, before, 'Reading notifications does not receive orders')
  await click('.nbell-btn')
  await wait(`!!document.querySelector('.nbell-pop')`, 'notification panel')
  await evaluate(`[...document.querySelectorAll('.nbell-pop li button')].find(b=>b.textContent.includes('Assigned order 75')).click()`)
  await wait(`location.pathname==='/staff/review/75' && document.querySelector('.wk-order-head')?.textContent.includes('075')`, 'single notification opens exact order')

  actor = 18
  await evaluate(`localStorage.setItem('aivhrs-user',JSON.stringify({id:18,name:'Staff B',role:'staff',apiRole:'STAFF'}))`)
  await goto('/staff/review?scope=mine')
  await wait(`!!document.querySelector('.ol-filter')`, 'second Staff workflow')
  assert.ok(!(await evaluate(`document.querySelector('.ol-scroll').textContent`)).includes('VHRS-075'), 'Second Staff cannot see Staff A order')
  actor = 17
  await evaluate(`localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Staff A',role:'staff',apiRole:'STAFF'}))`)
  for (const lang of ['vi', 'en', 'ja']) for (const theme of ['light', 'dark']) for (const width of [1440, 390]) {
    await evaluate(`localStorage.setItem('aivhrs-lang','${lang}');localStorage.setItem('aivhrs-theme','${theme}')`)
    await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 500 })
    await goto('/staff/review?scope=pool')
    await wait(`document.querySelectorAll('.ol-row').length===20`, 'translated list')
    assert.ok(await evaluate(`document.documentElement.scrollWidth<=innerWidth+1`), `No overflow ${lang} ${theme} ${width}`)
    if (lang === 'vi' && theme === 'light') { const shot = await command('Page.captureScreenshot', { format: 'png' }); await writeFile(join(scratch, `queue-${width}.png`), Buffer.from(shot.data, 'base64')) }
  }
  assert.ok(requests.some((r) => legacy ? r.includes('/workshop/orders?page=1&page_size=100') : r.includes('q=Outside+first+page') && r.includes('page_size=20')))
  assert.ok(!(await evaluate('document.body.innerText')).includes('Not Found'))
  assert.deepEqual(errors, [])
  console.log('PASS: 100 orders, two Staff fixtures; KPI hit area, scoped server search/page 20, accept/return, conflict UX, batch/single notification links, unread independence, en/vi/ja light/dark desktop/mobile. Screenshots: ' + scratch)
} finally { ws?.close(); browser?.kill(); server.closeAllConnections(); server.close() }
