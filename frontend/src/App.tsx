import {
  Header,
  HeaderName,
  HeaderGlobalBar,
  HeaderGlobalAction,
  SkipToContent,
  Theme,
  Content,
} from '@carbon/react'
import { Activity, Information } from '@carbon/icons-react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import HomePage from './pages/HomePage'
import JobDetailPage from './pages/JobDetailPage'

export default function App() {
  return (
    <Theme theme="g100">
      <BrowserRouter>
        {/* ── Carbon Shell ─────────────────────────────────────────── */}
        <Header aria-label="ESS Comprestimator">
          <SkipToContent />
          <HeaderName href="/" prefix="IBM">
            ESS Comprestimator
          </HeaderName>
          <HeaderGlobalBar>
            <HeaderGlobalAction
              aria-label="Activity"
              tooltipAlignment="end"
            >
              <Activity size={20} />
            </HeaderGlobalAction>
            <HeaderGlobalAction
              aria-label="About"
              tooltipAlignment="end"
              onClick={() =>
                window.open(
                  'https://github.com/IBM/ess_comprestimator',
                  '_blank',
                )
              }
            >
              <Information size={20} />
            </HeaderGlobalAction>
          </HeaderGlobalBar>
        </Header>

        {/* ── Page content (offset for fixed header) ───────────────── */}
        <Content>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/jobs/:jobId" element={<JobDetailPage />} />
          </Routes>
        </Content>
      </BrowserRouter>
    </Theme>
  )
}
