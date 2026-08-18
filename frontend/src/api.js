const API_BASE = '/flashcards/api/v1';

/**
 * Handles all backend interaction.
 */

// 1. Upload Document
export const uploadFile = async (file) => {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/documents/upload`, {
    method: 'POST',
    body: formData,
  });
  
  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to upload document');
  }
  return res.json();
};

// 2. Generate Flashcards
export const generateFlashcards = async (documentId, numCards = null) => {
  const payload = { document_id: documentId };
  if (numCards) payload.num_cards = numCards;

  const res = await fetch(`${API_BASE}/flashcards/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (res.status === 429) {
    throw new Error('AI Rate Limit Reached: The AI is currently under heavy load. Please wait about a minute and try again.');
  }

  if (!res.ok) {
    const error = await res.json();
    throw new Error(error.detail || 'Failed to generate flashcards');
  }
  return res.json();
};

// 3. List Flashcards (Adaptive Priority Sorted)
export const listFlashcards = async (limit = 100, cardType = null, lang = null) => {
  const url = new URL(`${API_BASE}/flashcards/`, window.location.origin);
  url.searchParams.append('limit', limit);
  if (cardType) url.searchParams.append('card_type', cardType);
  if (lang) url.searchParams.append('lang', lang);
  
  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch flashcards');
  return res.json();
};

// 4. Submit Review (SM-2)
export const submitReview = async (flashcardId, quality) => {
  const res = await fetch(`${API_BASE}/reviews/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      flashcard_id: flashcardId,
      quality: quality
    }),
  });

  if (!res.ok) throw new Error('Failed to submit review');
  return res.json();
};

// 5. Delete Flashcard
export const deleteFlashcard = async (flashcardId) => {
  const res = await fetch(`${API_BASE}/flashcards/${flashcardId}`, {
    method: 'DELETE',
  });

  if (!res.ok) throw new Error('Failed to delete flashcard');
  return true;
};

// 6. List Pending Flashcards (quality control queue)
export const listPendingFlashcards = async (cardType = null) => {
  const url = new URL(`${API_BASE}/flashcards/`, window.location.origin);
  url.searchParams.append('card_status', 'pending');
  if (cardType) url.searchParams.append('card_type', cardType);

  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch pending flashcards');
  return res.json();
};

// 7. Accept a Flashcard (move from pending to collection)
export const acceptFlashcard = async (flashcardId) => {
  const res = await fetch(`${API_BASE}/flashcards/${flashcardId}/accept`, {
    method: 'PATCH',
  });

  if (!res.ok) throw new Error('Failed to accept flashcard');
  return res.json();
};

// --- Vocabulary ---

// 8. Add words (AI fills translation, part of speech and an example)
export const addWords = async (terms, { sourceLang = 'ro', targetLang = 'en', enrich = true } = {}) => {
  const res = await fetch(`${API_BASE}/vocab/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      terms,
      source_lang: sourceLang,
      target_lang: targetLang,
      enrich,
    }),
  });

  if (res.status === 429) {
    throw new Error('AI Rate Limit Reached: please wait about a minute and try again.');
  }
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to add words');
  }
  return res.json();
};

// 9. List vocabulary entries. Capped well below deck size by default — this
// renders one card per word, so a 2,000-word deck should not mean 2,000 DOM
// nodes; search narrows down to a specific word instead of paging through all.
export const listVocab = async (search = '', lang = null, { limit = 30, pending = false } = {}) => {
  const url = new URL(`${API_BASE}/vocab/`, window.location.origin);
  if (search) url.searchParams.append('search', search);
  if (lang) url.searchParams.append('lang', lang);
  if (pending) url.searchParams.append('pending', 'true');
  url.searchParams.append('limit', limit);

  const res = await fetch(url);
  if (!res.ok) throw new Error('Failed to fetch vocabulary');
  return res.json();
};

// 10. Correct an entry (regenerates card text, keeps review history)
export const updateVocabEntry = async (entryId, fields) => {
  const res = await fetch(`${API_BASE}/vocab/${entryId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(fields),
  });

  if (!res.ok) throw new Error('Failed to update entry');
  return res.json();
};

// 11. Delete an entry and its cards
export const deleteVocabEntry = async (entryId) => {
  const res = await fetch(`${API_BASE}/vocab/${entryId}`, { method: 'DELETE' });
  if (!res.ok) throw new Error('Failed to delete entry');
  return true;
};

// 11b. Approve a word out of Quality Control (both its cards, at once)
export const acceptVocabEntry = async (entryId) => {
  const res = await fetch(`${API_BASE}/vocab/${entryId}/accept`, { method: 'PATCH' });
  if (!res.ok) throw new Error('Failed to accept entry');
  return res.json();
};

// 12. Per-deck counts, used by the language tabs
export const getVocabStats = async () => {
  const res = await fetch(`${API_BASE}/vocab/stats`);
  if (!res.ok) throw new Error('Failed to fetch vocabulary stats');
  return res.json();
};

// 13. Bulk-import a prepared word list (no AI call)
export const importWords = async (lang, entries, { glossLang = null, accepted = true } = {}) => {
  const res = await fetch(`${API_BASE}/vocab/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      lang,
      gloss_lang: glossLang || (lang === 'ro' ? 'en' : 'ro'),
      entries,
      accepted,
    }),
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to import words');
  }
  return res.json();
};


// 14. Progress through the bundled word lists, per deck
export const getDeckBatches = async () => {
  const res = await fetch(`${API_BASE}/vocab/decks/batches`);
  if (!res.ok) throw new Error('Failed to fetch word list progress');
  return res.json();
};

// 15. Load the next batch of bundled words into a deck
export const loadNextVocabBatch = async (lang, { cardStatus = 'pending' } = {}) => {
  const res = await fetch(
    `${API_BASE}/vocab/decks/${lang}/batches/next?card_status=${cardStatus}`,
    { method: 'POST' }
  );

  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.detail || 'Failed to load the next batch');
  }
  return res.json();
};
