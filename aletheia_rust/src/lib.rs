use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;

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
    let effective_total_value = if total_value == 0.0 { 1.0 } else { total_value };

    let mut weights = HashMap::new();
    for (sym, val) in &values {
        weights.insert(sym.clone(), val / effective_total_value);
    }

    let max_weight: f64 = weights.values().cloned().fold(0.0, f64::max);

    let mut daily_move_estimate = 0.0;
    for (symbol, _qty, open_opt, close) in holdings_data {
        if let Some(open) = open_opt {
            if open != 0.0 {
                let weight = weights.get(&symbol).cloned().unwrap_or(0.0);
                daily_move_estimate += ((close - open) / open).abs() * weight;
            }
        }
    }

    let portfolio_var_95 = -(effective_total_value * (daily_move_estimate * 1.65).max(0.01));
    let concentration_risk = (max_weight * 10000.0).round() / 10000.0; // round to 4 decimals

    let mut regime = "balanced".to_string();
    let mut alerts = Vec::new();

    if max_weight > 0.4 {
        regime = "concentrated".to_string();
        alerts.push("Single-position exposure is above 40% of portfolio market value.".to_string());
    }
    if daily_move_estimate > 0.04 {
        regime = "volatile".to_string();
        alerts.push("Observed mark-to-market volatility is elevated for the sampled holdings.".to_string());
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

#[pyfunction]
fn build_tax_summary_rust(
    py: Python<'_>,
    tax_profile_str: String,
    pre_tax_profit: f64,
) -> PyResult<PyObject> {
    let tax_drag_pct = match tax_profile_str.to_lowercase().as_str() {
        "equity" => 0.15,
        "fno" => 0.175,
        "crypto" => 0.15,
        "mutual_fund" => 0.20,
        _ => 0.15,
    };

    let estimated_tax_amount = pre_tax_profit.max(0.0) * tax_drag_pct;
    let post_tax_profit = pre_tax_profit - estimated_tax_amount;

    let result = PyDict::new_bound(py);
    result.set_item("tax_profile", tax_profile_str)?;
    result.set_item("pre_tax_profit", (pre_tax_profit * 100.0).round() / 100.0)?;
    result.set_item("tax_drag_pct", (tax_drag_pct * 10000.0).round() / 100.0)?;
    result.set_item("estimated_tax_amount", (estimated_tax_amount * 100.0).round() / 100.0)?;
    result.set_item("post_tax_profit", (post_tax_profit * 100.0).round() / 100.0)?;

    Ok(result.into())
}

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

    let avg_price_denom = if average_price == 0.0 { 1e-6 } else { average_price };
    let move_pct = (close - average_price) / avg_price_denom;
    let projected_return_pct = (move_pct * 100.0) + (conviction * 8.0);
    let pre_tax_profit = quantity * average_price * (projected_return_pct / 100.0);

    let tax_drag_pct = match tax_profile_str.to_lowercase().as_str() {
        "equity" => 0.15,
        "fno" => 0.175,
        "crypto" => 0.15,
        "mutual_fund" => 0.20,
        _ => 0.15,
    };

    let estimated_tax_amount = pre_tax_profit.max(0.0) * tax_drag_pct;
    let post_tax_profit = pre_tax_profit - estimated_tax_amount;

    let total_cost = quantity * average_price;
    let total_cost_denom = if total_cost == 0.0 { 1e-6 } else { total_cost };
    let projected_post_tax_return_pct = (post_tax_profit / total_cost_denom) * 100.0;

    let projected_sharpe = (projected_return_pct / 12.0).min(2.5).max(-1.0);

    let rationale = vec![
        format!("Projected pre-tax return is {:.2}% based on mark-to-market drift and conviction.", projected_return_pct),
        format!("Estimated tax drag for {} is {:.2}%.", tax_profile_str, tax_drag_pct * 100.0),
    ];

    let tax_summary = PyDict::new_bound(py);
    tax_summary.set_item("tax_profile", tax_profile_str)?;
    tax_summary.set_item("pre_tax_profit", (pre_tax_profit * 100.0).round() / 100.0)?;
    tax_summary.set_item("tax_drag_pct", (tax_drag_pct * 10000.0).round() / 100.0)?;
    tax_summary.set_item("estimated_tax_amount", (estimated_tax_amount * 100.0).round() / 100.0)?;
    tax_summary.set_item("post_tax_profit", (post_tax_profit * 100.0).round() / 100.0)?;

    let scenario = PyDict::new_bound(py);
    scenario.set_item("scenario_name", "base_tax_aware_projection")?;
    scenario.set_item("projected_return_pct", (projected_return_pct * 100.0).round() / 100.0)?;
    scenario.set_item("projected_post_tax_return_pct", (projected_post_tax_return_pct * 100.0).round() / 100.0)?;
    scenario.set_item("projected_sharpe", (projected_sharpe * 100.0).round() / 100.0)?;
    scenario.set_item("tax_summary", tax_summary)?;

    let result = PyDict::new_bound(py);
    result.set_item("symbol", symbol)?;
    result.set_item("scenario", scenario)?;
    let raw_confidence = 0.45 + conviction * 0.4;
    let confidence = raw_confidence.min(0.9).max(0.2);
    result.set_item("confidence", (confidence * 100.0).round() / 100.0)?;
    result.set_item("rationale", rationale)?;

    Ok(result.into())
}

use std::f64::consts::PI;
fn norm_cdf(x: f64) -> f64 {
    // A standard approximation for the standard normal CDF
    let l = x.abs();
    let k = 1.0 / (1.0 + 0.2316419 * l);
    let k_sum = k * (0.319381530 + k * (-0.356563782 + k * (1.781477937 + k * (-1.821255978 + 1.330274429 * k))));
    let approx = 1.0 - (1.0 / (2.0 * PI).sqrt()) * (-l * l / 2.0).exp() * k_sum;
    if x < 0.0 {
        1.0 - approx
    } else {
        approx
    }
}

fn norm_pdf(x: f64) -> f64 {
    (1.0 / (2.0 * PI).sqrt()) * (-x * x / 2.0).exp()
}

#[pyfunction]
fn options_pricing_rust(
    py: Python<'_>,
    s: f64, // Spot price
    k: f64, // Strike price
    t: f64, // Time to maturity (years)
    r: f64, // Risk-free rate
    v: f64, // Volatility
    is_call: bool,
) -> PyResult<PyObject> {
    if t <= 0.0 || v <= 0.0 {
        // Expired or zero vol, intrinsic value only
        let price = if is_call { (s - k).max(0.0) } else { (k - s).max(0.0) };
        let result = PyDict::new_bound(py);
        result.set_item("price", price)?;
        result.set_item("delta", if price > 0.0 { if is_call { 1.0 } else { -1.0 } } else { 0.0 })?;
        result.set_item("gamma", 0.0)?;
        result.set_item("theta", 0.0)?;
        result.set_item("vega", 0.0)?;
        return Ok(result.into());
    }

    let d1 = ((s / k).ln() + (r + v * v / 2.0) * t) / (v * t.sqrt());
    let d2 = d1 - v * t.sqrt();

    let nd1 = norm_cdf(d1);
    let nd2 = norm_cdf(d2);
    let n_neg_d1 = norm_cdf(-d1);
    let n_neg_d2 = norm_cdf(-d2);
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

    let result = PyDict::new_bound(py);
    result.set_item("price", price)?;
    result.set_item("delta", delta)?;
    result.set_item("gamma", gamma)?;
    result.set_item("theta", theta)?; // Per year
    result.set_item("vega", vega)?; // Per 1% change, usually reported as vega/100, but raw here

    Ok(result.into())
}

#[pyfunction]
fn monte_carlo_var_rust(
    py: Python<'_>,
    portfolio_value: f64,
    daily_vol: f64,
    simulations: usize,
    confidence_level: f64,
) -> PyResult<PyObject> {
    // A simplified pseudo-random Monte Carlo for demonstration.
    // In production, we'd use the `rand` crate and Cholesky decomposition.
    // For this engine, we'll approximate the VaR by generating N normally distributed random variables.
    
    // We use a simple linear congruential generator for standard normal approximations (Box-Muller)
    let mut losses = Vec::with_capacity(simulations);
    
    let mut seed = 123456789u32;
    let mut lcg = || {
        seed = seed.wrapping_mul(1664525).wrapping_add(1013904223);
        (seed as f64) / (std::u32::MAX as f64)
    };

    for _ in 0..(simulations / 2 + 1) {
        let u1 = lcg().max(1e-10);
        let u2 = lcg();
        
        let z0 = (-2.0 * u1.ln()).sqrt() * (2.0 * PI * u2).cos();
        let z1 = (-2.0 * u1.ln()).sqrt() * (2.0 * PI * u2).sin();

        // Calculate loss (positive number means loss)
        let pnl0 = portfolio_value * daily_vol * z0;
        let pnl1 = portfolio_value * daily_vol * z1;
        
        losses.push(-pnl0);
        losses.push(-pnl1);
    }
    
    losses.truncate(simulations);
    
    // Sort losses ascending
    // Actually we want the 95th percentile of losses, so sort descending and pick index
    losses.sort_by(|a, b| b.partial_cmp(a).unwrap_or(std::cmp::Ordering::Equal));
    
    let index = ((1.0 - confidence_level) * (simulations as f64)) as usize;
    let var = if index < losses.len() { losses[index] } else { losses[losses.len() - 1] };

    let result = PyDict::new_bound(py);
    result.set_item("var", var)?;
    result.set_item("simulations", simulations)?;
    result.set_item("confidence_level", confidence_level)?;

    Ok(result.into())
}

#[pyfunction]
fn calculate_technical_indicators_rust(
    py: Python<'_>,
    closes: Vec<f64>,
    window: usize,
) -> PyResult<PyObject> {
    let mut sma = Vec::new();
    let mut ema = Vec::new();
    
    // SMA
    for i in 0..closes.len() {
        if i + 1 < window {
            sma.push(None);
        } else {
            let sum: f64 = closes[i + 1 - window..=i].iter().sum();
            sma.push(Some(sum / window as f64));
        }
    }

    // EMA
    let multiplier = 2.0 / (window as f64 + 1.0);
    let mut current_ema = closes[0];
    ema.push(Some(current_ema));
    for i in 1..closes.len() {
        current_ema = (closes[i] - current_ema) * multiplier + current_ema;
        ema.push(Some(current_ema));
    }

    // RSI (14 period default approximation)
    let mut rsi = vec![None; closes.len()];
    let rsi_window = 14.min(closes.len());
    if closes.len() > rsi_window {
        let mut gains = 0.0;
        let mut losses = 0.0;
        for i in 1..=rsi_window {
            let change = closes[i] - closes[i-1];
            if change > 0.0 { gains += change; }
            else { losses -= change; }
        }
        let mut avg_gain = gains / rsi_window as f64;
        let mut avg_loss = losses / rsi_window as f64;
        
        if avg_loss == 0.0 {
            rsi[rsi_window] = Some(100.0);
        } else {
            rsi[rsi_window] = Some(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)));
        }

        for i in (rsi_window + 1)..closes.len() {
            let change = closes[i] - closes[i-1];
            let gain = if change > 0.0 { change } else { 0.0 };
            let loss = if change < 0.0 { -change } else { 0.0 };
            
            avg_gain = (avg_gain * 13.0 + gain) / 14.0;
            avg_loss = (avg_loss * 13.0 + loss) / 14.0;
            
            if avg_loss == 0.0 {
                rsi[i] = Some(100.0);
            } else {
                rsi[i] = Some(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)));
            }
        }
    }

    let result = PyDict::new_bound(py);
    result.set_item("sma", sma)?;
    result.set_item("ema", ema)?;
    result.set_item("rsi", rsi)?;

    Ok(result.into())
}

#[pymodule]
fn aletheia_rust(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(assess_portfolio_risk_rust, m)?)?;
    m.add_function(wrap_pyfunction!(build_tax_summary_rust, m)?)?;
    m.add_function(wrap_pyfunction!(build_scenario_rust, m)?)?;
    m.add_function(wrap_pyfunction!(options_pricing_rust, m)?)?;
    m.add_function(wrap_pyfunction!(monte_carlo_var_rust, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_technical_indicators_rust, m)?)?;
    Ok(())
}
