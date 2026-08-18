import React, { useState, useEffect } from 'react';
import { listPendingFlashcards, acceptFlashcard, deleteFlashcard } from '../api';
import { CheckCircle2, XCircle, FileText, ChevronLeft } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const ReviewNewCards = ({ onFinish }) => {
  const [cards, setCards] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [acceptedCount, setAcceptedCount] = useState(0);
  const [discardedCount, setDiscardedCount] = useState(0);
  const [isActioning, setIsActioning] = useState(false);

  useEffect(() => {
    const fetchPending = async () => {
      try {
        const res = await listPendingFlashcards();
        setCards(res.flashcards || []);
      } catch (err) {
        console.error("Failed to fetch pending cards", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchPending();
  }, []);

  const handleFlip = () => setIsFlipped(f => !f);

  const handleAccept = async () => {
    if (isActioning) return;
    setIsActioning(true);
    try {
      await acceptFlashcard(cards[currentIndex].id);
      setAcceptedCount(c => c + 1);
      advance();
    } catch (err) {
      console.error("Failed to accept card", err);
    } finally {
      setIsActioning(false);
    }
  };

  const handleDiscard = async () => {
    if (isActioning) return;
    setIsActioning(true);
    try {
      await deleteFlashcard(cards[currentIndex].id);
      setDiscardedCount(c => c + 1);
      advance();
    } catch (err) {
      console.error("Failed to discard card", err);
    } finally {
      setIsActioning(false);
    }
  };

  const advance = () => {
    setIsFlipped(false);
    setTimeout(() => {
      setCurrentIndex(i => i + 1);
    }, 200);
  };

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === ' ') { e.preventDefault(); handleFlip(); }
      if (e.key === 'ArrowRight' || e.key === 'a') handleAccept();
      if (e.key === 'ArrowLeft' || e.key === 'd') handleDiscard();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [currentIndex, isFlipped, isActioning]);

  if (isLoading) {
    return <div className="loader-container" style={{ marginTop: '100px' }}><div className="spinner"></div></div>;
  }

  // All cards reviewed
  if (currentIndex >= cards.length) {
    return (
      <div className="upload-container">
        <CheckCircle2 size={64} color="var(--accent-cyan)" style={{ marginBottom: '1rem' }} />
        <h1 className="upload-title text-gradient">Quality Control Complete</h1>
        <div style={{ display: 'flex', gap: '3rem', margin: '1.5rem 0' }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '2.5rem', fontWeight: '800', fontFamily: 'Outfit', color: '#2ed573' }}>{acceptedCount}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Accepted</div>
          </div>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '2.5rem', fontWeight: '800', fontFamily: 'Outfit', color: '#ff4757' }}>{discardedCount}</div>
            <div style={{ color: 'var(--text-secondary)', fontSize: '0.9rem' }}>Discarded</div>
          </div>
        </div>
        <p className="text-secondary" style={{ maxWidth: '400px', textAlign: 'center' }}>
          {acceptedCount > 0
            ? `${acceptedCount} card${acceptedCount !== 1 ? 's' : ''} added to your collection.`
            : 'No cards were accepted this time.'}
        </p>
        <button className="btn btn-primary" onClick={onFinish} style={{ marginTop: '2rem' }}>
          Back to Dashboard
        </button>
      </div>
    );
  }

  // No pending cards at all
  if (cards.length === 0) {
    return (
      <div className="upload-container">
        <CheckCircle2 size={48} color="var(--text-secondary)" style={{ marginBottom: '1rem', opacity: 0.5 }} />
        <h2 style={{ fontFamily: 'Outfit', marginBottom: '0.5rem' }}>No Pending Cards</h2>
        <p className="text-secondary">Generate flashcards from a document first, then come back to review them.</p>
        <button className="btn btn-secondary" onClick={onFinish} style={{ marginTop: '2rem' }}>
          Back to Dashboard
        </button>
      </div>
    );
  }

  const currentCard = cards[currentIndex];
  const progressPercent = ((currentIndex) / cards.length) * 100;

  return (
    <div style={{ animation: 'fadeIn 0.3s ease' }}>
      {/* Top bar */}
      <div className="card-toolbar">
        <button className="btn btn-secondary" onClick={onFinish}>
          <ChevronLeft size={16} /> Dashboard
        </button>
        <span className="card-toolbar-status">
          Quality Control — Card {currentIndex + 1} of {cards.length}
        </span>
        <div className="card-toolbar-counts">
          <span style={{ color: '#2ed573' }}>✓ {acceptedCount}</span>
          <span style={{ color: '#ff4757' }}>✕ {discardedCount}</span>
        </div>
      </div>

      {/* Source file */}
      {currentCard.document_filename && (
        <div className="source-badge">
          <FileText size={13} />
          {currentCard.document_filename}
        </div>
      )}

      {/* Progress bar */}
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
      </div>

      {/* Card */}
      <div className="review-container" style={{ maxWidth: '800px', margin: '0 auto' }}>
        <div className="scene scene-compact" onClick={handleFlip}>
          <div className={`flashcard ${isFlipped ? 'is-flipped' : ''}`}>

            {/* Front */}
            <div className="card-face card-front glass-panel">
              <div className="card-content">
                {currentCard.question}
              </div>
              {!isFlipped && (
                <div className="card-hint">Click to reveal answer · Space to flip</div>
              )}
            </div>

            {/* Back */}
            <div className="card-face card-back glass-panel">
              <div className="card-back-label">Answer</div>
              <div className="markdown-content">
                <ReactMarkdown>{currentCard.answer}</ReactMarkdown>
              </div>
            </div>

          </div>
        </div>

        {/* Accept / Discard actions */}
        <div className="card-actions">
          <button className="btn btn-danger" onClick={handleDiscard} disabled={isActioning}>
            <XCircle size={18} /> Discard
          </button>
          <button className="btn btn-secondary" onClick={handleFlip}>
            {isFlipped ? 'Hide Answer' : 'Show Answer'}
          </button>
          <button className="btn btn-success" onClick={handleAccept} disabled={isActioning}>
            <CheckCircle2 size={18} /> Accept
          </button>
        </div>

        <p className="keyboard-hint">
          Keyboard: A = accept · D = discard · Space = flip
        </p>
      </div>
    </div>
  );
};

export default ReviewNewCards;
