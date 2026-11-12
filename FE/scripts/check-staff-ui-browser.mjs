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
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-staff-ui-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = new Date().toISOString()
let mutations = 0
const order = { id: 42, code: 'VH-TEST-SHIPPING', customer_name: 'Test Customer', assigned_staff_id: 17, order_type: 'OT3_TEMPLATE', order_status: 'READY_TO_DELIVER', production_status: 'FINISHED', total_amount: '7400', deposit_amount: '3700', deposit_pct: '50', delivery_method: 'DELIVERY', delivery_address: { receiver: 'Test Recipient', phone: '0901234567', street: 'Test street', ward_name: 'Test ward', district_name: 'Test district', province_name: 'Test city' }, shipping_carrier: 'GHTK', shipping_service_code: 'STANDARD', quantity: 1, char_count: null, inputs: [{id:1,kind:'CANVAS',sort_order:0,canvas_data:{width_mm:210,height_mm:297,strokes:[{points:[{x:40,y:140},{x:160,y:155}]}]}}], created_at: now, submitted_at: now, pickup_slot_start: now, pickup_slot_end: now, completed_at: null, received_confirmed_at: null }
const payments = ['DEPOSIT','FINAL','SHIPPING'].map((type, i) => ({ id: i + 1, type, amount: i === 2 ? '30000' : '3700', status: 'SUCCESS', gateway: 'VNPAY', mode: 'MOCK', created_at: now }))
const shipments = []
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
  const command = (method, params = {}) => new Promise((resolve, reject) => { const id = ++nextId; const timer = setTimeout(() => { pending.delete(id); reject(new Error('CDP timeout: ' + method)) }, 15000); pending.set(id, { method, resolve: (value) => { clearTimeout(timer); resolve(value) }, reject: (error) => { clearTimeout(timer); reject(error) } }); ws.send(JSON.stringify({ id, method, params })) })
  const fulfill = (id, data, code = 200, mime = 'application/json') => command('Fetch.fulfillRequest', { requestId: id, responseCode: code, responseHeaders: [{ name: 'Content-Type', value: mime }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET,POST,PATCH,PUT,DELETE,OPTIONS' }], body: (Buffer.isBuffer(data) ? data : Buffer.from(JSON.stringify(data))).toString('base64') })


  ws.onmessage = async (message) => {
    const msg = JSON.parse(message.data)
    if (msg.id) { const p = pending.get(msg.id); pending.delete(msg.id); if (p) {
      // Navigation can cancel an intercepted request before its fixture response arrives.
      if (p.method.startsWith('Fetch.') && msg.error?.message === 'Invalid InterceptionId.') p.resolve({})
      else if (msg.error) p.reject(new Error(JSON.stringify(msg.error)))
      else p.resolve(msg.result)
    } return }
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.text)
    if (msg.method !== 'Fetch.requestPaused') return
    const { requestId, request } = msg.params
    const u = new URL(request.url)
    if (u.hostname === '127.0.0.1') return void command('Fetch.continueRequest', { requestId })
    if (request.url.includes('logo-') && request.url.endsWith('.png')) return void fulfill(requestId, await readFile(join(root,'dist/assets',u.pathname.split('/').pop())),200,'image/png')
    if (request.method === 'OPTIONS') return void fulfill(requestId, {})
    const path = u.pathname.replace('/api/v1', '')
    let data = {}
    try {
      if (request.method !== 'GET') {
        mutations++
        throw new Error('UI navigation attempted a data mutation: '+path)
      }
      if (path === '/workshop/refunds') data={refunds:[],orphans:[]}
      else if(path.endsWith('/eta')) data={order_id:42,eta:null,postponed_days:0,threshold_days:7,can_cancel_full_refund:false,history:[]}
      else if(path.endsWith('/notifications')) data={items:[],unread_count:0,next_before_id:null}
      else if(path.endsWith('/stream')) return void fulfill(requestId,Buffer.from('event: ready\ndata: {"unread_count":0}\n\n'),200,'text/event-stream')
      else if (path === '/me') data = { id: 17, email: 'test@example.test', full_name: 'Browser Test', role: 'STAFF', status: 'ACTIVE', addresses: [], created_at: now }
      else if (path === '/workshop/orders/42' || path === '/orders/42') data = order
      else if (path === '/workshop/orders') { const statuses = u.searchParams.getAll('status'); const candidates = [order,{...order,id:43,code:'VH-SKETCH',order_status:'ACCEPTED',submitted_at:new Date(Date.now()-15*86400000).toISOString()},{...order,id:44,code:'VH-POOL',assigned_staff_id:null,order_status:'SUBMITTED'}]; const visible = candidates.filter(o=>!statuses.length||statuses.includes(o.order_status)); data = {items:visible,total:visible.length,page:1,page_size:50} }
      else if (path.endsWith('/payments')) data = payments
      else if (path.endsWith('/quotations') || path.endsWith('/jobs') || path.startsWith('/catalog/')) data = []
      else if (path.endsWith('/shipment')) data = shipments
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


  const goto = async(path) => {await command('Page.navigate',{url:`http://127.0.0.1:${port}${path}`});await wait(`!!document.querySelector('.ws')`,'shell');await sleep(300)}
  await goto('/staff')
  for(const theme of ['light','dark']) for(const lang of ['en','vi','ja']) {
    await evaluate(`localStorage.setItem('aivhrs-lang','${lang}');localStorage.setItem('aivhrs-theme','${theme}')`)
    for(const width of [1440,1024,768,390]) {
      await command('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<500})
      for(const route of ['/staff','/staff/review','/staff/review/42','/staff/fulfillment/42','/staff/refunds']) {
        order.order_status=route.includes('/review')||route==='/staff'?'SUBMITTED':'READY_TO_DELIVER'
        await goto(route)
        await wait(`!!document.querySelector('.ws-staff')`,'staff styling')
        assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),`Overflow: ${route} ${width} ${lang}`)
        assert.equal(await evaluate(`document.querySelectorAll('.staff-nav-label').length`),4)
        assert.equal(await evaluate(`document.querySelectorAll('.staff-nav a').length`),4)
        assert.equal(await evaluate(`document.documentElement.dataset.theme`),theme,'Saved theme applied')
        assert.equal(await evaluate(`document.querySelectorAll('.staff-sidebar .staff-nav a').length`),4)
        assert.equal(await evaluate(`document.querySelectorAll('.staff-sidebar .appearance-switch, .staff-sidebar .nbell, .staff-sidebar .staff-user').length`),0)
        assert.equal(await evaluate(`document.querySelector('.staff-user-button').getAttribute('href')`),'/account/profile')
        assert.equal(await evaluate(`document.querySelectorAll('.staff-sidebar-signout').length`),1,'Sign out stays in sidebar')
        assert.equal(await evaluate(`document.querySelectorAll('.staff-header .staff-account-panel').length`),0)
        if(route==='/staff' && [1440,390].includes(width)) {
          await evaluate(`document.querySelector('.staff-user-button').click()`)
          await wait(`location.pathname==='/account/profile' && !!document.querySelector('.ac-form')`,'Staff account profile opens')
          assert.equal(await evaluate(`document.querySelector('.ac-form input[autocomplete="name"]').value`),'Browser Test')
          assert.equal(await evaluate(`document.querySelectorAll('.ac-nav a[href="/account/orders"]').length`),0,'Staff has no customer orders navigation')
          await evaluate(`document.querySelector('.ac-workspace-back').click()`)
          await wait(`location.pathname==='/staff' && !!document.querySelector('.ws-staff')`,'Return to Staff')
        }
        await evaluate(`document.querySelector('.staff-header .nbell-btn').click()`)
        await wait(`!!document.querySelector('.staff-header .nbell-pop')`,'Notifications open')
        assert.ok(await evaluate(`(()=>{const r=document.querySelector('.nbell-pop').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth})()`),'Notification popup fits viewport: '+JSON.stringify(await evaluate(`({width:innerWidth,rect:document.querySelector('.nbell-pop').getBoundingClientRect().toJSON()})`)))
        await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`)
        if(width<=980) {
          await evaluate(`document.querySelector('.staff-sidebar-menu').click()`)
          assert.ok(await evaluate(`document.querySelector('.ws-staff').classList.contains('staff-sidebar-open')`))
          await wait(`document.querySelector('.staff-nav').getBoundingClientRect().left>=0`,'sidebar entrance')
        }
        assert.ok(await evaluate(`(()=>{const e=document.querySelector('.staff-nav').getBoundingClientRect();return e.left>=0&&e.right<=innerWidth})()`),'Sidebar navigation fits viewport')
        if(width<=980) {
          await evaluate(`document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`)
          await wait(`!document.querySelector('.ws-staff').classList.contains('staff-sidebar-open')`,'Escape closes sidebar')
          assert.equal(await evaluate(`document.activeElement===document.querySelector('.staff-sidebar-menu')`),true,'Focus returns to menu')
        }
        if(route==='/staff') {
          await evaluate(`document.querySelector('.ws-staff>.app2').scrollTo({top:500,behavior:'instant'})`)
          await sleep(100)
          assert.ok(await evaluate(`(()=>{const h=document.querySelector('.staff-header').getBoundingClientRect(),a=document.querySelector('.ws-staff>.app2').getBoundingClientRect();return a.top>=h.bottom&&h.top===0&&document.documentElement.scrollHeight<=innerHeight+1})()`),'Content scrolls below header inside viewport frame')
          assert.ok(await evaluate(`(()=>{const r=document.querySelector('.staff-header').getBoundingClientRect();return r.top>=0&&r.top<=21})()`),'Navigation remains available while scrolling: '+JSON.stringify(await evaluate(`({width:innerWidth,scroll:scrollY,top:document.querySelector('.staff-header').getBoundingClientRect().top,root:document.querySelector('.ws-staff').getBoundingClientRect().height,position:getComputedStyle(document.querySelector('.staff-sidebar')).position})`)))
          await evaluate(`document.querySelector('.ws-staff>.app2').scrollTo({top:0,behavior:'instant'})`)
          const before=await evaluate(`Number(document.querySelector('.staff-chart-total b').textContent)`)
          await evaluate(`document.querySelector('.staff-period button:last-child').click()`)
          await wait(`document.querySelector('.staff-period button:last-child').getAttribute('aria-pressed')==='true'`,'30 day chart')
          assert.equal(await evaluate(`Number(document.querySelector('.staff-chart-total b').textContent)`),before+1,'Chart uses actual dated records')
          assert.equal(await evaluate(`document.querySelectorAll('.staff-kpis .k').length`),4)
          await evaluate(`document.querySelector('.staff-chart-data summary').click()`)
          assert.equal(await evaluate(`document.querySelector('.staff-chart-data').open`),true)
          assert.equal(await evaluate(`document.querySelectorAll('.staff-chart-data tbody tr').length`),30)
          assert.equal(await evaluate(`[...document.querySelectorAll('.staff-chart-data td')].reduce((n,td)=>n+Number(td.textContent),0)`),before+1)
          await evaluate(`document.querySelector('.staff-chart-data summary').click()`)
        }
        if(route==='/staff/review') {
          assert.ok(await evaluate(`!!document.querySelector('.staff-board')`),'Pipeline overview')
          assert.equal(await evaluate(`document.querySelectorAll('.staff-board .ol-sec').length`),4,'Existing groups only')
          assert.equal(await evaluate(`getComputedStyle(document.querySelector('.staff-board .ol-scroll')).gridTemplateColumns.split(' ').length`),width>1100?4:width>480?2:1,'Responsive pipeline')
          await evaluate(`document.querySelector('.ol-row').click()`)
          await wait(`!!document.querySelector('.wk-content') && location.pathname.includes('/review/')`,'Board card opens existing order detail')
          await goto('/staff/review')
        }
        if(route!=='/staff') assert.equal(await evaluate(`document.querySelector('.staff-back').getAttribute('href')`),'/staff')
        if(route==='/staff/review/42') {
          assert.equal(await evaluate(`getComputedStyle(document.querySelector('.wk-order-head')).backgroundColor`),await evaluate(`getComputedStyle(document.querySelector('.ol')).backgroundColor`),'Order surfaces follow the selected theme')
          assert.equal(await evaluate(`getComputedStyle(document.querySelector('.wk-block')).backgroundColor`),await evaluate(`getComputedStyle(document.querySelector('.ol')).backgroundColor`),'Detail cards follow the selected theme')
          assert.ok(await evaluate(`document.querySelector('.wk-content .opv-svg').getBoundingClientRect().height<=281`),'Preview must stay compact')
          if(width===1440) {
            assert.ok(await evaluate(`Math.abs(document.querySelector('.wk-content').getBoundingClientRect().top-document.querySelector('.wk-specs').getBoundingClientRect().top)<2`),'Preview and specs share a row')
            assert.ok(await evaluate(`document.querySelector('.hd').getBoundingClientRect().height<125`),'Compact header')
          }

          assert.equal(await evaluate(`document.querySelectorAll('.ol-stages button').length`),0,'Stage chips replaced by one select')
          assert.ok(await evaluate(`document.querySelector('.ol-top').getBoundingClientRect().height<185`),'Compact filters')
          await evaluate(`document.querySelector('.ol-filter [role=combobox]').focus();document.querySelector('.ol-filter [role=combobox]').click()`)
          await wait(`document.querySelectorAll('[role=option]').length===6`,'six existing stage filters')
          assert.equal(await evaluate(`getComputedStyle(document.querySelector('[role=listbox]')).scrollbarWidth`),'none')
          await evaluate(`document.querySelector('[role=option]:last-child').click()`)
          await wait(`document.querySelectorAll('.ol-scroll .ol-row').length===0`,'closed stage applied')
          await evaluate(`document.querySelector('.ol-filter [role=combobox]').click()`)
          await wait(`!!document.querySelector('[role=listbox]')`,'reopen filters')
          await evaluate(`document.querySelector('[role=option]:first-child').click()`)
          await wait(`document.querySelectorAll('.ol-scroll .ol-row').length===2`,'open stage restored')
          await evaluate(`(()=>{const el=document.querySelector('.ol-search input');Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,'VH-POOL');el.dispatchEvent(new Event('input',{bubbles:true}))})()`)
          await wait(`document.querySelectorAll('.ol-scroll .ol-row').length===1 && document.querySelector('.ol-scroll').textContent.includes('VH-POOL')`,'search still covers unclaimed orders')
          await evaluate(`document.querySelector('.ol-clear').click()`)
          await wait(`document.querySelectorAll('.ol-scroll .ol-row').length===2`,'clear restores scope')
          await wait(`document.querySelectorAll('.wk-actions button').length===3`,'intake actions')
          await evaluate(`document.querySelectorAll('.wk-actions button')[1].click()`)
          await wait(`!!document.querySelector('#wk-note')`,'request info editor')
          assert.equal(await evaluate(`document.querySelector('#wk-note').parentElement.querySelector('.vh-btn--primary').disabled`),true,'Empty info request remains blocked')
        }
        if(lang==='vi'&&[1440,390].includes(width)&&['/staff','/staff/review','/staff/review/42','/staff/fulfillment/42'].includes(route)) {
          const shot=await command('Page.captureScreenshot',{format:'png',captureBeyondViewport:false})
          await writeFile(join(scratch,`${route.replaceAll('/','-')}-${width}-${theme}.png`),Buffer.from(shot.data,'base64'))
        }
      }
    }
  }
  assert.equal(mutations,0,'Visual navigation must not mutate orders')
  assert.deepEqual(errors,[])
  console.log('PASS: Staff dashboard, review/request-info, fulfillment, refunds; 3 languages at 4 widths, sidebar and mobile drawer/light-dark/pipeline/chart filters/back, no overflow or data mutations. Screenshots: '+scratch)

} finally { ws?.close(); browser?.kill(); server.closeAllConnections(); server.close() }
