import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'
import { initializeI18n } from './i18n'
import './styles.css'

const rootElement = document.getElementById('root')

if (!rootElement) {
  throw new Error('AgentBox root element is missing')
}

initializeI18n()

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
