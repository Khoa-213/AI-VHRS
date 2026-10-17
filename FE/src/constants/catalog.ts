import type { Layout, LayoutId } from '../types'

export interface Priced {
  id: string
  name: string
  price: number
}

export const PAPERS: (Priced & { spec: string; color: string })[] = [
  { id: 'ivory', name: 'Ivory', spec: '120 gsm · smooth', price: 0, color: '#f4eee0' },
  { id: 'cotton', name: 'Cotton rag', spec: '300 gsm · deckle edge', price: 18000, color: '#fbfaf5' },
  { id: 'kraft', name: 'Kraft', spec: '200 gsm · recycled', price: 8000, color: '#c9a77e' },
  { id: 'do', name: 'Giấy dó', spec: 'Handmade · Bắc Ninh', price: 25000, color: '#ebe0c8' },
]

export type MethodKind = 'qr' | 'wallet' | 'card'

export const PAY_METHODS: { id: string; name: string; spec: string; dot: string; kind: MethodKind }[] = [
  { id: 'vietqr', name: 'VietQR transfer', spec: 'Any banking app', dot: '#e31f26', kind: 'qr' },
  { id: 'vnpay', name: 'VNPay', spec: 'QR · ATM · Napas', dot: '#005baa', kind: 'wallet' },
  { id: 'momo', name: 'MoMo', spec: 'E-wallet', dot: '#a50064', kind: 'wallet' },
  { id: 'zalopay', name: 'ZaloPay', spec: 'E-wallet', dot: '#0068ff', kind: 'wallet' },
  { id: 'card', name: 'Card', spec: 'VISA · Mastercard · JCB', dot: '#fbbf24', kind: 'card' },
]

export const LAYOUTS: Layout[] = [
  { id: 'classic', name: 'Centered', alignItems: 'center', justify: 'center', textAlign: 'center', pad: '10cqw', frame: false },
  { id: 'framed', name: 'Framed', alignItems: 'center', justify: 'center', textAlign: 'center', pad: '14cqw', frame: true },
  { id: 'letter', name: 'Letter', alignItems: 'flex-start', justify: 'flex-start', textAlign: 'left', pad: '12cqw 10cqw', frame: false },
]

export const layoutById = (id?: LayoutId): Layout => LAYOUTS.find((l) => l.id === id) ?? LAYOUTS[0]

export const PRODUCTS = [
  { id: 'tet', type: 'card', name: 'Tết greeting card', text: 'Chúc Mừng Năm Mới', font: "'Dancing Script', cursive", size: 26, ink: '#9e2a1f', aspect: '105/148', base: 45000 },
  { id: 'wed', type: 'invite', name: 'Wedding invitation', text: 'Thu & Khang', font: "'Great Vibes', cursive", size: 30, ink: '#b08732', aspect: '127/178', base: 65000 },
  { id: 'thanks', type: 'card', name: 'Thank-you card', text: 'Cảm ơn bạn!', font: "'Dancing Script', cursive", size: 28, ink: '#1b2440', aspect: '105/148', base: 45000 },
  { id: 'print', type: 'letter', name: 'Calligraphy print', text: 'An Khang Thịnh Vượng', font: "'Great Vibes', cursive", size: 26, ink: '#141414', aspect: '148/210', base: 95000 },
  { id: 'letter', type: 'letter', name: 'Love letter', text: 'Gửi em, người thương…', font: "'Caveat', cursive", size: 22, ink: '#1b2440', aspect: '148/210', base: 85000 },
  { id: 'env', type: 'envelope', name: 'Addressed envelope', text: 'Cô Lan — 12 Lý Thường Kiệt', font: "'Caveat', cursive", size: 16, ink: '#141414', aspect: '220/110', base: 25000 },
]

export const PAYMENT_BADGES = [
  { name: 'VISA', dot: '#1a1f71' }, { name: 'Mastercard', dot: '#eb001b' }, { name: 'JCB', dot: '#0b8e36' },
  { name: 'ATM · Napas', dot: '#1b4f9c' }, { name: 'VietQR', dot: '#e31f26' }, { name: 'VNPay', dot: '#005baa' },
  { name: 'MoMo', dot: '#a50064' }, { name: 'ZaloPay', dot: '#0068ff' }, { name: 'ShopeePay', dot: '#ee4d2d' },
  { name: '0% installment', dot: '#4ade80' }, { name: 'Cash on delivery', dot: '#fbbf24' },
]

/** Status chip colours: [text, background], as theme tokens. */
export const STATUS_COLORS: Record<string, [string, string]> = {
  Sketching: ['var(--st-sketch)', 'var(--st-sketch-bg)'],
  Pending: ['var(--st-pending)', 'var(--st-pending-bg)'],
  Rejected: ['var(--danger)', 'transparent'],
  Accepted: ['var(--st-accepted)', 'var(--st-accepted-bg)'],
  Queued: ['var(--st-queued)', 'var(--st-queued-bg)'],
  Written: ['var(--st-written)', 'var(--st-written-bg)'],
  Rewriting: ['var(--st-rewriting)', 'var(--st-rewriting-bg)'],
  Shipped: ['var(--st-pending)', 'var(--st-pending-bg)'],
  Delivered: ['var(--st-written)', 'var(--st-written-bg)'],
}
