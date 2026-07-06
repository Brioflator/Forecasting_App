"""All forecasting policy constants in one tunable place (doc 3 §4, plan 05 §2.4).

Thresholds live here so the ladder and its gates are testable and adjustable
without touching executor code.
"""

# Minimum-series-length thresholds (doc 3 §4).
ABS_MIN = 4  # absolute floor to return anything → seasonal-naive / drift
TREND_MIN = 10  # non-seasonal trend model (ETS trend / ARIMA)


def seasonal_min(m: int) -> int:
    """Two full cycles — the practical floor for a seasonal fit (doc 3 §4)."""
    return 2 * m


# autodetect_period (plan 05 §2.4): candidate cadences, most-common first.
CANDIDATE_PERIODS = [24, 168, 7, 12, 52, 4, 30]
SEASONALITY_ACF_THRESHOLD = 0.3  # ACF must clear this to call a period seasonal

# Seasonality-strength bands for the /eda plain reading (plan 05 §2.4).
SEASONALITY_STRONG = 0.6
SEASONALITY_MODERATE = 0.3

# Bounded gap-fill (doc 3 §5) — defaults mirror settings GAP_FILL_* knobs.
GAP_FILL_MAX_CONSECUTIVE = 3
GAP_FILL_MAX_FRACTION = 0.05

# auto_arima search bounds (doc 3 §6 latency; plan 05 §2.3 AUTO_ARIMA_MAX_*).
AUTO_ARIMA_MAX_P = 3
AUTO_ARIMA_MAX_Q = 3
AUTO_ARIMA_MAX_SEASONAL = 1  # max P and Q for the seasonal component
AUTO_ARIMA_MAXITER = 30  # per-candidate optimizer iterations

# ── Resource guards (reliability) ─────────────────────────────────────────
# Root cause these bound: an ever-growing series made single auto_arima fits
# take minutes and gigabytes; abandoned/retried requests then piled up on the
# request threadpool until the process ran out of memory.
#
# Per-fit work is bounded BY CONSTRUCTION:
#   window ≤ MAX_FIT_POINTS  ×  SARIMA only when m ≤ SARIMA_MAX_M
#   × constrained stepwise search (bounds above)
# and the app sheds load (503) instead of stacking concurrent fits.
MAX_FIT_POINTS = 512  # regularized grid points used for fitting
SARIMA_MAX_M = 24  # above this, the seasonal rung is Holt-Winters (O(n)), not SARIMA
MAX_CONCURRENT_FITS = 2  # heavy fits allowed at once (semaphore in app.py)
FIT_GATE_TIMEOUT_S = 5.0  # how long a request waits for a fit slot before 503
