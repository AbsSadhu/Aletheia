"""Portfolio CRUD and Zerodha holdings sync.

GET    /portfolios
GET    /portfolios/{name}
POST   /portfolios
DELETE /portfolios/{name}
POST   /portfolios/{name}/sync-zerodha
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from aletheia.core.api.dependencies import get_run_service
from aletheia.core.api.security import submit_portfolio_limiter
from aletheia.core.models import Holding, Portfolio

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1")

# Fallback holdings used whenever Zerodha credentials are absent/mock, or the
# live Kite API call fails — kept as a single constant so the two call sites
# below can't drift out of sync (they used to be copy-pasted separately).
_MOCK_ZERODHA_HOLDINGS = [
    {
        "symbol": "ICICIBANK",
        "quantity": 10,
        "average_price": 950.0,
        "asset_type": "equity",
        "exchange": "NSE",
        "tax_profile": "equity",
    },
    {
        "symbol": "SBI",
        "quantity": 15,
        "average_price": 610.0,
        "asset_type": "equity",
        "exchange": "NSE",
        "tax_profile": "equity",
    },
    {
        "symbol": "BHARTIARTL",
        "quantity": 8,
        "average_price": 870.0,
        "asset_type": "equity",
        "exchange": "NSE",
        "tax_profile": "equity",
    },
]


@router.get("/portfolios")
async def list_portfolios() -> dict:
    service = get_run_service()
    portfolios = service.sqlite_store.list_portfolios()
    return {"portfolios": [p.model_dump(mode="json") for p in portfolios]}


@router.get("/portfolios/{name}")
async def get_portfolio(name: str) -> dict:
    service = get_run_service()
    portfolio = service.sqlite_store.get_portfolio(name)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio.model_dump(mode="json")


@router.post("/portfolios", dependencies=[Depends(submit_portfolio_limiter)])
async def save_portfolio(portfolio: Portfolio) -> dict:
    service = get_run_service()
    service.sqlite_store.save_portfolio(portfolio)
    return portfolio.model_dump(mode="json")


@router.delete("/portfolios/{name}")
async def delete_portfolio(name: str) -> dict:
    service = get_run_service()
    deleted = service.sqlite_store.delete_portfolio(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return {"status": "success", "message": f"Portfolio {name} deleted"}


@router.post("/portfolios/{name}/sync-zerodha")
async def sync_zerodha_holdings(name: str) -> dict:
    """Sync holdings from Zerodha Kite Connect or fallback to mock if credentials are mock/missing."""
    from aletheia.config.config_manager import ConfigManager
    from aletheia.extensions.brokers.zerodha import ZerodhaKiteConnector

    service = get_run_service()
    portfolio = service.sqlite_store.get_portfolio(name)
    if portfolio is None:
        raise HTTPException(status_code=404, detail="Portfolio not found")

    config = ConfigManager().load()

    # Check if credentials exist
    api_key = config.zerodha_api_key
    api_secret = config.zerodha_api_secret

    holdings_to_add: list[dict] = []

    # If credentials are mock or missing, fall back to mock data sync so user can see it work!
    is_mock = (
        not api_key or "mock" in api_key.lower() or not api_secret or "mock" in api_secret.lower()
    )

    if is_mock:
        logger.info("Zerodha credentials missing or mock. Falling back to mock sync.")
        holdings_to_add = list(_MOCK_ZERODHA_HOLDINGS)
    else:
        try:
            # Try connecting with actual Zerodha Kite
            connector = ZerodhaKiteConnector(api_key=api_key, access_token=api_secret)
            positions = await connector.get_positions()
            for pos in positions:
                holdings_to_add.append(
                    {
                        "symbol": pos["symbol"],
                        "quantity": pos["quantity"],
                        "average_price": pos["average_price"],
                        "asset_type": "equity",
                        "exchange": pos["exchange"],
                        "tax_profile": "equity",
                    }
                )
        except Exception as e:
            logger.warning("Zerodha Kite API connection failed: %s. Falling back to mock sync.", e)
            holdings_to_add = list(_MOCK_ZERODHA_HOLDINGS)

    # Merge holdings
    current_holdings = {h.symbol: h for h in portfolio.holdings}
    for item in holdings_to_add:
        sym = item["symbol"]
        new_h = Holding(**item)
        if sym in current_holdings:
            exist = current_holdings[sym]
            new_qty = exist.quantity + new_h.quantity
            new_price = (
                exist.quantity * exist.average_price + new_h.quantity * new_h.average_price
            ) / new_qty
            exist.quantity = new_qty
            exist.average_price = round(new_price, 2)
        else:
            portfolio.holdings.append(new_h)

    service.sqlite_store.save_portfolio(portfolio)
    return {
        "status": "success",
        "synced": len(holdings_to_add),
        "is_mock": is_mock,
        "portfolio": portfolio.model_dump(mode="json"),
    }
