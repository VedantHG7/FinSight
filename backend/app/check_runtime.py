"""Verify saved ML artifacts and native dependencies before accepting local work."""
import sys
from pathlib import Path


def check_runtime():
    import joblib
    import numpy as np
    import pandas as pd
    from app.services.ml_explanations import explain_rows

    artifacts = Path(__file__).resolve().parent / 'models' / 'ml_artifacts'
    model = joblib.load(artifacts / 'isolation_forest.pkl')
    scaler = joblib.load(artifacts / 'robust_scaler.pkl')
    imputer = joblib.load(artifacts / 'imputer.pkl')
    features = list(joblib.load(artifacts / 'feature_columns.pkl'))
    sample = pd.DataFrame([imputer.statistics_], columns=features)
    filled = pd.DataFrame(imputer.transform(sample), columns=features)
    scaled = pd.DataFrame(scaler.transform(filled), columns=features)
    prediction = model.predict(scaled)
    score = model.decision_function(scaled)
    if len(prediction) != 1 or prediction[0] not in (-1, 1) or not np.isfinite(score).all():
        raise RuntimeError('Saved model did not produce a valid prediction.')
    explanation = explain_rows(model, scaler, imputer, sample, filled, artifacts)
    if explanation[0]['status'] != 'available':
        raise RuntimeError('SHAP explanation could not be verified.')


def main():
    try:
        check_runtime()
    except Exception as error:
        print(f'FinSight ML runtime check failed: {type(error).__name__}: {error}', file=sys.stderr)
        print('Check this Python environment and its installed dependencies. If Windows Application Control blocks a file, contact the device administrator to review the blocked package.', file=sys.stderr)
        return 1
    print('FinSight ML runtime ready: saved model prediction and SHAP verified.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
