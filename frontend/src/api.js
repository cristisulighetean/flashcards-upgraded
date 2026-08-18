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
export const listFlashcards = async (limit = 100, cardType = null) => {
  const url = new URL(`${API_BASE}/flashcards/`, window.location.origin);
  url.searchParams.append('limit', limit);
  if (cardType) url.searchParams.append('card_type', cardType);
  
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

// 9. List vocabulary entries
export const listVocab = async (search = '') => {
  const url = new URL(`${API_BASE}/vocab/`, window.location.origin);
  if (search) url.searchParams.append('search', search);

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
