import { useCallback, useEffect, useRef, useState } from 'react'
import Page from '../../components/layout/Page'
import OrderPreview from '../../components/ui/OrderPreview'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useSaveQueue } from '../../hooks/useSaveQueue'
import { useT } from '../../i18n'
import { Link, navigate, orderPath } from '../../router/router'
import {
  ACCEPTED_UPLOADS, MAX_UPLOAD_MB, createOrder, deleteInput, estimate, getInks, getOrder, getPapers, getPens, getTemplates,
  incompleteFields, orderErrorKey, patchOrder, provideInfo, putText, submitOrder, templatePreviewUrl, uploadOriginal,
  type Alignment, type Estimate, type Order, type OrderPatch, type OrderType,
} from '../../services/orders'
import { useUser } from '../../store/store'
import type { InputMode } from '../../types'
import { fmt } from '../../utils/format'
import { draftPathFor, drawPathFor } from './draft'
import './create-order.css'

const MODES: InputMode[] = ['text', 'upload', 'draw']
const STEPS = ['co.step.0', 'co.step.1', 'co.step.2']
const ALIGNMENTS: Alignment[] = ['LEFT', 'CENTER', 'RIGHT', 'JUSTIFY']
const MAX_QTY = 10000

const typeOf = (m: InputMode): OrderType => (m === 'upload' ? 'OT1_COPY_RESTORE' : 'OT3_TEMPLATE')

function initialMode(): InputMode | null {
  const m = /mode=(text|upload|draw)/.exec(window.location.hash)
  return (m?.[1] as InputMode | undefined) ?? null
}

/** The order is a draft on the server from the first thing the customer enters; every change is saved there. */
export default function CreateOrder({ orderId: given = null }: { orderId?: number | null }) {
  const t = useT()
  const user = useUser()

  const [order, setOrder] = useState<Order | null>(null)
  const orderRef = useRef<Order | null>(null)
  const [loading, setLoading] = useState(given !== null)
  const [step, setStep] = useState(0)
  const [maxStep, setMaxStep] = useState(0)
  const [mode, setMode] = useState<InputMode>(() => initialMode() ?? 'text')
  const [text, setText] = useState('')
  const [templateId, setTemplateId] = useState<number | null>(null)
  const [alignment, setAlignment] = useState<Alignment | null>(null)
  const [fontSize, setFontSize] = useState('')
  const [paperId, setPaperId] = useState<number | null>(null)
  const [penId, setPenId] = useState<number | null>(null)
  const [inkId, setInkId] = useState<number | null>(null)
  const [suggest, setSuggest] = useState(false)
  const [qty, setQty] = useState(1)
  const [note, setNote] = useState('')
  const [terms, setTerms] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(0)
  const [est, setEst] = useState<Estimate | null>(null)

  const papers = useAsync(getPapers, [])
  const templates = useAsync(getTemplates, [])
  const pens = useAsync(() => getPens(paperId), [paperId])
  const inks = useAsync(() => (penId ? getInks(penId) : Promise.resolve([])), [penId])

  // ---------- saving: one queue, so changes reach the server in the order they were made ----------

  const { enqueue, idle, pending } = useSaveQueue()
  const creating = useRef<PromiseLike<Order> | null>(null)
  const loaded = useRef(false)
  const lastSaved = useRef<string>('')
  const wanted = useRef<OrderType>(typeOf(mode))
  wanted.current = typeOf(mode)

  const adopt = useCallback((o: Order) => {
    orderRef.current = o
    setOrder(o)
  }, [])

  /** The draft on the server. It is created the first time something has to be saved. */
  const ensure = useCallback(async () => {
    if (orderRef.current) return orderRef.current
    creating.current ??= createOrder(wanted.current, 1).then((o) => {
      adopt(o)
      navigate(draftPathFor(o.id), { replace: true })
      return o
    }).finally(() => {
      creating.current = null
    })
    return creating.current
  }, [adopt])

  const fail = (e: unknown) => setErr(orderErrorKey(e))

  const patch = useCallback((p: OrderPatch) => {
    setErr('')
    return enqueue(async () => {
      const o = await ensure()
      adopt({ ...(await patchOrder(o.id, p)), inputs: orderRef.current?.inputs ?? o.inputs })
    }).then(undefined, fail)
  }, [adopt, enqueue, ensure])

  // ---------- loading an existing draft ----------

  useEffect(() => {
    if (given === (orderRef.current?.id ?? null)) return
    orderRef.current = null
    loaded.current = false
    lastSaved.current = ''
    setOrder(null)
    setStep(0)
    setMaxStep(0)
    setTerms(false)
    setErr('')
    setEst(null)
    if (given === null) {
      setText(''); setTemplateId(null); setAlignment(null); setFontSize('')
      setPaperId(null); setPenId(null); setInkId(null); setSuggest(false); setQty(1); setNote('')
      setLoading(false)
      return
    }
    setLoading(true)
    getOrder(given)
      .then((o) => {
        if (o.status !== 'DRAFT' && o.status !== 'NEED_INFO') {
          navigate(orderPath(o.id, 'review'), { replace: true })
          return
        }
        adopt(o)
        const tx = o.inputs.find((i) => i.kind === 'TEXT_CONTENT')
        setText(tx?.text ?? '')
        setTemplateId(tx?.templateId ?? null)
        setAlignment(tx?.alignment ?? null)
        setFontSize(tx?.fontSizeMm ? String(tx.fontSizeMm) : '')
        setPaperId(o.paperId); setPenId(o.penId); setInkId(o.inkId)
        setSuggest(o.workshopSuggest); setQty(o.quantity); setNote(o.note ?? '')
        setMode(initialMode() ?? (o.type === 'OT1_COPY_RESTORE' ? 'upload' : !tx && o.inputs.some((i) => i.kind === 'CANVAS') ? 'draw' : 'text'))
        // Go to the first step that still needs something.
        const hasContent = o.inputs.length > 0
        const hasMaterials = o.workshopSuggest || (o.paperId && o.penId && o.inkId)
        const s = hasContent ? (hasMaterials ? 2 : 1) : 0
        setStep(s)
        setMaxStep(s)
      })
      .catch((e) => {
        setErr(orderErrorKey(e))
      })
      .finally(() => setLoading(false))
  }, [given, adopt])

  // First template is the default, so typing text is enough to start a draft.
  useEffect(() => {
    if (templateId === null && templates.data?.length) setTemplateId(templates.data[0].id)
  }, [templates.data, templateId])

  // A paper change can make the chosen pen or ink invalid.
  useEffect(() => {
    if (penId && pens.data && !pens.data.some((p) => p.id === penId)) {
      setPenId(null)
      setInkId(null)
    }
  }, [pens.data, penId])
  useEffect(() => {
    if (inkId && inks.data && !inks.data.some((i) => i.id === inkId)) setInkId(null)
  }, [inks.data, inkId])

  // ---------- text: saved shortly after the typing stops ----------

  const dText = useDebounced(text, 700)
  const dSize = useDebounced(fontSize, 700)
  const textKey = `${dText}|${templateId}|${alignment}|${dSize}`
  useEffect(() => {
    if (loading) return
    if (!loaded.current) {
      loaded.current = true
      const tx = orderRef.current?.inputs.find((i) => i.kind === 'TEXT_CONTENT')
      lastSaved.current = `${tx?.text ?? ''}|${tx?.templateId ?? null}|${tx?.alignment ?? null}|${tx?.fontSizeMm ? String(tx.fontSizeMm) : ''}`
    }
    // Wait until the typing has settled, so a value still on its way is never saved.
    if (text !== dText || fontSize !== dSize) return
    if (mode !== 'text' || !dText.trim() || templateId === null || textKey === lastSaved.current) return
    lastSaved.current = textKey
    setErr('')
    const size = Number(dSize)
    enqueue(async () => {
      const o = await ensure()
      const input = await putText(o.id, {
        text_content: dText,
        template_id: templateId,
        alignment,
        font_size_mm: dSize && size > 0 ? size : null,
      })
      const cur = orderRef.current ?? o
      adopt({ ...cur, inputs: [...cur.inputs.filter((i) => i.kind !== 'TEXT_CONTENT'), input] })
    }).then(undefined, (e: unknown) => {
      lastSaved.current = ''
      fail(e)
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [textKey, mode, loading])

  // ---------- materials, quantity, note ----------

  const pickPaper = (id: number) => {
    setPaperId(id)
    setPenId(null)
    setInkId(null)
    void patch({ paper_type_id: id, pen_type_id: null, ink_color_id: null })
  }
  const pickPen = (id: number) => {
    setPenId(id)
    setInkId(null)
    void patch({ pen_type_id: id, ink_color_id: null })
  }
  const pickInk = (id: number) => {
    setInkId(id)
    void patch({ ink_color_id: id })
  }
  const toggleSuggest = (on: boolean) => {
    setSuggest(on)
    void patch({ workshop_suggest_materials: on })
  }

  const dQty = useDebounced(qty, 500)
  const dNote = useDebounced(note, 700)
  const sentQty = useRef<number | null>(null)
  const sentNote = useRef<string | null>(null)
  useEffect(() => {
    if (loading || qty !== dQty || note !== dNote) return
    const o = orderRef.current
    sentQty.current ??= o?.quantity ?? 1
    sentNote.current ??= o?.note ?? ''
    const p: OrderPatch = {}
    if (dQty !== sentQty.current) { p.quantity = dQty; sentQty.current = dQty }
    if (dNote !== sentNote.current) { p.customer_note = dNote.trim() ? dNote : null; sentNote.current = dNote }
    if (Object.keys(p).length) void patch(p)
  }, [dQty, dNote, loading, patch])

  const clampQty = (n: number) => setQty(Math.max(1, Math.min(MAX_QTY, Math.round(n) || 1)))

  // ---------- content mode ----------

  const chooseMode = async (m: InputMode) => {
    if (m === mode && m !== 'draw') return
    setErr('')
    const next = typeOf(m)
    const cur = orderRef.current
    if (cur && cur.type !== next) {
      const stale = cur.inputs.filter((i) => (next === 'OT1_COPY_RESTORE' ? i.kind !== 'ORIGINAL_IMAGE' : i.kind === 'ORIGINAL_IMAGE'))
      if (stale.length && !window.confirm(t('co.switchWarn'))) return
      setBusy(true)
      try {
        await enqueue(async () => {
          for (const i of stale) await deleteInput(cur.id, i.id)
          const o = await patchOrder(cur.id, { order_type: next })
          adopt({ ...o, inputs: cur.inputs.filter((i) => !stale.includes(i)) })
        })
      } catch (e) {
        fail(e)
        return
      } finally {
        setBusy(false)
      }
    }
    setMode(m)
    if (m === 'draw') await openCanvas()
  }

  const openCanvas = async () => {
    setErr('')
    setBusy(true)
    try {
      wanted.current = 'OT3_TEMPLATE'
      const o = await enqueue(ensure)
      if (o.type !== 'OT3_TEMPLATE') await enqueue(async () => adopt({ ...(await patchOrder(o.id, { order_type: 'OT3_TEMPLATE' })), inputs: o.inputs }))
      navigate(drawPathFor(o.id))
    } catch (e) {
      fail(e)
    } finally {
      setBusy(false)
    }
  }

  const addFiles = async (files: FileList | null) => {
    if (!files?.length) return
    setErr('')
    for (const f of Array.from(files)) {
      if (!ACCEPTED_UPLOADS.includes(f.type)) { setErr('err.fileType'); continue }
      if (f.size > MAX_UPLOAD_MB * 1024 * 1024) { setErr('err.fileTooLarge'); continue }
      setUploading((n) => n + 1)
      try {
        wanted.current = 'OT1_COPY_RESTORE'
        const input = await enqueue(async () => {
          const o = await ensure()
          if (o.type !== 'OT1_COPY_RESTORE') adopt({ ...(await patchOrder(o.id, { order_type: 'OT1_COPY_RESTORE' })), inputs: o.inputs })
          return uploadOriginal(o.id, f)
        })
        const cur = orderRef.current
        if (cur) adopt({ ...cur, inputs: [...cur.inputs, input] })
      } catch (e) {
        fail(e)
      } finally {
        setUploading((n) => n - 1)
      }
    }
  }

  const removeInput = (id: number) => {
    const cur = orderRef.current
    if (!cur) return
    setErr('')
    enqueue(async () => {
      await deleteInput(cur.id, id)
      const now = orderRef.current ?? cur
      adopt({ ...now, inputs: now.inputs.filter((i) => i.id !== id) })
    }).then(undefined, fail)
  }

  // ---------- estimate ----------

  const dTextForEst = useDebounced(text, 900)
  useEffect(() => {
    if (loading) return
    let live = true
    estimate({
      order_type: typeOf(mode),
      quantity: Math.max(1, dQty),
      paper_type_id: paperId, pen_type_id: penId, ink_color_id: inkId,
      ...(order ? { order_id: order.id } : { text: mode === 'text' ? dTextForEst || null : null }),
    })
      .then((r) => live && setEst(r))
      .catch(() => live && setEst(null))
    return () => {
      live = false
    }
    // The saved time changes whenever the server re-prices the draft.
  }, [loading, mode, dQty, paperId, penId, inkId, order?.id, order?.savedAt, dTextForEst, pending === 0]) // eslint-disable-line react-hooks/exhaustive-deps

  // ---------- steps ----------

  const photos = order?.inputs.filter((i) => i.kind === 'ORIGINAL_IMAGE') ?? []
  const canvas = order?.inputs.find((i) => i.kind === 'CANVAS')
  const strokes = canvas?.canvas?.strokes.length ?? 0
  const materialsOk = suggest || !!(paperId && penId && inkId)

  const valid = (i: number) => {
    if (i === 0) return mode === 'text' ? text.trim().length > 0 && templateId !== null : mode === 'upload' ? photos.length > 0 : strokes > 0
    if (i === 1) return materialsOk && qty >= 1
    return terms
  }
  const ok = valid(step) && !busy && uploading === 0
  const hints = [
    t(mode === 'text' ? 'co.hint0.text' : mode === 'upload' ? 'co.hint0.upload' : 'co.hint0.draw'),
    t(!materialsOk ? (!paperId ? 'co.hint1.paper' : !penId ? 'co.hint1.pen' : 'co.hint1.ink') : 'co.hint1.qty'),
    t('co.hint2'),
  ]

  const goTo = (i: number) => {
    setStep(i)
    setMaxStep((m) => Math.max(m, i))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const submit = async () => {
    if (!terms) return
    setErr('')
    setBusy(true)
    try {
      await idle() // everything typed so far is saved first
      const o = await ensure()
      const sent = o.status === 'NEED_INFO' ? await provideInfo(o.id) : await submitOrder(o.id)
      navigate(orderPath(sent.id, 'review'))
    } catch (e) {
      const fields = incompleteFields(e)
      if (fields.includes('inputs')) goTo(0)
      else if (fields.includes('materials')) goTo(1)
      fail(e)
    } finally {
      setBusy(false)
    }
  }

  const next = () => {
    if (!ok) return
    if (step < 2) goTo(step + 1)
    else void submit()
  }

  const openStep = (i: number) => (i <= maxStep ? goTo(i) : undefined)

  // ---------- guards ----------

  if (!user) {
    return (
      <Page label="Create Order" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <h1 className="vh-h1">{t('co.signInTitle')}</h1>
          <p className="vh-lede">{t('co.signInBody')}</p>
          <button className="vh-btn vh-btn--primary" onClick={() => navigate(`/login?next=${encodeURIComponent('/create-order')}`)}>{t('nav.signIn')}</button>
        </div>
      </Page>
    )
  }
  if (user.role !== 'customer') {
    return (
      <Page label="Create Order" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <h1 className="vh-h1">{t('co.customerOnlyTitle')}</h1>
          <p className="vh-lede">{t('co.customerOnlyBody')}</p>
        </div>
      </Page>
    )
  }
  if (loading) {
    return (
      <Page label="Create Order" width={720}>
        <p className="vh-lede" role="status">{t('co.loading')}</p>
      </Page>
    )
  }
  if (given !== null && !order) {
    return (
      <Page label="Create Order" width={720}>
        <div className="vh-panel" style={{ alignItems: 'flex-start' }}>
          <h1 className="vh-h1">{t('np.title')}</h1>
          {err && <p className="lg-error" role="alert">{t(err)}</p>}
          <Link to="/account/drafts" className="vh-btn vh-btn--primary">{t('co.toDrafts')}</Link>
        </div>
      </Page>
    )
  }

  // ---------- view ----------

  const paper = papers.data?.find((p) => p.id === paperId)
  const pen = pens.data?.find((p) => p.id === penId)
  const ink = inks.data?.find((i) => i.id === inkId)
  const template = templates.data?.find((x) => x.id === templateId)
  const materialsLabel = suggest ? t('co.sum.suggest') : [paper?.name, pen?.name, ink?.name].filter(Boolean).join(', ') || t('co.sum.notChosen')
  const range = est ? (est.priceMin === est.priceMax ? fmt(est.priceMax) : `${fmt(est.priceMin)} – ${fmt(est.priceMax)}`) : '–'
  const saveLabel = pending > 0 || uploading > 0 ? t('co.saving') : order ? t('co.saved') : ''
  const rewrite = order?.status === 'NEED_INFO'

  const summary = [
    {
      k: t('co.sum.content'),
      v: mode === 'text'
        ? t('co.sum.textIn', { text: `${text.trim().slice(0, 48)}${text.trim().length > 48 ? '…' : ''}`, font: template?.name ?? '' })
        : mode === 'upload' ? t(photos.length === 1 ? 'co.sum.photo' : 'co.sum.photos', { n: photos.length }) : t('co.sum.drawn', { n: strokes }),
      to: 0,
    },
    { k: t('co.sum.materials'), v: materialsLabel, to: 1 },
    { k: t('co.sum.qty'), v: t(qty > 1 ? 'co.pieces' : 'co.piece', { n: qty }), to: 1 },
    ...(note.trim() ? [{ k: t('co.sum.note'), v: note.trim(), to: 1 }] : []),
  ]

  return (
    <Page label="Create Order">
      <div className="co">
        <div className="vh-head-text">
          <span className="vh-eyebrow">{order ? `${t('co.eyebrow')} · ${order.code}` : t('co.eyebrow')}</span>
          <h1 className="vh-h1 vh-h1--lg">{t('co.h1')}</h1>
        </div>

        {rewrite && order?.infoRequestNote && (
          <div className="vh-callout vh-callout--amber" role="status">
            <b>{t('co.needInfo')}</b>
            <span>{order.infoRequestNote}</span>
          </div>
        )}

        <div className="co-shell">
          <div className="co-main">
            <div className="co-steps">
              {STEPS.map((key, i) => {
                const cur = i === step
                const done = i <= maxStep && !cur
                return (
                  <button key={key} className={`co-step${cur ? ' cur' : done ? ' done' : ''}`} disabled={i > maxStep} onClick={() => openStep(i)}>
                    <span className="co-step-bar" />
                    <span className="co-step-label">
                      <span className="co-step-num">0{i + 1}</span>
                      <span>{t(key)}</span>
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="co-body">
              {step === 0 && (
                <>
                  <div className="vh-stack">
                    <h2 className="co-h2">{t('co.s1.title')}</h2>
                    <p className="vh-lede">{t('co.s1.lede')}</p>
                  </div>

                  <div className="co-tray co-tray--3">
                    {MODES.map((m) => (
                      <button key={m} className={`co-opt${mode === m ? ' on' : ''}`} disabled={busy} onClick={() => void chooseMode(m)}>
                        <span className="co-opt-name">{t(`co.mode.${m}`)}</span>
                        <span className="co-opt-sub">{t(`co.mode.${m}.sub`)}</span>
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
                          maxLength={20000}
                          aria-label={t('co.message')}
                          placeholder={t('co.placeholder')}
                          onChange={(e) => setText(e.target.value)}
                        />
                        <div className="co-meta vh-mono">
                          <span>{t('co.chars', { n: text.length })}</span>
                          <span>{est ? t('co.charsCounted', { min: est.charsMin, max: est.charsMax }) : ''}</span>
                        </div>
                      </div>

                      <div className="co-group">
                        <span className="co-group-label">{t('co.styleLabel')}</span>
                        <div className="co-tray co-tray--3 co-tray--keep">
                          {(templates.data ?? []).map((s) => (
                            <button key={s.id} className={`co-opt co-font${templateId === s.id ? ' on' : ''}`} onClick={() => setTemplateId(s.id)}>
                              <img
                                className="co-font-preview"
                                src={templatePreviewUrl(s.id, dText || t('co.fontSample'))}
                                alt={t('co.templateAlt', { name: s.name })}
                                loading="lazy"
                              />
                              <span className="co-font-name">{s.name}</span>
                            </button>
                          ))}
                          {templates.loading && <span className="co-hint">{t('co.loading')}</span>}
                          {!!templates.error && <span className="co-hint">{t(orderErrorKey(templates.error))}</span>}
                        </div>
                      </div>

                      <div className="co-group">
                        <span className="co-group-label">{t('co.align')}</span>
                        <div className="co-tray co-tray--4 co-tray--keep">
                          <button className={`co-opt${alignment === null ? ' on' : ''}`} onClick={() => setAlignment(null)}>
                            <span className="co-opt-name">{t('co.align.auto')}</span>
                          </button>
                          {ALIGNMENTS.map((a) => (
                            <button key={a} className={`co-opt${alignment === a ? ' on' : ''}`} onClick={() => setAlignment(a)}>
                              <span className="co-opt-name">{t(`co.align.${a}`)}</span>
                            </button>
                          ))}
                        </div>
                      </div>

                      <label className="co-cell">
                        {t('co.fontSize')}
                        <input
                          inputMode="decimal"
                          placeholder={t('co.fontSizePh')}
                          value={fontSize}
                          onChange={(e) => setFontSize(e.target.value.replace(/[^\d.]/g, '').slice(0, 5))}
                        />
                      </label>
                    </>
                  )}

                  {mode === 'upload' && (
                    <>
                      <label
                        className="co-drop"
                        onDragOver={(e) => e.preventDefault()}
                        onDrop={(e) => {
                          e.preventDefault()
                          void addFiles(e.dataTransfer.files)
                        }}
                      >
                        <input type="file" multiple accept={ACCEPTED_UPLOADS.join(',')} className="co-file" onChange={(e) => { void addFiles(e.target.files); e.target.value = '' }} />
                        <span className="co-drop-icon">
                          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                            <path d="m17 8-5-5-5 5" />
                            <path d="M12 3v12" />
                          </svg>
                        </span>
                        <span className="co-drop-title">{t('co.dropPhoto')}</span>
                        <span className="co-meta vh-mono">{t('co.dropMeta', { mb: MAX_UPLOAD_MB })}</span>
                      </label>
                      {uploading > 0 && <p className="co-hint" role="status">{t('co.uploading')}</p>}
                      {photos.map((p, i) => (
                        <div key={p.id} className="co-file-row">
                          <div className="co-file-text">
                            <span className="co-file-name">{t('co.photoN', { n: i + 1 })}</span>
                            <span className={`co-file-ok vh-mono${p.qualityWarning ? ' warn' : ''}`}>
                              {t(p.qualityWarning ? 'co.qualityWarn' : 'co.fileReady')}
                            </span>
                          </div>
                          <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => removeInput(p.id)}>{t('co.remove')}</button>
                        </div>
                      ))}
                    </>
                  )}

                  {mode === 'draw' && (
                    <div className="co-sheet">
                      <div className="co-sheet-thumb">
                        {order && canvas?.canvas ? <OrderPreview order={{ ...order, inputs: [canvas] }} /> : <span className="vh-mono">{t('co.blank')}</span>}
                      </div>
                      <div className="co-sheet-text">
                        <span className="co-sheet-title">{t(strokes > 0 ? 'co.drawReady' : 'co.drawNone')}</span>
                        <span className="co-meta vh-mono">{t(strokes === 1 ? 'co.stroke' : 'co.strokes', { n: strokes })}</span>
                        <button className="vh-btn vh-btn--primary vh-btn--sm" disabled={busy} onClick={() => void openCanvas()}>
                          {t(strokes > 0 ? 'co.editCanvas' : 'co.openCanvas')}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}

              {step === 1 && (
                <>
                  <div className="vh-stack">
                    <h2 className="co-h2">{t('co.s2.title')}</h2>
                    <p className="vh-lede">{t('co.s2.lede')}</p>
                  </div>

                  <label className="co-switch">
                    <input type="checkbox" checked={suggest} onChange={(e) => toggleSuggest(e.target.checked)} />
                    <span className="co-switch-text">
                      <span className="co-opt-name">{t('co.suggest')}</span>
                      <span className="co-opt-sub">{t('co.suggestSub')}</span>
                    </span>
                  </label>

                  <div className={`co-group${suggest ? ' locked' : ''}`}>
                    <span className="co-group-label">{t('co.paper')}</span>
                    <div className="co-tray co-tray--4">
                      {(papers.data ?? []).map((o) => (
                        <button key={o.id} className={`co-opt co-opt--row${paperId === o.id ? ' on' : ''}`} onClick={() => pickPaper(o.id)}>
                          <span className="co-choice-text">
                            <span className="co-opt-name">{o.name}</span>
                            <span className="co-opt-sub">{t('co.paperSpec', { gsm: o.gsm, surface: o.surface, size: o.size })}</span>
                            <span className="co-price">{t('co.perSheet', { price: fmt(o.unitPrice) })}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                    {papers.loading && <span className="co-hint">{t('co.loading')}</span>}
                    {!!papers.error && <span className="co-hint">{t(orderErrorKey(papers.error))}</span>}
                  </div>

                  <div className={`co-group${suggest || !paperId ? ' locked' : ''}`}>
                    <span className="co-group-label">{t('co.pen')}</span>
                    <div className="co-tray co-tray--4">
                      {(pens.data ?? []).map((o) => (
                        <button key={o.id} className={`co-opt co-opt--pen${penId === o.id ? ' on' : ''}`} onClick={() => pickPen(o.id)}>
                          <span className="co-nib"><span style={{ height: Math.max(1, Math.min(10, o.strokeWidthMm * 6)) }} /></span>
                          <span className="co-choice-text">
                            <span className="co-opt-name">{o.name}</span>
                            <span className="co-opt-sub">{t('co.penSpec', { mm: o.strokeWidthMm })}</span>
                            <span className="co-price">{o.surcharge ? '+' + fmt(o.surcharge) : t('co.included')}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                    {!!paperId && !pens.loading && !pens.data?.length && <span className="co-hint">{t('co.noPens')}</span>}
                  </div>

                  <div className={`co-group${suggest || !penId ? ' locked' : ''}`}>
                    <span className="co-group-label">{t('co.ink')}</span>
                    <div className="co-inks">
                      {(inks.data ?? []).map((o) => (
                        <button key={o.id} className={`co-ink${inkId === o.id ? ' on' : ''}`} onClick={() => pickInk(o.id)}>
                          <span className="co-ink-dot" style={{ background: o.hex ?? 'var(--t5)' }} />
                          <span className="co-ink-name">{o.name}</span>
                          {o.unitPrice > 0 && <span className="co-price">+{fmt(o.unitPrice)}</span>}
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
                      <input type="number" aria-label={t('co.qty')} min={1} max={MAX_QTY} value={qty} onChange={(e) => clampQty(+e.target.value)} />
                      <button aria-label={t('co.inc')} onClick={() => clampQty(qty + 1)}>+</button>
                    </div>
                  </div>

                  <div className="co-field">
                    <label className="co-group-label" htmlFor="co-note">{t('co.noteLabel')}</label>
                    <textarea
                      id="co-note"
                      className="co-text"
                      rows={3}
                      maxLength={2000}
                      value={note}
                      placeholder={t('co.notePh')}
                      onChange={(e) => setNote(e.target.value)}
                    />
                  </div>
                </>
              )}

              {step === 2 && (
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
                    <div className="co-sum-row">
                      <span className="co-sum-k">{t('co.sum.estimate')}</span>
                      <span className="co-sum-v">{range}</span>
                    </div>
                  </div>
                  {!!order?.warnings.length && (
                    <div className="vh-callout vh-callout--amber" role="status">
                      <b>{t('co.warnings')}</b>
                      {order.warnings.map((w) => <span key={w}>{w}</span>)}
                    </div>
                  )}
                  <label className="co-switch">
                    <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} />
                    <span className="co-switch-text">
                      <span className="co-opt-name">{t('co.terms')}</span>
                      <span className="co-opt-sub">{t('co.termsSub')}</span>
                    </span>
                  </label>
                </>
              )}
            </div>

            {err && <p className="lg-error" role="alert">{t(err)}</p>}

            <div className="co-nav">
              <button className="vh-btn vh-btn--ghost vh-btn--md co-back" disabled={step === 0} onClick={() => step > 0 && goTo(step - 1)}>
                {t('co.back')}
              </button>
              <div className="co-next-wrap">
                <span className="co-hint" role="status">{ok ? saveLabel : hints[step]}</span>
                <button className={`vh-btn vh-btn--md ${step === 2 ? 'vh-btn--primary' : 'vh-btn--white'}`} disabled={!ok} onClick={next}>
                  {step === 2 ? t(rewrite ? 'co.resubmit' : busy ? 'co.sending' : 'co.submit') : t('co.continue')}
                </button>
              </div>
            </div>
          </div>

          <div className="co-side">
            <aside className="co-rail">
              <div className="co-preview">
                {mode === 'text' && templateId !== null && dText.trim() ? (
                  <img className="co-preview-img" src={templatePreviewUrl(templateId, dText)} alt={t('co.previewAlt')} />
                ) : order && order.inputs.length ? (
                  <OrderPreview order={order} inkColor={ink?.hex} />
                ) : (
                  <span className="co-hint">{t('co.previewEmpty')}</span>
                )}
              </div>
              <div className="co-rail-body">
                <span className="co-est-title">{t('co.estimate')}</span>
                <div className="co-lines">
                  <div className="co-line"><span>{t('co.sum.materials')}</span><span>{materialsLabel}</span></div>
                  <div className="co-line"><span>{t('co.sum.qty')}</span><span>{qty}</span></div>
                  {est && <div className="co-line"><span>{t('co.chars.label')}</span><span>{est.charsMin === est.charsMax ? est.charsMax : `${est.charsMin} – ${est.charsMax}`}</span></div>}
                </div>
                <div className="vh-total-row">
                  <span>{t('co.range')}</span>
                  <span className="co-total">{range}</span>
                </div>
                {est && (
                  <div className="co-eta">
                    <div><span>{t('co.minDeposit')}</span><b>{est.minDepositPct}%</b></div>
                  </div>
                )}
                {est && !est.materialsPriced && <span className="co-fine">{t('co.pickMaterialsHint')}</span>}
                <span className="co-fine">{t('co.fine')}</span>
              </div>
            </aside>
            <Link to="/account/drafts" className="vh-btn vh-btn--md vh-btn--white co-save">{t('co.saveExit')}</Link>
          </div>
        </div>
      </div>
    </Page>
  )
}
