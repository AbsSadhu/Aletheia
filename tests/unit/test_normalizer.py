from aletheia.extensions.data.normalizer import infer_asset_type, normalize_symbol
from aletheia.core.models import AssetType


def test_normalize_nse_symbol() -> None:
    assert normalize_symbol("reliance.ns", "NSE") == "RELIANCE"


def test_infer_crypto_asset_type() -> None:
    assert infer_asset_type("BTC/USDT") == AssetType.CRYPTO

