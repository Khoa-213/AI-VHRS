import { useSyncExternalStore } from 'react'
import { INKS, PAPERS, PENS, PRODUCTS, TYPES, FONT_STYLES } from '../constants/catalog'
import type { CartItem, Order, OrderSpec, OrderStatus, User } from '../types'
import { todayLabel } from '../utils/format'

/**
 * Front-end-only "backend": orders, cart, user and prototype flag live in
 * localStorage and are exposed through small subscribable stores. Swap the
 * functions at the bottom for API calls when a real backend exists.
 */

const KEYS = {
  orders: 'aivhrs-orders',
  cart: 'aivhrs-cart',
  user: 'aivhrs-user',
  prototype: 'aivhrs-prototype',
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

function seedOrders(): Order[] {
  const wed = TYPES[3]
  return [
    {
      id: 'VH-4821', title: 'Wedding invitation × 120', detail: 'Cotton rag · Metallic gold',
      status: 'Queued', total: 9840000, date: '06 Oct 2026', layout: 'framed', staff: 'Minh · AI-VHRS Studio',
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
    },
    {
      id: 'VH-4532', title: 'Handwritten letter × 1', detail: 'Giấy dó · Sepia',
      status: 'Delivered', total: 145000, date: '02 Sep 2026', staff: 'Minh · AI-VHRS Studio',
      spec: makeSpec({
        type: TYPES[1].name, size: TYPES[1].size, aspect: TYPES[1].aspect, mins: TYPES[1].mins,
        paper: PAPERS[3].name, paperColor: PAPERS[3].color, ink: INKS[2].name, inkColor: INKS[2].color,
        font: FONT_STYLES[2].font, fontName: FONT_STYLES[2].name, text: 'Gửi em, người thương…', qty: 1,
      }),
    },
  ]
}

const DEMO_USER: User = { name: 'Khang' }

// ---------- stores ----------

const ordersStore = createStore<Order[]>(
  () => {
    const saved = read<Order[]>(KEYS.orders)
    if (Array.isArray(saved) && saved.length) return saved
    const seed = seedOrders()
    write(KEYS.orders, seed)
    return seed
  },
  (orders) => {
    try {
      localStorage.setItem(KEYS.orders, JSON.stringify(orders.slice(0, 30)))
    } catch {
      // Uploaded photos are big. Drop the images and keep the orders.
      const slim = orders.slice(0, 10).map((o) => ({ ...o, spec: { ...o.spec, img: null } }))
      write(KEYS.orders, slim)
    }
  },
)

const cartStore = createStore<CartItem[]>(
  () => {
    const saved = read<CartItem[]>(KEYS.cart)
    return Array.isArray(saved) ? saved : []
  },
  (c) => write(KEYS.cart, c),
)

const userStore = createStore<User | null>(
  () => {
    const raw = localStorage.getItem(KEYS.user)
    if (raw === null) return DEMO_USER
    return read<User>(KEYS.user)
  },
  (u) => write(KEYS.user, u),
)

const prototypeStore = createStore<boolean>(
  () => read<boolean>(KEYS.prototype) ?? true,
  (v) => write(KEYS.prototype, v),
)

// ---------- hooks ----------

export const useOrders = () => useSyncExternalStore(ordersStore.subscribe, ordersStore.get)
export const useCart = () => useSyncExternalStore(cartStore.subscribe, cartStore.get)
export const useUser = () => useSyncExternalStore(userStore.subscribe, userStore.get)
export const usePrototypeMode = () => useSyncExternalStore(prototypeStore.subscribe, prototypeStore.get)

/**
 * The order for an id. Unknown or missing ids fall back to the newest order,
 * so every order page always has something to show.
 */
export function useOrder(id: string | null): Order | null {
  const orders = useOrders()
  return orders.find((o) => o.id === id) ?? orders[0] ?? null
}

// ---------- actions ----------

export const setPrototypeMode = (on: boolean) => prototypeStore.set(on)
export const signIn = () => userStore.set(DEMO_USER)
export const signOut = () => userStore.set(null)

export function createOrderId() {
  return 'VH-' + String(Math.floor(4900 + Math.random() * 5000))
}

export function addOrder(order: Order) {
  ordersStore.set([order, ...ordersStore.get()])
}

export function updateOrder(id: string, patch: Partial<Order>) {
  ordersStore.set(ordersStore.get().map((o) => (o.id === id ? { ...o, ...patch } : o)))
}

export function setStatus(id: string, status: OrderStatus, patch: Partial<Order> = {}) {
  updateOrder(id, { ...patch, status })
}

export function addToCart(item: Omit<CartItem, 'qty'>) {
  const cart = cartStore.get()
  const ex = cart.find((c) => c.key === item.key)
  cartStore.set(
    ex ? cart.map((c) => (c.key === item.key ? { ...c, qty: c.qty + 1 } : c)) : [...cart, { ...item, qty: 1 }],
  )
}

export function setCartQty(key: string, qty: number) {
  const cart = cartStore.get()
  cartStore.set(qty <= 0 ? cart.filter((c) => c.key !== key) : cart.map((c) => (c.key === key ? { ...c, qty } : c)))
}

export const clearCart = () => cartStore.set([])

/** Cart checkout: turns the cart into one order that goes straight to the robot queue. */
export function checkoutCart(): Order | null {
  const cart = cartStore.get()
  if (!cart.length) return null
  const sub = cart.reduce((n, c) => n + c.unit * c.qty, 0)
  const total = sub + (sub >= 500000 ? 0 : 30000)
  const first = cart[0]
  const product = PRODUCTS.find((p) => first.name === p.name)
  const paper = PAPERS.find((p) => p.name === first.paperName) ?? PAPERS[0]
  const order: Order = {
    id: createOrderId(),
    title: cart.length === 1 ? `${first.name} × ${first.qty * first.pack}` : `${cart.length} items`,
    detail: cart.map((c) => c.paperName).join(' · '),
    status: 'Queued',
    total,
    date: todayLabel(),
    staff: 'Minh · AI-VHRS Studio',
    spec: makeSpec({
      type: first.name, aspect: first.aspect, land: first.aspect === '220/110',
      paper: paper.name, paperColor: first.paperColor,
      ink: INKS[0].name, inkColor: product?.ink ?? INKS[0].color,
      font: first.font, fontName: 'Ready-made', text: first.text, qty: first.qty * first.pack,
    }),
  }
  addOrder(order)
  clearCart()
  return order
}

/** Wipe everything and go back to the seeded demo data. */
export function resetDemo() {
  ordersStore.set(seedOrders())
  cartStore.set([])
  userStore.set(DEMO_USER)
}
