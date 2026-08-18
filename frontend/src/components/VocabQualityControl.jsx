import React, { useEffect, useState } from 'react';
import { ShieldCheck, CheckCircle2, Trash2, ArrowLeft } from 'lucide-react';
import { listVocab, acceptVocabEntry, deleteVocabEntry } from '../api';

// Quality Control works word by word: a vocabulary word owns two cards
// (recognition and production) that say the same thing in two directions, so
// approving or discarding is one decision per word, not one per card. Every
// seeded word passes through here — read once, keep or throw out — before it
// can enter a study session.
const VocabQualityControl = ({ lang, label, onDone, onExit }) => {
  const [entries, setEntries] = useState([]);
  const [index, setIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isActioning, setIsActioning] = useState(false);
  const [error, setError] = useState('');
  const [acceptedCount, setAcceptedCount] = useState(0);
  const [discardedCount, setDiscardedCount] = useState(0);

  const fetchPending = async () => {
    setIsLoading(true);
    try {
      const res = await listVocab('', lang, { limit: 500, pending: true });
      setEntries(res.entries || []);
      setIndex(0);
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { fetchPending(); }, [lang]);

  const total = acceptedCount + discardedCount + entries.length;
  const current = entries[index];

  const advance = (removedEntry) => {
    setEntries((prev) => prev.filter((e) => e.id !== removedEntry.id));
  };

  const handleAccept = async () => {
    if (!current || isActioning) return;
    setIsActioning(true);
    try {
      await acceptVocabEntry(current.id);
      setAcceptedCount((c) => c + 1);
      advance(current);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsActioning(false);
    }
  };

  const handleDiscard = async () => {
    if (!current || isActioning) return;
    setIsActioning(true);
    try {
      await deleteVocabEntry(current.id);
      setDiscardedCount((c) => c + 1);
      advance(current);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsActioning(false);
    }
  };

  // Keyboard shortcuts, matching the document Quality Control screen.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'ArrowRight' || e.key === 'a') handleAccept();
      if (e.key === 'ArrowLeft' || e.key === 'd') handleDiscard();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [current, isActioning]);

  if (isLoading) {
    return <div className="loader-container"><div className="spinner"></div></div>;
  }

  if (!current) {
    return (
      <div className="glass-panel qc-panel qc-done">
        <CheckCircle2 size={40} color="var(--accent-cyan)" />
        <h3 style={{ fontFamily: 'Outfit' }}>{label} Quality Control clear</h3>
        <p className="text-secondary">
          {total > 0
            ? `Kept ${acceptedCount}, threw out ${discardedCount}. These words are ready to study.`
            : `No ${label} words are waiting.`}
        </p>
        <button className="btn btn-primary" onClick={onDone}>
          {total > 0 ? `Study ${label}` : `Back to ${label}`}
        </button>
      </div>
    );
  }

  const progressPercent = total > 0 ? ((acceptedCount + discardedCount) / total) * 100 : 0;

  return (
    <div className="glass-panel qc-panel">
      <div className="qc-header">
        <span>
          <ShieldCheck size={16} style={{ verticalAlign: 'text-bottom', marginRight: '4px' }} />
          <strong>{label} Quality Control</strong> · {entries.length} word{entries.length !== 1 ? 's' : ''} left
        </span>
        <button className="btn-remove-word" onClick={onExit}>
          <ArrowLeft size={14} /> Back to Vocabulary
        </button>
      </div>

      <div className="batch-meter">
        <div className="batch-meter-fill" style={{ width: `${progressPercent}%` }} />
      </div>

      {error && <div className="vocab-error">{error}</div>}

      <div className="qc-word">
        <div className="learn-word">{current.term}</div>
        {current.part_of_speech && <span className="vocab-pos">{current.part_of_speech}</span>}
        <div className="learn-divider" />
        <div className="vocab-translation">{current.translation}</div>
        {current.example && (
          <div className="vocab-example text-secondary">
            {current.example}
            {current.example_translation && <em> — {current.example_translation}</em>}
          </div>
        )}
      </div>

      <div className="qc-actions">
        <button className="btn btn-secondary qc-discard" onClick={handleDiscard} disabled={isActioning}>
          <Trash2 size={18} /> Don't need this
        </button>
        <button className="btn btn-primary" onClick={handleAccept} disabled={isActioning}>
          <CheckCircle2 size={18} /> Keep it
        </button>
      </div>
    </div>
  );
};

export default VocabQualityControl;
