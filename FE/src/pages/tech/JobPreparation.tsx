import { useState } from 'react'
import { useT } from '../../i18n'
import { CALIBRATION_CHECKS, calibrateJob, jobPermissions, simulateJob, type ProbePoint, type TechJobDetail } from '../../services/technician'
import { optionalJson, probePlaneValid, type TechRun } from './flow'

type PointInput = { x: string; y: string; z: string }
export default function JobPreparation({ job, disabled, gates, run }: {
  job: TechJobDetail; disabled: boolean; gates: ReturnType<typeof jobPermissions>; run: TechRun
}) {
  const t = useT()
  const [checks, setChecks] = useState<Record<string, boolean>>({})
  const [zero, setZero] = useState('')
  const [points, setPoints] = useState<PointInput[]>(Array.from({ length: 3 }, () => ({ x: '', y: '', z: '' })))
  const [frame, setFrame] = useState('')
  const [height, setHeight] = useState('')
  const [force, setForce] = useState('')
  const [result, setResult] = useState('')
  const [errors, setErrors] = useState('')
  const [report, setReport] = useState('')
  const probes: ProbePoint[] = points.map((p) => ({ x: Number(p.x), y: Number(p.y), z: Number(p.z) }))
  const pointsFilled = points.every((p) => [p.x, p.y, p.z].every((v) => v.trim() !== ''))
  const calibrated = CALIBRATION_CHECKS.every((k) => checks[k]) && zero.trim() !== '' && Number.isFinite(Number(zero))
    && Math.abs(Number(zero)) <= 1000
    && pointsFilled && probePlaneValid(probes)
  const errorLines = errors.split('\n').map((v) => v.trim()).filter(Boolean)
  const consistent = result !== '' && errorLines.length <= 100 && errorLines.every((v) =>
    v.length <= 500) && (result !== 'pass' || !errorLines.length)
  return <div className="flex">
    <section className="panel tech-detail-panel">
      <h2>{t('td.api.calibration')}</h2>
      <p className="sub">{t('td.flow.calibrationHelp')}</p>
      {job.calibration && <details><summary>{t('td.flow.currentCalibration')}</summary><pre className="tech-json">{JSON.stringify(job.calibration, null, 2)}</pre></details>}
      <form className="tech-form" onSubmit={(e) => { e.preventDefault(); if (calibrated && gates.calibrate) void run(async () => {
        await calibrateJob(job.id, {
          checklist: checks, force_zero_offset: Number(zero), probe_points: probes,
          frame_transform: optionalJson(frame) as Record<string, unknown> | undefined,
          height_map: optionalJson(height, true), force_curve: optionalJson(force, true),
        })
        setResult(''); setErrors(''); setReport('')
      }, job.simulationPassed !== null ? t('td.flow.confirmRecalibrate') : undefined) }}>
        <fieldset disabled={disabled || !gates.calibrate}>
          <legend>{t('td.flow.checklist')}</legend>
          {CALIBRATION_CHECKS.map((k) => <label className="wk-check" key={k}><input type="checkbox" checked={!!checks[k]} onChange={(e) => setChecks({ ...checks, [k]: e.target.checked })} />{t(`td.flow.check.${k}`)}</label>)}
          <label className="vh-label">{t('td.flow.forceZero')}<input className="vh-input" type="number" step="any" min={-1000} max={1000} required value={zero} onChange={(e) => setZero(e.target.value)} /></label>
          <p className="sub">{t('td.flow.probeHelp')}</p>
          <div className="tech-probe-grid">{points.map((p, i) => <div className="tech-probe-row" key={i}>
            <b>{`P${i}`}</b>{(['x', 'y', 'z'] as const).map((axis) => <label className="vh-label" key={axis}>{axis.toUpperCase()}
              <input className="vh-input" type="number" step="any" required aria-label={t('td.flow.probeCoordinate', { n: i, axis: axis.toUpperCase() })} value={p[axis]} onChange={(e) => setPoints(points.map((point, index) => index === i ? { ...point, [axis]: e.target.value } : point))} />
            </label>)}
            {i >= 3 && <button type="button" className="sd-btn" onClick={() => setPoints(points.filter((_, index) => index !== i))}>{t('td.flow.remove')}</button>}
          </div>)}</div>
          {pointsFilled && !probePlaneValid(probes) && <p className="lg-error" role="alert">{t('td.flow.error.INVALID_PROBE_POINTS')}</p>}
          <button type="button" className="sd-btn" disabled={points.length >= 400} onClick={() => setPoints([...points, { x: '', y: '', z: '' }])}>{t('td.flow.addProbe')}</button>
          <details><summary>{t('td.flow.advanced')}</summary>
            <label className="vh-label">{t('td.flow.frame')}<textarea className="vh-textarea" value={frame} onChange={(e) => setFrame(e.target.value)} /></label>
            <label className="vh-label">{t('td.flow.heightMap')}<textarea className="vh-textarea" value={height} onChange={(e) => setHeight(e.target.value)} /></label>
            <label className="vh-label">{t('td.flow.forceCurve')}<textarea className="vh-textarea" value={force} onChange={(e) => setForce(e.target.value)} /></label>
          </details>
          <button type="submit" className="sd-btn" disabled={!calibrated}>{t('td.flow.saveCalibration')}</button>
        </fieldset>
      </form>
    </section>
    <section className="panel tech-detail-panel">
      <h2>{t('td.api.simulation')}</h2><p className="wk-warn">{t('td.flow.simulationHelp')}</p>
      <form className="tech-form" onSubmit={(e) => { e.preventDefault(); if (consistent && gates.simulate) void run(() => simulateJob(job.id, {
        passed: result === 'pass', errors: errorLines, report: { ...optionalJson(report), source: 'web_manual', calibration_id: job.calibration?.id },
      })) }}>
        <fieldset disabled={disabled || !gates.simulate}>
          <legend>{t('td.flow.report')}</legend>
          <label className="vh-label">{t('td.flow.result')}<select className="vh-select" required value={result} onChange={(e) => setResult(e.target.value)}><option value="">{t('td.flow.choose')}</option><option value="pass">{t('td.api.passed')}</option><option value="fail">{t('td.api.notPassed')}</option></select></label>
          <label className="vh-label">{t('td.flow.simulationErrors')}<textarea className="vh-textarea" rows={4} value={errors} onChange={(e) => setErrors(e.target.value)} /></label>
          {result === 'pass' && errorLines.length > 0 && <p className="lg-error">{t('td.flow.inconsistent')}</p>}
          <label className="vh-label">{t('td.flow.reportJson')}<textarea className="vh-textarea" rows={3} value={report} onChange={(e) => setReport(e.target.value)} /></label>
          <button type="submit" className="sd-btn" disabled={!consistent}>{t('td.flow.saveSimulation')}</button>
        </fieldset>
      </form>
    </section>
  </div>
}
