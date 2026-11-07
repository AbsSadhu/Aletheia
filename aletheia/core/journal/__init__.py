"""Trade journal review: read a broker export, profile the trader, and flag behavioural patterns.

Adapted from the trade-journal analyzer in Vibe-Trading (MIT License, Copyright (c) 2026
Vibe-Trading Contributors; see THIRD_PARTY_NOTICES.md). The diagnostics (disposition effect,
overtrading, momentum chasing, anchoring) follow that project's definitions. The parsers are new
(Indian broker exports), the FIFO pairing also handles sell-first (short) trades, and each closed
round trip is classified intraday / short-term / long-term for Indian capital-gains purposes.

Everything runs in memory on the uploaded file. Nothing is stored.
"""
