"""Repeatable holdout evaluation. No sales are fetched or invented by this module."""
import argparse
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from statistics import median

from .pricing import Card, evaluate, evidence_url
from .providers import ManualCompsProvider, read_json


def _percent(numerator, denominator):
    return float(Decimal(numerator) * 100 / denominator) if denominator else None


def run(manifest: dict, root: Path, permissions: dict, as_of: date):
    """Missing files mean pending, never success. References must be disjoint.

    Independent annotations judge accepted comps, not the input parser's own
    matching decisions. Reviewer identity is attested, not authenticated.
    """
    rows, errors = [], []
    matched, conditioned, labeled = 0, 0, 0
    sufficient, emitted, unsupported, scored = 0, 0, 0, 0
    completed = assessed = accepted_total = 0
    ids = [case['id'] for case in manifest['cases']]
    if len(ids) != len(set(ids)) or any(not value or not all(c.isalnum() or c in '-_' for c in value) for value in ids):
        raise ValueError('Case IDs must be unique safe directory names')
    for case in manifest['cases']:
        target = Card(**case['target'])
        directory = Path(root) / case['id']
        prediction_path = directory / 'prediction.jsonl'
        if not prediction_path.exists():
            rows.append({'id': case['id'], 'status': 'pending_evidence'})
            continue
        completed += 1
        sales = ManualCompsProvider(prediction_path, permissions).retrieve(target, as_of)
        prediction = evaluate(target, sales, as_of)
        accepted_total += len(prediction.accepted)
        has_value = prediction.value is not None
        emitted += has_value
        sufficient += has_value
        row = {'id': case['id'], 'prediction': prediction.to_dict(), 'status': 'pending_reference'}
        reference_path = directory / 'reference.jsonl'
        annotation_path = directory / 'adjudication.json'
        bad = False
        if reference_path.exists() and annotation_path.exists():
            reference_sales = ManualCompsProvider(reference_path, permissions).retrieve(target, as_of)
            annotation = read_json(annotation_path.read_text())
            if annotation.get('target_verified') is not True:
                raise ValueError(f"{case['id']}: independent target printing review required")
            reviewer = annotation.get('reviewer')
            if not isinstance(reviewer, str) or not reviewer.strip() or reviewer in {s.verified_by for s in sales}:
                raise ValueError(f"{case['id']}: independent reviewer required")
            if any(s.verified_by != reviewer for s in reference_sales):
                raise ValueError(f"{case['id']}: reference verifier must be independent reviewer")
            # Compare all supplied evidence, not just accepted subsets.
            if ({s.key for s in sales} & {s.key for s in reference_sales}
                    or {evidence_url(s.url) for s in sales} & {evidence_url(s.url) for s in reference_sales}):
                raise ValueError(f"{case['id']}: reference evidence overlaps prediction evidence")
            labels = {}
            for label in annotation['labels']:
                key = (label['source'], label['transaction_id'])
                if key in labels or type(label['printing_matches']) is not bool or type(label['condition_matches']) is not bool:
                    raise ValueError(f"{case['id']}: invalid independent labels")
                labels[key] = label
            for sale in prediction.accepted:
                label = labels.get(sale.key)
                if label is None:
                    bad = True
                    continue
                labeled += 1
                matched += label['printing_matches']
                conditioned += label['condition_matches']
                bad |= not label['printing_matches'] or not label['condition_matches']
            assessed += 1
            reference = evaluate(target, reference_sales, as_of)
            row['reference'] = reference.to_dict()
            if has_value and reference.value is not None and not bad:
                error = abs(prediction.value - reference.value) / reference.value * 100
                errors.append(error)
                scored += 1
                bad |= error > 10
                row.update(status='scored', absolute_percentage_error=str(error))
            elif has_value:
                bad = True
                row['status'] = 'unsupported_prediction'
            else:
                row['status'] = 'abstained'
        elif has_value:
            bad = True
            row['status'] = 'unsupported_prediction'
        unsupported += has_value and bad
        rows.append(row)
    return {
        'as_of': as_of.isoformat(), 'planned_cards': len(ids), 'cards_with_input': completed,
        'valuations_emitted': emitted, 'independently_scored_cards': scored,
        'accepted_comps_independently_labeled': labeled,
        'accepted_comps_total': accepted_total,
        'annotation_coverage_pct': _percent(labeled, accepted_total),
        'independently_assessed_cards': assessed,
        'exact_printing_match_accuracy_pct': _percent(matched, labeled),
        'condition_match_accuracy_pct': _percent(conditioned, labeled),
        'median_absolute_percentage_error': float(median(errors)) if errors else None,
        'within_10_pct_rate': _percent(sum(e <= 10 for e in errors), len(errors)),
        'sufficient_evidence_pct_of_planned': _percent(sufficient, len(ids)),
        'incorrect_or_unsupported_valuation_pct': _percent(unsupported, emitted),
        'status': 'complete' if len(ids) > 0 and completed == len(ids) and assessed == len(ids) else 'incomplete',
        'cases': rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('evidence_root', type=Path)
    parser.add_argument('permissions', type=Path)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    args = parser.parse_args()
    try:
        report = run(read_json(args.manifest.read_text()), args.evidence_root,
                     read_json(args.permissions.read_text()), args.as_of)
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f'Evaluation error: {exc}\n')
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
