import Shell from '../../components/ws/Shell'
import { useT } from '../../i18n'
import { PricingPanel } from './Catalog'

/** Manager only: the versioned price list. A change makes the next version and applies it at once. */
export default function Pricing() {
  const t = useT()
  return (
    <Shell area="manager" active="pricing" title={t('rail.pricing')} lede={t('mg.p.lede')}>
      <div className="wk-page mg">
        <PricingPanel />
      </div>
    </Shell>
  )
}
