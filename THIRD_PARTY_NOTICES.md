# Third-party notices

Aletheia includes code adapted from the following open-source project. It is used under the terms of
its license, reproduced below.

## Vibe-Trading

Source: https://github.com/HKUDS/Vibe-Trading (a copy also exists locally under the name Itoryx).

Adapted into Aletheia:

| Aletheia module | Adapted from (Vibe-Trading) | What changed |
|---|---|---|
| `aletheia/core/journal/analysis.py` | `agent/src/tools/trade_journal_tool.py` | Same four behaviour diagnostics (disposition effect, overtrading, momentum chasing, anchoring). Pairing is now signed FIFO (short trades), round trips are classed intraday / short-term / long-term, a realized XIRR was added, and messages are in rupees. |
| `aletheia/core/journal/parsers.py` | `agent/src/tools/trade_journal_parsers.py` (generic parser) | New Indian broker support (Zerodha tradebook and alias matching for others), day-first dates, Excel serials, rupee strings. |
| `aletheia/core/validation/stats.py` | `agent/src/quantlib/multipletesting.py` | Probabilistic and deflated Sharpe ratio, expected maximum Sharpe and Benjamini-Hochberg, with the original conventions (per-observation Sharpe, non-excess kurtosis). Added minimum track-record length, Sortino, Calmar, drawdown and a one-call assessment. |
| `aletheia/core/analytics/regime.py` | `agent/backtest/regime.py` | Edge density, hysteresis regime detection and fused episodes. Prices come from Aletheia's own daily candles. |

### License text

```
MIT License

Copyright (c) 2026 Vibe-Trading Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
