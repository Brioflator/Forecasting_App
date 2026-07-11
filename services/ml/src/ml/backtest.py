"""Rolling-origin backtesting policy: fold plan, scores, selection (guide §4).

Engine-agnostic — consumes a tidy CV frame (ds, cutoff, y, one column per
candidate) regardless of what produced it. Selection is deliberately humble:
with ≤3 folds the argmin is noisy, so the robust default keeps its seat unless
a challenger beats it by a real margin in most folds (guide §2.4).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from ml.constants import (
    CV_MAX_FOLDS,
    LOW_CONFIDENCE_MASE,
    SELECTION_MARGIN,
    TREND_MIN,
    seasonal_min,
)


@dataclass
class FoldScore:
    fold: int
    cutoff: str  # ISO timestamp of the fold's train/test boundary
    mase: float | None
    smape: float | None
    rmse: float | None


@dataclass
class CandidateScore:
    model: str
    mean_mase: float | None
    mean_smape: float | None
    mean_rmse: float | None
    folds: list[FoldScore] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Selection:
    chosen: str
    low_confidence: bool
    reasons: list[str]


def plan_folds(n: int, horizon: int, m: int | None) -> tuple[int, int]:
    """(h_cv, n_windows). h_cv shrinks below the requested horizon on short
    series so folds exist at all; n_windows is the largest k ≤ CV_MAX_FOLDS
    that leaves the first fold a trainable window. k=0 means skip CV."""
    h_cv = min(horizon, max(1, n // 5))
    min_train = max(seasonal_min(m) if m else 0, TREND_MIN)
    k = min(CV_MAX_FOLDS, (n - min_train) // h_cv) if n > min_train else 0
    return h_cv, max(0, k)


def _mase_scale(train: np.ndarray, m: int | None) -> float:
    """In-sample (seasonal-)naive MAE — the MASE denominator (guide §1)."""
    lag = m if m and len(train) > m else 1
    if len(train) <= lag:
        return 0.0
    return float(np.mean(np.abs(train[lag:] - train[:-lag])))


def _smape(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(2 * np.abs(actual - pred) / (np.abs(actual) + np.abs(pred) + 1e-12)))


def score_candidates(
    cv: pd.DataFrame,
    s: pd.Series,
    names: list[str],
    m: int | None,
) -> list[CandidateScore]:
    """Score each candidate column of the CV frame per fold. A candidate whose
    column is missing or all-NaN (its fit failed inside CV) scores None and
    simply can't win — CV failure is a routing signal, not an error."""
    cutoffs = sorted(cv["cutoff"].unique())
    y_all = s.to_numpy(dtype="float64")
    out: list[CandidateScore] = []
    for name in names:
        folds: list[FoldScore] = []
        for i, cutoff in enumerate(cutoffs):
            fold_df = cv[cv["cutoff"] == cutoff]
            actual = fold_df["y"].to_numpy(dtype="float64")
            pred = (
                fold_df[name].to_numpy(dtype="float64")
                if name in fold_df.columns
                else np.full(len(fold_df), np.nan)
            )
            if not np.all(np.isfinite(pred)) or actual.size == 0:
                folds.append(FoldScore(i, pd.Timestamp(cutoff).isoformat(), None, None, None))
                continue
            train = y_all[: int(s.index.searchsorted(pd.Timestamp(cutoff), side="right"))]
            scale = _mase_scale(train, m)
            mae = float(np.mean(np.abs(actual - pred)))
            folds.append(
                FoldScore(
                    fold=i,
                    cutoff=pd.Timestamp(cutoff).isoformat(),
                    mase=(mae / scale) if scale > 0 else None,
                    smape=_smape(actual, pred),
                    rmse=float(np.sqrt(np.mean((actual - pred) ** 2))),
                )
            )
        out.append(
            CandidateScore(
                model=name,
                mean_mase=_mean([f.mase for f in folds]),
                mean_smape=_mean([f.smape for f in folds]),
                mean_rmse=_mean([f.rmse for f in folds]),
                folds=folds,
            )
        )
    return out


def _mean(vals: list[float | None]) -> float | None:
    kept = [v for v in vals if v is not None and math.isfinite(v)]
    return float(np.mean(kept)) if kept else None


def select(
    scores: list[CandidateScore],
    default_name: str,
    baseline_name: str,
) -> Selection:
    """Keep the robust default unless a challenger beats it by SELECTION_MARGIN
    on mean MASE AND in a majority of folds (guide §2.4). Flags, not gates:
    low confidence is reported, the forecast still ships."""
    by_name = {c.model: c for c in scores}
    valid = [c for c in scores if c.mean_mase is not None]
    if not valid:
        return Selection(chosen=baseline_name, low_confidence=True, reasons=["cv_skipped"])

    default = by_name.get(default_name)
    if default is None or default.mean_mase is None:
        default = by_name.get(baseline_name)
    if default is None or default.mean_mase is None:
        default = min(valid, key=lambda c: c.mean_mase)  # type: ignore[arg-type, return-value]

    best = min(valid, key=lambda c: c.mean_mase)  # type: ignore[arg-type, return-value]
    chosen = default
    if best.model != default.model:
        margin_ok = best.mean_mase < (1 - SELECTION_MARGIN) * default.mean_mase  # type: ignore[operator]
        wins = sum(
            1
            for bf, df in zip(best.folds, default.folds, strict=True)
            if bf.mase is not None and df.mase is not None and bf.mase < df.mase
        )
        scored = sum(1 for f in best.folds if f.mase is not None)
        if margin_ok and scored > 0 and wins >= math.ceil(scored / 2):
            chosen = best

    reasons: list[str] = []
    baseline = by_name.get(baseline_name)
    if (
        baseline is not None
        and baseline.mean_mase is not None
        and chosen.model != baseline.model
        and chosen.mean_mase is not None
        and chosen.mean_mase >= baseline.mean_mase
    ):
        reasons.append("baseline_not_beaten")
    if chosen.mean_mase is not None and chosen.mean_mase > LOW_CONFIDENCE_MASE:
        reasons.append("high_error")
    return Selection(chosen=chosen.model, low_confidence=bool(reasons), reasons=reasons)
