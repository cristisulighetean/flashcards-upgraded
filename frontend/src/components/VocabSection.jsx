import React, { useEffect, useState } from 'react';
import { Sparkles, Trash2, Search, BookOpen, Layers, ShieldCheck } from 'lucide-react';
import {
  addWords,
  listVocab,
  deleteVocabEntry,
  getVocabStats,
  getDeckBatches,
  loadNextVocabBatch,
} from '../api';
import VocabQualityControl from './VocabQualityControl';

// How many words the browse list shows at once. A deck holds thousands, but
// this list renders a full card per word — search narrows it down instead of
// paging through the whole thing.
const WORD_LIST_PAGE = 10;

// A deck is the language you are learning, and each word is explained in that
// same language — the way the bundled word lists in data/ do it. Definitions,
// not translations.
const DECKS = [
  { lang: 'en', label: 'English', gloss: 'en', flag: '🇬🇧', placeholder: 'ubiquitous\nresilient\nto thrive' },
  { lang: 'ro', label: 'Romanian', gloss: 'ro', flag: '🇷🇴', placeholder: 'cumpătat\nzăpadă\na cumpăra' },
];

const VocabSection = ({ onStudyVocab, initialLang = 'en' }) => {
  const [lang, setLang] = useState(initialLang);
  const [input, setInput] = useState('');
  const [entries, setEntries] = useState([]);
  const [stats, setStats] = useState({});
  // Progress through the word list shipped with the app, per deck.
  const [batches, setBatches] = useState({});
  const [isLoadingBatch, setIsLoadingBatch] = useState(false);
  const [search, setSearch] = useState('');
  const [isAdding, setIsAdding] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  // Quality Control gates study: a deck with pending words opens here instead.
  const [qcOpen, setQcOpen] = useState(false);

  const deck = DECKS.find((d) => d.lang === lang) || DECKS[0];

  const refreshStats = async () => {
    try {
      const res = await getVocabStats();
      const byLang = {};
      (res.decks || []).forEach((d) => { byLang[d.lang] = d; });
      setStats(byLang);
      return byLang;
    } catch {
      // Counts are decorative; a failure here shouldn't blank the page.
      return {};
    }
  };

  const refresh = async (term, deckLang) => {
    setIsLoading(true);
    try {
      const res = await listVocab(term, deckLang, { limit: WORD_LIST_PAGE });
      setEntries(res.entries || []);
      setError('');
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const refreshBatches = async () => {
    try {
      const res = await getDeckBatches();
      const byLang = {};
      (res.decks || []).forEach((d) => { byLang[d.lang] = d; });
      setBatches(byLang);
    } catch {
      // The word list panel is optional; hide it rather than break the page.
    }
  };

  const handleLoadNextBatch = async () => {
    if (isLoadingBatch) return;
    setIsLoadingBatch(true);
    try {
      const res = await loadNextVocabBatch(lang);
      setNotice(`Loaded batch ${res.batch}: ${res.entries_added} new words, ${res.cards_created} cards.`);
      setError('');
      await Promise.all([refresh(search, lang), refreshStats(), refreshBatches()]);
    } catch (err) {
      setError(err.message);
    } finally {
      setIsLoadingBatch(false);
    }
  };

  useEffect(() => { refreshStats(); refreshBatches(); }, []);

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
    setQcOpen(false);
  };

  const handleQcDone = async () => {
    setQcOpen(false);
    const [, freshStats] = await Promise.all([
      refresh(search, lang),
      refreshStats(),
      refreshBatches(),
    ]);
    if ((freshStats[lang]?.cards_accepted ?? 0) > 0) onStudyVocab(lang);
  };

  const deckStats = stats[lang] || { entries: 0, cards_accepted: 0, cards_pending: 0 };
  const deckBatch = batches[lang];
  const batchPercent = deckBatch
    ? Math.min(100, Math.round((deckBatch.words_loaded / deckBatch.words_available) * 100))
    : 0;

  return (
    <div>
      <div className="dashboard-header">
        <div>
          <h1 className="text-gradient">Vocabulary</h1>
          <p className="text-secondary">
            Learning <strong>{deck.label}</strong> words, each defined in{' '}
            {deck.label}.
          </p>
        </div>
        <div className="dashboard-actions">
          {deckStats.cards_pending > 0 && (
            <button
              className="btn btn-secondary"
              onClick={() => setQcOpen(true)}
              style={{ borderColor: 'var(--accent-cyan)', color: 'var(--accent-cyan)' }}
            >
              <ShieldCheck size={18} /> Quality Control ({deckStats.cards_pending})
            </button>
          )}
          <button
            className="btn btn-primary"
            onClick={() => onStudyVocab(lang)}
            disabled={deckStats.cards_accepted === 0 || deckStats.cards_pending > 0}
            title={
              deckStats.cards_pending > 0
                ? 'Go through Quality Control first — read each new word and remove what you don\'t need'
                : deckStats.cards_accepted === 0
                  ? 'Approve some words in Quality Control first'
                  : undefined
            }
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

      {/* Quality Control: every new word is read once and kept or thrown out
          here before Study unlocks — a stray word from the whole file is
          removed now, not discovered mid-session. */}
      {qcOpen ? (
        <VocabQualityControl
          lang={lang}
          label={deck.label}
          onDone={handleQcDone}
          onExit={() => setQcOpen(false)}
        />
      ) : (
        <>
      {deckStats.cards_pending > 0 && (
        <div className="glass-panel qc-banner">
          <span>
            <ShieldCheck size={16} style={{ verticalAlign: 'text-bottom', marginRight: '6px', color: 'var(--accent-cyan)' }} />
            {deckStats.cards_pending} new {deck.label} word{deckStats.cards_pending !== 1 ? 's' : ''} waiting —
            read through them and remove what you don't need before studying.
          </span>
          <button className="btn btn-primary" onClick={() => setQcOpen(true)}>
            Start Quality Control
          </button>
        </div>
      )}

      {/* Bundled word list: loaded a batch at a time, commonest words first. */}
      {deckBatch && (
        <div className="glass-panel batch-panel">
          <div>
            <strong>
              {deckBatch.words_loaded.toLocaleString()} of{' '}
              {deckBatch.words_available.toLocaleString()} {deck.label} words loaded
            </strong>
            <div className="text-secondary vocab-hint">
              Batch {deckBatch.batches_loaded} of {deckBatch.batches_total} · {deckBatch.batch_size} words each
              {deckBatch.words_in_catalog > deckBatch.words_loaded && (
                <> · {deckBatch.words_in_catalog.toLocaleString()} already in the database, waiting to be activated</>
              )}
            </div>
            <div className="batch-meter">
              <div className="batch-meter-fill" style={{ width: `${batchPercent}%` }} />
            </div>
            {deckBatch.next_batch_preview.length > 0 && (
              <div className="text-secondary batch-preview">
                Next up: {deckBatch.next_batch_preview.join(', ')} ...
              </div>
            )}
          </div>
          <button
            className="btn btn-secondary"
            onClick={handleLoadNextBatch}
            disabled={isLoadingBatch || !deckBatch.next_batch}
            title={deckBatch.next_batch ? undefined : 'The whole word list is loaded'}
          >
            <Layers size={18} />
            {isLoadingBatch
              ? 'Loading...'
              : deckBatch.next_batch
                ? `Load next ${deckBatch.batch_size}`
                : 'All loaded'}
          </button>
        </div>
      )}

      {/* Quick add */}
      <div className="glass-panel vocab-add">
        <div className="vocab-add-row">
          <span className="deck-badge">
            {deck.flag} {deck.label} → {deck.label} definition
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

      {/* Word list — capped to WORD_LIST_PAGE; search to find a specific word
          rather than paging through a deck that can hold thousands. */}
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

      {!isLoading && !search && entries.length >= WORD_LIST_PAGE && deckStats.entries > WORD_LIST_PAGE && (
        <div className="text-secondary vocab-hint" style={{ marginBottom: '0.75rem' }}>
          Showing {entries.length} of {deckStats.entries.toLocaleString()} words — search to find a specific one.
        </div>
      )}

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
        </>
      )}
    </div>
  );
};

export default VocabSection;
