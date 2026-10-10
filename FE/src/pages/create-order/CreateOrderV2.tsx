import { useEffect, useRef, useState, type ReactNode } from 'react'
import Page from '../../components/layout/Page'
import { MethodLogos } from '../../components/ui/PaymentLogos'
import { CREATE_PAYS, FONT_STYLES, INKS, MODES, PAPERS, PENS, TYPES } from '../../constants/catalog'
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

const priceLabel = (p: number) => (p ? '+' + fmt(p) : 'Included')

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

  const q = quote({ type, paper, pen, ink, qty, mode, text, hasUpload: !!upload, strokes })
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
  const missing = ['Pick a format', 'Add your content', 'Choose paper, pen and ink', 'Fill in delivery and payment'][done.indexOf(false)]

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
          <span className="vh-eyebrow">New order · Fairino FR3</span>
          <h1 className="cv-title">Write it once.<br />The robot does the rest.</h1>
        </header>

        <div className="cv-shell">
          <form className="cv-form" onSubmit={(e) => { e.preventDefault(); submit() }}>
            <Section n="01" title="Format" hint="Size sets the base price and robot time." state={stateOf(0)}>
              <div className="cv-list" role="radiogroup" aria-label="Format">
                {TYPES.map((o) => (
                  <Row
                    key={o.id}
                    on={type === o.id}
                    onPick={() => setType(o.id)}
                    lead={(() => {
                      const s = Math.min(44 / o.w, 32 / o.h)
                      return <span className="cv-paper" style={{ width: Math.round(o.w * s), height: Math.round(o.h * s) }} />
                    })()}
                    name={o.name}
                    sub={o.size}
                    meta={`from ${fmt(o.base)}`}
                  />
                ))}
              </div>
            </Section>

            <Section n="02" title="Content" hint="Type it, upload it, or draw it. The AI turns any of them into a pen path." state={stateOf(1)}>
              <div className="cv-tabs" role="tablist" aria-label="Input method">
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    role="tab"
                    aria-selected={mode === m.id}
                    className={`cv-tab${mode === m.id ? ' on' : ''}`}
                    onClick={() => setMode(m.id)}
                  >
                    {m.label}
                    <span>{m.desc}</span>
                  </button>
                ))}
              </div>

              {mode === 'text' && (
                <>
                  <textarea
                    className="cv-text"
                    rows={4}
                    value={text}
                    aria-label="Your message"
                    placeholder="Viết lời chúc của bạn… e.g. Chúc Mừng Năm Mới, An Khang Thịnh Vượng"
                    onChange={(e) => setText(e.target.value)}
                  />
                  <p className="cv-note">{text.length} / 120 characters included · +200₫ per extra character</p>
                  <div className="cv-fonts" role="radiogroup" aria-label="Single-line style">
                    {FONT_STYLES.map((s) => (
                      <button
                        key={s.id}
                        type="button"
                        role="radio"
                        aria-checked={fontStyle === s.id}
                        className={`cv-font${fontStyle === s.id ? ' on' : ''}`}
                        onClick={() => setFontStyle(s.id)}
                      >
                        <span style={{ fontFamily: s.font }}>Chữ đẹp</span>
                        <small>{s.name}</small>
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
                    <b>{upload ? upload.name : 'Drop a handwriting photo, or click to browse'}</b>
                    <span>PNG, JPG or PDF up to 20 MB · AI vectorization +30.000₫</span>
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
                      Remove file
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
                      {strokes} {strokes === 1 ? 'stroke' : 'strokes'} captured · write a few lines so the AI can learn your hand · +15.000₫
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
                      Clear canvas
                    </button>
                  </div>
                </>
              )}
            </Section>

            <Section n="03" title="Materials" hint="Paper, pen, ink. Prices are per piece." state={stateOf(2)}>
              <div className="cv-group">
                <span className="cv-label">Paper</span>
                <div className="cv-list" role="radiogroup" aria-label="Paper">
                  {PAPERS.map((o) => (
                    <Row
                      key={o.id}
                      on={paper === o.id}
                      onPick={() => setPaper(o.id)}
                      lead={<span className="cv-swatch" style={{ background: o.color }} />}
                      name={o.name}
                      sub={o.spec}
                      meta={priceLabel(o.price)}
                    />
                  ))}
                </div>
              </div>

              <div className={`cv-group${paper ? '' : ' cv-group--wait'}`}>
                <span className="cv-label">Pen</span>
                <div className="cv-list" role="radiogroup" aria-label="Pen">
                  {PENS.map((o) => (
                    <Row
                      key={o.id}
                      on={pen === o.id}
                      onPick={() => setPen(o.id)}
                      lead={<span className="cv-nib"><span style={{ height: o.w }} /></span>}
                      name={o.name}
                      sub={o.spec}
                      meta={priceLabel(o.price)}
                    />
                  ))}
                </div>
              </div>

              <div className={`cv-group${pen ? '' : ' cv-group--wait'}`}>
                <span className="cv-label">Ink</span>
                <div className="cv-list" role="radiogroup" aria-label="Ink">
                  {INKS.map((o) => (
                    <Row
                      key={o.id}
                      on={ink === o.id}
                      onPick={() => setInk(o.id)}
                      lead={<span className="cv-swatch cv-swatch--ink" style={{ background: o.color }} />}
                      name={o.name}
                      meta={priceLabel(o.price)}
                    />
                  ))}
                </div>
              </div>

              <div className="cv-qty">
                <div>
                  <span className="cv-label">Quantity</span>
                  <p className="cv-note">10% off from 10 pcs · 20% off from 50 pcs</p>
                </div>
                <div className="cv-stepper">
                  <button type="button" aria-label="Decrease" onClick={() => clampQty(qty - 1)}>−</button>
                  <input type="number" aria-label="Quantity" min={1} max={500} value={qty} onChange={(e) => clampQty(+e.target.value)} />
                  <button type="button" aria-label="Increase" onClick={() => clampQty(qty + 1)}>+</button>
                </div>
              </div>
            </Section>

            <Section n="04" title="Delivery and payment" hint="Where it goes, and how you pay the deposit." state={stateOf(3)}>
              <div className="cv-fields">
                <label className="cv-field">
                  <span>Full name</span>
                  <input autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} />
                </label>
                <label className="cv-field">
                  <span>Phone</span>
                  <input placeholder="0901 234 567" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
                </label>
                <label className="cv-field cv-field--wide">
                  <span>Delivery address</span>
                  <input autoComplete="street-address" value={address} onChange={(e) => setAddress(e.target.value)} />
                </label>
              </div>
              <div className="cv-group">
                <span className="cv-label">Payment</span>
                <div className="cv-list" role="radiogroup" aria-label="Payment">
                  {CREATE_PAYS.map((o) => (
                    <Row
                      key={o.id}
                      on={pay === o.id}
                      onPick={() => setPay(o.id)}
                      lead={<MethodLogos id={o.id} />}
                      name={o.name}
                      sub={o.spec}
                    />
                  ))}
                </div>
              </div>
            </Section>

            <div className="cv-submit">
              <p className="cv-note">{allDone ? 'Everything is set. Price locks when you submit.' : missing}</p>
              <button type="submit" className="vh-btn vh-btn--md vh-btn--primary" disabled={!allDone}>
                Submit and generate sketch →
              </button>
            </div>
          </form>

          <aside className="cv-rail" aria-label="Estimate">
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
              <h2 className="cv-receipt-title">Estimate</h2>
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
                <p className="cv-note">Choose a format to start.</p>
              )}
              <div className="cv-total">
                <span>Total</span>
                <b>{fmt(q.total)}</b>
              </div>
              <dl className="cv-eta">
                <div><dt>Robot time</dt><dd>{q.robotTime}</dd></div>
                <div><dt>Delivery by</dt><dd>{q.eta}</dd></div>
              </dl>
            </div>
          </aside>
        </div>
      </div>
    </Page>
  )
}
