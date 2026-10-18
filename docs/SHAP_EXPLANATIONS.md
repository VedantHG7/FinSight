# SHAP explanations in FinSight

Implemented 5 October 2026. Previously, ML evidence ranked deviations from the uploaded company's median. Those descriptive movements were not explanations of the Isolation Forest itself. They remain labeled as descriptive context in the artifact; the ML/XAI screens now use SHAP.

## What is explained

The prediction still comes from the saved Isolation Forest, feature list, training imputer and RobustScaler. No model is retrained. The explained output is `anomaly margin = -model.decision_function(scaled_inputs)`. Positive margins are flagged; zero or negative margins are not flagged. This is neither a probability nor a financial amount. The existing `Anomaly Score` field represents this same margin; the old field name is preserved for compatibility.

SHAP `PermutationExplainer` explains a callable that applies the saved scaler and then calculates this exact margin. Explaining this callable avoids incorrectly labeling TreeSHAP isolation-path-length values as decision-score contributions.

The reference is one synthetic vector containing each saved training median from `imputer.statistics_`. It is explicitly **not** an industry benchmark, a real reference company, or the average prediction over the training population. Original training rows are not needed or reconstructed.

For each year:

```text
Reference profile's anomaly margin + sum of every SHAP contribution
    = this year's anomaly margin
```

Positive contributions move toward anomaly; negative contributions move away, relative to the reference. Feature attribution is approximate: seed 42 and a budget of `8 * (2 * number_of_features + 1)` evaluations per row. SHAP may skip unchanged features. Additivity is verified within 0.000001 before publishing explanations. Passing this check verifies score reconstruction, not convergence of each estimated contribution.

## Missing data and interpretation

The pipeline preserves missing financial values outside ML. SHAP uses the same filled inputs as the prediction and identifies each filled feature separately, with null `observed_value` and an explicit `model_value`. A missing input filled with its reference median can have zero contribution; that is not evidence that missing information is harmless. A year with no observed model features has neither a prediction nor SHAP attribution.

Correlated financial metrics share attribution. Independently masked feature combinations can be unrealistic. SHAP describes model behavior relative to the chosen reference; it does not establish fraud, accounting error, a business cause, calibrated confidence or a sector benchmark.

## Saved data and interfaces

Each ML row now includes a `SHAP` object with status, method/version, reference, base/output values, contribution sum, reconstruction error, per-feature values and contributions, reproducibility settings, and SHA-256 fingerprints of the four model artifacts. All features are saved, even though the interface initially shows only six.

The object is also included in XAI rows and report JSON. PDFs contain a narrative, the additive score calculation, and the largest six contributions. The browser offers year selection, signed contribution bars, original/filled input labels, all-feature expansion, source-review links and method details. Finding review uses the same explanation component.

The ML screen includes normal-year conclusions, cutoff explanations, factors moving away from anomaly and movements to watch. Explainable AI now has a separate rule-focused screen: it loads the complete saved rule results, explains every failure, and provides year/severity/search filters. It shows recorded inputs, the failure condition, significance, suggested source checks and review links, with a compact ML summary. Failed rules remain visible when no ML anomaly is flagged. No failed rules, filtered-out results, loading errors and skipped checks have distinct states.

Existing analyses use all saved rule results rather than the older eight-item XAI excerpt. New XAI artifacts preserve every failed rule. New reconciliation results also save prior balances, differences and configured tolerances; older missing details are explicitly left unknown. These additions do not change rule verdicts. Explanations describe the implemented checks and do not establish a business cause or confirmed misstatement.

An import or computation/validation failure is logged and produces an explicit unavailable explanation instead of fabricated attribution. Pipeline cancellation still propagates from checkpoints. Older saved analyses remain unchanged: upload a workbook as a new analysis to obtain SHAP while preserving prior reviews and report history.

## Runtime and validation

Dependencies: `shap==0.49.1`, `numba==0.61.2`, alongside the existing NumPy 2.2.6 and scikit-learn 1.7.2. Numba is pinned because the newer automatically selected Windows wheel was blocked by this machine's Application Control policy. No Windows security settings were changed. Python 3.13 is the tested local runtime.

Backend tests exercise real-model additivity, cutoff direction, reference identity, missing-value labeling, deterministic output, unavailable explanations and nonconsecutive row indices. The existing end-to-end browser test now checks persisted SHAP output, year selection, feature expansion, review integration and desktop/mobile layout.

Run `python -m unittest discover -s tests -v` from `backend`. With the API, worker and frontend running, run `npm --prefix frontend run test:workspace` from the root. Browser tests create an isolated local QA workspace and retain its artifacts for inspection.

Implementation: `backend/app/services/ml_explanations.py`, `backend/app/services/analysis_service.py`, `frontend/src/MLInsights.jsx`, and `backend/tests/test_shap_explanations.py`.

References: [SHAP PermutationExplainer](https://shap.readthedocs.io/en/stable/generated/shap.PermutationExplainer.html) and [scikit-learn IsolationForest score convention](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.IsolationForest.html).
