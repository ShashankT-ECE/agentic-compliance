import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import DashboardPage from './pages/index';
import ReportPage from './pages/report';
import './App.css';

export default function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        {/* Header */}
        <header className="app-header">
          <div className="app-header__branding">
            <span className="app-header__logo" aria-hidden="true">
              🛡️
            </span>
            <div>
              <div className="app-header__title">Agentic Compliance</div>
              <div className="app-header__subtitle">
                SEBI Regulatory Verification
              </div>
            </div>
          </div>

          <nav className="app-header__nav">
            <NavLink
              to="/"
              end
              className={({ isActive }) =>
                [
                  'app-header__nav-link',
                  isActive ? 'app-header__nav-link--active' : '',
                ]
                  .filter(Boolean)
                  .join(' ')
              }
            >
              Dashboard
            </NavLink>
            <NavLink
              to="/report"
              className={({ isActive }) =>
                [
                  'app-header__nav-link',
                  isActive ? 'app-header__nav-link--active' : '',
                ]
                  .filter(Boolean)
                  .join(' ')
              }
            >
              Reports
            </NavLink>
          </nav>
        </header>

        {/* Main content */}
        <main className="app-main">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/report/:reportId?" element={<ReportPage />} />
          </Routes>
        </main>

        {/* Footer */}
        <footer className="app-footer">
          Agentic Compliance v1.0.0 &mdash; SEBI TechSprint Problem Statement 2
        </footer>
      </div>
    </BrowserRouter>
  );
}
