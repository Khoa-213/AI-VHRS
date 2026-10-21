import { MOCK_BAR_TITLE, MOCK_RESET_LABEL, isMockOrder, mockAdvance, mockReset, mockWorkshopStep } from '../../services/mockOrder'
import type { Order } from '../../services/orders'

/**
 * Dev only: plays the workshop for an order you submitted, so privacy, quotation and deposit can be run
 * without a backend that produces sketches. Shown on SUBMITTED orders and on orders already taken over.
 */
export default function MockWorkshopBar({ order, onChange }: { order: Order; onChange: () => void }) {
  const step = mockWorkshopStep(order.id, order.status)
  const taken = isMockOrder(order.id)
  if (!step && !taken) return null
  return (
    <div style={{ position: 'fixed', left: 16, bottom: 16, zIndex: 50, display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', border: '1px dashed var(--line-strong)', borderRadius: 12, background: 'var(--surface, var(--bg))', color: 'var(--t1)', fontSize: 12 }}>
      <b>{MOCK_BAR_TITLE}</b>
      {step && (
        <button className="vh-btn vh-btn--primary vh-btn--md" onClick={() => { mockAdvance(order.id, order.estMax ?? order.estMin); onChange() }}>
          {step.label}
        </button>
      )}
      {taken && <button className="vh-link" onClick={() => { mockReset(order.id); onChange() }}>{MOCK_RESET_LABEL}</button>}
    </div>
  )
}
