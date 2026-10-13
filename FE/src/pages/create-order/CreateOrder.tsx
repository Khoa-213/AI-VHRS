import { useCallback, useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import {
  CREATE_PAYS, FONT_STYLES, INKS, MODES, PAPERS, PENS, STEP_LABELS, TYPES,
} from '../../constants/catalog'
import { useLocale, useT, useTn } from '../../i18n'
import { navigate, orderPath } from '../../router/router'
import { addOrder, createOrderId, deleteDraft, getDraft, newDraftId, saveDraft, useProfile, useUser } from '../../store/store'
import type { InputMode, Order, OrderSpec } from '../../types'
import { fmt, todayLabel } from '../../utils/format'
import { quote } from '../../utils/pricing'
import { CANVAS_SIZES, drawPathFor } from './draft'
import { inkMask } from '../../components/ui/PaperSheet'
import { MethodLogos } from '../../components/ui/PaymentLogos'
import './create-order.css'

interface Upload {
  name: string
  url: string
  isImg: boolean
  dataUrl?: string
}

function initialMode(saved: InputMode): InputMode {
  const m = /mode=(text|upload|draw)/.exec(window.location.hash)
  return (m?.[1] as InputMode | undefined) ?? saved
}

/** `draftId` opens a saved draft. Without it the form starts empty and becomes a draft once something is filled in. */
export default function CreateOrder({ draftId: given = null }: { draftId?: string | null }) {
  const t = useT()
  const tn = useTn()
  const locale = useLocale()
  const user = useUser()
  const profile = useProfile()
  const priceLabel = (p: number) => (p ? '+' + fmt(p) : t('co.included'))

  // Every change is saved to a draft, so leaving at any point loses nothing.
  const [draftId] = useState(() => given ?? newDraftId())
  const [saved] = useState(() => getDraft(draftId))
  const createdAt = useRef(saved?.createdAt ?? new Date().toISOString())
  const submitted = useRef(false)

  const [step, setStep] = useState(saved?.step ?? 0)
  const [maxStep, setMaxStep] = useState(saved?.maxStep ?? saved?.step ?? 0)
  const [type, setType] = useState<string | null>(saved?.type ?? null)
  const [mode, setMode] = useState<InputMode>(() => initialMode(saved?.mode ?? 'text'))
  const [text, setText] = useState(saved?.text ?? '')
  const [fontStyle, setFontStyle] = useState(saved?.fontStyle ?? 'script')
  const [upload, setUpload] = useState<Upload | null>(() => {
    const u = saved?.upload
    if (!u || (u.isImg && !u.dataUrl)) return null
    return { name: u.name, url: u.dataUrl ?? '', isImg: u.isImg, dataUrl: u.dataUrl }
  })
  // The drawing comes from the full-screen canvas page, which writes it into the draft.
  const strokes = saved?.strokes ?? 0
  const drawUrl = saved?.drawUrl ?? null
  const sizeId = saved?.sizeId ?? 'a4'
  const landscape = saved?.landscape ?? false
  const sheet = CANVAS_SIZES.find((s) => s.id === sizeId) ?? CANVAS_SIZES[0]
  const sheetLabel = t('co.sheet', { label: sheet.label, orient: t(landscape ? 'co.landscape' : 'co.portrait') })
  const [paper, setPaper] = useState<string | null>(saved?.paper ?? null)
  const [pen, setPen] = useState<string | null>(saved?.pen ?? null)
  const [ink, setInk] = useState<string | null>(saved?.ink ?? null)
  const [qty, setQty] = useState(saved?.qty ?? 1)
  // Contact details start from the profile, so a new order only needs them once.
  const [name, setName] = useState(saved?.name ?? profile.fullName)
  const [phone, setPhone] = useState(saved?.phone ?? profile.phone)
  const [address, setAddress] = useState(saved?.address ?? profile.address)
  const [pay, setPay] = useState<string | null>(saved?.pay ?? null)

  const latest = useRef({ step, maxStep, type, mode, text, fontStyle, upload, paper, pen, ink, qty, name, phone, address, pay })
  latest.current = { step, maxStep, type, mode, text, fontStyle, upload, paper, pen, ink, qty, name, phone, address, pay }

  const persist = useCallback((force = false) => {
    if (submitted.current) return
    const s = latest.current
    const filled = !!(s.type || s.text.trim() || s.upload || strokes > 0 || s.paper || s.pen || s.ink || s.qty > 1 || (s.name && s.name !== profile.fullName) || (s.phone && s.phone !== profile.phone) || (s.address && s.address !== profile.address) || s.pay)
    if (!force && !filled && !getDraft(draftId)) return
    saveDraft({
      id: draftId,
      owner: user?.name ?? 'guest',
      createdAt: createdAt.current,
      updatedAt: new Date().toISOString(),
      step: s.step, maxStep: s.maxStep, type: s.type, mode: s.mode, text: s.text, fontStyle: s.fontStyle,
      upload: s.upload ? { name: s.upload.name, isImg: s.upload.isImg, dataUrl: s.upload.dataUrl } : null,
      strokes, drawUrl, sizeId, landscape,
      paper: s.paper, pen: s.pen, ink: s.ink, qty: s.qty, name: s.name, phone: s.phone, address: s.address, pay: s.pay,
    })
  }, [draftId, user, profile, strokes, drawUrl, sizeId, landscape])

  // Save after each change. The short delay only batches keystrokes of a single burst.
  const touched = useRef(false)
  useEffect(() => {
    if (!touched.current) {
      touched.current = true
      return
    }
    const h = window.setTimeout(() => persist(), 250)
    return () => window.clearTimeout(h)
  }, [step, maxStep, type, mode, text, fontStyle, upload, paper, pen, ink, qty, name, phone, address, pay, persist])
  useEffect(() => () => persist(), [persist])

  // Release the blob URL when the upload is replaced or the page unmounts.
  const blobRef = useRef<string | null>(null)
  useEffect(() => {
    blobRef.current = upload?.url ?? null
  }, [upload])
  useEffect(() => () => {
    if (blobRef.current) URL.revokeObjectURL(blobRef.current)
  }, [])

  const q = quote({ type, paper, pen, ink, qty, mode, text, hasUpload: !!upload, strokes }, t, tn, locale)
  const F = FONT_STYLES.find((f) => f.id === fontStyle)!

  const valid = (i: number) => {
    if (i === 0) return !!type
    if (i === 1) return mode === 'text' ? text.trim().length > 0 : mode === 'upload' ? !!upload : strokes > 0
    if (i === 2) return !!(paper && pen && ink && qty >= 1)
    return !!(name.trim() && phone.trim().length >= 8 && address.trim() && pay)
  }
  const ok = valid(step)
  const hints = [
    t('co.hint0'),
    t(mode === 'text' ? 'co.hint1.text' : mode === 'upload' ? 'co.hint1.upload' : 'co.hint1.draw'),
    t(!paper ? 'co.hint2.paper' : !pen ? 'co.hint2.pen' : 'co.hint2.ink'),
    t('co.hint3'),
  ]

  const goTo = (i: number) => {
    setStep(i)
    setMaxStep((m) => Math.max(m, i))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const clampQty = (n: number) => setQty(Math.max(1, Math.min(500, Math.round(n) || 1)))

  const setFile = (f: File | undefined | null) => {
    if (!f) return
    if (upload) URL.revokeObjectURL(upload.url)
    const isImg = f.type.startsWith('image/')
    const next: Upload = { name: f.name, url: URL.createObjectURL(f), isImg }
    setUpload(next)
    if (isImg) {
      const r = new FileReader()
      r.onload = () => setUpload((u) => (u && u.url === next.url ? { ...u, dataUrl: String(r.result) } : u))
      r.readAsDataURL(f)
    }
  }

  const submit = () => {
    const { T, P, N, I } = q
    if (!T || !P || !N || !I || !valid(3)) return
    const spec: OrderSpec = {
      type: T.name, size: T.size, aspect: T.aspect, land: T.land, mins: T.mins,
      paper: P.name, paperColor: P.color, pen: N.name, penW: N.w, ink: I.name, inkColor: I.color,
      font: F.font, fontName: F.name, mode, text: text.trim(),
      img: mode === 'upload' ? upload?.dataUrl ?? null : mode === 'draw' ? drawUrl : null,
      qty,
    }
    const order: Order = {
      id: createOrderId(),
      title: `${T.name} × ${qty}`,
      detail: [P.name, I.name].join(' · '),
      status: 'Sketching',
      total: q.total,
      date: todayLabel(),
      spec, name: name.trim(), phone: phone.trim(), address: address.trim(), pay: pay ?? undefined,
    }
    submitted.current = true
    deleteDraft(draftId)
    addOrder(order)
    navigate(orderPath(order.id, 'review'))
  }

  const openCanvas = () => {
    persist(true)
    navigate(drawPathFor(draftId))
  }

  const saveAndExit = () => {
    persist()
    navigate(user ? '/account/drafts' : `/login?next=${encodeURIComponent('/account/drafts')}`)
  }

  const next = () => {
    if (!ok) return
    if (step < 3) goTo(step + 1)
    else submit()
  }

  const pvImg = mode === 'upload' && upload?.isImg ? upload.url : mode === 'draw' && drawUrl ? drawUrl : null
  const raw = mode === 'text' ? text.trim() || 'Chúc Mừng Năm Mới' : mode === 'upload' && upload ? upload.name : 'Chúc Mừng Năm Mới'
  const previewText = raw.length > 160 ? raw.slice(0, 160) + '…' : raw
  const pvFont = previewText.length < 22 ? 24 : previewText.length < 60 ? 17 : 12

  const summary = [
    { k: t('co.sum.type'), v: q.T ? `${tn(q.T.name)}, ${q.T.size}` : t('co.sum.notChosen'), to: 0 },
    {
      k: t('co.sum.content'),
      v: mode === 'text'
        ? t('co.sum.textIn', { text: `${text.trim().slice(0, 48)}${text.trim().length > 48 ? '…' : ''}`, font: tn(F.name) })
        : mode === 'upload' ? (upload ? t('co.sum.image', { name: upload.name }) : t('co.sum.noImage')) : t('co.sum.drawn', { n: strokes, sheet: sheetLabel }),
      to: 1,
    },
    { k: t('co.sum.materials'), v: [q.P?.name, q.N?.name, q.I?.name].filter(Boolean).map((n) => tn(n!)).join(', ') || t('co.sum.notChosen'), to: 2 },
    { k: t('co.sum.qty'), v: t(qty > 1 ? 'co.pieces' : 'co.piece', { n: qty }), to: 2 },
  ]

  return (
    <Page label="Create Order">
      <div className="co">
        <div className="vh-head-text">
          <span className="vh-eyebrow">{t('co.eyebrow')}</span>
          <h1 className="vh-h1 vh-h1--lg">{t('co.h1')}</h1>
        </div>

        <div className="co-shell">
          <div className="co-main">
            <div className="co-steps">
              {STEP_LABELS.map((label, i) => {
                const cur = i === step
                const done = i <= maxStep && !cur
                const locked = i > maxStep
                return (
                  <button
                    key={label}
                    className={`co-step${cur ? ' cur' : done ? ' done' : ''}`}
                    disabled={locked}
                    onClick={() => goTo(i)}
                  >
                    <span className="co-step-bar" />
                    <span className="co-step-label">
                      <span className="co-step-num">0{i + 1}</span>
                      <span>{tn(label)}</span>
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="co-body">
              {step === 0 && (
                <>
                  <div className="vh-stack">
                    <h2 className="co-h2">{t('co.s0.title')}</h2>
                    <p className="vh-lede">{t('co.s0.lede')}</p>
                  </div>
                  <div className="co-tray co-tray--4">
                    {TYPES.map((o) => (
                      <button key={o.id} className={`co-opt co-type${type === o.id ? ' on' : ''}`} onClick={() => setType(o.id)}>
                        <div className="co-type-stage">
                          <div className="co-type-paper" style={{ width: o.w, height: o.h }} />
                        </div>
                        <div className="vh-stack" style={{ gap: 4 }}>
                          <span className="co-type-name">{tn(o.name)}</span>
                          <span className="co-type-size">{o.size}</span>
                        </div>
                        <span className="co-type-price">{t('co.from', { price: fmt(o.base) })}</span>
                      </button>
                    ))}
                  </div>
                </>
              )}

              {step === 1 && (
                <>
                  <div className="vh-stack">
                    <h2 className="co-h2">{t('co.s1.title')}</h2>
                    <p className="vh-lede">{t('co.s1.lede')}</p>
                  </div>

                  <div className="co-tray co-tray--3">
                    {MODES.map((m) => (
                      <button key={m.id} className={`co-opt${mode === m.id ? ' on' : ''}`} onClick={() => (m.id === 'draw' ? openCanvas() : setMode(m.id))}>
                        <span className="co-opt-name">{tn(m.label)}</span>
                        <span className="co-opt-sub">{tn(m.desc)}</span>
                      </button>
                    ))}
                  </div>

                  {mode === 'text' && (
                    <>
                      <div className="co-field">
                        <textarea
                          className="co-text"
                          rows={5}
                          value={text}
                          aria-label={t('co.message')}
                          placeholder={t('co.placeholder')}
                          onChange={(e) => setText(e.target.value)}
                        />
                        <div className="co-meta vh-mono">
                          <span>{t('co.chars', { n: text.length })}</span>
                          <span>{t('co.charsExtra')}</span>
                        </div>
                      </div>
                      <div className="co-group">
                        <span className="co-group-label">{t('co.styleLabel')}</span>
                        <div className="co-tray co-tray--3 co-tray--keep">
                          {FONT_STYLES.map((s) => (
                            <button key={s.id} className={`co-opt co-font${fontStyle === s.id ? ' on' : ''}`} onClick={() => setFontStyle(s.id)}>
                              <span className="co-font-sample" style={{ fontFamily: s.font }}>{t('co.fontSample')}</span>
                              <span className="co-font-name">{tn(s.name)}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </>
                  )}

                  {mode === 'upload' && (
                    <>
                      <label
                        className="co-drop"
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault()
                          setFile(e.dataTransfer.files[0])
                        }}
                      >
                        <input type="file" accept="image/*,.pdf" className="co-file" onChange={(e) => setFile(e.target.files?.[0])} />
                        <span className="co-drop-icon">
                          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                            <path d="m17 8-5-5-5 5" />
                            <path d="M12 3v12" />
                          </svg>
                        </span>
                        <span className="co-drop-title">{t('co.dropPhoto')}</span>
                        <span className="co-meta vh-mono">{t('co.dropMeta')}</span>
                      </label>
                      {upload && (
                        <div className="co-file-row">
                          <div
                            className="co-file-thumb"
                            style={{ backgroundImage: upload.isImg ? `url("${upload.url}")` : 'none' }}
                          />
                          <div className="co-file-text">
                            <span className="co-file-name">{upload.name}</span>
                            <span className="co-file-ok vh-mono">{t('co.fileReady')}</span>
                          </div>
                          <button
                            className="vh-btn vh-btn--ghost vh-btn--sm"
                            onClick={() => {
                              URL.revokeObjectURL(upload.url)
                              setUpload(null)
                            }}
                          >
                            {t('co.remove')}
                          </button>
                        </div>
                      )}
                    </>
                  )}

                  {mode === 'draw' && (
                    <div className="co-sheet">
                      <div
                        className="co-sheet-thumb"
                        style={{ aspectRatio: landscape ? `${sheet.h} / ${sheet.w}` : `${sheet.w} / ${sheet.h}` }}
                      >
                        {drawUrl ? <img src={drawUrl} alt={t('co.yourDrawing')} /> : <span className="vh-mono">{t('co.blank')}</span>}
                      </div>
                      <div className="co-sheet-text">
                        <span className="co-sheet-title">
                          {t(strokes > 0 ? 'co.drawReady' : 'co.drawNone')}
                        </span>
                        <span className="co-meta vh-mono">
                          {sheetLabel} · {t(strokes === 1 ? 'co.stroke' : 'co.strokes', { n: strokes })} · +15.000₫
                        </span>
                        <button className="vh-btn vh-btn--primary vh-btn--sm" onClick={openCanvas}>
                          {t(strokes > 0 ? 'co.editCanvas' : 'co.openCanvas')}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}

              {step === 2 && (
                <>
                  <div className="vh-stack">
                    <h2 className="co-h2">{t('co.s2.title')}</h2>
                    <p className="vh-lede">{t('co.s2.lede')}</p>
                  </div>

                  <div className="co-group">
                    <span className="co-group-label">{t('co.paper')}</span>
                    <div className="co-tray co-tray--4">
                      {PAPERS.map((o) => (
                        <button key={o.id} className={`co-opt co-opt--row${paper === o.id ? ' on' : ''}`} onClick={() => setPaper(o.id)}>
                          <span className="co-swatch" style={{ background: o.color }} />
                          <span className="co-choice-text">
                            <span className="co-opt-name">{tn(o.name)}</span>
                            <span className="co-opt-sub">{tn(o.spec)}</span>
                            <span className="co-price">{priceLabel(o.price)}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className={`co-group${paper ? '' : ' locked'}`}>
                    <span className="co-group-label">{t('co.pen')}</span>
                    <div className="co-tray co-tray--4">
                      {PENS.map((o) => (
                        <button key={o.id} className={`co-opt co-opt--pen${pen === o.id ? ' on' : ''}`} onClick={() => setPen(o.id)}>
                          <span className="co-nib"><span style={{ height: o.w }} /></span>
                          <span className="co-choice-text">
                            <span className="co-opt-name">{tn(o.name)}</span>
                            <span className="co-opt-sub">{tn(o.spec)}</span>
                            <span className="co-price">{priceLabel(o.price)}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className={`co-group${pen ? '' : ' locked'}`}>
                    <span className="co-group-label">{t('co.ink')}</span>
                    <div className="co-inks">
                      {INKS.map((o) => (
                        <button key={o.id} className={`co-ink${ink === o.id ? ' on' : ''}`} onClick={() => setInk(o.id)}>
                          <span className="co-ink-dot" style={{ background: o.color }} />
                          <span className="co-ink-name">{tn(o.name)}</span>
                          <span className="co-price">{priceLabel(o.price)}</span>
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="co-qty">
                    <div className="co-qty-text">
                      <span className="co-qty-title">{t('co.qty')}</span>
                      <span className="co-qty-sub">{t('co.qtyHint')}</span>
                    </div>
                    <div className="co-stepper">
                      <button aria-label={t('co.dec')} onClick={() => clampQty(qty - 1)}>−</button>
                      <input type="number" aria-label={t('co.qty')} min={1} max={500} value={qty} onChange={(e) => clampQty(+e.target.value)} />
                      <button aria-label={t('co.inc')} onClick={() => clampQty(qty + 1)}>+</button>
                    </div>
                  </div>
                </>
              )}

              {step === 3 && (
                <>
                  <div className="vh-stack">
                    <h2 className="co-h2">{t('co.s3.title')}</h2>
                    <p className="vh-lede">{t('co.s3.lede')}</p>
                  </div>
                  <div className="co-sum">
                    {summary.map((r) => (
                      <div key={r.k} className="co-sum-row">
                        <span className="co-sum-k">{r.k}</span>
                        <span className="co-sum-v">{r.v}</span>
                        <button className="vh-link" onClick={() => goTo(r.to)}>{t('co.edit')}</button>
                      </div>
                    ))}
                  </div>
                  <div className="co-group">
                    <span className="co-group-label">{t('co.delivery')}</span>
                    <div className="co-tray co-tray--2">
                      <label className="co-cell">
                        {t('co.fullName')}
                        <input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
                      </label>
                      <label className="co-cell">
                        {t('co.phone')}
                        <input placeholder="0901 234 567" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
                      </label>
                      <label className="co-cell co-cell--wide">
                        {t('co.address')}
                        <input autoComplete="street-address" value={address} onChange={(e) => setAddress(e.target.value)} />
                      </label>
                    </div>
                  </div>
                  <div className="co-group">
                    <span className="co-group-label">{t('co.payment')}</span>
                    <div className="co-tray co-tray--3">
                      {CREATE_PAYS.map((o) => (
                        <button key={o.id} className={`co-opt${pay === o.id ? ' on' : ''}`} onClick={() => setPay(o.id)}>
                          <MethodLogos id={o.id} />
                          <span className="co-opt-name">{tn(o.name)}</span>
                          <span className="co-opt-sub">{tn(o.spec)}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </div>

            <div className="co-nav">
              <button className="vh-btn vh-btn--ghost vh-btn--md co-back" disabled={step === 0} onClick={() => step > 0 && goTo(step - 1)}>
                {t('co.back')}
              </button>
              <div className="co-next-wrap">
                <span className="co-hint">{ok ? '' : hints[step]}</span>
                <button
                  className={`vh-btn vh-btn--md ${step === 3 ? 'vh-btn--primary' : 'vh-btn--white'}`}
                  disabled={!ok}
                  onClick={next}
                >
                  {t(step === 3 ? 'co.submit' : 'co.continue')}
                </button>
              </div>
            </div>
          </div>

          <div className="co-side">
          <aside className="co-rail">
            <div className="co-preview">
              <div
                className="co-preview-paper"
                style={{
                  height: q.T?.land ? '58%' : '88%',
                  aspectRatio: q.T?.aspect ?? '105/148',
                  background: q.P?.color ?? '#f4eee0',
                }}
              >
                {pvImg ? (
                  <div
                    className="co-preview-img"
                    style={mode === 'draw' ? inkMask(pvImg, q.I?.color ?? '#1b2440') : { backgroundImage: `url("${pvImg}")` }}
                  />
                ) : (
                  <span style={{ fontFamily: F.font, fontSize: pvFont, color: q.I?.color ?? '#1b2440' }}>{previewText}</span>
                )}
              </div>
            </div>
            <div className="co-rail-body">
              <span className="co-est-title">{t('co.estimate')}</span>
              <div className="co-lines">
                {q.lines.length ? (
                  q.lines.map((l) => (
                    <div key={l.label} className="co-line">
                      <span>{l.label}</span>
                      <span className={l.good ? 'good' : undefined}>{l.value}</span>
                    </div>
                  ))
                ) : (
                  <span className="co-hint">{t('co.chooseType')}</span>
                )}
              </div>
              <div className="vh-total-row">
                <span>{t('co.total')}</span>
                <span className="co-total">{fmt(q.total)}</span>
              </div>
              <div className="co-eta">
                <div><span>{t('co.robotTime')}</span><b>{q.robotTime}</b></div>
                <div><span>{t('co.deliveryBy')}</span><b>{q.eta}</b></div>
              </div>
              <span className="co-fine">{t('co.fine')}</span>
            </div>
          </aside>
          <button type="button" className="vh-btn vh-btn--md vh-btn--white co-save" onClick={saveAndExit}>
            {t('co.saveExit')}
          </button>
          </div>
        </div>
      </div>
    </Page>
  )
}
