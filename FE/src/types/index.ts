/** Lifecycle of an order, in the order a customer sees it. */
export type OrderStatus =
  | 'Sketching'
  | 'Pending'
  | 'Rejected'
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
  /** Demo only: original file name and the text a photo or drawing reads as. */
  fileName?: string
  simText?: string
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
  /** Staff console: where the order is in staff review, plus what staff recorded. */
  staffStage?: 'input' | 'sketch'
  ocrText?: string
  evalScore?: number
  rejectReasons?: string[]
  regen?: number
  /** Technician and robot staff picked after accepting the order. */
  assignment?: Assignment
  /** Set when a technician starts the real robot. Cleared when the order is marked written. */
  run?: RobotRun
  /** Photo and QC result sent to the customer. */
  qc?: QcReport
  /** Set when QC failed and the order went back to the robot queue. */
  qcFail?: { reasons: string[]; note: string; at: string }
  /** True for the sample orders the staff console seeds for itself. */
  demo?: boolean
}

export interface QcPhoto {
  slot: string
  /** Downscaled JPEG data URL. */
  url: string
}

/** What the technician recorded at photo and QC, and what the customer is sent. */
export interface QcReport {
  checked: string[]
  total: number
  photos: QcPhoto[]
  note: string
  by: string
  at: string
}

export interface RobotRun {
  robotId: string
  startedAt: number
  /** Prototype only: how long the simulated run lasts. */
  seconds: number
}

export interface Assignment {
  techId: string
  techName: string
  robotId: string
  at: string
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

export type Role = 'customer' | 'staff' | 'technician'

export interface User {
  name: string
  role: Role
  /** Roster id of a technician account (T-01 ...). */
  techId?: string
}
