import { createRoot } from 'react-dom/client';

import { App } from './App';
import './style/tailwind.css';
import './style/index.css';

createRoot(document.getElementById('root')!).render(<App />);
