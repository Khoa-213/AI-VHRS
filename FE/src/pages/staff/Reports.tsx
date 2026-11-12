import { ArrowCounterClockwise, ChartLineUp, DownloadSimple, FilePdf, Prohibit, Timer } from '@phosphor-icons/react'
import { useState } from 'react'
import { Kpi } from '../../components/ws/parts'
import Shell from '../../components/ws/Shell'
import { useAsync } from '../../hooks/useAsync'
import { useLocale, useT } from '../../i18n'
import { Link } from '../../router/router'
import { REPORT_GROUPS, exportReport, managerReport, type ReportGroup } from '../../services/managerOps'
import { errText, orderErrorKey } from '../../services/orders'
import { fmt } from '../../utils/format'
import { dayOf, daysAgo, pct } from '../../utils/managerDates'
import { LineChart, Panel, Period } from './managerKit'

/**
 * Manager reports (UC-46, FR-50) in the Staff frame: cash revenue net of refunds, output by order type, reject and rewrite
 * rates, robot time and incidents, orders completed after their ETA. Everything comes from `GET /manager/reports`; the export
 * buttons download the same report from `GET /manager/reports/export` as Excel or PDF with the Bearer header.
 */
export default function Reports() {
  const t = useT()
  const locale = useLocale()
  const [from, setFrom] = useState(() => daysAgo(29))
  const [to, setTo] = useState(() => daysAgo(0))
  const [group, setGroup] = useState<ReportGroup>('day')
  const [exporting, setExporting] = useState<'xlsx' | 'pdf' | null>(null)
  const [exportErr, setExportErr] = useState('')
  const query = { from: from || undefined, to: to || undefined, group }
  const rep = useAsync(() => managerReport(query), [from, to, group])
  const r = rep.data

  const download = async (format: 'xlsx' | 'pdf') => {
    if (exporting) return
    setExporting(format); setExportErr('')
    try {
      await exportReport(query, format)
    } catch (e) {
      setExportErr(orderErrorKey(e))
    } finally {
      setExporting(null)
    }
  }

  const day = (iso: string) => dayOf(iso).toLocaleDateString(locale, { day: 'numeric', month: 'short', year: 'numeric' })
  const bucket = (iso: string, long = false) => {
    const d = dayOf(iso)
    if (group === 'month') return d.toLocaleDateString(locale, { month: long ? 'long' : 'short', year: 'numeric' })
    if (group === 'week') return t('mgr.rp.weekOf', { date: d.toLocaleDateString(locale, { day: 'numeric', month: 'short' }) })
    return long ? d.toLocaleDateString(locale) : d.toLocaleDateString(locale, { day: 'numeric', month: 'numeric' })
  }
  const reset = () => { setFrom(daysAgo(29)); setTo(daysAgo(0)); setGroup('day') }
  const series = r?.revenue.series ?? []
  const icon = (I: typeof ChartLineUp) => <I size={20} aria-hidden />

  return (
    <Shell
      area="manager"
      active="reports"
      title={t('mgr.nav.reports')}
      tools={(
        <>
          <button type="button" className="btn ghost" disabled={!!exporting || !r} onClick={() => void download('pdf')}>
            <FilePdf size={18} aria-hidden />{t(exporting === 'pdf' ? 'mgr.rp.exporting' : 'mgr.rp.pdf')}
          </button>
          <button type="button" className="staff-primary-link" disabled={!!exporting || !r} onClick={() => void download('xlsx')}>
            {t(exporting === 'xlsx' ? 'mgr.rp.exporting' : 'mgr.rp.xlsx')}<DownloadSimple size={17} aria-hidden />
          </button>
        </>
      )}
    >
      {exportErr && <p className="lg-error" role="alert">{t('mgr.rp.exportFailed', { reason: errText(t, exportErr) })}</p>}

      <Panel
        title={t('mgr.rp.filters')}
        sub={t('mgr.rp.scope')}
        aside={<button type="button" className="vh-link" onClick={reset}><ArrowCounterClockwise size={14} aria-hidden style={{ verticalAlign: '-2px' }} /> {t('mgr.rp.reset')}</button>}
      >
        <div className="mgr-filters">
          <label className="vh-label">
            {t('mgr.rp.from')}
            <input className="vh-input" type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
          </label>
          <label className="vh-label">
            {t('mgr.rp.to')}
            <input className="vh-input" type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
          </label>
          <div className="mgr-field-group">
            <span>{t('mgr.rp.group')}</span>
            <Period options={REPORT_GROUPS} value={group} onChange={setGroup} label={t('mgr.rp.group')} text={(g) => t(`mgr.rp.group.${g}`)} />
          </div>
        </div>
      </Panel>

      {!!rep.error && <p className="lg-error" role="alert">{errText(t, orderErrorKey(rep.error))}</p>}
      {rep.loading && !r && <p className="sub" role="status">{t('co.loading')}</p>}

      {r && (
        <>
          <p className="sub" role="status">{t('mgr.rp.showing', { from: day(r.from), to: day(r.to) })}{rep.loading ? ` · ${t('co.loading')}` : ''}</p>
          <div className="row4 staff-kpis">
            <Kpi icon={icon(ChartLineUp)} title={t('mgr.rp.net')} value={fmt(r.revenue.net)}
              note={t('mgr.rp.netHint', { received: fmt(r.revenue.received), refunded: fmt(r.revenue.refunded) })} />
            <Kpi icon={icon(Prohibit)} title={t('mgr.rp.rejectRate')} value={pct(r.rates.rejectRate, locale) ?? t('mgr.rp.na')}
              note={t('mgr.rp.rejectHint', { n: r.rates.rejected, of: r.rates.submitted })} />
            <Kpi icon={icon(ArrowCounterClockwise)} title={t('mgr.rp.rewriteRate')} value={pct(r.rates.rewriteRate, locale) ?? t('mgr.rp.na')}
              note={t('mgr.rp.rewriteHint', { n: r.rates.rewrites, of: r.rates.jobsWritten })} />
            <Kpi icon={icon(Timer)} title={t('mgr.rp.lateRate')} value={pct(r.late.lateRate, locale) ?? t('mgr.rp.na')}
              note={t('mgr.rp.lateHint', { n: r.late.count, of: r.late.ofCompleted })} />
          </div>

          <Panel title={t('mgr.rp.revenue')} sub={t('mgr.rp.revenueSub')} className="staff-performance">
            <div className="staff-chart-total"><b>{fmt(r.revenue.net)}</b><span>{t('mgr.rp.net')}</span></div>
            {series.length ? (
              <>
                <LineChart
                  key={group}
                  locale={locale}
                  caption={t('mgr.rp.revenueCaption')}
                  column={t('mgr.rp.net')}
                  points={series.map((x) => ({ label: bucket(x.bucket), long: bucket(x.bucket, true), value: x.net, readout: fmt(x.net) }))}
                />
                <div className="mgr-table-wrap">
                  <table className="mgr-table">
                    <caption className="staff-sr">{t('mgr.rp.revenue')}</caption>
                    <thead>
                      <tr>
                        <th scope="col">{t('mgr.rp.period')}</th>
                        <th scope="col" className="num">{t('mgr.rp.received')}</th>
                        <th scope="col" className="num">{t('mgr.rp.refunded')}</th>
                        <th scope="col" className="num">{t('mgr.rp.net')}</th>
                        <th scope="col" className="num">{t('mgr.rp.payments')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {series.map((x) => (
                        <tr key={x.bucket}>
                          <th scope="row">{bucket(x.bucket, true)}</th>
                          <td className="num">{fmt(x.received)}</td>
                          <td className="num">{fmt(x.refunded)}</td>
                          <td className="num">{fmt(x.net)}</td>
                          <td className="num">{x.payments}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            ) : <p className="sub">{t('mgr.rp.noPayments')}</p>}
          </Panel>

          <div className="mgr-grid2">
            <Panel title={t('mgr.rp.output')} sub={t('mgr.rp.outputSub')}>
              {r.outputByType.length ? (
                <div className="mgr-table-wrap">
                  <table className="mgr-table">
                    <thead>
                      <tr>
                        <th scope="col">{t('mgr.rp.type')}</th>
                        <th scope="col" className="num">{t('mgr.rp.orders')}</th>
                        <th scope="col" className="num">{t('mgr.rp.copies')}</th>
                        <th scope="col" className="num">{t('mgr.rp.value')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.outputByType.map((x) => (
                        <tr key={x.orderType}>
                          <th scope="row">{t(`ot.${x.orderType}`)}</th>
                          <td className="num">{x.orders}</td>
                          <td className="num">{x.quantity}</td>
                          <td className="num">{fmt(x.totalAmount)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="sub">{t('mgr.rp.noOutput')}</p>}
            </Panel>

            <Panel title={t('mgr.rp.robots')} aside={<Link to="/staff/robots" className="link">{t('mgr.nav.robots')}</Link>}>
              {r.robots.length ? (
                <div className="mgr-table-wrap">
                  <table className="mgr-table">
                    <thead>
                      <tr>
                        <th scope="col">{t('mgr.rp.robot')}</th>
                        <th scope="col" className="num">{t('mgr.rp.jobs')}</th>
                        <th scope="col" className="num">{t('mgr.rp.minutes')}</th>
                        <th scope="col" className="num">{t('mgr.rp.incidents')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {r.robots.map((x) => (
                        <tr key={x.robotId}>
                          <th scope="row">{x.robotCode}</th>
                          <td className="num">{x.jobsWritten}</td>
                          <td className="num">{x.writingMinutes}</td>
                          <td className="num">{x.incidents}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="sub">{t('wk.noRobots')}</p>}
            </Panel>
          </div>

          <Panel title={t('mgr.rp.late')} sub={t('mgr.rp.lateSub')}>
            {r.late.orders.length ? (
              <div className="mgr-table-wrap">
                <table className="mgr-table">
                  <thead>
                    <tr>
                      <th scope="col">{t('mgr.rp.order')}</th>
                      <th scope="col">{t('mgr.rp.eta')}</th>
                      <th scope="col">{t('mgr.rp.completed')}</th>
                      <th scope="col" className="num">{t('mgr.rp.daysLate')}</th>
                      <th scope="col" className="num">{t('mgr.rp.postponed')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.late.orders.map((o) => (
                      <tr key={o.orderId}>
                        <th scope="row"><Link to={`/staff/review/${o.orderId}`} className="vh-link">{o.code}</Link></th>
                        <td>{day(o.eta)}</td>
                        <td>{day(o.completedOn)}</td>
                        <td className="num">{o.daysLate}</td>
                        <td className="num">{o.postponedDays}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <p className="sub">{t('mgr.rp.noLate')}</p>}
          </Panel>
        </>
      )}
    </Shell>
  )
}
