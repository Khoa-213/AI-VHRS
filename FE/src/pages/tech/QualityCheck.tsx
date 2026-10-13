import { useMemo, useRef, useState } from 'react'
import { ArrowLeft, ArrowsClockwise, Camera, Check, PaperPlaneTilt, Warning, X } from '@phosphor-icons/react'
import { useT, useTn } from '../../i18n'
import SkipLink from '../../components/ui/SkipLink'
import ThemeToggle from '../../components/ui/ThemeToggle'
import LanguageToggle from '../../components/ui/LanguageToggle'
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
  const t = useT()
  const tn = useTn()
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

  const groups = useMemo(() => (order ? qcGroups(order, t, tn) : []), [order, t, tn])
  const all = groups.flatMap((g) => g.items)
  const done = all.filter((i) => ticked[i.id]).length

  const shell = (body: React.ReactNode) => (
    <div className="sd">
      <SkipLink />
      <TechRail active="qc" />
      <main className="sd-body" id="main">
        <header className="sd-top">
          <div>
            <h1>{order ? t('qc.title', { id: order.id }) : t('qc.titleShort')}</h1>
            <p>{order ? t('qc.subtitle', { title: tn(order.title), name: order.name || t('qc.theCustomer') }) : t('qc.notFound')}</p>
          </div>
          <div className="sd-top-right">
            <Link to="/tech/qc" className="sd-btn">{t('qc.another')}</Link>
            <ThemeToggle className="vh-icon-btn" />
            <LanguageToggle className="vh-icon-btn" />
          </div>
        </header>
        {body}
      </main>
    </div>
  )

  if (!order) {
    return shell(
      <section className="sd-card"><div className="sd-empty"><b>{t('qc.notFound')}</b><span>{t('qc.notFoundBody', { id })}</span></div></section>,
    )
  }
  const asg = order.assignment
  if (!asg || asg.techId !== user?.techId) {
    return shell(
      <section className="sd-card">
        <div className="sd-empty">
          <b>{t('qc.notYours')}</b>
          <span>{asg ? t('qc.belongsTo', { id: order.id, name: asg.techName }) : t('qc.noTech', { id: order.id })}</span>
        </div>
      </section>,
    )
  }
  if (!sent && !runDone(order, now)) {
    return shell(
      <section className="sd-card">
        <div className="sd-empty">
          <b>{t(order.run ? 'qc.stillWriting' : 'qc.notWritten')}</b>
          <span>{t('qc.opensAfter')}</span>
          <Link to={`/tech/preview/${encodeURIComponent(order.id)}`} className="vh-link">{t('qc.openSim')}</Link>
          {prototype && order.run && (
            <button className="vh-btn vh-btn--ghost vh-btn--sm sc-self-start" onClick={() => finishRobotRun(order.id)}>
              {t('qc.protoFinish')}
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
      setError(e instanceof Error && e.message.startsWith('qc.err.') ? t(e.message) : t('qc.photoErr'))
    }
  }

  const send = () => {
    const list: QcPhoto[] = PHOTO_SLOTS.filter((s) => photos[s.id]).map((s) => ({ slot: s.label, url: photos[s.id] }))
    submitQc(order.id, {
      checked: all.filter((i) => ticked[i.id]).map((i) => i.id),
      total: all.length,
      photos: list,
      note: note.trim(),
      by: user?.name ?? t('td.technician'),
      at: new Date().toISOString(),
    })
    setConfirm(false)
    setSent('ok')
  }

  if (sent) {
    return shell(
      <section className="qc-sent" role="status">
        <b>{sent === 'ok' ? t('qc.sentOk', { name: order.name || t('qc.theCustomer') }) : t('qc.sentFail')}</b>
        <span>
          {sent === 'ok'
            ? t('qc.sentOkBody', { id: order.id, photos: t(Object.keys(photos).length === 1 ? 'qc.photoOne' : 'qc.photoMany', { n: Object.keys(photos).length }) })
            : t('qc.sentFailBody', { id: order.id })}
        </span>
        <div className="qc-sent-actions">
          <Link to="/tech" className="vh-btn vh-btn--primary vh-btn--md">{t('qc.toDash')}</Link>
          <Link to="/tech/qc" className="vh-btn vh-btn--ghost vh-btn--md">{t('qc.nextOrder')}</Link>
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
    <div className="sc-tabs qc-tabs" role="tablist" aria-label={t('qc.stepsAria')}>
      <button role="tab" aria-selected={tab === 'qc'} className={tab === 'qc' ? 'on' : ''} onClick={() => setTab('qc')}>
        {t('qc.tabChecklist')} <span className="vh-mono">{done}/{all.length}</span>
      </button>
      <button
        role="tab"
        aria-selected={tab === 'photos'}
        className={tab === 'photos' ? 'on' : ''}
        disabled={!qcDone}
        title={qcDone ? undefined : t('qc.finishFirst')}
        onClick={() => setTab('photos')}
      >
        {t('qc.tabPhotos')} <span className="vh-mono">{requiredDone}/{requiredTotal}</span>
      </button>
    </div>
  )

  const reference = (
    <section className="qc-ref">
      <h2 className="tp-h">{t('qc.compare')}</h2>
      <p className="qc-text-ref">{(sp.mode === 'text' ? sp.text : order.ocrText ?? sp.simText ?? sp.text) || t('qc.noText')}</p>
      <dl className="tp-opts">
        <div><dt>{t('qc.input')}</dt><dd>{tn(MODE_LABEL[sp.mode])}</dd></div>
        <div><dt>{t('qc.paperRow')}</dt><dd><i className="tp-sw" style={{ background: sp.paperColor }} />{tn(sp.paper)}</dd></div>
        <div><dt>{t('qc.inkRow')}</dt><dd><i className="tp-sw" style={{ background: sp.inkColor }} />{tn(sp.ink)}</dd></div>
        <div><dt>{t('qc.piecesRow')}</dt><dd>{sp.qty || 1}</dd></div>
        <div><dt>{t('qc.robotRow')}</dt><dd>{asg.robotId}</dd></div>
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
              <h2 id="qc-confirm-h">{t('qc.confirmTitle', { name: order.name || t('qc.theCustomer') })}</h2>
              <p>
                {t('qc.confirmBody', { photos: t(photoCount === 1 ? 'qc.photoOne' : 'qc.photoMany', { n: photoCount }), note: note.trim() ? t('qc.andNote') : '' })}
              </p>
            </div>
            <div className="sc-modal-actions">
              <button className="vh-btn vh-btn--primary" onClick={send}>{t('qc.sendCustomer')}</button>
              <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setConfirm(false)}>{t('qc.notYet')}</button>
            </div>
          </div>
        </div>
      )}

      <div className="qc-tabbar">{tabs}</div>

      {tab === 'qc' ? (
        <div className="tp-grid">
          <div className="tp-main qc-main">
            <div className="qc-progress" role="progressbar" aria-valuemin={0} aria-valuemax={all.length} aria-valuenow={done} aria-label={t('qc.checked')}>
              <p>{t('qc.progress', { done, total: all.length })}</p>
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

            <section className="qc-fail" aria-label={t('qc.ifWrong')}>
              {!failing ? (
                <button className="qc-link" onClick={() => setFailing(true)}>
                  <Warning size={18} /> {t('qc.reschedule')}
                </button>
              ) : (
                <div className="qc-fail-body">
                  <b>{t('qc.whatWrong')}</b>
                  <div className="sc-reasons">
                    {QC_FAIL_REASONS.map((r) => (
                      <button
                        key={r}
                        type="button"
                        className={`sc-reason${reasons.includes(r) ? ' on' : ''}`}
                        aria-pressed={reasons.includes(r)}
                        onClick={() => setReasons((rs) => (rs.includes(r) ? rs.filter((x) => x !== r) : [...rs, r]))}
                      >
                        {tn(r)}
                      </button>
                    ))}
                  </div>
                  <label className="qc-label">
                    {t('qc.scheduleNote')}
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
                      <ArrowsClockwise size={18} /> {t('qc.rescheduleBtn')}
                    </button>
                    <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={() => setFailing(false)}>{t('qc.cancel')}</button>
                  </div>
                </div>
              )}
            </section>
          </div>

          <aside className="tp-side" aria-label={t('qc.reference')}>
            {reference}
            {prototype && !qcDone && (
              <button
                className="vh-btn vh-btn--ghost vh-btn--sm qc-proto"
                onClick={() => {
                  setTicked(Object.fromEntries(all.map((i) => [i.id, true])))
                  setTab('photos')
                }}
              >
                {t('qc.protoTick')}
              </button>
            )}
          </aside>
        </div>
      ) : (
        <div className="tp-grid">
          <div className="tp-main qc-main">
            <div className="qc-lede">
              <h2 className="tp-h">{t('qc.photosFor')}</h2>
              <p>{t('qc.photosBody')}</p>
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
                    aria-label={t('qc.photoLabel', { label: tn(s.label) })}
                    onChange={(e) => {
                      void addPhoto(s.id, e.target.files?.[0])
                      e.target.value = ''
                    }}
                  />
                  <div className="qc-slot-head">
                    <b>{tn(s.label)}</b>
                    <span className={`qc-tag${s.required ? ' req' : ''}${photos[s.id] ? ' ok' : ''}`}>
                      {photos[s.id] ? t('qc.added') : s.required ? t('qc.required') : t('qc.optional')}
                    </span>
                  </div>
                  {photos[s.id] ? (
                    <div className="qc-shot">
                      <img src={photos[s.id]} alt={t('rs.photoAlt', { slot: tn(s.label), id: order.id })} />
                      <div className="qc-shot-bar">
                        <span>{tn(s.hint)}</span>
                        <button type="button" aria-label={t('qc.retake', { label: tn(s.label) })} onClick={() => inputs.current[s.id]?.click()}>
                          <ArrowsClockwise size={16} />
                        </button>
                        <button type="button" aria-label={t('qc.removePhoto', { label: tn(s.label) })} onClick={() => setPhotos((p) => { const n = { ...p }; delete n[s.id]; return n })}>
                          <X size={16} />
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button type="button" className={`qc-empty${s.required ? ' req' : ''}`} onClick={() => inputs.current[s.id]?.click()}>
                      <Camera size={28} />
                      <span className="qc-empty-text">
                        <b>{t('qc.takePhoto')}</b>
                        <span>{tn(s.hint)}</span>
                      </span>
                    </button>
                  )}
                </li>
              ))}
            </ul>
            {error && <p className="lg-error" role="alert">{error}</p>}
          </div>

          <aside className="tp-side" aria-label={t('qc.send')}>
            <section>
              <h2 className="tp-h">{t('qc.checklist')}</h2>
              <p className="qc-done-line"><Check size={18} weight="bold" /> {t('qc.passed', { n: all.length })}</p>
              <button className="qc-link qc-back" onClick={() => setTab('qc')}>
                <ArrowLeft size={16} /> {t('qc.backList')}
              </button>
            </section>
            {reference}
            <section aria-label={t('qc.send')}>
              <label className="qc-label">
                {t('qc.customerNote')}
                <textarea
                  className="vh-textarea"
                  rows={3}
                  value={note}
                  placeholder={t('qc.notePh')}
                  onChange={(e) => setNote(e.target.value)}
                />
              </label>
              <p className="qc-need" aria-live="polite">
                {ready
                  ? t('qc.allIn')
                  : t('qc.addPhotos', { list: missingPhotos.map((s) => tn(s.label).toLowerCase()).join(t('qc.and')), s: missingPhotos.length > 1 ? 's' : '' })}
              </p>
              <button className="vh-btn vh-btn--primary vh-btn--md qc-send" disabled={!ready} onClick={() => setConfirm(true)}>
                <PaperPlaneTilt size={18} weight="bold" /> {t('qc.sendCustomer')}
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
                  {t('qc.protoPhotos')}
                </button>
              )}
            </section>
          </aside>
        </div>
      )}
    </>,
  )
}
