import React from 'react';
import { BrainCircuit } from 'lucide-react';

const Layout = ({ currentView, setView, children }) => {
  return (
    <div className="app-container">
      <nav className="navbar">
        <div className="logo" onClick={() => setView('dashboard')} style={{cursor:'pointer'}}>
          <BrainCircuit size={28} color="var(--accent-cyan)" />
          <span>NeuroCard</span>
        </div>
        
        <div className="nav-links">
          <a
            className={`nav-item ${currentView === 'dashboard' ? 'active' : ''}`}
            onClick={() => setView('dashboard')}
          >
            Dashboard
          </a>
          <a
            className={`nav-item ${currentView === 'vocab' ? 'active' : ''}`}
            onClick={() => setView('vocab')}
          >
            Vocabulary
          </a>
          <a
            className={`nav-item ${currentView === 'upload' ? 'active' : ''}`}
            onClick={() => setView('upload')}
          >
            Create
          </a>
        </div>
      </nav>
      <main>
        {children}
      </main>
    </div>
  );
};

export default Layout;
