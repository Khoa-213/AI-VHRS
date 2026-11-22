import { Moon, Sun } from '@phosphor-icons/react'
import { useT } from '../../i18n'
import { setTheme, useTheme } from '../../store/theme'
import './appearance-switch.css'

/** One saved appearance preference shared by the management areas and the public site. */
export default function AppearanceSwitch({ className = '' }: { className?: string }) {
  const t = useT()
  const theme = useTheme()
  return (
    <div className={`appearance-switch ${className}`} role="group" aria-label={t('adm.theme.label')}>
      <button type="button" aria-label={t('adm.theme.light')} title={t('adm.theme.light')} aria-pressed={theme === 'light'} onClick={() => setTheme('light')}><Sun size={16} aria-hidden /><span>{t('adm.theme.light')}</span></button>
      <button type="button" aria-label={t('adm.theme.dark')} title={t('adm.theme.dark')} aria-pressed={theme === 'dark'} onClick={() => setTheme('dark')}><Moon size={16} aria-hidden /><span>{t('adm.theme.dark')}</span></button>
    </div>
  )
}
