import React, { useEffect, useState } from 'react';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import UploadSection from './components/UploadSection';
import ReviewSession from './components/ReviewSession';
import ReviewNewCards from './components/ReviewNewCards';
import CardBrowser from './components/CardBrowser';
import VocabSection from './components/VocabSection';

// Which screen you're on survives a refresh; sessionStorage rather than
// localStorage, so closing the tab still starts fresh next time. 'browse'
// is deliberately excluded — its card list is a specific selection passed in
// at click time (e.g. one document's cards), not something worth re-deriving
// from scratch after a reload, so a refresh there lands on the dashboard.
const VIEW_STORAGE_KEY = 'flashcards_view_state';
const RESTORABLE_VIEWS = new Set(['dashboard', 'upload', 'review', 'vocab', 'review-new']);

const loadViewState = () => {
  try {
    const saved = JSON.parse(sessionStorage.getItem(VIEW_STORAGE_KEY) || '{}');
    if (RESTORABLE_VIEWS.has(saved.currentView)) return saved;
  } catch {
    // Corrupt or missing: fall through to the default.
  }
  return { currentView: 'dashboard', studyType: null, studyLang: null };
};

function App() {
  const initial = loadViewState();
  const [currentView, setCurrentView] = useState(initial.currentView);
  const [browseCards, setBrowseCards] = useState([]);
  const [browseStartIndex, setBrowseStartIndex] = useState(0);
  // null = study everything; 'vocab' or 'qa' narrows the session.
  const [studyType, setStudyType] = useState(initial.studyType);
  // Which vocabulary deck (language being learned) to study.
  const [studyLang, setStudyLang] = useState(initial.studyLang);

  // Persist whichever screen is up, so a refresh lands back on it instead of
  // bouncing to the dashboard.
  useEffect(() => {
    if (!RESTORABLE_VIEWS.has(currentView)) return;
    sessionStorage.setItem(
      VIEW_STORAGE_KEY,
      JSON.stringify({ currentView, studyType, studyLang })
    );
  }, [currentView, studyType, studyLang]);

  const handleGenerationSuccess = (count) => {
    setTimeout(() => {
      setCurrentView('dashboard');
    }, 1500);
  };

  const handleStartReview = (cardType = null, lang = null) => {
    setStudyType(cardType);
    setStudyLang(lang);
    setCurrentView('review');
  };

  const handleStudyVocab = (lang = null) => handleStartReview('vocab', lang);

  const handleReviewNew = () => {
    setCurrentView('review-new');
  };

  const handleFinishReview = () => {
    setCurrentView('dashboard');
  };

  const handleBrowseCard = (cards, index) => {
    setBrowseCards(cards);
    setBrowseStartIndex(index);
    setCurrentView('browse');
  };

  const handleCloseBrowse = () => {
    setCurrentView('dashboard');
  };

  return (
    <Layout currentView={currentView} setView={setCurrentView}>
      {currentView === 'dashboard' && (
        <Dashboard
          // qa only: the Dashboard is the document-library home now that
          // vocabulary has its own page with its own study entry points.
          onStartReview={() => handleStartReview('qa')}
          onReviewNew={handleReviewNew}
          onBrowseCard={handleBrowseCard}
        />
      )}
      {currentView === 'upload' && <UploadSection onGenerationSuccess={handleGenerationSuccess} />}
      {currentView === 'review' && (
        <ReviewSession
          onFinish={handleFinishReview}
          cardType={studyType}
          lang={studyLang}
        />
      )}
      {currentView === 'vocab' && (
        <VocabSection onStudyVocab={handleStudyVocab} />
      )}
      {/* Document-generated cards only — vocabulary words have their own
          per-deck Quality Control on the Vocabulary page. */}
      {currentView === 'review-new' && <ReviewNewCards onFinish={handleFinishReview} cardType="qa" />}
      {currentView === 'browse' && <CardBrowser cards={browseCards} startIndex={browseStartIndex} onClose={handleCloseBrowse} />}
    </Layout>
  );
}

export default App;
