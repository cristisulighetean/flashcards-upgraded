import React, { useState } from 'react';
import { ArrowLeft, ArrowRight, ChevronLeft, Trash2, FileText } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { deleteFlashcard } from '../api';

const CardBrowser = ({ cards: initialCards, startIndex = 0, onClose, onCardDeleted }) => {
  const [cards, setCards] = useState(initialCards);
  const [currentIndex, setCurrentIndex] = useState(startIndex);
  const [isFlipped, setIsFlipped] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // If all cards have been deleted, go back
  if (cards.length === 0) {
    onClose();
    return null;
  }

  // Clamp the index if we deleted the last card
  const safeIndex = Math.min(currentIndex, cards.length - 1);
  if (safeIndex !== currentIndex) {
    setCurrentIndex(safeIndex);
  }

  const currentCard = cards[safeIndex];
  const progressPercent = ((safeIndex + 1) / cards.length) * 100;

  const goNext = () => {
    if (safeIndex < cards.length - 1) {
      setIsFlipped(false);
      setShowDeleteConfirm(false);
      setTimeout(() => setCurrentIndex(i => i + 1), 200);
    }
  };

  const goPrev = () => {
    if (safeIndex > 0) {
      setIsFlipped(false);
      setShowDeleteConfirm(false);
      setTimeout(() => setCurrentIndex(i => i - 1), 200);
    }
  };

  const handleFlip = () => {
    if (!showDeleteConfirm) {
      setIsFlipped(f => !f);
    }
  };

  const handleDelete = async () => {
    if (!showDeleteConfirm) {
      setShowDeleteConfirm(true);
      return;
    }

    setIsDeleting(true);
    try {
      await deleteFlashcard(currentCard.id);
      const newCards = cards.filter(c => c.id !== currentCard.id);
      setCards(newCards);
      setIsFlipped(false);
      setShowDeleteConfirm(false);
      if (onCardDeleted) onCardDeleted(currentCard.id);
      // Index will be clamped on next render
    } catch (err) {
      console.error('Failed to delete flashcard', err);
    } finally {
      setIsDeleting(false);
    }
  };

  // Keyboard navigation
  React.useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight') goNext();
      if (e.key === 'ArrowLeft') goPrev();
      if (e.key === ' ') { e.preventDefault(); handleFlip(); }
      if (e.key === 'Escape') {
        if (showDeleteConfirm) {
          setShowDeleteConfirm(false);
        } else {
          onClose();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [currentIndex, isFlipped, showDeleteConfirm]);

  return (
    <div style={{ animation: 'fadeIn 0.3s ease' }}>
      {/* Top bar */}
      <div className="card-toolbar">
        <button className="btn btn-secondary" onClick={onClose}>
          <ChevronLeft size={16} /> Library
        </button>
        <span className="card-toolbar-status">
          Card {safeIndex + 1} of {cards.length}
        </span>
        {/* Delete button */}
        <button
          className={`btn ${showDeleteConfirm ? 'btn-danger' : 'btn-secondary'}`}
          onClick={handleDelete}
          disabled={isDeleting}
        >
          <Trash2 size={14} />
          {isDeleting ? 'Deleting...' : showDeleteConfirm ? 'Confirm Delete' : 'Delete'}
        </button>
      </div>

      {/* Source file badge */}
      {currentCard.document_filename && (
        <div className="source-badge">
          <FileText size={13} />
          {currentCard.document_filename}
        </div>
      )}

      {/* Delete confirmation banner */}
      {showDeleteConfirm && (
        <div style={{
          padding: '0.75rem 1rem',
          background: 'rgba(255, 71, 87, 0.1)',
          border: '1px solid rgba(255, 71, 87, 0.3)',
          borderRadius: 'var(--radius-sm)',
          marginBottom: '1.5rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: '0.9rem',
        }}>
          <span style={{ color: '#ff4757' }}>Are you sure you want to delete this card?</span>
          <button
            className="btn btn-secondary"
            onClick={() => setShowDeleteConfirm(false)}
            style={{ padding: '0.3rem 0.8rem', fontSize: '0.8rem' }}
          >
            Cancel
          </button>
        </div>
      )}

      {/* Progress bar */}
      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progressPercent}%` }} />
      </div>

      {/* Card */}
      <div className="review-container">
        <div className="scene scene-compact" onClick={handleFlip}>
          <div className={`flashcard ${isFlipped ? 'is-flipped' : ''}`}>

            {/* Front */}
            <div className="card-face card-front glass-panel">
              <div className="card-content">
                {currentCard.question}
              </div>
              {!isFlipped && (
                <div className="card-hint">Click to reveal answer · Space · ←→ to navigate</div>
              )}
            </div>

            {/* Back — scrollable for longer answers */}
            <div className="card-face card-back glass-panel">
              <div className="card-back-label">Answer</div>
              <div className="markdown-content">
                <ReactMarkdown>{currentCard.answer}</ReactMarkdown>
              </div>
              <div className="card-hint card-hint-inline">
                Click to flip back
              </div>
            </div>

          </div>
        </div>

        {/* Navigation */}
        <div className="card-actions">
          <button className="btn btn-secondary" onClick={goPrev} disabled={safeIndex === 0}>
            <ArrowLeft size={16} /> Previous
          </button>
          <button className="btn btn-secondary" onClick={handleFlip}>
            {isFlipped ? 'Hide Answer' : 'Show Answer'}
          </button>
          <button
            className="btn btn-secondary"
            onClick={goNext}
            disabled={safeIndex === cards.length - 1}
          >
            Next <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
};

export default CardBrowser;
