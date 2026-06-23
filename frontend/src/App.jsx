import { NavLink, Route, Routes } from 'react-router-dom'
import { useApi } from './useApi.js'
import { useTheme } from './useTheme.js'
import { fmtAge } from './ui.jsx'
import Sites from './views/Sites.jsx'
import SiteDetail from './views/SiteDetail.jsx'
import CheckDetail from './views/CheckDetail.jsx'
import Versions from './views/Versions.jsx'
import Changes from './views/Changes.jsx'
import Rollout from './views/Rollout.jsx'

export default function App() {
  const health = useApi('/health')
  const tier = health.data?.tier
  const age = health.data?.age_seconds
  const version = health.data?.version
  const { theme, toggleTheme } = useTheme()

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Nectar Conformance</h1>
          {tier && <span className={`tier tier-${tier}`}>{tier}</span>}
        </div>
        <nav>
          <NavLink to="/" end>
            Sites
          </NavLink>
          <NavLink to="/versions">Versions</NavLink>
          <NavLink to="/changes">Changes</NavLink>
          <NavLink to="/rollout">Rollout</NavLink>
        </nav>
        <span className="freshness" title="When the refresh job last evaluated sites">
          reports {fmtAge(age)}
        </span>
        {version && (
          <span className="version" title="nectar-conformance version">
            v{version}
          </span>
        )}
        <button
          type="button"
          className="theme-toggle"
          onClick={toggleTheme}
          aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
        >
          {theme === 'dark' ? <SunIcon /> : <MoonIcon />}
        </button>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Sites />} />
          <Route path="/sites/:site" element={<SiteDetail />} />
          <Route path="/checks/:checkId" element={<CheckDetail />} />
          <Route path="/versions" element={<Versions />} />
          <Route path="/changes" element={<Changes />} />
          <Route path="/rollout" element={<Rollout />} />
        </Routes>
      </main>
    </div>
  )
}

function SunIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}
