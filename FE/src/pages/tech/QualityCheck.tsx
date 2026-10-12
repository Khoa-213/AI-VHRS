import { useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowsClockwise, Camera, Check, PaperPlaneTilt, Warning, X } from '@phosphor-icons/react'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import { Link } from '../../router/router'
import { failQc, finishRobotRun, submitQc, useAllStaffOrders, usePrototypeMode, useUser } from '../../store/store'
import type { QcPhoto } from '../../types'
import { MODE_LABEL } from '../staff/evaluate'
import { PHOTO_SLOTS, QC_FAIL_REASONS, qcGroups } from './qcItems'
import { runDone, samplePhoto, shrinkImage, useNow } from './phase'
import TechRail from './TechRail'
import '../staff/dashboard.css'
import '../staff/staff.css'
import '../staff/polish.css'
import './tech.css'
import './qc.css'

export default function QualityCheck({ id }: { id: string }) {
  const user = useUser()
  const orders = useAllStaffOrders()
  const now = useNow(1000)
  const prototype = usePrototypeMode()
  const order = orders.find((o) => o.id === id)

  const [ticked, setTicked] = useState<Record<string, boolean>>({})
  const [photos, setPhotos] = useState<Record<string, string>>({})
  const [note, setNote] = useState('')
  const [confirm, setConfirm] = useState(false)
  const [tab, setTab] = useState<'qc' | 'photos'>('qc')
  const [failing, setFailing] = useState(false)
  const [reasons, setReasons] = useState<string[]>([])
  const [failNote, setFailNote] = useState('')
  const [error, setError] = useState('')
  const [sent, setSent] = useState<'ok' | 'failed' | null>(null)
  const inputs = useRef<Record<string, HTMLInputElement | null>>({})

  const groups = useMemo(() => (order ? qcGroups(order) : []), [order])
  const all = groups.flatMap((g) => g.items)
  const done = all.filter((i) => ticked[i.id]).length

  const shell = (body: React.ReactNode) => (
    <div className="sd">
      <SkipLink />
      <TechRail active="qc" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{order ? `Photo and QC for ${order.id}` : 'Photo and QC'}</h1>
            <p>{order ? `${order.title} for ${order.name || 'the customer'}` : 'Order not found'}</p>
          </div>
          <div className="sd-top-right">
            <Link to="/tech/qc" className="sd-btn">Choose another order</Link>
            <ThemeToggle className="vh-icon-btn" />
          </div>
        </header>
        {body}
      </main>
    </div>
  )

  if (!order) {
    return shell(
      <section className="sd-card"><div className="sd-empty"><b>Order not found</b><span>There is no order {id}.</span></div></section>,
    )
  }
  const asg = order.assignment
  if (!asg || asg.techId !== user?.techId) {
    return shell(
      <section className="sd-card">
        <div className="sd-empty">
          <b>Not your order</b>
          <span>{asg ? `${order.id} belongs to ${asg.techName}.` : `${order.id} has no technician yet.`}</span>
        </div>
      </section>,
    )
  }
  if (!sent && !runDone(order, now)) {
    return shell(
      <section className="sd-card">
        <div className="sd-empty">
          <b>{order.run ? 'The robot is still writing' : 'This order has not been written yet'}</b>
          <span>Photo and QC opens once the FR3 has finished the run.</span>
          <Link to={`/tech/preview/${encodeURIComponent(order.id)}`} className="vh-link">Open the simulator</Link>
          {prototype && order.run && (
            <button className="vh-btn vh-btn--ghost vh-btn--sm sc-self-start" onClick={() => finishRobotRun(order.id)}>
              Prototype: finish the run now
            </button>
          )}
        </div>
      </section>,
    )
  }

  const sp = order.spec
  const missingPhotos = PHOTO_SLOTS.filter((s) => s.required && !photos[s.id])
  const ready = done === all.length && !missingPhotos.length

  const addPhoto = async (slot: string, file: File | undefined) => {
    if (!file) return
    setError('')
    try {
      const url = await shrinkImage(file)
      setPhotos((p) => ({ ...p, [slot]: url }))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not read that photo. Try another one.')
    }
  }

  const send = () => {
    const list: QcPhoto[] = PHOTO_SLOTS.filter((s) => photos[s.id]).map((s) => ({ slot: s.label, url: photos[s.id] }))
    submitQc(order.id, {
      checked: all.filter((i) => ticked[i.id]).map((i) => i.id),
      total: all.length,
      photos: list,
      note: note.trim(),
      by: user?.name ?? 'Technician',
      at: new Date().toISOString(),
    })
    setConfirm(false)
    setSent('ok')
  }

  if (sent) {
    return shell(
      <section className="qc-sent" role="status">
        <b>{sent === 'ok' ? `Sent to ${order.name || 'the customer'}` : 'Back in the robot queue'}</b>
        <span>
          {sent === 'ok'
            ? `${order.id} is marked written. The customer sees ${Object.keys(photos).length} photo${Object.keys(photos).length === 1 ? '' : 's'} and can accept the product or ask for the free rewrite.`
            : `${order.id} failed QC and is waiting to be rewritten. It shows under Ready to preview.`}
        </span>
        <div className="qc-sent-actions">
          <Link to="/tech" className="vh-btn vh-btn--primary vh-btn--md">Back to dashboard</Link>
          <Link to="/tech/qc" className="vh-btn vh-btn--ghost vh-btn--md">Next order to check</Link>
        </div>
      </section>,
    )
  }

  const photoCount = PHOTO_SLOTS.filter((s) => photos[s.id]).length
  const requiredDone = PHOTO_SLOTS.filter((s) => s.required && photos[s.id]).length
  const requiredTotal = PHOTO_SLOTS.filter((s) => s.required).length
  const qcDone = done === all.length

  const tick = (id: string, on: boolean) => {
    const next = { ...ticked, [id]: on }
    setTicked(next)
    // The last box moves the technician straight on to the photos.
    if (on && all.every((i) => next[i.id])) setTab('photos')
  }

  const tabs = (
    <div className="sc-tabs qc-tabs" role="tablist" aria-label="Photo and QC steps">
      <button role="tab" aria-selected={tab === 'qc'} className={tab === 'qc' ? 'on' : ''} onClick={() => setTab('qc')}>
        QC checklist <span className="vh-mono">{done}/{all.length}</span>
      </button>
      <button
        role="tab"
        aria-selected={tab === 'photos'}
        className={tab === 'photos' ? 'on' : ''}
        disabled={!qcDone}
        title={qcDone ? undefined : 'Finish the checklist first'}
        onClick={() => setTab('photos')}
      >
        Photos <span className="vh-mono">{requiredDone}/{requiredTotal}</span>
      </button>
    </div>
  )

  const reference = (
    <section className="qc-ref">
      <h2 className="tp-h">Compare against</h2>
      <p className="qc-text-ref">{(sp.mode === 'text' ? sp.text : order.ocrText ?? sp.simText ?? sp.text) || 'No text recorded'}</p>
      <dl className="tp-opts">
        <div><dt>Input</dt><dd>{MODE_LABEL[sp.mode]}</dd></div>
        <div><dt>Paper</dt><dd><i className="tp-sw" style={{ background: sp.paperColor }} />{sp.paper}</dd></div>
        <div><dt>Ink</dt><dd><i className="tp-sw" style={{ background: sp.inkColor }} />{sp.ink}</dd></div>
        <div><dt>Pieces</dt><dd>{sp.qty || 1}</dd></div>
        <div><dt>Robot</dt><dd>{asg.robotId}</dd></div>
      </dl>
    </section>
  )

  return shell(
    <>
      {confirm && (
        <div className="sc-modal" onClick={() => setConfirm(false)}>
          <div className="sc-modal-card" role="dialog" aria-modal="true" aria-labelledby="qc-confirm-h" onClick={(e) => e.stopPropagation()}>
            <span className="sc-modal-mark sc-modal-mark--accent" aria-hidden="true" />
            <div className="sc-modal-head">
              <h2 id="qc-confirm-h">Send to {order.name || 'the customer'}?</h2>
              <p>
                They are notified now and see {photoCount} photo{photoCount === 1 ? '' : 's'}
                {note.trim() ? ' and your note' : ''}. This cannot be taken back from this screen.
              </p>
            </div>
            <div className="sc-modal-actions">
              <button className="vh-btn vh-btn--primary" onClick={send}>Send to customer</button>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setConfirm(false)}>Not yet</button>
            </div>
          </div>
        </div>
      )}

      <div className="qc-tabbar">{tabs}</div>

      {tab === 'qc' ? (
        <div className="tp-grid">
          <div className="tp-main qc-main">
            <div className="qc-progress" role="progressbar" aria-valuemin={0} aria-valuemax={all.length} aria-valuenow={done} aria-label="Checks completed">
              <p><b className="vh-mono">{done}</b> of {all.length} checked. The photos step opens when all are ticked.</p>
              <div className="qc-segs" aria-hidden="true">
                {all.map((i) => <i key={i.id} className={ticked[i.id] ? 'on' : ''} />)}
              </div>
            </div>

            {groups.map((g) => {
              const n = g.items.filter((i) => ticked[i.id]).length
              return (
                <fieldset key={g.id} className="qc-group">
                  <legend>
                    <span>{g.title}</span>
                    <span className="vh-mono qc-count">{n}/{g.items.length}</span>
                  </legend>
                  <div className="qc-items">
                    {g.items.map((i) => (
                      <label key={i.id} className={`qc-item${ticked[i.id] ? ' on' : ''}`}>
                        <input type="checkbox" checked={!!ticked[i.id]} onChange={(e) => tick(i.id, e.target.checked)} />
                        <span className="qc-box" aria-hidden="true">{ticked[i.id] && <Check size={14} weight="bold" />}</span>
                        <span className="qc-text">
                          <b>{i.title}</b>
                          <span>{i.detail}</span>
                        </span>
                      </label>
                    ))}
                  </div>
                </fieldset>
              )
            })}

            <section className="qc-fail" aria-label="If something is wrong">
              {!failing ? (
                <button className="qc-link" onClick={() => setFailing(true)}>
                  <Warning size={18} /> Something is wrong, reschedule this order
                </button>
              ) : (
                <div className="qc-fail-body">
                  <b>What went wrong?</b>
                  <div className="sc-reasons">
                    {QC_FAIL_REASONS.map((r) => (
                      <button
                        key={r}
                        type="button"
                        className={`sc-reason${reasons.includes(r) ? ' on' : ''}`}
                        aria-pressed={reasons.includes(r)}
                        onClick={() => setReasons((rs) => (rs.includes(r) ? rs.filter((x) => x !== r) : [...rs, r]))}
                      >
                        {r}
                      </button>
                    ))}
                  </div>
                  <label className="qc-label">
                    Note for the schedule
                    <textarea className="vh-textarea" rows={2} value={failNote} onChange={(e) => setFailNote(e.target.value)} />
                  </label>
                  <div className="sc-row">
                    <button
                      className="vh-btn vh-btn--md qc-danger"
                      disabled={!reasons.length}
                      onClick={() => {
                        failQc(order.id, reasons, failNote.trim())
                        setSent('failed')
                      }}
                    >
                      <ArrowsClockwise size={18} /> Reschedule
                    </button>
                    <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setFailing(false)}>Cancel</button>
                  </div>
                </div>
              )}
            </section>
          </div>

          <aside className="tp-side" aria-label="Reference">
            {reference}
            {prototype && !qcDone && (
              <button
                className="vh-btn vh-btn--ghost vh-btn--sm qc-proto"
                onClick={() => {
                  setTicked(Object.fromEntries(all.map((i) => [i.id, true])))
                  setTab('photos')
                }}
              >
                Prototype: tick all checks
              </button>
            )}
          </aside>
        </div>
      ) : (
        <div className="tp-grid">
          <div className="tp-main qc-main">
            <div className="qc-lede">
              <h2 className="tp-h">Photos for the customer</h2>
              <p>
                The customer sees these with your note. The two highlighted photos are required.
              </p>
            </div>

            <ul className="qc-slots qc-slots--big">
              {PHOTO_SLOTS.map((s) => (
                <li key={s.id} className={s.required ? 'req' : ''}>
                  <input
                    ref={(el) => { inputs.current[s.id] = el }}
                    type="file"
                    accept="image/*"
                    capture="environment"
                    hidden
                    aria-label={`${s.label} photo`}
                    onChange={(e) => {
                      void addPhoto(s.id, e.target.files?.[0])
                      e.target.value = ''
                    }}
                  />
                  <div className="qc-slot-head">
                    <b>{s.label}</b>
                    <span className={`qc-tag${s.required ? ' req' : ''}${photos[s.id] ? ' ok' : ''}`}>
                      {photos[s.id] ? 'Added' : s.required ? 'Required' : 'Optional'}
                    </span>
                  </div>
                  {photos[s.id] ? (
                    <div className="qc-shot">
                      <img src={photos[s.id]} alt={`${s.label} of ${order.id}`} />
                      <div className="qc-shot-bar">
                        <span>{s.hint}</span>
                        <button type="button" aria-label={`Retake ${s.label}`} onClick={() => inputs.current[s.id]?.click()}>
                          <ArrowsClockwise size={16} />
                        </button>
                        <button type="button" aria-label={`Remove ${s.label}`} onClick={() => setPhotos((p) => { const n = { ...p }; delete n[s.id]; return n })}>
                          <X size={16} />
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className={`qc-empty${s.required ? ' req' : ''}`} onClick={() => inputs.current[s.id]?.click()}>
                      <Camera size={28} />
                      <span className="qc-empty-text">
                        <b>Take or upload a photo</b>
                        <span>{s.hint}</span>
                      </span>
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {error && <p className="lg-error" role="alert">{error}</p>}
          </div>

          <aside className="tp-side" aria-label="Send">
            <section>
              <h2 className="tp-h">Checklist</h2>
              <p className="qc-done-line"><Check size={18} weight="bold" /> {all.length} of {all.length} checks passed</p>
              <button className="qc-link qc-back" onClick={() => setTab('qc')}>
                <ArrowLeft size={16} /> Back to the checklist
              </button>
            </section>
            {reference}
            <section aria-label="Send">
              <label className="qc-label">
                Note for the customer
                <textarea
                  className="vh-textarea"
                  rows={3}
                  value={note}
                  placeholder="Optional, shown under the photos"
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
              <p className="qc-need" aria-live="polite">
                {ready
                  ? 'Everything is in. You can send it.'
                  : `Add the ${missingPhotos.map((s) => s.label.toLowerCase()).join(' and ')} photo${missingPhotos.length > 1 ? 's' : ''} to send.`}
              </p>
              <button className="vh-btn vh-btn--primary vh-btn--md qc-send" disabled={!ready} onClick={() => setConfirm(true)}>
                <PaperPlaneTilt size={18} weight="bold" /> Send to customer
              </button>
              {prototype && !ready && (
                <button
                  className="vh-btn vh-btn--ghost vh-btn--sm qc-proto"
                  onClick={() =>
                    setPhotos((p) => ({
                      ...p,
                      ...Object.fromEntries(
                        PHOTO_SLOTS.filter((s) => s.required && !p[s.id]).map((s) => [s.id, samplePhoto(s.label, sp.paperColor, sp.inkColor)]),
                      ),
                    }))
                  }
                >
                  Prototype: add sample photos
                </button>
              )}
            </section>
          </aside>
        </div>
      )}
    </>,
  )
}
