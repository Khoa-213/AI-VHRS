import { useT } from '../../i18n'

/** First tab stop: jumps over the navigation to the page content. */
export default function SkipLink({ target = 'main' }: { target?: string }) {
  const t = useT()
  return <a href={`#${target}`} className="skip-link">{t('skip')}</a>
}
