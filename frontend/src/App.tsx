import { NavLink, Route, Routes, useLocation } from "react-router";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { DashboardPage } from "./pages/DashboardPage";
import { StatsPage } from "./pages/StatsPage";
import { SubmitPage } from "./pages/SubmitPage";

export function App() {
  const { pathname } = useLocation();
  return (
    <>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <header className="site-header">
        <NavLink to="/" className="brand">
          CivicPulse
        </NavLink>
        <nav aria-label="Main">
          <NavLink to="/" end>
            Report
          </NavLink>
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/stats">Stats</NavLink>
        </nav>
      </header>
      <main id="main">
        {/* A boundary per view keeps the header usable if one page crashes;
            keying it by path clears the error when the user navigates away. */}
        <ErrorBoundary key={pathname}>
          <Routes>
            <Route path="/" element={<SubmitPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/stats" element={<StatsPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </>
  );
}

function NotFound() {
  return (
    <div className="page narrow">
      <h1>Page not found</h1>
      <p>
        <NavLink to="/">Report a problem</NavLink> or open the <NavLink to="/dashboard">dashboard</NavLink>.
      </p>
    </div>
  );
}
