import { useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import {
  CREATE_PAYS, FONT_STYLES, INKS, MODES, PAPERS, PENS, STEP_LABELS, TYPES,
} from '../../constants/catalog'
import { navigate, orderPath } from '../../router/router'
import { addOrder, createOrderId } from '../../store/store'
import type { InputMode, Order, OrderSpec } from '../../types'
import { fmt, todayLabel } from '../../utils/format'
import { quote } from '../../utils/pricing'
import DrawPad from './DrawPad'
import './create-order.css'

interface Upload {
  name: string
  url: string
  isImg: boolean
  dataUrl?: string
}

function initialMode(): InputMode {
  const m = /mode=(text|upload|draw)/.exec(window.location.hash)
  return (m?.[1] as InputMode | undefined) ?? 'text'
}

const priceLabel = (p: number) => (p ? '+' + fmt(p) : 'Included')

export default function CreateOrder() {
  const [step, setStep] = useState(0)
  const [maxStep, setMaxStep] = useState(0)
  const [type, setType] = useState<string | null>(null)
  const [mode, setMode] = useState<InputMode>(initialMode)
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

  // Release the blob URL when the upload is replaced or the page unmounts.
  const blobRef = useRef<string | null>(null)
  useEffect(() => {
    blobRef.current = upload?.url ?? null
  }, [upload])
  useEffect(() => () => {
    if (blobRef.current) URL.revokeObjectURL(blobRef.current)
  }, [])

  const q = quote({ type, paper, pen, ink, qty, mode, text, hasUpload: !!upload, strokes })
  const F = FONT_STYLES.find((f) => f.id === fontStyle)!

  const valid = (i: number) => {
    if (i === 0) return !!type
    if (i === 1) return mode === 'text' ? text.trim().length > 0 : mode === 'upload' ? !!upload : strokes > 0
    if (i === 2) return !!(paper && pen && ink && qty >= 1)
    return !!(name.trim() && phone.trim().length >= 8 && address.trim() && pay)
  }
  const ok = valid(step)
  const hints = [
    'Pick a format',
    mode === 'text' ? 'Write something first' : mode === 'upload' ? 'Add an image' : 'Draw at least one stroke',
    !paper ? 'Choose paper' : !pen ? 'Choose a pen' : 'Choose ink',
    'Fill in contact & payment',
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
    addOrder(order)
    navigate(orderPath(order.id, 'review'))
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
    { k: 'Type', v: q.T ? `${q.T.name} · ${q.T.size}` : '—', to: 0 },
    {
      k: 'Content',
      v: mode === 'text'
        ? `“${text.trim().slice(0, 48) || '—'}${text.trim().length > 48 ? '…' : ''}” · ${F.name}`
        : mode === 'upload' ? (upload ? `Image · ${upload.name}` : '—') : `${strokes} hand-drawn strokes`,
      to: 1,
    },
    { k: 'Materials', v: [q.P?.name, q.N?.name, q.I?.name].filter(Boolean).join(' · ') || '—', to: 2 },
    { k: 'Quantity', v: `${qty} ${qty > 1 ? 'pieces' : 'piece'}`, to: 2 },
  ]

  return (
    <Page label="Create Order">
      <div className="vh-head-text">
        <span className="vh-eyebrow">New order · Fairino FR3</span>
        <h1 className="vh-h1 vh-h1--lg">Create your order.</h1>
      </div>

      <div className="vh-cols">
        <div className="vh-col" style={{ gap: 28 }}>
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
                    <span>{label}</span>
                  </span>
                </button>
              )
            })}
          </div>

          <div className="vh-panel" style={{ gap: 24 }}>
            {step === 0 && (
              <>
                <div className="vh-stack">
                  <h2 className="vh-h2" style={{ fontSize: 24 }}>What are we writing?</h2>
                  <p className="vh-lede">Pick a format. Size sets the base price and robot time.</p>
                </div>
                <div className="vh-choice-grid vh-choice-grid--200">
                  {TYPES.map((o) => (
                    <button key={o.id} className={`vh-choice co-type${type === o.id ? ' on' : ''}`} onClick={() => setType(o.id)}>
                      <div className="co-type-stage vh-stage-sm" style={{ height: 96, borderRadius: 12 }}>
                        <div className="co-type-paper" style={{ width: o.w, height: o.h }} />
                      </div>
                      <div className="vh-stack" style={{ gap: 4 }}>
                        <span className="co-type-name">{o.name}</span>
                        <span className="co-type-size">{o.size}</span>
                      </div>
                      <span className="co-type-price">from {fmt(o.base)}</span>
                    </button>
                  ))}
                </div>
              </>
            )}

            {step === 1 && (
              <>
                <div className="vh-stack">
                  <h2 className="vh-h2" style={{ fontSize: 24 }}>Add your content</h2>
                  <p className="vh-lede">Choose how you’ll provide it — the AI turns any of them into a pen trajectory.</p>
                </div>

                <div className="vh-choice-grid">
                  {MODES.map((m, i) => (
                    <button key={m.id} className={`vh-choice${mode === m.id ? ' on' : ''}`} style={{ gap: 6 }} onClick={() => setMode(m.id)}>
                      <span className="co-mode-num">0{i + 1}</span>
                      <span className="vh-choice-name">{m.label}</span>
                      <span className="vh-choice-sub" style={{ lineHeight: 1.45 }}>{m.desc}</span>
                    </button>
                  ))}
                </div>

                {mode === 'text' && (
                  <>
                    <div className="vh-stack" style={{ gap: 10 }}>
                      <textarea
                        className="vh-textarea co-text"
                        rows={5}
                        value={text}
                        placeholder="Viết lời chúc của bạn… e.g. Chúc Mừng Năm Mới — An Khang Thịnh Vượng"
                        onChange={(e) => setText(e.target.value)}
                      />
                      <div className="co-meta vh-mono">
                        <span>{text.length} / 120 chars included</span>
                        <span>+200₫ / char beyond 120</span>
                      </div>
                    </div>
                    <div className="vh-stack" style={{ gap: 10 }}>
                      <span className="vh-label">Single-line style</span>
                      <div className="vh-choice-grid" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(min(100%,150px),1fr))' }}>
                        {FONT_STYLES.map((s) => (
                          <button key={s.id} className={`vh-choice${fontStyle === s.id ? ' on' : ''}`} style={{ gap: 6 }} onClick={() => setFontStyle(s.id)}>
                            <span className="co-font-sample" style={{ fontFamily: s.font }}>Chữ đẹp</span>
                            <span className="co-font-name">{s.name}</span>
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
                      <span className="co-drop-title">Drop a handwriting photo or click to browse</span>
                      <span className="co-meta vh-mono">PNG · JPG · PDF — up to 20 MB · AI vectorization +30.000₫</span>
                    </label>
                    {upload && (
                      <div className="co-file-row">
                        <div
                          className="co-file-thumb"
                          style={{ backgroundImage: upload.isImg ? `url("${upload.url}")` : 'none' }}
                        />
                        <div className="co-file-text">
                          <span className="co-file-name">{upload.name}</span>
                          <span className="co-file-ok vh-mono">Ready · strokes will be skeletonized</span>
                        </div>
                        <button
                          className="vh-btn vh-btn--ghost vh-btn--sm"
                          onClick={() => {
                            URL.revokeObjectURL(upload.url)
                            setUpload(null)
                          }}
                        >
                          Remove
                        </button>
                      </div>
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
                    <div className="co-draw-foot">
                      <span className="co-meta vh-mono">
                        {strokes} {strokes === 1 ? 'stroke' : 'strokes'} captured · write a few lines so the AI can learn your hand · +15.000₫
                      </span>
                      <button
                        className="vh-btn vh-btn--ghost vh-btn--sm"
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
              </>
            )}

            {step === 2 && (
              <>
                <div className="vh-stack">
                  <h2 className="vh-h2" style={{ fontSize: 24 }}>Paper → pen → ink</h2>
                  <p className="vh-lede">Each choice unlocks the next. Prices are per piece.</p>
                </div>

                <div className="co-group">
                  <span className="co-group-label">A · PAPER</span>
                  <div className="vh-choice-grid">
                    {PAPERS.map((o) => (
                      <button key={o.id} className={`vh-choice co-row-choice${paper === o.id ? ' on' : ''}`} onClick={() => setPaper(o.id)}>
                        <span className="co-swatch" style={{ background: o.color }} />
                        <span className="co-choice-text">
                          <span className="vh-choice-name">{o.name}</span>
                          <span className="vh-choice-sub">{o.spec}</span>
                          <span className="co-price">{priceLabel(o.price)}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className={`co-group${paper ? '' : ' locked'}`}>
                  <span className="co-group-label">B · PEN</span>
                  <div className="vh-choice-grid">
                    {PENS.map((o) => (
                      <button key={o.id} className={`vh-choice${pen === o.id ? ' on' : ''}`} style={{ gap: 12 }} onClick={() => setPen(o.id)}>
                        <span className="co-nib"><span style={{ height: o.w }} /></span>
                        <span className="co-choice-text">
                          <span className="vh-choice-name">{o.name}</span>
                          <span className="vh-choice-sub">{o.spec}</span>
                          <span className="co-price">{priceLabel(o.price)}</span>
                        </span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className={`co-group${pen ? '' : ' locked'}`}>
                  <span className="co-group-label">C · INK</span>
                  <div className="co-inks">
                    {INKS.map((o) => (
                      <button key={o.id} className={`co-ink${ink === o.id ? ' on' : ''}`} onClick={() => setInk(o.id)}>
                        <span className="co-ink-dot" style={{ background: o.color }} />
                        <span className="co-ink-name">{o.name}</span>
                        <span className="co-price">{priceLabel(o.price)}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="co-qty">
                  <div className="vh-stack" style={{ gap: 4 }}>
                    <span className="co-qty-title">Quantity</span>
                    <span className="co-qty-sub">10% off from 10 pcs · 20% off from 50 pcs</span>
                  </div>
                  <div className="co-stepper">
                    <button aria-label="Decrease" onClick={() => clampQty(qty - 1)}>−</button>
                    <input type="number" min={1} max={500} value={qty} onChange={(e) => clampQty(+e.target.value)} />
                    <button aria-label="Increase" onClick={() => clampQty(qty + 1)}>+</button>
                  </div>
                </div>
              </>
            )}

            {step === 3 && (
              <>
                <div className="vh-stack">
                  <h2 className="vh-h2" style={{ fontSize: 24 }}>Review &amp; submit</h2>
                  <p className="vh-lede">Check the details, then tell us where to send it.</p>
                </div>
                <div className="vh-rows">
                  {summary.map((r) => (
                    <div key={r.k} className="co-sum-row">
                      <span className="co-sum-k vh-mono">{r.k}</span>
                      <span className="co-sum-v">{r.v}</span>
                      <button className="vh-link" onClick={() => goTo(r.to)}>Edit</button>
                    </div>
                  ))}
                </div>
                <div className="vh-form-grid">
                  <input className="vh-input" placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
                  <input className="vh-input" placeholder="Phone (e.g. 0901 234 567)" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} />
                </div>
                <input className="vh-input" placeholder="Delivery address" value={address} onChange={(e) => setAddress(e.target.value)} />
                <div className="vh-stack" style={{ gap: 10 }}>
                  <span className="vh-label">Payment</span>
                  <div className="vh-choice-grid vh-choice-grid--170">
                    {CREATE_PAYS.map((o) => (
                      <button key={o.id} className={`vh-choice${pay === o.id ? ' on' : ''}`} style={{ gap: 3 }} onClick={() => setPay(o.id)}>
                        <span className="vh-choice-name">{o.name}</span>
                        <span className="vh-choice-sub">{o.spec}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}

            <div className="co-nav">
              <button className="vh-btn vh-btn--ghost vh-btn--md co-back" disabled={step === 0} onClick={() => step > 0 && goTo(step - 1)}>
                ← Back
              </button>
              <div className="co-next-wrap">
                <span className="co-hint">{ok ? '' : hints[step]}</span>
                <button
                  className={`vh-btn vh-btn--md ${step === 3 ? 'vh-btn--primary' : 'vh-btn--white'}`}
                  disabled={!ok}
                  onClick={next}
                >
                  {step === 3 ? 'Submit & generate sketch →' : 'Continue →'}
                </button>
              </div>
            </div>
          </div>
        </div>

        <aside className="vh-aside" style={{ boxShadow: '0 30px 60px var(--sh-35)' }}>
          <div className="co-est-head">
            <span>Instant estimate</span>
            <span className="co-live vh-mono"><i />LIVE</span>
          </div>
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
                <div className="co-preview-img" style={{ backgroundImage: `url("${pvImg}")` }} />
              ) : (
                <span style={{ fontFamily: F.font, fontSize: pvFont, color: q.I?.color ?? '#1b2440' }}>{previewText}</span>
              )}
            </div>
          </div>
          <div className="vh-rows">
            {q.lines.length ? (
              q.lines.map((l) => (
                <div key={l.label} className="vh-row vh-row--mono">
                  <span style={{ fontFamily: 'inherit' }}>{l.label}</span>
                  <span style={l.good ? { color: 'var(--good)' } : undefined}>{l.value}</span>
                </div>
              ))
            ) : (
              <div className="vh-row"><span>Choose an order type to start</span><span>—</span></div>
            )}
          </div>
          <div className="vh-total-row" style={{ alignItems: 'baseline' }}>
            <span>Total</span>
            <span style={{ fontSize: 30, letterSpacing: '-.03em' }}>{fmt(q.total)}</span>
          </div>
          <div className="co-eta">
            <div><span className="vh-mono">ROBOT TIME</span><b>{q.robotTime}</b></div>
            <div><span className="vh-mono">DELIVERY BY</span><b>{q.eta}</b></div>
          </div>
          <span className="co-fine">Estimate updates as you choose. Price locks at submit.</span>
        </aside>
      </div>
    </Page>
  )
}
