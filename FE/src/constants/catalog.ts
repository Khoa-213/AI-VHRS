import type { InputMode, Layout, LayoutId } from '../types'

export interface OrderType {
  id: string
  name: string
  size: string
  base: number
  mins: number
  w: number
  h: number
  aspect: string
  land: boolean
}

export const TYPES: OrderType[] = [
  { id: 'card', name: 'Greeting card', size: 'A6 · 105×148 mm', base: 45000, mins: 4, w: 46, h: 64, aspect: '105/148', land: false },
  { id: 'letter', name: 'Handwritten letter', size: 'A5 · 148×210 mm', base: 85000, mins: 9, w: 50, h: 70, aspect: '148/210', land: false },
  { id: 'envelope', name: 'Addressed envelope', size: 'DL · 220×110 mm', base: 25000, mins: 2, w: 78, h: 39, aspect: '220/110', land: true },
  { id: 'invite', name: 'Wedding invitation', size: '127×178 mm', base: 65000, mins: 6, w: 44, h: 62, aspect: '127/178', land: false },
]

export const MODES: { id: InputMode; label: string; desc: string }[] = [
  { id: 'text', label: 'Type text', desc: 'Single-line calligraphy fonts' },
  { id: 'upload', label: 'Upload image', desc: 'Photo or scan · AI vectorization · +30.000₫' },
  { id: 'draw', label: 'Write it yourself', desc: 'Live canvas · AI learns your style · +15.000₫' },
]

export const FONT_STYLES = [
  { id: 'script', name: 'Script', font: "'Dancing Script', cursive" },
  { id: 'formal', name: 'Formal', font: "'Great Vibes', cursive" },
  { id: 'casual', name: 'Casual', font: "'Caveat', cursive" },
]

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

export const PENS: (Priced & { spec: string; w: number })[] = [
  { id: 'fountain', name: 'Fountain pen', spec: '0.5 mm fine nib', price: 0, w: 2 },
  { id: 'gel', name: 'Gel pen', spec: '0.7 mm · quick dry', price: 0, w: 3 },
  { id: 'italic', name: 'Calligraphy nib', spec: '2.0 mm italic', price: 12000, w: 5 },
  { id: 'brush', name: 'Brush pen', spec: 'Flexible tip', price: 15000, w: 8 },
]

export const INKS: (Priced & { color: string })[] = [
  { id: 'navy', name: 'Midnight blue', price: 0, color: '#1b2440' },
  { id: 'black', name: 'Carbon black', price: 0, color: '#141414' },
  { id: 'sepia', name: 'Sepia', price: 5000, color: '#6b3f22' },
  { id: 'red', name: 'Lacquer red', price: 5000, color: '#9e2a1f' },
  { id: 'gold', name: 'Metallic gold', price: 20000, color: '#b08732' },
]

export const CREATE_PAYS = [
  { id: 'vnpay', name: 'VNPay', spec: 'QR · ATM · Visa' },
  { id: 'momo', name: 'MoMo', spec: 'E-wallet' },
  { id: 'cod', name: 'Cash on delivery', spec: 'Pay when it arrives' },
]

export const STEP_LABELS = ['Order type', 'Content', 'Materials', 'Review']

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

export const CITIES = [
  'TP. Hồ Chí Minh', 'Hà Nội', 'Đà Nẵng', 'Hải Phòng', 'Cần Thơ',
  'Huế', 'Khánh Hòa', 'Bình Dương', 'Đồng Nai', 'Other',
]

export const PROMOS: Record<string, { label: string; kind: 'pct' | 'ship'; v?: number }> = {
  VHRS10: { label: '10% off balance', kind: 'pct', v: 0.1 },
  FREESHIP: { label: 'Free shipping', kind: 'ship' },
}

export const REWRITE_REASONS = ['Ink smudge', 'Uneven spacing', 'Stroke quality', 'Wrong content', 'Other']

export const PRODUCTS = [
  { id: 'tet', name: 'Tết greeting card', text: 'Chúc Mừng Năm Mới', font: "'Dancing Script', cursive", size: 26, ink: '#9e2a1f', aspect: '105/148', base: 45000 },
  { id: 'wed', name: 'Wedding invitation', text: 'Thu & Khang', font: "'Great Vibes', cursive", size: 30, ink: '#b08732', aspect: '127/178', base: 65000 },
  { id: 'thanks', name: 'Thank-you card', text: 'Cảm ơn bạn!', font: "'Dancing Script', cursive", size: 28, ink: '#1b2440', aspect: '105/148', base: 45000 },
  { id: 'print', name: 'Calligraphy print', text: 'An Khang Thịnh Vượng', font: "'Great Vibes', cursive", size: 26, ink: '#141414', aspect: '148/210', base: 95000 },
  { id: 'letter', name: 'Love letter', text: 'Gửi em, người thương…', font: "'Caveat', cursive", size: 22, ink: '#1b2440', aspect: '148/210', base: 85000 },
  { id: 'env', name: 'Addressed envelope', text: 'Cô Lan — 12 Lý Thường Kiệt', font: "'Caveat', cursive", size: 16, ink: '#141414', aspect: '220/110', base: 25000 },
]

export const PACKS = [
  { n: 1, label: '1 pc', mult: 1 },
  { n: 10, label: '10 pcs', mult: 9 },
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
  Accepted: ['var(--st-accepted)', 'var(--st-accepted-bg)'],
  Queued: ['var(--st-queued)', 'var(--st-queued-bg)'],
  Written: ['var(--st-written)', 'var(--st-written-bg)'],
  Rewriting: ['var(--st-rewriting)', 'var(--st-rewriting-bg)'],
  Shipped: ['var(--st-pending)', 'var(--st-pending-bg)'],
  Delivered: ['var(--st-written)', 'var(--st-written-bg)'],
}
