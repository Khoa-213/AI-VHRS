// Real Edge DOM test of "Forgot password" inside the sign-in dialog, with every API call intercepted (no backend, no mail).
// Covers: email or phone, then the six code boxes (typing, paste, wrong code, resend wait), the new password, and the way back to
// sign in with the email filled in; the three languages at 1440 and 390; and the page the email links to (/reset-password).
// Run `npm run build` first.
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
const scratch = await mkdtemp(join(tmpdir(), 'vhrs-forgot-browser-'))
const sleep = (ms) => new Promise((done) => setTimeout(done, ms))

// ---- the fake backend: BE/docs/FE_API_GUIDE.md (2026-11-26), the code is checked together with the new password ----
const EMAIL = 'mai@example.com'
const CODE = '482913'
const log = []
const bodies = []
function answer(method, path, body) {
  const json = body ? JSON.parse(body) : null
  if (json) bodies.push({ path, ...json })
  if (path === '/auth/password-reset/request' || path === '/auth/phone-reset/request') return [{ message: 'ok' }, 202]
  if (path === '/auth/password-reset/confirm') {
    assert.equal('token' in json, false, 'no reset token is ever sent')
    assert.equal('email' in json && 'phone' in json, false, 'the email or the phone, never both')
    if (json.code !== CODE) return [{ error: { code: 'OTP_INVALID', message: 'Sai mã', details: { attempts_left: 4 } } }, 400]
    return [null, 204]
  }
  if (path === '/auth/refresh' || path === '/me') return [{ error: { code: 'UNAUTHENTICATED', message: 'no session' } }, 401]
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
    responseHeaders: [{ name: 'Content-Type', value: 'application/json' }, { name: 'Access-Control-Allow-Origin', value: '*' }, { name: 'Access-Control-Allow-Headers', value: '*' }],
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
  await command('Page.addScriptToEvaluateOnNewDocument', { source: `localStorage.setItem('aivhrs-lang', localStorage.getItem('aivhrs-lang') || 'en')` })
  const evaluate = async (expression) => { const r = await command('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }); if (r.exceptionDetails) throw new Error(r.exceptionDetails.text); return r.result.value }
  const wait = async (expression, label) => { for (let i = 0; i < 100; i++) { if (await evaluate(expression)) return; await sleep(100) } throw new Error(`Timed out: ${label}\n${errors.join('\n')}\n${log.slice(-12).join('\n')}\n${await evaluate('document.querySelector(".entry-login")?.innerText ?? document.body.innerText')}`) }
  const shot = async (name) => { const r = await command('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }); const f = join(scratch, name); await writeFile(f, Buffer.from(r.data, 'base64')); console.log('Screenshot: ' + f) }
  const panel = () => evaluate(`document.querySelector('.entry-login-panel')?.innerText ?? ''`)
  const title = () => evaluate(`document.querySelector('#entry-login-title')?.innerText ?? ''`)
  const button = (text) => `[...document.querySelectorAll('.entry-login button')].find(b=>b.textContent.trim()===${JSON.stringify(text)})`
  const click = async (text) => { await wait(`!!(${button(text)}) && !(${button(text)}).disabled`, `button "${text}"`); await evaluate(`(${button(text)}).click()`); await sleep(120) }
  /** Sets a React-controlled input and fires the event React listens to. */
  const setInput = (selector, value) => evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, ${JSON.stringify(value)}); el.dispatchEvent(new Event('input', { bubbles: true })) })()`)
  const typeKeys = async (digits) => { for (const d of digits) { await command('Input.insertText', { text: d }); await sleep(40) } }
  const boxes = () => evaluate(`[...document.querySelectorAll('.entry-otp input')].map(i => i.value).join('')`)
  const noOverflow = async (label) => assert.equal(await evaluate('document.documentElement.scrollWidth > innerWidth + 1'), false, `horizontal overflow: ${label}`)
  const openForgot = async (label) => {
    await command('Page.navigate', { url: `http://127.0.0.1:${port}/login` })
    await wait(`!!document.querySelector('.entry-login #entry-email')`, 'sign-in dialog')
    await evaluate(`[...document.querySelectorAll('.entry-login .entry-login-link')][0].click()`)
    await wait(`!!document.querySelector('#forgot-email')`, `forgot password: ${label}`)
  }
  const toOtp = async () => {
    await setInput('#forgot-email', EMAIL)
    await evaluate(`document.querySelector('.entry-login form .entry-login-submit').click()`)
    await wait(`document.querySelectorAll('.entry-otp input').length === 6`, 'the six code boxes')
  }

  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })

  // 1. Sign in, "Forgot password", the email: the next thing on screen is the six boxes, in the same dialog.
  await openForgot('en')
  assert.equal(await title(), 'Reset password')
  await evaluate(`document.querySelector('.entry-login form .entry-login-submit').click()`)
  await wait(`!!document.querySelector('.entry-login-error')`, 'an empty email is refused')
  assert.equal(log.includes('POST /auth/password-reset/request'), false, 'no request without an email')
  await toOtp()
  assert.equal(await title(), 'Enter the code')
  assert.ok((await panel()).includes(EMAIL), 'the screen says where the code went')
  assert.notEqual(await evaluate(`location.pathname`), '/reset-password', 'no page change')
  assert.equal(await evaluate(`document.activeElement === document.querySelector('.entry-otp input')`), true, 'the first box has the focus')
  assert.equal(await evaluate(`document.querySelector('.entry-otp input').autocomplete`), 'one-time-code')
  assert.equal(await evaluate(`${button('Continue')}.disabled`), true, 'nothing to send before six digits')
  assert.match(await panel(), /Send a new code in \d+s/, 'a new code has to wait')
  await shot('forgot-otp-1440.png')

  // 2. Backspace walks back; the sixth digit moves on to the new password. A wrong code is reported by the backend with
  //    the password, and brings the six boxes back, empty.
  await typeKeys('111')
  assert.equal(await boxes(), '111')
  await command('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 })
  await command('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Backspace', code: 'Backspace', windowsVirtualKeyCode: 8 })
  await sleep(80)
  assert.equal(await boxes(), '11', 'Backspace removes the last digit')
  await typeKeys('1111')
  await wait(`!!document.querySelector('#forgot-password')`, 'six digits move on to the new password')
  assert.equal(await title(), 'Choose a new password')
  assert.equal(log.includes('POST /auth/password-reset/confirm'), false, 'nothing is sent before the password')
  await click('Save new password')
  await wait(`!!document.querySelector('#forgot-password-help.entry-login-error')`, 'a weak password is refused')
  await setInput('#forgot-password', 'Newpass123')
  await setInput('#forgot-confirm', 'Newpass124')
  await click('Save new password')
  await wait(`!!document.querySelector('#forgot-confirm-help.entry-login-error')`, 'the two passwords must match')
  assert.equal(log.includes('POST /auth/password-reset/confirm'), false, 'nothing is sent while the form is wrong')
  await setInput('#forgot-confirm', 'Newpass123')
  await click('Save new password')
  await wait(`document.querySelectorAll('.entry-otp input').length === 6 && !!document.querySelector('.entry-login-error')`, 'the wrong code brings the boxes back')
  assert.match(await panel(), /That code is not right/)
  assert.equal(await boxes(), '', 'the boxes are cleared for another try')
  assert.deepEqual(bodies.at(-1), { path: '/auth/password-reset/confirm', email: EMAIL, code: '111111', new_password: 'Newpass123' })

  // 3. A pasted code fills every box and moves on; the passwords typed before are still there.
  await evaluate(`(() => { const el = document.querySelector('.entry-otp input'); el.focus(); const dt = new DataTransfer(); dt.setData('text', ' ${CODE.slice(0, 3)} ${CODE.slice(3)} '); el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })) })()`)
  await wait(`!!document.querySelector('#forgot-password')`, 'the new password step again')
  assert.equal(await evaluate(`document.querySelector('#forgot-password').value`), 'Newpass123', 'the password typed is kept')
  await click('Save new password')
  await wait(`!!(${button('Sign in')})`, 'the reset is done')
  assert.deepEqual(bodies.at(-1), { path: '/auth/password-reset/confirm', email: EMAIL, code: CODE, new_password: 'Newpass123' })
  await click('Sign in')
  await wait(`!!document.querySelector('#entry-email')`, 'back to sign in')
  assert.equal(await evaluate(`document.querySelector('#entry-email').value`), EMAIL, 'the email is already filled in')
  assert.match(await panel(), /Your password has been changed/)

  // 3b. By phone: the switch, the number verified on the account, the code by SMS, the same confirm call with the phone.
  await openForgot('phone')
  const via = (n) => `document.querySelectorAll('.entry-seg button')[${n}]`
  assert.equal(await evaluate(`${via(0)}.getAttribute('aria-checked')`), 'true', 'email is the default')
  await evaluate(`${via(1)}.click()`)
  await wait(`!!document.querySelector('#forgot-phone')`, 'the phone field')
  assert.equal(await evaluate(`!!document.querySelector('#forgot-email')`), false, 'one field at a time')
  assert.match(await panel(), /verified/, 'the screen says the number must be verified')
  await sleep(250)
  assert.equal(await evaluate(`${via(1)}.classList.contains('on') && !${via(0)}.classList.contains('on') && ${via(1)}.getAttribute('aria-checked') === 'true'`), true, 'the phone choice is the selected one')
  await shot('forgot-phone-1440.png')
  await setInput('#forgot-phone', '12345')
  await evaluate(`document.querySelector('.entry-login form .entry-login-submit').click()`)
  await wait(`!!document.querySelector('.entry-login-error')`, 'a bad number is refused')
  assert.equal(log.includes('POST /auth/phone-reset/request'), false, 'no request with a bad number')
  await setInput('#forgot-phone', '090 123 4567')
  await evaluate(`document.querySelector('.entry-login form .entry-login-submit').click()`)
  await wait(`document.querySelectorAll('.entry-otp input').length === 6`, 'the six boxes after the number')
  assert.deepEqual(bodies.at(-1), { path: '/auth/phone-reset/request', phone: '0901234567' }, 'spaces are dropped from the number')
  assert.match(await panel(), /If 0901234567 is verified/, 'nothing says whether the number has an account')
  await typeKeys(CODE)
  await wait(`!!document.querySelector('#forgot-password')`, 'the new password after the SMS code')
  await setInput('#forgot-password', 'Newpass123')
  await setInput('#forgot-confirm', 'Newpass123')
  await click('Save new password')
  await wait(`!!(${button('Sign in')})`, 'the reset by phone is done')
  assert.deepEqual(bodies.at(-1), { path: '/auth/password-reset/confirm', phone: '0901234567', code: CODE, new_password: 'Newpass123' })
  await click('Sign in')
  await wait(`!!document.querySelector('#entry-email')`, 'back to sign in after the phone reset')
  assert.match(await panel(), /Your password has been changed/)
  // Vietnamese, narrow: the switch and the phone field fit.
  await evaluate(`localStorage.setItem('aivhrs-lang','vi')`)
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await openForgot('phone vi 390')
  await evaluate(`${via(1)}.click()`)
  await wait(`!!document.querySelector('#forgot-phone')`, 'the phone field, vi 390')
  await noOverflow('phone vi 390')
  assert.equal(await evaluate(`(() => { const d = document.querySelector('.entry-login').getBoundingClientRect(); return [...document.querySelectorAll('.entry-seg button')].every(b => { const r = b.getBoundingClientRect(); return r.left >= d.left && r.right <= d.right && b.scrollWidth <= b.clientWidth + 1 }) })()`), true, 'the switch fits: vi 390')
  await sleep(250)
  await shot('forgot-phone-vi-390.png')
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })

  // 4. Vietnamese and Japanese, wide and narrow: the six boxes fit.
  for (const [lang, heading] of [['vi', 'Nhập mã xác nhận'], ['ja', '確認コードを入力']]) {
    for (const width of [1440, 390]) {
      await evaluate(`localStorage.setItem('aivhrs-lang','${lang}')`)
      await command('Emulation.setDeviceMetricsOverride', { width, height: width === 390 ? 844 : 1000, deviceScaleFactor: 1, mobile: width === 390 })
      await openForgot(`${lang} ${width}`)
      await toOtp()
      assert.equal(await title(), heading)
      await noOverflow(`${lang} ${width}`)
      assert.equal(await evaluate(`(() => { const d = document.querySelector('.entry-login').getBoundingClientRect(); return [...document.querySelectorAll('.entry-otp input')].every(i => { const r = i.getBoundingClientRect(); return r.left >= d.left && r.right <= d.right && r.width >= 34 }) })()`), true, `the boxes fit: ${lang} ${width}`)
      if (lang === 'vi') await shot(`forgot-otp-vi-${width}.png`)
    }
  }

  // 5. The page the email links to (no token in the link): the email, the six boxes and the new password on one screen.
  await evaluate(`localStorage.setItem('aivhrs-lang','en')`)
  await command('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false })
  const openPage = async (query, label) => {
    await command('Page.navigate', { url: `http://127.0.0.1:${port}/reset-password${query}` })
    await wait(`!!document.querySelector('.entry-reset #reset-password')`, `reset page: ${label}`)
  }
  const save = () => evaluate(`document.querySelector('.entry-reset .entry-login-submit').click()`)
  const pageText = () => evaluate(`document.querySelector('.entry-reset')?.innerText ?? ''`)
  await openPage('', 'no token')
  assert.equal(await evaluate(`location.search`), '', 'nothing is left in the address')
  assert.equal(await evaluate(`!!document.querySelector('#reset-email') && document.querySelectorAll('.entry-reset .entry-otp input').length === 6`), true, 'email and six boxes')
  await save()
  await wait(`!!document.querySelector('#reset-email-help.entry-login-error') && !!document.querySelector('#reset-code-help.entry-login-error')`, 'email and code are required')
  await setInput('#reset-email', EMAIL)
  await evaluate(`document.querySelector('.entry-reset .entry-otp input').focus()`)
  await typeKeys(CODE)
  await setInput('#reset-password', 'Newpass123')
  await setInput('#reset-confirm', 'Newpass123')
  await save()
  await wait(`/Your password has been changed/.test(document.querySelector('.entry-reset').innerText)`, 'saved with the code')
  assert.deepEqual(bodies.at(-1), { path: '/auth/password-reset/confirm', email: EMAIL, code: CODE, new_password: 'Newpass123' })
  await shot('reset-page-done-1440.png')

  // `?email=` fills the email in; a wrong code clears the boxes and keeps the rest.
  await openPage(`?email=${encodeURIComponent(EMAIL)}`, 'email given')
  assert.equal(await evaluate(`document.querySelector('#reset-email').value`), EMAIL)
  assert.equal(await evaluate(`document.activeElement === document.querySelector('.entry-reset .entry-otp input')`), true, 'the first box has the focus when the email is known')
  await typeKeys('000000')
  await setInput('#reset-password', 'Newpass123')
  await setInput('#reset-confirm', 'Newpass123')
  await shot('reset-page-code-1440.png')
  await save()
  await wait(`!!document.querySelector('.entry-reset p.entry-login-error')`, 'the wrong code is refused')
  assert.match(await pageText(), /That code is not right/)
  assert.equal(await evaluate(`[...document.querySelectorAll('.entry-reset .entry-otp input')].map(i => i.value).join('')`), '', 'the boxes are cleared')
  assert.equal(await evaluate(`document.querySelector('#reset-password').value`), 'Newpass123', 'the password is kept')

  // A token left in an old link is ignored: the page still asks for the email and the code.
  await openPage('?token=old-token', 'old link')
  assert.equal(await evaluate(`!!document.querySelector('#reset-email') && document.querySelectorAll('.entry-reset .entry-otp input').length === 6`), true, 'an old token link shows the code form')
  assert.equal(await evaluate(`location.search`), '', 'the token is dropped from the address')

  // Narrow, in Vietnamese: the page fits.
  await evaluate(`localStorage.setItem('aivhrs-lang','vi')`)
  await command('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 1, mobile: true })
  await openPage('', 'vi 390')
  await noOverflow('reset page vi 390')
  await shot('reset-page-vi-390.png')

  assert.deepEqual(errors, [])
  console.log('PASS: email then six code boxes in the dialog (no page change), focus and one-time-code, Backspace, six digits move on, new password rules, confirm with email + code + password, wrong code brings the boxes back, paste, back to sign in with the email filled in, by phone (switch, number rule, SMS request, confirm with the phone), vi/ja at 1440 and 390; the /reset-password page (email + code + password, ?email=, wrong code, no token read or sent). All API calls intercepted.')
} finally {
  ws?.close(); browser?.kill(); server.closeAllConnections(); server.close()
}
