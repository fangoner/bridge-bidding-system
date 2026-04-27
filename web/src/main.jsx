import React, { StrictMode, useState, useMemo, useCallback, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import { ThemeProvider } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import { createAppTheme } from './theme'
import './index.css'
import App from './App.jsx'
import ErrorBoundary from './components/ErrorBoundary.jsx'

const DARK_MODE_KEY = 'bridge_dark_mode'

function ThemeWrapper({ children }) {
  const [darkMode, setDarkMode] = useState(() => {
    try {
      return localStorage.getItem(DARK_MODE_KEY) === 'true'
    } catch {
      return false
    }
  })

  const theme = useMemo(() => createAppTheme(darkMode ? 'dark' : 'light'), [darkMode])

  const toggleDarkMode = useCallback(() => {
    setDarkMode(prev => {
      const next = !prev
      try {
        localStorage.setItem(DARK_MODE_KEY, String(next))
      } catch { /* ignore */ }
      return next
    })
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', darkMode ? 'dark' : 'light')
  }, [darkMode])

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <ErrorBoundary>
        {React.cloneElement(children, { darkMode, onToggleDarkMode: toggleDarkMode })}
      </ErrorBoundary>
    </ThemeProvider>
  )
}

// 全局错误捕获 —— 记录崩溃原因，便于排查
const BIDDING_CRASH_LOG_KEY = 'bridge_crash_log'

window.addEventListener('error', (event) => {
  const { message, filename, lineno, colno, error } = event
  const crash = {
    type: 'uncaught_error',
    message: message || (error?.message || 'Unknown'),
    stack: error?.stack || '',
    filename, lineno, colno,
    timestamp: new Date().toISOString(),
    url: window.location.href,
  }
  console.error('[Global Error]', crash)
  try {
    // 只保留最近一次崩溃日志
    localStorage.setItem(BIDDING_CRASH_LOG_KEY, JSON.stringify(crash))
  } catch (e) { /* ignore */ }
})

window.addEventListener('unhandledrejection', (event) => {
  const { reason } = event
  const crash = {
    type: 'unhandled_rejection',
    message: reason?.message || (typeof reason === 'string' ? reason : 'Unknown Promise rejection'),
    stack: reason?.stack || '',
    timestamp: new Date().toISOString(),
    url: window.location.href,
  }
  console.error('[Global Unhandled Rejection]', crash)
  try {
    localStorage.setItem(BIDDING_CRASH_LOG_KEY, JSON.stringify(crash))
  } catch (e) { /* ignore */ }
})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ThemeWrapper>
      <App />
    </ThemeWrapper>
  </StrictMode>,
)
