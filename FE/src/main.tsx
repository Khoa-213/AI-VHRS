import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/theme.css'
import './index.css'
import './styles/shell.css'
import './store/theme'
import App from './App.tsx'
import { startSession } from './store/store'

// Check the saved sign-in against the backend before the first render settles.
startSession()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
