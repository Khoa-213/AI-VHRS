import { useEffect, useRef } from 'react'
import { useT } from '../../i18n'
import { navigate } from '../../router/router'
import type { User } from '../../types'
import SignInPanel from '../login/SignInPanel'

export default function SignInDialog({ onClose, initialMode = 'login', next }: { onClose: () => void; initialMode?: 'login' | 'register'; next?: string }) {
  const t = useT()
  const dialog = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const el = dialog.current!
    const previousOverflow = document.body.style.overflow
    el.showModal()
    document.body.style.overflow = 'hidden'
    return () => {
      el.close()
      document.body.style.overflow = previousOverflow
    }
  }, [])

  const finish = (user: User) => {
    if (user.role !== 'customer') navigate(user.role === 'admin' ? '/admin' : user.role === 'technician' ? '/tech' : '/staff')
    else if (next && next.startsWith('/') && !next.startsWith('//') && !/^\/(login|register|staff|tech|admin)\b/.test(next)) navigate(next)
    onClose()
  }

  return (
    <dialog ref={dialog} className="entry-login" aria-label={t('login.title')}
      onCancel={onClose} onClick={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <SignInPanel onSuccess={finish} onClose={onClose} initialMode={initialMode} />
    </dialog>
  )
}
