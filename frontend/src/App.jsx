import React, { useState } from 'react';
import Layout from './components/Layout';
import Dashboard from './components/Dashboard';
import UploadSection from './components/UploadSection';
import ReviewSession from './components/ReviewSession';
import ReviewNewCards from './components/ReviewNewCards';
import CardBrowser from './components/CardBrowser';
import VocabSection from './components/VocabSection';

function App() {
  const [currentView, setCurrentView] = useState('dashboard');
  const [browseCards, setBrowseCards] = useState([]);
  const [browseStartIndex, setBrowseStartIndex] = useState(0);
  // null = study everything; 'vocab' or 'qa' narrows the session.
  const [studyType, setStudyType] = useState(null);
  // Which vocabulary deck (language being learned) to study or open.
  const [studyLang, setStudyLang] = useState(null);
  const [vocabLang, setVocabLang] = useState('en');

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

  const handleOpenVocab = (lang = 'en') => {
    setVocabLang(lang);
    setCurrentView('vocab');
  };

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
          onStartReview={() => handleStartReview(null)} 
          onStudyVocab={handleStudyVocab}
          onAddWords={handleOpenVocab} 
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
        <VocabSection onStudyVocab={handleStudyVocab} initialLang={vocabLang} />
      )}
      {currentView === 'review-new' && <ReviewNewCards onFinish={handleFinishReview} />}
      {currentView === 'browse' && <CardBrowser cards={browseCards} startIndex={browseStartIndex} onClose={handleCloseBrowse} />}
    </Layout>
  );
}

export default App;
