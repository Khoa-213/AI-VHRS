// Real Edge DOM smoke test, with all API/storage calls intercepted. No production credentials or data.
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
assert.ok(existsSync(join(root, 'dist/index.html')), 'Run npm.cmd run build first')
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-customer-browser-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-10-25T00:00:00Z'
const order = { id: 42, code: 'VH-TEST-FINAL', order_type: 'OT3_TEMPLATE', order_status: 'AWAITING_FINAL_PAYMENT', production_status: 'FINISHED', total_amount: '7400', deposit_amount: '3700', deposit_pct: '50', delivery_method: 'DELIVERY', quantity: 1, inputs: [], created_at: now, last_saved_at: now }
const fee = 30000, balance = 3700
const payments = [{ id: 1, type: 'DEPOSIT', amount: '3700', status: 'SUCCESS', gateway: 'VNPAY', mode: 'MOCK', created_at: now }]
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
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text)
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (u.hostname === '127.0.0.1') return void command('Fetch.continueRequest', { requestId })
    if (request.method === 'OPTIONS') return void fulfill(requestId, {})
    const path = u.pathname.replace('/api/v1', '')
    let data = {}
    try {
      if (path === '/me') data = { id: 17, email: 'test@example.test', full_name: 'Browser Test', role: 'CUSTOMER', status: 'ACTIVE', addresses: [], created_at: now }
      else if (path === '/orders/42') data = order
      else if (path === '/orders') data = { items: [order], total: 1, page: 1, page_size: 20 }
      else if (path.startsWith('/catalog/') || path.startsWith('/locations/')) data = []
      else if (path === '/privacy-policy') data = { version: '1', content: 'Test privacy policy' }
      else if (path.endsWith('/quotation')) data = { id: 1, version: 1, status: 'APPROVED', line_items: [], options: [], chosen_option: null, char_count: 10, quantity: 1, final_total: '7400', min_deposit_pct: '50', eta: null, valid_until: null, pdf_url: null, note: '', sketch: null }
      else if (path.endsWith('/product-photos')) data = { photos: [], sketch_preview_url: null, acceptance_due_at: null, can_accept: true, can_request_rewrite: true }
      else if (path.endsWith('/refunds') || path.endsWith('/shipment')) data = []
      else if (path.endsWith('/review')) return void fulfill(requestId, { error: { code: 'REVIEW_NOT_FOUND', message: 'No review' } }, 404)
      else if (path.includes('notifications')) data = { items: [], total: 0, unread_count: 0 }
      else if (path === '/orders/42/delivery-quote') data = quote()
      else if (path === '/orders/42/payments' && request.method === 'GET') data = payments
      else if (path === '/payments/gateways') data = [{ gateway: 'VNPAY', mode: 'MOCK', enabled: true }]
      else if (path.includes('conversations')) data = path.endsWith('unread-count') ? { unread_count: 0 } : { items: [], total: 0 }
      await fulfill(requestId, data)
    } catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:'customer',apiRole:'CUSTOMER'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}\n${await evaluate('document.body.innerText')}`) }
  const button = (text) => `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`
  const click = async (text) => { await wait(`!!(${button(text)}) && !(${button(text)}).disabled && !(${button(text)}).closest('fieldset:disabled')`, text); await evaluate(`(${button(text)}).click()`); await sleep(100) }

  await command('Page.navigate', { url: `http://127.0.0.1:${port}/account` })
  await wait(`!!document.querySelector('.ac')`, 'initial account')
  const cases = [
    ['/account', 'COMPLETED', '.ac'],
    ['/account/orders', 'COMPLETED', '.ac-order'],
    ['/account/drafts', 'DRAFT', '.ac'],
    ['/create-order#mode=text', 'DRAFT', '.co'],
    ['/create-order#mode=upload', 'DRAFT', '.co'],
    ['/create-order#mode=draw', 'DRAFT', '.co'],
    ...['SUBMITTED', 'NEED_INFO', 'REJECTED', 'AWAITING_PRIVACY', 'QUOTED', 'CONFIRMED', 'AWAITING_ACCEPTANCE', 'AWAITING_FINAL_PAYMENT', 'DELIVERING', 'COMPLETED', 'CANCELLED'].map(status => ['/orders/42/review', status, '.ov']),
    ['/orders/42/deposit', 'AWAITING_DEPOSIT', '.ov'],
    ['/orders/42/delivery', 'AWAITING_FINAL_PAYMENT', '.ov'],
    ['/orders/42/payment', 'AWAITING_FINAL_PAYMENT', '.ov'],
    ['/payment/result?order_id=42', 'COMPLETED', '.vh-wrap'],
    ['/reset-password', 'COMPLETED', '.entry-reset'],
  ]
  for (const lang of ['en', 'vi', 'ja']) {
    for (const theme of ['light', 'dark']) {
      for (const width of [1440, 390]) {
        await command('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 600 })
        for (const [path, status, selector] of cases) {
          order.order_status = status
          await evaluate(`localStorage.setItem('aivhrs-lang',${JSON.stringify(lang)});localStorage.setItem('aivhrs-theme',${JSON.stringify(theme)})`)
          await command('Page.navigate', { url: `http://127.0.0.1:${port}${path}` })
          await wait(`!!document.querySelector(${JSON.stringify(selector)})`, `${path} ${status}`)
          await sleep(100)
          const state = await evaluate(`(() => {
            const main = document.querySelector('main'); const header = document.querySelector('.lp-header');
            return { shared: !!document.querySelector('.customer-root'), legacy: !!document.querySelector('.vh-header'),
              overflow: document.documentElement.scrollWidth > innerWidth + 1,
              overlap: main.getBoundingClientRect().top + parseFloat(getComputedStyle(main).paddingTop) < header.getBoundingClientRect().bottom - 1,
              theme: document.documentElement.dataset.theme,
              radius: getComputedStyle(main).borderRadius };
          })()`)
          const context = `${lang}/${theme}/${width} ${path} ${status}: ${JSON.stringify(state)}`
          assert.ok(state.shared && !state.legacy, context)
          assert.equal(state.overflow, false, context)
          assert.equal(state.overlap, false, context)
          assert.notEqual(state.radius, '0px', context)
          assert.equal(state.theme, theme, context)
          assert.ok(await evaluate(`[...document.querySelectorAll('.ov .vh-choice,.ov .vh-input,.ov .ov-opt')].every(el => parseFloat(getComputedStyle(el).borderRadius) >= 12)`), 'Legacy square controls: ' + context)
          if (lang === 'vi' && ((theme === 'light' && width === 1440 && status === 'QUOTED') || (theme === 'dark' && width === 390 && path.endsWith('/delivery')))) {
            const shot = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })
            const file = join(scratch, `customer-${theme}-${width}.png`)
            await writeFile(file, Buffer.from(shot.data, 'base64'))
            console.log('Screenshot: ' + file)
          }
        }
      }
    }
  }
  assert.deepEqual(errors, [])
  console.log(`PASS: ${cases.length * 12} customer route/status, language, theme and viewport combinations. Shared frame, no legacy header, no horizontal overflow or header overlap. All API calls intercepted.`)
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close()
}
