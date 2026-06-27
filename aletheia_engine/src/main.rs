//! aletheia-engine â€” Tokio + Axum compute sidecar
//!
//! Exposes a lightweight HTTP API for:
//!   POST /compute/indicators        â€” technical indicator suite (no GIL)
//!   POST /compute/portfolio-metrics â€” Sharpe, Sortino, Calmar, max drawdown
//!   POST /compute/monte-carlo       â€” portfolio path simulation
//!   POST /compute/correlation       â€” correlation matrix
//!   GET  /health                    â€” liveness probe
//!
//! Python binds to this via `ComputeClient` (async httpx).

use axum::{
    extract::Json,
    http::{header, Method, StatusCode},
    response::IntoResponse,
    routing::{get, post},
    Router,
};
use serde::{Deserialize, Serialize};
use std::f64::consts::PI;
use std::net::SocketAddr;
use tower_http::cors::{Any, CorsLayer};
use tracing::info;

// ============================================================
// RNG (Xorshift128+, no external deps)
// ============================================================

struct Xorshift128Plus { s: [u64; 2] }
impl Xorshift128Plus {
    fn new(seed: u64) -> Self {
        Self { s: [seed | 1, seed.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407) | 1] }
    }
    fn next_u64(&mut self) -> u64 {
        let mut s1 = self.s[0]; let s0 = self.s[1];
        self.s[0] = s0; s1 ^= s1 << 23;
        self.s[1] = s1 ^ s0 ^ (s1 >> 18) ^ (s0 >> 5);
        self.s[1].wrapping_add(s0)
    }
    fn next_f64(&mut self) -> f64 { (self.next_u64() >> 11) as f64 / (1u64 << 53) as f64 }
    fn next_normal(&mut self) -> f64 {
        let u1 = self.next_f64().max(1e-15); let u2 = self.next_f64();
        (-2.0 * u1.ln()).sqrt() * (2.0 * PI * u2).cos()
    }
}

// ============================================================
// Request / Response types
// ============================================================

#[derive(Deserialize)]
struct IndicatorsRequest {
    closes: Vec<f64>,
    highs: Option<Vec<f64>>,
    lows: Option<Vec<f64>>,
    volumes: Option<Vec<f64>>,
    sma_window: Option<usize>,
    macd_fast: Option<usize>,
    macd_slow: Option<usize>,
    macd_signal: Option<usize>,
    bollinger_window: Option<usize>,
    bollinger_std: Option<f64>,
}

#[derive(Serialize)]
struct IndicatorsResponse {
    sma: Vec<Option<f64>>,
    ema: Vec<Option<f64>>,
    rsi: Vec<Option<f64>>,
    macd_line: Option<Vec<f64>>,
    signal_line: Option<Vec<f64>>,
    macd_histogram: Option<Vec<f64>>,
    bb_upper: Option<Vec<Option<f64>>>,
    bb_middle: Option<Vec<Option<f64>>>,
    bb_lower: Option<Vec<Option<f64>>>,
    vwap: Option<Vec<f64>>,
}

#[derive(Deserialize)]
struct PortfolioMetricsRequest {
    returns: Vec<f64>,
    equity_curve: Option<Vec<f64>>,
    risk_free_rate: Option<f64>,
    periods_per_year: Option<f64>,
}

#[derive(Serialize)]
struct PortfolioMetricsResponse {
    sharpe: f64,
    sortino: f64,
    calmar: f64,
    max_drawdown: f64,
    max_drawdown_pct: f64,
    annualized_return: f64,
    annualized_vol: f64,
}

#[derive(Deserialize)]
struct MonteCarloRequest {
    initial_value: f64,
    daily_vol: f64,
    daily_drift: Option<f64>,
    n_paths: Option<usize>,
    n_days: Option<usize>,
}

#[derive(Serialize)]
struct MonteCarloResponse {
    p5: Vec<f64>,
    p25: Vec<f64>,
    p50: Vec<f64>,
    p75: Vec<f64>,
    p95: Vec<f64>,
    mean_final: f64,
    n_paths: usize,
    n_days: usize,
}

#[derive(Deserialize)]
struct CorrelationRequest {
    returns_matrix: Vec<Vec<f64>>,
    labels: Option<Vec<String>>,
}

#[derive(Serialize)]
struct CorrelationResponse {
    matrix: Vec<Vec<f64>>,
    n_assets: usize,
    labels: Vec<String>,
}

// ============================================================
// Math helpers
// ============================================================

fn ema_series(data: &[f64], period: usize) -> Vec<Option<f64>> {
    let m = 2.0 / (period as f64 + 1.0);
    let mut out = Vec::with_capacity(data.len());
    out.push(Some(data[0]));
    let mut prev = data[0];
    for &x in &data[1..] {
        prev = (x - prev) * m + prev;
        out.push(Some(prev));
    }
    out
}

fn sma_series(data: &[f64], window: usize) -> Vec<Option<f64>> {
    data.iter().enumerate().map(|(i, _)| {
        if i + 1 < window { None }
        else { Some(data[i + 1 - window..=i].iter().sum::<f64>() / window as f64) }
    }).collect()
}

fn rsi_series(data: &[f64]) -> Vec<Option<f64>> {
    let n = data.len(); let window = 14.min(n);
    let mut rsi = vec![None; n];
    if n <= window { return rsi; }
    let mut gains = 0.0; let mut losses = 0.0;
    for i in 1..=window {
        let d = data[i] - data[i - 1];
        if d > 0.0 { gains += d; } else { losses -= d; }
    }
    let mut ag = gains / window as f64; let mut al = losses / window as f64;
    rsi[window] = Some(if al == 0.0 { 100.0 } else { 100.0 - 100.0 / (1.0 + ag / al) });
    for i in (window + 1)..n {
        let d = data[i] - data[i - 1];
        ag = (ag * 13.0 + d.max(0.0)) / 14.0;
        al = (al * 13.0 + (-d).max(0.0)) / 14.0;
        rsi[i] = Some(if al == 0.0 { 100.0 } else { 100.0 - 100.0 / (1.0 + ag / al) });
    }
    rsi
}

fn sharpe(returns: &[f64], rfr: f64, ppy: f64) -> f64 {
    if returns.is_empty() { return 0.0; }
    let mean = returns.iter().sum::<f64>() / returns.len() as f64;
    let var = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / returns.len() as f64;
    let std = var.sqrt();
    if std == 0.0 { return 0.0; }
    (mean - rfr / ppy) / std * ppy.sqrt()
}

fn sortino(returns: &[f64], target: f64, ppy: f64) -> f64 {
    if returns.is_empty() { return 0.0; }
    let mean = returns.iter().sum::<f64>() / returns.len() as f64;
    let downside = (returns.iter().map(|r| (target - r).max(0.0).powi(2)).sum::<f64>() / returns.len() as f64).sqrt();
    if downside == 0.0 { return f64::INFINITY; }
    (mean - target) / downside * ppy.sqrt()
}

fn max_drawdown(equity: &[f64]) -> (f64, f64) {
    let mut peak = equity[0]; let mut mdd = 0.0;
    for &v in equity.iter() {
        if v > peak { peak = v; }
        let dd = if peak > 0.0 { (peak - v) / peak } else { 0.0 };
        if dd > mdd { mdd = dd; }
    }
    (mdd, mdd * 100.0)
}

fn calmar(returns: &[f64], ppy: f64) -> f64 {
    if returns.is_empty() { return 0.0; }
    let ann = returns.iter().sum::<f64>() / returns.len() as f64 * ppy;
    let mut equity = 1.0f64; let mut peak = 1.0f64; let mut mdd = 0.0f64;
    for r in returns { equity *= 1.0 + r; if equity > peak { peak = equity; } let dd = (peak - equity) / peak; if dd > mdd { mdd = dd; } }
    if mdd == 0.0 { f64::INFINITY } else { ann / mdd }
}

// ============================================================
// Route handlers
// ============================================================

async fn health() -> impl IntoResponse {
    (StatusCode::OK, Json(serde_json::json!({ "status": "ok", "service": "aletheia-engine" })))
}

async fn compute_indicators(Json(req): Json<IndicatorsRequest>) -> impl IntoResponse {
    let closes = &req.closes;
    if closes.is_empty() {
        return (StatusCode::BAD_REQUEST, Json(serde_json::json!({ "error": "closes is empty" })));
    }

    let window = req.sma_window.unwrap_or(20);
    let sma = sma_series(closes, window);
    let ema = ema_series(closes, window);
    let rsi = rsi_series(closes);

    // MACD
    let (macd_line_opt, signal_opt, histogram_opt) = if let (Some(fast), Some(slow), Some(sig)) =
        (req.macd_fast, req.macd_slow, req.macd_signal)
    {
        let fast_ema: Vec<f64> = ema_series(closes, fast).into_iter().filter_map(|x| x).collect();
        let slow_ema: Vec<f64> = ema_series(closes, slow).into_iter().filter_map(|x| x).collect();
        let macd: Vec<f64> = fast_ema.iter().zip(slow_ema.iter()).map(|(f, s)| f - s).collect();
        let signal_raw: Vec<f64> = ema_series(&macd, sig).into_iter().filter_map(|x| x).collect();
        let hist: Vec<f64> = macd.iter().zip(signal_raw.iter()).map(|(m, s)| m - s).collect();
        (Some(macd), Some(signal_raw), Some(hist))
    } else {
        (None, None, None)
    };

    // Bollinger Bands
    let (bb_upper, bb_middle, bb_lower) = if let Some(bw) = req.bollinger_window {
        let bstd = req.bollinger_std.unwrap_or(2.0);
        let n = closes.len();
        let mut up = vec![None; n]; let mut mid = vec![None; n]; let mut lo = vec![None; n];
        for i in (bw - 1)..n {
            let sl = &closes[i + 1 - bw..=i];
            let m = sl.iter().sum::<f64>() / bw as f64;
            let std = (sl.iter().map(|x| (x - m).powi(2)).sum::<f64>() / bw as f64).sqrt();
            up[i] = Some(m + bstd * std); mid[i] = Some(m); lo[i] = Some(m - bstd * std);
        }
        (Some(up), Some(mid), Some(lo))
    } else {
        (None, None, None)
    };

    // VWAP
    let vwap_opt = if let (Some(highs), Some(lows), Some(volumes)) =
        (&req.highs, &req.lows, &req.volumes)
    {
        let n = closes.len();
        let mut cum_v = 0.0; let mut cum_tp = 0.0;
        let mut vwap = Vec::with_capacity(n);
        for i in 0..n {
            let tp = (highs.get(i).copied().unwrap_or(closes[i])
                + lows.get(i).copied().unwrap_or(closes[i])
                + closes[i]) / 3.0;
            let vol = volumes.get(i).copied().unwrap_or(0.0);
            cum_tp += tp * vol; cum_v += vol;
            vwap.push(if cum_v > 0.0 { cum_tp / cum_v } else { tp });
        }
        Some(vwap)
    } else { None };

    let resp = IndicatorsResponse {
        sma, ema, rsi,
        macd_line: macd_line_opt,
        signal_line: signal_opt,
        macd_histogram: histogram_opt,
        bb_upper, bb_middle, bb_lower,
        vwap: vwap_opt,
    };
    (StatusCode::OK, Json(serde_json::to_value(resp).unwrap()))
}

async fn compute_portfolio_metrics(Json(req): Json<PortfolioMetricsRequest>) -> impl IntoResponse {
    let rfr = req.risk_free_rate.unwrap_or(0.065); // India risk-free ~ 6.5%
    let ppy = req.periods_per_year.unwrap_or(252.0);
    let returns = &req.returns;

    if returns.is_empty() {
        return (StatusCode::BAD_REQUEST, Json(serde_json::json!({ "error": "returns is empty" })));
    }

    let eq: Vec<f64> = req.equity_curve.as_ref().cloned().unwrap_or_else(|| {
        let mut v = Vec::with_capacity(returns.len() + 1);
        v.push(1.0);
        let mut eq = 1.0;
        for r in returns { eq *= 1.0 + r; v.push(eq); }
        v
    });

    let ann_return = returns.iter().sum::<f64>() / returns.len() as f64 * ppy;
    let mean = returns.iter().sum::<f64>() / returns.len() as f64;
    let var = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / returns.len() as f64;
    let ann_vol = var.sqrt() * ppy.sqrt();
    let (mdd, mdd_pct) = max_drawdown(&eq);

    let resp = PortfolioMetricsResponse {
        sharpe: sharpe(returns, rfr, ppy),
        sortino: sortino(returns, 0.0, ppy),
        calmar: calmar(returns, ppy),
        max_drawdown: mdd,
        max_drawdown_pct: mdd_pct,
        annualized_return: (ann_return * 10000.0).round() / 10000.0,
        annualized_vol: (ann_vol * 10000.0).round() / 10000.0,
    };
    (StatusCode::OK, Json(serde_json::to_value(resp).unwrap()))
}

async fn compute_monte_carlo(Json(req): Json<MonteCarloRequest>) -> impl IntoResponse {
    let n_paths = req.n_paths.unwrap_or(1000).min(10_000);
    let n_days = req.n_days.unwrap_or(252).min(2_520);
    let drift = req.daily_drift.unwrap_or(0.0);

    let mut rng = Xorshift128Plus::new(0xDEAD_C0DE_1234_5678);
    let mut paths: Vec<Vec<f64>> = Vec::with_capacity(n_paths);

    for _ in 0..n_paths {
        let mut path = Vec::with_capacity(n_days + 1);
        let mut v = req.initial_value;
        path.push(v);
        for _ in 0..n_days {
            v *= 1.0 + drift + req.daily_vol * rng.next_normal();
            path.push(v);
        }
        paths.push(path);
    }

    let pcts = [5usize, 25, 50, 75, 95];
    let mut series: Vec<Vec<f64>> = (0..5).map(|_| Vec::with_capacity(n_days + 1)).collect();

    for day in 0..=n_days {
        let mut vals: Vec<f64> = paths.iter().map(|p| p[day]).collect();
        vals.sort_by(|a, b| a.partial_cmp(b).unwrap());
        for (i, &p) in pcts.iter().enumerate() {
            let idx = (p * n_paths / 100).min(n_paths - 1);
            series[i].push((vals[idx] * 100.0).round() / 100.0);
        }
    }

    let final_vals: Vec<f64> = paths.iter().map(|p| p[n_days]).collect();
    let mean_final = final_vals.iter().sum::<f64>() / n_paths as f64;

    let resp = MonteCarloResponse {
        p5: series[0].clone(), p25: series[1].clone(), p50: series[2].clone(),
        p75: series[3].clone(), p95: series[4].clone(),
        mean_final: (mean_final * 100.0).round() / 100.0,
        n_paths, n_days,
    };
    (StatusCode::OK, Json(serde_json::to_value(resp).unwrap()))
}

async fn compute_correlation(Json(req): Json<CorrelationRequest>) -> impl IntoResponse {
    let rm = &req.returns_matrix;
    let n = rm.len();
    if n == 0 {
        return (StatusCode::BAD_REQUEST, Json(serde_json::json!({ "error": "empty matrix" })));
    }

    let mean = |v: &[f64]| v.iter().sum::<f64>() / v.len() as f64;
    let std = |v: &[f64]| { let m = mean(v); (v.iter().map(|x|(x-m).powi(2)).sum::<f64>() / v.len() as f64).sqrt() };

    let mut matrix = vec![vec![0.0f64; n]; n];
    for i in 0..n {
        matrix[i][i] = 1.0;
        let mi = mean(&rm[i]); let si = std(&rm[i]);
        for j in (i + 1)..n {
            let mj = mean(&rm[j]); let sj = std(&rm[j]);
            let l = rm[i].len().min(rm[j].len());
            let cov = (0..l).map(|k| (rm[i][k] - mi) * (rm[j][k] - mj)).sum::<f64>() / l as f64;
            let c = if si * sj > 0.0 { cov / (si * sj) } else { 0.0 };
            matrix[i][j] = c; matrix[j][i] = c;
        }
    }

    let labels = req.labels.unwrap_or_else(|| (0..n).map(|i| format!("asset_{}", i)).collect());
    let resp = CorrelationResponse { matrix, n_assets: n, labels };
    (StatusCode::OK, Json(serde_json::to_value(resp).unwrap()))
}


// ============================================================
// Intelligence Sprint -- Regime Detection
// ============================================================

#[derive(Deserialize)]
struct RegimeRequest { returns: Vec<f64>, n_regimes: Option<u8> }
#[derive(Serialize)]
struct RegimeResponse { current_regime: String, current_regime_index: usize, regime_sequence: Vec<usize>, regime_labels: Vec<String>, n_regimes: usize }

async fn compute_regime(Json(req): Json<RegimeRequest>) -> impl IntoResponse {
    let k = req.n_regimes.unwrap_or(3).clamp(2, 3) as usize;
    let returns = &req.returns; let n = returns.len();
    if n < k + 1 {
        let r = RegimeResponse { current_regime: "insufficient_data".into(), current_regime_index: 0, regime_sequence: vec![], regime_labels: vec![], n_regimes: k };
        return (StatusCode::OK, Json(serde_json::to_value(r).unwrap()));
    }
    let mut sorted = returns.clone();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let mk = |sl: &[f64], label: &str| -> (f64, f64, String) { let m=sl.iter().sum::<f64>()/sl.len() as f64; let s=(sl.iter().map(|r|(r-m).powi(2)).sum::<f64>()/sl.len() as f64).sqrt().max(1e-8); (m,s,label.to_string()) };
    let regimes: Vec<(f64,f64,String)> = if k==2 { vec![mk(&sorted[..n/2],if sorted[..n/2].iter().sum::<f64>()/(n/2) as f64<0.0{"bearish"}else{"low_vol_bull"}),mk(&sorted[n/2..],"high_vol_bull")] } else { vec![mk(&sorted[..n/3],"crash"),mk(&sorted[n/3..2*n/3],"sideways"),mk(&sorted[2*n/3..],"bull")] };
    let mut seq: Vec<usize>=returns.iter().map(|&r|{regimes.iter().enumerate().map(|(i,(mu,sg,_))|{let z=(r-mu)/sg;(i,-z*z)}).max_by(|a,b|a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal)).map(|(i,_)|i).unwrap_or(1)}).collect();
    for i in 1..seq.len().saturating_sub(1){if seq[i-1]==seq[i+1]&&seq[i-1]!=seq[i]{seq[i]=seq[i-1];}}
    let cur=*seq.last().unwrap_or(&1);
    (StatusCode::OK, Json(serde_json::to_value(RegimeResponse{current_regime:regimes[cur].2.clone(),current_regime_index:cur,regime_sequence:seq,regime_labels:regimes.into_iter().map(|(_,_,l)|l).collect(),n_regimes:k}).unwrap()))
}

// ============================================================
// Intelligence Sprint -- Fama-French Factor Model
// ============================================================

#[derive(Deserialize)]
struct FactorModelRequest { returns: Vec<f64>, market: Vec<f64>, smb: Vec<f64>, hml: Vec<f64> }
#[derive(Serialize)]
struct FactorModelResponse { alpha: f64, beta: f64, smb_loading: f64, hml_loading: f64, r_squared: f64 }

async fn compute_factor_model(Json(req): Json<FactorModelRequest>) -> impl IntoResponse {
    let n=req.returns.len();
    if n<5||req.market.len()!=n||req.smb.len()!=n||req.hml.len()!=n { return (StatusCode::BAD_REQUEST,Json(serde_json::json!({"error":"Series length mismatch or min 5 required"}))); }
    let nf=n as f64; let (ym,x1m,x2m,x3m)=(req.returns.iter().sum::<f64>()/nf,req.market.iter().sum::<f64>()/nf,req.smb.iter().sum::<f64>()/nf,req.hml.iter().sum::<f64>()/nf);
    let yc: Vec<f64>=req.returns.iter().map(|r|r-ym).collect(); let x1c: Vec<f64>=req.market.iter().map(|r|r-x1m).collect(); let x2c: Vec<f64>=req.smb.iter().map(|r|r-x2m).collect(); let x3c: Vec<f64>=req.hml.iter().map(|r|r-x3m).collect();
    let xx11: f64=x1c.iter().map(|x|x*x).sum(); let xx12: f64=x1c.iter().zip(x2c.iter()).map(|(a,b)|a*b).sum(); let xx13: f64=x1c.iter().zip(x3c.iter()).map(|(a,b)|a*b).sum(); let xx22: f64=x2c.iter().map(|x|x*x).sum(); let xx23: f64=x2c.iter().zip(x3c.iter()).map(|(a,b)|a*b).sum(); let xx33: f64=x3c.iter().map(|x|x*x).sum();
    let xy1: f64=x1c.iter().zip(yc.iter()).map(|(x,y)|x*y).sum(); let xy2: f64=x2c.iter().zip(yc.iter()).map(|(x,y)|x*y).sum(); let xy3: f64=x3c.iter().zip(yc.iter()).map(|(x,y)|x*y).sum();
    let det=xx11*(xx22*xx33-xx23*xx23)-xx12*(xx12*xx33-xx23*xx13)+xx13*(xx12*xx23-xx22*xx13);
    let (beta,sl,hl)=if det.abs()<1e-12{(if xx11>1e-12{xy1/xx11}else{0.0},0.0,0.0)}else{((xy1*(xx22*xx33-xx23*xx23)-xx12*(xy2*xx33-xx23*xy3)+xx13*(xy2*xx23-xx22*xy3))/det,(xx11*(xy2*xx33-xx23*xy3)-xy1*(xx12*xx33-xx23*xx13)+xx13*(xx12*xy3-xy2*xx13))/det,(xx11*(xx22*xy3-xy2*xx23)-xx12*(xx12*xy3-xy2*xx13)+xy1*(xx12*xx23-xx22*xx13))/det)};
    let alpha=ym-beta*x1m-sl*x2m-hl*x3m; let yhat: Vec<f64>=(0..n).map(|i|alpha+beta*req.market[i]+sl*req.smb[i]+hl*req.hml[i]).collect();
    let ss_res: f64=req.returns.iter().zip(yhat.iter()).map(|(y,yh)|(y-yh).powi(2)).sum(); let ss_tot: f64=req.returns.iter().map(|y|(y-ym).powi(2)).sum();
    let r6=|x:f64|(x*1e6).round()/1e6; let r2=if ss_tot>1e-12{1.0-ss_res/ss_tot}else{0.0};
    (StatusCode::OK,Json(serde_json::to_value(FactorModelResponse{alpha:r6(alpha),beta:r6(beta),smb_loading:r6(sl),hml_loading:r6(hl),r_squared:r6(r2)}).unwrap()))
}

// ============================================================
// Intelligence Sprint -- Options Flow
// ============================================================

#[derive(Deserialize)]
struct OptionsFlowRequest { calls_oi: Vec<f64>, puts_oi: Vec<f64>, calls_iv: Vec<f64>, puts_iv: Vec<f64>, iv_52w_high: f64, iv_52w_low: f64 }
#[derive(Serialize)]
struct OptionsFlowResponse { put_call_ratio: f64, iv_rank: f64, iv_skew: f64, atm_iv: f64, oi_concentration: String, iv_signal: String, total_calls_oi: f64, total_puts_oi: f64 }

async fn compute_options_flow(Json(req): Json<OptionsFlowRequest>) -> impl IntoResponse {
    if req.calls_oi.is_empty()||req.puts_oi.is_empty() { return (StatusCode::BAD_REQUEST,Json(serde_json::json!({"error":"OI vectors must be non-empty"}))); }
    let (tc,tp)=(req.calls_oi.iter().sum::<f64>(),req.puts_oi.iter().sum::<f64>());
    let pcr=if tc>0.0{tp/tc}else{1.0};
    let civ=req.calls_oi.iter().zip(req.calls_iv.iter()).map(|(w,iv)|w*iv).sum::<f64>()/tc.max(1e-8);
    let piv=req.puts_oi.iter().zip(req.puts_iv.iter()).map(|(w,iv)|w*iv).sum::<f64>()/tp.max(1e-8);
    let atm_iv=(civ+piv)/2.0; let iv_rank=((atm_iv-req.iv_52w_low)/(req.iv_52w_high-req.iv_52w_low).max(1e-8)*100.0).clamp(0.0,100.0);
    let oi_conc=if pcr>1.3{"BEARISH_OI"}else if pcr<0.7{"BULLISH_OI"}else{"NEUTRAL"};
    let iv_sig=if iv_rank>80.0{"CONTRARIAN_BUY"}else if iv_rank<20.0{"CONTRARIAN_SELL"}else{"NEUTRAL"};
    let r3=|x:f64|(x*1000.0).round()/1000.0;
    (StatusCode::OK,Json(serde_json::to_value(OptionsFlowResponse{put_call_ratio:r3(pcr),iv_rank:r3(iv_rank),iv_skew:r3(piv-civ),atm_iv:r3(atm_iv),oi_concentration:oi_conc.into(),iv_signal:iv_sig.into(),total_calls_oi:tc,total_puts_oi:tp}).unwrap()))
}
// ============================================================
// Main
// ============================================================

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(
            std::env::var("RUST_LOG")
                .unwrap_or_else(|_| "aletheia_engine=info,tower_http=warn".into()),
        )
        .init();

    let cors = CorsLayer::new()
        .allow_origin(Any)
        .allow_methods([Method::GET, Method::POST])
        .allow_headers([header::CONTENT_TYPE]);

    let app = Router::new()
        .route("/health", get(health))
        .route("/compute/indicators", post(compute_indicators))
        .route("/compute/portfolio-metrics", post(compute_portfolio_metrics))
        .route("/compute/monte-carlo", post(compute_monte_carlo))
        .route("/compute/correlation", post(compute_correlation))
        // Intelligence Sprint
        .route("/compute/regime", post(compute_regime))
        .route("/compute/factor-model", post(compute_factor_model))
        .route("/compute/options-flow", post(compute_options_flow))
        .layer(cors);

    let host = std::env::var("ALETHEIA_ENGINE_HOST").unwrap_or_else(|_| "127.0.0.1".into());
    let port: u16 = std::env::var("ALETHEIA_ENGINE_PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(18899);

    let addr: SocketAddr = format!("{}:{}", host, port).parse().unwrap();
    info!("aletheia-engine listening on {}", addr);

    let listener = tokio::net::TcpListener::bind(addr).await.unwrap();
    axum::serve(listener, app).await.unwrap();
}

