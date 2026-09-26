import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { lazy, Suspense, useEffect } from 'react';
import type { ReactNode } from 'react';
import { AuthProvider } from './context/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import Navbar, { TABBAR_HEIGHT } from './components/Navbar';
import Footer from './components/Footer';
import useIsMobile from './hooks/useIsMobile';
import LoadingSpinner from './components/LoadingSpinner';

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

// Every page except Landing is loaded on demand: a visitor downloads the code
// for the page they open, not all ~30 pages (and the charting/PDF libraries
// only a few of them use) up front. Landing stays in the main bundle so the
// first thing a new visitor sees paints without a second round trip.
import Landing from './pages/Landing';
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Login = lazy(() => import('./pages/Login'));
const Register = lazy(() => import('./pages/Register'));
const Billing = lazy(() => import('./pages/Billing'));

const NBAGameLog = lazy(() => import('./pages/nba/NBAGameLog'));
const NBAInOut = lazy(() => import('./pages/nba/NBAInOut'));
const NBAProps = lazy(() => import('./pages/nba/NBAProps'));
const NBATeamUsage = lazy(() => import('./pages/nba/NBATeamUsage'));
const NBATeamMatchup = lazy(() => import('./pages/nba/NBATeamMatchup'));

const NFLGameLog = lazy(() => import('./pages/nfl/NFLGameLog'));
const NFLMatchup = lazy(() => import('./pages/nfl/NFLMatchup'));
const NFLFantasyMatchup = lazy(() => import('./pages/nfl/NFLFantasyMatchup'));
const NFLInOut = lazy(() => import('./pages/nfl/NFLInOut'));
const NFLSeasonScreener = lazy(() => import('./pages/nfl/NFLSeasonScreener'));
const NFLMismatches = lazy(() => import('./pages/nfl/NFLMismatches'));
const NFLProps = lazy(() => import('./pages/nfl/NFLProps'));
const NFLTeamUsage = lazy(() => import('./pages/nfl/NFLTeamUsage'));
const NFLPlayerUsageTrend = lazy(() => import('./pages/nfl/NFLPlayerUsageTrend'));
const NFLWeather = lazy(() => import('./pages/nfl/NFLWeather'));

const MLBGameLog = lazy(() => import('./pages/mlb/MLBGameLog'));
const MLBMatchup = lazy(() => import('./pages/mlb/MLBMatchup'));
const MLBTeamMatchup = lazy(() => import('./pages/mlb/MLBTeamMatchup'));
const MLBBullpen = lazy(() => import('./pages/mlb/MLBBullpen'));
const MLBPitcherDailyReport = lazy(() => import('./pages/mlb/MLBPitcherDailyReport'));
const MLBHotHitters = lazy(() => import('./pages/mlb/MLBHotHitters'));
const MLBProps = lazy(() => import('./pages/mlb/MLBProps'));
const MLBWeather = lazy(() => import('./pages/mlb/MLBWeather'));
const MLBMatchupEdge = lazy(() => import('./pages/mlb/MLBMatchupEdge'));
const HitRateSheet = lazy(() => import('./pages/HitRateSheet'));
const BettingEVFinder = lazy(() => import('./pages/betting/EVFinder'));
const BettingAltLineValue = lazy(() => import('./pages/betting/AltLineValue'));
const BettingMiddles = lazy(() => import('./pages/betting/Middles'));
const BettingToday = lazy(() => import('./pages/betting/Today'));
const DailyBriefing = lazy(() => import('./pages/DailyBriefing'));
const BettingMyBets = lazy(() => import('./pages/betting/MyBets'));

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <PageTracker />
        <Navbar />
        <AppShell>
        <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/billing" element={<PrivateRoute><Billing /></PrivateRoute>} />

          <Route path="/nba/game-log" element={<PrivateRoute><NBAGameLog /></PrivateRoute>} />
          <Route path="/nba/in-out" element={<PrivateRoute><NBAInOut /></PrivateRoute>} />
          <Route path="/nba/team-usage" element={<PrivateRoute><NBATeamUsage /></PrivateRoute>} />
          <Route path="/nba/team-matchup" element={<PrivateRoute><NBATeamMatchup /></PrivateRoute>} />
          <Route path="/nba/props" element={<PrivateRoute><NBAProps /></PrivateRoute>} />

          <Route path="/nfl/game-log" element={<PrivateRoute><NFLGameLog /></PrivateRoute>} />
          <Route path="/nfl/matchup" element={<PrivateRoute><NFLMatchup /></PrivateRoute>} />
          <Route path="/nfl/fantasy-matchup" element={<PrivateRoute><NFLFantasyMatchup /></PrivateRoute>} />
          <Route path="/nfl/in-out" element={<PrivateRoute><NFLInOut /></PrivateRoute>} />
          <Route path="/nfl/season-screener" element={<PrivateRoute><NFLSeasonScreener /></PrivateRoute>} />
          <Route path="/nfl/mismatches" element={<PrivateRoute><NFLMismatches /></PrivateRoute>} />
          <Route path="/nfl/team-usage" element={<PrivateRoute><NFLTeamUsage /></PrivateRoute>} />
          <Route path="/nfl/usage-trend" element={<PrivateRoute><NFLPlayerUsageTrend /></PrivateRoute>} />
          <Route path="/nfl/props" element={<PrivateRoute><NFLProps /></PrivateRoute>} />
          <Route path="/nfl/weather" element={<PrivateRoute><NFLWeather /></PrivateRoute>} />

          <Route path="/mlb/game-log" element={<PrivateRoute><MLBGameLog /></PrivateRoute>} />
          <Route path="/mlb/matchup" element={<PrivateRoute><MLBMatchup /></PrivateRoute>} />
          <Route path="/mlb/team-matchup" element={<PrivateRoute><MLBTeamMatchup /></PrivateRoute>} />
          <Route path="/mlb/bullpen" element={<PrivateRoute><MLBBullpen /></PrivateRoute>} />
          <Route path="/mlb/pitcher-daily-report" element={<PrivateRoute><MLBPitcherDailyReport /></PrivateRoute>} />
          <Route path="/mlb/hot-hitters" element={<PrivateRoute><MLBHotHitters /></PrivateRoute>} />
          <Route path="/mlb/props" element={<PrivateRoute><MLBProps /></PrivateRoute>} />
          <Route path="/mlb/weather" element={<PrivateRoute><MLBWeather /></PrivateRoute>} />
          <Route path="/mlb/matchup-edge" element={<PrivateRoute><MLBMatchupEdge /></PrivateRoute>} />

          {/* Betting tools: cross-sport, listed after the sports (see siteMap.ts). */}
          <Route path="/betting/ev" element={<PrivateRoute><BettingEVFinder /></PrivateRoute>} />
          <Route path="/betting/alt-lines" element={<PrivateRoute><BettingAltLineValue /></PrivateRoute>} />
          <Route path="/betting/middles" element={<PrivateRoute><BettingMiddles /></PrivateRoute>} />
          <Route path="/betting/edge-board" element={<PrivateRoute><BettingToday /></PrivateRoute>} />
          <Route path="/betting/today" element={<Navigate to="/betting/edge-board" replace />} />
          <Route path="/briefing" element={<PrivateRoute><DailyBriefing /></PrivateRoute>} />
          <Route path="/betting/my-bets" element={<PrivateRoute><BettingMyBets /></PrivateRoute>} />
          <Route path="/betting/hit-rate-sheet" element={<PrivateRoute><HitRateSheet /></PrivateRoute>} />
          {/* Old addresses, kept working for bookmarks. */}
          <Route path="/hit-rate-sheet" element={<Navigate to="/betting/hit-rate-sheet" replace />} />
          <Route path="/mlb/middles" element={<Navigate to="/betting/middles?sport=mlb" replace />} />
          <Route path="/nfl/middles" element={<Navigate to="/betting/middles?sport=nfl" replace />} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </Suspense>
        <Footer />
        </AppShell>
      </BrowserRouter>
    </AuthProvider>
  );
}
