use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;
use std::f64::consts::PI;

// ============================================================
// Utility: Normal CDF + PDF (Black-Scholes, VaR)
// ============================================================

fn norm_cdf(x: f64) -> f64 {
    let l = x.abs();
    let k = 1.0 / (1.0 + 0.2316419 * l);
    let k_sum = k * (0.319381530 + k * (-0.356563782 + k * (1.781477937 + k * (-1.821255978 + 1.330274429 * k))));
    let approx = 1.0 - (1.0 / (2.0 * PI).sqrt()) * (-l * l / 2.0).exp() * k_sum;
    if x < 0.0 { 1.0 - approx } else { approx }
}

fn norm_pdf(x: f64) -> f64 {
    (1.0 / (2.0 * PI).sqrt()) * (-x * x / 2.0).exp()
}

/// Xorshift128+ RNG — much better than LCG, zero external dependencies
struct Xorshift128Plus {
    s: [u64; 2],
}

impl Xorshift128Plus {
    fn new(seed: u64) -> Self {
        Self { s: [seed | 1, seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407) | 1] }
    }

    fn next_u64(&mut self) -> u64 {
        let mut s1 = self.s[0];
        let s0 = self.s[1];
        self.s[0] = s0;
        s1 ^= s1 << 23;
        self.s[1] = s1 ^ s0 ^ (s1 >> 18) ^ (s0 >> 5);
        self.s[1].wrapping_add(s0)
    }

    fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64
    }

    /// Box-Muller: standard normal sample
    fn next_normal(&mut self) -> f64 {
        let u1 = (self.next_f64()).max(1e-15);
        let u2 = self.next_f64();
        (-2.0 * u1.ln()).sqrt() * (2.0 * PI * u2).cos()
    }
}

// ============================================================
// Portfolio Risk Assessment (existing, preserved)
// ============================================================

#[pyfunction]
fn assess_portfolio_risk_rust(
    py: Python<'_>,
    portfolio: Bound<'_, PyAny>,
    quotes_by_symbol: Bound<'_, PyDict>,
) -> PyResult<PyObject> {
    let holdings_py = portfolio.getattr("holdings")?;
    let holdings: Bound<'_, PyList> = holdings_py.downcast_into()?;

    let mut values = HashMap::new();
    let mut holdings_data = Vec::new();

    for holding_py in holdings.iter() {
        let symbol: String = holding_py.getattr("symbol")?.extract::<String>()?.to_uppercase();
        let quantity: f64 = holding_py.getattr("quantity")?.extract::<f64>()?;

        let quote_py_opt = quotes_by_symbol.get_item(&symbol)?;
        if let Some(quote_py) = quote_py_opt {
            let close: f64 = quote_py.getattr("close")?.extract::<f64>()?;
            let open_opt: Option<f64> = {
                let op = quote_py.getattr("open")?;
                if op.is_none() { None } else { Some(op.extract::<f64>()?) }
            };
            let market_value = quantity * close;
            values.insert(symbol.clone(), market_value);
            holdings_data.push((symbol, quantity, open_opt, close));
        }
    }

    let total_value: f64 = values.values().sum();
    let effective_total = if total_value == 0.0 { 1.0 } else { total_value };

    let mut weights = HashMap::new();
    for (sym, val) in &values {
        weights.insert(sym.clone(), val / effective_total);
    }

    let max_weight: f64 = weights.values().cloned().fold(0.0, f64::max);
    let mut daily_move = 0.0;

    for (symbol, _qty, open_opt, close) in holdings_data {
        if let Some(open) = open_opt {
            if open != 0.0 {
                let weight = weights.get(&symbol).cloned().unwrap_or(0.0);
                daily_move += ((close - open) / open).abs() * weight;
            }
        }
    }

    let portfolio_var_95 = -(effective_total * (daily_move * 1.65).max(0.01));
    let concentration_risk = (max_weight * 10000.0).round() / 10000.0;

    let mut regime = "balanced".to_string();
    let mut alerts = Vec::new();

    if max_weight > 0.4 {
        regime = "concentrated".to_string();
        alerts.push("Single-position exposure is above 40% of portfolio market value.".to_string());
    }
    if daily_move > 0.04 {
        regime = "volatile".to_string();
        alerts.push("Observed mark-to-market volatility is elevated.".to_string());
    }

    let mut confidence = 0.55;
    if values.is_empty() {
        alerts.push("Risk metrics are estimated with incomplete market data.".to_string());
        confidence = 0.2;
    }

    let result = PyDict::new_bound(py);
    result.set_item("portfolio_var_95", (portfolio_var_95 * 100.0).round() / 100.0)?;
    result.set_item("concentration_risk", concentration_risk)?;
    result.set_item("max_single_position_pct", (max_weight * 10000.0).round() / 100.0)?;
    result.set_item("market_regime", regime)?;
    result.set_item("confidence", confidence)?;
    result.set_item("alerts", alerts)?;
    Ok(result.into())
}

// ============================================================
// Tax Summary (existing)
// ============================================================

fn tax_drag(profile: &str) -> f64 {
    match profile.to_lowercase().as_str() {
        "equity"      => 0.15,
        "fno"         => 0.175,
        "crypto"      => 0.15,
        "mutual_fund" => 0.20,
        _             => 0.15,
    }
}

#[pyfunction]
fn build_tax_summary_rust(py: Python<'_>, tax_profile_str: String, pre_tax_profit: f64) -> PyResult<PyObject> {
    let drag = tax_drag(&tax_profile_str);
    let tax_amt = pre_tax_profit.max(0.0) * drag;
    let post_tax = pre_tax_profit - tax_amt;
    let r = PyDict::new_bound(py);
    r.set_item("tax_profile", tax_profile_str)?;
    r.set_item("pre_tax_profit", (pre_tax_profit * 100.0).round() / 100.0)?;
    r.set_item("tax_drag_pct", (drag * 10000.0).round() / 100.0)?;
    r.set_item("estimated_tax_amount", (tax_amt * 100.0).round() / 100.0)?;
    r.set_item("post_tax_profit", (post_tax * 100.0).round() / 100.0)?;
    Ok(r.into())
}

// ============================================================
// Scenario builder (existing)
// ============================================================

#[pyfunction]
fn build_scenario_rust(
    py: Python<'_>,
    holding: Bound<'_, PyAny>,
    quote: Bound<'_, PyAny>,
    conviction: f64,
) -> PyResult<PyObject> {
    let symbol: String = holding.getattr("symbol")?.extract::<String>()?.to_uppercase();
    let quantity: f64 = holding.getattr("quantity")?.extract::<f64>()?;
    let average_price: f64 = holding.getattr("average_price")?.extract::<f64>()?;
    let tax_profile_py = holding.getattr("tax_profile")?;
    let tax_profile_str: String = if tax_profile_py.hasattr("value")? {
        tax_profile_py.getattr("value")?.extract::<String>()?
    } else {
        tax_profile_py.extract::<String>()?
    };
    let close: f64 = quote.getattr("close")?.extract::<f64>()?;
    let avg_denom = if average_price == 0.0 { 1e-6 } else { average_price };
    let move_pct = (close - average_price) / avg_denom;
    let projected_return_pct = (move_pct * 100.0) + (conviction * 8.0);
    let pre_tax_profit = quantity * average_price * (projected_return_pct / 100.0);
    let drag = tax_drag(&tax_profile_str);
    let tax_amt = pre_tax_profit.max(0.0) * drag;
    let post_tax = pre_tax_profit - tax_amt;
    let total_cost = quantity * average_price;
    let cost_denom = if total_cost == 0.0 { 1e-6 } else { total_cost };
    let post_tax_return_pct = (post_tax / cost_denom) * 100.0;
    let sharpe = (projected_return_pct / 12.0).min(2.5).max(-1.0);
    let rationale = vec![
        format!("Projected pre-tax return is {:.2}% based on mark-to-market drift and conviction.", projected_return_pct),
        format!("Estimated tax drag for {} is {:.2}%.", tax_profile_str, drag * 100.0),
    ];
    let tax_summary = PyDict::new_bound(py);
    tax_summary.set_item("tax_profile", &tax_profile_str)?;
    tax_summary.set_item("pre_tax_profit", (pre_tax_profit * 100.0).round() / 100.0)?;
    tax_summary.set_item("tax_drag_pct", (drag * 10000.0).round() / 100.0)?;
    tax_summary.set_item("estimated_tax_amount", (tax_amt * 100.0).round() / 100.0)?;
    tax_summary.set_item("post_tax_profit", (post_tax * 100.0).round() / 100.0)?;
    let scenario = PyDict::new_bound(py);
    scenario.set_item("scenario_name", "base_tax_aware_projection")?;
    scenario.set_item("projected_return_pct", (projected_return_pct * 100.0).round() / 100.0)?;
    scenario.set_item("projected_post_tax_return_pct", (post_tax_return_pct * 100.0).round() / 100.0)?;
    scenario.set_item("projected_sharpe", (sharpe * 100.0).round() / 100.0)?;
    scenario.set_item("tax_summary", tax_summary)?;
    let result = PyDict::new_bound(py);
    result.set_item("symbol", symbol)?;
    result.set_item("scenario", scenario)?;
    let raw_conf = (0.45 + conviction * 0.4).min(0.9).max(0.2);
    result.set_item("confidence", (raw_conf * 100.0).round() / 100.0)?;
    result.set_item("rationale", rationale)?;
    Ok(result.into())
}

// ============================================================
// Black-Scholes Options Pricing (existing)
// ============================================================

#[pyfunction]
fn options_pricing_rust(
    py: Python<'_>,
    s: f64, k: f64, t: f64, r: f64, v: f64, is_call: bool,
) -> PyResult<PyObject> {
    if t <= 0.0 || v <= 0.0 {
        let price = if is_call { (s - k).max(0.0) } else { (k - s).max(0.0) };
        let r = PyDict::new_bound(py);
        r.set_item("price", price)?;
        r.set_item("delta", if price > 0.0 { if is_call { 1.0 } else { -1.0 } } else { 0.0 })?;
        r.set_item("gamma", 0.0)?; r.set_item("theta", 0.0)?; r.set_item("vega", 0.0)?;
        return Ok(r.into());
    }
    let d1 = ((s / k).ln() + (r + v * v / 2.0) * t) / (v * t.sqrt());
    let d2 = d1 - v * t.sqrt();
    let nd1 = norm_cdf(d1); let nd2 = norm_cdf(d2);
    let n_neg_d1 = norm_cdf(-d1); let n_neg_d2 = norm_cdf(-d2);
    let npdf_d1 = norm_pdf(d1);
    let (price, delta, theta) = if is_call {
        let p = s * nd1 - k * (-r * t).exp() * nd2;
        let d = nd1;
        let th = -(s * v * npdf_d1) / (2.0 * t.sqrt()) - r * k * (-r * t).exp() * nd2;
        (p, d, th)
    } else {
        let p = k * (-r * t).exp() * n_neg_d2 - s * n_neg_d1;
        let d = nd1 - 1.0;
        let th = -(s * v * npdf_d1) / (2.0 * t.sqrt()) + r * k * (-r * t).exp() * n_neg_d2;
        (p, d, th)
    };
    let gamma = npdf_d1 / (s * v * t.sqrt());
    let vega = s * t.sqrt() * npdf_d1;
    let res = PyDict::new_bound(py);
    res.set_item("price", price)?; res.set_item("delta", delta)?;
    res.set_item("gamma", gamma)?; res.set_item("theta", theta)?; res.set_item("vega", vega)?;
    Ok(res.into())
}

// ============================================================
// Monte Carlo VaR — upgraded to Xorshift128+ RNG
// ============================================================

#[pyfunction]
fn monte_carlo_var_rust(
    py: Python<'_>,
    portfolio_value: f64,
    daily_vol: f64,
    simulations: usize,
    confidence_level: f64,
) -> PyResult<PyObject> {
    let mut rng = Xorshift128Plus::new(0xDEAD_BEEF_CAFE_1337);
    let mut losses: Vec<f64> = Vec::with_capacity(simulations);

    for _ in 0..simulations {
        let z = rng.next_normal();
        losses.push(-(portfolio_value * daily_vol * z));
    }

    losses.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
    let idx = ((1.0 - confidence_level) * simulations as f64) as usize;
    let var = if idx < losses.len() { losses[idx] } else { losses[losses.len() - 1] };

    let res = PyDict::new_bound(py);
    res.set_item("var", var)?;
    res.set_item("simulations", simulations)?;
    res.set_item("confidence_level", confidence_level)?;
    Ok(res.into())
}

// ============================================================
// Monte Carlo Portfolio Paths — NEW
// Returns percentile paths: p5, p25, p50, p75, p95
// ============================================================

#[pyfunction]
fn monte_carlo_portfolio_paths_rust(
    py: Python<'_>,
    initial_value: f64,
    daily_vol: f64,
    daily_drift: f64,
    n_paths: usize,
    n_days: usize,
) -> PyResult<PyObject> {
    let mut rng = Xorshift128Plus::new(0xABCD_1234_EF56_7890);

    // Generate all paths
    let mut paths: Vec<Vec<f64>> = Vec::with_capacity(n_paths);
    for _ in 0..n_paths {
        let mut path = Vec::with_capacity(n_days + 1);
        let mut value = initial_value;
        path.push(value);
        for _ in 0..n_days {
            let z = rng.next_normal();
            let daily_return = daily_drift + daily_vol * z;
            value *= 1.0 + daily_return;
            path.push(value);
        }
        paths.push(path);
    }

    // Compute percentiles at each day
    let percentiles = [5usize, 25, 50, 75, 95];
    let mut pct_series: HashMap<&str, Vec<f64>> = HashMap::new();
    let labels = ["p5", "p25", "p50", "p75", "p95"];

    for (i, &pct) in percentiles.iter().enumerate() {
        let mut day_values = Vec::with_capacity(n_days + 1);
        for day in 0..=n_days {
            let mut vals: Vec<f64> = paths.iter().map(|p| p[day]).collect();
            vals.sort_by(|a, b| a.partial_cmp(b).unwrap());
            let idx = (pct * n_paths / 100).min(n_paths - 1);
            day_values.push((vals[idx] * 100.0).round() / 100.0);
        }
        pct_series.insert(labels[i], day_values);
    }

    let final_values: Vec<f64> = paths.iter().map(|p| p[n_days]).collect();
    let mean_final = final_values.iter().sum::<f64>() / n_paths as f64;

    let res = PyDict::new_bound(py);
    for (label, series) in &pct_series {
        res.set_item(*label, series)?;
    }
    res.set_item("n_paths", n_paths)?;
    res.set_item("n_days", n_days)?;
    res.set_item("initial_value", initial_value)?;
    res.set_item("mean_final", (mean_final * 100.0).round() / 100.0)?;
    Ok(res.into())
}

// ============================================================
// Technical Indicators — expanded suite
// ============================================================

#[pyfunction]
fn calculate_technical_indicators_rust(
    py: Python<'_>,
    closes: Vec<f64>,
    window: usize,
) -> PyResult<PyObject> {
    let n = closes.len();
    let mut sma: Vec<Option<f64>> = Vec::with_capacity(n);
    let mut ema: Vec<Option<f64>> = Vec::with_capacity(n);

    // SMA
    for i in 0..n {
        if i + 1 < window { sma.push(None); }
        else {
            let sum: f64 = closes[i + 1 - window..=i].iter().sum();
            sma.push(Some(sum / window as f64));
        }
    }

    // EMA
    let multiplier = 2.0 / (window as f64 + 1.0);
    let mut current_ema = closes[0];
    ema.push(Some(current_ema));
    for i in 1..n {
        current_ema = (closes[i] - current_ema) * multiplier + current_ema;
        ema.push(Some(current_ema));
    }

    // RSI (Wilder smoothing)
    let mut rsi = vec![None; n];
    let rsi_window = 14.min(n);
    if n > rsi_window {
        let mut gains = 0.0; let mut losses_sum = 0.0;
        for i in 1..=rsi_window {
            let change = closes[i] - closes[i - 1];
            if change > 0.0 { gains += change; } else { losses_sum -= change; }
        }
        let mut avg_gain = gains / rsi_window as f64;
        let mut avg_loss = losses_sum / rsi_window as f64;
        rsi[rsi_window] = Some(if avg_loss == 0.0 { 100.0 } else { 100.0 - 100.0 / (1.0 + avg_gain / avg_loss) });
        for i in (rsi_window + 1)..n {
            let change = closes[i] - closes[i - 1];
            let g = if change > 0.0 { change } else { 0.0 };
            let l = if change < 0.0 { -change } else { 0.0 };
            avg_gain = (avg_gain * 13.0 + g) / 14.0;
            avg_loss = (avg_loss * 13.0 + l) / 14.0;
            rsi[i] = Some(if avg_loss == 0.0 { 100.0 } else { 100.0 - 100.0 / (1.0 + avg_gain / avg_loss) });
        }
    }

    let res = PyDict::new_bound(py);
    res.set_item("sma", sma)?;
    res.set_item("ema", ema)?;
    res.set_item("rsi", rsi)?;
    Ok(res.into())
}

// ============================================================
// MACD — NEW
// Returns: macd_line, signal_line, histogram
// ============================================================

#[pyfunction]
fn calculate_macd_rust(
    py: Python<'_>,
    closes: Vec<f64>,
    fast: usize,
    slow: usize,
    signal: usize,
) -> PyResult<PyObject> {
    let ema_vec = |data: &[f64], period: usize| -> Vec<f64> {
        let m = 2.0 / (period as f64 + 1.0);
        let mut e = Vec::with_capacity(data.len());
        e.push(data[0]);
        for i in 1..data.len() {
            let prev = *e.last().unwrap();
            e.push((data[i] - prev) * m + prev);
        }
        e
    };

    let ema_fast = ema_vec(&closes, fast);
    let ema_slow = ema_vec(&closes, slow);
    let macd_line: Vec<f64> = ema_fast.iter().zip(ema_slow.iter()).map(|(f, s)| f - s).collect();
    let signal_line = ema_vec(&macd_line, signal);
    let histogram: Vec<f64> = macd_line.iter().zip(signal_line.iter()).map(|(m, s)| m - s).collect();

    let res = PyDict::new_bound(py);
    res.set_item("macd_line", macd_line)?;
    res.set_item("signal_line", signal_line)?;
    res.set_item("histogram", histogram)?;
    Ok(res.into())
}

// ============================================================
// Bollinger Bands — NEW
// ============================================================

#[pyfunction]
fn calculate_bollinger_bands_rust(
    py: Python<'_>,
    closes: Vec<f64>,
    window: usize,
    num_std: f64,
) -> PyResult<PyObject> {
    let n = closes.len();
    let mut upper = vec![None::<f64>; n];
    let mut middle = vec![None::<f64>; n];
    let mut lower = vec![None::<f64>; n];
    let mut bandwidth = vec![None::<f64>; n];
    let mut pct_b = vec![None::<f64>; n];

    for i in (window - 1)..n {
        let slice = &closes[i + 1 - window..=i];
        let mean = slice.iter().sum::<f64>() / window as f64;
        let variance = slice.iter().map(|x| (x - mean).powi(2)).sum::<f64>() / window as f64;
        let std = variance.sqrt();
        let u = mean + num_std * std;
        let l = mean - num_std * std;
        upper[i] = Some(u);
        middle[i] = Some(mean);
        lower[i] = Some(l);
        bandwidth[i] = Some(if mean != 0.0 { (u - l) / mean } else { 0.0 });
        pct_b[i] = Some(if u != l { (closes[i] - l) / (u - l) } else { 0.5 });
    }

    let res = PyDict::new_bound(py);
    res.set_item("upper", upper)?;
    res.set_item("middle", middle)?;
    res.set_item("lower", lower)?;
    res.set_item("bandwidth", bandwidth)?;
    res.set_item("pct_b", pct_b)?;
    Ok(res.into())
}

// ============================================================
// ATR — Average True Range — NEW
// ============================================================

#[pyfunction]
fn calculate_atr_rust(
    py: Python<'_>,
    highs: Vec<f64>,
    lows: Vec<f64>,
    closes: Vec<f64>,
    window: usize,
) -> PyResult<PyObject> {
    let n = closes.len();
    if n < 2 { return Err(pyo3::exceptions::PyValueError::new_err("Need at least 2 data points")); }

    let mut tr = Vec::with_capacity(n - 1);
    for i in 1..n {
        let hl = highs[i] - lows[i];
        let hc = (highs[i] - closes[i - 1]).abs();
        let lc = (lows[i] - closes[i - 1]).abs();
        tr.push(hl.max(hc).max(lc));
    }

    // Wilder smoothed ATR
    let mut atr = vec![None::<f64>; n];
    if tr.len() >= window {
        let initial_atr = tr[..window].iter().sum::<f64>() / window as f64;
        atr[window] = Some(initial_atr);
        let mut prev_atr = initial_atr;
        for i in window..tr.len() {
            let smoothed = (prev_atr * (window as f64 - 1.0) + tr[i]) / window as f64;
            atr[i + 1] = Some(smoothed);
            prev_atr = smoothed;
        }
    }

    let res = PyDict::new_bound(py);
    res.set_item("tr", tr)?;
    res.set_item("atr", atr)?;
    Ok(res.into())
}

// ============================================================
// VWAP — Volume Weighted Average Price — NEW
// ============================================================

#[pyfunction]
fn calculate_vwap_rust(
    py: Python<'_>,
    highs: Vec<f64>,
    lows: Vec<f64>,
    closes: Vec<f64>,
    volumes: Vec<f64>,
) -> PyResult<PyObject> {
    let n = closes.len();
    let mut vwap = Vec::with_capacity(n);
    let mut cum_vol = 0.0;
    let mut cum_tp_vol = 0.0;

    for i in 0..n {
        let typical_price = (highs[i] + lows[i] + closes[i]) / 3.0;
        cum_tp_vol += typical_price * volumes[i];
        cum_vol += volumes[i];
        vwap.push(if cum_vol > 0.0 { cum_tp_vol / cum_vol } else { typical_price });
    }

    let res = PyDict::new_bound(py);
    res.set_item("vwap", vwap)?;
    Ok(res.into())
}

// ============================================================
// OBV — On-Balance Volume — NEW
// ============================================================

#[pyfunction]
fn calculate_obv_rust(
    py: Python<'_>,
    closes: Vec<f64>,
    volumes: Vec<f64>,
) -> PyResult<PyObject> {
    let n = closes.len();
    let mut obv = Vec::with_capacity(n);
    let mut current_obv: f64 = 0.0;
    obv.push(current_obv);
    for i in 1..n {
        if closes[i] > closes[i - 1] { current_obv += volumes[i]; }
        else if closes[i] < closes[i - 1] { current_obv -= volumes[i]; }
        obv.push(current_obv);
    }
    let res = PyDict::new_bound(py);
    res.set_item("obv", obv)?;
    Ok(res.into())
}

// ============================================================
// Stochastic Oscillator — NEW
// ============================================================

#[pyfunction]
fn calculate_stochastic_rust(
    py: Python<'_>,
    highs: Vec<f64>,
    lows: Vec<f64>,
    closes: Vec<f64>,
    k_period: usize,
    d_period: usize,
) -> PyResult<PyObject> {
    let n = closes.len();
    let mut k_raw = vec![None::<f64>; n];
    let mut d_values = vec![None::<f64>; n];

    for i in (k_period - 1)..n {
        let slice_high = highs[i + 1 - k_period..=i].iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let slice_low  = lows[i + 1 - k_period..=i].iter().cloned().fold(f64::INFINITY, f64::min);
        let denom = slice_high - slice_low;
        k_raw[i] = Some(if denom > 0.0 { (closes[i] - slice_low) / denom * 100.0 } else { 50.0 });
    }

    // %D is d_period SMA of %K
    for i in (k_period + d_period - 2)..n {
        let slice: Vec<f64> = (i + 1 - d_period..=i)
            .filter_map(|j| k_raw[j])
            .collect();
        if slice.len() == d_period {
            d_values[i] = Some(slice.iter().sum::<f64>() / d_period as f64);
        }
    }

    let res = PyDict::new_bound(py);
    res.set_item("pct_k", k_raw)?;
    res.set_item("pct_d", d_values)?;
    Ok(res.into())
}

// ============================================================
// Correlation Matrix — NEW
// Returns lower-triangular correlation matrix as list of (sym_i, sym_j, corr)
// ============================================================

#[pyfunction]
fn correlation_matrix_rust(py: Python<'_>, returns_matrix: Vec<Vec<f64>>) -> PyResult<PyObject> {
    let n = returns_matrix.len();
    if n == 0 { return Err(pyo3::exceptions::PyValueError::new_err("Empty returns matrix")); }

    let mean = |v: &[f64]| v.iter().sum::<f64>() / v.len() as f64;
    let std_dev = |v: &[f64]| {
        let m = mean(v);
        (v.iter().map(|x| (x - m).powi(2)).sum::<f64>() / v.len() as f64).sqrt()
    };

    let mut matrix = vec![vec![0.0f64; n]; n];

    for i in 0..n {
        matrix[i][i] = 1.0;
        let mi = mean(&returns_matrix[i]);
        let si = std_dev(&returns_matrix[i]);
        for j in (i + 1)..n {
            let mj = mean(&returns_matrix[j]);
            let sj = std_dev(&returns_matrix[j]);
            let len = returns_matrix[i].len().min(returns_matrix[j].len());
            let cov = (0..len)
                .map(|k| (returns_matrix[i][k] - mi) * (returns_matrix[j][k] - mj))
                .sum::<f64>() / len as f64;
            let corr = if si * sj > 0.0 { cov / (si * sj) } else { 0.0 };
            matrix[i][j] = corr;
            matrix[j][i] = corr;
        }
    }

    let res = PyDict::new_bound(py);
    res.set_item("matrix", matrix)?;
    res.set_item("n_assets", n)?;
    Ok(res.into())
}

// ============================================================
// Rolling Correlation — NEW
// ============================================================

#[pyfunction]
fn rolling_correlation_rust(
    py: Python<'_>,
    series_a: Vec<f64>,
    series_b: Vec<f64>,
    window: usize,
) -> PyResult<PyObject> {
    let n = series_a.len().min(series_b.len());
    let mut corr = vec![None::<f64>; n];

    for i in (window - 1)..n {
        let a = &series_a[i + 1 - window..=i];
        let b = &series_b[i + 1 - window..=i];
        let ma = a.iter().sum::<f64>() / window as f64;
        let mb = b.iter().sum::<f64>() / window as f64;
        let cov = a.iter().zip(b.iter()).map(|(x, y)| (x - ma) * (y - mb)).sum::<f64>() / window as f64;
        let sa = (a.iter().map(|x| (x - ma).powi(2)).sum::<f64>() / window as f64).sqrt();
        let sb = (b.iter().map(|y| (y - mb).powi(2)).sum::<f64>() / window as f64).sqrt();
        corr[i] = Some(if sa * sb > 0.0 { cov / (sa * sb) } else { 0.0 });
    }

    let res = PyDict::new_bound(py);
    res.set_item("rolling_corr", corr)?;
    Ok(res.into())
}

// ============================================================
// Backtest Metrics: Sharpe, Sortino, Calmar, Max Drawdown — NEW
// ============================================================

#[pyfunction]
fn calculate_sharpe_rust(returns: Vec<f64>, risk_free_rate: f64, periods_per_year: f64) -> f64 {
    if returns.is_empty() { return 0.0; }
    let mean = returns.iter().sum::<f64>() / returns.len() as f64;
    let variance = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / returns.len() as f64;
    let std = variance.sqrt();
    if std == 0.0 { return 0.0; }
    let excess = mean - risk_free_rate / periods_per_year;
    excess / std * periods_per_year.sqrt()
}

#[pyfunction]
fn calculate_sortino_rust(returns: Vec<f64>, target_return: f64, periods_per_year: f64) -> f64 {
    if returns.is_empty() { return 0.0; }
    let mean = returns.iter().sum::<f64>() / returns.len() as f64;
    let downside_sq: f64 = returns.iter()
        .map(|r| (target_return - r).max(0.0).powi(2))
        .sum::<f64>() / returns.len() as f64;
    let downside = downside_sq.sqrt();
    if downside == 0.0 { return f64::INFINITY; }
    (mean - target_return) / downside * periods_per_year.sqrt()
}

#[pyfunction]
fn calculate_calmar_rust(returns: Vec<f64>, periods_per_year: f64) -> f64 {
    if returns.is_empty() { return 0.0; }
    let annual_return = returns.iter().sum::<f64>() / returns.len() as f64 * periods_per_year;

    // Max drawdown from equity curve
    let mut equity = 1.0f64;
    let mut peak = 1.0f64;
    let mut max_dd = 0.0f64;
    for r in &returns {
        equity *= 1.0 + r;
        if equity > peak { peak = equity; }
        let dd = (peak - equity) / peak;
        if dd > max_dd { max_dd = dd; }
    }
    if max_dd == 0.0 { return f64::INFINITY; }
    annual_return / max_dd
}

#[pyfunction]
fn calculate_max_drawdown_rust(py: Python<'_>, equity_curve: Vec<f64>) -> PyResult<PyObject> {
    if equity_curve.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err("Empty equity curve"));
    }

    let mut peak = equity_curve[0];
    let mut peak_idx = 0usize;
    let mut max_dd = 0.0f64;
    let mut trough_idx = 0usize;
    let mut dd_start = 0usize;
    let mut underwater: Vec<f64> = Vec::with_capacity(equity_curve.len());

    for (i, &val) in equity_curve.iter().enumerate() {
        if val > peak { peak = val; peak_idx = i; }
        let dd = if peak > 0.0 { (peak - val) / peak } else { 0.0 };
        underwater.push(dd);
        if dd > max_dd { max_dd = dd; trough_idx = i; dd_start = peak_idx; }
    }

    // Find recovery (first index after trough where equity >= peak at dd_start)
    let peak_at_dd = equity_curve[dd_start];
    let recovery_idx = equity_curve[trough_idx..].iter().position(|&v| v >= peak_at_dd)
        .map(|offset| trough_idx + offset);

    let drawdown_duration = trough_idx - dd_start;
    let recovery_period = recovery_idx.map(|r| r - trough_idx);

    let res = PyDict::new_bound(py);
    res.set_item("max_drawdown", max_dd)?;
    res.set_item("max_drawdown_pct", (max_dd * 10000.0).round() / 100.0)?;
    res.set_item("drawdown_start_idx", dd_start)?;
    res.set_item("trough_idx", trough_idx)?;
    res.set_item("drawdown_duration", drawdown_duration)?;
    res.set_item("recovery_period", recovery_period)?;
    res.set_item("underwater", underwater)?;
    Ok(res.into())
}

// ============================================================
// BM25 Scoring — for memory retrieval — NEW
// Returns relevance scores for each document given a query.
// Parameters: k1 (term saturation ~1.5), b (length norm ~0.75)
// ============================================================

#[pyfunction]
fn bm25_score_rust(
    query: String,
    documents: Vec<String>,
    k1: f64,
    b: f64,
) -> Vec<f64> {
    if documents.is_empty() { return vec![]; }

    let tokenize = |text: &str| -> Vec<String> {
        text.to_lowercase()
            .split(|c: char| !c.is_alphanumeric())
            .filter(|t| !t.is_empty())
            .map(String::from)
            .collect()
    };

    let query_terms = tokenize(&query);
    if query_terms.is_empty() { return vec![0.0; documents.len()]; }

    let tokenized_docs: Vec<Vec<String>> = documents.iter().map(|d| tokenize(d)).collect();
    let n = tokenized_docs.len() as f64;
    let avg_dl = tokenized_docs.iter().map(|d| d.len() as f64).sum::<f64>() / n;

    // IDF: log((N - df + 0.5) / (df + 0.5) + 1)
    let idf = |term: &str| -> f64 {
        let df = tokenized_docs.iter().filter(|d| d.iter().any(|t| t == term)).count() as f64;
        ((n - df + 0.5) / (df + 0.5) + 1.0).ln()
    };

    tokenized_docs.iter().map(|doc| {
        let dl = doc.len() as f64;
        let tf_map: HashMap<&str, usize> = {
            let mut m = HashMap::new();
            for t in doc { *m.entry(t.as_str()).or_insert(0) += 1; }
            m
        };
        query_terms.iter().map(|qt| {
            let tf = *tf_map.get(qt.as_str()).unwrap_or(&0) as f64;
            let tf_norm = (tf * (k1 + 1.0)) / (tf + k1 * (1.0 - b + b * dl / avg_dl));
            idf(qt) * tf_norm
        }).sum::<f64>()
    }).collect()
}

// ============================================================
// Rate Limiter — thread-safe token bucket — NEW
// ============================================================

use std::sync::{Arc, Mutex};
use std::time::Instant;


#[pyclass]
struct RateLimiter {
    tokens: Arc<Mutex<f64>>,
    rate: f64,      // tokens per second
    capacity: f64,  // max tokens
    last_refill: Arc<Mutex<Instant>>,
}

#[pymethods]
impl RateLimiter {
    #[new]
    fn new(rate: f64, capacity: f64) -> Self {
        Self {
            tokens: Arc::new(Mutex::new(capacity)),
            rate,
            capacity,
            last_refill: Arc::new(Mutex::new(Instant::now())),
        }
    }

    /// Attempt to consume `n` tokens. Returns True if allowed, False if rate-limited.
    fn consume(&self, n: f64) -> bool {
        let mut last = self.last_refill.lock().unwrap();
        let mut tokens = self.tokens.lock().unwrap();

        let elapsed = last.elapsed().as_secs_f64();
        *tokens = (*tokens + elapsed * self.rate).min(self.capacity);
        *last = Instant::now();

        if *tokens >= n {
            *tokens -= n;
            true
        } else {
            false
        }
    }

    /// Return available tokens (snapshot).
    fn available(&self) -> f64 {
        let mut last = self.last_refill.lock().unwrap();
        let mut tokens = self.tokens.lock().unwrap();
        let elapsed = last.elapsed().as_secs_f64();
        *tokens = (*tokens + elapsed * self.rate).min(self.capacity);
        *last = Instant::now();
        *tokens
    }
}

// ============================================================
// Module Registration
// ============================================================

#[pymodule]
fn aletheia_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Existing functions
    m.add_function(wrap_pyfunction!(assess_portfolio_risk_rust, m)?)?;
    m.add_function(wrap_pyfunction!(build_tax_summary_rust, m)?)?;
    m.add_function(wrap_pyfunction!(build_scenario_rust, m)?)?;
    m.add_function(wrap_pyfunction!(options_pricing_rust, m)?)?;
    m.add_function(wrap_pyfunction!(monte_carlo_var_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_technical_indicators_rust, m)?)?;

    // Technical Indicators
    m.add_function(wrap_pyfunction!(calculate_macd_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_bollinger_bands_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_atr_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_vwap_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_obv_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_stochastic_rust, m)?)?;

    // Portfolio Analytics
    m.add_function(wrap_pyfunction!(monte_carlo_portfolio_paths_rust, m)?)?;
    m.add_function(wrap_pyfunction!(correlation_matrix_rust, m)?)?;
    m.add_function(wrap_pyfunction!(rolling_correlation_rust, m)?)?;

    // Backtest Metrics
    m.add_function(wrap_pyfunction!(calculate_sharpe_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_sortino_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_calmar_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_max_drawdown_rust, m)?)?;

    // Memory + Security
    m.add_function(wrap_pyfunction!(bm25_score_rust, m)?)?;
    m.add_class::<RateLimiter>()?;

    // Intelligence Sprint — new functions
    m.add_function(wrap_pyfunction!(brier_score_rust, m)?)?;
    m.add_function(wrap_pyfunction!(regime_detection_rust, m)?)?;
    m.add_function(wrap_pyfunction!(fama_french_rust, m)?)?;
    m.add_function(wrap_pyfunction!(options_flow_metrics_rust, m)?)?;

    Ok(())
}

// ============================================================
// Intelligence Sprint — Brier Score (confidence calibration)
// ============================================================

/// Compute Brier score for a sequence of probability predictions vs. binary outcomes.
/// predictions: probabilities [0.0, 1.0]
/// outcomes: 1.0 if direction correct, 0.0 if wrong
/// Returns: mean squared error (lower = better calibrated)
#[pyfunction]
fn brier_score_rust(predictions: Vec<f64>, outcomes: Vec<f64>) -> PyResult<f64> {
    if predictions.len() != outcomes.len() || predictions.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "predictions and outcomes must be non-empty and same length",
        ));
    }
    let mse: f64 = predictions
        .iter()
        .zip(outcomes.iter())
        .map(|(p, o)| (p - o).powi(2))
        .sum::<f64>()
        / predictions.len() as f64;
    Ok(mse)
}

// ============================================================
// Intelligence Sprint — Regime Detection (Gaussian Mixture + Viterbi)
// ============================================================

/// Detect market regime from a return series using a simplified 2- or 3-state HMM.
/// Returns a dict: {"current_regime": "low_vol_bull", "regime_sequence": [...], "regime_labels": [...]}
#[pyfunction]
fn regime_detection_rust(py: Python<'_>, returns: Vec<f64>, n_regimes: u8) -> PyResult<PyObject> {
    let n = returns.len();
    let k = n_regimes.clamp(2, 3) as usize;
    if n < k + 1 {
        let d = PyDict::new(py);
        d.set_item("current_regime", "insufficient_data")?;
        d.set_item("regime_sequence", Vec::<usize>::new())?;
        d.set_item("regime_labels", Vec::<&str>::new())?;
        return Ok(d.into());
    }

    // Compute mean and std of returns for initialisation
    let mean = returns.iter().sum::<f64>() / n as f64;
    let variance = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / n as f64;
    let std_dev = variance.sqrt().max(1e-8);

    // Sort returns to derive regime thresholds (percentile-based init)
    let mut sorted = returns.clone();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

    // Define regime means/stds based on quantile split
    let regimes: Vec<(f64, f64, &str)> = if k == 2 {
        let median = sorted[n / 2];
        let lower_mean = sorted[..n / 2].iter().sum::<f64>() / (n / 2) as f64;
        let upper_mean = sorted[n / 2..].iter().sum::<f64>() / (n - n / 2) as f64;
        let lower_std = (sorted[..n / 2].iter().map(|r| (r - lower_mean).powi(2)).sum::<f64>() / (n / 2) as f64).sqrt().max(1e-8);
        let upper_std = (sorted[n / 2..].iter().map(|r| (r - upper_mean).powi(2)).sum::<f64>() / (n - n / 2) as f64).sqrt().max(1e-8);
        vec![
            (lower_mean, lower_std, if lower_mean < 0.0 { "bearish" } else { "low_vol_bull" }),
            (upper_mean, upper_std, if upper_mean > 0.005 { "high_vol_bull" } else { "sideways" }),
        ]
    } else {
        let q33 = sorted[n / 3];
        let q67 = sorted[2 * n / 3];
        let _median_unused = q33; // suppress warning
        let slice0 = &sorted[..n / 3];
        let slice1 = &sorted[n / 3..2 * n / 3];
        let slice2 = &sorted[2 * n / 3..];
        let m0 = slice0.iter().sum::<f64>() / slice0.len() as f64;
        let m1 = slice1.iter().sum::<f64>() / slice1.len() as f64;
        let m2 = slice2.iter().sum::<f64>() / slice2.len() as f64;
        let s0 = (slice0.iter().map(|r| (r - m0).powi(2)).sum::<f64>() / slice0.len() as f64).sqrt().max(1e-8);
        let s1 = (slice1.iter().map(|r| (r - m1).powi(2)).sum::<f64>() / slice1.len() as f64).sqrt().max(1e-8);
        let s2 = (slice2.iter().map(|r| (r - m2).powi(2)).sum::<f64>() / slice2.len() as f64).sqrt().max(1e-8);
        let _ = (q33, q67); // suppress unused warning
        vec![
            (m0, s0, "crash"),
            (m1, s1, "sideways"),
            (m2, s2, "bull"),
        ]
    };

    // Viterbi decoding (simplified: greedy nearest-regime assignment)
    let mut sequence: Vec<usize> = returns
        .iter()
        .map(|&r| {
            regimes
                .iter()
                .enumerate()
                .map(|(i, (mu, sigma, _))| {
                    let z = (r - mu) / sigma;
                    (i, -z * z) // log-likelihood approximation
                })
                .max_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal))
                .map(|(i, _)| i)
                .unwrap_or(1)
        })
        .collect();

    // Smooth: apply a simple 3-window majority filter to reduce noise
    let n_seq = sequence.len();
    for i in 1..n_seq - 1 {
        let a = sequence[i - 1];
        let b = sequence[i];
        let c = sequence[i + 1];
        if a == c && a != b {
            sequence[i] = a; // smooth isolated flip
        }
    }

    let current_idx = *sequence.last().unwrap_or(&1);
    let current_label = regimes[current_idx].2;
    let labels: Vec<&str> = regimes.iter().map(|(_, _, l)| *l).collect();

    let d = PyDict::new(py);
    d.set_item("current_regime", current_label)?;
    d.set_item("current_regime_index", current_idx)?;
    d.set_item("regime_sequence", sequence)?;
    d.set_item("regime_labels", labels)?;
    d.set_item("n_regimes", k)?;
    Ok(d.into())
}

// ============================================================
// Intelligence Sprint — Fama-French 3-Factor Model (OLS)
// ============================================================

/// OLS regression: r_i = alpha + beta*(r_m) + s*SMB + h*HML + error
/// All inputs are excess returns (already risk-free adjusted) or raw returns.
/// Returns: {"alpha", "beta", "smb_loading", "hml_loading", "r_squared"}
#[pyfunction]
fn fama_french_rust(
    py: Python<'_>,
    returns: Vec<f64>,
    market_returns: Vec<f64>,
    smb: Vec<f64>,
    hml: Vec<f64>,
) -> PyResult<PyObject> {
    let n = returns.len();
    if n < 5 || market_returns.len() != n || smb.len() != n || hml.len() != n {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "All return series must have the same length (min 5)",
        ));
    }

    // Build design matrix X: [1, r_m, smb, hml] for each observation
    // Solve via OLS: beta = (X'X)^-1 X'y
    // Use closed-form 4x4 matrix inversion via Cramer's rule (no external deps)

    let nf = n as f64;
    // Compute means
    let y_mean = returns.iter().sum::<f64>() / nf;
    let x1_mean = market_returns.iter().sum::<f64>() / nf;
    let x2_mean = smb.iter().sum::<f64>() / nf;
    let x3_mean = hml.iter().sum::<f64>() / nf;

    // Center the variables for numerical stability
    let y_c: Vec<f64> = returns.iter().map(|r| r - y_mean).collect();
    let x1_c: Vec<f64> = market_returns.iter().map(|r| r - x1_mean).collect();
    let x2_c: Vec<f64> = smb.iter().map(|r| r - x2_mean).collect();
    let x3_c: Vec<f64> = hml.iter().map(|r| r - x3_mean).collect();

    // 3x3 normal equations (centered, no intercept — intercept computed separately)
    let xx11: f64 = x1_c.iter().map(|x| x * x).sum();
    let xx12: f64 = x1_c.iter().zip(x2_c.iter()).map(|(a, b)| a * b).sum();
    let xx13: f64 = x1_c.iter().zip(x3_c.iter()).map(|(a, b)| a * b).sum();
    let xx22: f64 = x2_c.iter().map(|x| x * x).sum();
    let xx23: f64 = x2_c.iter().zip(x3_c.iter()).map(|(a, b)| a * b).sum();
    let xx33: f64 = x3_c.iter().map(|x| x * x).sum();
    let xy1: f64 = x1_c.iter().zip(y_c.iter()).map(|(x, y)| x * y).sum();
    let xy2: f64 = x2_c.iter().zip(y_c.iter()).map(|(x, y)| x * y).sum();
    let xy3: f64 = x3_c.iter().zip(y_c.iter()).map(|(x, y)| x * y).sum();

    // Cramer's rule for 3x3 system
    let det = xx11 * (xx22 * xx33 - xx23 * xx23)
        - xx12 * (xx12 * xx33 - xx23 * xx13)
        + xx13 * (xx12 * xx23 - xx22 * xx13);

    let (beta, smb_load, hml_load) = if det.abs() < 1e-12 {
        // Near-singular: fall back to univariate beta
        let beta_uni = if xx11 > 1e-12 { xy1 / xx11 } else { 0.0 };
        (beta_uni, 0.0, 0.0)
    } else {
        let b1 = (xy1 * (xx22 * xx33 - xx23 * xx23)
            - xx12 * (xy2 * xx33 - xx23 * xy3)
            + xx13 * (xy2 * xx23 - xx22 * xy3))
            / det;
        let b2 = (xx11 * (xy2 * xx33 - xx23 * xy3)
            - xy1 * (xx12 * xx33 - xx23 * xx13)
            + xx13 * (xx12 * xy3 - xy2 * xx13))
            / det;
        let b3 = (xx11 * (xx22 * xy3 - xy2 * xx23)
            - xx12 * (xx12 * xy3 - xy2 * xx13)
            + xy1 * (xx12 * xx23 - xx22 * xx13))
            / det;
        (b1, b2, b3)
    };

    let alpha = y_mean - beta * x1_mean - smb_load * x2_mean - hml_load * x3_mean;

    // R-squared
    let y_hat: Vec<f64> = (0..n)
        .map(|i| alpha + beta * market_returns[i] + smb_load * smb[i] + hml_load * hml[i])
        .collect();
    let ss_res: f64 = returns.iter().zip(y_hat.iter()).map(|(y, yh)| (y - yh).powi(2)).sum();
    let ss_tot: f64 = returns.iter().map(|y| (y - y_mean).powi(2)).sum();
    let r_squared = if ss_tot > 1e-12 { 1.0 - ss_res / ss_tot } else { 0.0 };

    let d = PyDict::new(py);
    d.set_item("alpha", (alpha * 1e6).round() / 1e6)?;
    d.set_item("beta", (beta * 1e6).round() / 1e6)?;
    d.set_item("smb_loading", (smb_load * 1e6).round() / 1e6)?;
    d.set_item("hml_loading", (hml_load * 1e6).round() / 1e6)?;
    d.set_item("r_squared", (r_squared * 1e6).round() / 1e6)?;
    Ok(d.into())
}

// ============================================================
// Intelligence Sprint — Options Flow Metrics
// ============================================================

/// Compute put/call ratio, IV rank, and OI-based signal.
/// calls_oi / puts_oi: open interest at each strike
/// calls_iv / puts_iv: implied volatility at each strike
/// iv_52w_high / iv_52w_low: ATM IV extremes over last 52 weeks
#[pyfunction]
fn options_flow_metrics_rust(
    py: Python<'_>,
    calls_oi: Vec<f64>,
    puts_oi: Vec<f64>,
    calls_iv: Vec<f64>,
    puts_iv: Vec<f64>,
    iv_52w_high: f64,
    iv_52w_low: f64,
) -> PyResult<PyObject> {
    if calls_oi.is_empty() || puts_oi.is_empty() {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "OI vectors must be non-empty",
        ));
    }

    let total_calls_oi: f64 = calls_oi.iter().sum();
    let total_puts_oi: f64 = puts_oi.iter().sum();
    let pcr = if total_calls_oi > 0.0 {
        total_puts_oi / total_calls_oi
    } else {
        1.0
    };

    // ATM IV: use weighted average (OI-weighted)
    let total_calls_weight: f64 = calls_oi.iter().sum::<f64>().max(1e-8);
    let total_puts_weight: f64 = puts_oi.iter().sum::<f64>().max(1e-8);
    let calls_avg_iv: f64 = calls_oi
        .iter()
        .zip(calls_iv.iter())
        .map(|(w, iv)| w * iv)
        .sum::<f64>()
        / total_calls_weight;
    let puts_avg_iv: f64 = puts_oi
        .iter()
        .zip(puts_iv.iter())
        .map(|(w, iv)| w * iv)
        .sum::<f64>()
        / total_puts_weight;
    let atm_iv = (calls_avg_iv + puts_avg_iv) / 2.0;

    // IV Rank (0-100)
    let iv_range = (iv_52w_high - iv_52w_low).max(1e-8);
    let iv_rank = ((atm_iv - iv_52w_low) / iv_range * 100.0).clamp(0.0, 100.0);

    // IV Skew: puts_avg_iv > calls_avg_iv → bearish skew
    let iv_skew = puts_avg_iv - calls_avg_iv;

    // OI concentration signal
    let oi_signal = if pcr > 1.3 {
        "BEARISH_OI"  // Heavy put OI = bearish pressure
    } else if pcr < 0.7 {
        "BULLISH_OI"  // Heavy call OI = bullish expectation
    } else {
        "NEUTRAL"
    };

    // Contrarian IV signal: extreme IV = fear/greed extreme
    let iv_signal = if iv_rank > 80.0 {
        "CONTRARIAN_BUY"  // Extreme fear = potential bottom
    } else if iv_rank < 20.0 {
        "CONTRARIAN_SELL"  // Extreme complacency = potential top
    } else {
        "NEUTRAL"
    };

    let d = PyDict::new(py);
    d.set_item("put_call_ratio", (pcr * 1000.0).round() / 1000.0)?;
    d.set_item("iv_rank", (iv_rank * 100.0).round() / 100.0)?;
    d.set_item("iv_skew", (iv_skew * 1000.0).round() / 1000.0)?;
    d.set_item("atm_iv", (atm_iv * 1000.0).round() / 1000.0)?;
    d.set_item("oi_concentration", oi_signal)?;
    d.set_item("iv_signal", iv_signal)?;
    d.set_item("total_calls_oi", total_calls_oi)?;
    d.set_item("total_puts_oi", total_puts_oi)?;
    Ok(d.into())
}
