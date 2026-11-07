"""Aggregates all Aletheia API v1 routers into the two routers main.py expects.

Endpoint definitions live in `aletheia.core.api.routers.*`, one module per
domain (health, runs, portfolios, backtest, marketdata, execution, shadow,
hypotheses, memory, factors, risk, config, chat, websocket). This module
just composes them — see each submodule's docstring for its endpoint list.
"""

from __future__ import annotations

from fastapi import APIRouter

from aletheia.core.api.routers import (
    analytics,
    backtest,
    brokers,
    chat,
    config,
    execution,
    feed,
    factors,
    health,
    hypotheses,
    journal,
    marketdata,
    memory,
    news,
    options,
    portfolios,
    risk,
    runs,
    shadow,
    signals,
    swarm,
    validation,
    websocket,
)

router = APIRouter()
for _module in (
    analytics,
    brokers,
    feed,
    health,
    runs,
    portfolios,
    backtest,
    marketdata,
    execution,
    shadow,
    hypotheses,
    journal,
    memory,
    news,
    options,
    factors,
    risk,
    config,
    chat,
    signals,
    swarm,
    validation,
):
    router.include_router(_module.router)

# Separate router: included in main.py WITHOUT the router-level X-API-Key
# dependency — see aletheia.core.api.routers.websocket for why.
ws_router = websocket.router
callback_router = brokers.callback_router
