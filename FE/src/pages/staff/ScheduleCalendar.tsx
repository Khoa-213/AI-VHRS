import { CaretLeft, CaretRight } from '@phosphor-icons/react'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { errText, orderErrorKey } from '../../services/orders'
import {
  calendarJobs, listRobots, listTechnicians, scheduleConfig, scheduleOrder, scheduleSuggestion, type Robot, type ScheduleConfig,
} from '../../services/workshop'
import {
  addDays, addWorkingMinutes, at, checkSlot, clockOf, dateKey, dayMinutes, deadlineOf, hm, inDay, lateDays, weekDays, workingDayFrom, type Deadline, type Verdict,
} from './scheduleMath'

const HOUR_PX = 72
const PX = HOUR_PX / 60
const COMPACT_PX = 44
const MIN_BLOCK_PX = 20
const LOOKAHEAD_DAYS = 21

export interface ScheduleTarget {
  id: number
  code: string
}

interface Draft {
  robotId: number
  date: string
  time: string
}

/** A week or day of robot jobs from the API. With `order`, a click on a free time opens the booking form for it. */
export default function ScheduleCalendar({ order, version, onBooked }: { order?: ScheduleTarget; version: number; onBooked: () => void }) {
  const t = useT()
  const config = useAsync(scheduleConfig, [])
  if (config.error) {
    return (
      <section className="wk-block">
        <p className="lg-error" role="alert">{errText(t, orderErrorKey(config.error))}</p>
        <button className="vh-btn vh-btn--ghost vh-btn--sm wk-self" onClick={() => void config.reload()}>{t('wk.cal.retry')}</button>
      </section>
    )
  }
  if (!config.data) return <section className="wk-block"><p className="sd-sub" role="status">{t('co.loading')}</p></section>
  return <Calendar config={config.data} order={order} version={version} onBooked={onBooked} />
}

function Calendar({ config: c, order, version, onBooked }: { config: ScheduleConfig; order?: ScheduleTarget; version: number; onBooked: () => void }) {
  const t = useT()
  const locale = useLocale()
  const robots = useAsync(listRobots, [])
  const techs = useAsync(listTechnicians, [])
  const sug = useAsync(async () => (order ? scheduleSuggestion(order.id) : null), [order?.id, version])
  const [now, setNow] = useState(() => Date.now())
  const [view, setView] = useState<'week' | 'day'>('week')
  const [focus, setFocus] = useState(() => workingDayFrom(c, dateKey(c, Date.now()), 1))
  const [robotPick, setRobotPick] = useState<number | null>(null)
  const [techPick, setTechPick] = useState<number | null>(null)
  const [hover, setHover] = useState<{ robotId: number; start: number } | null>(null)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const days = useMemo(() => (view === 'week' ? weekDays(c, focus) : [focus]), [c, view, focus])
  const firstDay = days[0]
  const lastDay = days[days.length - 1]
  // Further than the view, so a long job's clash shows even when it runs past the last day on screen.
  const jobsQ = useAsync(
    () => calendarJobs(new Date(at(c, firstDay, 0)).toISOString(), new Date(at(c, addDays(lastDay, LOOKAHEAD_DAYS), 0)).toISOString()),
    [c, firstDay, lastDay, version],
    30000,
  )
  useEffect(() => {
    const h = window.setInterval(() => setNow(Date.now()), 30000)
    return () => window.clearInterval(h)
  }, [])

  const jobs = useMemo(() => jobsQ.data ?? [], [jobsQ.data])
  const robotList = useMemo(() => robots.data ?? [], [robots.data])
  const techList = useMemo(() => techs.data ?? [], [techs.data])
  const robotId = robotPick ?? robotList.find((r) => r.status === 'AVAILABLE')?.id ?? robotList[0]?.id ?? null
  const techId = techPick ?? sug.data?.suggestions[0]?.technicianId ?? techList[0]?.id ?? null
  const robot = robotList.find((r) => r.id === robotId)
  const tech = techList.find((x) => x.id === techId)
  const minutes = order ? sug.data?.durationMin ?? 0 : 0
  const bookable = !!order && minutes > 0 && techId !== null
  const deadline: Deadline = useMemo(() => (order && sug.data ? deadlineOf(c, sug.data.eta, now) : { state: 'none' }), [c, order, sug.data, now])
  const today = dateKey(c, now)
  const height = dayMinutes(c) * PX

  const dayName = (key: string, opts: Intl.DateTimeFormatOptions) => new Date(`${key}T00:00:00Z`).toLocaleDateString(locale, { timeZone: 'UTC', ...opts })
  const shortDate = (key: string) => dayName(key, { day: '2-digit', month: '2-digit' })
  const longDay = (key: string) => dayName(key, { weekday: 'short', day: '2-digit', month: '2-digit' })
  const span = (start: number, end: number) => {
    const a = dateKey(c, start)
    const b = dateKey(c, end)
    return a === b ? `${longDay(a)}, ${clockOf(c, start)} → ${clockOf(c, end)}` : `${longDay(a)}, ${clockOf(c, start)} → ${longDay(b)}, ${clockOf(c, end)}`
  }
  const deadlineText = (d: Deadline) => {
    if (d.state === 'none') return t('wk.cal.noEta')
    if (d.state === 'overdue') return t('wk.cal.overdue', { date: shortDate(d.eta) })
    if (d.state === 'tight') return t('wk.cal.tight', { date: shortDate(d.eta) })
    return t('wk.cal.finishBy', { date: shortDate(d.eta), safe: shortDate(d.safe) })
  }
  const verdictText = (v: Verdict) => {
    switch (v.kind) {
      case 'robot': return t('wk.cal.robotOff', { status: t(`rs.${v.status}`) })
      case 'closed': return t('wk.cal.closed', { start: c.workingHours.start, end: c.workingHours.end })
      case 'past': return t('wk.cal.past')
      case 'robotBusy': return t('wk.cal.robotBusy', { code: v.code })
      case 'techBusy': return t('wk.cal.techBusy', { code: v.code })
      default: return ''
    }
  }
  const lateFor = (end: number) => lateDays(c, deadline, end)

  const move = (dir: 1 | -1) => {
    setHover(null)
    setFocus(view === 'week' ? addDays(focus, dir * 7) : workingDayFrom(c, addDays(focus, dir), dir))
  }
  const openDraft = (id: number, start: number, tid?: number) => {
    if (tid !== undefined) setTechPick(tid)
    setHover(null)
    setErr('')
    setDraft({ robotId: id, date: dateKey(c, start), time: clockOf(c, start) })
  }
  const closeDraft = () => {
    setDraft(null)
    setErr('')
  }

  const draftStart = draft ? at(c, draft.date, hm(draft.time)) : 0
  const draftRobot = draft ? robotList.find((r) => r.id === draft.robotId) : undefined
  const draftCheck: Verdict | null = draftRobot && techId !== null ? checkSlot(c, draftRobot, techId, draftStart, minutes, jobs, now) : null
  const draftEnd = draftCheck && draftCheck.kind !== 'closed' ? addWorkingMinutes(c, draftStart, minutes) : null

  const book = async () => {
    if (!order || !draft || techId === null || busy) return
    setBusy(true)
    setErr('')
    try {
      await scheduleOrder(order.id, {
        robot_id: draft.robotId,
        technician_id: techId,
        slot_start: new Date(draftStart).toISOString(),
        ...(note.trim() ? { note: note.trim() } : {}),
      })
      setDraft(null)
      setNote('')
      onBooked()
    } catch (e) {
      setErr(orderErrorKey(e))
      void jobsQ.reload()
    } finally {
      setBusy(false)
    }
  }

  const cols: { key: string; robot: Robot; day: string }[] = robot || view === 'day'
    ? (view === 'week' ? days.map((d) => ({ key: d, robot: robot as Robot, day: d })) : robotList.map((r) => ({ key: String(r.id), robot: r, day: focus })))
    : []

  const pointerStart = (e: MouseEvent<HTMLButtonElement>, day: string) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const raw = ((e.clientY - rect.top) / rect.height) * dayMinutes(c)
    const stepped = Math.floor(raw / c.slotStepMin) * c.slotStepMin
    return at(c, day, hm(c.workingHours.start) + Math.max(0, Math.min(dayMinutes(c) - c.slotStepMin, stepped)))
  }
  const keyMove = (e: KeyboardEvent<HTMLButtonElement>, col: { robot: Robot; day: string }) => {
    if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return
    e.preventDefault()
    const open = at(c, col.day, hm(c.workingHours.start))
    const last = open + (dayMinutes(c) - c.slotStepMin) * 60000
    const cur = hover && hover.robotId === col.robot.id && dateKey(c, hover.start) === col.day ? hover.start : open
    setHover({ robotId: col.robot.id, start: Math.max(open, Math.min(last, cur + (e.key === 'ArrowDown' ? 1 : -1) * c.slotStepMin * 60000)) })
  }
  const block = (from: number, mins: number) => {
    const h = Math.max(mins * PX - 1, MIN_BLOCK_PX)
    return { style: { top: from * PX, height: h }, compact: h < COMPACT_PX }
  }

  const hours = Array.from({ length: Math.ceil(dayMinutes(c) / 60) }, (_, i) => hm(c.workingHours.start) + i * 60)
  const hint = !order
    ? t('wk.cal.pickOrder')
    : sug.error
      ? errText(t, orderErrorKey(sug.error))
      : sug.data
        ? `${t('wk.cal.booking', { code: order.code, min: minutes })} ${deadlineText(deadline)}`
        : t('co.loading')
  const hintTone = !!sug.error || deadline.state === 'overdue' || deadline.state === 'tight' ? ' bad' : ''

  return (
    <section className="wk-block wc-card">
      <div className="wc-bar">
        <button className="vh-btn vh-btn--ghost vh-btn--sm" onClick={() => setFocus(workingDayFrom(c, today, 1))}>{t('wk.cal.today')}</button>
        <span className="wc-nav">
          <button aria-label={t('wk.cal.prev')} onClick={() => move(-1)}><CaretLeft size={16} aria-hidden /></button>
          <button aria-label={t('wk.cal.next')} onClick={() => move(1)}><CaretRight size={16} aria-hidden /></button>
        </span>
        <b className="wc-range">{view === 'week' ? `${shortDate(firstDay)} → ${shortDate(lastDay)}` : longDay(focus)}</b>
        <span className="wc-space" />
        {view === 'week' && (
          <label className="wc-pick">
            {t('wk.robot')}
            <select className="vh-select" value={robotId ?? ''} onChange={(e) => setRobotPick(Number(e.target.value))}>
              {robotList.map((r) => <option key={r.id} value={r.id}>{r.code} · {t(`rs.${r.status}`)}</option>)}
            </select>
          </label>
        )}
        <label className="wc-pick">
          {t('wk.technician')}
          <select className="vh-select" value={techId ?? ''} onChange={(e) => setTechPick(Number(e.target.value))}>
            {techList.map((x) => <option key={x.id} value={x.id}>{x.fullName} · {t('wk.activeJobs', { n: x.activeJobs })}</option>)}
          </select>
        </label>
        <span className="wk-tabs wc-tabs" role="group" aria-label={t('wk.cal.view')}>
          <button className={view === 'day' ? 'on' : ''} aria-pressed={view === 'day'} onClick={() => setView('day')}>{t('wk.cal.day')}</button>
          <button className={view === 'week' ? 'on' : ''} aria-pressed={view === 'week'} onClick={() => setView('week')}>{t('wk.cal.week')}</button>
        </span>
      </div>

      <p className={`wc-hint${hintTone}`} aria-live="polite">{hint}</p>
      {[robots.error, techs.error, jobsQ.error].filter(Boolean).slice(0, 1).map((e, i) => <p key={i} className="lg-error" role="alert">{errText(t, orderErrorKey(e))}</p>)}
      {sug.data?.stockWarnings.map((w) => <p key={w} className="wk-warn">{w}</p>)}

      {order && sug.data && (
        <div className="wc-sugs">
          <h3>{t('wk.suggestions')}</h3>
          {!sug.data.suggestions.length && <p className="sd-sub">{t('wk.noSuggestions')}</p>}
          <div className="wc-sug-list">
            {sug.data.suggestions.map((s) => (
              <button key={`${s.robotId}-${s.slotStart}`} className="wc-sug" onClick={() => { setFocus(dateKey(c, Date.parse(s.slotStart))); setRobotPick(s.robotId); openDraft(s.robotId, Date.parse(s.slotStart), s.technicianId) }}>
                <b>{s.robotCode}{s.isSimulated ? ` · ${t('wk.simulated')}` : ''} · {s.technicianName}</b>
                <span>{span(Date.parse(s.slotStart), Date.parse(s.slotEnd))}</span>
                {s.etaRisk && <span className="wc-risk">{deadline.state === 'overdue' ? t('wk.cal.alreadyLate') : t('wk.cal.lateDays', { n: lateFor(Date.parse(s.slotEnd)) })}</span>}
              </button>
            ))}
          </div>
        </div>
      )}

      {robots.data && !robotList.length && <p className="sd-sub">{t('wk.cal.noRobots')}</p>}
      {robots.data && techs.data && !techList.length && <p className="sd-sub">{t('wk.cal.noTechs')}</p>}

      <div className="wc-scroll">
        <div className="wc-grid" style={{ minWidth: 56 + cols.length * (view === 'week' ? 128 : 200) }}>
          <div className="wc-row wc-head">
            <div className="wc-gutter" />
            {cols.map((col) => {
              const isToday = view === 'week' && col.day === today
              return (
                <div key={col.key} className={`wc-colhead${isToday ? ' today' : ''}`}>
                  <span>{view === 'week' ? dayName(col.day, { weekday: 'short' }) : t(`rs.${col.robot.status}`)}</span>
                  <b>{view === 'week' ? dayName(col.day, { day: '2-digit' }) : col.robot.code}</b>
                  {deadline.state !== 'none' && deadline.eta === col.day && <i className="wc-chip">{t('wk.cal.etaChip')}</i>}
                  {deadline.state === 'normal' && deadline.lastOk === col.day && <i className="wc-chip dark">{t('wk.cal.lastOkChip')}</i>}
                </div>
              )
            })}
          </div>
          <div className="wc-row">
            <div className="wc-gutter wc-hours" style={{ height }}>
              {hours.map((h, i) => <span key={h} style={{ top: i * HOUR_PX + 1 }}>{`${String(Math.floor(h / 60)).padStart(2, '0')}:${String(h % 60).padStart(2, '0')}`}</span>)}
            </div>
            {cols.map((col) => {
              const locked = col.robot.status !== 'AVAILABLE'
              const open = at(c, col.day, hm(c.workingHours.start))
              const pastMin = Math.max(0, Math.min(dayMinutes(c), (now - open) / 60000))
              const late = deadline.state === 'normal' && col.day > deadline.lastOk
              const nowIn = open <= now && open + dayMinutes(c) * 60000 > now
              const hovering = hover && hover.robotId === col.robot.id && bookable && !draft ? hover : null
              const ghost = hovering ? inDay(c, hovering.start, addWorkingMinutes(c, hovering.start, minutes), col.day) : null
              const ghostCheck = hovering && techId !== null ? checkSlot(c, col.robot, techId, hovering.start, minutes, jobs, now) : null
              const ghostLate = hovering && ghostCheck?.kind === 'ok' ? lateFor(addWorkingMinutes(c, hovering.start, minutes)) : 0
              const draftHere = draft && draft.robotId === col.robot.id && draftEnd ? inDay(c, draftStart, draftEnd, col.day) : null
              return (
                <div key={col.key} className="wc-col" style={{ height, backgroundSize: `100% ${HOUR_PX}px, 100% ${HOUR_PX / 2}px` }}>
                  {locked && <><div className="wc-locked" /><span className="wc-lock-text">{t('wk.cal.robotOff', { status: t(`rs.${col.robot.status}`) })}</span></>}
                  <div className="wc-past" style={{ height: pastMin * PX }} />
                  {late && <div className="wc-late" />}
                  <button
                    className="wc-slot"
                    disabled={locked || !bookable}
                    aria-label={t('wk.cal.slotAria', { robot: col.robot.code, day: longDay(col.day) })}
                    onMouseMove={(e) => {
                      const start = pointerStart(e, col.day)
                      if (!hover || hover.robotId !== col.robot.id || hover.start !== start) setHover({ robotId: col.robot.id, start })
                    }}
                    onMouseLeave={() => setHover(null)}
                    onKeyDown={(e) => keyMove(e, col)}
                    onClick={(e) => openDraft(col.robot.id, e.detail === 0 && hover ? hover.start : pointerStart(e, col.day))}
                  />
                  {!locked && techId !== null && jobs.filter((j) => j.technicianId === techId).map((j) => {
                    const seg = inDay(c, Date.parse(j.slotStart), Date.parse(j.slotEnd), col.day)
                    return seg ? <div key={j.id} className="wc-busy" style={{ top: seg.from * PX, height: seg.minutes * PX }} /> : null
                  })}
                  {jobs.filter((j) => j.robotId === col.robot.id).map((j) => {
                    const seg = inDay(c, Date.parse(j.slotStart), Date.parse(j.slotEnd), col.day)
                    if (!seg) return null
                    const b = block(seg.from, seg.minutes)
                    return (
                      <Link
                        key={j.id}
                        to={`/staff/review/${j.orderId}`}
                        className={`wc-ev ${j.status === 'SCHEDULED' ? 'sched' : 'run'}${b.compact ? ' compact' : ''}`}
                        style={b.style}
                        title={`${j.orderCode} · ${j.technicianName} · ${t(`js.${j.status}`)} · ${span(Date.parse(j.slotStart), Date.parse(j.slotEnd))}`}
                      >
                        <b>{j.orderCode}</b><span>{j.technicianName}</span>
                      </Link>
                    )
                  })}
                  {!draft && sug.data?.suggestions.filter((s) => s.robotId === col.robot.id).map((s) => {
                    const seg = inDay(c, Date.parse(s.slotStart), Date.parse(s.slotEnd), col.day)
                    if (!seg) return null
                    const b = block(seg.from, seg.minutes)
                    return (
                      <button key={s.slotStart} className="wc-sugg" style={b.style} title={span(Date.parse(s.slotStart), Date.parse(s.slotEnd))} onClick={() => openDraft(s.robotId, Date.parse(s.slotStart), s.technicianId)}>
                        {t('wk.cal.suggested', { name: s.technicianName })}
                      </button>
                    )
                  })}
                  {draftHere && (() => {
                    const b = block(draftHere.from, draftHere.minutes)
                    return <div className={`wc-ev draft${b.compact ? ' compact' : ''}`} style={b.style}><b>{order?.code}</b><span>{clockOf(c, draftStart)}</span></div>
                  })()}
                  {ghost && hovering && ghostCheck && (() => {
                    const b = block(ghost.from, ghost.minutes)
                    const kind = ghostCheck.kind !== 'ok' ? 'bad' : ghostLate ? 'risk' : 'ok'
                    return (
                      <div className={`wc-ev ${kind}${b.compact ? ' compact' : ''}`} style={b.style}>
                        <b>{kind === 'bad' ? verdictText(ghostCheck) : clockOf(c, hovering.start)}</b>
                        {kind === 'risk' && <span>{t('wk.cal.lateDays', { n: ghostLate })}</span>}
                      </div>
                    )
                  })()}
                  {deadline.state === 'normal' && deadline.lastOk === col.day && view === 'week' && <div className="wc-lastok" />}
                  {nowIn && <div className="wc-now" style={{ top: pastMin * PX }} />}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <div className="wc-legend">
        <span><i className="sched" />{t('js.SCHEDULED')}</span>
        <span><i className="run" />{t('wk.cal.legendRun')}</span>
        {bookable && <span><i className="sugg" />{t('wk.suggestions')}</span>}
        <span><i className="busy" />{tech ? t('wk.cal.legendBusy', { name: tech.fullName }) : ''}</span>
        {deadline.state === 'normal' && <span><i className="late" />{t('wk.cal.legendLate')}</span>}
      </div>

      {draft && order && (
        <BookDialog onClose={closeDraft}>
          <h2>{t('wk.cal.dialogTitle', { code: order.code })}</h2>
          <p className="sd-sub">{t('wk.cal.needs', { min: minutes })}</p>
          <p className={`wc-dl${hintTone}`}>{deadlineText(deadline)}</p>
          {sug.data?.stockWarnings.map((w) => <p key={w} className="wk-warn">{w}</p>)}
          {err && <p className="lg-error" role="alert">{errText(t, err)}</p>}
          <div className="wc-fields">
            <label className="vh-label">
              {t('wk.robot')}
              <select className="vh-select" value={draft.robotId} onChange={(e) => setDraft({ ...draft, robotId: Number(e.target.value) })}>
                {robotList.map((r) => <option key={r.id} value={r.id} disabled={r.status !== 'AVAILABLE'}>{r.code} · {t(`rs.${r.status}`)}</option>)}
              </select>
            </label>
            <label className="vh-label">
              {t('wk.technician')}
              <select className="vh-select" value={techId ?? ''} onChange={(e) => setTechPick(Number(e.target.value))}>
                {techList.map((x) => <option key={x.id} value={x.id}>{x.fullName}</option>)}
              </select>
            </label>
            <label className="vh-label">
              {t('wk.cal.date')}
              <input className="vh-input" type="date" value={draft.date} onChange={(e) => e.target.value && setDraft({ ...draft, date: e.target.value })} />
            </label>
            <label className="vh-label">
              {t('wk.slot')}
              <input className="vh-input" type="time" step={c.slotStepMin * 60} value={draft.time} onChange={(e) => e.target.value && setDraft({ ...draft, time: e.target.value })} />
            </label>
          </div>
          {draftEnd !== null && <p className="sd-sub">{t('wk.cal.endsAt', { when: `${longDay(dateKey(c, draftEnd))}, ${clockOf(c, draftEnd)}` })}</p>}
          {draftCheck && (
            <p className={`wc-verdict ${draftCheck.kind !== 'ok' ? 'bad' : draftEnd && lateFor(draftEnd) && deadline.state !== 'none' ? 'risk' : 'ok'}`} aria-live="polite">
              {draftCheck.kind !== 'ok'
                ? verdictText(draftCheck)
                : deadline.state === 'overdue'
                  ? t('wk.cal.alreadyLate')
                  : deadline.state === 'none'
                    ? t('wk.cal.etaWillSet', { date: draftEnd ? shortDate(addDays(dateKey(c, draftEnd), c.etaBufferDays)) : '' })
                    : draftEnd && lateFor(draftEnd)
                      ? t('wk.cal.lateDays', { n: lateFor(draftEnd) })
                      : t('wk.cal.onTime')}
            </p>
          )}
          <label className="vh-label">
            {t('co.sum.note')}
            <input className="vh-input" value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />
          </label>
          <div className="wc-actions">
            <button className="vh-btn vh-btn--ghost vh-btn--md" onClick={closeDraft}>{t('ov.back')}</button>
            <button className="vh-btn vh-btn--primary vh-btn--md" disabled={busy || draftCheck?.kind !== 'ok'} onClick={() => void book()}>{t('wk.book')}</button>
          </div>
        </BookDialog>
      )}
    </section>
  )
}

function BookDialog({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  const t = useT()
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const before = document.activeElement as HTMLElement | null
    box.current?.focus()
    return () => before?.focus?.()
  }, [])
  return (
    <div className="wc-overlay">
      <div ref={box} className="wc-dialog" role="dialog" aria-modal="true" aria-label={t('wk.book')} tabIndex={-1} onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}>
        {children}
      </div>
    </div>
  )
}
