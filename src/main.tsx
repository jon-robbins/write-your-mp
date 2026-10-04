import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { startHeightReporting } from './lib/embed';
import './styles.css';

const root = document.getElementById('root')!;
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
startHeightReporting(window, root);
