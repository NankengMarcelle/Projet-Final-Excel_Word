import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import { AuthProvider } from './auth/AuthContext'
import { ThemeProvider } from './theme/ThemeContext'
import { LangProvider } from './i18n/LangContext'
import { router } from './routes/router'

// refetchOnWindowFocus defaults to true — harmless for most apps, but actively harmful here:
// EditorWorkbook's own worksheet query deliberately fetches every sheet one at a time (its own
// comment explains why parallel fetching is *slower* for this backend — CPU-bound work fighting
// over the GIL), which already takes tens of seconds on a real multi-sheet workbook. Confirmed
// live: every time the browser tab regained focus, React Query silently restarted that entire
// slow fetch — and the app's own invalidateQueries calls (after every autosave, after syncing a
// child sheet) already cover every case where this app's own actions make cached data stale, so
// there's nothing this was buying beyond "someone alt-tabbed."  Nothing here depends on picking
// up changes made by *another* browser tab/session either, so refetchOnReconnect is equally
// unnecessary.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      refetchOnReconnect: false,
    },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <LangProvider>
        <QueryClientProvider client={queryClient}>
          <AuthProvider>
            <RouterProvider router={router} />
          </AuthProvider>
        </QueryClientProvider>
      </LangProvider>
    </ThemeProvider>
  </StrictMode>,
)
