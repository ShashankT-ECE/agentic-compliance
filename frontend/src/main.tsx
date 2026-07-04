import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './App.css';

const root = document.getElementById('root');

if (!root) {
  throw new Error(
    'Root element not found. Ensure index.html contains <div id="root"></div>.',
  );
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
