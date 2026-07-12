# The ml service — forecasting in full detail

`services/ml` is the product core: a **stateless** FastAPI service that turns a
list of `(timestamp, value)` points into a forecast with confidence intervals,
an EDA report, and an explicit trust verdict. It has no database, no auth, and
no per-request state — the same input always produces the same output, which is
what makes golden-file testing and horizontal scaling possible.

> Historical note: the original spec (`03-forecasting-and-ml-service.md`)
> described a pmdarima/statsmodels "ladder". The implementation has since moved
> to a **StatsForecast (Nixtla) model zoo selected by rolling-origin
> cross-validation**; pmdarima was removed. The statsmodels ladder survives
> only as the `FORECAST_ENGINE=legacy` fallback and as the naive floor. This
> document describes what runs today.

## Module map

| File | Role |
|---|---|
| `app.py` | FastAPI app: `/forecast`, `/eda`, `/healthz`; the fit-slot semaphore (load shedding) |
| `forecasting.py` | The pipeline orchestrator: gate → route → backtest → select → fit; also the legacy ladder |
| `regularize.py` | Messy input → regular grid: frequency inference, resampling, bounded gap-fill, fit-window cap |
| `profile.py` | Series diagnostics (`SeriesProfile`), winsorization, intermittency test, the validation gate |
| `routing.py` | Diagnostics → candidate model set (policy only, no fitting) |
| `backtest.py` | Fold planning, per-fold scoring (MASE/sMAPE/RMSE), humble selection |
| `sf_engine.py` | The **only** module that imports `statsforecast`; wraps Nixtla models behind `CandidateSpec` |
| `results.py` | `ForecastResult` dataclass + assembly helpers shared by both engines |
| `constants.py` | **Every policy number** in one tunable place |
| `eda.py` | Stationarity (ADF), seasonality strength (STL), ACF/PACF — each with a plain-language reading |
| `errors.py` | `InsufficientData`, `SeriesRejected` — the structured refusals |

Policy lives in three files — `constants.py`, `routing.py`, `backtest.py`.
Executors (`sf_engine.py` and the legacy statsmodels functions) are dumb.
**Tuning the product's forecasting behavior means editing those three files and
nowhere else.**

## The API contract

`POST /forecast` — request (`shared/models/dto.py::ForecastRequest`):

```jsonc
{
  "series": [{"timestamp": "2026-06-01T00:00:00Z", "value": 42.0}, ...],
  "horizon": 24,
  "model": "auto",            // "auto" | "sarima" | "ets" | "prophet"
  "seasonal_period": 24,      // m; null → auto-detect (from metrics.seasonal_period)
  "model_params": {},         // reserved; currently unused by the pipeline
  "confidence": 0.95
}
```

Success (`ForecastResponse`) — the trust fields are additive-with-defaults so
old and new services interoperate during rollout:

```jsonc
{
  "model": "auto_ets",              // the model ACTUALLY used
  "model_params": {"m": 24},
  "frequency": "h",                 // pandas offset alias ml inferred
  "points": [{"timestamp": "...", "predicted": 43.1, "lower": 40.2, "upper": 46.0}, ...],
  "metrics": {"cv_mase": 0.41, "cv_smape": 0.06, "cv_rmse": 3.2, "train_points": 512},
  "warning": null,                  // human-readable caveat(s), "; "-joined
  "route": "seasonal",              // which diagnostic route was taken (auto only)
  "candidates": [ /* per-candidate CV scores incl. per-fold detail */ ],
  "low_confidence": false,          // the explicit "did not earn confidence" flag
  "confidence_reasons": [],         // e.g. ["baseline_not_beaten", "high_error", "cv_skipped", "fallback"]
  "series_profile": { /* n, frequency, impute_frac, pct_zeros, is_intermittent,
                         seasonal_period, seasonal_strength, variance,
                         n_outliers_winsorized, is_constant */ },
  "fit_config": { /* deterministic re-fit recipe: engine, engine_version,
                     model, m, confidence, frequency, train_points, params */ }
}
```

Refusal — HTTP 422 with `ForecastError` (`error` ∈ `insufficient_data` |
`series_rejected` | `invalid_request`, plus `detail` and a machine-readable
`reason` slug for gate rejections). Saturation — HTTP **503 + Retry-After**
when all fit slots are busy (see "Resource guards").

`POST /eda` — `{series, seasonal_period?}` → `{frequency, n_points,
stationarity, seasonality, acf_pacf}`, each section carrying a one-sentence
`plain` reading for non-experts.

## The pipeline, step by step (`forecasting.forecast()`)

### Step 0 — validate & absolute floor

Unknown model or `horizon < 1` → `ValueError` (422). Fewer than `ABS_MIN` (4)
raw points → `InsufficientData` (422).

### Step 1 — regularize (`regularize.py`)

Real polled data is irregular. `regularize()`:

1. Mean-aggregates duplicate timestamps (shouldn't exist given the upsert, but
   defended anyway) and sorts.
2. **Infers frequency** from the median spacing, snapped to the nearest rung of
   `s / min / h / D / W / MS` in log space.
3. **Resamples onto the frequency's own bucket grid.** Load-bearing subtlety:
   the bucket labels come from the resampler (wall-clock aligned), *never* from
   a `date_range` anchored at the first raw timestamp — an unaligned source
   (a webhook firing at :12s past each minute) would otherwise match zero grid
   points and the whole series would regularize to NaN.
4. **Bounded gap-fill**: time-interpolate interior runs up to
   `GAP_FILL_MAX_CONSECUTIVE` (3), then ffill/bfill the remainder, and report
   `impute_frac`. Above `GAP_FILL_MAX_FRACTION` (5%) the response carries a
   "rests heavily on interpolation" warning. Unbounded fill is forbidden —
   inventing a week of data produces confident nonsense.

Then `cap_fit_window()` bounds training to the most recent `MAX_FIT_POINTS`
(512) grid points — per-fit cost must not grow with a metric's lifetime (this
is half of the historical OOM fix; the worker's 5000-point payload cap is the
other half). EDA routes through the same cap so the invariant can't drift.

### Step 2 — gate (`profile.gate`)

Reject-with-reason for asks no model can honestly serve, deliberately narrow:

- collapsed below `ABS_MIN` after regularization → `insufficient_after_regularization`;
- `horizon > HORIZON_MAX_FACTOR (3) × n` → `horizon_too_long`.

Everything past the gate **never hard-fails**: any downstream failure lands on
the naive floor with an explicit `low_confidence` flag.

### Step 3 — winsorize, detect period, profile

- **Winsorize before period detection**: one glitch spike can poison the ACF
  and every fit downstream. Detection is a MAD z-score (`OUTLIER_MAD_Z = 5`)
  on the residual from a 5-point rolling median — robust to trend and level
  shifts, unlike a global z-score. Values are **capped, never dropped**.
  Skipped for intermittent series (spikes *are* the signal there) and below
  `OUTLIER_MIN_POINTS` (10). When the rolling-median residual MAD degenerates
  to 0 (locally monotone series — exactly when a lone spike matters most), it
  falls back to the mean absolute deviation, which the spike inflates, i.e.
  errs conservative.
- **Seasonal period `m`**: the caller's `seasonal_period` (from
  `metrics.seasonal_period`) wins; otherwise `autodetect_period()` — ACF of the
  once-differenced series at candidate lags `[24, 168, 7, 12, 52, 4, 30]`
  (each only if ≤ n/2), best candidate must clear
  `SEASONALITY_ACF_THRESHOLD` (0.3) or the series is treated as non-seasonal.
  Deliberately conservative: real periods should come from metric config.
- **`SeriesProfile`** captures n, frequency, impute_frac, pct_zeros,
  intermittency, m, STL seasonal strength, variance, winsorized count,
  is_constant. It drives routing and travels in the response for the UI.

*Intermittency*: ≥ `INTERMITTENT_ZERO_FRAC` (30%) zeros **and** all values
non-negative (negative values mean zeros are a scale artifact, not absent
demand). Typical for event counts / conversions.

### Step 4 — route to a candidate set (`routing.py`)

Routing is a *hint with fallbacks*, never a hard decision — every candidate
list ends with its baseline, and every failure path lands on the baseline with
an explicit flag.

| Route | When | Candidates (baseline last) |
|---|---|---|
| `short` | n below `max(TREND_MIN, 2m)` | `seasonal_naive` only — no CV, fit the baseline directly and say so |
| `intermittent` | profile says intermittent | `croston`, `tsb`, `naive` |
| `seasonal` | m known and enough history | `auto_ets(m)`, `auto_arima(m)` *(only if m ≤ SF_SEASON_MAX_M = 52)*, `auto_theta(m)`, `seasonal_naive(m)` |
| `non_seasonal` | otherwise | `auto_ets`, `auto_theta`, `naive` |

The set is capped at `MAX_CANDIDATES` (4) by construction — this is what
bounds CV work. A `multi_seasonal` (MSTL) route is a known phase-2 extension
point (needs second-period detection first).

### Step 5 — rolling-origin cross-validation (`backtest.py` + `sf_engine.cross_validate`)

- **Fold plan** (`plan_folds`): CV horizon `h_cv = min(horizon, max(1, n // 5))`
  (shrinks on short series so folds exist at all); number of windows is the
  largest `k ≤ CV_MAX_FOLDS` (3) that leaves the first fold a trainable window
  (`min_train = max(2m, TREND_MIN)`). For non-seasonal routes a (possibly
  misdetected) m is ignored in the plan so it can't inflate `min_train` or
  degenerate the MASE scale. `k = 0` → skip CV, fit the baseline, flag
  `cv_skipped`.
- **Execution**: one vectorized `StatsForecast.cross_validation` call over all
  candidates (`n_jobs=1` — determinism over parallelism). Point forecasts only;
  no interval math inside CV.
- **Scoring** (`score_candidates`): per fold and candidate — **MASE** (MAE
  scaled by the in-sample (seasonal-)naive MAE up to the cutoff), **sMAPE**,
  **RMSE**. A candidate whose fit failed inside CV (missing/NaN column) scores
  `None` and simply can't win — CV failure is a routing signal, not an error.

### Step 6 — humble selection (`backtest.select`)

With ≤3 folds the argmin is noise, so selection is deliberately conservative:

- The **robust default** is `auto_ets` (or the baseline if ETS isn't in the
  set). It keeps its seat unless a challenger beats it by
  `SELECTION_MARGIN` (5%) on **mean MASE** *and* wins a **majority of folds**.
- Trust is **flags, not gates** — the forecast still ships, annotated:
  - `baseline_not_beaten` — the chosen model did not out-score the naive
    baseline;
  - `high_error` — chosen mean MASE > `LOW_CONFIDENCE_MASE` (1.0), i.e. no
    better than naive;
  - `cv_skipped` — too little history to backtest (or CV itself failed);
  - `fallback` — an engine failure landed the request on the floor.
  Any reason present ⇒ `low_confidence: true`.

If the whole CV step throws, the pipeline fits the robust default without a
backtest and flags `cv_skipped` — visible, never silent.

### Step 7 — final fit (`sf_engine.fit_predict`)

The chosen `CandidateSpec` is refit on the full (capped) series with prediction
intervals at the requested level. Model construction
(`sf_engine._make_model`):

- `auto_arima` → `AutoARIMA` with the bounded search (`max_p/q = 3`, seasonal
  `P/Q ≤ 1`) that ended the OOM incident;
- `auto_ets` → `AutoETS`; `auto_theta` → `AutoTheta`;
- `seasonal_naive` → `SeasonalNaive` (or `Naive` when m is unknown);
- `croston` → `CrostonOptimized`; `tsb` → `TSB(alpha_d=alpha_p=0.2)`
  (statsforecast has no auto-TSB).

Intervals: the interval-capable models return analytic bands; the sparse-demand
models (croston/tsb) get honest residual widening —
`ŷ ± z·σ̂·√step` from one-step residuals, the same recipe as the legacy
executors. `assemble_points` raises on non-finite predictions (so the caller
falls to the next fallback) and collapses non-finite bounds onto the
prediction (a zero-width band is honest for a residual-free fit); NaN
diagnostics are dropped before JSON (`clean_metrics`).

If even the final fit fails, `_floor_result` fits the pure-arithmetic
seasonal-naive/drift floor — which **cannot fail** — with
`low_confidence: true` and reason `fallback`.

### Explicit model requests (`model != "auto"`)

The user chose the model, so no CV selection runs: `sarima → auto_arima`,
`ets → auto_ets` (degrading to trend-only below two cycles), with the same
honesty gates (SARIMA needs `m ≤ 52` and two full cycles). `prophet` is not in
the dependency closure and degrades honestly. Any failure substitutes down the
legacy ladder with a warning naming the substitution and `low_confidence`
(reason `fallback`) — never a hard error.

## The legacy engine (`FORECAST_ENGINE=legacy`)

For machines where statsforecast/numba can't install (`sf_engine.available()`
also flips this off automatically on import failure). It is the old
statsmodels ladder: Holt-Winters (if `n ≥ 2m`) → ETS trend (if `n ≥ TREND_MIN`)
→ seasonal-naive/drift floor. No ARIMA rung, no CV, and the response is always
flagged `low_confidence` with a "statistical engine unavailable" warning.
Interval recipe: `ŷ ± z·σ̂(resid)·√step`.

The floor (`_seasonal_naive`) is worth knowing precisely because *everything*
lands on it eventually: with m known it repeats the last full seasonal cycle;
otherwise **drift** (`ŷ_{n+h} = y_n + h·(y_n − y_1)/(n−1)`), with intervals
from one-step naive residuals — genuinely wide bands on short series.

## Resource guards — why the service cannot be worked to death

Root cause of the 2026-07-06 incident: an ever-growing series made single fits
take minutes and gigabytes; the worker's timeout+retry then stacked duplicate
fits on the request threadpool (uvicorn keeps computing abandoned requests)
until OOM. Per-fit work is now bounded **by construction**:

```
window ≤ MAX_FIT_POINTS (512)
× ARIMA only when m ≤ SF_SEASON_MAX_M (52)
× ≤ MAX_CANDIDATES (4) candidates × ≤ CV_MAX_FOLDS (3) folds
× constrained search (max_p/q=3, seasonal P/Q ≤ 1)
```

plus load shedding: both endpoints run behind a
`BoundedSemaphore(MAX_CONCURRENT_FITS = 2)`; a request that can't get a slot in
`FIT_GATE_TIMEOUT_S` (5s) gets **503 + Retry-After** instead of queueing —
the worker treats 5xx as a transport failure and backs off, so load is shed,
not stacked. The worker side holds up its end with the 5000-point payload cap
and a 120s read timeout (never abandon a bounded fit mid-flight). The numba
JIT warm-up runs off-thread at startup, without a fit slot, so the first real
request doesn't pay the compile cost.

**Raise these budgets only together** (window/search ↔ concurrency/timeout);
the incident was exactly that mismatch. AutoARIMA search bounds deliberately
have no settings knob — they live only in `constants.py` so nothing tempts
raising them past the safe ceiling in config.

## EDA (`eda.py`)

Same regularize + window cap as forecasting (robust STL on an unbounded grid is
the same hazard), then:

- **Stationarity**: ADF test (`autolag="AIC"`), guarded for tiny/constant
  series and wrapped so a pathological series yields "inconclusive" rather
  than a 500. `p < 0.05` ⇒ stationary.
- **Seasonality**: `profile.seasonal_strength` — STL-based Wang–Hyndman
  strength `max(0, 1 − Var(resid)/Var(resid + seasonal))`, clamped to [0,1];
  the single shared implementation with the series profile (they must never
  disagree). Bands: > 0.6 strong / ≥ 0.3 moderate / else weak.
- **ACF/PACF** arrays for the frontend chart, `nlags ≤ min(40, n/2)`.

Every section carries a `plain` one-sentence reading — the EDA report is a
product feature for non-experts, not a stats dump.

## Determinism & testing

Deterministic for fixed input + params: `n_jobs=1`, no sampling models, pinned
`statsforecast==2.0.3` (numba-compiled model code must not shift). Test suite
(`services/ml/tests/`, pure in-process, no DB, no HTTP):

- **Golden files** (`test_golden.py` + `tests/golden/*.json`): committed
  input + expected response, numeric fields compared with
  `pytest.approx(rel=1e-3)`, non-numeric exactly. Regeneration is an explicit,
  reviewable `make regen-golden` — never a test-run auto-accept. **Always
  review the diff.**
- **Ladder/route coverage** (`test_ladder.py`, `test_routing.py`): one test per
  route/rung, asserting both the chosen model and the warning/flags.
- **Backtest policy** (`test_backtest.py`): fold plan, scoring, humble
  selection margins.
- **Regularization, profile, contract, explicit-model, resource-guard,
  sf-engine** suites pin the rest.

When bumping `statsforecast`: bump the pin deliberately, `make regen-golden`,
and review the diff as a behavioral change review.
