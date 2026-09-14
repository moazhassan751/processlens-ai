"""
ProcessLens — Central Machine Learning & Risk Threshold Configuration
======================================================================
This module establishes the centrally configured risk threshold selected
under Model Improvement Part 2.

The threshold is chosen using 5-fold out-of-fold cross-validation on the
training set, maximizing F1 subject to the operational constraint of
precision >= 0.30, without any holdout data leakage.
"""

from typing import Dict, Any

# Primary selected operating threshold (Part 2)
DEFAULT_RISK_THRESHOLD: float = 0.19

# Methodology specification
THRESHOLD_SELECTION_METHOD: str = "OOF F1 with precision >= 0.30"

# Alternative operating points documented in Part 2 analysis
OPERATING_POINTS: Dict[str, Dict[str, Any]] = {
    "conservative": {
        "threshold": 0.40,
        "precision": 0.3966,
        "recall": 0.3966,
        "f1": 0.3966,
        "fpr": 0.1923,
        "fnr": 0.6034,
        "flagged_pct": 24.2,
        "description": "High-precision threshold for resource-constrained operations",
    },
    "balanced": {
        "threshold": 0.19,
        "precision": 0.3309,
        "recall": 0.7931,
        "f1": 0.4670,
        "fpr": 0.5110,
        "fnr": 0.2069,
        "flagged_pct": 57.9,
        "description": "Selected primary threshold maximizing F1 with precision >= 0.30",
    },
    "sensitive": {
        "threshold": 0.10,
        "precision": 0.2784,
        "recall": 0.9310,
        "f1": 0.4286,
        "fpr": 0.7692,
        "fnr": 0.0690,
        "flagged_pct": 80.8,
        "description": "High-recall threshold for mission-critical zero-tolerance SLAs",
    },
}


def classify_risk_probability(
    probability: float | None,
    threshold: float = DEFAULT_RISK_THRESHOLD,
) -> str:
    """
    Classify a continuous late risk probability into an operational risk label.
    Returns 'Insufficient Data' if probability is None.
    """
    if probability is None:
        return "Insufficient Data"
    return "Late Risk" if probability >= threshold else "On Track"
