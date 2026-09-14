import json
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedGroupKFold, GroupKFold
from sklearn.ensemble import RandomForestClassifier
import lightgbm as lgb
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score, average_precision_score

# Load event log
df = pd.read_csv("event_log.csv")
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values(["case_id", "timestamp"]).reset_index(drop=True)

# Resources
unique_resources = sorted([str(r) for r in df["resource"].dropna().unique()])
resource_map = {name: i for i, name in enumerate(unique_resources)}

# Calculate total cycle time per case (for ground truth label)
case_times = df.groupby("case_id")["timestamp"].agg(["min", "max"])
case_times["total_cycle_hours"] = (case_times["max"] - case_times["min"]).dt.total_seconds() / 3600.0

# 80/20 train/test split strictly by case_id
np.random.seed(42)
all_cases = df["case_id"].unique()
shuffled_cases = np.random.permutation(all_cases)
train_cases = set(shuffled_cases[:int(0.8 * len(all_cases))])
test_cases = set(shuffled_cases[int(0.8 * len(all_cases)):])

# Lateness threshold from train cases only
train_cycle_times = case_times.loc[list(train_cases), "total_cycle_hours"]
late_threshold = float(train_cycle_times.quantile(0.75))
case_late_label = (case_times["total_cycle_hours"] > late_threshold).astype(int).to_dict()

# Compute WIP congestion across chronological events:
# For each event timestamp T, active WIP cases = count of cases that have started <= T and not finished < T
case_start_end = df.groupby("case_id")["timestamp"].agg(start="min", end="max")
all_starts = case_start_end["start"].values
all_ends = case_start_end["end"].values

def get_wip_at_ts(ts):
    # number of cases where start <= ts and end > ts
    return int(np.sum((all_starts <= np.datetime64(ts)) & (all_ends > np.datetime64(ts))))

# Generate multi-prefix features for each case at prefixes >= 2 (and before completion)
rows = []
for case_id, group in df.groupby("case_id"):
    group = group.sort_values("timestamp").reset_index(drop=True)
    n_events = len(group)
    start_ts = group.iloc[0]["timestamp"]
    submitted_events = group[group["activity"] == "Submitted"]
    submitted_ts = submitted_events.iloc[0]["timestamp"] if not submitted_events.empty else start_ts
    
    # We create snapshots for prefix lengths from 2 up to min(n_events-1, 4)
    # (avoiding the final event which is completion)
    max_prefix = min(n_events - 1, 4) if n_events > 2 else 2
    for prefix_len in range(2, max_prefix + 1):
        prefix_events = group.iloc[:prefix_len]
        last_event = prefix_events.iloc[-1]
        snapshot_ts = last_event["timestamp"]
        
        # Temporal boundary guard
        assert prefix_events["timestamp"].max() <= snapshot_ts
        
        # System WIP congestion
        wip_cases = get_wip_at_ts(snapshot_ts)
        
        # Time calculations
        elapsed_hours = (snapshot_ts - start_ts).total_seconds() / 3600.0
        wait_before_snapshot = (snapshot_ts - submitted_ts).total_seconds() / 3600.0
        
        # Waits between events
        waits = prefix_events["timestamp"].diff().dropna().dt.total_seconds() / 3600.0
        total_wait = float(waits.sum()) if not waits.empty else 0.0
        avg_wait = float(waits.mean()) if not waits.empty else 0.0
        max_wait = float(waits.max()) if not waits.empty else 0.0
        min_wait = float(waits.min()) if not waits.empty else 0.0
        long_waits = int((waits > 3.0).sum()) if not waits.empty else 0
        time_since_prev = float(waits.iloc[-1]) if not waits.empty else 0.0
        
        # Counts & rework
        has_rework = 1 if len(prefix_events["activity"]) > len(set(prefix_events["activity"])) else 0
        unique_acts = prefix_events["activity"].nunique()
        res_encoded = resource_map.get(str(last_event["resource"]), -1)
        start_res = resource_map.get(str(group.iloc[0]["resource"]), -1)
        
        rows.append({
            "case_id": case_id,
            "prefix_len": prefix_len,
            "current_activity": last_event["activity"],
            "split": "train" if case_id in train_cases else "test",
            "late": case_late_label[case_id],
            # Features
            "elapsed_hours_so_far": round(elapsed_hours, 4),
            "wait_before_reviewed_hours": round(wait_before_snapshot, 4),
            "resource_at_reviewed": res_encoded,
            "hour_of_day_submitted": submitted_ts.hour,
            "has_been_reworked_yet": has_rework,
            "events_seen_so_far": prefix_len,
            "unique_activities_so_far": unique_acts,
            "transition_count_so_far": prefix_len - 1,
            "activity_repetition_count": prefix_len - unique_acts,
            "total_wait_hours_so_far": round(total_wait, 4),
            "average_wait_hours_so_far": round(avg_wait, 4),
            "max_wait_hours_so_far": round(max_wait, 4),
            "min_wait_hours_so_far": round(min_wait, 4),
            "number_of_long_waits_so_far": long_waits,
            "time_since_previous_activity": round(time_since_prev, 4),
            "hour_of_day_at_snapshot": snapshot_ts.hour,
            "day_of_week_submitted": submitted_ts.dayofweek,
            "day_of_week_at_snapshot": snapshot_ts.dayofweek,
            "is_weekend_submitted": 1 if submitted_ts.dayofweek >= 5 else 0,
            "resource_at_submitted": start_res,
            # NEW WIP congestion features
            "wip_active_cases": wip_cases,
        })

df_multi = pd.DataFrame(rows)
print("Total multi-prefix rows generated:", len(df_multi))
print("Train rows:", len(df_multi[df_multi['split'] == 'train']), "Test rows:", len(df_multi[df_multi['split'] == 'test']))

feature_cols = [
    "elapsed_hours_so_far", "wait_before_reviewed_hours", "resource_at_reviewed",
    "hour_of_day_submitted", "has_been_reworked_yet", "events_seen_so_far",
    "unique_activities_so_far", "transition_count_so_far", "activity_repetition_count",
    "total_wait_hours_so_far", "average_wait_hours_so_far", "max_wait_hours_so_far",
    "min_wait_hours_so_far", "number_of_long_waits_so_far", "time_since_previous_activity",
    "hour_of_day_at_snapshot", "day_of_week_submitted", "day_of_week_at_snapshot",
    "is_weekend_submitted", "resource_at_submitted", "wip_active_cases"
]

# Benchmark 5-Fold GroupKFold CV on train data
train_data = df_multi[df_multi["split"] == "train"].reset_index(drop=True)
test_data = df_multi[df_multi["split"] == "test"].reset_index(drop=True)

gkf = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)
groups = train_data["case_id"].values
X_tr_all = train_data[feature_cols]
y_tr_all = train_data["late"]

# Evaluate Random Forest vs LightGBM
rf_aucs, lgb_aucs = [], []
rf_praucs, lgb_praucs = [], []

for tr_idx, val_idx in gkf.split(X_tr_all, y_tr_all, groups=groups):
    X_f_tr, y_f_tr = X_tr_all.iloc[tr_idx], y_tr_all.iloc[tr_idx]
    X_f_val, y_f_val = X_tr_all.iloc[val_idx], y_tr_all.iloc[val_idx]
    
    # RF
    rf = RandomForestClassifier(n_estimators=200, max_depth=10, min_samples_split=5, min_samples_leaf=1, max_features="sqrt", random_state=42)
    rf.fit(X_f_tr, y_f_tr)
    rf_prob = rf.predict_proba(X_f_val)[:, 1]
    rf_aucs.append(roc_auc_score(y_f_val, rf_prob))
    rf_praucs.append(average_precision_score(y_f_val, rf_prob))
    
    # LightGBM
    lgbm = lgb.LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.05, num_leaves=15, random_state=42, verbose=-1)
    lgbm.fit(X_f_tr, y_f_tr)
    lgb_prob = lgbm.predict_proba(X_f_val)[:, 1]
    lgb_aucs.append(roc_auc_score(y_f_val, lgb_prob))
    lgb_praucs.append(average_precision_score(y_f_val, lgb_prob))

print("\n--- 5-FOLD STRATIFIED GROUP CV BENCHMARK ---")
print(f"Random Forest ROC-AUC : {np.mean(rf_aucs):.4f} +/- {np.std(rf_aucs):.4f} (PR-AUC: {np.mean(rf_praucs):.4f})")
print(f"LightGBM ROC-AUC      : {np.mean(lgb_aucs):.4f} +/- {np.std(lgb_aucs):.4f} (PR-AUC: {np.mean(lgb_praucs):.4f})")

# Evaluate on test set
rf_full = RandomForestClassifier(n_estimators=200, max_depth=10, min_samples_split=5, min_samples_leaf=1, max_features="sqrt", random_state=42)
rf_full.fit(X_tr_all, y_tr_all)
rf_test_prob = rf_full.predict_proba(test_data[feature_cols])[:, 1]

lgbm_full = lgb.LGBMClassifier(n_estimators=100, max_depth=5, learning_rate=0.05, num_leaves=15, random_state=42, verbose=-1)
lgbm_full.fit(X_tr_all, y_tr_all)
lgb_test_prob = lgbm_full.predict_proba(test_data[feature_cols])[:, 1]

print("\n--- TEST SET EVALUATION ---")
print(f"Random Forest Test ROC-AUC: {roc_auc_score(test_data['late'], rf_test_prob):.4f} (PR-AUC: {average_precision_score(test_data['late'], rf_test_prob):.4f})")
print(f"LightGBM Test ROC-AUC     : {roc_auc_score(test_data['late'], lgb_test_prob):.4f} (PR-AUC: {average_precision_score(test_data['late'], lgb_test_prob):.4f})")
