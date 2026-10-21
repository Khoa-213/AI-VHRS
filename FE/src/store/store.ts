import { useMemo, useSyncExternalStore } from 'react'
import type { Order, Profile, OrderStatus, QcReport, User } from '../types'
import { getTokens, onSessionExpired } from '../services/api'
import { apiGoogleLogin, apiLogin, apiLogout, apiMe, apiUpdateMe } from '../services/auth'

/**
 * App state in small subscribable stores. The signed-in user comes from the
 * backend (services/auth.ts); the customer's orders come from the API
 * (services/orders.ts). The orders kept here are the staff and technician screens' own, until those are wired in.
 */

const KEYS = {
  orders: 'aivhrs-orders',
  profiles: 'aivhrs-profiles',
  user: 'aivhrs-user',
} as const

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage full or blocked: keep working in memory */
  }
}

function createStore<T>(init: () => T, persist: (v: T) => void) {
  let value = init()
  const subs = new Set<() => void>()
  return {
    get: () => value,
    set(next: T) {
      value = next
      persist(next)
      subs.forEach((s) => s())
    },
    subscribe(cb: () => void) {
      subs.add(cb)
      return () => {
        subs.delete(cb)
      }
    },
  }
}

/** Ids of the sample orders the prototype used to seed. */
const SAMPLE_IDS = ['VH-4821', 'VH-4710', 'VH-4532']

// ---------- stores ----------

const ordersStore = createStore<Order[]>(
  () => {
    // Browsers that ran the prototype still hold its sample orders and flags: drop them once.
    try {
      localStorage.removeItem('aivhrs-prototype')
      localStorage.removeItem('aivhrs-staff-demos')
    } catch {
      // Storage blocked: nothing to clean.
    }
    const saved = read<Order[]>(KEYS.orders)
    return Array.isArray(saved) ? saved.filter((o) => !SAMPLE_IDS.includes(o.id)) : []
  },
  (orders) => {
    try {
      localStorage.setItem(KEYS.orders, JSON.stringify(orders.slice(0, 30)))
    } catch {
      // Uploaded photos are big. Drop the images and keep the orders.
      const slim = orders.slice(0, 10).map((o) => ({
        ...o,
        spec: { ...o.spec, img: null },
        qc: o.qc ? { ...o.qc, photos: [] } : undefined,
      }))
      write(KEYS.orders, slim)
    }
  },
)

const profilesStore = createStore<Record<string, Partial<Profile>>>(
  () => read<Record<string, Partial<Profile>>>(KEYS.profiles) ?? {},
  (p) => write(KEYS.profiles, p),
)

/** Cached copy of the signed-in account. Only trusted while API tokens exist; refreshed by `startSession`. */
const userStore = createStore<User | null>(
  () => (getTokens() ? read<User>(KEYS.user) : null),
  (u) => write(KEYS.user, u),
)

/** True after the refresh token was rejected, until the next sign-in. The login page explains it. */
const expiredStore = createStore<boolean>(
  () => {
    try {
      return sessionStorage.getItem('aivhrs-expired') === '1'
    } catch {
      return false
    }
  },
  (v) => {
    try {
      if (v) sessionStorage.setItem('aivhrs-expired', '1')
      else sessionStorage.removeItem('aivhrs-expired')
    } catch {
      // The notice just will not survive a reload.
    }
  },
)

// ---------- hooks ----------

export const useOrders = () => useSyncExternalStore(ordersStore.subscribe, ordersStore.get)
export const useUser = () => useSyncExternalStore(userStore.subscribe, userStore.get)
export const useSessionExpired = () => useSyncExternalStore(expiredStore.subscribe, expiredStore.get)
/** Profile of the signed-in user. Missing fields fall back to the account name. */
export function useProfile(): Profile {
  const all = useSyncExternalStore(profilesStore.subscribe, profilesStore.get)
  const user = useUser()
  return useMemo(() => {
    const p = (user && all[profileKey(user)]) || {}
    // Name, email and phone come from the backend account; the rest is kept on this device.
    return {
      fullName: user?.name ?? '',
      email: user?.email ?? '',
      phone: user?.phone ?? '',
      address: p.address ?? '',
      bio: p.bio ?? '',
      avatar: p.avatar ?? null,
      payMethod: p.payMethod ?? null,
    }
  }, [all, user])
}


/** Orders staff can work on: pending, accepted and rejected. */
export function useStaffQueue(): Order[] {
  const orders = useOrders()
  return useMemo(() => orders.filter((o) => ['Pending', 'Accepted', 'Rejected'].includes(o.status)), [orders])
}

/** Every order staff care about: those past the sketch step. */
export function useAllStaffOrders(): Order[] {
  const orders = useOrders()
  return useMemo(() => orders.filter((o) => o.status !== 'Sketching'), [orders])
}

/** The order for an id, or null when there is none. */
export function useOrder(id: string | null): Order | null {
  const orders = useOrders()
  return orders.find((o) => o.id === id) ?? null
}

// ---------- actions ----------

/** Signs in against the backend. Throws an `ApiError` (see `authErrorKey`). */
export async function signInWithPassword(email: string, password: string): Promise<User> {
  const user = await apiLogin(email.trim(), password)
  expiredStore.set(false)
  userStore.set(user)
  return user
}

/** Signs in with a Google ID token (customers). Throws an `ApiError`. */
export async function signInWithGoogle(idToken: string): Promise<User> {
  const user = await apiGoogleLogin(idToken)
  expiredStore.set(false)
  userStore.set(user)
  return user
}

/** Signs out here at once and revokes the session on the server in the background. */
export function signOut() {
  void apiLogout()
  userStore.set(null)
}

/**
 * Checks the saved session against `GET /me` when the app starts, so a
 * changed name or role shows up and a revoked session ends.
 */
export function startSession() {
  onSessionExpired(() => {
    userStore.set(null)
    expiredStore.set(true)
  })
  if (!getTokens()) {
    if (userStore.get()) userStore.set(null)
    return
  }
  apiMe()
    .then((u) => userStore.set(u))
    .catch(() => {
      // Offline or waking server: keep the cached user. A rejected session already signed out.
    })
}

export function updateOrder(id: string, patch: Partial<Order>) {
  ordersStore.set(ordersStore.get().map((o) => (o.id === id ? { ...o, ...patch } : o)))
}

/** Technician presses Start on the robot. */
export function startRobotRun(id: string, robotId: string, seconds = 45) {
  updateOrder(id, { run: { robotId, startedAt: Date.now(), seconds } })
}

/** QC passed: the order is Written and the customer gets the photos. */
export function submitQc(id: string, qc: QcReport) {
  updateOrder(id, { status: 'Written', qc, run: undefined, qcFail: undefined })
}

/** QC failed: back to the robot queue to be rescheduled. */
export function failQc(id: string, reasons: string[], note: string) {
  updateOrder(id, {
    status: 'Queued', run: undefined, qc: undefined,
    qcFail: { reasons, note, at: new Date().toISOString() },
  })
}

export function saveStaffOrder(order: Order) {
  updateOrder(order.id, order)
}

export function setStatus(id: string, status: OrderStatus, patch: Partial<Order> = {}) {
  updateOrder(id, { ...patch, status })
}

// ---------- profile ----------

const profileKey = (u: User) => u.email ?? u.name

/** Fields kept on this device only (address, bio, picture, payment method). */
export function updateProfile(patch: Partial<Omit<Profile, 'fullName' | 'email' | 'phone'>>) {
  const u = userStore.get()
  if (!u) return
  const all = profilesStore.get()
  const key = profileKey(u)
  profilesStore.set({ ...all, [key]: { ...all[key], ...patch } })
}

/** Name and phone live on the backend account (`PATCH /me`). Throws an `ApiError`. */
export async function saveAccount(patch: { fullName?: string; phone?: string | null }) {
  const u = await apiUpdateMe({
    ...(patch.fullName !== undefined ? { full_name: patch.fullName } : {}),
    ...(patch.phone !== undefined ? { phone: patch.phone } : {}),
  })
  userStore.set(u)
  return u
}
