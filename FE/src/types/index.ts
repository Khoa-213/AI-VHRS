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
  /** Packing and courier tracking, filled in once the customer has paid. */
  shipment?: Shipment
  /** True for the sample orders the staff console seeds for itself. */
  demo?: boolean
}

/** Order statuses reported by GHN (order detail and webhook). */
export type GhnStatus =
  | 'ready_to_pick'
  | 'picking'
  | 'picked'
  | 'storing'
  | 'transporting'
  | 'sorting'
  | 'delivering'
  | 'delivered'
  | 'delivery_fail'
  | 'waiting_to_return'
  | 'return'
  | 'return_transporting'
  | 'return_sorting'
  | 'returning'
  | 'returned'
  | 'cancel'
  | 'exception'
  | 'damage'
  | 'lost'

/** One scan from GHN. */
export interface ShipLog {
  status: GhnStatus
  /** ISO time of the scan. */
  at: string
  place?: string
}

export interface Shipment {
  /** Packing steps staff have ticked, with the time each was done. */
  pack: { id: string; at: string }[]
  weightG: number
  /** Cash the courier collects on delivery. The prototype takes payment online, so this is 0. */
  codAmount: number
  /** GHN order code, set once staff books the courier. */
  ghnCode?: string
  bookedAt?: string
  fee?: number
  expectedAt?: string
  /** Scans from GHN, oldest first. */
  logs: ShipLog[]
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

/** Account details a customer keeps on their profile page. */
export interface Profile {
  fullName: string
  email: string
  phone: string
  address: string
  bio: string
  /** Small JPEG data URL. */
  avatar: string | null
  /** Payment method id from PAY_METHODS that checkout preselects. */
  payMethod: string | null
}

/** A create-order form saved part way. Kept per user and updated on every change. */
export interface OrderDraft {
  id: string
  /** Name of the user it belongs to. Drafts started signed out use "guest" until sign in. */
  owner: string
  createdAt: string
  updatedAt: string
  /** Step the user is on (0 to 3) and the furthest step they have reached. */
  step: number
  maxStep: number
  type: string | null
  mode: InputMode
  text: string
  fontStyle: string
  /** Uploaded handwriting photo. Only the data URL survives a reload. */
  upload: { name: string; isImg: boolean; dataUrl?: string } | null
  strokes: number
  drawUrl: string | null
  sizeId: string
  landscape: boolean
  paper: string | null
  pen: string | null
  ink: string | null
  qty: number
  name: string
  phone: string
  address: string
  pay: string | null
}

export type Role = 'customer' | 'staff' | 'technician'

export interface User {
  name: string
  role: Role
  /** Roster id of a technician account (T-01 ...). */
  techId?: string
}
