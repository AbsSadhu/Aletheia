import json
import pytest
from pathlib import Path
from aletheia.core.security.encryption import DatabaseEncryptor
from aletheia.core.db.sqlite_store import SQLiteStore
from aletheia.core.models import Portfolio, Holding, AssetType, TaxProfile


def test_encryptor_basic():
    key = "my-secret-key"
    encryptor = DatabaseEncryptor(key)
    
    plain = '{"name": "My Portfolio", "holdings": []}'
    ciphertext = encryptor.encrypt(plain)
    
    # pyrefly: ignore [missing-attribute]
    assert ciphertext.startswith("__enc__:")
    assert ciphertext != plain
    
    decrypted = encryptor.decrypt(ciphertext)
    assert decrypted == plain


def test_encryptor_wrong_key():
    encryptor1 = DatabaseEncryptor("key1")
    encryptor2 = DatabaseEncryptor("key2")
    
    plain = "secret-data"
    cipher = encryptor1.encrypt(plain)
    
    with pytest.raises(ValueError):
        encryptor2.decrypt(cipher)


def test_sqlite_store_encryption(tmp_path: Path):
    db_file = tmp_path / "test_store_enc.sqlite3"
    
    # Enable encryption via settings mock or monkeypatch
    key = "secure-key"
    
    # 1. Initialize SQLiteStore
    store = SQLiteStore(db_file)
    store.encryptor = DatabaseEncryptor(key)  # Override for test
    
    holding = Holding(
        symbol="RELIANCE",
        quantity=10.0,
        average_price=2500.0,
        asset_type=AssetType.EQUITY,
        exchange="NSE",
        tax_profile=TaxProfile.EQUITY
    )
    portfolio = Portfolio(
        name="Test Portfolio",
        base_currency="INR",
        holdings=[holding]
    )
    
    store.save_portfolio(portfolio)
    
    # 2. Verify on-disk format is encrypted
    import sqlite3
    conn = sqlite3.connect(db_file)
    row = conn.execute("SELECT holdings_json FROM portfolios WHERE name = ?", (portfolio.name,)).fetchone()
    conn.close()
    
    assert row is not None
    holdings_json_raw = row[0]
    assert holdings_json_raw.startswith("__enc__:")
    
    # 3. Read back using store (should decrypt transparently)
    retrieved = store.get_portfolio(portfolio.name)
    assert retrieved is not None
    assert retrieved.name == portfolio.name
    assert len(retrieved.holdings) == 1
    assert retrieved.holdings[0].symbol == "RELIANCE"
    assert retrieved.holdings[0].quantity == 10.0
    
    # 4. Attempt to read with a store configured with the wrong key
    store_wrong = SQLiteStore(db_file)
    store_wrong.encryptor = DatabaseEncryptor("wrong-key")
    with pytest.raises(ValueError):
        store_wrong.get_portfolio(portfolio.name)
