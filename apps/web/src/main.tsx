import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles/tokens.css';
import './styles/global.css';
import './styles/market-intelligence.css';
import './styles/strength-intelligence.css';
import './styles/market-scanner.css';
import './styles/market-structure.css';
import './styles/ai-outlook.css';
import './styles/h8-bos-btl.css';
import './styles/system-control-mt5.css';
import './styles/notifications.css';
import './styles/responsive-layout.css';
import './styles/compact-laptop.css';
import './styles/overview-dashboard.css';
import './styles/autonomous-engine.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
