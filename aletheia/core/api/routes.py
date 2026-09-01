"""Aggregates all Aletheia API v1 routers into the two routers main.py expects.

Endpoint definitions live in `aletheia.core.api.routers.*`, one module per
domain (health, runs, portfolios, backtest, marketdata, execution, shadow,
hypotheses, memory, factors, risk, config, chat, websocket). This module
just composes them — see each submodule's docstring for its endpoint list.
"""

from __future__ import annotations

from fastapi import APIRouter

from aletheia.core.api.routers import (
    backtest,
    chat,
    config,
    execution,
    factors,
    health,
    hypotheses,
    marketdata,
    memory,
    portfolios,
    risk,
    runs,
    shadow,
    websocket,
)

router = APIRouter()
for _module in (
    health,
    runs,
    portfolios,
    backtest,
    marketdata,
    execution,
    shadow,
    hypotheses,
    memory,
    factors,
    risk,
    config,
    chat,
):
    router.include_router(_module.router)

# Separate router: included in main.py WITHOUT the router-level X-API-Key
# dependency — see aletheia.core.api.routers.websocket for why.
ws_router = websocket.router
