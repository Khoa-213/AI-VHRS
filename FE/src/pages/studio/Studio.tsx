import {
  ArrowArcLeft, ArrowArcRight, ArrowClockwise, CaretLeft, CaretRight, CheckCircle, ClockCounterClockwise, Plus,
  Trash, UploadSimple, WarningCircle,
} from '@phosphor-icons/react'
import { useCallback, useEffect, useRef, useState } from 'react'
import CustomerFrame from '../../components/layout/CustomerFrame'
import { useAsync } from '../../hooks/useAsync'
import { useDebounced } from '../../hooks/useDebounced'
import { useLocale, useT } from '../../i18n'
import { Link, navigate, orderPath } from '../../router/router'
import {
  ACCEPTED_UPLOADS, MAX_UPLOAD_MB, errText, getInks, getPapers, getPens, getTemplates, orderErrorKey,
  type Alignment, type Pen,
} from '../../services/orders'
import {
  abandonDraft, checkDraft, createDraft, fetchDraftPreview, getDraft, getRevisions, listDrafts, patchDraft, redoDraft,
  removeDraftImage, rotateDraftImage, submitDraft, undoDraft, uploadDraftImage,
  type Check, type Draft, type DraftCall, type DraftPatch, type StudioMode,
} from '../../services/studio'
import { openAuth } from '../../store/authDialog'
import { useUser } from '../../store/store'
import { fmt } from '../../utils/format'
import Assistant from './Assistant'
import './studio.css'

const ALIGNS: Alignment[] = ['LEFT', 'CENTER', 'RIGHT', 'JUSTIFY']
const RESTORE_MODES = ['FAITHFUL', 'ASSISTED'] as const

function ago(iso: string, locale: string) {
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' })
  const s = Math.round((new Date(iso).getTime() - Date.now()) / 1000)
  const a = Math.abs(s)
  if (a < 45) return rtf.format(0, 'second')
  if (a < 3600) return rtf.format(Math.round(s / 60), 'minute')
  if (a < 86400) return rtf.format(Math.round(s / 3600), 'hour')
  return rtf.format(Math.round(s / 86400), 'day')
}

function Guest() {
  const t = useT()
  return (
    <CustomerFrame label="Studio" narrow>
      <div className="co-card co-card--msg">
        <h1 className="co-h1">{t('stu.guestTitle')}</h1>
        <p className="co-lede">{t('stu.guestBody')}</p>
        <button className="co-btn co-btn--solid" onClick={() => openAuth('login', '/studio')}>{t('nav.signIn')}</button>
      </div>
    </CustomerFrame>
  )
}

const rangeOf = (min: number, max: number) => (min === max ? fmt(max) : `${fmt(min)} - ${fmt(max)}`)

// ---------------------------------------------------------------------------------------------------------- list

/** `/studio`: the customer's drafts and the two ways to start one. */
export function StudioHome() {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const customer = user?.role === 'customer'
  const list = useAsync(async () => (customer ? await listDrafts('OPEN') : []), [customer])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [asking, setAsking] = useState<number | null>(null)

  if (!customer) return <Guest />

  const start = async (mode: StudioMode) => {
    setBusy(true)
    setErr('')
    try {
      const d = await createDraft(mode)
      navigate(`/studio/${d.id}`)
    } catch (e) {
      setErr(orderErrorKey(e))
      setBusy(false)
    }
  }

  const discard = async (id: number) => {
    setErr('')
    try {
      await abandonDraft(id)
      setAsking(null)
      await list.reload()
    } catch (e) {
      setErr(orderErrorKey(e))
    }
  }

  const rows = list.data ?? []
  return (
    <CustomerFrame label="Studio">
      <div className="co stu">
        <header className="co-head">
          <span className="co-eyebrow">{t('stu.eyebrow')}</span>
          <h1 className="co-h1">{t('stu.title')}</h1>
          <p className="co-lede">{t('stu.lede')}</p>
        </header>

        <div className="co-tray co-tray--3 stu-start">
          {(['TEXT', 'RESTORE'] as const).map((m) => (
            <button key={m} className="co-opt" disabled={busy} onClick={() => void start(m)}>
              <span className="co-opt-name"><Plus size={16} aria-hidden /> {t(`stu.new.${m}`)}</span>
              <span className="co-opt-sub">{t(`stu.new.${m}.sub`)}</span>
            </button>
          ))}
        </div>
        {!!err && <p className="stu-error" role="alert">{errText(t, err)}</p>}

        <section aria-labelledby="stu-list-h" className="stu-list-wrap">
          <h2 id="stu-list-h" className="co-h2">{t('stu.list.title')}</h2>
          {list.loading && !list.data && <p className="stu-hint" role="status">{t('stu.loading')}</p>}
          {!!list.error && <p className="stu-error" role="alert">{errText(t, orderErrorKey(list.error))}</p>}
          {!list.loading && !rows.length && !list.error && <p className="stu-hint">{t('stu.list.empty')}</p>}
          <ul className="stu-list">
            {rows.map((d) => (
              <li key={d.id} className="stu-row">
                <div className="stu-row-main">
                  <span className="stu-row-name">{d.title || t('stu.untitled')}</span>
                  <span className="stu-row-meta">
                    <span>{t(`stu.mode.${d.mode}`)}</span>
                    <span>{t('stu.updated', { time: ago(d.updatedAt, locale) })}</span>
                  </span>
                </div>
                <div className="stu-row-side">
                  {asking === d.id ? (
                    <span className="stu-confirm" role="alert">
                      <span>{t('stu.discardAsk')}</span>
                      <button className="co-btn co-btn--line co-btn--sm" onClick={() => void discard(d.id)}>{t('stu.yes')}</button>
                      <button className="co-btn co-btn--line co-btn--sm" onClick={() => setAsking(null)}>{t('stu.no')}</button>
                    </span>
                  ) : (
                    <>
                      <button className="co-btn co-btn--line co-btn--sm" onClick={() => setAsking(d.id)}>
                        <Trash size={16} aria-hidden />{t('stu.discard')}
                      </button>
                      <Link to={`/studio/${d.id}`} className="co-btn co-btn--solid co-btn--sm">{t('stu.open')}</Link>
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </CustomerFrame>
  )
}

// ---------------------------------------------------------------------------------------------------------- preview

/** JPEG preview of one page. It is rendered by the backend (a few seconds for photo restoration), so it waits for the edits to settle. */
function Preview({ draft, ready }: { draft: Draft; ready: boolean }) {
  const t = useT()
  const [page, setPage] = useState(1)
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')
  const rev = useDebounced(draft.revisionId, 700)
  const open = draft.status === 'OPEN'
  const active = open && ready

  useEffect(() => {
    if (!open || !ready) return
    const ctrl = new AbortController()
    let made = ''
    setLoading(true)
    setErr('')
    fetchDraftPreview(draft.id, page, ctrl.signal)
      .then((blob) => {
        made = URL.createObjectURL(blob)
        setUrl(made)
      })
      .catch((e) => {
        if (!ctrl.signal.aborted) {
          setUrl('')
          setErr(orderErrorKey(e))
        }
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false)
      })
    return () => {
      ctrl.abort()
      if (made) URL.revokeObjectURL(made)
    }
  }, [draft.id, rev, page, open, ready])

  return (
    <section className="stu-card" aria-labelledby="stu-pv-h">
      <h2 id="stu-pv-h" className="stu-h2">{t('stu.preview')}</h2>
      <div className="stu-pv" aria-busy={loading}>
        {active && url && <img src={url} alt={t('stu.preview.alt', { n: page })} className={loading ? 'dim' : ''} />}
        {!(active && url) && !loading && !err && <p className="stu-hint">{t('stu.preview.empty')}</p>}
        {loading && <p className="stu-hint" role="status">{t('stu.preview.loading')}</p>}
        {!!err && <p className="stu-error" role="alert">{errText(t, err)}</p>}
      </div>
      <div className="stu-pv-nav">
        <button className="co-btn co-btn--line co-btn--sm" aria-label={t('stu.prevPage')} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
          <CaretLeft size={16} aria-hidden />
        </button>
        <span className="vh-mono">{t('stu.page', { n: page })}</span>
        <button className="co-btn co-btn--line co-btn--sm" aria-label={t('stu.nextPage')} disabled={page >= 20} onClick={() => setPage((p) => p + 1)}>
          <CaretRight size={16} aria-hidden />
        </button>
      </div>
      <p className="stu-hint">{t('stu.preview.note')}</p>
    </section>
  )
}

// ---------------------------------------------------------------------------------------------------------- editor

/** `/studio/:id`: edit a draft, preview it, check it, ask the assistant, then send it to the workshop. */
export function StudioEditor({ id }: { id: number }) {
  const t = useT()
  const locale = useLocale()
  const user = useUser()
  const customer = user?.role === 'customer'
  const first = useAsync(async () => (customer ? await getDraft(id) : null), [id, customer])
  const [draft, setDraft] = useState<Draft | null>(null)
  const [err, setErr] = useState('')
  const [saving, setSaving] = useState(false)
  const [text, setText] = useState('')
  const [title, setTitle] = useState('')
  const [note, setNote] = useState('')
  const [check, setCheck] = useState<Check | null>(null)
  const [checking, setChecking] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [terms, setTerms] = useState(false)
  const [right, setRight] = useState(false)
  const [sending, setSending] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const file = useRef<HTMLInputElement>(null)

  const papers = useAsync(getPapers, [])
  const templates = useAsync(getTemplates, [])
  const paperId = draft?.content.paper_type_id ?? null
  const penId = draft?.content.pen_type_id ?? null
  const pens = useAsync(() => getPens(paperId), [paperId])
  const inks = useAsync(async () => (penId ? await getInks(penId) : []), [penId])
  const revisions = useAsync(async () => (showHistory && draft ? await getRevisions(draft.id) : []), [showHistory, draft?.revisionId])

  /** Take a draft from the server and reset the fields that are typed locally. */
  const adopt = useCallback((d: Draft) => {
    setDraft(d)
    setText(d.content.text ?? '')
    setTitle(d.title ?? '')
    setNote(d.content.customer_note ?? '')
    setCheck(null)
  }, [])

  useEffect(() => {
    if (first.data) adopt(first.data)
  }, [first.data, adopt])

  const run = async (fn: DraftCall) => {
    setSaving(true)
    setErr('')
    try {
      adopt(await fn())
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setSaving(false)
    }
  }

  const change = (patch: DraftPatch) => draft && run(() => patchDraft(draft.id, patch))

  // Typed fields save once the customer stops typing; a server answer replaces the draft (without resetting what is still being typed).
  const dText = useDebounced(text, 800)
  const dTitle = useDebounced(title, 800)
  const dNote = useDebounced(note, 800)
  useEffect(() => {
    if (!draft || draft.status !== 'OPEN') return
    const patch: DraftPatch = {}
    if (draft.mode === 'TEXT' && dText !== (draft.content.text ?? '') && dText === text) patch.text = dText
    if (dTitle !== (draft.title ?? '') && dTitle === title) patch.title = dTitle.trim() || null
    if (dNote !== (draft.content.customer_note ?? '') && dNote === note) patch.customer_note = dNote.trim() || null
    if (!Object.keys(patch).length) return
    let alive = true
    setSaving(true)
    setErr('')
    patchDraft(draft.id, patch)
      .then((d) => alive && setDraft(d))
      .catch((e) => alive && setErr(orderErrorKey(e)))
      .finally(() => alive && setSaving(false))
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dText, dTitle, dNote])

  const onUpload = async (f: File | undefined) => {
    if (!f || !draft) return
    setErr('')
    if (!ACCEPTED_UPLOADS.includes(f.type)) return setErr('msg:' + t('stu.upload.type'))
    if (f.size > MAX_UPLOAD_MB * 1024 * 1024) return setErr('msg:' + t('stu.upload.tooBig'))
    setUploading(true)
    try {
      adopt(await uploadDraftImage(draft.id, f))
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setUploading(false)
      if (file.current) file.current.value = ''
    }
  }

  const runCheck = async () => {
    if (!draft) return
    setChecking(true)
    setErr('')
    try {
      setCheck(await checkDraft(draft.id))
    } catch (e) {
      setErr(orderErrorKey(e))
    } finally {
      setChecking(false)
    }
  }

  const send = async () => {
    if (!draft) return
    setSending(true)
    setErr('')
    try {
      const r = await submitDraft(draft.id, { terms_accepted: terms, confirm_right_to_use: right })
      navigate(orderPath(r.order_id, 'review'))
    } catch (e) {
      setErr(orderErrorKey(e))
      // ORDER_INCOMPLETE carries the open problems.
      void checkDraft(draft.id).then(setCheck).catch(() => undefined)
      setSending(false)
    }
  }

  if (!customer) return <Guest />

  if (!draft) {
    return (
      <CustomerFrame label="Studio" narrow>
        <div className="co-card co-card--msg">
          {first.loading
            ? <p className="co-lede" role="status">{t('stu.loading')}</p>
            : <><p className="stu-error" role="alert">{errText(t, orderErrorKey(first.error))}</p>
              <Link to="/studio" className="co-btn co-btn--solid">{t('stu.backList')}</Link></>}
        </div>
      </CustomerFrame>
    )
  }

  const c = draft.content
  const open = draft.status === 'OPEN'
  const restore = draft.mode === 'RESTORE'
  const problems = check?.problems ?? draft.problems
  const estimate = check?.estimate ?? draft.estimate
  const hasContent = restore ? c.images.length > 0 : !!c.text.trim() && c.template_id !== null
  const pensList: Pen[] = paperId ? pens.data ?? [] : []

  return (
    <CustomerFrame label="Studio">
      <div className="co stu">
        <header className="co-head">
          <Link to="/studio" className="stu-back"><CaretLeft size={16} aria-hidden />{t('stu.backList')}</Link>
          <span className="co-eyebrow">{t(`stu.mode.${draft.mode}`)} · {t(`stu.status.${draft.status}`)}</span>
          <h1 className="co-h1">{draft.title || t('stu.untitled')}</h1>
          <span className="co-save-state" role="status">{saving ? t('stu.saving') : t('stu.saved')}</span>
        </header>

        {!open && (
          <p className="stu-note" role="status">
            {t('stu.closed')} {draft.orderId && <Link to={orderPath(draft.orderId, 'review')} className="vh-link">{t('stu.openOrder')}</Link>}
          </p>
        )}
        {!!err && <p className="stu-error" role="alert">{errText(t, err)}</p>}
        {draft.warnings.map((w) => <p key={w} className="stu-note" role="status">{t(`stu.warn.${w}`)}</p>)}

        <div className="stu-grid">
          <div className="stu-col">
            <section className="stu-card" aria-label={t('stu.titleLabel')}>
              <div className="stu-toolbar">
                <button className="co-btn co-btn--line co-btn--sm" disabled={!open || !draft.canUndo || saving} onClick={() => void run(() => undoDraft(draft.id))}>
                  <ArrowArcLeft size={16} aria-hidden />{t('stu.undo')}
                </button>
                <button className="co-btn co-btn--line co-btn--sm" disabled={!open || !draft.canRedo || saving} onClick={() => void run(() => redoDraft(draft.id))}>
                  <ArrowArcRight size={16} aria-hidden />{t('stu.redo')}
                </button>
                <button className="co-btn co-btn--line co-btn--sm" aria-expanded={showHistory} onClick={() => setShowHistory((v) => !v)}>
                  <ClockCounterClockwise size={16} aria-hidden />{t('stu.history')}
                </button>
              </div>
              {showHistory && (
                <ol className="stu-history" aria-label={t('stu.history')}>
                  {revisions.loading && !revisions.data && <li className="stu-hint">{t('stu.loading')}</li>}
                  {!revisions.loading && !(revisions.data ?? []).length && <li className="stu-hint">{t('stu.history.empty')}</li>}
                  {[...(revisions.data ?? [])].reverse().map((r) => (
                    <li key={r.id} className={r.isCurrent ? 'cur' : ''}>
                      <span>{r.author === 'AI' ? t('stu.rev.ai', { tool: r.toolName ?? '' }) : t('stu.rev.you')}</span>
                      <span className="vh-mono">{new Date(r.createdAt).toLocaleString(locale)}</span>
                      {r.isCurrent && <b>{t('stu.rev.now')}</b>}
                    </li>
                  ))}
                </ol>
              )}
              <div className="stu-field">
                <label className="co-group-label" htmlFor="stu-title">{t('stu.titleLabel')}</label>
                <input id="stu-title" className="stu-input" maxLength={150} value={title} disabled={!open} placeholder={t('stu.titlePh')} onChange={(e) => setTitle(e.target.value)} />
              </div>
            </section>

            {!restore && (
              <section className="stu-card" aria-labelledby="stu-text-h">
                <h2 id="stu-text-h" className="stu-h2">{t('stu.text')}</h2>
                <textarea
                  className="stu-input stu-text"
                  rows={6}
                  maxLength={20000}
                  value={text}
                  disabled={!open}
                  aria-label={t('stu.text')}
                  placeholder={t('stu.textPh')}
                  onChange={(e) => setText(e.target.value)}
                />
                <span className="stu-hint vh-mono">{t('stu.chars', { n: text.length })}</span>

                <div className="stu-field">
                  <label className="co-group-label" htmlFor="stu-style">{t('stu.style')}</label>
                  <select id="stu-style" className="stu-input" disabled={!open} value={c.template_id ?? ''} onChange={(e) => void change({ template_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">{t('stu.styleNone')}</option>
                    {(templates.data ?? []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                  </select>
                </div>

                <div className="stu-field">
                  <label className="co-group-label" htmlFor="stu-size">{t('stu.size')}</label>
                  <input
                    id="stu-size"
                    className="stu-input stu-num"
                    type="number"
                    min={4}
                    max={100}
                    step={0.5}
                    disabled={!open}
                    defaultValue={c.font_size_mm ?? ''}
                    key={`size-${draft.revisionId}`}
                    onBlur={(e) => {
                      const v = e.target.value === '' ? null : Number(e.target.value)
                      if (v !== c.font_size_mm) void change({ font_size_mm: v })
                    }}
                  />
                </div>

                <div className="stu-field">
                  <span className="co-group-label">{t('stu.align')}</span>
                  <div className="co-seg" role="group" aria-label={t('stu.align')}>
                    <button type="button" className={c.alignment === null ? 'on' : ''} aria-pressed={c.alignment === null} disabled={!open} onClick={() => void change({ alignment: null })}>{t('stu.align.none')}</button>
                    {ALIGNS.map((a) => (
                      <button key={a} type="button" className={c.alignment === a ? 'on' : ''} aria-pressed={c.alignment === a} disabled={!open} onClick={() => void change({ alignment: a })}>{t(`stu.align.${a}`)}</button>
                    ))}
                  </div>
                </div>
              </section>
            )}

            {restore && (
              <section className="stu-card" aria-labelledby="stu-img-h">
                <h2 id="stu-img-h" className="stu-h2">{t('stu.images')}</h2>
                {!c.images.length && <p className="stu-hint">{t('stu.images.empty')}</p>}
                <ul className="stu-images">
                  {c.images.map((img, n) => (
                    <li key={img.id}>
                      <span>{t('stu.image.n', { n: n + 1 })}</span>
                      <span className="stu-images-act">
                        <button className="co-btn co-btn--line co-btn--sm" disabled={!open || saving} onClick={() => void run(() => rotateDraftImage(draft.id, img.id, (((img.rotation_deg ?? 0) + 90) % 360) as 0 | 90 | 180 | 270))}>
                          <ArrowClockwise size={16} aria-hidden />{t('stu.rotate')}
                        </button>
                        <button className="co-btn co-btn--line co-btn--sm" disabled={!open || saving} onClick={() => void run(() => removeDraftImage(draft.id, img.id))}>
                          <Trash size={16} aria-hidden />{t('stu.remove')}
                        </button>
                      </span>
                    </li>
                  ))}
                </ul>
                <input ref={file} type="file" hidden accept={ACCEPTED_UPLOADS.join(',')} onChange={(e) => void onUpload(e.target.files?.[0])} />
                <button className="co-btn co-btn--line co-btn--sm stu-upload" disabled={!open || uploading} onClick={() => file.current?.click()}>
                  <UploadSimple size={16} aria-hidden />{t(uploading ? 'stu.uploading' : 'stu.upload')}
                </button>
                <span className="stu-hint">{t('stu.upload.hint')}</span>

                <div className="stu-field">
                  <span className="co-group-label">{t('stu.restore.mode')}</span>
                  <div className="co-tray co-tray--2" role="radiogroup" aria-label={t('stu.restore.mode')}>
                    {RESTORE_MODES.map((m) => (
                      <button key={m} type="button" role="radio" aria-checked={c.restoration_mode === m} disabled={!open} className={`co-opt${c.restoration_mode === m ? ' on' : ''}`} onClick={() => void change({ restoration_mode: m })}>
                        <span className="co-opt-name">{t(`stu.restore.${m}`)}</span>
                        <span className="co-opt-sub">{t(`stu.restore.${m}.sub`)}</span>
                      </button>
                    ))}
                  </div>
                </div>
              </section>
            )}

            <section className="stu-card" aria-labelledby="stu-mat-h">
              <h2 id="stu-mat-h" className="stu-h2">{t('stu.materials')}</h2>
              <label className="stu-check">
                <input type="checkbox" disabled={!open} checked={c.workshop_suggest_materials} onChange={(e) => void change({ workshop_suggest_materials: e.target.checked })} />
                <span>{t('stu.suggest')}</span>
              </label>
              <div className="stu-trio">
                <div className="stu-field">
                  <label className="co-group-label" htmlFor="stu-paper">{t('stu.paper')}</label>
                  <select id="stu-paper" className="stu-input" disabled={!open} value={paperId ?? ''} onChange={(e) => void change({ paper_type_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">{t('stu.pick')}</option>
                    {(papers.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name} · {p.size}</option>)}
                  </select>
                </div>
                <div className="stu-field">
                  <label className="co-group-label" htmlFor="stu-pen">{t('stu.pen')}</label>
                  <select id="stu-pen" className="stu-input" disabled={!open || !paperId} value={penId ?? ''} onChange={(e) => void change({ pen_type_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">{paperId ? t('stu.pick') : t('stu.pickPaperFirst')}</option>
                    {pensList.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                <div className="stu-field">
                  <label className="co-group-label" htmlFor="stu-ink">{t('stu.ink')}</label>
                  <select id="stu-ink" className="stu-input" disabled={!open || !penId} value={c.ink_color_id ?? ''} onChange={(e) => void change({ ink_color_id: e.target.value ? Number(e.target.value) : null })}>
                    <option value="">{penId ? t('stu.pick') : t('stu.pickPenFirst')}</option>
                    {(penId ? inks.data ?? [] : []).map((i) => <option key={i.id} value={i.id}>{i.name}</option>)}
                  </select>
                </div>
              </div>

              <div className="stu-field">
                <label className="co-group-label" htmlFor="stu-qty">{t('stu.qty')}</label>
                <input
                  id="stu-qty"
                  className="stu-input stu-num"
                  type="number"
                  min={1}
                  max={10000}
                  disabled={!open}
                  defaultValue={c.quantity}
                  key={`qty-${draft.revisionId}`}
                  onBlur={(e) => {
                    const v = Math.min(10000, Math.max(1, Math.round(Number(e.target.value) || 1)))
                    if (v !== c.quantity) void change({ quantity: v })
                    else e.target.value = String(v)
                  }}
                />
              </div>

              <label className="stu-check">
                <input type="checkbox" disabled={!open || restore} checked={c.physical_watermark} onChange={(e) => void change({ physical_watermark: e.target.checked })} />
                <span><b>{t('stu.watermark')}</b><br />{t('stu.watermark.sub')}{restore && <> {t('stu.watermark.forced')}</>}</span>
              </label>

              <div className="stu-field">
                <label className="co-group-label" htmlFor="stu-note">{t('stu.note')}</label>
                <textarea id="stu-note" className="stu-input" rows={3} maxLength={2000} value={note} disabled={!open} placeholder={t('stu.notePh')} onChange={(e) => setNote(e.target.value)} />
              </div>
            </section>
          </div>

          <aside className="stu-col stu-side">
            <Preview draft={draft} ready={hasContent} />

            <section className="stu-card" aria-labelledby="stu-chk-h">
              <h2 id="stu-chk-h" className="stu-h2">{t('stu.check')}</h2>
              {estimate && (
                <p className="stu-estimate">
                  {t('stu.estimate', { range: rangeOf(estimate.priceMin, estimate.priceMax) })}
                  {!estimate.materialsPriced && <span className="stu-hint"> {t('stu.estimate.noMaterials')}</span>}
                </p>
              )}
              {check?.pages != null && <p className="stu-hint">{t('stu.check.pages', { n: check.pages })}</p>}
              {problems.length > 0 ? (
                <div>
                  <b className="stu-problems-h"><WarningCircle size={16} aria-hidden /> {t('stu.problems')}</b>
                  <ul className="stu-problems">{problems.map((p, i) => <li key={`${p.field}-${p.code}-${i}`}>{p.message}</li>)}</ul>
                </div>
              ) : (check ?? draft).ready && (
                <p className="stu-ok"><CheckCircle size={16} aria-hidden /> {t('stu.check.ok')}</p>
              )}
              <button className="co-btn co-btn--line co-btn--sm" disabled={!open || checking || !hasContent} onClick={() => void runCheck()}>
                {t(checking ? 'stu.checking' : 'stu.check')}
              </button>
            </section>

            <Assistant draft={draft} onDraft={adopt} />

            {open && (
              <section className="stu-card" aria-labelledby="stu-sub-h">
                <h2 id="stu-sub-h" className="stu-h2">{t('stu.submit.title')}</h2>
                <p className="stu-hint">{t('stu.submit.sub')}</p>
                <label className="stu-check"><input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} /><span>{t('stu.terms')}</span></label>
                <label className="stu-check"><input type="checkbox" checked={right} onChange={(e) => setRight(e.target.checked)} /><span>{t('stu.right')}</span></label>
                <button className="co-btn co-btn--solid" disabled={sending || saving || !terms || !right || !hasContent} onClick={() => void send()}>
                  {t(sending ? 'stu.submitting' : 'stu.submit')}
                </button>
              </section>
            )}
          </aside>
        </div>
      </div>
    </CustomerFrame>
  )
}
