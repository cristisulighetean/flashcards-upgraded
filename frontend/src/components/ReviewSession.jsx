import React, { useState, useEffect } from 'react';
import { listFlashcards, submitReview } from '../api';
import { CheckCircle2, Zap } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

const ReviewSession = ({ onFinish, cardType = null }) => {
  const [priorityCards, setPriorityCards] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Load top priority cards
  useEffect(() => {
    const fetchPriority = async () => {
      try {
        const res = await listFlashcards(15, cardType);
        setPriorityCards(res.flashcards || []);
      } catch (err) {
        console.error("Failed to fetch priority cards", err);
      } finally {
        setIsLoading(false);
      }
    };
    fetchPriority();
  }, [cardType]);

  const handleFlip = () => {
    if (!isFlipped) setIsFlipped(true);
  };

  const handleGrade = async (quality) => {
    const currentCard = priorityCards[currentIndex];
    try {
      // Send grade to backend calculation
      await submitReview(currentCard.id, quality);
      
      // Advance to next card
      setIsFlipped(false);
      setTimeout(() => {
        setCurrentIndex(prev => prev + 1);
      }, 200);
      
    } catch (err) {
      console.error("Failed to submit review", err);
    }
  };

  const handleStartAnother = async () => {
    setIsLoading(true);
    setCurrentIndex(0);
    try {
      const res = await listFlashcards(15, cardType);
      setPriorityCards(res.flashcards || []);
    } catch (err) {
      console.error("Failed to fetch another batch", err);
    } finally {
      setIsLoading(false);
    }
  };

  if (isLoading) {
    return <div className="loader-container" style={{marginTop: '100px'}}><div className="spinner"></div></div>;
  }

  // Session complete
  if (currentIndex >= priorityCards.length) {
    return (
      <div className="upload-container">
        <div style={{ position: 'relative', marginBottom: '1rem' }}>
          <CheckCircle2 size={64} color="var(--accent-cyan)" />
          <div style={{ position: 'absolute', top: -10, right: -10 }}>
            <Zap size={24} color="#ffd32a" fill="#ffd32a" />
          </div>
        </div>
        <h1 className="upload-title text-gradient">Knowledge Strengthened</h1>
        <p className="upload-subtitle text-secondary">
          You've focused on these {priorityCards.length} high-priority concepts. Your adaptive priority list is updating...
        </p>
        <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem' }}>
          <button className="btn btn-secondary" onClick={onFinish}>
            Back to Dashboard
          </button>
          <button className="btn btn-primary" onClick={handleStartAnother}>
            Study Another Batch
          </button>
        </div>
      </div>
    );
  }

  const currentCard = priorityCards[currentIndex];
  // Calculate progress
  const progressPercent = ((currentIndex) / priorityCards.length) * 100;

  return (
    <div className="review-container">
      
      <div style={{ width: '100%', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          <span>Concept {currentIndex + 1} of {priorityCards.length}</span>
          <span>{progressPercent.toFixed(0)}% Strengthened</span>
        </div>
        <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px' }}>
          <div style={{ width: `${progressPercent}%`, height: '100%', background: 'var(--accent-gradient)', borderRadius: '2px', transition: 'width 0.3s ease' }}></div>
        </div>
      </div>

      <div className="scene" onClick={handleFlip}>
        <div className={`flashcard ${isFlipped ? 'is-flipped' : ''}`}>
          
          {/* Front */}
          <div className="card-face card-front glass-panel">
            <div className="card-content">{currentCard.question}</div>
            {!isFlipped && <div className="card-hint">Click space to flip</div>}
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

      <div className={`grading-actions ${isFlipped ? 'visible' : ''}`}>
        <p className="text-secondary grading-label">How easy was it to recall?</p>
        <div className="grade-buttons">
          <button className="grade-btn" data-grade="0" onClick={() => handleGrade(0)}>
            <span className="grade-num">0</span>
            <span className="grade-label">Blackout</span>
          </button>
          <button className="grade-btn" data-grade="1" onClick={() => handleGrade(1)}>
            <span className="grade-num">1</span>
            <span className="grade-label">Failed</span>
          </button>
          <button className="grade-btn" data-grade="2" onClick={() => handleGrade(2)}>
            <span className="grade-num">2</span>
            <span className="grade-label">Hard</span>
          </button>
          <button className="grade-btn" data-grade="3" onClick={() => handleGrade(3)}>
            <span className="grade-num">3</span>
            <span className="grade-label">Good</span>
          </button>
          <button className="grade-btn" data-grade="4" onClick={() => handleGrade(4)}>
            <span className="grade-num">4</span>
            <span className="grade-label">Easy</span>
          </button>
          <button className="grade-btn" data-grade="5" onClick={() => handleGrade(5)}>
            <span className="grade-num">5</span>
            <span className="grade-label">Perfect</span>
          </button>
        </div>
      </div>

    </div>
  );
};

export default ReviewSession;
