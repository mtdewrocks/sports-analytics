import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { AuthProvider } from './context/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import Navbar, { TABBAR_HEIGHT } from './components/Navbar';
import Footer from './components/Footer';
import useIsMobile from './hooks/useIsMobile';

declare global {
  interface Window {
    gtag?: (...args: any[]) => void;
  }
}

// Fires a GA4 page_view on every route change, including the first one.
// Needed because this is a single-page app -- the page never actually
// reloads on navigation, so GA4's own automatic page_view (disabled in
// index.html) would only ever fire once per visit no matter how many pages
// someone actually browsed. Must be rendered inside <BrowserRouter>, since
// useLocation only works within the Router context.
function usePageTracking() {
  const location = useLocation();
  useEffect(() => {
    window.gtag?.('event', 'page_view', {
      page_path: location.pathname + location.search,
      page_title: document.title,
    });
  }, [location]);
}

function PageTracker() {
  usePageTracking();
  return null;
}

// The mobile tab bar is fixed to the bottom of the viewport, so the page has
// to reserve its height -- without this the last card on every page sits
// underneath it and can't be scrolled into view.
function AppShell({ children }: { children: ReactNode }) {
  const isMobile = useIsMobile();
  return <div style={{ paddingBottom: isMobile ? TABBAR_HEIGHT : 0 }}>{children}</div>;
}

import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import Login from './pages/Login';
import Register from './pages/Register';
import Billing from './pages/Billing';

import NBAGameLog from './pages/nba/NBAGameLog';
import NBAInOut from './pages/nba/NBAInOut';
import NBAProps from './pages/nba/NBAProps';

import NFLGameLog from './pages/nfl/NFLGameLog';
import NFLMatchup from './pages/nfl/NFLMatchup';
import NFLFantasyMatchup from './pages/nfl/NFLFantasyMatchup';
import NFLInOut from './pages/nfl/NFLInOut';
import NFLSeasonScreener from './pages/nfl/NFLSeasonScreener';
import NFLMismatches from './pages/nfl/NFLMismatches';

import MLBMatchup from './pages/mlb/MLBMatchup';
import MLBTeamMatchup from './pages/mlb/MLBTeamMatchup';
import MLBBullpen from './pages/mlb/MLBBullpen';
import MLBPitcherDailyReport from './pages/mlb/MLBPitcherDailyReport';
import MLBHotHitters from './pages/mlb/MLBHotHitters';
import MLBProps from './pages/mlb/MLBProps';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <PageTracker />
        <Navbar />
        <AppShell>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/billing" element={<PrivateRoute><Billing /></PrivateRoute>} />

          <Route path="/nba/game-log" element={<PrivateRoute><NBAGameLog /></PrivateRoute>} />
          <Route path="/nba/in-out" element={<PrivateRoute><NBAInOut /></PrivateRoute>} />
          <Route path="/nba/props" element={<PrivateRoute><NBAProps /></PrivateRoute>} />

          <Route path="/nfl/game-log" element={<PrivateRoute><NFLGameLog /></PrivateRoute>} />
          <Route path="/nfl/matchup" element={<PrivateRoute><NFLMatchup /></PrivateRoute>} />
          <Route path="/nfl/fantasy-matchup" element={<PrivateRoute><NFLFantasyMatchup /></PrivateRoute>} />
          <Route path="/nfl/in-out" element={<PrivateRoute><NFLInOut /></PrivateRoute>} />
          <Route path="/nfl/season-screener" element={<PrivateRoute><NFLSeasonScreener /></PrivateRoute>} />
          <Route path="/nfl/mismatches" element={<PrivateRoute><NFLMismatches /></PrivateRoute>} />

          <Route path="/mlb/matchup" element={<PrivateRoute><MLBMatchup /></PrivateRoute>} />
          <Route path="/mlb/team-matchup" element={<PrivateRoute><MLBTeamMatchup /></PrivateRoute>} />
          <Route path="/mlb/bullpen" element={<PrivateRoute><MLBBullpen /></PrivateRoute>} />
          <Route path="/mlb/pitcher-daily-report" element={<PrivateRoute><MLBPitcherDailyReport /></PrivateRoute>} />
          <Route path="/mlb/hot-hitters" element={<PrivateRoute><MLBHotHitters /></PrivateRoute>} />
          <Route path="/mlb/props" element={<PrivateRoute><MLBProps /></PrivateRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        <Footer />
        </AppShell>
      </BrowserRouter>
    </AuthProvider>
  );
}
