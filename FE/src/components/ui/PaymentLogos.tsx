import type { ReactNode } from 'react'
import visa from '../../assets/payment/visa.svg'
import mastercard from '../../assets/payment/mastercard.svg'
import jcb from '../../assets/payment/jcb.svg'
import vietqr from '../../assets/payment/vietqr.svg'
import momo from '../../assets/payment/momo.svg'
import zalopay from '../../assets/payment/zalopay.svg'

/** Official logo files. Methods without one (Napas, VNPay, ShopeePay, ...) fall back to the drawn marks below. */
const FILES: Record<string, string> = { VISA: visa, Mastercard: mastercard, JCB: jcb, VietQR: vietqr, MoMo: momo, ZaloPay: zalopay }

/** Simplified brand marks for the supported payment methods, drawn on a 64x40 canvas. */
const FONT = "'Inter','Segoe UI',Arial,sans-serif"

const LOGOS: Record<string, ReactNode> = {
  VISA: (
    <text x="32" y="26" textAnchor="middle" fontFamily={FONT} fontSize="17" fontWeight="900" fontStyle="italic" fill="#1a1f71" letterSpacing="-.5">VISA</text>
  ),
  Mastercard: (
    <>
      <circle cx="26" cy="20" r="9" fill="#eb001b" />
      <circle cx="38" cy="20" r="9" fill="#f79e1b" />
      <path d="M32 12.6a9 9 0 0 1 0 14.8 9 9 0 0 1 0-14.8z" fill="#ff5f00" />
    </>
  ),
  JCB: (
    <>
      <rect x="12" y="9" width="12" height="22" rx="4" fill="#0e4c96" />
      <rect x="26" y="9" width="12" height="22" rx="4" fill="#e20138" />
      <rect x="40" y="9" width="12" height="22" rx="4" fill="#007940" />
      <g fontFamily={FONT} fontSize="11" fontWeight="900" fill="#fff" textAnchor="middle">
        <text x="18" y="24">J</text><text x="32" y="24">C</text><text x="46" y="24">B</text>
      </g>
    </>
  ),
  'ATM · Napas': (
    <>
      <rect x="8" y="10" width="48" height="20" rx="3" fill="#1b4f9c" />
      <text x="32" y="24" textAnchor="middle" fontFamily={FONT} fontSize="11" fontWeight="800" fill="#fff">ATM</text>
    </>
  ),
  VietQR: (
    <>
      <g fill="#1d1d1b">
        <rect x="14" y="8" width="10" height="10" rx="1.5" /><rect x="40" y="8" width="10" height="10" rx="1.5" />
        <rect x="14" y="22" width="10" height="10" rx="1.5" />
        <rect x="28" y="8" width="6" height="6" /><rect x="28" y="18" width="8" height="6" /><rect x="40" y="22" width="4" height="4" />
        <rect x="46" y="26" width="4" height="6" /><rect x="30" y="28" width="6" height="4" />
      </g>
      <g fill="#fff"><rect x="17" y="11" width="4" height="4" /><rect x="43" y="11" width="4" height="4" /><rect x="17" y="25" width="4" height="4" /></g>
    </>
  ),
  VNPay: (
    <text x="32" y="25" textAnchor="middle" fontFamily={FONT} fontSize="14" fontWeight="900" letterSpacing="-.3">
      <tspan fill="#e31f26">VN</tspan><tspan fill="#005baa">PAY</tspan>
    </text>
  ),
  MoMo: (
    <>
      <rect x="20" y="8" width="24" height="24" rx="5" fill="#a50064" />
      <text x="32" y="25" textAnchor="middle" fontFamily={FONT} fontSize="11" fontWeight="900" fill="#fff">mo</text>
    </>
  ),
  ZaloPay: (
    <text x="32" y="25" textAnchor="middle" fontFamily={FONT} fontSize="12" fontWeight="900" letterSpacing="-.3">
      <tspan fill="#0068ff">zalo</tspan><tspan fill="#00c26e">pay</tspan>
    </text>
  ),
  ShopeePay: (
    <>
      <rect x="20" y="8" width="24" height="24" rx="5" fill="#ee4d2d" />
      <text x="32" y="25" textAnchor="middle" fontFamily={FONT} fontSize="9.5" fontWeight="900" fill="#fff">Pay</text>
    </>
  ),
  '0% installment': (
    <>
      <text x="32" y="26" textAnchor="middle" fontFamily={FONT} fontSize="18" fontWeight="900" fill="#222">0%</text>
      <path d="M12 31h40" stroke="#222" strokeWidth="2" strokeLinecap="round" />
    </>
  ),
  'Cash on delivery': (
    <>
      <rect x="10" y="11" width="44" height="18" rx="3" fill="none" stroke="#222" strokeWidth="2.2" />
      <circle cx="32" cy="20" r="5" fill="none" stroke="#222" strokeWidth="2.2" />
      <circle cx="17" cy="20" r="1.6" fill="#222" /><circle cx="47" cy="20" r="1.6" fill="#222" />
    </>
  ),
}

/** One logo on its white tile; unknown names render nothing. */
export function PayLogo({ name }: { name: string }) {
  if (!FILES[name] && !LOGOS[name]) return null
  return (
    <span className="pl-tile" title={name}>
      {FILES[name]
        ? <img src={FILES[name]} alt={name} />
        : <svg viewBox="0 0 64 40" role="img" aria-label={name}>{LOGOS[name]}</svg>}
    </span>
  )
}

const LOGO_NAMES_BY_ID: Record<string, string[]> = {
  vietqr: ['VietQR'],
  vnpay: ['VNPay'],
  momo: ['MoMo'],
  zalopay: ['ZaloPay'],
  card: ['VISA', 'Mastercard', 'JCB'],
  cod: ['Cash on delivery'],
}

/** Logo(s) for a payment method id used in the order flows. */
export function MethodLogos({ id }: { id: string }) {
  const names = LOGO_NAMES_BY_ID[id]
  if (!names) return null
  return <span className="pl-row">{names.map((n) => <PayLogo key={n} name={n} />)}</span>
}

export default function PaymentLogos({ names }: { names: string[] }) {
  return (
    <ul className="ct-logos">
      {names.map((name) => (
        <li key={name}><PayLogo name={name} /></li>
      ))}
    </ul>
  )
}
