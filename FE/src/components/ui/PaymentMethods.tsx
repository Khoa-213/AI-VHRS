import { PAY_METHODS } from '../../constants/catalog'
import { MethodLogos } from './PaymentLogos'

export interface CardFields {
  no: string
  exp: string
  cvc: string
}

export const EMPTY_CARD: CardFields = { no: '', exp: '', cvc: '' }

/** True when the chosen method has everything it needs to pay. */
export function methodReady(methodId: string | null, card: CardFields) {
  const m = PAY_METHODS.find((x) => x.id === methodId)
  if (!m) return false
  if (m.kind === 'card') {
    return (
      card.no.replace(/\D/g, '').length >= 15 &&
      /^\d{2}\s*\/\s*\d{2}$/.test(card.exp.trim()) &&
      /^\d{3,4}$/.test(card.cvc)
    )
  }
  return true
}

interface PaymentMethodsProps {
  method: string | null
  onPick: (id: string) => void
  card: CardFields
  onCard: (card: CardFields) => void
  orderId: string
  /** Transfer note suffix, e.g. COC for deposit or TT for the final payment. */
  noteSuffix: string
  amountLabel: string
}

/** Method grid plus the detail panel for the selected method. */
export default function PaymentMethods({ method, onPick, card, onCard, orderId, noteSuffix, amountLabel }: PaymentMethodsProps) {
  const m = PAY_METHODS.find((x) => x.id === method)
  return (
    <>
      <div className="vh-choice-grid vh-choice-grid--170">
        {PAY_METHODS.map((x) => (
          <button key={x.id} className={`vh-choice${x.id === method ? ' on' : ''}`} onClick={() => onPick(x.id)}>
            <MethodLogos id={x.id} />
            <span className="vh-choice-name">{x.name}</span>
            <span className="vh-choice-sub">{x.spec}</span>
          </button>
        ))}
      </div>

      {m?.kind === 'qr' && (
        <div className="vh-qr">
          <div className="vh-qr-box">
            <span className="vh-qr-title">VietQR</span>
            <span className="vh-qr-sub">QR generated at checkout</span>
          </div>
          <div className="vh-qr-rows">
            <div><span>Bank</span><b>Vietcombank</b></div>
            <div><span>Account</span><b className="vh-mono">0071 0023 4567</b></div>
            <div><span>Name</span><b>CTY AI-VHRS</b></div>
            <div><span>Transfer note</span><b className="vh-mono vh-accent">{orderId} {noteSuffix}</b></div>
          </div>
        </div>
      )}

      {m?.kind === 'card' && (
        <div className="vh-card-grid">
          <input
            className="vh-input vh-mono vh-span2"
            placeholder="Card number"
            aria-label="Card number"
            inputMode="numeric"
            value={card.no}
            onChange={(e) => onCard({ ...card, no: e.target.value.replace(/[^\d ]/g, '').slice(0, 23) })}
          />
          <input
            className="vh-input vh-mono"
            placeholder="MM / YY"
            aria-label="Expiry date"
            value={card.exp}
            onChange={(e) => onCard({ ...card, exp: e.target.value.slice(0, 7) })}
          />
          <input
            className="vh-input vh-mono"
            placeholder="CVC"
            aria-label="Security code"
            inputMode="numeric"
            value={card.cvc}
            onChange={(e) => onCard({ ...card, cvc: e.target.value.replace(/\D/g, '').slice(0, 4) })}
          />
        </div>
      )}

      {m?.kind === 'wallet' && (
        <p className="vh-callout-plain">
          You’ll be redirected to {m.name} to confirm {amountLabel}, then brought back here.
        </p>
      )}
    </>
  )
}
