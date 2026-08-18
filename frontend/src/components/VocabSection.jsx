import React, { useEffect, useState } from 'react';
import { Sparkles, Trash2, ArrowLeftRight, Search, BookOpen } from 'lucide-react';
import { addWords, listVocab, deleteVocabEntry } from '../api';

const VocabSection = ({ onStudyVocab }) => {
  const [input, setInput] = useState('');
  const [sourceLang, setSourceLang] = useState('ro');
  const [entries, setEntries] = useState([]);
  const [search, setSearch] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const targetLang = sourceLang === 'ro' ? 'en' : 'ro';

  const refresh = async (term = '') => {
    try {
      const res = await listVocab(term);
      setEntries(res.entries || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  // Debounced: also covers the initial load, since search starts empty.
  useEffect(() => {
    const t = setTimeout(() => refresh(search), search ? 300 : 0);
    return () => clearTimeout(t);
  }, [search]);

  // One word per line, or several separated by commas.
  const parseTerms = (raw) =>
    raw.split(/[\n,]/).map((t) => t.trim()).filter(Boolean);

  const terms = parseTerms(input);

  const handleAdd = async () => {
    if (terms.length === 0 || isAdding) return;
    setError('');
    setNotice('');
    setIsAdding(true);
    try {
      const res = await addWords(terms, { sourceLang, targetLang, enrich: true });
      const bits = [];
      if (res.added) {
        bits.push(`${res.added} word${res.added !== 1 ? 's' : ''} added · ${res.cards_created} cards awaiting review`);
      }
      if (res.skipped_duplicates.length) {
        bits.push(`already known: ${res.skipped_duplicates.join(', ')}`);
      }
      setNotice(bits.join(' · ') || 'Nothing added.');
      setInput('');
      await refresh(search);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsAdding(false);
    }
  };

  const handleDelete = async (id) => {
    try {
      await deleteVocabEntry(id);
      setEntries((prev) => prev.filter((e) => e.id !== id));
    } catch (err) {
      setError(err.message);
    }
  };

  const handleKeyDown = (e) => {
    // Cmd/Ctrl+Enter submits without leaving the keyboard.
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleAdd();
  };

  return (
    <div>
      <div className="dashboard-header">
        <div>
          <h1 className="text-gradient">Vocabulary</h1>
          <p className="text-secondary">
            Type a word — the AI fills in the translation, part of speech and an example.
          </p>
        </div>
        <div className="dashboard-actions">
          <button className="btn btn-primary" onClick={onStudyVocab}>
            <BookOpen size={18} /> Study Vocabulary
          </button>
        </div>
      </div>

      {/* Quick add */}
      <div className="glass-panel vocab-add">
        <div className="vocab-add-row">
          <button
            className="btn btn-secondary lang-toggle"
            onClick={() => setSourceLang(sourceLang === 'ro' ? 'en' : 'ro')}
            title="Swap language direction"
          >
            {sourceLang.toUpperCase()} <ArrowLeftRight size={14} /> {targetLang.toUpperCase()}
          </button>
          <span className="text-secondary vocab-hint">
            One word per line, or separate with commas
          </span>
        </div>

        <textarea
          className="vocab-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={sourceLang === 'ro' ? 'cumpătat\nzăpadă\na cumpăra' : 'temperate\nsnow\nto buy'}
          rows={3}
          disabled={isAdding}
        />

        <div className="vocab-add-actions">
          <span className="text-secondary vocab-hint">
            {terms.length > 0
              ? `${terms.length} word${terms.length !== 1 ? 's' : ''} ready`
              : 'Cmd/Ctrl + Enter to add'}
          </span>
          <button
            className="btn btn-primary"
            onClick={handleAdd}
            disabled={terms.length === 0 || isAdding}
          >
            <Sparkles size={16} />
            {isAdding ? 'Looking up...' : 'Add words'}
          </button>
        </div>
      </div>

      {notice && <div className="vocab-notice">{notice}</div>}
      {error && <div className="vocab-error">{error}</div>}

      {/* Word list */}
      <div className="library-header">
        <h3 style={{ fontFamily: 'Outfit' }}>Your Words</h3>
        <div className="vocab-search">
          <Search size={14} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search"
            aria-label="Search vocabulary"
          />
        </div>
      </div>

      {isLoading ? (
        <div className="loader-container"><div className="spinner"></div></div>
      ) : entries.length === 0 ? (
        <div className="vocab-empty text-secondary">
          {search ? `No words match "${search}".` : 'No words yet. Add a few above to get started.'}
        </div>
      ) : (
        <div className="vocab-list">
          {entries.map((entry) => (
            <div key={entry.id} className="vocab-item glass-panel">
              <div className="vocab-item-main">
                <div className="vocab-term">
                  {entry.term}
                  {entry.part_of_speech && (
                    <span className="vocab-pos">{entry.part_of_speech}</span>
                  )}
                </div>
                <div className="vocab-translation">{entry.translation}</div>
                {entry.example && (
                  <div className="vocab-example text-secondary">
                    {entry.example}
                    {entry.example_translation && <em> — {entry.example_translation}</em>}
                  </div>
                )}
              </div>
              <button
                className="btn btn-secondary vocab-delete"
                onClick={() => handleDelete(entry.id)}
                title="Delete word and its cards"
                aria-label={`Delete ${entry.term}`}
              >
                <Trash2 size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default VocabSection;
