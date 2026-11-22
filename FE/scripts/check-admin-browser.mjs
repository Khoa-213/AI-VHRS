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
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-admin-browser-'))
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const now = '2026-10-25T00:00:00Z'
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
    let data = {}
    try {
      const account={id:17,email:'admin@example.test',full_name:'Preview',role:'ADMIN',status:'ACTIVE',addresses:[],created_at:now}
      const page={items:[],total:0,page:1,page_size:100}
      if(path==='/me') data=account
      else if(path==='/admin/dashboard') data={generated_at:now,database_ms:48,accounts:{by_role:{ADMIN:{ACTIVE:1,LOCKED:2}},new_last_7_days:1,active_sessions:1},robots:{total:1,online:1,by_status:{IDLE:1}},integrations:[],background_jobs:{enabled:true,interval_seconds:60,last_run:null},notifications:{emails_failed_last_24h:3}}
      else if(path==='/admin/accounts') data={...page,items:[account,{...account,id:18,role:'STAFF'}],total:2}
      else if(path==='/admin/audit-logs') data=page
      else if(path==='/admin/settings'||path==='/admin/integrations') data=[]
      else if(path.endsWith('/notifications')) data={items:[],unread_count:0,next_before_id:null}
      else if(path.endsWith('/stream')) return void fulfill(requestId,Buffer.from('event: ready\ndata: {"unread_count":0}\n\n'),200,'text/event-stream')
      else if(path.includes('conversations')) data=path.endsWith('unread-count')?{unread_count:0}:page
      await fulfill(requestId, data)
    } catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-auth',JSON.stringify({access:'test-only',refresh:'test-only'}));localStorage.setItem('aivhrs-user',JSON.stringify({id:17,name:'Browser Test',role:'admin',apiRole:'ADMIN'}));if(!localStorage.getItem('aivhrs-lang'))localStorage.setItem('aivhrs-lang','en');` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 120; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}`) }
  const button = (text) => `[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`
  const click = async (text) => { await wait(`!!(${button(text)}) && !(${button(text)}).disabled && !(${button(text)}).closest('fieldset:disabled')`, text); await evaluate(`(${button(text)}).click()`); await sleep(100) }

  const go=async(route)=>{await command('Page.navigate',{url:`http://127.0.0.1:${port}${route}`});await wait(`!!document.querySelector('.adm-card')`,'page')}
  await go('/admin')
  for(const theme of ['light','dark']) for(const lang of ['vi','ja']) for(const width of [1440,390]) {
    await evaluate(`localStorage.setItem('aivhrs-theme','${theme}');localStorage.setItem('aivhrs-lang','${lang}')`)
    await command('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<500})
    await go('/admin')
    assert.equal(await evaluate(`document.documentElement.dataset.theme`),theme)
    const beforeThemeColor=await evaluate(`getComputedStyle(document.querySelector('.adm-app')).backgroundColor`)
    await evaluate(`document.querySelector('.adm-theme button:${theme==='dark'?'first':'last'}-child').click()`)
    assert.equal(await evaluate(`document.documentElement.dataset.theme`),theme==='dark'?'light':'dark')
    assert.notEqual(await evaluate(`getComputedStyle(document.querySelector('.adm-app')).backgroundColor`),beforeThemeColor,'Palette switches')
    await evaluate(`document.querySelector('.adm-theme button:${theme==='light'?'first':'last'}-child').click()`)
    assert.equal(await evaluate(`localStorage.getItem('aivhrs-theme')`),theme,'Theme preference saved')
    await command('Page.reload'); await wait(`!!document.querySelector('.adm-card')`,'theme reload')
    assert.equal(await evaluate(`document.documentElement.dataset.theme`),theme,'Theme survives reload')
    assert.equal(await evaluate(`document.querySelector('.adm-theme button:${theme==='light'?'first':'last'}-child').getAttribute('aria-pressed')`),'true')
    await wait(`!!document.querySelector('.adm-kpi--link')`,'widget')
    await evaluate(`document.querySelector('.adm-kpi--link').click()`)
    await wait(`!!document.querySelector('.adm-back')`,'back button')
    assert.equal(await evaluate(`document.querySelector('.adm-back').getAttribute('href')`),'/admin')
    await wait(`!!document.querySelector('.adm-select-trigger')`,'select')
    await evaluate(`document.querySelector('.adm-select-trigger').focus();document.querySelector('.adm-select-trigger').click()`)
    await wait(`!!document.querySelector('[role=listbox]')`,'popup')
    assert.ok(await evaluate(`(()=>{const r=document.querySelector('[role=listbox]').getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight})()`),'Popup stays in viewport')
    await evaluate(`document.querySelector('[role=option]:nth-child(2)').click()`)
    await wait(`!document.querySelector('[role=listbox]')`,'selected and closed')
    assert.equal(await evaluate(`document.activeElement.getAttribute('role')`),'combobox')
    await evaluate(`document.querySelector('.adm-select-trigger').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}))`)
    await wait(`!!document.querySelector('[role=listbox]')`,'keyboard open')
    await evaluate(`document.querySelector('.adm-select-trigger').dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}));`)
    await evaluate(`document.querySelector('.adm-select-trigger').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));`)
    await wait(`!document.querySelector('[role=listbox]')`,'keyboard select')
    await evaluate(`document.querySelector('.adm-select-trigger').click()`)
    await wait(`!!document.querySelector('[role=listbox]')`,'reopen')
    await evaluate(`document.querySelector('.adm-select-trigger').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))`)
    await wait(`!document.querySelector('[role=listbox]')`,'escape')
    await evaluate(`document.querySelector('.adm-select-trigger').click()`); await wait(`!!document.querySelector('[role=listbox]')`,'outside test');
    await evaluate(`document.querySelector('.adm-h1').dispatchEvent(new PointerEvent('pointerdown',{bubbles:true}))`); await wait(`!document.querySelector('[role=listbox]')`,'outside closes');
    await evaluate(`document.querySelector('.adm-back').click()`)
    await wait(`location.pathname==='/admin' && !document.querySelector('.adm-back')`,'returned')
    for(const route of ['/admin/audit','/admin/settings']) {
      await go(route);assert.ok(await evaluate(`!!document.querySelector('.adm-back')`))
      if(route==='/admin/audit') {
        await evaluate(`document.querySelector('.adm-select-trigger').focus();document.querySelector('.adm-select-trigger').click()`)
        await wait(`!!document.querySelector('[role=listbox]')`,'audit dropdown')
        assert.equal(await evaluate(`getComputedStyle(document.querySelector('[role=listbox]')).scrollbarWidth`),'none','Scrollbar hidden')
        assert.ok(await evaluate(`(()=>{const e=document.querySelector('[role=listbox]');return e.scrollHeight>e.clientHeight})()`),'List can scroll')
        await evaluate(`document.querySelector('[role=listbox]').scrollTop=100`)
        assert.ok(await evaluate(`document.querySelector('[role=listbox]').scrollTop>0`),'Scrolling still works')
        await evaluate(`document.querySelector('.adm-select-trigger').dispatchEvent(new KeyboardEvent('keydown',{key:'End',bubbles:true}))`)
        await evaluate(`document.querySelector('.adm-select-trigger').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}))`)
        await wait(`!document.querySelector('[role=listbox]')`,'last audit kind selected')

      }
    }
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'No overflow')
  }
  await go('/admin/accounts')
  await wait(`!!document.querySelector('.adm-person-act button')`,'accounts loaded')
  await evaluate(`[...document.querySelectorAll('.adm-person-act button')].at(-1).click()`)
  await wait(`!!document.querySelector('.adm-edit .adm-select-trigger')`,'edit select')
  assert.equal(await evaluate(`document.querySelector('.adm-edit .adm-select-trigger').disabled`),true,'Self role stays disabled')
  assert.deepEqual(errors,[])
  console.log('PASS: widget navigation and back links; dropdown pointer/keyboard selection, Escape, focus, viewport positioning, disabled self role; light/dark, vi/ja, desktop/mobile. API fixture isolation.')

} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close()
}
