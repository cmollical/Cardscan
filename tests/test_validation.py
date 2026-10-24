"""Evaluation math and holdout isolation using explicitly synthetic transactions."""
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import asdict, replace
from cardscan.validation import run
from test_evidence import record
from test_pricing import CARD, TODAY

MANIFEST = {'cases': [{'id': 'case-1', 'target': asdict(CARD)}]}


class ValidationTests(unittest.TestCase):
    def test_pending_does_not_claim_accuracy(self):
        with tempfile.TemporaryDirectory() as directory:
            report = run(MANIFEST, Path(directory), {}, TODAY)
        self.assertIsNone(report['median_absolute_percentage_error'])
        self.assertIsNone(report['exact_printing_match_accuracy_pct'])
        self.assertIsNone(report['incorrect_or_unsupported_valuation_pct'])
        self.assertEqual(report['status'], 'incomplete')

    def fixture(self, root, reference_price='100', labels=True):
        directory = root / 'case-1'
        directory.mkdir()
        prediction = [record(i) for i in range(3)]
        references = [dict(record(i + 10), item_price=reference_price, verified_by='independent reviewer') for i in range(3)]
        (directory / 'prediction.jsonl').write_text('\n'.join(map(json.dumps, prediction)))
        (directory / 'reference.jsonl').write_text('\n'.join(map(json.dumps, references)))
        annotations = {'reviewer': 'independent reviewer', 'target_verified': True, 'labels': [dict(source='synthetic', transaction_id=str(i),
                      printing_matches=labels, condition_matches=labels) for i in range(3)]}
        (directory / 'adjudication.json').write_text(json.dumps(annotations))
        return directory

    def test_disjoint_holdout_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            self.fixture(Path(directory))
            report = run(MANIFEST, Path(directory), {'synthetic': 'synthetic'}, TODAY)
        self.assertEqual(report['median_absolute_percentage_error'], 0)
        self.assertEqual(report['exact_printing_match_accuracy_pct'], 100)
        self.assertEqual(report['condition_match_accuracy_pct'], 100)
        self.assertEqual(report['incorrect_or_unsupported_valuation_pct'], 0)
        self.assertEqual(report['status'], 'complete')

    def test_independent_labels_can_disprove_input_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            self.fixture(Path(directory), labels=False)
            report = run(MANIFEST, Path(directory), {'synthetic': 'synthetic'}, TODAY)
        self.assertEqual(report['exact_printing_match_accuracy_pct'], 0)
        self.assertEqual(report['incorrect_or_unsupported_valuation_pct'], 100)
        self.assertIsNone(report['median_absolute_percentage_error'])

    def test_large_error_counts_as_incorrect(self):
        with tempfile.TemporaryDirectory() as directory:
            self.fixture(Path(directory), reference_price='200')
            report = run(MANIFEST, Path(directory), {'synthetic': 'synthetic'}, TODAY)
        self.assertGreater(report['median_absolute_percentage_error'], 10)
        self.assertEqual(report['within_10_pct_rate'], 0)
        self.assertEqual(report['incorrect_or_unsupported_valuation_pct'], 100)

    def test_reference_leakage_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            case = self.fixture(Path(directory))
            original = record(0)
            original['verified_by'] = 'independent reviewer'
            (case / 'reference.jsonl').write_text(json.dumps(original))
            with self.assertRaisesRegex(ValueError, 'overlaps'):
                run(MANIFEST, Path(directory), {'synthetic': 'synthetic'}, TODAY)

    def test_prediction_without_reference_is_unsupported(self):
        with tempfile.TemporaryDirectory() as directory:
            case = self.fixture(Path(directory))
            (case / 'reference.jsonl').unlink()
            report = run(MANIFEST, Path(directory), {'synthetic': 'synthetic'}, TODAY)
        self.assertEqual(report['incorrect_or_unsupported_valuation_pct'], 100)
        self.assertIsNone(report['median_absolute_percentage_error'])
