import { useState } from 'react'
import { useT } from '../../i18n'
import { CLIENT_EVENTS, INCIDENT_TYPES, eventAllowed, jobPermissions, postJobEvent, reportIncident, type ClientEvent, type IncidentInput, type TechJobDetail } from '../../services/technician'
import { optionalJson, type TechRun } from './flow'

const FORCE_KEYS = ['f_mean', 'f_max', 'rms_err_pct', 'in_band_pct', 'samples'] as const
export default function JobEvents({ job, disabled, run }: { job: TechJobDetail; disabled: boolean; run: TechRun }) {
  const t = useT()
  const [event, setEvent] = useState<ClientEvent>('PROGRESS')
  const [progress, setProgress] = useState('')
  const [stroke, setStroke] = useState('')
  const [note, setNote] = useState('')
  const [payload, setPayload] = useState('')
  const [force, setForce] = useState<Record<string, string>>({})
  const [incident, setIncident] = useState<IncidentInput['type']>('OTHER')
  const [description, setDescription] = useState('')
  const [robotStatus, setRobotStatus] = useState('')
  const allowed = CLIENT_EVENTS.filter((v) => eventAllowed(job.status, v))
  const selected = allowed.includes(event) ? event : allowed[0]
  const forceValues = Object.fromEntries(FORCE_KEYS.filter((k) => force[k]?.trim()).map((k) => [k, Number(force[k])]))
  const validForce = Object.keys(forceValues).length > 0 && Object.values(forceValues).every(Number.isFinite)
    && (forceValues.in_band_pct === undefined || (forceValues.in_band_pct >= 0
      && forceValues.in_band_pct <= 100))
  const valid = selected && (selected !== 'PROGRESS' || (progress.trim() !== '' && Number.isFinite(Number(progress)) && Number(progress) >= (job.progress ?? 0)
    && Number(progress) <= 100))
    && (selected !== 'FORCE_SUMMARY' || validForce)
    && (stroke === '' || (Number.isInteger(Number(stroke)) && Number(stroke) >= 0
      && Number(stroke) <= 10000000))
  const canIncident = jobPermissions(job).incident
  if (!allowed.length && !canIncident) return null
  return <div className="flex">
    {allowed.length > 0 && <section className="panel tech-detail-panel">
      <h2>{t('td.flow.events')}</h2><p className="sub">{t('td.flow.eventHelp')}</p>
      <form className="tech-form" onSubmit={(e) => { e.preventDefault(); if (valid) void run(() => postJobEvent(job.id, {
        event_type: selected, ...(selected === 'PROGRESS' ? { progress_pct: Number(progress) } : {}),
        ...(stroke !== '' ? { stroke_index: Number(stroke) } : {}),
        ...(selected === 'FORCE_SUMMARY' ? { force_summary: forceValues } : {}),
        payload: { ...optionalJson(payload), source: 'web_manual', ...(note.trim() ? { note: note.trim() } : {}) },
      }), ['ESTOP', 'OVER_FORCE', 'STROKE_LOST', 'SENSOR_LOST'].includes(selected) ? t('td.flow.confirmSafety') : undefined) }}>
        <fieldset disabled={disabled}>
          <legend>{t('td.flow.events')}</legend>
          <label className="vh-label">{t('td.flow.eventType')}<select className="vh-select" value={selected} onChange={(e) => setEvent(e.target.value as ClientEvent)}>{allowed.map((v) => <option key={v} value={v}>{t(`td.flow.event.${v}`)}</option>)}</select></label>
          {selected === 'PROGRESS' && <label className="vh-label">{t('td.flow.progressPct')}<input className="vh-input" type="number" step="any" min={job.progress ?? 0} max={100} required value={progress} onChange={(e) => setProgress(e.target.value)} /></label>}
          <label className="vh-label">{t('td.flow.strokeIndex')}<input className="vh-input" type="number" min={0} max={10000000} value={stroke} onChange={(e) => setStroke(e.target.value)} /></label>
          {selected === 'FORCE_SUMMARY' && <div className="tech-fields">{FORCE_KEYS.map((k) => <label className="vh-label" key={k}>{t(`td.flow.force.${k}`)}<input className="vh-input" type="number" step="any" min={k === 'in_band_pct' ? 0 : undefined} max={k === 'in_band_pct' ? 100 : undefined} value={force[k] ?? ''} onChange={(e) => setForce({ ...force, [k]: e.target.value })} /></label>)}</div>}
          <label className="vh-label">{t('td.flow.note')}<textarea className="vh-textarea" maxLength={1000} value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <details><summary>{t('td.flow.advanced')}</summary><label className="vh-label">{t('td.flow.payload')}<textarea className="vh-textarea" value={payload} onChange={(e) => setPayload(e.target.value)} /></label></details>
          <button type="submit" className="sd-btn" disabled={!valid}>{t('td.flow.sendEvent')}</button>
        </fieldset>
      </form>
    </section>}
    {canIncident && <section className="panel tech-detail-panel">
      <h2>{t('td.flow.incident')}</h2><p className="sub">{t('td.flow.incidentHelp')}</p>
      <form className="tech-form" onSubmit={(e) => { e.preventDefault(); if (description.trim()) void run(() => reportIncident(job.id, {
        type: incident, description: description.trim(), ...(robotStatus ? { robot_status_after: robotStatus as 'MAINTENANCE' | 'BROKEN' } : {}),
      }), t('td.flow.confirmIncident')) }}>
        <fieldset disabled={disabled}>
          <legend>{t('td.flow.incident')}</legend>
          <label className="vh-label">{t('td.flow.incidentType')}<select className="vh-select" value={incident} onChange={(e) => setIncident(e.target.value as IncidentInput['type'])}>{INCIDENT_TYPES.map((v) => <option key={v} value={v}>{t(`td.flow.incident.${v}`)}</option>)}</select></label>
          <label className="vh-label">{t('td.flow.description')}<textarea className="vh-textarea" required maxLength={1000} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
          <label className="vh-label">{t('td.flow.robotAfter')}<select className="vh-select" value={robotStatus} onChange={(e) => setRobotStatus(e.target.value)}>
            <option value="">{t('td.flow.unchanged')}</option><option value="MAINTENANCE">{t('td.flow.maintenance')}</option><option value="BROKEN">{t('td.flow.broken')}</option>
          </select></label>
          <button type="submit" className="sd-btn" disabled={!description.trim()}>{t('td.flow.reportIncident')}</button>
        </fieldset>
      </form>
    </section>}
  </div>
}
