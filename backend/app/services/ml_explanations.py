"""Explain the actual anomaly margin against a saved training-median profile."""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import shap

VERSION = 'shap-margin-v1'
PERMUTATIONS = 8
SEED = 42
REFERENCE = 'Synthetic profile made from the saved training median of each feature'
LIMITATION = ('SHAP explains this model relative to a synthetic training-median profile. '
              'It does not prove fraud or a business cause. Correlated financial metrics '
              'share attribution, and masked combinations may not be realistic companies. '
              'Contributions are approximate and are not probabilities or financial amounts.')


def explain_rows(model, scaler, imputer, observed, filled, artifacts: Path, checkpoint=None):
    features = list(filled.columns)
    reference = np.asarray(imputer.statistics_, dtype=float).reshape(1, -1)
    if reference.shape[1] != len(features) or not np.isfinite(reference).all():
        raise ValueError('Training median reference does not match the model features.')

    def margin(values):
        frame = pd.DataFrame(values, columns=features)
        scaled = pd.DataFrame(scaler.transform(frame), columns=features)
        return -model.decision_function(scaled)

    explainer = shap.PermutationExplainer(margin, reference, feature_names=features, seed=SEED)
    fingerprints = {name: hashlib.sha256((artifacts / name).read_bytes()).hexdigest()
                    for name in ('isolation_forest.pkl', 'robust_scaler.pkl', 'imputer.pkl', 'feature_columns.pkl')}
    result = {}
    for index in filled.index:
        if checkpoint:
            checkpoint()
        values = filled.loc[[index]].to_numpy(dtype=float)
        explanation = explainer(values, max_evals=PERMUTATIONS * (2 * len(features) + 1), silent=True)
        contributions = np.asarray(explanation.values[0], dtype=float)
        base = float(explanation.base_values[0])
        output = float(margin(values)[0])
        residual = output - (base + float(contributions.sum()))
        if not np.isfinite(contributions).all() or not np.isfinite([base, output]).all() or abs(residual) > 1e-6:
            raise ValueError('SHAP contributions failed the model-score reconstruction check.')
        items = []
        for position, feature in enumerate(features):
            missing = bool(pd.isna(observed.loc[index, feature]))
            value = float(values[0, position])
            effect = float(contributions[position])
            label = feature.replace('_', ' ')
            direction = 'toward anomaly' if effect > 1e-10 else 'away from anomaly' if effect < -1e-10 else 'neutral'
            items.append({'feature': feature, 'label': label, 'observed_value': None if missing else value,
                          'model_value': value, 'reference_value': float(reference[0, position]),
                          'imputed': missing, 'contribution': effect, 'direction': direction,
                          'interpretation': (f'{label} was missing and filled with its training median; it is not reported evidence.' if missing else
                            f'{label} moved the model score {direction} relative to the reference profile.'),
                          'review_action': (f'Obtain the missing {label} value and rerun the analysis.' if missing else
                            f'Reconcile {label} to the workbook and supporting schedule; compare its calculation and movement with prior periods.')})
        items.sort(key=lambda item: abs(item['contribution']), reverse=True)
        positive = [item for item in items if item['contribution'] > 1e-10 and not item['imputed']]
        negative = [item for item in items if item['contribution'] < -1e-10 and not item['imputed']]
        lead = (f'The anomaly margin is {output:.6f}, above the zero cutoff, so the model flagged this year.' if output > 0 else
                f'The anomaly margin is {output:.6f}, at or below the zero cutoff, so the model did not flag this year.')
        if positive:
            lead += ' The largest pushes toward anomaly were ' + ', '.join(i['label'] for i in positive[:3]) + '.'
        if negative:
            lead += ' Offsetting factors were ' + ', '.join(i['label'] for i in negative[:3]) + '.'
        if not positive and not negative:
            lead += ' No material feature contributions differed from the reference profile.'
        result[index] = {'status': 'available', 'version': VERSION, 'method': 'Permutation SHAP',
                         'shap_version': shap.__version__, 'seed': SEED, 'permutation_budget': PERMUTATIONS,
                         'output_name': 'Anomaly margin (-decision_function)', 'threshold': 0,
                         'base_value': base, 'output_value': output, 'contribution_sum': float(contributions.sum()),
                         'reconstruction_error': residual, 'model_offset': float(model.offset_),
                         'reference': REFERENCE, 'limitations': LIMITATION, 'artifacts_sha256': fingerprints,
                         'features': items, 'summary': lead}
    return result
