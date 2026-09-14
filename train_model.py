import json
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, KFold, train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, average_precision_score,
)
import joblib
from ml_config import (
    DEFAULT_RISK_THRESHOLD,
    THRESHOLD_SELECTION_METHOD,
    OPERATING_POINTS,
)

TRAINING_DATA_FILE = "training_data.csv"
MODEL_FILE = "delay_model.joblib"
METRICS_FILE = "model_metrics.json"

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


def evaluate_cross_validation(X, y):
    """
    Perform defensible cross-validation on the actual training data.
    Uses StratifiedKFold where feasible, dynamically adjusting splits
    if minority class count is small.
    """
    n_samples = len(y)
    n_pos = int(y.sum())
    n_neg = n_samples - n_pos
    min_class = min(n_pos, n_neg)

    # Defensible split strategy detection
    strategy_note = ""
    if min_class < 2:
        n_splits = 2
        cv = KFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_name = "2-Fold K-Fold (Minority class < 2)"
        strategy_note = f"Minority class has only {min_class} sample(s); falling back to standard KFold(n_splits=2)."
    elif min_class < 5:
        n_splits = min_class
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_name = f"{n_splits}-Fold Stratified CV (Adaptive)"
        strategy_note = f"Minority class has {min_class} samples; adjusted StratifiedKFold n_splits from 5 to {n_splits} to ensure each fold contains both classes."
    else:
        n_splits = 5
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
        cv_name = "5-Fold Stratified Cross-Validation"

    fold_metrics = []
    accs, precs, recs, f1s, aucs, praucs = [], [], [], [], [], []

    for fold_idx, (train_idx, val_idx) in enumerate(cv.split(X, y), start=1):
        X_tr, X_val = X.iloc[train_idx], X.iloc[val_idx]
        y_tr, y_val = y.iloc[train_idx], y.iloc[val_idx]

        clf_f = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=1,
            max_features="sqrt",
            class_weight=None,
            random_state=42,
        )
        clf_f.fit(X_tr, y_tr)

        y_prob = clf_f.predict_proba(X_val)[:, 1] if len(clf_f.classes_) > 1 else np.zeros(len(y_val))
        y_pred = (y_prob >= DEFAULT_RISK_THRESHOLD).astype(int)

        acc = float(accuracy_score(y_val, y_pred))
        prec = float(precision_score(y_val, y_pred, zero_division=0))
        rec = float(recall_score(y_val, y_pred, zero_division=0))
        f1 = float(f1_score(y_val, y_pred, zero_division=0))

        if len(np.unique(y_val)) > 1:
            auc = float(roc_auc_score(y_val, y_prob))
            prauc = float(average_precision_score(y_val, y_prob))
        else:
            auc = acc
            prauc = 0.0

        accs.append(acc)
        precs.append(prec)
        recs.append(rec)
        f1s.append(f1)
        aucs.append(auc)
        praucs.append(prauc)

        fold_metrics.append({
            "fold": fold_idx,
            "val_samples": len(y_val),
            "late_cases": int(y_val.sum()),
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "roc_auc": round(auc, 4),
            "pr_auc": round(prauc, 4),
        })

    def get_var_dict(values):
        arr = np.array(values, dtype=float)
        mean_v = float(np.mean(arr))
        std_v = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        min_v = float(np.min(arr))
        max_v = float(np.max(arr))
        return {
            "mean": round(mean_v, 4),
            "std": round(std_v, 4),
            "min": round(min_v, 4),
            "max": round(max_v, 4),
            "range_str": f"{min_v:.4f} – {max_v:.4f}",
        }

    variation = {
        "roc_auc": get_var_dict(aucs),
        "pr_auc": get_var_dict(praucs),
        "f1": get_var_dict(f1s),
        "accuracy": get_var_dict(accs),
        "precision": get_var_dict(precs),
        "recall": get_var_dict(recs),
    }

    return {
        "cv_strategy": cv_name,
        "n_splits": n_splits,
        "strategy_note": strategy_note,
        "fold_metrics": fold_metrics,
        "variation": variation,
        "accuracy": variation["accuracy"]["mean"],
        "precision": variation["precision"]["mean"],
        "recall": variation["recall"]["mean"],
        "f1": variation["f1"]["mean"],
        "roc_auc": variation["roc_auc"]["mean"],
        "pr_auc": variation["pr_auc"]["mean"],
    }


def main():
    print("=" * 60)
    print("  PHASE 2, STEP 3 -- Train Delay-Risk Classifier & Cross-Validation")
    print("=" * 60)

    df = pd.read_csv(TRAINING_DATA_FILE)

    X = df[FEATURE_COLS]
    y = df["late"]

    print(f"  Total dataset: {len(X)} cases  (late={y.sum()}, on_time={len(y) - y.sum()})")

    # 1. Cross-Validation Evaluation
    cv_res = evaluate_cross_validation(X, y)
    print()
    print(f"  Evaluation Strategy: {cv_res['cv_strategy']}")
    if cv_res["strategy_note"]:
        print(f"  Note: {cv_res['strategy_note']}")
    print("  " + "-" * 66)
    print(f"  {'Fold':<6} {'Accuracy':>10} {'Precision':>10} {'Recall':>10} {'F1':>10} {'ROC-AUC':>10}")
    print("  " + "-" * 66)
    for fm in cv_res["fold_metrics"]:
        print(f"  {fm['fold']:<6} {fm['accuracy']:>10.4f} {fm['precision']:>10.4f} {fm['recall']:>10.4f} {fm['f1']:>10.4f} {fm['roc_auc']:>10.4f}")
    print("  " + "-" * 66)
    print(f"  {'MEAN':<6} {cv_res['accuracy']:>10.4f} {cv_res['precision']:>10.4f} {cv_res['recall']:>10.4f} {cv_res['f1']:>10.4f} {cv_res['roc_auc']:>10.4f}")
    print(f"  {'RANGE':<6} {cv_res['variation']['accuracy']['range_str']:>10} {cv_res['variation']['precision']['range_str']:>10} {cv_res['variation']['recall']['range_str']:>10} {cv_res['variation']['f1']['range_str']:>10} {cv_res['variation']['roc_auc']['range_str']:>10}")
    print(f"  {'STD':<6} {cv_res['variation']['accuracy']['std']:>10.4f} {cv_res['variation']['precision']['std']:>10.4f} {cv_res['variation']['recall']['std']:>10.4f} {cv_res['variation']['f1']['std']:>10.4f} {cv_res['variation']['roc_auc']['std']:>10.4f}")
    print(f"  {'PR-AUC':<6} Mean: {cv_res['pr_auc']:.4f} (range: {cv_res['variation']['pr_auc']['range_str']}, std: {cv_res['variation']['pr_auc']['std']:.4f})")

    # 2. Fit deployment model on 80/20 train/test split for baseline preservation
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y if min(y.sum(), len(y)-y.sum()) >= 2 else None, random_state=42
    )

    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_split=5,
        min_samples_leaf=1,
        max_features="sqrt",
        class_weight=None,
        random_state=42,
    )
    clf.fit(X_train, y_train)

    y_prob = clf.predict_proba(X_test)[:, 1] if len(clf.classes_) > 1 else np.zeros(len(y_test))
    y_pred = (y_prob >= DEFAULT_RISK_THRESHOLD).astype(int)

    test_acc = accuracy_score(y_test, y_pred)
    test_prec = precision_score(y_test, y_pred, zero_division=0)
    test_rec = recall_score(y_test, y_pred, zero_division=0)
    test_f1 = f1_score(y_test, y_pred, zero_division=0)
    test_auc = roc_auc_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else test_acc
    test_prauc = average_precision_score(y_test, y_prob) if len(np.unique(y_test)) > 1 else 0.0

    # Feature importances
    importances_list = [
        {"feature": f, "importance": round(float(imp), 4)}
        for f, imp in sorted(zip(FEATURE_COLS, clf.feature_importances_), key=lambda x: x[1], reverse=True)
    ]

    print()
    print("  Feature Importances (sorted descending):")
    print("  " + "-" * 55)
    for row in importances_list:
        bar = "#" * int(row["importance"] * 40)
        print(f"    {row['feature']:<35} {row['importance']:.4f}  {bar}")

    # Save model and metrics JSON
    joblib.dump(clf, MODEL_FILE)
    print()
    print(f"  Model saved to: {MODEL_FILE}")

    metrics_payload = {
        "cv_strategy": cv_res["cv_strategy"],
        "n_splits": cv_res["n_splits"],
        "strategy_note": cv_res["strategy_note"],
        "risk_threshold": DEFAULT_RISK_THRESHOLD,
        "threshold": DEFAULT_RISK_THRESHOLD,
        "threshold_method": THRESHOLD_SELECTION_METHOD,
        "operating_points": OPERATING_POINTS,
        "accuracy": cv_res["accuracy"],
        "precision": cv_res["precision"],
        "recall": cv_res["recall"],
        "f1": cv_res["f1"],
        "roc_auc": cv_res["roc_auc"],
        "pr_auc": cv_res["pr_auc"],
        "variation": cv_res["variation"],
        "fold_metrics": cv_res["fold_metrics"],
        "test_set_metrics": {
            "accuracy": round(float(test_acc), 4),
            "precision": round(float(test_prec), 4),
            "recall": round(float(test_rec), 4),
            "f1": round(float(test_f1), 4),
            "roc_auc": round(float(test_auc), 4),
            "pr_auc": round(float(test_prauc), 4),
            "risk_threshold": DEFAULT_RISK_THRESHOLD,
        },
        "feature_importances": importances_list,
    }

    with open(METRICS_FILE, "w", encoding="utf-8") as f:
        json.dump(metrics_payload, f, indent=2)
    print(f"  Cross-validation metrics saved to: {METRICS_FILE}")
    print("=" * 60)

    return cv_res["roc_auc"]


if __name__ == "__main__":
    main()
