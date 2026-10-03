import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/tokens.css';
import './styles/global.css';
import './styles/market-intelligence.css';
import './styles/strength-intelligence.css';
import './styles/system-control-mt5.css';
import './styles/responsive-layout.css';
import './styles/compact-laptop.css';
import './styles/overview-dashboard.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
