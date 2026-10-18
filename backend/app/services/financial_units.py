"""Read explicit monetary-unit declarations without guessing from numeric values."""
import re

import pandas as pd


def workbook_units(path):
    declarations = set()
    # Only explicit currency + scale declarations qualify. Share-count labels
    # such as 'Adjusted Equity Shares in Cr' must never set monetary units.
    pattern = re.compile(
        r'(₹|rs\.?|inr|rupees|usd|us\$|eur|gbp)\s*(?:in\s+)?'
        r'(crores?|cr\.?|lakhs?|lacs?|millions?|mn|billions?|bn|thousands?)\b',
        re.IGNORECASE,
    )
    try:
        with pd.ExcelFile(path) as book:
            for sheet in book.sheet_names:
                header = book.parse(sheet, header=None, nrows=15)
                for value in header.to_numpy().flat:
                    if not isinstance(value, str):
                        continue
                    for currency, scale in pattern.findall(value):
                        currency = currency.lower().rstrip('.')
                        currency = 'INR' if currency in ('₹', 'rs', 'inr', 'rupees') else {'us$': 'USD'}.get(currency, currency.upper())
                        scale = scale.lower().rstrip('.')
                        scale = ('crore' if scale.startswith('cr') else 'lakh' if scale.startswith(('la',))
                                 else 'million' if scale.startswith('m') else 'billion' if scale.startswith('b') else 'thousand')
                        declarations.add((currency, scale))
    except (OSError, ValueError, ImportError):
        return {'label': 'Source units unspecified', 'status': 'unknown'}
    if len(declarations) == 1:
        currency, scale = declarations.pop()
        return {'label': f'{currency} {scale}', 'status': 'detected'}
    return {'label': 'Source units unspecified', 'status': 'conflicting' if declarations else 'unknown'}
