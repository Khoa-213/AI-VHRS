import { useState } from 'react'
import { useT } from '../../i18n'
import { jobPermissions, simulateJob, type TechJobDetail } from '../../services/technician'
import { optionalJson, type TechRun } from './flow'

/**
 * Simulation result of a job being prepared. Calibration is sent from the workstation (`robot_console.py calibrate`), and the
 * simulation is normally recorded from the agent's check in Robot control; this form is the manual fallback.
 */
export default function JobPreparation({ job, disabled, gates, run }: {
  job: TechJobDetail; disabled: boolean; gates: ReturnType<typeof jobPermissions>; run: TechRun
}) {
  const t = useT()
  const [result, setResult] = useState('')
  const [errors, setErrors] = useState('')
  const [report, setReport] = useState('')
  const errorLines = errors.split('\n').map((v) => v.trim()).filter(Boolean)
  const consistent = result !== '' && errorLines.length <= 100 && errorLines.every((v) =>
    v.length <= 500) && (result !== 'pass' || !errorLines.length)
  return <section className="panel">
    <h2>{t('td.api.simulation')}</h2><p className="sub">{t('td.flow.simulationHelp')}</p>
    <details><summary>{t('td.flow.manualSimulation')}</summary>
      <p className="wk-warn">{t('td.flow.manualSimulationHelp')}</p>
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
    </details>
  </section>
}
