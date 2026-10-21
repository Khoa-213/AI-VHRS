import type { Gateway, Order, OrderStatus, Payment, PrivacyPolicy, Quotation } from './orders'

/**
 * Dev only (`npm run dev`): plays the workshop so the customer flow can be run before the backend can produce a sketch.
 * On any order you submitted, the "Dev: workshop" bar on the order page accepts it and finishes a fake sketch; from
 * there privacy, quotation and deposit run against this local state instead of the API. The real order is still
 * read from the API (code, inputs); only status, price and payments are overridden. `/orders/999999/review` is a
 * fully fake order for when there is no backend at all. State is kept in localStorage per order id.
 */
export const MOCK_ORDER_ID = 999999
const KEY = 'aivhrs-dev-mock'
/** Mock payment ids start here so they never collide with real ones. */
const PAY_BASE = 900000

interface State { status: OrderStatus; depositPct: number | null; total: number; payments: Payment[] }

const load = (): Record<string, State> => {
  try { return JSON.parse(localStorage.getItem(KEY) ?? '{}') as Record<string, State> } catch { return {} }
}
const save = (all: Record<string, State>) => {
  try { localStorage.setItem(KEY, JSON.stringify(all)) } catch { /* storage blocked: the mock just does not persist */ }
}
const get = (id: number): State | undefined => load()[id]
const put = (id: number, st: State) => save({ ...load(), [id]: st })

export const isMockOrder = (id: number) => import.meta.env.DEV && (id === MOCK_ORDER_ID || get(id) !== undefined)
/** The fully fake order, as opposed to a real order that the dev bar has taken over. */
export const isFakeOnly = (id: number) => id === MOCK_ORDER_ID

const iso = (d = 0) => new Date(Date.now() + d * 864e5).toISOString()
const FAKE_TOTAL = 220000

const state = (id: number): State => get(id) ?? { status: 'SUBMITTED', depositPct: null, total: FAKE_TOTAL, payments: [] }
const depositOf = (st: State) => (st.depositPct === null ? null : Math.round((st.total * st.depositPct) / 100))

const fakeBase = (): Order => ({
  id: MOCK_ORDER_ID, code: 'VH-MOCK-0001', type: 'OT3_TEMPLATE', status: 'SUBMITTED', production: 'NOT_STARTED',
  paperId: null, penId: null, inkId: null, workshopSuggest: true, quantity: 1, charCount: 24,
  estMin: 180000, estMax: 240000, total: null, depositPct: null, depositAmount: null,
  note: null, infoRequestNote: null, rejectReason: null, rejectNote: null, eta: null,
  savedAt: iso(), submittedAt: iso(), createdAt: iso(),
  inputs: [{
    id: 1, kind: 'TEXT_CONTENT', sortOrder: 0, mime: null, size: null, quality: null, rotation: 0, cropBox: null,
    qualityWarning: false, text: 'Cảm ơn bạn đã đồng hành cùng chúng tôi', templateId: null, fontSizeMm: null,
    alignment: null, canvas: null, fileUrl: null,
  }],
  warnings: [],
})

/** The order with the mock state laid over it. `real` is the order from the API, absent for the fully fake one. */
export const mockOrder = (id: number, real?: Order): Order => {
  const st = state(id)
  const base = real ?? fakeBase()
  const priced = st.depositPct !== null
  return {
    ...base, status: st.status, production: st.status === 'CONFIRMED' ? 'PENDING_SCHEDULE' : base.production,
    total: priced ? st.total : base.total, depositPct: st.depositPct, depositAmount: depositOf(st), eta: priced ? iso(10) : base.eta,
  }
}

// ---------- the workshop (played by the dev bar) ----------

export const MOCK_BAR_TITLE = 'Dev: workshop'
export const MOCK_RESET_LABEL = 'Restart the mock'

/** The one workshop step that is next, or null when the workshop has nothing to do. */
export const mockWorkshopStep = (id: number, realStatus: OrderStatus): { label: string } | null => {
  const st = get(id)
  if (!st) return realStatus === 'SUBMITTED' || isFakeOnly(id) ? { label: 'Workshop: accept the order' } : null
  if (st.status === 'SUBMITTED') return { label: 'Workshop: accept the order' }
  if (st.status === 'ACCEPTED') return { label: 'Workshop: finish the sketch' }
  return null
}

/** `price` is the order's own estimate when it has one, so the mock quotation looks like the order. */
export const mockAdvance = (id: number, price: number | null) => {
  const st = get(id) ?? { ...state(id), total: price ?? FAKE_TOTAL }
  if (st.status === 'SUBMITTED') put(id, { ...st, status: 'ACCEPTED' })
  else if (st.status === 'ACCEPTED') put(id, { ...st, status: 'AWAITING_PRIVACY' })
}
export const mockReset = (id: number) => {
  const all = load()
  delete all[id]
  save(all)
}

// ---------- privacy ----------

export const mockPolicy = (): PrivacyPolicy => ({
  version: '1.0',
  title: 'Chính sách quyền riêng tư',
  body: `Xưởng Nét Việt – AI-VHRS. Phiên bản 1.0, hiệu lực từ 01/11/2026.

Tại Xưởng Nét Việt, chúng tôi tôn trọng và cam kết bảo vệ thông tin cá nhân, hình ảnh, tài liệu và nét chữ mà Quý khách cung cấp.

### 1. Thông tin chúng tôi thu thập
- **Thông tin cá nhân:** Họ tên, email, số điện thoại và địa chỉ giao hàng.
- **Dữ liệu đơn hàng:** Hình ảnh, tài liệu PDF, mẫu chữ viết tay, nét vẽ và nội dung Quý khách cung cấp.
- **Dữ liệu xử lý:** Phác thảo, bộ nét chữ, dữ liệu vận hành robot và ảnh sản phẩm hoàn thành.
- **Thông tin giao dịch:** Mã giao dịch, số tiền, trạng thái thanh toán và lịch sử đơn hàng.

Chúng tôi không lưu số thẻ ngân hàng, mã bảo mật thẻ hoặc mật khẩu ví điện tử.

### 2. Mục đích sử dụng dữ liệu
- Xử lý yêu cầu, tạo phác thảo và báo giá.
- Phục dựng nét chữ và vận hành robot để tạo sản phẩm.
- Quản lý đơn hàng, thanh toán và giao nhận sản phẩm.
- Hỗ trợ khách hàng, xử lý khiếu nại và bảo đảm an toàn hệ thống.

**Cam kết:** Xưởng Nét Việt không sử dụng hình ảnh, tài liệu hoặc nét chữ của khách hàng để huấn luyện AI, nghiên cứu, quảng cáo hoặc bán cho bên thứ ba.

### 3. Bảo mật và chia sẻ thông tin
Chúng tôi áp dụng các biện pháp bảo vệ dữ liệu bao gồm kết nối HTTPS, phân quyền truy cập theo vai trò và ghi nhận lịch sử các thao tác quan trọng.

Dữ liệu chỉ được chia sẻ trong phạm vi cần thiết với nhân sự phụ trách, đơn vị thanh toán, vận chuyển, nhà cung cấp dịch vụ hỗ trợ hệ thống hoặc cơ quan có thẩm quyền theo quy định pháp luật.

### 4. Thời gian lưu trữ và xóa dữ liệu
- **Ảnh, tài liệu và nét chữ của đơn hàng:** Được xóa sau 90 ngày kể từ khi đơn hoàn tất.
- **Đơn hàng bị hủy:** Dữ liệu ảnh và nét chữ được xử lý xóa theo quy trình hủy đơn.
- **Bộ nét chữ được chọn lưu:** Được giữ để sử dụng cho các đơn tiếp theo đến khi Quý khách yêu cầu xóa.
- **Thông tin giao dịch và nhật ký:** Được lưu trong thời hạn cần thiết theo quy định pháp luật.

### 5. Quyền của Quý khách
Quý khách có quyền truy cập, chỉnh sửa, yêu cầu xóa, hạn chế xử lý dữ liệu hoặc rút lại sự đồng ý theo quy định của pháp luật Việt Nam.

### 6. Đồng ý và tiếp tục sử dụng dịch vụ
Bằng việc chọn "Đồng ý và xem phác thảo", Quý khách xác nhận đã đọc, hiểu và đồng ý với Chính sách quyền riêng tư này. Hệ thống sẽ ghi nhận thời điểm và phiên bản chính sách được chấp thuận.`,
})

export const mockDecidePrivacy = (id: number, accept: boolean) => {
  // Matches the backend today: accept goes on to the quotation, decline cancels the order.
  put(id, { ...state(id), status: accept ? 'QUOTED' : 'CANCELLED' })
}

export const mockCancel = (id: number) => put(id, { ...state(id), status: 'CANCELLED' })

// ---------- fake sketch and quotation ----------

/** A sheet of paper with a few handwritten-looking lines, as an image link. */
const sketchSvg = () => {
  const line = (y: number, d: string) => `<path d="${d}" fill="none" stroke="#1b2a4a" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" transform="translate(0 ${y})"/>`
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="560" height="360" viewBox="0 0 560 360">
<rect width="560" height="360" fill="#fbf8f1"/>
${line(90, 'M40 40 q20-40 40 0 t40 0 t40 0 t40 0 t40 0 t40 0 t40 0 t40 0 t40 0')}
${line(150, 'M40 40 q15-30 30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0 t30 0')}
${line(210, 'M40 40 q25-34 50 0 t50 0 t50 0 t50 0 t50 0 t50 0 t50 0 t50 0')}
</svg>`
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`
}

export const mockQuotation = (id: number): Quotation => {
  const total = state(id).total
  const service = Math.round(total * 0.82)
  return {
    id: 1, version: 1, status: 'SENT',
    lines: [
      { option: 1, item: 'Handwriting service', calc: '', amount: service },
      { option: 1, item: 'Paper and ink', calc: '', amount: total - service },
    ],
    options: [], chosenOption: null, charCount: 24, quantity: 1, finalTotal: total, minDepositPct: 50,
    eta: iso(10), validUntil: iso(7), pdfUrl: null, note: 'Mock quotation.',
    sketch: { version: 1, previewUrls: [sketchSvg()], approachNote: 'Mock sketch: a steady upright hand.', estimatedWritingSec: 600, similarity: null },
  }
}

export const mockApprove = (id: number, pct: number | undefined) =>
  put(id, { ...state(id), depositPct: Math.min(100, Math.max(50, pct ?? 50)), status: 'AWAITING_DEPOSIT' })

// ---------- deposit ----------

export const isMockPayment = (paymentId: number) => import.meta.env.DEV && paymentId >= PAY_BASE

export const mockStartDeposit = (id: number, gateway: Gateway): Payment => {
  const st = state(id)
  const p: Payment = { id: PAY_BASE + id * 10 + st.payments.length, amount: depositOf(st) ?? 0, status: 'PENDING', gateway, mode: 'MOCK', needsRefund: false, createdAt: iso() }
  put(id, { ...st, payments: [...st.payments, p] })
  return p
}

export const mockCheckoutResult = (paymentId: number, result: 'SUCCESS' | 'FAILED') => {
  const all = load()
  for (const [key, st] of Object.entries(all)) {
    const p = st.payments.find((x) => x.id === paymentId)
    if (!p) continue
    p.status = result === 'SUCCESS' ? 'SUCCESS' : 'FAILED'
    if (result === 'SUCCESS') st.status = 'CONFIRMED'
    save(all)
    return { result, status: p.status, order_status: st.status, order: Number(key) }
  }
  return { result, status: result, order_status: 'AWAITING_DEPOSIT' as OrderStatus, order: 0 }
}

export const mockPayments = (id: number): Payment[] => state(id).payments
