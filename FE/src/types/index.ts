/** Lifecycle of an order, in the order a customer sees it. */
export type OrderStatus =
  | 'Sketching'
  | 'Pending'
  | 'Accepted'
  | 'Queued'
  | 'Written'
  | 'Rewriting'
  | 'Shipped'
  | 'Delivered'

export type InputMode = 'text' | 'upload' | 'draw'

export type LayoutId = 'classic' | 'framed' | 'letter'

export interface Layout {
  id: LayoutId
  name: string
  alignItems: string
  justify: string
  textAlign: 'center' | 'left'
  pad: string
  frame: boolean
}

/** Everything the robot needs to know about one piece. */
export interface OrderSpec {
  type: string
  size: string
  aspect: string
  land: boolean
  mins: number
  paper: string
  paperColor: string
  pen: string
  penW: number
  ink: string
  inkColor: string
  font: string
  fontName: string
  mode: InputMode
  text: string
  img: string | null
  qty: number
}

export interface ShipTo {
  name: string
  phone: string
  street: string
  ward: string
  city: string
  note: string
}

export interface Order {
  id: string
  title: string
  detail: string
  status: OrderStatus
  total: number
  date: string
  spec: OrderSpec
  layout?: LayoutId
  note?: string
  staff?: string
  name?: string
  phone?: string
  address?: string
  pay?: string
  depositMethod?: string
  finalMethod?: string
  finalPaid?: number
  promo?: string | null
  shipTo?: ShipTo
  rewrites?: number
  rewriteReasons?: string[]
  rewriteNote?: string
}

export interface CartItem {
  key: string
  name: string
  text: string
  font: string
  aspect: string
  paperName: string
  paperColor: string
  pack: number
  unit: number
  qty: number
}

export interface User {
  name: string
}
