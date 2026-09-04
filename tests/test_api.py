"""
Integration tests — full API flow with mocked OpenAI.
"""
import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_openai_response(cards: list[dict]) -> MagicMock:
    """Build a minimal mock of the OpenAI chat completion response."""
    import json

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = json.dumps({"flashcards": cards})
    return mock_response


SAMPLE_CARDS = [
    {"question": "What is photosynthesis?", "answer": "The process by which plants convert light to energy."},
    {"question": "What organelle carries out photosynthesis?", "answer": "The chloroplast."},
]

TXT_CONTENT = b"""Photosynthesis is the process by which green plants convert sunlight into chemical energy.
It takes place mainly in the chloroplasts. The overall equation is:
6CO2 + 6H2O + light energy -> C6H12O6 + 6O2."""

MD_CONTENT = b"""# Photosynthesis

**Photosynthesis** is carried out by plants, algae, and some bacteria.
The process requires *light*, water, and carbon dioxide.

## Products
- Glucose
- Oxygen
"""

# 1x1 transparent PNG.
TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


# ---------------------------------------------------------------------------
# Document upload
# ---------------------------------------------------------------------------


class TestDocumentUpload:

    async def test_upload_txt_returns_201(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("sample.txt", io.BytesIO(TXT_CONTENT), "text/plain")},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file_type"] == "txt"
        assert data["status"] == "uploaded"
        assert "id" in data

    async def test_upload_markdown_returns_201(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("notes.md", io.BytesIO(MD_CONTENT), "text/markdown")},
        )
        assert response.status_code == 201
        assert response.json()["file_type"] == "md"

    async def test_upload_unsupported_type_returns_415(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("file.csv", io.BytesIO(b"a,b,c"), "text/csv")},
        )
        assert response.status_code == 415

    async def test_upload_empty_file_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
        )
        assert response.status_code == 422

    async def test_list_documents(self, client: AsyncClient):
        await client.post(
            "/api/v1/documents/upload",
            files={"file": ("doc.txt", io.BytesIO(b"Some content here."), "text/plain")},
        )
        response = await client.get("/api/v1/documents/")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_get_document_not_found(self, client: AsyncClient):
        response = await client.get("/api/v1/documents/nonexistent-id")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Flashcard generation
# ---------------------------------------------------------------------------


class TestFlashcardGeneration:

    async def _upload(self, client: AsyncClient) -> str:
        r = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("test.txt", io.BytesIO(TXT_CONTENT), "text/plain")},
        )
        return r.json()["id"]

    @patch(
        "app.services.openai_service.AsyncOpenAI",
        autospec=True,
    )
    async def test_generate_returns_flashcards(self, mock_openai_cls, client: AsyncClient):
        mock_client = mock_openai_cls.return_value
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_response(SAMPLE_CARDS)
        )

        doc_id = await self._upload(client)
        response = await client.post(
            "/api/v1/flashcards/generate",
            json={"document_id": doc_id, "num_cards": 2},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["total"] == 2
        assert body["flashcards"][0]["question"] == SAMPLE_CARDS[0]["question"]

    async def test_generate_unknown_document_returns_404(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/flashcards/generate",
            json={"document_id": "does-not-exist"},
        )
        assert response.status_code == 404

    async def test_generate_validates_num_cards(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/flashcards/generate",
            json={"document_id": "x", "num_cards": 0},
        )
        assert response.status_code == 422

    async def test_list_flashcards(self, client: AsyncClient):
        response = await client.get("/api/v1/flashcards/")
        assert response.status_code == 200
        body = response.json()
        assert "flashcards" in body
        assert "total" in body

    async def test_get_flashcard_not_found(self, client: AsyncClient):
        response = await client.get("/api/v1/flashcards/nonexistent")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Bulk (non-AI) flashcard creation
# ---------------------------------------------------------------------------


class TestBulkCreateFlashcards:

    async def _upload(self, client: AsyncClient) -> str:
        r = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("bulk.txt", io.BytesIO(TXT_CONTENT), "text/plain")},
        )
        return r.json()["id"]

    async def test_bulk_create_returns_pending_cards(self, client: AsyncClient):
        doc_id = await self._upload(client)
        response = await client.post(
            "/api/v1/flashcards/bulk",
            json={"document_id": doc_id, "cards": SAMPLE_CARDS},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["total"] == 2
        assert body["flashcards"][0]["status"] == "pending"
        assert body["flashcards"][0]["question"] == SAMPLE_CARDS[0]["question"]

    async def test_bulk_create_dedupes_by_question(self, client: AsyncClient):
        doc_id = await self._upload(client)
        cards = SAMPLE_CARDS + [SAMPLE_CARDS[0]]
        response = await client.post(
            "/api/v1/flashcards/bulk",
            json={"document_id": doc_id, "cards": cards},
        )
        assert response.status_code == 201
        assert response.json()["total"] == 2

    async def test_bulk_create_unknown_document_returns_404(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/flashcards/bulk",
            json={"document_id": "does-not-exist", "cards": SAMPLE_CARDS},
        )
        assert response.status_code == 404

    async def test_bulk_create_empty_cards_returns_422(self, client: AsyncClient):
        doc_id = await self._upload(client)
        response = await client.post(
            "/api/v1/flashcards/bulk",
            json={"document_id": doc_id, "cards": []},
        )
        assert response.status_code == 422

    async def test_bulk_create_with_image_is_retrievable(self, client: AsyncClient):
        doc_id = await self._upload(client)
        cards = [{**SAMPLE_CARDS[0], "image_base64": TINY_PNG_B64, "image_content_type": "image/png"}]
        response = await client.post(
            "/api/v1/flashcards/bulk",
            json={"document_id": doc_id, "cards": cards},
        )
        assert response.status_code == 201
        card = response.json()["flashcards"][0]
        assert card["has_image"] is True

        image = await client.get(f"/api/v1/flashcards/{card['id']}/image")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content == base64.b64decode(TINY_PNG_B64)

    async def test_bulk_create_without_image_has_no_image(self, client: AsyncClient):
        doc_id = await self._upload(client)
        response = await client.post(
            "/api/v1/flashcards/bulk",
            json={"document_id": doc_id, "cards": SAMPLE_CARDS},
        )
        card = response.json()["flashcards"][0]
        assert card["has_image"] is False

        image = await client.get(f"/api/v1/flashcards/{card['id']}/image")
        assert image.status_code == 404

    async def test_bulk_create_rejects_oversized_image(self, client: AsyncClient):
        doc_id = await self._upload(client)
        huge = base64.b64encode(b"x" * (3 * 1024 * 1024 + 1)).decode()
        cards = [{**SAMPLE_CARDS[0], "image_base64": huge, "image_content_type": "image/png"}]
        response = await client.post(
            "/api/v1/flashcards/bulk",
            json={"document_id": doc_id, "cards": cards},
        )
        assert response.status_code == 422

    async def test_bulk_create_rejects_unpaired_image_fields(self, client: AsyncClient):
        doc_id = await self._upload(client)
        cards = [{**SAMPLE_CARDS[0], "image_base64": TINY_PNG_B64}]  # missing content_type
        response = await client.post(
            "/api/v1/flashcards/bulk",
            json={"document_id": doc_id, "cards": cards},
        )
        assert response.status_code == 422

    async def test_get_image_unknown_flashcard_returns_404(self, client: AsyncClient):
        response = await client.get("/api/v1/flashcards/does-not-exist/image")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Review flow
# ---------------------------------------------------------------------------


class TestReviews:

    @patch("app.services.openai_service.AsyncOpenAI")
    async def test_submit_review_updates_due_date(self, mock_openai_cls, client: AsyncClient):
        mock_client = mock_openai_cls.return_value
        mock_client.chat = MagicMock()
        mock_client.chat.completions = MagicMock()
        mock_client.chat.completions.create = AsyncMock(
            return_value=_make_openai_response(SAMPLE_CARDS)
        )

        # Upload and generate
        r = await client.post(
            "/api/v1/documents/upload",
            files={"file": ("r.txt", io.BytesIO(TXT_CONTENT), "text/plain")},
        )
        doc_id = r.json()["id"]
        gen = await client.post(
            "/api/v1/flashcards/generate",
            json={"document_id": doc_id, "num_cards": 2},
        )
        flashcard_id = gen.json()["flashcards"][0]["id"]

        # Submit review
        review = await client.post(
            "/api/v1/reviews/",
            json={"flashcard_id": flashcard_id, "quality": 4},
        )
        assert review.status_code == 201
        body = review.json()
        assert body["quality"] == 4
        assert "next_due_date" in body
        assert body["scheduled_days"] >= 1

    async def test_review_invalid_quality_returns_422(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/reviews/",
            json={"flashcard_id": "x", "quality": 10},
        )
        assert response.status_code == 422

    async def test_review_nonexistent_flashcard_returns_404(self, client: AsyncClient):
        response = await client.post(
            "/api/v1/reviews/",
            json={"flashcard_id": "ghost-id", "quality": 3},
        )
        assert response.status_code == 404

    async def test_review_history_nonexistent_flashcard_returns_404(self, client: AsyncClient):
        response = await client.get("/api/v1/reviews/nonexistent")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


async def test_health_check(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
