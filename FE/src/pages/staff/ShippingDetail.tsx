import { ArrowLeft, ArrowUpRight, ArrowsClockwise, FastForward } from '@phosphor-icons/react'
import { useState } from 'react'
import SkipLink from '../../components/ui/SkipLink'
import ShipmentTimeline from '../../components/ui/ShipmentTimeline'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
import { useLocale, useT } from '../../i18n'
import { useShipmentSync } from '../../hooks/useShipmentSync'
import {
  GHN_LIVE, PACK_STEPS, bookShipment, isFinal, lastLog, packed, shipmentOf, stageChip, stageOf, trackingUrl,
} from '../../services/ghn'
import { Link } from '../../router/router'
import {
  advanceCourier, saveBooking, setParcelWeight, togglePackStep, useAllStaffOrders, usePrototypeMode,
} from '../../store/store'
import { fmt } from '../../utils/format'
import StaffRail from './StaffRail'
import './dashboard.css'
import './polish.css'
import './shipping.css'

export default function ShippingDetail({ id }: { id: string }) {
  const order = useAllStaffOrders().find((o) => o.id === id)
  const t = useT()
  const locale = useLocale()
  const when = (iso?: string) =>
    iso ? new Date(iso).toLocaleString(locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }) : t('sp.notSet')
  const sync = useShipmentSync(order ?? null)
  const proto = usePrototypeMode()
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  const shell = (children: React.ReactNode) => (
    <div className="sd">
      <SkipLink />
      <StaffRail active="shipping" />
      <main className="sd-body" id="main">{children}</main>
    </div>
  )

  if (!order || !['Shipped', 'Delivered'].includes(order.status)) {
    return shell(
      <div className="sp-body">
        <div className="sd-empty">
          <b>{t(order ? 'sp.notReady' : 'sp.notFound')}</b>
          <span>
            {order
              ? t('sp.notReadyBody', { id: order.id, status: t(`status.${order.status}`) })
              : t('sp.notFoundBody', { id })}
          </span>
          <Link to="/staff/shipping" className="sd-btn sp-self-start">{t('sp.backToBoard')}</Link>
        </div>
      </div>,
    )
  }

  const s = shipmentOf(order)
  const stage = stageOf(order)
  const chip = stageChip(order)
  const last = lastLog(s)
  const booked = !!s.ghnCode
  const ready = packed(s)
  const finished = !!last && isFinal(last.status)
  const to = order.shipTo
  const address = [to?.street, to?.ward, to?.city].filter(Boolean).join(', ') || order.address || t('sp.noAddress')

  const book = async () => {
    if (busy || !ready || booked) return
    setBusy(true)
    setErr(null)
    try {
      const b = await bookShipment(order, s.weightG)
      saveBooking(order.id, b)
      if (!GHN_LIVE) advanceCourier(order.id)
    } catch (e) {
      setErr(e instanceof Error ? e.message : t('sp.bookErr'))
    } finally {
      setBusy(false)
    }
  }

  return shell(
    <>
      <header className="sd-top">
        <div>
          <Link to="/staff/shipping" className="sp-back"><ArrowLeft size={16} aria-hidden /> {t('sp.back')}</Link>
          <h1>{order.title}</h1>
          <p>{order.id} · {to?.name || order.name || t('sp.customer')} · {to?.phone || order.phone || t('sp.noPhone')}</p>
        </div>
        <div className="sd-top-right">
          <span className="vh-chip" style={{ color: chip.color }}>{t(chip.key)}</span>
          <ThemeToggle className="vh-icon-btn" />
          <LanguageToggle className="vh-icon-btn" />
        </div>
      </header>

      <div className="sp-body sp-two">
        <div className="sp-col">
          <section className="sd-card" aria-labelledby="sp-pack">
            <div className="sd-card-head">
              <h2 id="sp-pack">{t('sp.packing')}</h2>
              <span className="sd-tag">{t('sp.nOfTotal', { n: s.pack.length, total: PACK_STEPS.length })}</span>
            </div>
            <ul className="sp-checks">
              {PACK_STEPS.map((p) => {
                const done = s.pack.some((m) => m.id === p.id)
                return (
                  <li key={p.id}>
                    <label className={done ? 'done' : ''}>
                      <input
                        type="checkbox"
                        checked={done}
                        disabled={booked || order.status === 'Delivered'}
                        onChange={() => togglePackStep(order.id, p.id)}
                      />
                      <span>{t(`pack.${p.id}`)}</span>
                    </label>
                  </li>
                )
              })}
            </ul>
          </section>

          <section className="sd-card" aria-labelledby="sp-courier">
            <div className="sd-card-head">
              <h2 id="sp-courier">{t('sp.courier')}</h2>
              {booked && <span className="sd-tag vh-mono">{s.ghnCode}</span>}
            </div>

            <dl className="sp-facts">
              <div><dt>{t('sp.deliverTo')}</dt><dd>{to?.name || order.name || t('sp.customer')}</dd></div>
              <div><dt>{t('sp.address')}</dt><dd>{address}</dd></div>
              {to?.note && <div><dt>{t('sp.courierNote')}</dt><dd>{to.note}</dd></div>}
              <div><dt>{t('sp.cod')}</dt><dd className="vh-mono">{fmt(s.codAmount)}</dd></div>
              {booked && <div><dt>{t('sp.fee')}</dt><dd className="vh-mono">{fmt(s.fee ?? 0)}</dd></div>}
              {booked && <div><dt>{t('sp.booked')}</dt><dd>{when(s.bookedAt)}</dd></div>}
              {booked && <div><dt>{t('sp.expected')}</dt><dd>{when(s.expectedAt)}</dd></div>}
            </dl>

            <div className="sp-weight">
              <label htmlFor="sp-w">{t('sp.weight')}</label>
              <input
                id="sp-w"
                className="vh-input"
                type="number"
                inputMode="numeric"
                min={1}
                value={s.weightG}
                disabled={booked}
                onChange={(e) => setParcelWeight(order.id, Number(e.target.value))}
              />
            </div>

            {!booked && order.status === 'Shipped' && (
              <>
                <button type="button" className="sd-btn sp-primary" disabled={!ready || busy} onClick={book}>
                  {t(busy ? 'sp.booking' : 'sp.book')}
                </button>
                {!ready && <p className="sd-note">{t('sp.finishPack')}</p>}
                {err && <p className="sp-error" role="alert">{err}</p>}
              </>
            )}

            {booked && (
              <a className="sd-btn sp-self-start" href={trackingUrl(s.ghnCode!)} target="_blank" rel="noreferrer">
                {t('sp.openGhn')} <ArrowUpRight size={16} aria-hidden />
              </a>
            )}
          </section>
        </div>

        <section className="sd-card" aria-labelledby="sp-log">
          <div className="sd-card-head">
            <h2 id="sp-log">{t('sp.activity')}</h2>
            {GHN_LIVE ? (
              <button type="button" className="sp-ghost" onClick={() => void sync.refresh()} disabled={!booked || sync.busy}>
                <ArrowsClockwise size={16} aria-hidden /> {t(sync.busy ? 'sp.refreshing' : 'sp.refresh')}
              </button>
            ) : (
              <span className="sd-tag">{t('sp.simCourier')}</span>
            )}
          </div>

          <ShipmentTimeline shipment={s} audience="staff" />

          {GHN_LIVE && sync.syncedAt && <p className="sd-note">{t('sp.lastSync', { time: sync.syncedAt.toLocaleTimeString(locale) })}</p>}
          {sync.error && <p className="sp-error" role="alert">{t('sp.syncErr', { msg: sync.error })}</p>}

          {!GHN_LIVE && proto && booked && order.status === 'Shipped' && (
            <div className="sp-sim">
              <button type="button" className="sp-ghost" disabled={finished} onClick={() => advanceCourier(order.id)}>
                <FastForward size={16} aria-hidden /> {t('sp.simNext')}
              </button>
              <span className="sd-note">{t('sp.simNote')}</span>
            </div>
          )}
          {stage === 'problem' && (
            <p className="sd-note">{t('sp.problemNote')}</p>
          )}
        </section>
      </div>
    </>,
  )
}
