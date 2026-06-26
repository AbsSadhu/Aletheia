from __future__ import annotations

from aletheia.core.models import AssetType, Holding


def normalize_symbol(symbol: str, exchange: str) -> str:
    cleaned = symbol.strip().upper()
    if exchange.upper() == "NSE" and cleaned.endswith(".NS"):
        return cleaned[:-3]
    if exchange.upper() == "BSE" and cleaned.endswith(".BO"):
        return cleaned[:-3]
    return cleaned


def infer_asset_type(symbol: str) -> AssetType:
    if "/" in symbol:
        return AssetType.CRYPTO
    return AssetType.EQUITY


def normalize_holding(holding: Holding) -> Holding:
    normalized_symbol = normalize_symbol(holding.symbol, holding.exchange)
    return holding.model_copy(
        update={
            "symbol": normalized_symbol,
            "asset_type": infer_asset_type(normalized_symbol),
        }
    )
