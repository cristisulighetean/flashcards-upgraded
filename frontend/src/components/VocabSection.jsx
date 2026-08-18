import React, { useEffect, useState } from 'react';
import { Sparkles, Trash2, Search, BookOpen } from 'lucide-react';
import { addWords, listVocab, deleteVocabEntry, getVocabStats } from '../api';

// A deck is the language you are learning; the other language supplies the gloss.
const DECKS = [
  { lang: 'en', label: 'English', gloss: 'ro', flag: '🇬🇧', placeholder: 'ubiquitous\nresilient\nto thrive' },
  { lang: 'ro', label: 'Romanian', gloss: 'en', flag: '🇷🇴', placeholder: 'cumpătat\nzăpadă\na cumpăra' },
];

const VocabSection = ({ onStudyVocab, initialLang = 'en' }) => {
  const [lang, setLang] = useState(initialLang);
  const [input, setInput] = useState('');
  const [entries, setEntries] = useState([]);
  const [stats, setStats] = useState({});
  const [search, setSearch] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const deck = DECKS.find((d) => d.lang === lang) || DECKS[0];

  const refreshStats = async () => {
    try {
      const res = await getVocabStats();
      const byLang = {};
      (res.decks || []).forEach((d) => { byLang[d.lang] = d; });
      setStats(byLang);
    } catch {
      // Counts are decorative; a failure here shouldn't blank the page.
    }
  };

  const refresh = async (term, deckLang) => {
    setIsLoading(true);
    try {
      const res = await listVocab(term, deckLang);
      setEntries(res.entries || []);
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => { refreshStats(); }, []);

  // Debounced on search; immediate when switching decks.
  useEffect(() => {
    const t = setTimeout(() => refresh(search, lang), search ? 300 : 0);
    return () => clearTimeout(t);
  }, [search, lang]);

  const parseTerms = (raw) => raw.split(/[\n,]/).map((t) => t.trim()).filter(Boolean);
  const terms = parseTerms(input);

  const handleAdd = async () => {
    if (terms.length === 0 || isAdding) return;
    setError('');
    setNotice('');
    setIsAdding(true);
    try {
      const res = await addWords(terms, {
        sourceLang: deck.lang,
        targetLang: deck.gloss,
        enrich: true,
      });
      const bits = [];
      if (res.added) {
        bits.push(`${res.added} word${res.added !== 1 ? 's' : ''} added · ${res.cards_created} cards awaiting review`);
      }
      if (res.skipped_duplicates.length) {
        bits.push(`already known: ${res.skipped_duplicates.join(', ')}`);
      }
      setNotice(bits.join(' · ') || 'Nothing added.');
      setInput('');
      await Promise.all([refresh(search, lang), refreshStats()]);
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
      refreshStats();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleKeyDown = (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') handleAdd();
  };

  const switchDeck = (nextLang) => {
    if (nextLang === lang) return;
    setLang(nextLang);
    setNotice('');
    setError('');
    setInput('');
  };

  const deckStats = stats[lang] || { entries: 0, cards_accepted: 0, cards_pending: 0 };

  return (
    <div>
      <div className="dashboard-header">
        <div>
          <h1 className="text-gradient">Vocabulary</h1>
          <p className="text-secondary">
            Learning <strong>{deck.label}</strong> words, explained in{' '}
            {DECKS.find((d) => d.lang === deck.gloss)?.label}.
          </p>
        </div>
        <div className="dashboard-actions">
          <button
            className="btn btn-primary"
            onClick={() => onStudyVocab(lang)}
            disabled={deckStats.cards_accepted === 0}
            title={deckStats.cards_accepted === 0 ? 'Approve some cards in Quality Control first' : undefined}
          >
            <BookOpen size={18} /> Study {deck.label}
          </button>
        </div>
      </div>

      {/* Deck tabs */}
      <div className="deck-tabs" role="tablist">
        {DECKS.map((d) => {
          const s = stats[d.lang] || { entries: 0 };
          return (
            <button
              key={d.lang}
              role="tab"
              aria-selected={d.lang === lang}
              className={`deck-tab ${d.lang === lang ? 'active' : ''}`}
              onClick={() => switchDeck(d.lang)}
            >
              <span className="deck-flag">{d.flag}</span>
              <span className="deck-name">{d.label}</span>
              <span className="deck-count">{s.entries}</span>
            </button>
          );
        })}
      </div>

      {deckStats.cards_pending > 0 && (
        <div className="deck-pending-hint text-secondary">
          {deckStats.cards_pending} {deck.label} card{deckStats.cards_pending !== 1 ? 's' : ''} waiting in Quality Control.
        </div>
      )}

      {/* Quick add */}
      <div className="glass-panel vocab-add">
        <div className="vocab-add-row">
          <span className="deck-badge">
            {deck.flag} {deck.label} → {DECKS.find((d) => d.lang === deck.gloss)?.label}
          </span>
          <span className="text-secondary vocab-hint">
            One word per line, or separate with commas
          </span>
        </div>

        <textarea
          className="vocab-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={deck.placeholder}
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
            {isAdding ? 'Looking up...' : `Add to ${deck.label}`}
          </button>
        </div>
      </div>

      {notice && <div className="vocab-notice">{notice}</div>}
      {error && <div className="vocab-error">{error}</div>}

      {/* Word list */}
      <div className="library-header">
        <h3 style={{ fontFamily: 'Outfit' }}>{deck.label} Words</h3>
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
          {search
            ? `No ${deck.label} words match "${search}".`
            : `No ${deck.label} words yet. Add a few above to get started.`}
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
