// Real Edge DOM test of the phone number of an account, with every API call intercepted (no backend, no SMS).
// Covers: Account > Profile read only until "Edit profile" (save, cancel), the "Not verified" chip and the verification
// (send, wrong code with the tries left, right code), the reminder after sign-in (ADD_PHONE, VERIFY_PHONE, "Later"), the
// bell notification that opens the profile, and Vietnamese at 390. Run `npm run build` first.
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
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-phone-browser-'))
const sleep = (ms) => new Promise((done) => setTimeout(done, ms))
const now = '2026-11-26T08:00:00Z'

// ---- the fake backend (BE/docs/FE_API_GUIDE.md 3.2 and the sign-in reminders of 2026-11-26) ----
const CODE = '482913'
const log = []
const bodies = []
const account = (over = {}) => ({
  id: 17, email: 'mai@example.com', full_name: 'Mai Tran', phone: '0901234567', phone_verified: false, role: 'CUSTOMER', status: 'ACTIVE',
  addresses: [], created_at: now, last_login_at: now, ...over,
})
const state = { account: account(), reminders: [], notifications: [] }
const mask = (p) => `${p.slice(0, 3)}****${p.slice(-3)}`
function answer(method, path, body) {
  const json = body ? JSON.parse(body) : null
  if (json && method !== 'GET') bodies.push({ path, ...json })
  if (path === '/auth/login') return [{ access_token: 'a', refresh_token: 'r', token_type: 'bearer', account: state.account, reminders: state.reminders }]
  if (path === '/auth/logout') return [null, 204]
  if (path === '/me' && method === 'GET') return [state.account]
  if (path === '/me' && method === 'PATCH') {
    if ('phone' in json && json.phone !== state.account.phone) Object.assign(state.account, { phone: json.phone, phone_verified: false })
    if (json.full_name) state.account.full_name = json.full_name
    return [state.account]
  }
  if (path === '/me/phone/otp') return [{ phone_masked: mask(state.account.phone), expires_in: 300, resend_after: 60, mode: 'MOCK' }, 202]
  if (path === '/me/phone/verify') {
    if (json.code !== CODE) return [{ error: { code: 'OTP_INVALID', message: 'Sai mã', details: { attempts_left: 4 } } }, 400]
    state.account.phone_verified = true
    return [state.account]
  }
  if (path === '/me/notifications/unread-count') return [{ unread_count: state.notifications.filter((n) => !n.is_read).length }]
  if (/^\/me\/notifications\/\d+\/read$/.test(path)) { const n = state.notifications.find((x) => String(x.id) === path.split('/')[3]); n.is_read = true; return [n] }
  if (path === '/me/notifications') return [{ items: state.notifications, unread_count: state.notifications.filter((n) => !n.is_read).length, next_before_id: null }]
  if (path.startsWith('/orders')) return [{ items: [], total: 0, page: 1, page_size: 10 }]
  return [{}]
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
await new Promise((done) => server.listen(0, '127.0.0.1', done))
const port = server.address().port
let browser, ws
const errors = []

try {
  browser = spawn(edge, ['--headless=new', '--no-sandbox', '--disable-extensions', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--disable-background-networking', '--remote-debugging-port=0', `--user-data-dir=${scratch}`, 'about:blank'], { stdio: 'ignore' })
  let debugPort
  for (let n = 0; n < 100; n++) { try { debugPort = Number((await readFile(join(scratch, 'DevToolsActivePort'), 'utf8')).split('\n')[0]); break } catch { await sleep(100) } }
  assert.ok(debugPort, 'Browser did not expose a debugging port')
  const targets = await (await fetch(`http://127.0.0.1:${debugPort}/json/list`)).json()
  ws = new WebSocket(targets.find((v) => v.type === 'page').webSocketDebuggerUrl)
  await new Promise((done, fail) => { ws.onopen = done; ws.onerror = fail })
  let nextId = 0
  const pending = new Map()
  const command = (method, params = {}) => new Promise((done, fail) => {
    const id = ++nextId
    const timer = setTimeout(() => { pending.delete(id); fail(new Error('CDP timeout: ' + method)) }, 15000)
    pending.set(id, { resolve: (value) => { clearTimeout(timer); done(value) }, reject: (error) => { clearTimeout(timer); fail(error) } })
    ws.send(JSON.stringify({ id, method, params }))
  })
  const fulfill = (id, data, code = 200) => command('Fetch.fulfillRequest', {
    requestId: id, responseCode: code,
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }, { name: 'Access-Control-Allow-Methods', value: 'GET, POST, PUT, PATCH, DELETE, OPTIONS' }],
    body: Buffer.from(data === null ? '' : JSON.stringify(data)).toString('base64'),
  })
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
    log.push(`${request.method} ${path}`)
    try {
      const [data, code = 200] = answer(request.method, path, request.postData)
      await fulfill(requestId, data, code)
    } catch (e) { errors.push(e.message); await fulfill(requestId, { error: { code: 'TEST_ERROR', message: e.message } }, 500) }
  }
  await command('Page.enable'); await command('Runtime.enable')
  await command('Fetch.enable', { patterns: [{ urlPattern: '*' }] })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}\n${log.slice(-12).join('\n')}\n${await evaluate('(document.querySelector("dialog[open]") ?? document.body).innerText')}`) }
  const shot = async (name) => { const r = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); const f = join(scratch, name); await writeFile(f, Buffer.from(r.data, 'base64')); console.log('Screenshot: ' + f) }
  const text = (selector) => evaluate(`document.querySelector(${JSON.stringify(selector)})?.innerText ?? ''`)
  const button = (scope, label) => `[...document.querySelectorAll(${JSON.stringify(scope + ' button')})].find(b=>b.textContent.trim()===${JSON.stringify(label)})`
  const click = async (scope, label) => { await wait(`!!(${button(scope, label)}) && !(${button(scope, label)}).disabled`, `button "${label}"`); await evaluate(`(${button(scope, label)}).click()`); await sleep(120) }
  /** Sets a React-controlled input and fires the event React listens to. */
  const setInput = (selector, value) => evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })) })()`)
  const typeKeys = async (digits) => { for (const d of digits) { await command('Input.insertText', { text: d }); await sleep(40) } }
  const noOverflow = async (label) => assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth + 1'), false, `horizontal overflow: ${label}`)
  const go = (path) => command('Page.navigate', { url: `http://127.0.0.1:${port}${path}` })
  /** A session as the app keeps it, or none. The app then reads the account from `GET /me`. */
  const session = async (signedIn, lang = 'en') => {
    await go('/')
    await wait(`document.readyState === 'complete'`, 'origin')
    await evaluate(`localStorage.clear(); localStorage.setItem('aivhrs-lang', '${lang}'); ${signedIn ? `localStorage.setItem('aivhrs-auth', JSON.stringify({ access: 'test-only', refresh: 'test-only' })); localStorage.setItem('aivhrs-user', JSON.stringify({ id: 17, name: 'Mai Tran', email: 'mai@example.com', role: 'customer', apiRole: 'CUSTOMER' }))` : ''}`)
  }
  const profile = async (label) => { await go('/account/profile'); await wait(`!!document.querySelector('.ac-form #ac-phone') && !!document.querySelector('.ac-phone-state')`, `profile: ${label}`) }
  const readOnly = () => evaluate(`[...document.querySelectorAll('.ac-form input:not([type=email]), .ac-form textarea')].map(i => i.disabled)`)

  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })

  // 1. The profile is read only until "Edit profile".
  await session(true)
  await profile('unverified')
  assert.deepEqual(await readOnly(), [true, true, true, true], 'name, phone, address and bio are locked')
  assert.equal(await evaluate(`!!(${button('.ac-actions', 'Update profile')})`), false, 'no save button before editing')
  await evaluate(`(() => { const el = document.querySelector('.ac-form input'); el.focus() })()`)
  await typeKeys('X')
  assert.equal(await evaluate(`document.querySelector('.ac-form input').value`), 'Mai Tran', 'typing changes nothing while locked')
  assert.match(await text('.ac-phone-state'), /Not verified/)
  assert.match(await text('#ac-phone-help'), /reset your password by SMS/, 'the reason to verify is said')
  await shot('profile-locked-1440.png')

  await click('.ac-photo', 'Edit profile')
  assert.deepEqual(await readOnly(), [false, false, false, false], 'the fields open for editing')
  assert.equal(await evaluate(`(${button('.ac-phone-state', 'Verify')}).disabled`), true, 'no verification while editing')
  assert.equal(await evaluate(`(${button('.ac-actions', 'Update profile')}).disabled`), true, 'nothing to save yet')
  await setInput('.ac-form input', 'Mai T.')
  await click('.ac-actions', 'Cancel')
  assert.equal(await evaluate(`document.querySelector('.ac-form input').value`), 'Mai Tran', 'Cancel puts the saved name back')
  assert.deepEqual(await readOnly(), [true, true, true, true], 'Cancel locks the profile again')
  assert.equal(log.includes('PATCH /me'), false, 'Cancel saves nothing')

  await click('.ac-photo', 'Edit profile')
  await setInput('.ac-form input', 'Mai Tran Thi')
  await click('.ac-actions', 'Update profile')
  await wait(`/Profile updated/.test(document.querySelector('.ac-actions').innerText)`, 'the profile is saved')
  assert.deepEqual(bodies.at(-1), { path: '/me', full_name: 'Mai Tran Thi', phone: '0901234567' })
  assert.deepEqual(await readOnly(), [true, true, true, true], 'saving locks the profile again')

  // 2. Verify the number: the click sends the SMS, a wrong code says how many tries are left, the right one verifies.
  assert.equal(log.includes('POST /me/phone/otp'), false, 'no code is sent before "Verify"')
  await click('.ac-phone-state', 'Verify')
  await wait(`document.querySelectorAll('.phv .entry-otp input').length === 6`, 'the six boxes')
  assert.ok(log.includes('POST /me/phone/otp'))
  assert.match(await text('.phv'), /090\*\*\*\*567/, 'the masked number')
  assert.match(await text('.phv'), /test mode: no real SMS/, 'MOCK mode is said')
  assert.match(await text('.phv'), /Send a new code in \d+s/, 'the resend wait')
  await shot('profile-verify-1440.png')
  await typeKeys('111111')
  await wait(`!!document.querySelector('.phv .phv-error')`, 'the wrong code is refused')
  assert.match(await text('.phv-error'), /Tries left: 4/)
  assert.equal(await evaluate(`[...document.querySelectorAll('.phv .entry-otp input')].map(i => i.value).join('')`), '', 'the boxes are cleared')
  await evaluate(`document.querySelector('.phv .entry-otp input').focus()`)
  await typeKeys(CODE)
  await wait(`/Verified/.test(document.querySelector('.ac-phone-state').innerText) && !document.querySelector('.phv')`, 'the number is verified')
  assert.deepEqual(bodies.at(-1), { path: '/me/phone/verify', code: CODE })
  assert.equal(await evaluate(`!!(${button('.ac-phone-state', 'Verify')})`), false, 'no Verify button once verified')

  // A changed number is unverified again and asks to be verified.
  await click('.ac-photo', 'Edit profile')
  await setInput('#ac-phone', '0912 345 678')
  await click('.ac-actions', 'Update profile')
  await wait(`/Not verified/.test(document.querySelector('.ac-phone-state').innerText)`, 'the new number is not verified')
  assert.deepEqual(bodies.at(-1), { path: '/me', full_name: 'Mai Tran Thi', phone: '0912345678' })

  // 3. The bell: a phone reminder opens the profile.
  state.notifications = [{ id: 5, order_id: null, type: 'SYSTEM', msg_code: 'PHONE_VER', title: 'Xác minh số điện thoại', body: 'Số điện thoại 091****678 chưa được xác minh.', is_read: false, read_at: null, created_at: now }]
  await go('/')
  await wait(`!!document.querySelector('.nbell-btn')`, 'the bell')
  await evaluate(`document.querySelector('.nbell-btn').click()`)
  await wait(`!!document.querySelector('.nbell-pop li button')`, 'the reminder in the bell')
  await evaluate(`document.querySelector('.nbell-pop li button').click()`)
  await wait(`location.pathname === '/account/profile' && !!document.querySelector('.ac-phone-state')`, 'the reminder opens the profile')
  state.notifications = []

  // 4. Sign in with VERIFY_PHONE: the prompt opens on the verification, sends nothing by itself, and "Later" closes it.
  const signIn = async () => {
    await go('/login')
    await wait(`!!document.querySelector('.entry-login #entry-email')`, 'sign-in dialog')
    await setInput('#entry-email', 'mai@example.com')
    await setInput('#entry-password', 'Password123')
    await evaluate(`document.querySelector('.entry-login form .entry-login-submit').click()`)
    await wait(`!!document.querySelector('#phone-reminder-title')`, 'the reminder after sign-in')
  }
  state.account = account({ phone: '0912345678' })
  state.reminders = ['VERIFY_PHONE']
  await session(false)
  log.length = 0
  await signIn()
  assert.equal(await text('#phone-reminder-title'), 'Verify your phone number')
  assert.match(await text('dialog[open]'), /091\*\*\*\*678 is not verified yet/)
  assert.equal(log.includes('POST /me/phone/otp'), false, 'no SMS before "Send the code"')
  await shot('reminder-verify-1440.png')
  await click('dialog[open]', 'Later')
  await wait(`!document.querySelector('#phone-reminder-title')`, '"Later" closes the prompt')
  assert.equal(await evaluate(`document.body.style.overflow`), '', 'the page scrolls again')

  // 5. Sign in with ADD_PHONE: the number is saved, the code is sent at once, the code verifies it.
  state.account = account({ phone: null })
  state.reminders = ['ADD_PHONE']
  await session(false)
  log.length = 0
  await signIn()
  assert.equal(await text('#phone-reminder-title'), 'Add your phone number')
  await setInput('#phone-reminder-number', '123')
  await click('dialog[open]', 'Continue')
  await wait(`!!document.querySelector('dialog[open] .entry-login-error')`, 'a bad number is refused')
  assert.equal(log.includes('PATCH /me'), false)
  await setInput('#phone-reminder-number', '+84 987 654 321')
  await click('dialog[open]', 'Continue')
  await wait(`document.querySelectorAll('dialog[open] .entry-otp input').length === 6`, 'the six boxes after the number')
  assert.deepEqual(bodies.filter((b) => b.path === '/me').at(-1), { path: '/me', phone: '+84987654321' })
  assert.ok(log.includes('POST /me/phone/otp'), 'the code is sent right after the number')
  await typeKeys(CODE)
  await wait(`/Your phone number is verified/.test(document.querySelector('dialog[open]').innerText)`, 'verified from the prompt')
  await click('dialog[open]', 'Close')
  await wait(`!document.querySelector('#phone-reminder-title')`, 'the prompt closes')

  // No reminder: nothing opens.
  state.reminders = []
  await session(false)
  await go('/login')
  await wait(`!!document.querySelector('.entry-login #entry-email')`, 'sign-in dialog')
  await setInput('#entry-email', 'mai@example.com')
  await setInput('#entry-password', 'Password123')
  await evaluate(`document.querySelector('.entry-login form .entry-login-submit').click()`)
  await wait(`!document.querySelector('dialog[open]')`, 'signed in')
  await sleep(300)
  assert.equal(await evaluate(`!!document.querySelector('#phone-reminder-title')`), false, 'no prompt without a reminder')

  // 6. Vietnamese, narrow: the profile and the verification fit.
  state.account = account()
  await session(true, 'vi')
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await profile('vi 390')
  assert.match(await text('.ac-phone-state'), /Chưa xác minh/)
  await click('.ac-phone-state', 'Xác minh')
  await wait(`document.querySelectorAll('.phv .entry-otp input').length === 6`, 'the six boxes, vi 390')
  await noOverflow('profile vi 390')
  await evaluate(`document.querySelector('.phv').scrollIntoView({ block: 'center' })`)
  await sleep(200)
  await shot('profile-verify-vi-390.png')

  assert.deepEqual(errors, [])
  console.log('PASS: profile locked until "Edit profile" (cancel, save), chip and reason, verification (send on click, masked number, MOCK note, resend wait, wrong code with tries left, right code), changed number unverified again, bell reminder opens the profile, sign-in reminders (VERIFY_PHONE waits for the button and "Later"; ADD_PHONE saves, sends and verifies; none without a reminder), vi at 390. All API calls intercepted.')
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close()
}
