"""Backtest policy (guide §4 step 4) — driven with fabricated CV frames and
scores so none of this depends on statsforecast being installed."""

import numpy as np
import pandas as pd

from ml.backtest import (
    CandidateScore,
    FoldScore,
    plan_folds,
    score_candidates,
    select,
)
from ml.constants import CV_MAX_FOLDS, LOW_CONFIDENCE_MASE, TREND_MIN


class TestPlanFolds:
    def test_long_series_gets_max_folds(self) -> None:
        h_cv, k = plan_folds(n=512, horizon=24, m=24)
        assert h_cv == 24
        assert k == CV_MAX_FOLDS

    def test_h_cv_shrinks_on_short_series(self) -> None:
        h_cv, _ = plan_folds(n=30, horizon=24, m=None)
        assert h_cv == 6  # n // 5

    def test_no_folds_when_train_would_vanish(self) -> None:
        _, k = plan_folds(n=TREND_MIN, horizon=5, m=None)
        assert k == 0

    def test_seasonal_min_train_respected(self) -> None:
        # n=30, m=12 → min_train=24; h_cv=min(6, 6)=6 → k = (30-24)//6 = 1
        h_cv, k = plan_folds(n=30, horizon=6, m=12)
        assert (h_cv, k) == (6, 1)

    def test_never_negative(self) -> None:
        _, k = plan_folds(n=5, horizon=100, m=52)
        assert k == 0


def _cv_frame(s: pd.Series, h_cv: int, k: int, preds: dict[str, float]) -> pd.DataFrame:
    """A tidy CV frame where each candidate predicts a constant offset from y."""
    rows = []
    n = len(s)
    for fold in range(k):
        cutoff_pos = n - (k - fold) * h_cv
        cutoff = s.index[cutoff_pos - 1]
        for j in range(h_cv):
            y = float(s.iloc[cutoff_pos + j])
            row = {"ds": s.index[cutoff_pos + j], "cutoff": cutoff, "y": y}
            for name, offset in preds.items():
                row[name] = y + offset
            rows.append(row)
    return pd.DataFrame(rows)


def _series(n: int = 60) -> pd.Series:
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.Series(100 + np.sin(np.arange(n, dtype="float64")), index=idx)


class TestScoreCandidates:
    def test_better_offset_scores_lower(self) -> None:
        s = _series()
        cv = _cv_frame(s, h_cv=6, k=2, preds={"good": 0.1, "bad": 5.0})
        scores = score_candidates(cv, s, ["good", "bad"], m=None)
        by = {c.model: c for c in scores}
        assert by["good"].mean_mase < by["bad"].mean_mase
        assert len(by["good"].folds) == 2
        assert all(f.mase is not None for f in by["good"].folds)

    def test_missing_column_scores_none(self) -> None:
        s = _series()
        cv = _cv_frame(s, h_cv=6, k=2, preds={"good": 0.1})
        scores = score_candidates(cv, s, ["good", "absent"], m=None)
        by = {c.model: c for c in scores}
        assert by["absent"].mean_mase is None

    def test_nan_predictions_score_none(self) -> None:
        s = _series()
        cv = _cv_frame(s, h_cv=6, k=1, preds={"broken": 0.0})
        cv.loc[cv.index[0], "broken"] = np.nan
        scores = score_candidates(cv, s, ["broken"], m=None)
        assert scores[0].mean_mase is None

    def test_mase_scale_uses_naive_mae(self) -> None:
        # Constant series diffs are 0 → scale 0 → MASE undefined (None), never inf.
        idx = pd.date_range("2026-01-01", periods=40, freq="D")
        s = pd.Series(np.full(40, 5.0), index=idx)
        cv = _cv_frame(s, h_cv=5, k=1, preds={"m1": 1.0})
        scores = score_candidates(cv, s, ["m1"], m=None)
        assert scores[0].folds[0].mase is None
        assert scores[0].folds[0].rmse is not None  # other metrics still score


def _score(name: str, fold_mases: list[float | None]) -> CandidateScore:
    folds = [
        FoldScore(fold=i, cutoff=f"2026-01-0{i + 1}T00:00:00", mase=v, smape=v, rmse=v)
        for i, v in enumerate(fold_mases)
    ]
    kept = [v for v in fold_mases if v is not None]
    mean = float(np.mean(kept)) if kept else None
    return CandidateScore(name, mean, mean, mean, folds)


class TestSelect:
    def test_default_keeps_seat_without_margin(self) -> None:
        # Challenger is better but by <5% — noise, keep the robust default.
        sel = select(
            [
                _score("auto_ets", [0.50, 0.50]),
                _score("auto_arima", [0.49, 0.49]),
                _score("seasonal_naive", [0.9, 0.9]),
            ],
            default_name="auto_ets",
            baseline_name="seasonal_naive",
        )
        assert sel.chosen == "auto_ets"
        assert not sel.low_confidence

    def test_challenger_wins_with_margin_and_majority(self) -> None:
        sel = select(
            [
                _score("auto_ets", [0.50, 0.52]),
                _score("auto_arima", [0.30, 0.31]),
                _score("seasonal_naive", [0.9, 0.9]),
            ],
            default_name="auto_ets",
            baseline_name="seasonal_naive",
        )
        assert sel.chosen == "auto_arima"
        assert not sel.low_confidence

    def test_margin_without_majority_keeps_default(self) -> None:
        # Mean beats the margin only because of one lucky fold.
        sel = select(
            [
                _score("auto_ets", [0.50, 0.50, 0.50]),
                _score("auto_arima", [0.05, 0.55, 0.55]),
                _score("seasonal_naive", [0.9, 0.9, 0.9]),
            ],
            default_name="auto_ets",
            baseline_name="seasonal_naive",
        )
        assert sel.chosen == "auto_ets"

    def test_baseline_not_beaten_flags(self) -> None:
        sel = select(
            [_score("auto_ets", [0.80, 0.80]), _score("seasonal_naive", [0.5, 0.5])],
            default_name="auto_ets",
            baseline_name="seasonal_naive",
        )
        # Baseline is best by margin+majority → chosen; no flag when the
        # baseline itself is the winner and error is low.
        assert sel.chosen == "seasonal_naive"
        assert not sel.low_confidence

    def test_chosen_worse_than_baseline_flags(self) -> None:
        # Challenger ties the baseline exactly → default keeps seat, but the
        # default is worse than the baseline → flag.
        sel = select(
            [_score("auto_ets", [0.80, 0.80]), _score("seasonal_naive", [0.78, 0.78])],
            default_name="auto_ets",
            baseline_name="seasonal_naive",
        )
        assert sel.chosen == "auto_ets"
        assert sel.low_confidence
        assert "baseline_not_beaten" in sel.reasons

    def test_high_error_flags(self) -> None:
        high = LOW_CONFIDENCE_MASE + 0.5
        sel = select(
            [_score("auto_ets", [high, high]), _score("naive", [high + 1, high + 1])],
            default_name="auto_ets",
            baseline_name="naive",
        )
        assert sel.low_confidence
        assert "high_error" in sel.reasons

    def test_all_failed_falls_to_baseline_with_cv_skipped(self) -> None:
        sel = select(
            [_score("auto_ets", [None, None]), _score("naive", [None, None])],
            default_name="auto_ets",
            baseline_name="naive",
        )
        assert sel.chosen == "naive"
        assert sel.low_confidence
        assert sel.reasons == ["cv_skipped"]
