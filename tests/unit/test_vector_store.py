import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aletheia.core.memory.vector_store import VectorMemoryStore


@pytest.fixture
def temp_store_path(tmp_path):
    return tmp_path / "test_memory.db"


@pytest.mark.asyncio
async def test_vector_store_bm25_fallback(temp_store_path):
    store = VectorMemoryStore(db_path=temp_store_path)

    row1 = await store.store("Reliance profits hit all time high", {"category": "news"})
    row2 = await store.store("Tata steel expands operations in UK", {"category": "expansion"})

    assert row1 == 1
    assert row2 == 2

    results = await store.search("Reliance profits", k=2)
    assert len(results) >= 1
    assert results[0].text == "Reliance profits hit all time high"
    assert results[0].metadata["category"] == "news"


@pytest.mark.asyncio
async def test_vector_store_semantic_search(temp_store_path):
    store = VectorMemoryStore(db_path=temp_store_path)
    store._use_vector = True

    dummy_embedding = [0.1] * 768

    with patch.object(store, "_embed", AsyncMock(return_value=dummy_embedding)):
        mock_conn = MagicMock()
        mock_conn.execute.return_value.lastrowid = 42
        store._conn = mock_conn

        row_id = await store.store("Nifty momentum is positive", {"type": "macro"})
        assert row_id == 42

        mock_conn.execute.assert_any_call(
            "INSERT INTO memories (text, metadata_json, text_tokens) VALUES (?, ?, ?)",
            ("Nifty momentum is positive", '{"type": "macro"}', "nifty momentum is positive"),
        )
