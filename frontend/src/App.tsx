import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import PrivateRoute from './components/PrivateRoute';
import Navbar from './components/Navbar';

import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Billing from './pages/Billing';

import NBAGameLog from './pages/nba/NBAGameLog';
import NBAInOut from './pages/nba/NBAInOut';
import NBAProps from './pages/nba/NBAProps';

import NFLGameLog from './pages/nfl/NFLGameLog';
import NFLMatchup from './pages/nfl/NFLMatchup';

import MLBMatchup from './pages/mlb/MLBMatchup';
import MLBHotHitters from './pages/mlb/MLBHotHitters';
import MLBProps from './pages/mlb/MLBProps';

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Navbar />
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/billing" element={<PrivateRoute><Billing /></PrivateRoute>} />

          <Route path="/nba/game-log" element={<PrivateRoute><NBAGameLog /></PrivateRoute>} />
          <Route path="/nba/in-out" element={<PrivateRoute><NBAInOut /></PrivateRoute>} />
          <Route path="/nba/props" element={<PrivateRoute><NBAProps /></PrivateRoute>} />

          <Route path="/nfl/game-log" element={<PrivateRoute><NFLGameLog /></PrivateRoute>} />
          <Route path="/nfl/matchup" element={<PrivateRoute><NFLMatchup /></PrivateRoute>} />

          <Route path="/mlb/matchup" element={<PrivateRoute><MLBMatchup /></PrivateRoute>} />
          <Route path="/mlb/hot-hitters" element={<PrivateRoute><MLBHotHitters /></PrivateRoute>} />
          <Route path="/mlb/props" element={<PrivateRoute><MLBProps /></PrivateRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
