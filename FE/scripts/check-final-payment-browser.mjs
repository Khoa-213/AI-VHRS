// Real Edge DOM smoke test, with all API/storage calls intercepted. No production credentials or data.
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
assert.ok(existsSync(join(root, 'dist/index.html')), 'Run npm.cmd run build first')
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-final-browser-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-10-25T00:00:00Z'
const order = { id: 42, code: 'VH-TEST-FINAL', order_type: 'OT3_TEMPLATE', order_status: 'AWAITING_FINAL_PAYMENT', production_status: 'FINISHED', total_amount: '7400', deposit_amount: '3700', deposit_pct: '50', delivery_method: 'DELIVERY', quantity: 1, inputs: [], created_at: now }
let fee = 30000, balance = 3700, changed = false, starts = 0
let payments = [{ id: 1, type: 'DEPOSIT', amount: '3700', status: 'SUCCESS', gateway: 'VNPAY', mode: 'MOCK', created_at: now }]
const quote = () => ({ balance: String(balance), paper_size: 'A4', package_type: 'DOCUMENT', is_fallback_fee: true, chosen: order.delivery_method, options: { DELIVERY: { fee: String(fee), total_due: String(balance + fee) }, PICKUP: { fee: '0', total_due: String(balance) } }, services: [], chosen_service: order.delivery_method === 'DELIVERY' ? { carrier: 'GHTK', service_code: 'STANDARD', service_name: 'Standard', fee: String(fee), total_due: String(balance + fee), is_fallback_fee: true, mode: 'FALLBACK' } : null })
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
  const fulfill = (id, data, code = 200, mime = 'application/json') => command('Fetch.fulfillRequest', { requestId: id, responseCode: code, responseHeaders: [{ name: 'Content-Type', value: mime }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET,POST,PATCH,PUT,DELETE,OPTIONS' }], body: (Buffer.isBuffer(data) ? data : Buffer.from(JSON.stringify(data))).toString('base64') })

  ws.onmessage = async (message) => {
    const msg = JSON.parse(message.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) msg.error ? p.reject(new Error(JSON.stringify(msg.error))) : p.resolve(msg.result); return }
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.text)
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (u.hostname === '127.0.0.1') return void command('Fetch.continueRequest', { requestId })
    if (request.method === 'OPTIONS') return void fulfill(requestId, {})
    const path = u.pathname.replace('/api/v1', '')
    const body = JSON.parse(request.postData || '{}')
    let data = {}
    try {
      if (path === '/me') data = { id: 17, email: 'test@example.test', full_name: 'Browser Test', role: 'CUSTOMER', status: 'ACTIVE', addresses: [], created_at: now }
      else if (path === '/orders/42') data = order
      else if (path === '/orders/42/delivery-quote') data = quote()
      else if (path === '/orders/42/payments' && request.method === 'GET') data = payments
      else if (path === '/payments/gateways') data = [{ gateway: 'VNPAY', mode: 'MOCK', enabled: true }]
      else if (path === '/orders/42/payments/final') {
        starts++
        if (changed) { changed = false; fee = 32000; return void fulfill(requestId, { error: { code: 'FEE_CHANGED', message: 'Fee changed' } }, 409) }
        assert.equal(body.expected_total, balance + (order.delivery_method === 'DELIVERY' ? fee : 0))
        payments = payments.filter(p => p.type === 'DEPOSIT')
        const total = body.expected_total
        if (!total) order.order_status = 'READY_TO_DELIVER'
        if (balance) payments.push({ id: 2, type: 'FINAL', amount: String(balance), status: 'PENDING', gateway: body.gateway, mode: 'MOCK', created_at: now })
        if (order.delivery_method === 'DELIVERY' && fee) payments.push({ id: 3, type: 'SHIPPING', amount: String(fee), status: 'PENDING', gateway: body.gateway, mode: 'MOCK', created_at: now })
        data = { payment_required: total > 0, total_due: String(total), order_status: order.order_status, payments: payments.filter(p => p.type !== 'DEPOSIT') }
      } else if (path.endsWith('/mock-checkout')) {
        payments.filter(p => p.type !== 'DEPOSIT').forEach(p => p.status = body.result)
        if (body.result === 'SUCCESS') order.order_status = 'READY_TO_DELIVER'
        data = { result: body.result, status: body.result, order_status: order.order_status }
      } else if (path.includes('conversations')) data = path.endsWith('unread-count') ? { unread_count: 0 } : { items: [], total: 0 }
      await fulfill(requestId, data)
    } catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:'customer',apiRole:'CUSTOMER'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}`) }
  const button = (text) => `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`
  const click = async (text) => { await wait(`!!(${button(text)}) && !(${button(text)}).disabled && !(${button(text)}).closest('fieldset:disabled')`, text); await evaluate(`(${button(text)}).click()`); await sleep(100) }

  const navigate = () => command('Page.navigate', { url: `http://127.0.0.1:${port}/orders/42/payment` })
  await navigate()
  await wait(`document.body.textContent.includes('Final payment')`, 'final payment page')
  await wait(`!!(${button('Pay 33.700\u20ab')})`, 'full amount')
  assert.equal(starts, 0)
  await click('Pay 33.700\u20ab')
  await wait(`document.body.textContent.includes('Pretend to pay 33.700\u20ab')`, 'combined mock amount')
  await command('Page.reload')
  await wait(`document.body.textContent.includes('Pretend to pay 33.700\u20ab')`, 'pending checkout restored')
  await click('Payment failed')
  await click('Pay 33.700\u20ab')
  await click('Payment succeeded')
  await wait(`document.body.textContent.includes('Your order is fully paid')`, 'paid')
  assert.equal(order.order_status, 'READY_TO_DELIVER')
  assert.ok(await evaluate(`document.querySelector('.vh-total-row').textContent.includes('33.700\u20ab')`))
  order.order_status = 'AWAITING_FINAL_PAYMENT'; payments = payments.filter(p => p.type === 'DEPOSIT'); changed = true
  await navigate()
  await click('Pay 33.700\u20ab')
  await wait(`!!(${button('Pay 35.700\u20ab')})`, 'changed fee requires another confirmation')
  await click('Pay 35.700\u20ab')
  await click('Payment succeeded')
  for (const lang of ['vi', 'ja']) {
    await evaluate(`localStorage.setItem('aivhrs-lang',${JSON.stringify(lang)})`)
    await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
    await navigate()
    await wait(`document.querySelector('.pay-done') !== null`, 'translated paid page')
    assert.equal(await evaluate(`document.body.textContent.includes('fp.')`), false)
    assert.ok(await evaluate('document.documentElement.scrollWidth <= 391'), 'Mobile overflow')
  }
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  order.order_status = 'AWAITING_FINAL_PAYMENT'; order.delivery_method = 'PICKUP'; balance = 0; order.deposit_amount = '7400'; payments = payments.filter(p => p.type === 'DEPOSIT')
  await navigate()
  await click('Pay 0\u20ab')
  await wait(`document.body.textContent.includes('Your order is fully paid')`, 'zero due completion')
  assert.equal(order.order_status, 'READY_TO_DELIVER')
  assert.deepEqual(errors, [])
  console.log('PASS: grouped final/shipping checkout, reload pending, failed retry, success, fee change confirmation, zero balance pickup, Vietnamese/Japanese and mobile layout. All API calls intercepted with local fixtures.')
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close()
}
