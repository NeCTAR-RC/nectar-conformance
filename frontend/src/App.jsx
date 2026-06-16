import { NavLink, Route, Routes } from 'react-router-dom'
import { useApi } from './useApi.js'
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
