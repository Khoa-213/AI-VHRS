import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import CustomerFrame from '../../components/layout/CustomerFrame'
import OrderPreview from '../../components/ui/OrderPreview'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useStyledPreview } from '../../hooks/useStyledPreview'
import { useSaveQueue } from '../../hooks/useSaveQueue'
import { useT } from '../../i18n'
import { Link, navigate, orderPath } from '../../router/router'
import {
  ACCEPTED_UPLOADS, MAX_UPLOAD_MB, createOrder, deleteInput, editPhoto, estimate, getInks, getOrder, getPapers, getPens, getTemplates,
  incompleteFields, orderErrorKey, patchOrder, provideInfo, putText, submitOrder, uploadOriginal,
  type Alignment, type CropBox, type Estimate, type Order, type OrderPatch, type OrderType, type SheetSize, errText } from '../../services/orders'
import { useUser } from '../../store/store'
import type { InputMode } from '../../types'
import { fmt } from '../../utils/format'
import { ApiError } from '../../services/api'
import { aiStatus, emptySelection, getSketchInfo, redrawSketch, type AiSelection, type SketchInfo } from '../../services/orderAi'
import { draftPathFor, drawPathFor } from './draft'
import { Sparkle } from '@phosphor-icons/react'
import OrderAssistant from './ai/OrderAssistant'
import AiPolicyDialog from './ai/AiPolicyDialog'
import SketchView from './ai/SketchView'
import PhotoRow from './PhotoRow'
import TemplateCard from './TemplateCard'
import { DEFAULT_PLACE, MARGIN_SIDES, VERTICAL_ALIGNS, hasRichLayout, layoutWithPlace, placeFromLayout, placeKey, type Place } from './textPlace'
import { openAuth } from '../../store/authDialog'
import Header from '../landing/components/Header'
import fr3Arm from '../../assets/fr3-arm.png'
import '../landing/landing.css'
import '../landing/landing-redesign.css'
import './create-order.css'
import './order-entry.css'
import './co-home.css'
import './ai/order-ai.css'

const MODES: InputMode[] = ['text', 'upload', 'draw']
const STEPS = ['co.step.0', 'co.step.1', 'co.step.2']
const ALIGNMENTS: Alignment[] = ['LEFT', 'CENTER', 'RIGHT', 'JUSTIFY']
const MAX_QTY = 10000

const typeOf = (m: InputMode): OrderType => (m === 'upload' ? 'OT1_COPY_RESTORE' : 'OT3_TEMPLATE')

function initialMode(): InputMode | null {
  const m = /mode=(text|upload|draw)/.exec(window.location.hash)
  return (m?.[1] as InputMode | undefined) ?? null
}

/** Same shell as the homepage (floating navbar, one rounded surface), without the footer: this is the order flow. */
function Frame({ children, narrow = false }: { children: ReactNode; narrow?: boolean }) {
  return (
    <CustomerFrame label="Create Order" narrow={narrow} footer={false}>{children}</CustomerFrame>
  )
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
  /** Where the text sits on the sheet: top / middle / bottom, the margins, the line spacing. */
  const [place, setPlace] = useState<Place>(DEFAULT_PLACE)
  const [paperId, setPaperId] = useState<number | null>(null)
  const [penId, setPenId] = useState<number | null>(null)
  const [inkId, setInkId] = useState<number | null>(null)
  const [suggest, setSuggest] = useState(false)
  const [qty, setQty] = useState(1)
  const [note, setNote] = useState('')
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')
  const [closed, setClosed] = useState<InputMode[]>([])
  const [sizeFilter, setSizeFilter] = useState('')
  // Templates whose preview the backend refuses cannot be sketched either, so they are not offered.
  const [broken, setBroken] = useState<number[]>([])
  const [busy, setBusy] = useState(false)
  const [uploading, setUploading] = useState(0)
  const [est, setEst] = useState<Estimate | null>(null)
  // The AI assistant: on or off by the customer's choice; `aiBusy` keeps the form still while it works.
  // Create Order always opens on "By myself". The assistant opens only after the customer ticks the AI chat data policy,
  // asked again on every visit (owner decision 2026-11-24, Quang).
  const [wantAi, setWantAi] = useState(false)
  const [aiAccepted, setAiAccepted] = useState(false)
  const [policyOpen, setPolicyOpen] = useState(false)
  const [aiBusy, setAiBusy] = useState(false)
  const [sketch, setSketch] = useState<SketchInfo | null>(null)
  // What the customer picked on the sketch for the assistant; ids belong to one revision, so a new revision clears it.
  const [selection, setSelection] = useState<AiSelection>(emptySelection)
  // Upload mode: the customer asks the backend to restore the photos (OT-1 engine) and sees the result before sending.
  const [restoring, setRestoring] = useState(false)
  // The photos (ids, rotation, crop) the shown restoration was drawn from; null when it was only read back from the server.
  const [restoredFor, setRestoredFor] = useState<string | null>(null)

  const aiState = useAsync(aiStatus, [])
  const aiAvailable = !!aiState.data?.available
  const aiOn = mode === 'text' && wantAi && aiAvailable
  // Until the status is known the form waits, so it does not flash and then give way to the assistant.
  const aiWait = mode === 'text' && wantAi && aiState.loading
  // What the "AI / myself" switch shows: the assistant while it is on or still being checked.
  const aiPicked = aiOn || aiWait

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

  const fail = (e: unknown) => {
    // The workshop can switch an order type off: its modes are then not offered any more.
    if (e instanceof ApiError && e.code === 'ORDER_TYPE_SUSPENDED') {
      const off: InputMode[] = wanted.current === 'OT1_COPY_RESTORE' ? ['upload'] : ['text', 'draw']
      setClosed((c) => [...new Set([...c, ...off])])
    }
    setErr(orderErrorKey(e))
  }

  const patch = useCallback((p: OrderPatch) => {
    setErr('')
    setNotice('')
    return enqueue(async () => {
      const o = await ensure()
      const fresh = await patchOrder(o.id, p)
      adopt({ ...fresh, inputs: orderRef.current?.inputs ?? o.inputs })
      // The backend resets the pen or the ink when a change makes them invalid: follow what it kept.
      const reset = fresh.warnings.filter((w) => w === 'PEN_RESET' || w === 'INK_RESET')
      if (p.paper_type_id !== undefined || reset.length) {
        setPenId(fresh.penId)
        setInkId(fresh.inkId)
      }
      if (reset.length) setNotice(reset.includes('PEN_RESET') ? 'warn.PEN_RESET' : 'warn.INK_RESET')
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
        setPlace(placeFromLayout(tx?.layout))
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
    const ok = templates.data?.find((x) => !broken.includes(x.id))
    if (templateId === null && ok) setTemplateId(ok.id)
    if (templateId !== null && broken.includes(templateId)) setTemplateId(ok?.id ?? null)
  }, [templates.data, templateId, broken])

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
  const dPlace = useDebounced(place, 700)
  const textKey = `${dText}|${templateId}|${alignment}|${dSize}|${placeKey(dPlace)}`
  useEffect(() => {
    if (loading) return
    if (!loaded.current) {
      loaded.current = true
      const tx = orderRef.current?.inputs.find((i) => i.kind === 'TEXT_CONTENT')
      lastSaved.current = `${tx?.text ?? ''}|${tx?.templateId ?? null}|${tx?.alignment ?? null}|${tx?.fontSizeMm ? String(tx.fontSizeMm) : ''}|${placeKey(placeFromLayout(tx?.layout))}`
    }
    // Wait until the typing has settled, so a value still on its way is never saved.
    if (text !== dText || fontSize !== dSize || place !== dPlace) return
    if (mode !== 'text' || !dText.trim() || templateId === null || textKey === lastSaved.current) return
    lastSaved.current = textKey
    setErr('')
    const size = Number(dSize)
    enqueue(async () => {
      const o = await ensure()
      const fields = { text_content: dText, template_id: templateId, alignment, font_size_mm: dSize && size > 0 ? size : null }
      // The placement is part of the text's layout, and a PUT replaces the whole layout. Styles of parts of the text
      // (made by the assistant or the studio) index its characters: when the words changed too, the text is saved first
      // with `keep_layout`, so those styles follow the characters that stayed, and the placement goes on top of the result.
      const stored = (orderRef.current ?? o).inputs.find((i) => i.kind === 'TEXT_CONTENT')
      let base = stored?.layout ?? null
      if (hasRichLayout(base) && stored?.text !== dText) base = (await putText(o.id, { ...fields, keep_layout: true })).layout
      const input = await putText(o.id, { ...fields, layout: layoutWithPlace(base, dPlace) })
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
    // Only the paper is sent: the backend keeps a pen that still fits and clears one that does not.
    setPaperId(id)
    void patch({ paper_type_id: id })
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

  // ---------- AI assistant ----------

  /** Puts a server copy of the draft into the form without saving it back (the assistant changed it there). */
  const fill = useCallback((o: Order) => {
    adopt(o)
    const tx = o.inputs.find((i) => i.kind === 'TEXT_CONTENT')
    setText(tx?.text ?? '')
    setTemplateId(tx?.templateId ?? null)
    setAlignment(tx?.alignment ?? null)
    setFontSize(tx?.fontSizeMm ? String(tx.fontSizeMm) : '')
    setPlace(placeFromLayout(tx?.layout))
    setPaperId(o.paperId); setPenId(o.penId); setInkId(o.inkId)
    setSuggest(o.workshopSuggest); setQty(o.quantity); setNote(o.note ?? '')
    // What is on screen is what the server has: the autosave must not send it back.
    lastSaved.current = `${tx?.text ?? ''}|${tx?.templateId ?? null}|${tx?.alignment ?? null}|${tx?.fontSizeMm ? String(tx.fontSizeMm) : ''}|${placeKey(placeFromLayout(tx?.layout))}`
    sentQty.current = o.quantity
    sentNote.current = o.note ?? ''
  }, [adopt])

  /** After the assistant worked, or the sketch was undone or drawn again: load the draft and the sketch again. */
  const aiChanged = useCallback(async () => {
    const id = orderRef.current?.id
    if (!id) return
    try {
      await idle() // a save still on its way must not overwrite what the assistant just did
      const [o, s] = await Promise.all([getOrder(id), getSketchInfo(id)])
      fill(o)
      setSketch(s)
    } catch (e) {
      setErr(orderErrorKey(e))
    }
  }, [fill, idle])

  /** The draft the assistant works on; it is created when the first message is sent. */
  const ensureOrderId = useCallback(async () => {
    await idle()
    return (await enqueue(ensure)).id
  }, [enqueue, ensure, idle])

  const pickAi = (on: boolean) => setWantAi(on)

  const sketchRev = sketch?.revisionId ?? null
  useEffect(() => {
    setSelection(emptySelection())
  }, [sketchRev])

  // A draft that already has a sketch (made by the assistant earlier) shows it.
  const orderId = order?.id ?? null
  useEffect(() => {
    if (orderId === null) {
      setSketch(null)
      return
    }
    // Upload mode shows the restoration made earlier, with or without the assistant. Without the assistant the other modes
    // show their own preview, never a restoration drawn in upload mode.
    if (!aiAvailable && mode !== 'upload') {
      setSketch(null)
      return
    }
    let live = true
    getSketchInfo(orderId).then((s) => live && setSketch(s)).catch(() => undefined)
    return () => {
      live = false
    }
  }, [orderId, aiAvailable, mode])

  // ---------- content mode ----------

  /** Switches the input mode; false when the customer cancelled or the switch failed. */
  const chooseMode = async (m: InputMode): Promise<boolean> => {
    if (m === mode && m !== 'draw') return true
    setErr('')
    const next = typeOf(m)
    const cur = orderRef.current
    if (cur && cur.type !== next) {
      const stale = cur.inputs.filter((i) => (next === 'OT1_COPY_RESTORE' ? i.kind !== 'ORIGINAL_IMAGE' : i.kind === 'ORIGINAL_IMAGE'))
      if (stale.length && !window.confirm(t('co.switchWarn'))) return false
      setBusy(true)
      try {
        await enqueue(async () => {
          for (const i of stale) await deleteInput(cur.id, i.id)
          const o = await patchOrder(cur.id, { order_type: next })
          adopt({ ...o, inputs: cur.inputs.filter((i) => !stale.includes(i)) })
        })
      } catch (e) {
        fail(e)
        return false
      } finally {
        setBusy(false)
      }
    }
    setMode(m)
    if (m === 'draw') await openCanvas()
    return true
  }

  /** The first choice of step 1: the assistant writes from text, so choosing it moves to the text mode. */
  /** "AI assistant" opens the data policy first; the chat opens once the customer ticks it. */
  const chooseHow = async (ai: boolean, accepted = aiAccepted) => {
    if (ai && !accepted) {
      setPolicyOpen(true)
      return
    }
    if (ai && mode !== 'text' && !(await chooseMode('text'))) return
    pickAi(ai)
  }

  const policyAccepted = () => {
    setAiAccepted(true)
    setPolicyOpen(false)
    void chooseHow(true, true)
  }

  /** Closed without ticking: back to (or staying on) "By myself". */
  const policyDeclined = () => {
    setPolicyOpen(false)
    pickAi(false)
  }

  /** The backend refused a message for want of consent (withdrawn or a new policy version). */
  const consentNeeded = () => {
    setAiAccepted(false)
    setPolicyOpen(true)
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

  const changePhoto = (id: number, change: { rotation_deg?: 0 | 90 | 180 | 270; crop_box?: CropBox | null }) => {
    const cur = orderRef.current
    if (!cur) return
    setErr('')
    enqueue(async () => {
      const input = await editPhoto(cur.id, id, change)
      // The photo was analysed again, so the character count and the price changed too.
      const fresh = await getOrder(cur.id)
      adopt({ ...fresh, inputs: fresh.inputs.map((i) => (i.id === input.id ? input : i)) })
    }).then(undefined, fail)
  }

  // ---------- estimate ----------

  const dTextForEst = useDebounced(text, 900)
  // The preview is only a picture, so it follows the typing more closely than the autosave does.
  const dPreview = useDebounced(text, 300)
  const sizeMm = Number(dSize)
  // The picture is the first page as the robot would write it: on the sheet of the chosen paper (A5 until one is chosen),
  // with the placement being edited. Styles stored on parts of the text only fit the text they were made for.
  const sheet: SheetSize = (['A4', 'A5', 'A6'] as const).find((s) => s === papers.data?.find((p) => p.id === paperId)?.size) ?? 'A5'
  const dPlaceView = useDebounced(place, 300)
  const storedText = order?.inputs.find((i) => i.kind === 'TEXT_CONTENT')
  const previewLayout = JSON.stringify(layoutWithPlace(storedText?.text === dPreview ? storedText.layout : null, dPlaceView))
  const previewSrc = useStyledPreview(mode === 'text' ? templateId : null, dPreview, alignment, sizeMm > 0 ? sizeMm : null, previewLayout, sheet)
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
  // The backend restores JPG / PNG only: one PDF among the photos and the engine refuses the order (PDF_NOT_SUPPORTED_AI).
  const hasPdf = photos.some((p) => p.mime === 'application/pdf')
  const photoSig = photos.map((p) => `${p.id}:${p.rotation}:${JSON.stringify(p.cropBox)}`).join('|')
  const canRestore = !!order && !restoring && !busy && uploading === 0 && !hasPdf && photos.some((p) => p.quality !== null)
  // The server's own flag covers a reload; the local one covers photos changed in this visit.
  const restoreStale = !!sketch && !sketch.inputsChanged && restoredFor !== null && restoredFor !== photoSig

  /** Draws the working sketch from the photos (the same engine the workshop uses) and shows it under them. */
  const restore = async () => {
    const id = orderRef.current?.id
    if (!id || !canRestore) return
    const sig = photoSig
    setErr('')
    setRestoring(true)
    try {
      await idle() // an upload, rotation or crop still on its way must reach the server first
      // An upload order has no sketch edits of its own: edits left from another mode belong to content that is gone.
      setSketch(await redrawSketch(id, true))
      setRestoredFor(sig)
    } catch (e) {
      fail(e)
    } finally {
      setRestoring(false)
    }
  }
  const strokes = canvas?.canvas?.strokes.length ?? 0
  const materialsOk = suggest || !!(paperId && penId && inkId)

  const valid = (i: number) => {
    if (i === 0) return mode === 'text' ? text.trim().length > 0 && templateId !== null : mode === 'upload' ? photos.length > 0 : strokes > 0
    if (i === 1) return materialsOk && qty >= 1
    return true
  }
  // The assistant's answers are applied as they come, so the form is only held while it works.
  const aiLocked = aiOn && aiBusy
  const ok = valid(step) && !busy && uploading === 0 && !aiBusy
  const hints = [
    t(aiOn
      ? 'oa.hint'
      : mode === 'text'
      ? (!text.trim() ? 'co.hint0.textEmpty' : 'co.hint0.textStyle')
      : mode === 'upload' ? 'co.hint0.upload' : 'co.hint0.draw'),
    t(!materialsOk ? (!paperId ? 'co.hint1.paper' : !penId ? 'co.hint1.pen' : 'co.hint1.ink') : 'co.hint1.qty'),
    aiBusy ? t('oa.thinking') : '',
  ]

  const goTo = (i: number) => {
    setStep(i)
    setMaxStep((m) => Math.max(m, i))
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const submit = async () => {
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
      else if (e instanceof ApiError && e.code === 'SKETCH_OUTDATED' && mode === 'text') {
        // The text or the paper changed after the assistant drew the sketch: the assistant panel can draw it again.
        if (aiAvailable) void chooseHow(true)
        goTo(0)
      }
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
      <div className="lp-root order-entry">
        <Header />
        <main className="order-entry-hero" aria-labelledby="order-entry-title">
          <div className="order-entry-orbit" aria-hidden="true"><span /></div>
          <div className="order-entry-copy">
            <span className="order-entry-eyebrow">{t('lp.eyebrow')}</span>
            <h1 id="order-entry-title">{t('co.signInTitle')}</h1>
            <p>{t('co.signInBody')}</p>
            <div className="order-entry-buttons">
              <button type="button" className="order-entry-primary" onClick={() => openAuth('login')}>
                {t('nav.signIn')}<span aria-hidden="true">↗</span>
              </button>
              <button type="button" className="order-entry-secondary" onClick={() => openAuth('register')}>{t('reg.submit')}</button>
            </div>
          </div>
          <div className="order-entry-art" aria-hidden="true">
            <span className="order-entry-brand">AI-VHRS</span>
            <img src={fr3Arm} alt="" draggable={false} />
          </div>
          <div className="order-entry-footer"><span>AI-VHRS</span><span>{t('lp.eyebrow')}</span></div>
        </main>
      </div>
    )
  }
  if (user.role !== 'customer') {
    return (
      <Frame narrow>
        <div className="co-card co-card--msg">
          <h1 className="co-h1">{t('co.customerOnlyTitle')}</h1>
          <p className="co-lede">{t('co.customerOnlyBody')}</p>
        </div>
      </Frame>
    )
  }
  if (loading) {
    return (
      <Frame narrow>
        <p className="co-lede" role="status">{t('co.loading')}</p>
      </Frame>
    )
  }
  if (given !== null && !order) {
    return (
      <Frame narrow>
        <div className="co-card co-card--msg">
          <h1 className="co-h1">{t('np.title')}</h1>
          {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
          <Link to="/account/drafts" className="co-btn co-btn--solid">{t('co.toDrafts')}</Link>
        </div>
      </Frame>
    )
  }

  // ---------- view ----------

  const paper = papers.data?.find((p) => p.id === paperId)
  const pen = pens.data?.find((p) => p.id === penId)
  const ink = inks.data?.find((i) => i.id === inkId)
  const template = templates.data?.find((x) => x.id === templateId)
  const picked = [paper?.name, pen?.name, ink?.name].filter(Boolean).join(', ')
  const leftToWorkshop = [!paperId && t('co.paper'), !penId && t('co.pen'), !inkId && t('co.ink')].filter(Boolean).join(', ')
  const materialsLabel = suggest
    ? (!leftToWorkshop ? picked : picked ? t('co.sum.suggestRest', { picked }) : t('co.sum.suggest'))
    : picked || t('co.sum.notChosen')
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
    <Frame>
      <div className={`co${aiOn ? ' co--ai' : ''}`}>
        {policyOpen && <AiPolicyDialog onAccepted={policyAccepted} onDecline={policyDeclined} />}
        <header className="co-head">
          <h1 className="co-h1">{t('co.h1')}</h1>
          <div className="co-head-row">
            <span className="co-progress">{t('co.progress', { n: step + 1, total: STEPS.length })}</span>
            {saveLabel && (
              <span className={`co-save-state${pending > 0 || uploading > 0 ? ' busy' : ''}`} role="status">
                <i aria-hidden="true" />{saveLabel}
              </span>
            )}
          </div>
        </header>

        {rewrite && order?.infoRequestNote && (
          <div className="co-callout" role="status">
            <b>{t('co.needInfo')}</b>
            <span>{order.infoRequestNote}</span>
          </div>
        )}

        <div className={`co-shell${aiOn ? ' co-shell--ai' : ''}`}>
          <div className="co-main">
            <div className="co-steps">
              {STEPS.map((key, i) => {
                const cur = i === step
                const done = i <= maxStep && !cur
                return (
                  <button key={key} className={`co-step${cur ? ' cur' : done ? ' done' : ''}`} disabled={i > maxStep || aiBusy} aria-current={cur ? 'step' : undefined} onClick={() => openStep(i)}>
                    <span className="co-step-bar" />
                    <span className="co-step-label">
                      <span className="co-step-num">{done ? '✓' : i + 1}</span>
                      <span>{t(key)}</span>
                    </span>
                  </button>
                )
              })}
            </div>

            <div className="co-body">
              <fieldset className="co-lock" disabled={aiLocked}>
              {step === 0 && (
                <>
                  <div className="co-intro">
                    <h2 className="co-h2">{t('co.s1.title')}</h2>
                  </div>

                  <div className="co-how">
                    <span id="oa-who" className="co-group-label">{t('oa.who')}</span>
                    <div className="co-seg co-seg--how" role="radiogroup" aria-labelledby="oa-who">
                      <button type="button" role="radio" aria-checked={aiPicked} className={`co-how-ai${aiPicked ? ' on' : ''}`}
                        disabled={!aiAvailable || busy || aiBusy} onClick={() => void chooseHow(true)}>
                        <Sparkle aria-hidden="true" weight="fill" className="co-how-icon" />
                        {t('oa.ai')}
                      </button>
                      <button type="button" role="radio" aria-checked={!aiPicked} className={!aiPicked ? 'on' : ''}
                        disabled={busy || aiBusy} onClick={() => void chooseHow(false)}>
                        {t('oa.manual')}
                      </button>
                    </div>
                    {!(aiPicked && aiAvailable && !aiState.loading) && (
                      <p className="co-how-hint" role="status">
                        {aiState.loading ? t('oa.checking') : !aiAvailable ? t('oa.unavailable') : t('oa.manual.sub')}
                      </p>
                    )}
                  </div>

                  {!aiPicked && (
                    <div className="co-tray co-tray--3">
                      {MODES.map((m) => (
                        <button key={m} className={`co-opt${mode === m ? ' on' : ''}`} disabled={busy || aiBusy || closed.includes(m)} onClick={() => void chooseMode(m)}>
                          <span className="co-opt-name">{t(`co.mode.${m}`)}</span>
                          <span className="co-opt-sub">{closed.includes(m) ? t('co.modeClosed') : t(`co.mode.${m}.sub`)}</span>
                        </button>
                      ))}
                    </div>
                  )}

                  {mode === 'text' && !aiOn && !aiWait && (
                    <>
                      <section className="co-sub" aria-labelledby="co-t1">
                        <div className="co-sub-head">
                          <span className="co-sub-n" aria-hidden="true">1</span>
                          <div>
                            <h3 id="co-t1" className="co-h3">{t('co.t.1')}</h3>
                            <p className="co-sub-hint">{t('co.t.1.sub')}</p>
                          </div>
                        </div>
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
                          {!text.trim() && (
                            <div className="co-try">
                              <span>{t('co.try')}</span>
                              <div className="co-try-list">
                                {[1, 2, 3].map((n) => (
                                  <button key={n} type="button" className="co-example" onClick={() => setText(t(`co.ex.${n}`))}>
                                    {t(`co.ex.${n}`)}
                                  </button>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </section>

                      <section className="co-sub" aria-labelledby="co-t2">
                        <div className="co-sub-head">
                          <span className="co-sub-n" aria-hidden="true">2</span>
                          <div>
                            <h3 id="co-t2" className="co-h3">{t('co.t.2')}</h3>
                            <p className="co-sub-hint">{t('co.t.2.sub')}</p>
                          </div>
                        </div>
                        <div className="co-tray co-tray--3 co-tray--keep" role="group" aria-label={t('co.styleLabel')}>
                          {(templates.data ?? []).map((s) => (
                            <TemplateCard
                              key={s.id}
                              template={s}
                              text={dText || t('co.fontSample')}
                              on={templateId === s.id}
                              onPick={() => setTemplateId(s.id)}
                              onBroken={() => setBroken((b) => (b.includes(s.id) ? b : [...b, s.id]))}
                              broken={broken.includes(s.id)}
                            />
                          ))}
                          {templates.loading && <span className="co-hint">{t('co.loading')}</span>}
                          {!!templates.error && <span className="co-hint">{errText(t, orderErrorKey(templates.error))}</span>}
                        </div>
                      </section>

                      <section className="co-sub" aria-labelledby="co-t3">
                        <div className="co-sub-head">
                          <span className="co-sub-n" aria-hidden="true">3</span>
                          <div>
                            <h3 id="co-t3" className="co-h3">{t('co.t.3')}</h3>
                            <p className="co-sub-hint">{t('co.t.3.sub')}</p>
                          </div>
                        </div>

                        <div className="co-group">
                          <span className="co-group-label">{t('co.align')}</span>
                          <div className="co-seg" role="group" aria-label={t('co.align')}>
                            <button type="button" className={alignment === null ? 'on' : ''} aria-pressed={alignment === null} onClick={() => setAlignment(null)}>
                              {t('co.align.auto')}
                            </button>
                            {ALIGNMENTS.map((a) => (
                              <button key={a} type="button" className={alignment === a ? 'on' : ''} aria-pressed={alignment === a} onClick={() => setAlignment(a)}>
                                {t(`co.align.${a}`)}
                              </button>
                            ))}
                          </div>
                          {alignment === null && <span className="co-sub-hint">{t('co.align.autoNote')}</span>}
                        </div>

                        <div className="co-group">
                          <span className="co-group-label">{t('co.place.vertical')}</span>
                          <div className="co-seg" role="group" aria-label={t('co.place.vertical')}>
                            {VERTICAL_ALIGNS.map((v) => (
                              <button key={v} type="button" className={place.vertical === v ? 'on' : ''} aria-pressed={place.vertical === v} onClick={() => setPlace((p) => ({ ...p, vertical: v }))}>
                                {t(`co.place.${v}`)}
                              </button>
                            ))}
                          </div>
                        </div>

                        <div className="co-group">
                          <span className="co-group-label">{t('co.place.margins')}</span>
                          <div className="co-place-grid">
                            {MARGIN_SIDES.map((side) => (
                              <label key={side} className="co-cell">
                                {t(`co.place.m.${side}`)}
                                <input
                                  inputMode="decimal"
                                  value={place[side]}
                                  onChange={(e) => setPlace((p) => ({ ...p, [side]: e.target.value.replace(/[^\d.]/g, '').slice(0, 5) }))}
                                />
                              </label>
                            ))}
                            <label className="co-cell">
                              {t('co.place.spacing')}
                              <input
                                inputMode="decimal"
                                value={place.spacing}
                                onChange={(e) => setPlace((p) => ({ ...p, spacing: e.target.value.replace(/[^\d.]/g, '').slice(0, 4) }))}
                              />
                            </label>
                          </div>
                          <span className="co-sub-hint">{t('co.place.note')}</span>
                        </div>

                        <div className="co-live" aria-live="polite">
                          {previewSrc ? (
                            <img className="co-live-img" src={previewSrc} alt={t('co.previewAlt')} />
                          ) : (
                            <span className="co-hint">{t('co.previewWait')}</span>
                          )}
                        </div>
                        {previewSrc && <span className="co-sub-hint">{t('co.place.sheet', { size: sheet })}</span>}

                        <label className="co-cell">
                          {t('co.fontSize')}
                          <input
                            inputMode="decimal"
                            placeholder={t('co.fontSizePh')}
                            value={fontSize}
                            onChange={(e) => setFontSize(e.target.value.replace(/[^\d.]/g, '').slice(0, 5))}
                          />
                        </label>
                      </section>
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
                      {order && photos.map((p, i) => (
                        <PhotoRow
                          key={p.id}
                          orderId={order.id}
                          input={p}
                          index={i + 1}
                          busy={busy}
                          onEdit={(change) => changePhoto(p.id, change)}
                          onRemove={() => removeInput(p.id)}
                        />
                      ))}
                      {order && photos.length > 0 && (
                        <section className="co-restore" aria-labelledby="co-restore-h" aria-busy={restoring}>
                          <div className="co-restore-head">
                            <div className="co-restore-copy">
                              <h3 id="co-restore-h" className="co-restore-title">{t('co.restore.title')}</h3>
                              <p className="co-hint">{t(sketch ? 'co.restore.ready' : 'co.restore.intro')}</p>
                            </div>
                            <button type="button" className="co-btn co-btn--line co-btn--sm" disabled={!canRestore} onClick={() => void restore()}>
                              {t(restoring ? 'co.restore.working' : sketch ? 'co.restore.again' : 'co.restore.run')}
                            </button>
                          </div>
                          {hasPdf && <p className="co-hint">{t('co.restore.pdf')}</p>}
                          {restoring && <p className="co-hint" role="status">{t('co.restore.wait')}</p>}
                          {sketch && (
                            <div className="co-restore-stage">
                              <SketchView orderId={order.id} sketch={sketch} outdatedKey="co.restore.stale" />
                              {restoreStale && <span className="oa-stale" role="status">{t('co.restore.stale')}</span>}
                            </div>
                          )}
                          {sketch && sketch.warnings.length > 0 && (
                            <div className="co-restore-notes">
                              <b>{t('co.restore.notes')}</b>
                              <ul>{sketch.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
                            </div>
                          )}
                        </section>
                      )}
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
                        <button className="co-btn co-btn--solid co-btn--sm" disabled={busy} onClick={() => void openCanvas()}>
                          {t(strokes > 0 ? 'co.editCanvas' : 'co.openCanvas')}
                        </button>
                      </div>
                    </div>
                  )}
                </>
              )}

              {step === 1 && (
                <>
                  <div className="co-intro">
                    <h2 className="co-h2">{t('co.s2.title')}</h2>
                    <p className="co-lede">{t('co.s2.lede')}</p>
                  </div>

                  <div className="co-tray co-tray--2" role="radiogroup" aria-label={t('co.who')}>
                    <button type="button" role="radio" aria-checked={!suggest} className={`co-opt${!suggest ? ' on' : ''}`} onClick={() => suggest && toggleSuggest(false)}>
                      <span className="co-opt-name">{t('co.who.self')}</span>
                      <span className="co-opt-sub">{t('co.who.selfSub')}</span>
                    </button>
                    <button type="button" role="radio" aria-checked={suggest} className={`co-opt${suggest ? ' on' : ''}`} onClick={() => !suggest && toggleSuggest(true)}>
                      <span className="co-opt-name">{t('co.suggest')}</span>
                      <span className="co-opt-sub">{t('co.suggestSub')}</span>
                    </button>
                  </div>
                  {suggest && (
                    <p className="co-note" role="status">
                      {!leftToWorkshop ? t('co.suggest.none') : t(picked ? 'co.suggest.left' : 'co.suggest.all', { items: leftToWorkshop })}
                    </p>
                  )}

                  {notice && <p className="co-notice" role="status">{t(notice)}</p>}

                  <ol className="co-chain" aria-label={t('co.chain')}>
                    <li className={paper ? 'done' : 'now'}><b>1</b> {t('co.paper')}: <span>{paper?.name ?? t(suggest ? 'co.chain.workshop' : 'co.sum.notChosen')}</span></li>
                    <li className={pen ? 'done' : paper ? 'now' : ''}><b>2</b> {t('co.pen')}: <span>{pen?.name ?? t(suggest ? 'co.chain.workshop' : 'co.sum.notChosen')}</span></li>
                    <li className={ink ? 'done' : pen ? 'now' : ''}>
                      <b>3</b> {t('co.ink')}:{' '}
                      <span>{ink ? <><i className="co-ink-dot co-ink-dot--sm" style={{ background: ink.hex ?? 'var(--t5)' }} /> {ink.name}</> : t(suggest ? 'co.chain.workshop' : 'co.sum.notChosen')}</span>
                    </li>
                  </ol>

                  <div className="co-group">
                    <span className="co-group-label">1. {t('co.paper')}</span>
                    <div className="co-chips" role="group" aria-label={t('co.sizeFilter')}>
                      {['', ...new Set((papers.data ?? []).map((p) => p.size))].map((sz) => (
                        <button key={sz || 'all'} className={`co-chip${sizeFilter === sz ? ' on' : ''}`} onClick={() => setSizeFilter(sz)}>
                          {sz || t('co.sizeAll')}
                        </button>
                      ))}
                    </div>
                    <div className="co-tray co-tray--4">
                      {(papers.data ?? []).filter((o) => !sizeFilter || o.size === sizeFilter).map((o) => (
                        <button key={o.id} className={`co-opt co-opt--row${paperId === o.id ? ' on' : ''}`} onClick={() => pickPaper(o.id)}>
                          <span className="co-choice-text">
                            <span className="co-opt-name">{o.name}</span>
                            <span className="co-opt-sub">{t('co.paperSpec', { gsm: o.gsm, surface: t(`surface.${o.surface}`), size: o.size })}</span>
                            <span className="co-price">{t('co.perSheet', { price: fmt(o.unitPrice) })}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                    {papers.loading && <span className="co-hint">{t('co.loading')}</span>}
                    {!!papers.error && <span className="co-hint">{errText(t, orderErrorKey(papers.error))}</span>}
                  </div>

                  <div className="co-group">
                    <span className="co-group-label">2. {t('co.pen')}</span>
                    {!paperId && <span className="co-hint">{t(suggest ? 'co.skipHint' : 'co.pickPaperFirst')}</span>}
                    <div className="co-tray co-tray--4">
                      {(paperId ? pens.data ?? [] : []).map((o) => (
                        <button key={o.id} className={`co-opt co-opt--pen${penId === o.id ? ' on' : ''}`} onClick={() => pickPen(o.id)}>
                          <span className="co-nib"><span style={{ height: Math.max(1, Math.min(10, o.strokeWidthMm * 6)) }} /></span>
                          <span className="co-choice-text">
                            <span className="co-opt-name">{o.name}</span>
                            <span className="co-opt-sub">{t(`pen.${o.category}`)} · {t('co.penSpec', { mm: o.strokeWidthMm })}</span>
                            <span className="co-price">{o.surcharge ? '+' + fmt(o.surcharge) : t('co.included')}</span>
                          </span>
                        </button>
                      ))}
                    </div>
                    {!!paperId && !pens.loading && !pens.data?.length && <span className="co-hint">{t('co.noPens')}</span>}
                  </div>

                  <div className="co-group">
                    <span className="co-group-label">3. {t('co.ink')}</span>
                    {!penId && <span className="co-hint">{t(suggest ? 'co.skipHint' : 'co.pickPenFirst')}</span>}
                    <div className="co-inks">
                      {(penId ? inks.data ?? [] : []).map((o) => (
                        <button key={o.id} className={`co-ink${inkId === o.id ? ' on' : ''}`} onClick={() => pickInk(o.id)} aria-pressed={inkId === o.id}>
                          <span className="co-ink-dot" style={{ background: o.hex ?? 'var(--t5)' }} />
                          <span className="co-ink-name">{o.name}</span>
                          {o.unitPrice > 0 && <span className="co-price">+{fmt(o.unitPrice)}</span>}
                        </button>
                      ))}
                    </div>
                    {!!penId && inks.loading && <span className="co-hint">{t('co.loading')}</span>}
                    {!!penId && !inks.loading && !inks.data?.length && <span className="co-hint">{t('co.noInks')}</span>}
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
                  <div className="co-intro">
                    <h2 className="co-h2">{t('co.s3.title')}</h2>
                    <p className="co-lede">{t('co.s3.lede')}</p>
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
                    <div className="co-callout" role="status">
                      <b>{t('co.warnings')}</b>
                      {order.warnings.map((w) => <span key={w}>{t(`warn.${w}`)}</span>)}
                    </div>
                  )}
                </>
              )}
              </fieldset>
            </div>

            {aiOn && (
              <section className="co-sketch" aria-labelledby="co-sketch-t">
                <div className="co-sketch-head">
                  <h3 id="co-sketch-t" className="co-h3">{t('oa.sketchTitle')}</h3>
                  <details className="oa-est">
                    <summary>
                      <span>{t('co.range')}</span>
                      <b className="oa-est-total">{range}</b>
                    </summary>
                    <dl className="oa-est-lines">
                      <div><dt>{t('co.sum.materials')}</dt><dd>{materialsLabel}</dd></div>
                      <div><dt>{t('co.sum.qty')}</dt><dd>{qty}</dd></div>
                      {est && <div><dt>{t('co.minDeposit')}</dt><dd>{est.minDepositPct}%</dd></div>}
                    </dl>
                    <span className="oa-fine">{t(est && !est.materialsPriced ? 'co.pickMaterialsHint' : 'co.fine')}</span>
                  </details>
                </div>
                <div className={`co-sketch-stage${aiBusy ? ' busy' : ''}`} aria-busy={aiBusy}>
                  {order && sketch ? (
                    <SketchView orderId={order.id} sketch={sketch} selection={selection} onSelection={setSelection} pickLocked={aiBusy} />
                  ) : (
                    <span className="co-hint">{t('oa.sketchEmpty')}</span>
                  )}
                </div>
              </section>
            )}

            {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}

            <div className="co-nav">
              <button className="co-btn co-btn--line co-back" disabled={step === 0 || aiBusy} onClick={() => step > 0 && goTo(step - 1)}>
                {t('co.back')}
              </button>
              <div className="co-next-wrap">
                <span className={`co-need${ok ? ' ok' : ''}`} role="status">
                  <i aria-hidden="true" />
                  {ok ? (step < 2 ? t(`co.ready.${step}`) : saveLabel) : <><b>{t('co.needLabel')}:</b> {hints[step]}</>}
                </span>
                <button className="co-btn co-btn--solid co-next" disabled={!ok} onClick={next}>
                  {step === 2 ? t(rewrite ? 'co.resubmit' : busy ? 'co.sending' : 'co.submit') : t('co.continue')}
                </button>
              </div>
            </div>
          </div>

          <div className={`co-side${aiOn ? ' co-side--ai' : ''}`}>
            {aiOn ? (
              <OrderAssistant
                orderId={orderId}
                ensureOrder={ensureOrderId}
                sketch={sketch}
                selection={selection}
                onClearSelection={() => setSelection(emptySelection())}
                onChanged={aiChanged}
                onBusy={setAiBusy}
                onConsentNeeded={consentNeeded}
              />
            ) : (
              <aside className="co-rail">
                <div className="co-preview">
                  {/* In upload mode the restoration sits under the photos; this box keeps the original for comparison. */}
                  {order && sketch && mode !== 'upload' ? (
                    <SketchView orderId={order.id} sketch={sketch} />
                  ) : mode === 'text' && previewSrc ? (
                    <img className="co-preview-img" src={previewSrc} alt={t('co.previewAlt')} />
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
                  <div className="co-total-row">
                    <span>{t('co.range')}</span>
                    <span className="co-total">{range}</span>
                  </div>
                  {est && (
                    <div className="co-eta">
                      <div><span>{t('co.minDeposit')}</span><b>{est.minDepositPct}%</b></div>
                    </div>
                  )}
                  {est && <span className="co-fine">{t(`co.basis.${est.basis}`)}</span>}
                  {est && !est.materialsPriced && <span className="co-fine">{t('co.pickMaterialsHint')}</span>}
                  <span className="co-fine">{t('co.fine')}</span>
                </div>
              </aside>
            )}
            <Link to="/account/drafts" className="co-btn co-btn--line co-save">{t('co.saveExit')}</Link>
          </div>
        </div>
      </div>
    </Frame>
  )
}
