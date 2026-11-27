/**
 * A phone number proved by Firebase Authentication (`BE/docs/FE_API_GUIDE.md` 3.2, 2026-11-27). Google texts the 6-digit
 * code and checks it; what comes back is a Firebase ID token, sent to the backend as the proof (`POST
 * /me/phone/verify-firebase`, or `firebase_id_token` in `POST /auth/password-reset/confirm`). The Firebase session itself
 * is not kept: it is signed out as soon as the token is read.
 *
 * On only when the four `VITE_FIREBASE_*` values are set (public values of the project's web app). Without them
 * `firebasePhoneEnabled` is false and the screens keep the backend's own SMS code flow. The SDK is loaded on first use.
 */
import type { Auth, RecaptchaVerifier } from 'firebase/auth'
import type { Lang } from '../i18n'
import { authErrorKey } from './api'

const env = import.meta.env as Record<string, string | undefined>
const config = {
  apiKey: env.VITE_FIREBASE_API_KEY,
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: env.VITE_FIREBASE_PROJECT_ID,
  appId: env.VITE_FIREBASE_APP_ID,
}

export const firebasePhoneEnabled = !!(config.apiKey && config.authDomain && config.projectId && config.appId)

/** A failure of the Firebase step, with the translation key to show. */
export class FirebasePhoneError extends Error {
  key: string
  code: string
  constructor(key: string, code: string) {
    super(code)
    this.key = key
    this.code = code
  }
}

/** Translation key for an error of either side: Firebase's step or the backend's answer. */
export const phoneErrorKey = (e: unknown): string => (e instanceof FirebasePhoneError ? e.key : authErrorKey(e))

/** A code that was texted: `confirm` checks what the person typed and gives the ID token for the backend. */
export interface PhoneCode {
  confirm(code: string): Promise<string>
}

function toError(e: unknown): FirebasePhoneError {
  if (e instanceof FirebasePhoneError) return e
  const code = typeof (e as { code?: unknown } | null)?.code === 'string' ? (e as { code: string }).code : 'unknown'
  const key = (() => {
    switch (code) {
      case 'auth/invalid-phone-number':
      case 'auth/missing-phone-number': return 'reset.errPhone'
      case 'auth/invalid-verification-code':
      case 'auth/missing-verification-code': return 'auth.err.otpInvalid'
      case 'auth/code-expired':
      case 'auth/session-expired': return 'auth.err.otpExpired'
      case 'auth/too-many-requests':
      case 'auth/quota-exceeded': return 'auth.err.phoneTooMany'
      case 'auth/captcha-check-failed':
      case 'auth/invalid-app-credential':
      case 'auth/missing-app-credential': return 'auth.err.phoneCaptcha'
      case 'auth/network-request-failed': return 'auth.err.network'
      // The project's own setup: provider off, region not allowed, domain not authorised, no billing, bad key.
      case 'auth/operation-not-allowed':
      case 'auth/unauthorized-domain':
      case 'auth/billing-not-enabled':
      case 'auth/invalid-api-key':
      case 'auth/app-not-authorized': return 'auth.err.phoneSetup'
    }
    return 'ph.err.sms'
  })()
  // The exact Firebase code is what tells a setup problem apart; it never holds the number or the code.
  console.warn('[firebase phone]', code)
  return new FirebasePhoneError(key, code)
}

type Loaded = { auth: Auth; mod: typeof import('firebase/auth') }
let loading: Promise<Loaded> | null = null

function load(): Promise<Loaded> {
  loading ??= (async () => {
    const [{ initializeApp }, mod] = await Promise.all([import('firebase/app'), import('firebase/auth')])
    return { auth: mod.getAuth(initializeApp(config)), mod }
  })().catch((e) => {
    loading = null
    throw e
  })
  return loading
}

/** The modal dialog on screen, if any: everything outside it is inert, so reCAPTCHA has to live inside it. */
const modal = () => document.querySelector<HTMLDialogElement>('dialog:modal')

const isChallenge = (node: Node): node is HTMLElement =>
  node instanceof HTMLElement && !!node.querySelector('iframe[src*="recaptcha"]')

let host: HTMLElement | null = null
let verifier: RecaptchaVerifier | null = null
let watcher: MutationObserver | null = null

/**
 * reCAPTCHA appends its picture challenge to `<body>`. Under a modal `<dialog>` (the sign-in dialog, the phone reminder)
 * that is behind the top layer and cannot be clicked, so it is moved into the dialog as soon as it appears.
 */
function adoptChallenges() {
  const move = (node: Node) => {
    const dialog = modal()
    if (dialog && isChallenge(node) && node !== host && !dialog.contains(node)) dialog.appendChild(node)
  }
  document.body.childNodes.forEach(move)
  watcher = new MutationObserver((records) => records.forEach((r) => r.addedNodes.forEach(move)))
  watcher.observe(document.body, { childList: true })
}

/** Drops the reCAPTCHA widget of the last code. Call it when the screen that asked for the code goes away. */
export function cancelPhoneCode() {
  watcher?.disconnect()
  watcher = null
  try {
    verifier?.clear()
  } catch {
    // Already gone with its container.
  }
  verifier = null
  host?.remove()
  host = null
}

/**
 * Texts a code to the number (Vietnamese numbers as `0xxxxxxxxx` or `+84xxxxxxxxx`) in the reader's language. Each call
 * makes a fresh invisible reCAPTCHA; a picture challenge may open before the SMS leaves. Throws a `FirebasePhoneError`.
 */
export async function sendPhoneCode(phone: string, lang: Lang): Promise<PhoneCode> {
  if (!firebasePhoneEnabled) throw new FirebasePhoneError('auth.err.phoneSetup', 'not-configured')
  cancelPhoneCode()
  try {
    const { auth, mod } = await load()
    auth.languageCode = lang
    host = document.createElement('div')
    ;(modal() ?? document.body).appendChild(host)
    adoptChallenges()
    verifier = new mod.RecaptchaVerifier(auth, host, { size: 'invisible' })
    const number = phone.startsWith('+') ? phone : `+84${phone.slice(1)}`
    const confirmation = await mod.signInWithPhoneNumber(auth, number, verifier)
    return {
      async confirm(code: string) {
        try {
          const { user } = await confirmation.confirm(code)
          const token = await user.getIdToken()
          // Only the proof is wanted: no Firebase session stays in this browser.
          await mod.signOut(auth).catch(() => undefined)
          cancelPhoneCode()
          return token
        } catch (e) {
          throw toError(e)
        }
      },
    }
  } catch (e) {
    cancelPhoneCode()
    throw toError(e)
  }
}
