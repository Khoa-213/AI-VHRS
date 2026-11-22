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
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-fulfillment-browser-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-10-25T00:00:00Z'
let actorRole = 'STAFF', mutations = 0, nextId = 100, shipmentError = false
const order = { id: 42, code: 'VH-TEST-SHIPPING', customer_name: 'Test Customer', assigned_staff_id: 17, order_type: 'OT3_TEMPLATE', order_status: 'READY_TO_DELIVER', production_status: 'FINISHED', total_amount: '7400', deposit_amount: '3700', deposit_pct: '50', delivery_method: 'DELIVERY', delivery_address: { receiver: 'Test Recipient', phone: '0901234567', street: 'Test street', ward_name: 'Test ward', district_name: 'Test district', province_name: 'Test city' }, shipping_carrier: 'GHTK', shipping_service_code: 'STANDARD', quantity: 1, inputs: [], created_at: now, submitted_at: now, pickup_slot_start: now, pickup_slot_end: now, completed_at: null, received_confirmed_at: null }
const payments = ['DEPOSIT','FINAL','SHIPPING'].map((type, i) => ({ id: i + 1, type, amount: i === 2 ? '30000' : '3700', status: 'SUCCESS', gateway: 'VNPAY', mode: 'MOCK', created_at: now }))
const shipments = []
const moves = { CREATED:['PICKED_UP','DELIVERING','DELIVERED','FAILED','RETURNED','CANCELLED'], PICKED_UP:['DELIVERING','DELIVERED','FAILED','RETURNED'], DELIVERING:['DELIVERED','FAILED','RETURNED'], FAILED:['DELIVERING','DELIVERED','RETURNED'], DELIVERED:[], RETURNED:[], CANCELLED:[] }
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
      if (request.method !== 'GET') {
        mutations++
        assert.ok(actorRole === 'STAFF' || path === '/orders/42/receipt', 'Read-only role attempted a mutation')
      }
      if (path === '/me') data = { id: 17, email: 'test@example.test', full_name: 'Browser Test', role: actorRole, status: 'ACTIVE', addresses: [], created_at: now }
      else if (path === '/workshop/orders/42' || path === '/orders/42') data = order
      else if (path === '/workshop/orders') { const statuses = u.searchParams.getAll('status'); const visible = !statuses.length || statuses.includes(order.order_status); data = { items: visible ? [order] : [], total: visible ? 1 : 0, page: 1, page_size: 50 } }
      else if (path.endsWith('/payments')) data = payments
      else if (path.endsWith('/quotations') || path.endsWith('/jobs') || path.startsWith('/catalog/')) data = []
      else if (path === '/manager/staff') data = [{ id:17, full_name:'Staff One', open_orders:1 }, { id:18, full_name:'Staff Two', open_orders:0 }]
      else if (path.startsWith('/manager/')) data = { items: [], total: 0 }
      else if (path === '/workshop/orders/42/shipment' && request.method === 'POST') {
        assert.equal(order.order_status === 'READY_TO_DELIVER' || order.order_status === 'DELIVERING', true)
        assert.ok(!shipments[0] || !['CREATED','PICKED_UP','DELIVERING'].includes(shipments[0].status))
        assert.ok(body.note === null || body.note.length <= 300)
        const row = { id:nextId++, order_id:42, carrier:order.shipping_carrier, service_code:order.shipping_service_code, waybill_code:'MOCK-GHTK-' + nextId, status:'CREATED', fee:'30000', eta:now, picked_up_at:null, delivered_at:null, mode:'MOCK', tracking_url:null, created_at:now, package_type:'FLAT', weight_g:120, is_fallback_fee:true, to_address:order.delivery_address, label_link:'https://storage.test/label.pdf', carrier_status_raw:null, created_by:17 }
        shipments.unshift(row); data = row
      } else if (path.endsWith('/shipment')) {
        if (shipmentError) return void fulfill(requestId, { error:{ code:'CARRIER_UNAVAILABLE', message:'Unavailable' } }, 502)
        data = shipments
      } else if (path.endsWith('/cancel')) {
        const row = shipments.find(s => s.id === Number(path.split('/')[3])); assert.equal(row.status,'CREATED'); assert.ok(body.reason.trim()); row.status='CANCELLED'; data=row
      } else if (path.endsWith('/mock-event')) {
        const row=shipments.find(s=>s.id===Number(path.split('/')[3])); assert.ok(moves[row.status].includes(body.status)); row.status=body.status
        if (['PICKED_UP','DELIVERING'].includes(body.status)) { order.order_status='DELIVERING'; row.picked_up_at=now }
        if (body.status==='DELIVERED') { order.order_status='COMPLETED'; order.completed_at=now; row.delivered_at=now }
        data={ result:'PROCESSED',status:row.status,order_status:order.order_status }
      } else if (path.endsWith('/pickup/confirm')) {
        assert.equal(order.order_status,'READY_TO_DELIVER'); assert.equal(order.delivery_method,'PICKUP')
        if(body.phone !== order.delivery_address.phone) return void fulfill(requestId,{error:{code:'PICKUP_PHONE_MISMATCH',message:'Wrong phone'}},422)
        order.order_status='COMPLETED'; order.completed_at=now; data=order
      } else if(path === '/orders/42/receipt') { assert.ok(['DELIVERING','COMPLETED'].includes(order.order_status)); order.received_confirmed_at=now; data=order }
      else if (path.endsWith('/product-photos')) data={photos:[],order_status:order.order_status}
      else if (path.includes('conversations')) data=path.endsWith('unread-count') ? {unread_count:0} : {items:[],total:0}
      else return void fulfill(requestId, { error:{code:'NOT_FOUND',message:'Fixture not found'} }, 404)
      await fulfill(requestId,data)
    } catch(e) { errors.push(e.message); await fulfill(requestId,{error:{code:'TEST_ERROR',message:e.message}},500) }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns:[{urlPattern:'*'}] })
  await command('Page.addScriptToEvaluateOnNewDocument',{source:`if(!localStorage.getItem('aivhrs-auth')){localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:'staff',apiRole:'STAFF'}));}if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');`})
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}`) }
  const button = (text) => `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`
  const click = async (text) => {
    await wait(`!!(${button(text)}) && !(${button(text)}).disabled && !(${button(text)}).closest('fieldset:disabled')`, text)
    await evaluate(`(()=>{const el=(${button(text)});const parents=[];for(let p=el.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS'&&!p.open)parents.push(p);parents.reverse().forEach(p=>p.querySelector(':scope > summary').click());})()`)
    await evaluate(`(${button(text)}).click()`); await sleep(100)
  }


  const field = (selector,value) => evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});const p=e.tagName==='SELECT'?HTMLSelectElement.prototype:e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(p,'value').set.call(e,${JSON.stringify(value)});e.dispatchEvent(new Event(e.tagName==='SELECT'?'change':'input',{bubbles:true}));})()`)
  const check = (text) => evaluate(`(()=>{const label=[...document.querySelectorAll('label')].find(l=>l.textContent.includes(${JSON.stringify(text)}));label.querySelector('input[type=checkbox]').click();})()`)
  const goto = (path='/staff/fulfillment/42') => command('Page.navigate',{url:`http://127.0.0.1:${port}${path}`})
  const role = async (value) => { actorRole=value; await evaluate(`localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:${JSON.stringify(value==='CUSTOMER'?'customer':'staff')},apiRole:${JSON.stringify(value)}}))`) }
  await command('Emulation.setDeviceMetricsOverride',{width:1365,height:1000,deviceScaleFactor:1,mobile:false})
  await goto()
  await wait(`!!(${button('Create waybill')})`,'shipping panel')
  assert.equal(mutations,0)
  assert.equal(await evaluate(`document.querySelector('.fulfillment').open`),true)
  await field('.fulfillment .sp-form textarea','Keep this packing note')
  await evaluate(`document.querySelector('.fulfillment > summary').click()`)
  assert.equal(await evaluate(`document.querySelector('.fulfillment').open`),false,'Fulfillment collapses')
  await evaluate(`document.querySelector('.fulfillment > summary').click()`)
  assert.equal(await evaluate(`document.querySelector('.fulfillment .sp-form textarea').value`),'Keep this packing note','Collapse keeps unsent form input')

  assert.ok(await evaluate(`(${button('Create waybill')}).disabled`))
  await check('I checked the recipient, address and product')
  await click('Create waybill')
  await wait(`document.querySelector('.sp-shipment')!==null`,'waybill created')
  assert.equal(order.order_status,'READY_TO_DELIVER','Creating a waybill must not mark the order delivering')
  assert.equal(await evaluate(`document.querySelector('.sp-history').open`),false,'History starts collapsed')
  await evaluate(`document.querySelector('.sp-history > summary').click()`)
  assert.equal(await evaluate(`document.querySelector('.sp-history').open`),true)
  await evaluate(`document.querySelector('.sp-history > summary').click()`)
  assert.equal(await evaluate(`document.querySelector('.sp-history').open`),false)
  for(const lang of ['vi','ja']) {
    await evaluate(`localStorage.setItem('aivhrs-lang',${JSON.stringify(lang)})`)
    await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
    await goto(); await wait(`!!document.querySelector('.sp-demo')`,'translated mock form')
    assert.ok(await evaluate(`(()=>{const f=document.querySelector('.sp-demo').getBoundingClientRect();const l=document.querySelector('.sp-demo legend').getBoundingClientRect();return f.width>0&&f.height>0&&l.top>=f.top&&l.left>=f.left&&l.right<=f.right+1})()`),'Legend stays inside the test card')
    assert.ok(await evaluate(`document.querySelector('.sp-demo .wk-warn').scrollWidth<=document.querySelector('.sp-demo .wk-warn').clientWidth+1`),'Warning copy wraps')
    assert.ok(await evaluate('document.documentElement.scrollWidth<=391'),'No mobile overflow')
    await evaluate(`document.querySelector('.sp-demo').scrollIntoView({block:'center',behavior:'instant'})`)
    await sleep(150)
    const shot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false})
    await writeFile(join(scratch,`mock-form-${lang}-mobile.png`),Buffer.from(shot.data,'base64'))
  }
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  await command('Emulation.setDeviceMetricsOverride',{width:1365,height:1000,deviceScaleFactor:1,mobile:false})
  await goto(); await wait(`!!document.querySelector('.sp-shipment')`,'restored shipment')

  await wait(`document.querySelector('.sp-shipment a[target="_blank"]')!==null`,'label')
  assert.equal(await evaluate(`document.querySelector('.sp-shipment a').getAttribute('href')`),'https://storage.test/label.pdf')
  await click('Cancel waybill')
  assert.ok(await evaluate(`(${button('Confirm waybill cancellation')}).disabled`))
  await field('.sp-shipment textarea','Test cancellation')
  await click('Confirm waybill cancellation')
  await wait(`!!(${button('Create replacement waybill')})`,'replacement enabled')
  assert.equal(order.order_status,'READY_TO_DELIVER')
  await check('I checked the recipient, address and product')
  await click('Create replacement waybill')
  await wait(`document.querySelectorAll('.sp-shipment').length===2`,'replacement history')
  await check('I understand this test event')
  await click('Send simulated carrier event')
  await wait(`document.querySelector('.sp-notice') && !document.querySelector('.sp-demo input:checked')`,'pickup processed')
  assert.equal(order.order_status,'DELIVERING')
  assert.equal(await evaluate(`!!(${button('Cancel waybill')})`),false)
  await field('.sp-demo select','FAILED'); await field('.sp-demo textarea','Recipient absent')
  await check('I understand this test event'); await click('Send simulated carrier event')
  await wait(`!!(${button('Create replacement waybill')})`,'failed delivery retry')
  assert.equal(order.order_status,'DELIVERING')
  assert.ok(await evaluate(`document.body.textContent.includes('The latest delivery failed')`))
  await field('.sp-demo select','RETURNED'); await field('.sp-demo textarea','Returned to workshop')
  await check('I understand this test event'); await click('Send simulated carrier event')
  await wait(`document.querySelector('.sp-shipment .chip').textContent==='Returned to workshop'`,'returned shipment')
  assert.equal(order.order_status,'DELIVERING')
  await check('I checked the recipient, address and product'); await click('Create replacement waybill')
  await wait(`document.querySelectorAll('.sp-shipment').length===3`,'third waybill')
  await field('.sp-demo select','DELIVERED'); await check('I understand this test event'); await click('Send simulated carrier event')
  await wait(`document.body.textContent.includes('The order has been handed over or delivered successfully.')`,'delivery completes order')
  assert.equal(order.order_status,'COMPLETED')
  const shippingImage = await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false})
  await writeFile(join(scratch,'shipping-desktop.png'),Buffer.from(shippingImage.data,'base64'))
  order.order_status='DELIVERING'; shipments[0].mode='SANDBOX'; shipments[0].status='PICKED_UP'; shipments[0].waybill_code='REAL-TEST-001'; shipments[0].tracking_url='https://tracking.test/001'
  await goto(); await wait(`document.body.textContent.includes('REAL-TEST-001')`,'real carrier shipment')
  assert.equal(await evaluate(`!!document.querySelector('.sp-demo')`),false,'Real shipments must not show mock controls')
  assert.equal(await evaluate(`!!(${button('Create replacement waybill')})`),false,'Active shipment must block replacement')
  order.order_status='AWAITING_FINAL_PAYMENT'; shipments.length=0
  await goto(); await wait(`document.querySelector('.fulfillment')!==null`,'unpaid shipment')
  assert.equal(await evaluate(`!!(${button('Create waybill')})`),false,'Unpaid order must not ship')
  order.order_status='READY_TO_DELIVER'; shipmentError=true
  await goto(); await wait(`document.querySelector('.fulfillment .lg-error')!==null`,'shipment fetch error')
  assert.equal(await evaluate(`!!(${button('Create waybill')})`),false,'A failed shipment read must not allow creating a duplicate')
  shipmentError=false
  order.order_status='READY_TO_DELIVER'; shipments.length=0
  await role('MANAGER'); const before=mutations; await goto()
  await wait(`document.querySelector('.fulfillment')!==null`,'manager read only')
  await wait(`document.body.textContent.includes('Only the Staff assigned')`,'read only help')
  assert.equal(await evaluate(`!!(${button('Create waybill')})`),false)
  assert.equal(await evaluate(`!!document.querySelector('.sp-demo')`),false)
  assert.equal(mutations,before)
  await role('STAFF'); order.delivery_method='PICKUP'; await goto()
  await wait(`!!(${button('Confirm workshop handover')})`,'pickup panel')
  assert.ok(await evaluate(`(${button('Confirm workshop handover')}).disabled`))
  await field('.sp-form input:not([type])','VH-TEST-SHIPPING')
  await field('.sp-form input[type=tel]','0909999999')
  await check('I checked the order code and handed')
  await click('Confirm workshop handover')
  await wait(`document.body.textContent.includes('The phone does not match')`,'phone mismatch feedback')
  assert.equal(order.order_status,'READY_TO_DELIVER')
  await field('.sp-form input[type=tel]','0901234567')
  await click('Confirm workshop handover')
  await wait(`document.body.textContent.includes('Workshop handover confirmed.')`,'pickup complete')
  assert.equal(order.order_status,'COMPLETED')
  for(const lang of ['vi','ja']) {
    await evaluate(`localStorage.setItem('aivhrs-lang',${JSON.stringify(lang)})`)
    await command('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true})
    await goto(); await wait(`document.querySelector('.fulfillment')!==null`,'translated fulfillment')
    assert.equal(await evaluate(`document.body.textContent.includes('sp.')`),false)
    assert.ok(await evaluate('document.documentElement.scrollWidth <= 391'),'Staff mobile overflow')
    assert.ok(await evaluate('document.querySelector(".main2").getBoundingClientRect().top < 350'),'Mobile rail must not leave a viewport of blank space')
    const screenshot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false})
    await writeFile(join(scratch,`pickup-${lang}-mobile.png`),Buffer.from(screenshot.data,'base64'))
  }
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  await role('CUSTOMER'); await goto('/orders/42/review')
  await wait(`!!(${button('Confirm I received the product')})`,'customer receipt')
  await check('I have physically received'); await click('Confirm I received the product')
  await wait(`document.body.textContent.includes('You confirmed receipt at')`,'receipt recorded')
  assert.equal(order.order_status,'COMPLETED')
  assert.ok(order.received_confirmed_at)
  order.delivery_method='DELIVERY'; shipments.push({id:150,order_id:42,carrier:'GHTK',service_code:'STANDARD',waybill_code:'MOCK-CUSTOMER-150',status:'DELIVERED',fee:'30000',mode:'MOCK',eta:now,created_at:now,picked_up_at:now,delivered_at:now,tracking_url:null})
  await goto('/orders/42/review'); await wait(`document.body.textContent.includes('MOCK-CUSTOMER-150')`,'customer tracking')
  assert.deepEqual(errors,[])
  console.log('PASS: create, label, cancel with reason, replacement, mock pickup, failed/returned delivery and retry, delivery completion, real shipment controls, unpaid/error guards, Manager read-only, pickup phone mismatch and completion, customer tracking/receipt, vi/ja and mobile. All API calls used local fixtures; backend and real orders were not modified.')
  console.log('Screenshots: '+scratch)
} finally { ws?.close(); browser?.kill(); server.closeAllConnections(); server.close() }
