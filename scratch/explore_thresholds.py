import json
import os
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    average_precision_score,
    confusion_matrix,
    brier_score_loss,
)
from sklearn.calibration import calibration_curve

os.environ["LOKY_MAX_CPU_COUNT"] = "4"

TRAINING_DATA_FILE = "training_data.csv"

FEATURE_COLS = [
    "elapsed_hours_so_far",
    "wait_before_reviewed_hours",
    "resource_at_reviewed",
    "hour_of_day_submitted",
    "has_been_reworked_yet",
    "events_seen_so_far",
    "unique_activities_so_far",
    "transition_count_so_far",
    "activity_repetition_count",
    "total_wait_hours_so_far",
    "average_wait_hours_so_far",
    "max_wait_hours_so_far",
    "min_wait_hours_so_far",
    "number_of_long_waits_so_far",
    "time_since_previous_activity",
    "hour_of_day_at_snapshot",
    "day_of_week_submitted",
    "day_of_week_at_snapshot",
    "is_weekend_submitted",
    "resource_at_submitted",
]

def main():
    df = pd.read_csv(TRAINING_DATA_FILE)
    X = df[FEATURE_COLS]
    y = df["late"]

    # 80/20 train/holdout split (exact H1/Phase 2 contract)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, stratify=y, random_state=42
    )

    print(f"Total dataset: {len(df)} cases")
    print(f"Train split (80%): {len(X_train)} cases (late={y_train.sum()}, on_time={len(y_train) - y_train.sum()})")
    print(f"Holdout split (20%): {len(X_test)} cases (late={y_test.sum()}, on_time={len(y_test) - y_test.sum()})")

    # 1. Generate Out-of-Fold (OOF) Probabilities on Training Set
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    oof_probs = np.zeros(len(X_train))
    fold_indices = []

    for fold_idx, (train_idx, val_idx) in enumerate(cv.split(X_train, y_train), start=1):
        X_tr, X_val = X_train.iloc[train_idx], X_train.iloc[val_idx]
        y_tr, y_val = y_train.iloc[train_idx], y_train.iloc[val_idx]

        clf = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=5,
            min_samples_leaf=1,
            max_features="sqrt",
            class_weight=None,
            random_state=42,
        )
        clf.fit(X_tr, y_tr)
        val_probs = clf.predict_proba(X_val)[:, 1]
        oof_probs[val_idx] = val_probs
        fold_indices.append((train_idx, val_idx))

    y_train_arr = y_train.values

    # OOF Overall ROC-AUC and PR-AUC
    oof_auc = roc_auc_score(y_train_arr, oof_probs)
    oof_prauc = average_precision_score(y_train_arr, oof_probs)
    print(f"\nOOF ROC-AUC on Training Set: {oof_auc:.4f}")
    print(f"OOF PR-AUC on Training Set:  {oof_prauc:.4f}")

    # 2. Evaluate Threshold Grid
    thresholds = [round(t, 2) for t in np.arange(0.10, 0.91, 0.05)]
    fine_thresholds = [round(t, 2) for t in np.arange(0.05, 0.95, 0.01)]

    print("\n" + "=" * 115)
    print("THRESHOLD EVALUATION TABLE (ON 240 OUT-OF-FOLD PREDICTIONS)")
    print("=" * 115)
    print(f"{'Thresh':<8} {'Prec':<8} {'Recall':<8} {'F1':<8} {'Acc':<8} {'BalAcc':<8} {'FPR':<8} {'FNR':<8} {'Flagged':<10} {'TN':<5} {'FP':<5} {'FN':<5} {'TP':<5}")
    print("-" * 115)

    records = []
    for t in fine_thresholds:
        preds = (oof_probs >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_train_arr, preds, labels=[0, 1]).ravel()
        prec = precision_score(y_train_arr, preds, zero_division=0)
        rec = recall_score(y_train_arr, preds, zero_division=0)
        f1 = f1_score(y_train_arr, preds, zero_division=0)
        acc = accuracy_score(y_train_arr, preds)
        bal_acc = balanced_accuracy_score(y_train_arr, preds)
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
        flagged = int(preds.sum())
        flagged_pct = (flagged / len(preds)) * 100

        row = {
            "threshold": t,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "accuracy": acc,
            "balanced_accuracy": bal_acc,
            "fpr": fpr,
            "fnr": fnr,
            "flagged": flagged,
            "flagged_pct": flagged_pct,
            "tn": tn,
            "fp": fp,
            "fn": fn,
            "tp": tp,
        }
        records.append(row)
        if t in thresholds:
            print(f"{t:<8.2f} {prec:<8.4f} {rec:<8.4f} {f1:<8.4f} {acc:<8.4f} {bal_acc:<8.4f} {fpr:<8.4f} {fnr:<8.4f} {flagged:>3} ({flagged_pct:>4.1f}%) {tn:<5} {fp:<5} {fn:<5} {tp:<5}")

    print("=" * 115)

    # 3. Selection Rule:
    # constraint: precision >= 0.30
    # 1. maximize F1
    # 2. if F1 tied (within 0.001), prefer higher recall
    # 3. if still tied, prefer fewer false positives
    valid_candidates = [r for r in records if r["precision"] >= 0.30]
    # Sort with rule
    valid_candidates.sort(
        key=lambda r: (round(r["f1"], 3), round(r["recall"], 4), -r["fp"]),
        reverse=True,
    )
    best_balanced = valid_candidates[0]
    print(f"\nSELECTED BALANCED THRESHOLD (Primary F1 rule with prec >= 0.30): {best_balanced['threshold']:.2f}")
    print(f"  Precision:         {best_balanced['precision']:.4f}")
    print(f"  Recall:            {best_balanced['recall']:.4f}")
    print(f"  F1:                {best_balanced['f1']:.4f}")
    print(f"  Accuracy:          {best_balanced['accuracy']:.4f}")
    print(f"  Balanced Accuracy: {best_balanced['balanced_accuracy']:.4f}")
    print(f"  FPR:               {best_balanced['fpr']:.4f}")
    print(f"  FNR:               {best_balanced['fnr']:.4f}")
    print(f"  Cases Flagged:     {best_balanced['flagged']} ({best_balanced['flagged_pct']:.1f}%)")
    print(f"  Confusion Matrix:  TN={best_balanced['tn']}, FP={best_balanced['fp']}, FN={best_balanced['fn']}, TP={best_balanced['tp']}")

    # 4. Alternative Operating Points
    # Conservative: Highest precision that provides meaningful recall (e.g. recall >= 0.20, highest precision)
    meaningful_rec = [r for r in records if r["recall"] >= 0.15 and r["precision"] >= 0.35]
    meaningful_rec.sort(key=lambda r: (r["precision"], r["recall"]), reverse=True)
    best_conservative = meaningful_rec[0] if meaningful_rec else records[0]

    # Sensitive: Lower threshold with substantially higher recall while precision >= 0.30 (or >= 0.25)
    sensitive_cands = [r for r in records if r["precision"] >= 0.30 and r["recall"] > best_balanced["recall"]]
    sensitive_cands.sort(key=lambda r: (r["recall"], r["precision"]), reverse=True)
    best_sensitive = sensitive_cands[0] if sensitive_cands else best_balanced

    print(f"\nALTERNATIVE OPERATING POINTS:")
    print(f"  Conservative (High Precision): Thresh={best_conservative['threshold']:.2f} -> Prec={best_conservative['precision']:.4f}, Recall={best_conservative['recall']:.4f}, F1={best_conservative['f1']:.4f}, Flagged={best_conservative['flagged']}")
    print(f"  Balanced (Primary F1):         Thresh={best_balanced['threshold']:.2f} -> Prec={best_balanced['precision']:.4f}, Recall={best_balanced['recall']:.4f}, F1={best_balanced['f1']:.4f}, Flagged={best_balanced['flagged']}")
    print(f"  Sensitive (High Recall):       Thresh={best_sensitive['threshold']:.2f} -> Prec={best_sensitive['precision']:.4f}, Recall={best_sensitive['recall']:.4f}, F1={best_sensitive['f1']:.4f}, Flagged={best_sensitive['flagged']}")

    # 5. Compare against Threshold = 0.50
    t50 = [r for r in records if r["threshold"] == 0.50][0]
    print("\n" + "=" * 80)
    print(f"{'Metric':<25} {'Threshold 0.50':>16} {'Selected (' + str(best_balanced['threshold']) + ')':>16} {'Change':>16}")
    print("-" * 80)
    diff_prec = best_balanced["precision"] - t50["precision"]
    diff_rec = best_balanced["recall"] - t50["recall"]
    diff_f1 = best_balanced["f1"] - t50["f1"]
    diff_acc = best_balanced["accuracy"] - t50["accuracy"]
    diff_bal = best_balanced["balanced_accuracy"] - t50["balanced_accuracy"]
    diff_fpr = best_balanced["fpr"] - t50["fpr"]
    diff_fnr = best_balanced["fnr"] - t50["fnr"]
    diff_flag = best_balanced["flagged"] - t50["flagged"]

    print(f"{'Precision':<25} {t50['precision']:>16.4f} {best_balanced['precision']:>16.4f} {'+' if diff_prec>=0 else ''}{diff_prec:>15.4f}")
    print(f"{'Recall':<25} {t50['recall']:>16.4f} {best_balanced['recall']:>16.4f} {'+' if diff_rec>=0 else ''}{diff_rec:>15.4f}")
    print(f"{'F1':<25} {t50['f1']:>16.4f} {best_balanced['f1']:>16.4f} {'+' if diff_f1>=0 else ''}{diff_f1:>15.4f}")
    print(f"{'Accuracy':<25} {t50['accuracy']:>16.4f} {best_balanced['accuracy']:>16.4f} {'+' if diff_acc>=0 else ''}{diff_acc:>15.4f}")
    print(f"{'Balanced Accuracy':<25} {t50['balanced_accuracy']:>16.4f} {best_balanced['balanced_accuracy']:>16.4f} {'+' if diff_bal>=0 else ''}{diff_bal:>15.4f}")
    print(f"{'False Positive Rate':<25} {t50['fpr']:>16.4f} {best_balanced['fpr']:>16.4f} {'+' if diff_fpr>=0 else ''}{diff_fpr:>15.4f}")
    print(f"{'False Negative Rate':<25} {t50['fnr']:>16.4f} {best_balanced['fnr']:>16.4f} {'+' if diff_fnr>=0 else ''}{diff_fnr:>15.4f}")
    print(f"{'Cases Flagged':<25} {t50['flagged']:>16} {best_balanced['flagged']:>16} {'+' if diff_flag>=0 else ''}{diff_flag:>16}")
    print("=" * 80)

    # 6. Threshold Stability Across Folds
    print("\nTHRESHOLD STABILITY ACROSS 5 FOLDS:")
    fold_thresholds = []
    for f_idx, (tr_idx, val_idx) in enumerate(fold_indices, start=1):
        # Determine best threshold using fold training data
        # We run inner CV or fit model on tr_idx, predict on inner split or tr_idx
        # Specifically, requirement: 'determine the best threshold using only the fold's training portion'
        X_inner_tr, y_inner_tr = X_train.iloc[tr_idx], y_train.iloc[tr_idx]
        inner_cv = StratifiedKFold(n_splits=4, shuffle=True, random_state=42)
        inner_oof = np.zeros(len(X_inner_tr))
        for in_tr, in_val in inner_cv.split(X_inner_tr, y_inner_tr):
            m = RandomForestClassifier(
                n_estimators=200, max_depth=10, min_samples_split=5, min_samples_leaf=1,
                max_features="sqrt", class_weight=None, random_state=42,
            )
            m.fit(X_inner_tr.iloc[in_tr], y_inner_tr.iloc[in_tr])
            inner_oof[in_val] = m.predict_proba(X_inner_tr.iloc[in_val])[:, 1]
        
        # Select threshold using same rule
        best_t_fold = None
        best_f1_fold = -1
        y_in_arr = y_inner_tr.values
        for t in fine_thresholds:
            p_in = (inner_oof >= t).astype(int)
            pr = precision_score(y_in_arr, p_in, zero_division=0)
            if pr >= 0.30:
                f1_in = f1_score(y_in_arr, p_in, zero_division=0)
                if f1_in > best_f1_fold:
                    best_f1_fold = f1_in
                    best_t_fold = t
        fold_thresholds.append(best_t_fold)
        print(f"  Fold {f_idx}: optimal threshold = {best_t_fold:.2f} (inner F1 = {best_f1_fold:.4f})")

    print(f"Fold Thresholds: Mean={np.mean(fold_thresholds):.4f}, Median={np.median(fold_thresholds):.4f}, Std={np.std(fold_thresholds, ddof=1):.4f}, Min={np.min(fold_thresholds):.2f}, Max={np.max(fold_thresholds):.2f}")

    # 7. Calibration Analysis on OOF Probabilities
    brier = brier_score_loss(y_train_arr, oof_probs)
    prob_true, prob_pred = calibration_curve(y_train_arr, oof_probs, n_bins=5, strategy="uniform")
    print(f"\nCALIBRATION ANALYSIS (Development Data):")
    print(f"  Brier Score: {brier:.4f}")
    print(f"  Calibration Curve (5 uniform bins):")
    for bin_idx, (pt, pp) in enumerate(zip(prob_true, prob_pred), start=1):
        print(f"    Bin {bin_idx}: Mean Predicted P={pp:.4f}, Observed Positive Fraction={pt:.4f} (gap = {pt - pp:+.4f})")

    # 8. Single Final Evaluation on Holdout Set
    print("\n" + "=" * 80)
    print("FINAL UNTOUCHED HOLDOUT EVALUATION (TOUCHED ONLY ONCE AT END)")
    print("=" * 80)
    full_rf = RandomForestClassifier(
        n_estimators=200, max_depth=10, min_samples_split=5, min_samples_leaf=1,
        max_features="sqrt", class_weight=None, random_state=42,
    )
    full_rf.fit(X_train, y_train)
    test_probs = full_rf.predict_proba(X_test)[:, 1]

    holdout_auc = roc_auc_score(y_test, test_probs)
    holdout_prauc = average_precision_score(y_test, test_probs)

    sel_t = best_balanced["threshold"]
    test_preds_sel = (test_probs >= sel_t).astype(int)
    test_preds_50 = (test_probs >= 0.50).astype(int)

    tn_h, fp_h, fn_h, tp_h = confusion_matrix(y_test, test_preds_sel, labels=[0, 1]).ravel()
    prec_h = precision_score(y_test, test_preds_sel, zero_division=0)
    rec_h = recall_score(y_test, test_preds_sel, zero_division=0)
    f1_h = f1_score(y_test, test_preds_sel, zero_division=0)
    acc_h = accuracy_score(y_test, test_preds_sel)
    bal_acc_h = balanced_accuracy_score(y_test, test_preds_sel)
    fpr_h = fp_h / (fp_h + tn_h)
    fnr_h = fn_h / (fn_h + tp_h)
    flagged_h = int(test_preds_sel.sum())

    tn_50, fp_50, fn_50, tp_50 = confusion_matrix(y_test, test_preds_50, labels=[0, 1]).ravel()
    prec_50 = precision_score(y_test, test_preds_50, zero_division=0)
    rec_50 = recall_score(y_test, test_preds_50, zero_division=0)
    f1_50 = f1_score(y_test, test_preds_50, zero_division=0)

    print(f"Holdout ROC-AUC:        {holdout_auc:.4f}")
    print(f"Holdout PR-AUC:         {holdout_prauc:.4f}")
    print(f"\nHoldout Performance at Selected Threshold ({sel_t:.2f}):")
    print(f"  Precision:            {prec_h:.4f}  (vs 0.50: {prec_50:.4f})")
    print(f"  Recall:               {rec_h:.4f}  (vs 0.50: {rec_50:.4f})")
    print(f"  F1-Score:             {f1_h:.4f}  (vs 0.50: {f1_50:.4f})")
    print(f"  Accuracy:             {acc_h:.4f}")
    print(f"  Balanced Accuracy:    {bal_acc_h:.4f}")
    print(f"  False Positive Rate:  {fpr_h:.4f}")
    print(f"  False Negative Rate:  {fnr_h:.4f}")
    print(f"  Cases Flagged:        {flagged_h} / {len(y_test)} ({flagged_h/len(y_test)*100:.1f}%)")
    print(f"  Confusion Matrix:     TN={tn_h}, FP={fp_h}, FN={fn_h}, TP={tp_h}")
    print("=" * 80)

if __name__ == "__main__":
    main()
