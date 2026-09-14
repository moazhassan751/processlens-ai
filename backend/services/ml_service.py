"""
ProcessLens — ML Service
=========================
Prediction data computation extracted from main.py.
Deterministic — no LLM calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from backend.config import OUTPUT_FILES
from ml_config import (
    DEFAULT_RISK_THRESHOLD,
    THRESHOLD_SELECTION_METHOD,
    OPERATING_POINTS,
)

logger = logging.getLogger("processlens.ml")


def compute_prediction_data(
    predictions_path: Optional[Path] = None,
    delay_model_path: Optional[Path] = None,
    training_data_path: Optional[Path] = None,
) -> dict:
    """Compute prediction summary, model metrics, feature importances, and open cases."""
    pred_p = predictions_path or OUTPUT_FILES["predictions"]
    if not pred_p.exists():
        return {}

    with open(str(pred_p), encoding="utf-8") as f:
        open_cases = json.load(f)

    for c in open_cases:
        if "risk_threshold" not in c:
            c["risk_threshold"] = DEFAULT_RISK_THRESHOLD
        if "risk_label" not in c:
            c["risk_label"] = c.get("predicted_label")

    late_risk_count = sum(1 for c in open_cases if c.get("predicted_label") == "Late Risk" or c.get("risk_label") == "Late Risk")
    on_track_count = sum(1 for c in open_cases if c.get("predicted_label") == "On Track" or c.get("risk_label") == "On Track")
    insufficient_count = sum(1 for c in open_cases if c.get("predicted_label") == "Insufficient Data")
    anomaly_count = sum(1 for c in open_cases if c.get("anomaly_flag"))

    feature_importances: list = []
    model_metrics: dict = {}

    dm_p = delay_model_path or OUTPUT_FILES["delay_model"]
    td_p = training_data_path or OUTPUT_FILES["training_data"]
    mm_p = dm_p.parent / "model_metrics.json" if dm_p else OUTPUT_FILES["model_metrics"]
    if not mm_p.exists():
        mm_p = OUTPUT_FILES["model_metrics"]

    if mm_p.exists():
        try:
            with open(str(mm_p), encoding="utf-8") as f:
                saved_metrics = json.load(f)
            model_metrics = saved_metrics
            if "feature_importances" in saved_metrics:
                feature_importances = saved_metrics["feature_importances"]
        except Exception as exc:
            logger.warning(f"Failed loading saved model_metrics.json: {exc}")

    if not model_metrics and dm_p.exists() and td_p.exists():
        try:
            import joblib
            import numpy as np
            import pandas as pd
            from sklearn.metrics import (
                accuracy_score, f1_score, precision_score,
                recall_score, roc_auc_score,
            )
            from sklearn.model_selection import StratifiedKFold, KFold

            FEATURE_COLS = [
                # Original 5 baseline features
                "elapsed_hours_so_far",
                "wait_before_reviewed_hours",
                "resource_at_reviewed",
                "hour_of_day_submitted",
                "has_been_reworked_yet",
                # Process progress
                "events_seen_so_far",
                "unique_activities_so_far",
                "transition_count_so_far",
                "activity_repetition_count",
                # Waiting behavior
                "total_wait_hours_so_far",
                "average_wait_hours_so_far",
                "max_wait_hours_so_far",
                "min_wait_hours_so_far",
                "number_of_long_waits_so_far",
                "time_since_previous_activity",
                # Timing & Calendar
                "hour_of_day_at_snapshot",
                "day_of_week_submitted",
                "day_of_week_at_snapshot",
                "is_weekend_submitted",
                # Resource context
                "resource_at_submitted",
            ]

            clf = joblib.load(str(dm_p))
            df = pd.read_csv(str(td_p))
            X = df[FEATURE_COLS]
            y = df["late"]

            n_samples = len(y)
            n_pos = int(y.sum())
            n_neg = n_samples - n_pos
            min_class = min(n_pos, n_neg)

            if min_class < 2:
                n_splits = 2
                cv = KFold(n_splits=n_splits, shuffle=True, random_state=42)
                cv_name = "2-Fold K-Fold"
            elif min_class < 5:
                n_splits = min_class
                cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
                cv_name = f"{n_splits}-Fold Stratified CV (Adaptive)"
            else:
                n_splits = 5
                cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
                cv_name = "5-Fold Stratified Cross-Validation"

            fold_metrics = []
            accs, precs, recs, f1s, aucs = [], [], [], [], []

            for fold_idx, (train_idx, val_idx) in enumerate(cv.split(X, y), start=1):
                X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

                clf_f = joblib.load(str(dm_p))
                clf_f.fit(X_tr, y_tr)

                y_pred_f = clf_f.predict(X_val)
                y_prob_f = clf_f.predict_proba(X_val)[:, 1] if len(clf_f.classes_) > 1 else np.zeros(len(y_val))

                acc = float(accuracy_score(y_val, y_pred_f))
                prec = float(precision_score(y_val, y_pred_f, zero_division=0))
                rec = float(recall_score(y_val, y_pred_f, zero_division=0))
                f1 = float(f1_score(y_val, y_pred_f, zero_division=0))
                auc = float(roc_auc_score(y_val, y_prob_f)) if len(np.unique(y_val)) > 1 else acc

                accs.append(acc)
                precs.append(prec)
                recs.append(rec)
                f1s.append(f1)
                aucs.append(auc)

                fold_metrics.append({
                    "fold": fold_idx,
                    "accuracy": round(acc, 4),
                    "precision": round(prec, 4),
                    "recall": round(rec, 4),
                    "f1": round(f1, 4),
                    "roc_auc": round(auc, 4),
                })

            def calc_var(values):
                arr = np.array(values, dtype=float)
                return {
                    "mean": round(float(np.mean(arr)), 4),
                    "std": round(float(np.std(arr, ddof=1)), 4) if len(arr) > 1 else 0.0,
                    "min": round(float(np.min(arr)), 4),
                    "max": round(float(np.max(arr)), 4),
                    "range_str": f"{float(np.min(arr)):.4f} – {float(np.max(arr)):.4f}",
                }

            variation = {
                "roc_auc": calc_var(aucs),
                "f1": calc_var(f1s),
                "accuracy": calc_var(accs),
                "precision": calc_var(precs),
                "recall": calc_var(recs),
            }

            model_metrics = {
                "cv_strategy": cv_name,
                "n_splits": n_splits,
                "accuracy": variation["accuracy"]["mean"],
                "precision": variation["precision"]["mean"],
                "recall": variation["recall"]["mean"],
                "f1": variation["f1"]["mean"],
                "roc_auc": variation["roc_auc"]["mean"],
                "variation": variation,
                "fold_metrics": fold_metrics,
            }

            importances = sorted(
                zip(FEATURE_COLS, clf.feature_importances_),
                key=lambda x: x[1], reverse=True,
            )
            feature_importances = [
                {"feature": f, "importance": round(float(imp), 4)}
                for f, imp in importances
            ]
        except Exception as exc:
            model_metrics = {"error": str(exc)}

    enterprise_benchmark = None
    eb_p = OUTPUT_FILES.get("enterprise_model_metrics")
    if eb_p and eb_p.exists():
        try:
            with open(str(eb_p), encoding="utf-8") as f:
                enterprise_benchmark = json.load(f)
        except Exception as exc:
            logger.warning(f"Failed loading enterprise_model_metrics.json: {exc}")

    return {
        "summary": {
            "late_risk_count":        late_risk_count,
            "on_track_count":         on_track_count,
            "insufficient_data_count": insufficient_count,
            "anomaly_count":          anomaly_count,
            "total_cases":            len(open_cases),
        },
        "risk_threshold":       DEFAULT_RISK_THRESHOLD,
        "threshold":            DEFAULT_RISK_THRESHOLD,
        "threshold_method":     THRESHOLD_SELECTION_METHOD,
        "operating_points":     OPERATING_POINTS,
        "model_metrics":        model_metrics,
        "enterprise_benchmark": enterprise_benchmark,
        "feature_importances":  feature_importances,
        "open_cases":           open_cases,
    }
