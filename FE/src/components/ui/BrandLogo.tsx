import { useId } from 'react'
import darkLogo from '../../assets/logo-dark.png'
import lightLogo from '../../assets/logo-light.png'
import { useTheme } from '../../store/theme'
import './brand-logo.css'

export default function BrandLogo({ theme }: { theme?: 'dark' | 'light' }) {
  const currentTheme = useTheme()
  const filterId = useId()
  const dark = (theme ?? currentTheme) === 'dark'
  // Convert the monochrome artwork's background to alpha, independent of the page beneath it.
  const matrix = dark
    ? '0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  .2126 .7152 .0722 0 0'
    : '0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  -.2126 -.7152 -.0722 0 1'
  return <svg className="brand-logo" viewBox="140 200 1070 420" role="img" aria-label="AI-VHRS">
    <defs>
      <filter id={filterId} colorInterpolationFilters="sRGB" x="0%" y="0%" width="100%" height="100%">
        <feColorMatrix type="matrix" values={matrix} />
      </filter>
    </defs>
    <image href={dark ? darkLogo : lightLogo} width={1264} height={848} filter={`url(#${filterId})`} />
  </svg>
}
