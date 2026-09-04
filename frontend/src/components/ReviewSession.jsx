import React, { useState, useEffect } from 'react';
import { listFlashcards, submitReview, deleteVocabEntry, deleteFlashcard, flashcardImageUrl } from '../api';
import { CheckCircle2, Zap, RotateCcw, GraduationCap, ArrowRight, Trash2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

// A session is a block of words you sit down with, not a handful. Anything
// smaller stops before repetition has a chance to do its work.
const SESSION_SIZE = 50;

// SM-2 treats a grade below 3 as a failed recall, so that is also the line
// for "see this one again before the session ends".
const PASS_GRADE = 3;

// Cards you have never been graded on. Meeting a word for the first time as
// a blank test teaches nothing, so these get shown with their meaning first.
const isUnseen = (card) => card.repetitions === 0;

// One introduction per word, not per card: a vocabulary entry produces both a
// recognition and a production card, and reading the same meaning twice in a
// row is filler. The recognition card leads, since it shows the word itself.
const introCards = (cards) => {
  const byEntry = new Map();
  const intro = [];

  cards.filter(isUnseen).forEach((card) => {
    if (!card.vocab_entry_id) {
      intro.push(card);
      return;
    }
    const seen = byEntry.get(card.vocab_entry_id);
    if (!seen) {
      byEntry.set(card.vocab_entry_id, card);
      intro.push(card);
    } else if (card.direction === 'recognition' && seen.direction !== 'recognition') {
      byEntry.set(card.vocab_entry_id, card);
      intro[intro.indexOf(seen)] = card;
    }
  });

  return intro;
};

const shuffle = (cards) => {
  const out = [...cards];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
};

const ReviewSession = ({ onFinish, cardType = null, lang = null }) => {
  // The words drawn for this session, and the subset being shown right now.
  const [sessionCards, setSessionCards] = useState([]);
  const [queue, setQueue] = useState([]);
  // 'learn' introduces the words you have never seen; 'quiz' grades them.
  const [phase, setPhase] = useState('learn');
  const [learnCards, setLearnCards] = useState([]);
  const [learnIndex, setLearnIndex] = useState(0);
  const [round, setRound] = useState(1);
  const [missed, setMissed] = useState([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  const startSession = async () => {
    setIsLoading(true);
    try {
      const res = await listFlashcards(SESSION_SIZE, cardType, lang);
      const cards = res.flashcards || [];
      const intro = introCards(cards);

      setSessionCards(cards);
      setQueue(cards);
      setLearnCards(intro);
      setLearnIndex(0);
      setPhase(intro.length > 0 ? 'learn' : 'quiz');
      setRound(1);
      setMissed([]);
      setCurrentIndex(0);
      setIsFlipped(false);
    } catch (err) {
      console.error('Failed to fetch session cards', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { startSession(); }, [cardType, lang]);

  const handleFlip = () => {
    if (!isFlipped) setIsFlipped(true);
  };

  const handleGrade = async (quality) => {
    const currentCard = queue[currentIndex];

    // Only the first pass schedules. Repeat rounds are drill: grading the same
    // word three times in ten minutes would tell SM-2 you have seen it three
    // times on three separate days, and collapse its interval for no reason.
    if (round === 1) {
      try {
        await submitReview(currentCard.id, quality);
      } catch (err) {
        console.error('Failed to submit review', err);
      }
    }

    if (quality < PASS_GRADE) {
      setMissed((prev) => [...prev, currentCard]);
    }

    setIsFlipped(false);
    setTimeout(() => setCurrentIndex((prev) => prev + 1), 200);
  };

  // Throwing a word out mid-session. A vocabulary word owns both of its
  // cards, so removing it takes the recognition and production card together —
  // being asked the other direction of a word you just discarded is exactly
  // the annoyance this button exists to remove.
  const removeWord = async (card) => {
    const belongsToCard = (other) =>
      card.vocab_entry_id
        ? other.vocab_entry_id === card.vocab_entry_id
        : other.id === card.id;

    try {
      if (card.vocab_entry_id) await deleteVocabEntry(card.vocab_entry_id);
      else await deleteFlashcard(card.id);
    } catch (err) {
      console.error('Failed to remove the word', err);
      return;
    }

    const keep = (list) => list.filter((c) => !belongsToCard(c));

    setSessionCards(keep);
    setMissed(keep);
    setIsFlipped(false);

    // The quiz queue was seeded from the same session batch, so a word
    // discarded during the learn phase must be pulled out of it too —
    // otherwise it still turns up once practising starts, pointing at cards
    // that no longer exist server-side.
    setQueue(keep);

    if (phase === 'learn') {
      const remaining = keep(learnCards);
      setLearnCards(remaining);
      // The next word slides into this position; past the end, start practising.
      if (learnIndex >= remaining.length) setPhase('quiz');
      return;
    }

    // The other direction of the same word may sit behind the cursor, so the
    // index moves back by however many cards vanished before it.
    const removedBefore = queue.slice(0, currentIndex).filter(belongsToCard).length;
    setCurrentIndex(currentIndex - removedBefore);
  };

  const startRound = (cards) => {
    setQueue(shuffle(cards));
    setMissed([]);
    setCurrentIndex(0);
    setIsFlipped(false);
    setRound((prev) => prev + 1);
  };

  if (isLoading) {
    return <div className="loader-container" style={{marginTop: '100px'}}><div className="spinner"></div></div>;
  }

  if (sessionCards.length === 0) {
    return (
      <div className="upload-container">
        <h1 className="upload-title text-gradient">Nothing to study</h1>
        <p className="upload-subtitle text-secondary">
          Approve some cards in Quality Control, or load more words into a deck.
        </p>
        <button className="btn btn-secondary" onClick={onFinish} style={{ marginTop: '2rem' }}>
          Back to Dashboard
        </button>
      </div>
    );
  }

  // Learning phase: word and meaning side by side, nothing to grade yet.
  if (phase === 'learn') {
    const card = learnCards[learnIndex];
    const learnPercent = (learnIndex / learnCards.length) * 100;

    const nextWord = () => {
      if (learnIndex + 1 >= learnCards.length) setPhase('quiz');
      else setLearnIndex((prev) => prev + 1);
    };

    return (
      <div className="review-container">
        <div style={{ width: '100%', marginBottom: '2rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
            <span>
              <strong style={{ color: 'var(--accent-cyan)' }}>
                <GraduationCap size={16} style={{ verticalAlign: 'text-bottom', marginRight: '4px' }} />
                First look ·{' '}
              </strong>
              New word {learnIndex + 1} of {learnCards.length}
            </span>
            <span>{sessionCards.length} words to practise after this</span>
          </div>
          <div style={{ width: '100%', height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px' }}>
            <div style={{ width: `${learnPercent}%`, height: '100%', background: 'var(--accent-gradient)', borderRadius: '2px', transition: 'width 0.3s ease' }}></div>
          </div>
        </div>

        <div className="glass-panel learn-card">
          <div className="learn-word">{card.question}</div>
          <div className="learn-divider" />
          <div className="markdown-content">
            {card.has_image && (
              <img className="card-answer-image" src={flashcardImageUrl(card.id)} alt="" />
            )}
            <ReactMarkdown>{card.answer}</ReactMarkdown>
          </div>
        </div>

        <div className="learn-actions">
          <button className="btn btn-primary" onClick={nextWord}>
            {learnIndex + 1 >= learnCards.length ? 'Start practising' : 'Next word'}
            <ArrowRight size={18} />
          </button>
          <button className="btn btn-secondary" onClick={() => setPhase('quiz')}>
            Skip the introduction
          </button>
          <button className="btn-remove-word" onClick={() => removeWord(card)}>
            <Trash2 size={16} /> I don't need this word
          </button>
        </div>
      </div>
    );
  }

  // End of a round: repeat what did not stick, then close the session.
  if (currentIndex >= queue.length) {
    const stillShaky = missed.length;

    return (
      <div className="upload-container">
        <div style={{ position: 'relative', marginBottom: '1rem' }}>
          {stillShaky > 0
            ? <RotateCcw size={64} color="var(--accent-cyan)" />
            : <CheckCircle2 size={64} color="var(--accent-cyan)" />}
          <div style={{ position: 'absolute', top: -10, right: -10 }}>
            <Zap size={24} color="#ffd32a" fill="#ffd32a" />
          </div>
        </div>

        <h1 className="upload-title text-gradient">
          {stillShaky > 0 ? 'One more pass' : 'Knowledge Strengthened'}
        </h1>

        <p className="upload-subtitle text-secondary">
          {stillShaky > 0
            ? `${stillShaky} of the ${queue.length} words you just went through need another look.`
            : `You went through ${sessionCards.length} words in ${round} round${round !== 1 ? 's' : ''}. Your adaptive priority list is updating...`}
        </p>

        {round > 1 && (
          <p className="text-secondary" style={{ fontSize: '0.8rem', marginTop: '-0.5rem' }}>
            Repeat rounds drill only — your review schedule was set on the first pass.
          </p>
        )}

        <div style={{ display: 'flex', gap: '1rem', marginTop: '2rem', flexWrap: 'wrap', justifyContent: 'center' }}>
          {stillShaky > 0 && (
            <button className="btn btn-primary" onClick={() => startRound(missed)}>
              <RotateCcw size={18} /> Repeat {stillShaky} word{stillShaky !== 1 ? 's' : ''}
            </button>
          )}
          <button className="btn btn-secondary" onClick={() => startRound(sessionCards)}>
            Repeat all {sessionCards.length}
          </button>
          <button className={`btn ${stillShaky > 0 ? 'btn-secondary' : 'btn-primary'}`} onClick={startSession}>
            Study another {SESSION_SIZE}
          </button>
          <button className="btn btn-secondary" onClick={onFinish}>
            Back to Dashboard
          </button>
        </div>
      </div>
    );
  }

  const currentCard = queue[currentIndex];
  const progressPercent = (currentIndex / queue.length) * 100;

  return (
    <div className="review-container">
      
      <div style={{ width: '100%', marginBottom: '2rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', color: 'var(--text-secondary)', fontSize: '0.9rem' }}>
          <span>
            {round > 1 && <strong style={{ color: 'var(--accent-cyan)' }}>Repeat {round - 1} · </strong>}
            Word {currentIndex + 1} of {queue.length}
          </span>
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
              {currentCard.has_image && (
                <img className="card-answer-image" src={flashcardImageUrl(currentCard.id)} alt="" />
              )}
              <ReactMarkdown>{currentCard.answer}</ReactMarkdown>
            </div>
          </div>
          
        </div>
      </div>

      <div className="card-tools">
        <button className="btn-remove-word" onClick={() => removeWord(currentCard)}>
          <Trash2 size={16} /> Remove this word from the deck
        </button>
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
