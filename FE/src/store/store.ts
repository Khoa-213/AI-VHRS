import { useMemo, useSyncExternalStore } from 'react'
import { INKS, PAPERS, PENS, TYPES, FONT_STYLES } from '../constants/catalog'
import { PACK_STEPS, emptyShipment, nextMockLog, scriptedLogs } from '../services/ghn'
import type { Order, OrderDraft, OrderSpec, OrderStatus, QcReport, ShipLog, Shipment, User } from '../types'

/**
 * Front-end-only "backend": orders, cart, user and prototype flag live in
 * localStorage and are exposed through small subscribable stores. Swap the
 * functions at the bottom for API calls when a real backend exists.
 */

const KEYS = {
  orders: 'aivhrs-orders',
  drafts: 'aivhrs-drafts',
  user: 'aivhrs-user',
  prototype: 'aivhrs-prototype',
  staffDemos: 'aivhrs-staff-demos',
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

// ---------- seeds ----------

function makeSpec(over: Partial<OrderSpec> = {}): OrderSpec {
  const t = TYPES[0]
  return {
    type: t.name, size: t.size, aspect: t.aspect, land: t.land, mins: t.mins,
    paper: PAPERS[0].name, paperColor: PAPERS[0].color,
    pen: PENS[0].name, penW: PENS[0].w,
    ink: INKS[0].name, inkColor: INKS[0].color,
    font: FONT_STYLES[0].font, fontName: FONT_STYLES[0].name,
    mode: 'text', text: 'Chúc Mừng Năm Mới', img: null, qty: 10,
    ...over,
  }
}

const SEED_SHIP_TO = {
  name: 'Khang', phone: '0901234567', street: '12 Nguyễn Huệ', ward: 'Bến Nghé', city: 'TP. Hồ Chí Minh', note: '',
}

/** A sample order's shipment, scanned through `through`, finishing some days ago. */
function seedShipment(code: string, through: ShipLog['status'], qty: number, daysAgo = 0): Shipment {
  const end = new Date(Date.now() - daysAgo * 864e5 - 36e5)
  const logs = scriptedLogs(through, end, SEED_SHIP_TO.city)
  const first = new Date(logs[0].at)
  return {
    pack: PACK_STEPS.map((p, i) => ({ id: p.id, at: new Date(first.getTime() - (3 - i) * 36e5).toISOString() })),
    weightG: Math.max(150, 120 + qty * 15),
    codAmount: 0,
    ghnCode: code,
    bookedAt: new Date(first.getTime() - 36e5).toISOString(),
    fee: 27000,
    expectedAt: new Date(end.getTime() + (through === 'delivered' ? 0 : 864e5)).toISOString(),
    logs,
  }
}

function seedOrders(): Order[] {
  const wed = TYPES[3]
  return [
    {
      id: 'VH-4821', title: 'Wedding invitation × 120', detail: 'Cotton rag · Metallic gold',
      status: 'Queued', total: 9840000, date: '06 Oct 2026', layout: 'framed', staff: 'Minh · AI-VHRS Studio',
      assignment: { techId: 'T-01', techName: 'Hà Trần', robotId: 'FR3-01', at: '2026-10-06T08:00:00.000Z' },
      spec: makeSpec({
        type: wed.name, size: wed.size, aspect: wed.aspect, land: wed.land, mins: wed.mins,
        paper: PAPERS[1].name, paperColor: PAPERS[1].color, ink: INKS[4].name, inkColor: INKS[4].color,
        font: FONT_STYLES[1].font, fontName: FONT_STYLES[1].name, text: 'Thu & Khang', qty: 120,
      }),
    },
    {
      id: 'VH-4710', title: 'Greeting card × 10', detail: 'Ivory · Midnight blue',
      status: 'Shipped', total: 405000, date: '28 Sep 2026', staff: 'Minh · AI-VHRS Studio',
      spec: makeSpec({ qty: 10 }),
      shipTo: SEED_SHIP_TO,
      shipment: seedShipment('LBX4K2TM', 'sorting', 10),
    },
    {
      id: 'VH-4532', title: 'Handwritten letter × 1', detail: 'Giấy dó · Sepia',
      status: 'Delivered', total: 145000, date: '02 Sep 2026', staff: 'Minh · AI-VHRS Studio',
      spec: makeSpec({
        type: TYPES[1].name, size: TYPES[1].size, aspect: TYPES[1].aspect, mins: TYPES[1].mins,
        paper: PAPERS[3].name, paperColor: PAPERS[3].color, ink: INKS[2].name, inkColor: INKS[2].color,
        font: FONT_STYLES[2].font, fontName: FONT_STYLES[2].name, text: 'Gửi em, người thương…', qty: 1,
      }),
      shipTo: SEED_SHIP_TO,
      shipment: seedShipment('GHNW7P9Q', 'delivered', 1, 21),
    },
  ]
}

/** Sample orders waiting in the staff console, one per input type. */
function staffDemoSeeds(): Order[] {
  const base = makeSpec()
  return [
    {
      id: 'VH-5102', title: 'Wedding invitation × 120', detail: 'Cotton rag · Metallic gold', status: 'Pending',
      total: 9840000, name: 'Thu Trang', date: '10 Oct 2026', demo: true,
      spec: makeSpec({
        type: TYPES[3].name, size: TYPES[3].size, aspect: TYPES[3].aspect, mins: TYPES[3].mins,
        paper: PAPERS[1].name, paperColor: PAPERS[1].color, ink: INKS[4].name, inkColor: INKS[4].color,
        font: FONT_STYLES[1].font, fontName: FONT_STYLES[1].name, mode: 'text',
        text: 'Trân trọng kính mời\nThu & Khang', qty: 120,
      }),
    },
    {
      id: 'VH-5107', title: 'Handwritten letter × 1', detail: 'Giấy dó · Sepia', status: 'Pending',
      total: 145000, name: 'Quốc Bảo', date: '10 Oct 2026', demo: true,
      spec: {
        ...makeSpec({
          type: TYPES[1].name, size: TYPES[1].size, aspect: TYPES[1].aspect, mins: TYPES[1].mins,
          paper: PAPERS[3].name, paperColor: PAPERS[3].color, ink: INKS[2].name, inkColor: INKS[2].color,
          mode: 'upload', text: '', qty: 1,
        }),
        fileName: 'thu-gui-me.jpg',
        simText: 'Gửi mẹ,\ncon nhớ mẹ nhiều lắm.\nTết này con về nhé.',
      },
    },
    {
      id: 'VH-5111', title: 'Greeting card × 10', detail: 'Ivory · Midnight blue', status: 'Pending',
      total: 405000, name: 'Ngọc Hân', date: '09 Oct 2026', demo: true,
      spec: { ...base, mode: 'draw', text: '', qty: 10, simText: 'chúc mừng sinh nhật\nbé Na tròn 5 tuổi' },
    },
  ]
}

const DEMO_USER: User = { name: 'Khang', role: 'customer' }

/** Prototype accounts. Any other email signs in as a customer. */
export const STAFF_ACCOUNTS: Record<string, string> = { 'minh@aivhrs.vn': 'Minh' }

/** Technician accounts, matched to the roster ids on the assignment page. */
export const TECH_ACCOUNTS: Record<string, { name: string; techId: string }> = {
  'ha@aivhrs.vn': { name: 'Hà Trần', techId: 'T-01' },
  'phuc@aivhrs.vn': { name: 'Phúc Lê', techId: 'T-02' },
  'anh@aivhrs.vn': { name: 'Anh Vũ', techId: 'T-03' },
  'thao@aivhrs.vn': { name: 'Thảo Đinh', techId: 'T-04' },
}

// ---------- stores ----------

const ordersStore = createStore<Order[]>(
  () => {
    const saved = read<Order[]>(KEYS.orders)
    if (Array.isArray(saved) && saved.length) {
      // Sample order saved before technicians existed: give it to the first one.
      return saved.map((o) =>
        o.id === 'VH-4821' && o.status === 'Queued' && !o.assignment
          ? { ...o, assignment: { techId: 'T-01', techName: 'Hà Trần', robotId: 'FR3-01', at: '2026-10-06T08:00:00.000Z' } }
          : o,
      )
    }
    const seed = seedOrders()
    write(KEYS.orders, seed)
    return seed
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

const draftsStore = createStore<OrderDraft[]>(
  () => {
    const saved = read<OrderDraft[]>(KEYS.drafts)
    return Array.isArray(saved) ? saved : []
  },
  (d) => {
    try {
      localStorage.setItem(KEYS.drafts, JSON.stringify(d))
    } catch {
      // Photos and drawings are big. Keep the drafts, drop their bitmaps.
      write(KEYS.drafts, d.map((x) => ({ ...x, drawUrl: null, upload: x.upload ? { ...x.upload, dataUrl: undefined } : null })))
    }
  },
)

const userStore = createStore<User | null>(
  () => {
    const raw = localStorage.getItem(KEYS.user)
    if (raw === null) return DEMO_USER
    const saved = read<Partial<User>>(KEYS.user)
    // Sessions saved before roles existed are customers.
    if (!saved?.name) return null
    if (saved.role === 'technician' && saved.techId) return { name: saved.name, role: 'technician', techId: saved.techId }
    return { name: saved.name, role: saved.role === 'staff' ? 'staff' : 'customer' }
  },
  (u) => write(KEYS.user, u),
)

const staffDemoStore = createStore<Order[]>(
  () => {
    const saved = read<Order[]>(KEYS.staffDemos)
    return Array.isArray(saved) ? saved : staffDemoSeeds()
  },
  (o) => write(KEYS.staffDemos, o),
)

const prototypeStore = createStore<boolean>(
  () => read<boolean>(KEYS.prototype) ?? true,
  (v) => write(KEYS.prototype, v),
)

// ---------- hooks ----------

export const useOrders = () => useSyncExternalStore(ordersStore.subscribe, ordersStore.get)
export const useUser = () => useSyncExternalStore(userStore.subscribe, userStore.get)
export const useAllDrafts = () => useSyncExternalStore(draftsStore.subscribe, draftsStore.get)
export const usePrototypeMode = () => useSyncExternalStore(prototypeStore.subscribe, prototypeStore.get)

/** Orders staff can work on: the customer's real orders plus the console's own sample orders. */
export function useStaffQueue(): Order[] {
  const orders = useOrders()
  const demos = useSyncExternalStore(staffDemoStore.subscribe, staffDemoStore.get)
  return useMemo(
    () => [...orders.filter((o) => ['Pending', 'Accepted', 'Rejected'].includes(o.status)), ...demos],
    [orders, demos],
  )
}

/** Every order staff care about: customers' orders past the sketch step, plus the sample orders. */
export function useAllStaffOrders(): Order[] {
  const orders = useOrders()
  const demos = useSyncExternalStore(staffDemoStore.subscribe, staffDemoStore.get)
  return useMemo(() => [...orders.filter((o) => o.status !== 'Sketching'), ...demos], [orders, demos])
}

/**
 * The order for an id. Unknown or missing ids fall back to the newest order,
 * so every order page always has something to show.
 */
export function useOrder(id: string | null): Order | null {
  const orders = useOrders()
  return orders.find((o) => o.id === id) ?? orders[0] ?? null
}

/** Drafts of the signed-in user, newest first. */
export function useDrafts(): OrderDraft[] {
  const all = useAllDrafts()
  const user = useUser()
  return useMemo(
    () => all.filter((d) => d.owner === (user?.name ?? 'guest')).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)),
    [all, user],
  )
}

// ---------- actions ----------

export const setPrototypeMode = (on: boolean) => prototypeStore.set(on)
export const signIn = () => {
  userStore.set(DEMO_USER)
  adoptGuestDrafts(DEMO_USER.name)
}

/** Mock login: the email decides the role, the password is not checked. */
export function login(email: string): User {
  const key = email.trim().toLowerCase()
  const staffName = STAFF_ACCOUNTS[key]
  const tech = TECH_ACCOUNTS[key]
  const local = key.split('@')[0] || 'Guest'
  const user: User = staffName
    ? { name: staffName, role: 'staff' }
    : tech
      ? { name: tech.name, role: 'technician', techId: tech.techId }
      : { name: local.charAt(0).toUpperCase() + local.slice(1), role: 'customer' }
  userStore.set(user)
  if (user.role === 'customer') adoptGuestDrafts(user.name)
  return user
}
export const signOut = () => userStore.set(null)

export function createOrderId() {
  return 'VH-' + String(Math.floor(4900 + Math.random() * 5000))
}

export function addOrder(order: Order) {
  ordersStore.set([order, ...ordersStore.get()])
}

export function updateOrder(id: string, patch: Partial<Order>) {
  // The staff console's sample orders live in their own store.
  if (staffDemoStore.get().some((o) => o.id === id)) {
    staffDemoStore.set(staffDemoStore.get().map((o) => (o.id === id ? { ...o, ...patch } : o)))
    return
  }
  ordersStore.set(ordersStore.get().map((o) => (o.id === id ? { ...o, ...patch } : o)))
}

/** Saves a staff change to the right store (sample orders live apart from the customer's). */
/** Technician presses Start on the real robot. The run is simulated in the prototype. */
export function startRobotRun(id: string, robotId: string, seconds = 45) {
  updateOrder(id, { run: { robotId, startedAt: Date.now(), seconds } })
}

/** Prototype only: jumps a running robot job to its end so photo and QC can open. */
export function finishRobotRun(id: string) {
  const o = [...ordersStore.get(), ...staffDemoStore.get()].find((x) => x.id === id)
  if (!o?.run) return
  updateOrder(id, { run: { ...o.run, startedAt: Date.now() - o.run.seconds * 1000 } })
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

// ---------- shipping ----------

function findOrder(id: string): Order | undefined {
  return [...ordersStore.get(), ...staffDemoStore.get()].find((o) => o.id === id)
}

function patchShipment(id: string, fn: (s: Shipment) => Shipment, status?: OrderStatus) {
  const o = findOrder(id)
  if (!o) return
  updateOrder(id, { shipment: fn(o.shipment ?? emptyShipment(o)), ...(status ? { status } : {}) })
}

/** Staff ticks or unticks a packing step. Locked once the courier is booked. */
export function togglePackStep(id: string, step: string) {
  patchShipment(id, (s) => {
    if (s.ghnCode) return s
    const done = s.pack.some((m) => m.id === step)
    return { ...s, pack: done ? s.pack.filter((m) => m.id !== step) : [...s.pack, { id: step, at: new Date().toISOString() }] }
  })
}

export function setParcelWeight(id: string, weightG: number) {
  patchShipment(id, (s) => (s.ghnCode ? s : { ...s, weightG: Math.max(1, Math.round(weightG) || 1) }))
}

/** Saves the GHN order that staff just booked. */
export function saveBooking(id: string, b: { code: string; fee: number; expectedAt: string }) {
  patchShipment(id, (s) => ({ ...s, ghnCode: b.code, fee: b.fee, expectedAt: b.expectedAt, bookedAt: new Date().toISOString() }))
}

/**
 * Takes the scans GHN reports. An order moves to Delivered when GHN says so.
 * Same-length input is ignored, so polling does not rewrite storage.
 */
export function applyShipLogs(id: string, logs: ShipLog[]) {
  const o = findOrder(id)
  const cur = o?.shipment?.logs ?? []
  if (!o || !logs.length) return
  const same = logs.length === cur.length && logs[logs.length - 1].status === cur[cur.length - 1]?.status
  if (same) return
  const delivered = logs[logs.length - 1].status === 'delivered'
  patchShipment(id, (s) => ({ ...s, logs }), delivered ? 'Delivered' : undefined)
}

/** Prototype only: the scripted courier reports its next scan. */
export function advanceCourier(id: string) {
  const o = findOrder(id)
  if (!o?.shipment?.ghnCode) return
  const next = nextMockLog(o.shipment.logs, o.shipTo?.city ?? 'TP. Hồ Chí Minh')
  if (next) applyShipLogs(id, [...o.shipment.logs, next])
}

/** Prototype only: packs, books and runs the scripted courier to the doorstep in one go. */
export function fastForwardCourier(id: string) {
  const o = findOrder(id)
  if (!o) return
  if (!o.shipment?.ghnCode) {
    const at = new Date().toISOString()
    patchShipment(id, (s) => ({
      ...s,
      pack: PACK_STEPS.map((p) => ({ id: p.id, at })),
      ghnCode: 'DEMO' + id.replace(/\D/g, '').padStart(4, '0'),
      bookedAt: at,
      fee: 27000,
      expectedAt: at,
    }))
  }
  let logs = findOrder(id)?.shipment?.logs ?? []
  const city = o.shipTo?.city ?? 'TP. Hồ Chí Minh'
  for (let n = nextMockLog(logs, city); n; n = nextMockLog(logs, city)) logs = [...logs, n]
  applyShipLogs(id, logs)
}

export function saveStaffOrder(order: Order) {
  if (order.demo) staffDemoStore.set(staffDemoStore.get().map((o) => (o.id === order.id ? order : o)))
  else updateOrder(order.id, order)
}

export function setStatus(id: string, status: OrderStatus, patch: Partial<Order> = {}) {
  updateOrder(id, { ...patch, status })
}

// ---------- drafts ----------

export const newDraftId = () => 'DR-' + Date.now().toString(36).toUpperCase() + Math.floor(Math.random() * 36 ** 2).toString(36).toUpperCase()

export const getDraft = (id: string) => draftsStore.get().find((d) => d.id === id)

/** Creates or replaces a draft. */
export function saveDraft(d: OrderDraft) {
  const all = draftsStore.get()
  draftsStore.set(all.some((x) => x.id === d.id) ? all.map((x) => (x.id === d.id ? d : x)) : [d, ...all])
}

export const deleteDraft = (id: string) => draftsStore.set(draftsStore.get().filter((d) => d.id !== id))

export function patchDraft(id: string, patch: Partial<OrderDraft>) {
  const d = getDraft(id)
  if (d) saveDraft({ ...d, ...patch, updatedAt: new Date().toISOString() })
}

/** Drafts started before sign in move to the account that just signed in. */
function adoptGuestDrafts(name: string) {
  const all = draftsStore.get()
  if (all.some((d) => d.owner === 'guest')) draftsStore.set(all.map((d) => (d.owner === 'guest' ? { ...d, owner: name } : d)))
}

/** Wipe everything and go back to the seeded demo data. */
export function resetDemo() {
  ordersStore.set(seedOrders())
  draftsStore.set([])
  userStore.set(DEMO_USER)
  staffDemoStore.set(staffDemoSeeds())
}
