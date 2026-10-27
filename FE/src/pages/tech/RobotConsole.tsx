import { Pause, Play, Stop } from '@phosphor-icons/react'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT, type TFn } from '../../i18n'
import { ApiError } from '../../services/api'
import type { Job } from '../../services/async'
import {
  getLive, jobCommands, sendCommand, waitCommand,
  type CommandKind, type Live, type LiveFrame, type RobotCommand,
} from '../../services/robot'
import { useRobotStatus } from '../../store/robotStatus'
import { simulateJob, startJob, type TechJobDetail } from '../../services/technician'
import { flowError, type TechRun } from './flow'

/** The workshop runs the real arm only; MOCK and SIM stay on the workstation for testing. */
const MODE = 'REAL'
const LOADABLE = ['PREPARING', 'WRITING', 'PAUSED']

/** The agent's answer to a command, in words: a translated code when we know it, else the agent's own message. */
function commandError(c: RobotCommand, t: TFn): string {
  if (c.status === 'EXPIRED') return t('rb.err.expired')
  if (c.status === 'CANCELLED') return t('rb.err.cancelled')
  const key = `rb.agentErr.${c.errorCode}`
  const known = c.errorCode ? t(key) : key
  return known !== key ? known : c.errorMessage || c.errorCode || t('rb.err.failed')
}

/** Live frames of the robot: 4 times a second while it runs, once a second otherwise, paused while the tab is hidden. */
function useLive(robotId: number) {
  const [live, setLive] = useState<Live | null>(null)
  const [frame, setFrame] = useState<LiveFrame | null>(null)
  const [error, setError] = useState<unknown>(null)
  useEffect(() => {
    let stopped = false
    let after = 0
    let timer = 0
    const tick = async () => {
      let wait = 1000
      if (!document.hidden) {
        try {
          const l = await getLive(robotId, after)
          if (stopped) return
          // The backend keeps frames in memory; after a restart its counter starts again from zero.
          after = l.lastSeq < after ? 0 : l.lastSeq
          if (l.frames.length) setFrame(l.frames[l.frames.length - 1])
          setLive(l)
          setError(null)
          if (l.status.busy) wait = 250
        } catch (e) {
          if (stopped) return
          setError(e)
          wait = e instanceof ApiError && e.status === 429 ? Math.max(e.retryAfterMs ?? 5000, 1000) : 3000
        }
      }
      if (!stopped) timer = window.setTimeout(() => void tick(), wait)
    }
    void tick()
    return () => { stopped = true; window.clearTimeout(timer) }
  }, [robotId])
  return { live, frame, error }
}

/**
 * Robot control through the backend (FE_API_GUIDE 7f, 7g): the app sends commands, the Robot Agent on the workstation pulls
 * and runs them on the real arm (mode REAL). Order of a job: LOAD → PREFLIGHT → record the simulation → DRY_RUN (pen up) →
 * start writing → RUN, then PAUSE / RESUME / STOP. Software STOP never replaces the physical E-Stop.
 */
interface Props {
  job: TechJobDetail
  refresh: Job
  run: TechRun
  /** The job package was downloaded and its hash checked in this browser. */
  verified: boolean
  disabled: boolean
}

export default function RobotConsole({ job, refresh, run, verified, disabled }: Props) {
  const t = useT()
  const locale = useLocale()
  const { live, frame, error: liveError } = useLive(job.robotId)
  const status = useRobotStatus()
  const history = useAsync(() => jobCommands(job.id), [job.id])
  const row = status.data?.find((r) => r.robotId === job.robotId) ?? null
  const [auth, setAuth] = useState('')
  const [resumeFrom, setResumeFrom] = useState('')
  const [confirmUnknown, setConfirmUnknown] = useState(false)
  const [pending, setPending] = useState<RobotCommand | null>(null)
  const [controlBusy, setControlBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const abort = useRef<AbortController | null>(null)

  useEffect(() => () => abort.current?.abort(), [])

  // The workstation lists the modes it allows; without REAL nothing can run from here.
  const realEnabled = !live?.status.enabled_modes || live.status.enabled_modes.map((m) => m.toUpperCase()).includes(MODE)
  const online = !!live?.online
  const busy = !!live?.status.busy
  const agentState = frame?.state ?? live?.status.state ?? ''
  const commands = history.data ?? []
  const latest = (kind: CommandKind) => commands.find((c) => c.kind === kind && c.jobId === job.id) ?? null
  const load = latest('LOAD')
  const loaded = load?.status === 'DONE' ? load : null
  const preflight = latest('PREFLIGHT')
  const loadResult = (loaded?.result ?? {}) as {
    order_code?: string; pages?: number; strokes?: number; estimated_seconds?: number | null; plan_digest?: string
    authorization_token?: string
    validation?: { passed?: boolean; errors?: { code: string; message: string }[]; warnings?: unknown[]; checks?: Record<string, string> }
  }
  const pre = (preflight?.status === 'DONE' ? preflight.result : null) as { ok?: boolean; moves?: number; code?: string; message?: string; mode?: string; note?: string } | null
  const authValid = /^AUTHORIZE-\S+$/.test(auth.trim())
  const locked = disabled || !!pending || !online || !realEnabled
  const level = Math.max(row?.level ?? 1, frame?.level ?? 1)

  const finish = async () => {
    await Promise.all([history.reload(), refresh()])
  }

  /** A command that takes time (load, check, run). One at a time; it is followed until the agent answers. */
  const exec = async (kind: CommandKind, params: Record<string, unknown> = {}, confirmation?: string) => {
    if (pending || disabled) return
    if (confirmation && !window.confirm(confirmation)) return
    setError(''); setNotice('')
    const ctl = new AbortController()
    abort.current = ctl
    try {
      const cmd = await sendCommand({ kind, job_id: job.id, params })
      setPending(cmd)
      const done = await waitCommand(cmd, setPending, ctl.signal)
      if (ctl.signal.aborted) return
      if (done.status === 'DONE') setNotice(t('rb.done', { kind: t(`rb.kind.${kind}`) }))
      else setError(commandError(done, t))
    } catch (e) {
      if (!ctl.signal.aborted) setError(flowError(e, t))
    } finally {
      if (!ctl.signal.aborted) {
        setPending(null)
        await finish()
      }
    }
  }

  /** PAUSE / RESUME / STOP / PAPER_CHANGED: never wait behind a running command. */
  const control = async (kind: CommandKind, confirmation?: string) => {
    if (controlBusy) return
    if (confirmation && !window.confirm(confirmation)) return
    setControlBusy(true); setError('')
    const ctl = new AbortController()
    try {
      const cmd = await sendCommand({ kind, job_id: job.id })
      const done = await waitCommand(cmd, () => undefined, ctl.signal)
      if (done.status !== 'DONE') setError(commandError(done, t))
    } catch (e) {
      setError(flowError(e, t))
    } finally {
      setControlBusy(false)
      await finish()
    }
  }

  const modeParams = (extra: Record<string, unknown> = {}) => ({ mode: MODE, authorization: auth.trim(), ...extra })

  /** The simulation result the backend gates "start" on, taken from the agent's own check (LOAD validation + PREFLIGHT). */
  const recordSimulation = () => run(async () => {
    if (!pre || !preflight || !loaded) return
    const validation = loadResult.validation
    const errors = [
      ...(validation?.errors ?? []).map((e) => `${e.code}: ${e.message}`),
      ...(pre.ok ? [] : [`${pre.code ?? 'PREFLIGHT_REFUSED'}: ${pre.message ?? ''}`]),
    ].map((s) => s.slice(0, 500)).slice(0, 100)
    const passed = pre.ok === true && validation?.passed !== false && errors.length === 0
    const saved = await simulateJob(job.id, {
      passed, errors,
      report: {
        source: 'robot_agent', mode: pre.mode?.toUpperCase() ?? preflight.params.mode, load_command_id: loaded.id,
        preflight_command_id: preflight.id, plan_digest: loadResult.plan_digest, moves: pre.moves,
        checks: validation?.checks, warnings: validation?.warnings?.length ?? 0, calibration_id: job.calibration?.id,
      },
    })
    // The server rebuilds the plan and may turn a claimed pass into a fail.
    if (passed && saved.simulationPassed === false) throw new Error('td.flow.simServerRejected')
  })

  /** Backend and agent codes we have words for; anything new is shown as it came. */
  const label = (key: string, raw: string) => (t(key) === key ? raw : t(key))

  const canLoad = LOADABLE.includes(job.status) && !!job.calibration?.is_valid
  const simRecorded = job.simulationPassed === true
  const writing = ['WRITING', 'PAUSED'].includes(job.status)
  const paused = agentState === 'PAUSED'
  const pct = Math.round(Math.max(0, Math.min(100, frame?.progress_pct ?? job.progress ?? 0)))
  const when = (iso: string) => new Date(iso).toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit', second: '2-digit' })

  /** One preparation step: number, name, its result chip and its button. The help text is the button's tooltip. */
  const step = (n: number, title: string, ok: boolean | null, button: ReactNode, result?: ReactNode) => (
    <li className={`rb-step${ok === true ? ' ok' : ok === false ? ' bad' : ''}`}>
      <div className="rb-step-h"><span className="rb-num">{n}</span><b>{title}</b>
        {ok !== null && <span className={`chip ${ok ? 'good' : 'warn'}`}>{t(ok ? 'rb.stepDone' : 'rb.stepTodo')}</span>}</div>
      {button}
      {result}
    </li>
  )

  return <section className="panel rb" aria-labelledby="rb-h">
    <div className="rb-top">
      <h2 id="rb-h">{t('rb.title')}</h2>
      <div className="rb-badges">
        <span className={`chip ${online ? 'good' : 'bad'}`}>{t(online ? 'rb.online' : 'rb.offline')}</span>
        <span className="chip info">{label(`rb.mode.${MODE}`, MODE)}</span>
        {row && <span className={`chip ${row.level >= 4 ? 'bad' : row.level === 3 ? 'orange' : row.level === 2 ? 'warn' : 'mute'}`}>{t(`rb.state.${row.state}`)}</span>}
        {busy && <span className="chip orange">{t('rb.busy')}</span>}
      </div>
    </div>

    {level >= 4 && <div className="rb-estop" role="alert"><b>{t('rb.estopNow')}</b>
      {(row?.alerts ?? []).filter((a) => a.level >= 4).map((a) => <span key={a.id}>{a.title} {a.action}</span>)}</div>}
    {live && !realEnabled && <p className="lg-error" role="alert">{t('rb.realDisabled')}</p>}
    {!!liveError && !live && <p className="lg-error" role="alert">{flowError(liveError, t)}</p>}
    {error && <p className="lg-error tech-error" role="alert">{error}</p>}
    {(pending || notice) && <p className="sub" role="status">{pending ? t('rb.waiting', { kind: t(`rb.kind.${pending.kind}`), status: t(`rb.cmd.${pending.status}`) }) : notice}</p>}

    <div className="rb-main">
      <aside className="rb-side" aria-label={t('rb.controls')}>
        <div className="rb-prog">
          <div className="rb-prog-h"><b className="mono">{pct}%</b><span className="sub">{t('rb.stroke')} {frame ? `${frame.stroke} / ${frame.total_strokes}` : '–'}</span></div>
          <div className="bar" role="progressbar" aria-label={t('rb.progress')} aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${pct}%` }} /></div>
        </div>

        <dl className="rb-tele">
          <div><dt>{t('rb.agentState')}</dt><dd>{agentState ? label(`rb.agent.${agentState}`, agentState) : '–'}</dd></div>
          <div><dt>{t('rb.force')}</dt><dd>{frame?.force_n != null ? `${frame.force_n.toFixed(2)} N` : '–'}{frame?.touching ? ` / ${t('rb.touching')}` : ''}</dd></div>
          <div><dt>{t('rb.tcp')}</dt><dd className="mono">{frame?.tcp ? frame.tcp.slice(0, 3).map((v) => v.toFixed(1)).join(', ') : '–'}</dd></div>
          <div><dt>{t('rb.lastSeen')}</dt><dd>{live?.ageS != null ? t('rb.secondsAgo', { n: Math.round(live.ageS) }) : '–'}</dd></div>
        </dl>
        {frame?.joints_deg && <p className="sub mono rb-joints">{frame.joints_deg.map((d, i) => `J${i + 1} ${Number(d).toFixed(1)}°`).join('  ')}</p>}

        <label className="vh-label rb-auth">{t('rb.authLabel')}
          <input className="vh-input mono" value={auth} autoComplete="off" spellCheck={false} placeholder={loadResult.authorization_token ?? t('rb.authPlaceholder')} onChange={(e) => setAuth(e.target.value)} /></label>

        <div className="rb-run" role="group" aria-label={t('rb.controls')}>
          <button type="button" className="rb-big rb-go" title={t(writing ? 'rb.help.RUN' : 'rb.help.runBlocked')}
            disabled={locked || busy || !loaded || !writing || !authValid}
            onClick={() => void exec('RUN', modeParams({
              ...(resumeFrom.trim() !== '' && Number.isInteger(Number(resumeFrom)) ? { resume_from: Number(resumeFrom) } : {}),
              ...(confirmUnknown ? { confirm_unknown: true } : {}),
            }), t('rb.confirmReal'))}><Play size={20} weight="fill" aria-hidden />{t('rb.kind.RUN')}</button>
          {paused
            ? <button type="button" className="rb-big" disabled={!online || controlBusy || !busy} onClick={() => void control('RESUME')}><Play size={20} aria-hidden />{t('rb.do.RESUME')}</button>
            : <button type="button" className="rb-big" disabled={!online || controlBusy || !busy} onClick={() => void control('PAUSE')}><Pause size={20} weight="fill" aria-hidden />{t('rb.do.PAUSE')}</button>}
          <button type="button" className="rb-big rb-stop" title={t('rb.estopNote')} disabled={!online || controlBusy || !busy} onClick={() => void control('STOP', t('rb.confirmStop'))}><Stop size={20} weight="fill" aria-hidden />{t('rb.do.STOP')}</button>
          {agentState === 'AWAITING_PAPER' && <button type="button" className="rb-big rb-wide" disabled={!online || controlBusy} onClick={() => void control('PAPER_CHANGED')}>{t('rb.do.PAPER_CHANGED')}</button>}
        </div>

        <details className="rb-adv"><summary>{t('td.flow.advanced')}</summary>
          <label className="vh-label">{t('rb.resumeFrom')}<input className="vh-input" type="number" min={0} value={resumeFrom} onChange={(e) => setResumeFrom(e.target.value)} /></label>
          <label className="wk-check"><input type="checkbox" checked={confirmUnknown} onChange={(e) => setConfirmUnknown(e.target.checked)} />{t('rb.confirmUnknown')}</label>
          <button type="button" className="sd-btn" title={t('rb.help.ALIGN_START')} disabled={locked || busy || !loaded || !authValid}
            onClick={() => void exec('ALIGN_START', modeParams(), t('rb.confirmReal'))}>{t('rb.do.ALIGN_START')}</button>
        </details>

        {live?.status.last && !busy && <div className="rb-last">
          <b>{t('rb.lastRun')}</b>
          {live.status.last.refused && <span className="lg-error">{live.status.last.refused.code}: {live.status.last.refused.message}</span>}
          {live.status.last.error && <span className="lg-error">{live.status.last.error}</span>}
          {live.status.last.result && <pre className="tech-json">{JSON.stringify(live.status.last.result, null, 2)}</pre>}
        </div>}
      </aside>

    <ol className="rb-steps" aria-label={t('rb.prepare')}>
      {step(1, t('rb.kind.LOAD'), loaded ? true : load && load.status !== 'DONE' ? false : null,
        <button type="button" className="sd-btn" title={t(canLoad ? 'rb.help.LOAD' : 'rb.help.loadBlocked')} disabled={locked || busy || !canLoad} onClick={() => void exec('LOAD')}>{t('rb.do.LOAD')}</button>,
        loaded
          ? <p className="rb-res">{t('rb.loadSummary', { pages: loadResult.pages ?? '–', strokes: loadResult.strokes ?? '–' })}{loadResult.estimated_seconds != null ? ` / ${t('rb.seconds', { n: Math.round(loadResult.estimated_seconds) })}` : ''}
            {loadResult.validation?.passed === false && <span className="lg-error"> {loadResult.validation.errors?.map((e) => e.code).join(', ')}</span>}</p>
          : load && <p className="rb-res lg-error">{commandError(load, t)}</p>)}

      {step(2, t('rb.kind.PREFLIGHT'), pre ? pre.ok === true : preflight && preflight.status !== 'DONE' ? false : null,
        <button type="button" className="sd-btn" title={t('rb.help.PREFLIGHT')} disabled={locked || busy || !loaded} onClick={() => void exec('PREFLIGHT', { mode: MODE })}>{t('rb.do.PREFLIGHT', { mode: MODE })}</button>,
        pre ? (pre.ok ? <p className="rb-res">{t('rb.preflightOk', { n: pre.moves ?? 0, mode: MODE })}</p> : <p className="rb-res lg-error">{pre.code}: {pre.message}</p>)
          : preflight && <p className="rb-res lg-error">{commandError(preflight, t)}</p>)}

      {step(3, t('rb.recordSim'), job.simulationPassed === null ? null : simRecorded,
        <button type="button" className="sd-btn" title={t('rb.help.record')} disabled={disabled || !!pending || job.status !== 'PREPARING' || !pre || !loaded} onClick={() => void recordSimulation()}>{t('rb.do.record')}</button>)}

      {step(4, t('rb.kind.DRY_RUN'), null,
        <button type="button" className="sd-btn" title={t('rb.help.DRY_RUN')} disabled={locked || busy || !loaded || !['PREPARING', 'PAUSED'].includes(job.status) || !authValid}
          onClick={() => void exec('DRY_RUN', modeParams(), t('rb.confirmReal'))}>{t('rb.do.DRY_RUN', { mode: MODE })}</button>)}

      {step(5, t('td.flow.start'), job.status === 'PREPARING' ? null : writing,
        <button type="button" className="sd-btn" disabled={disabled || !!pending || job.status !== 'PREPARING' || !verified || !job.canStart}
          onClick={() => void run(() => startJob(job.id), t('td.flow.confirmStart'))}>{t('td.flow.start')}</button>,
        <p className="rb-res rb-gates">{([['td.flow.verified', verified], ['td.api.calibration', !!job.calibration?.is_valid], ['td.api.simulation', simRecorded]] as const).map(([key, ok]) =>
          <span key={key} className={ok ? 'ok' : undefined}>{t(key)}</span>)}</p>)}
    </ol>
    </div>

    <details className="rb-history"><summary>{t('rb.history', { n: commands.length })}</summary>
      <ul className="rb-log">{commands.map((c) => <li key={c.id}>
        <time className="mono" dateTime={c.createdAt}>{when(c.createdAt)}</time>
        <b>{t(`rb.kind.${c.kind}`)}</b>
        <span className={`chip ${c.status === 'DONE' ? 'good' : c.status === 'FAILED' || c.status === 'EXPIRED' ? 'bad' : 'mute'}`}>{t(`rb.cmd.${c.status}`)}</span>
        {c.status !== 'DONE' && (c.errorCode || c.errorMessage) && <span className="sub">{commandError(c, t)}</span>}
      </li>)}</ul>
    </details>
  </section>
}
