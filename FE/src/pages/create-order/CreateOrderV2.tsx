import { useEffect, useRef, useState, type ReactNode } from 'react'
import Page from '../../components/layout/Page'
import { MethodLogos } from '../../components/ui/PaymentLogos'
import { CREATE_PAYS, FONT_STYLES, INKS, MODES, PAPERS, PENS, TYPES } from '../../constants/catalog'
import { useLocale, useT, useTn } from '../../i18n'
import { navigate, orderPath } from '../../router/router'
import { addOrder, createOrderId } from '../../store/store'
import type { InputMode, Order, OrderSpec } from '../../types'
import { fmt, todayLabel } from '../../utils/format'
import { quote } from '../../utils/pricing'
import DrawPad from './DrawPad'
import './create-order-v2.css'

/* Experimental redesign of Create Order: one continuous form instead of a 4-step wizard.
   Same state, pricing and submit logic as CreateOrder.tsx; only the structure and styling differ. */

interface Upload {
  name: string
  url: string
  isImg: boolean
  dataUrl?: string
}

function Section({ n, title, hint, state, children }: {
  n: string
  title: string
  hint: string
  state: 'open' | 'done' | 'locked'
  children: ReactNode
}) {
  return (
    <section className={`cv-sec cv-sec--${state}`} aria-disabled={state === 'locked'}>
      <header className="cv-sec-head">
        <span className="cv-sec-n">{n}</span>
        <div>
          <h2 className="cv-sec-title">{title}</h2>
          <p className="cv-sec-hint">{hint}</p>
        </div>
      </header>
      <div className="cv-sec-body" inert={state === 'locked'}>{children}</div>
    </section>
  )
}

interface RowProps {
  on: boolean
  onPick: () => void
  lead?: ReactNode
  name: string
  sub?: string
  meta?: string
}

function Row({ on, onPick, lead, name, sub, meta }: RowProps) {
  return (
    <button type="button" role="radio" aria-checked={on} className={`cv-row${on ? ' on' : ''}`} onClick={onPick}>
      <span className="cv-row-lead">{lead ?? <span className="cv-mark" />}</span>
      <span className="cv-row-main">
        <span className="cv-row-name">{name}</span>
        {sub && <span className="cv-row-sub">{sub}</span>}
      </span>
      {meta && <span className="cv-row-meta">{meta}</span>}
    </button>
  )
}

export default function CreateOrderV2() {
  const t = useT()
  const tn = useTn()
  const locale = useLocale()
  const priceLabel = (p: number) => (p ? '+' + fmt(p) : t('co.included'))
  const [type, setType] = useState<string | null>(null)
  const [mode, setMode] = useState<InputMode>('text')
  const [text, setText] = useState('')
  const [fontStyle, setFontStyle] = useState('script')
  const [upload, setUpload] = useState<Upload | null>(null)
  const [strokes, setStrokes] = useState(0)
  const [drawUrl, setDrawUrl] = useState<string | null>(null)
  const [padKey, setPadKey] = useState(0)
  const [paper, setPaper] = useState<string | null>(null)
  const [pen, setPen] = useState<string | null>(null)
  const [ink, setInk] = useState<string | null>(null)
  const [qty, setQty] = useState(1)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [address, setAddress] = useState('')
  const [pay, setPay] = useState<string | null>(null)

  const blobRef = useRef<string | null>(null)
  useEffect(() => {
    blobRef.current = upload?.url ?? null
  }, [upload])
  useEffect(() => () => {
    if (blobRef.current) URL.revokeObjectURL(blobRef.current)
  }, [])

  const q = quote({ type, paper, pen, ink, qty, mode, text, hasUpload: !!upload, strokes }, t, tn, locale)
  const F = FONT_STYLES.find((f) => f.id === fontStyle)!

  const done = [
    !!type,
    mode === 'text' ? text.trim().length > 0 : mode === 'upload' ? !!upload : strokes > 0,
    !!(paper && pen && ink && qty >= 1),
    !!(name.trim() && phone.trim().length >= 8 && address.trim() && pay),
  ]
  // A section opens once every section before it is complete.
  const stateOf = (i: number): 'open' | 'done' | 'locked' => {
    if (done.slice(0, i).some((d) => !d)) return 'locked'
    return done[i] ? 'done' : 'open'
  }
  const allDone = done.every(Boolean)
  const missing = [t('co.hint0'), t('co.hint1.content'), t('co.hint2.all'), t('co.hint3.all')][done.indexOf(false)]

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
    if (!T || !P || !N || !I || !allDone) return
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
    addOrder(order)
    navigate(orderPath(order.id, 'review'))
  }

  const pvImg = mode === 'upload' && upload?.isImg ? upload.url : mode === 'draw' && drawUrl ? drawUrl : null
  const raw = mode === 'text' ? text.trim() || 'Chúc Mừng Năm Mới' : mode === 'upload' && upload ? upload.name : 'Chúc Mừng Năm Mới'
  const previewText = raw.length > 160 ? raw.slice(0, 160) + '…' : raw
  const pvFont = previewText.length < 22 ? 24 : previewText.length < 60 ? 17 : 12

  return (
    <Page label="Create Order">
      <div className="cv">
        <header className="cv-head">
          <span className="vh-eyebrow">{t('co.eyebrow')}</span>
          <h1 className="cv-title">{t('co.v2.h1a')}<br />{t('co.v2.h1b')}</h1>
        </header>

        <div className="cv-shell">
          <form className="cv-form" onSubmit={(e) => { e.preventDefault(); submit() }}>
            <Section n="01" title={t('co.format')} hint={t('co.s0.lede')} state={stateOf(0)}>
              <div className="cv-list" role="radiogroup" aria-label={t('co.format')}>
                {TYPES.map((o) => (
                  <Row
                    key={o.id}
                    on={type === o.id}
                    onPick={() => setType(o.id)}
                    lead={(() => {
                      const s = Math.min(44 / o.w, 32 / o.h)
                      return <span className="cv-paper" style={{ width: Math.round(o.w * s), height: Math.round(o.h * s) }} />
                    })()}
                    name={tn(o.name)}
                    sub={o.size}
                    meta={t('co.from', { price: fmt(o.base) })}
                  />
                ))}
              </div>
            </Section>

            <Section n="02" title={t('co.content2')} hint={t('co.s1.lede')} state={stateOf(1)}>
              <div className="cv-tabs" role="tablist" aria-label={t('co.inputMethod')}>
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    role="tab"
                    aria-selected={mode === m.id}
                    className={`cv-tab${mode === m.id ? ' on' : ''}`}
                    onClick={() => setMode(m.id)}
                  >
                    {tn(m.label)}
                    <span>{tn(m.desc)}</span>
                  </button>
                ))}
              </div>

              {mode === 'text' && (
                <>
                  <textarea
                    className="cv-text"
                    rows={4}
                    value={text}
                    aria-label={t('co.message')}
                    placeholder={t('co.placeholder')}
                    onChange={(e) => setText(e.target.value)}
                  />
                  <p className="cv-note">{t('co.charsLine', { n: text.length })}</p>
                  <div className="cv-fonts" role="radiogroup" aria-label={t('co.styleLabel')}>
                    {FONT_STYLES.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        role="radio"
                        aria-checked={fontStyle === s.id}
                        className={`cv-font${fontStyle === s.id ? ' on' : ''}`}
                        onClick={() => setFontStyle(s.id)}
                      >
                        <span style={{ fontFamily: s.font }}>{t('co.fontSample')}</span>
                        <small>{tn(s.name)}</small>
                      </button>
                    ))}
                  </div>
                </>
              )}

              {mode === 'upload' && (
                <>
                  <label
                    className="cv-drop"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => {
                      e.preventDefault()
                      setFile(e.dataTransfer.files[0])
                    }}
                  >
                    <input type="file" accept="image/*,.pdf" className="cv-file" onChange={(e) => setFile(e.target.files?.[0])} />
                    <b>{upload ? upload.name : t('co.dropPhoto2')}</b>
                    <span>{t('co.dropMeta')}</span>
                  </label>
                  {upload && (
                    <button
                      type="button"
                      className="cv-link"
                      onClick={() => {
                        URL.revokeObjectURL(upload.url)
                        setUpload(null)
                      }}
                    >
                      {t('co.removeFile')}
                    </button>
                  )}
                </>
              )}

              {mode === 'draw' && (
                <>
                  <DrawPad
                    key={padKey}
                    url={drawUrl}
                    onStroke={(u) => {
                      setStrokes((n) => n + 1)
                      setDrawUrl(u)
                    }}
                  />
                  <div className="cv-draw-foot">
                    <p className="cv-note">
                      {t('co.drawFoot', { n: t(strokes === 1 ? 'co.stroke' : 'co.strokes', { n: strokes }) })}
                    </p>
                    <button
                      type="button"
                      className="cv-link"
                      onClick={() => {
                        setStrokes(0)
                        setDrawUrl(null)
                        setPadKey((k) => k + 1)
                      }}
                    >
                      {t('co.clearCanvas')}
                    </button>
                  </div>
                </>
              )}
            </Section>

            <Section n="03" title={t('co.materials2')} hint={t('co.s2.lede2')} state={stateOf(2)}>
              <div className="cv-group">
                <span className="cv-label">{t('co.paper')}</span>
                <div className="cv-list" role="radiogroup" aria-label={t('co.paper')}>
                  {PAPERS.map((o) => (
                    <Row
                      key={o.id}
                      on={paper === o.id}
                      onPick={() => setPaper(o.id)}
                      lead={<span className="cv-swatch" style={{ background: o.color }} />}
                      name={tn(o.name)}
                      sub={tn(o.spec)}
                      meta={priceLabel(o.price)}
                    />
                  ))}
                </div>
              </div>

              <div className={`cv-group${paper ? '' : ' cv-group--wait'}`}>
                <span className="cv-label">{t('co.pen')}</span>
                <div className="cv-list" role="radiogroup" aria-label={t('co.pen')}>
                  {PENS.map((o) => (
                    <Row
                      key={o.id}
                      on={pen === o.id}
                      onPick={() => setPen(o.id)}
                      lead={<span className="cv-nib"><span style={{ height: o.w }} /></span>}
                      name={tn(o.name)}
                      sub={tn(o.spec)}
                      meta={priceLabel(o.price)}
                    />
                  ))}
                </div>
              </div>

              <div className={`cv-group${pen ? '' : ' cv-group--wait'}`}>
                <span className="cv-label">{t('co.ink')}</span>
                <div className="cv-list" role="radiogroup" aria-label={t('co.ink')}>
                  {INKS.map((o) => (
                    <Row
                      key={o.id}
                      on={ink === o.id}
                      onPick={() => setInk(o.id)}
                      lead={<span className="cv-swatch cv-swatch--ink" style={{ background: o.color }} />}
                      name={tn(o.name)}
                      meta={priceLabel(o.price)}
                    />
                  ))}
                </div>
              </div>

              <div className="cv-qty">
                <div>
                  <span className="cv-label">{t('co.qty')}</span>
                  <p className="cv-note">{t('co.qtyHint')}</p>
                </div>
                <div className="cv-stepper">
                  <button type="button" aria-label={t('co.dec')} onClick={() => clampQty(qty - 1)}>−</button>
                  <input type="number" aria-label={t('co.qty')} min={1} max={500} value={qty} onChange={(e) => clampQty(+e.target.value)} />
                  <button type="button" aria-label={t('co.inc')} onClick={() => clampQty(qty + 1)}>+</button>
                </div>
              </div>
            </Section>

            <Section n="04" title={t('co.s4.title')} hint={t('co.s4.hint')} state={stateOf(3)}>
              <div className="cv-fields">
                <label className="cv-field">
                  <span>{t('co.fullName')}</span>
                  <input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
                </label>
                <label className="cv-field">
                  <span>{t('co.phone')}</span>
                  <input placeholder="0901 234 567" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
                </label>
                <label className="cv-field cv-field--wide">
                  <span>{t('co.address')}</span>
                  <input autoComplete="street-address" value={address} onChange={(e) => setAddress(e.target.value)} />
                </label>
              </div>
              <div className="cv-group">
                <span className="cv-label">{t('co.payment')}</span>
                <div className="cv-list" role="radiogroup" aria-label={t('co.payment')}>
                  {CREATE_PAYS.map((o) => (
                    <Row
                      key={o.id}
                      on={pay === o.id}
                      onPick={() => setPay(o.id)}
                      lead={<MethodLogos id={o.id} />}
                      name={tn(o.name)}
                      sub={tn(o.spec)}
                    />
                  ))}
                </div>
              </div>
            </Section>

            <div className="cv-submit">
              <p className="cv-note">{allDone ? t('co.ready') : missing}</p>
              <button type="submit" className="vh-btn vh-btn--md vh-btn--primary" disabled={!allDone}>
                {t('co.submit2')}
              </button>
            </div>
          </form>

          <aside className="cv-rail" aria-label={t('co.estimate2')}>
            <div className="cv-stage">
              <div
                className="cv-sheet"
                style={{
                  height: q.T?.land ? '58%' : '88%',
                  aspectRatio: q.T?.aspect ?? '105/148',
                  background: q.P?.color ?? '#f4eee0',
                }}
              >
                {pvImg ? (
                  <span className="cv-sheet-img" style={{ backgroundImage: `url("${pvImg}")` }} />
                ) : (
                  <span style={{ fontFamily: F.font, fontSize: pvFont, color: q.I?.color ?? '#1b2440' }}>{previewText}</span>
                )}
              </div>
            </div>

            <div className="cv-receipt">
              <h2 className="cv-receipt-title">{t('co.estimate2')}</h2>
              {q.lines.length ? (
                <dl className="cv-lines">
                  {q.lines.map((l) => (
                    <div key={l.label} className="cv-line">
                      <dt>{l.label}</dt>
                      <dd className={l.good ? 'good' : undefined}>{l.value}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="cv-note">{t('co.chooseFormat')}</p>
              )}
              <div className="cv-total">
                <span>{t('co.total')}</span>
                <b>{fmt(q.total)}</b>
              </div>
              <dl className="cv-eta">
                <div><dt>{t('co.robotTime')}</dt><dd>{q.robotTime}</dd></div>
                <div><dt>{t('co.deliveryBy')}</dt><dd>{q.eta}</dd></div>
              </dl>
            </div>
          </aside>
        </div>
      </div>
    </Page>
  )
}
