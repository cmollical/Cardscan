import unittest
from datetime import date
from decimal import Decimal
from dataclasses import replace
from cardscan.pricing import Card, Sale, evaluate

CARD = Card("pokemon", "base set", "4/102", "english", "unlimited", "holo", "LP")
TODAY = date(2026, 10, 24)

def sale(i, amount="100"):
    return Sale(CARD, Decimal(amount), Decimal("5"), TODAY,
                f"https://example.com/test-{i}", source="synthetic", transaction_id=str(i),
                verified_by="synthetic fixture", verified_on=TODAY,
                verification_notes="Synthetic test only", permission_reference="synthetic",
                price_confirmed=True, condition_confirmed=True)

class PricingTests(unittest.TestCase):
    def test_median_with_shipping(self):
        result = evaluate(CARD, [sale(1, "100"), sale(2, "120"), sale(3, "110")], TODAY)
        self.assertEqual(result.value, Decimal("115.00"))

    def test_not_enough_sales(self):
        self.assertIsNone(evaluate(CARD, [sale(1)], TODAY).value)

    def test_reject_wrong_condition(self):
        wrong = replace(sale(1), card=replace(CARD, condition="NM"))
        result = evaluate(CARD, [wrong, sale(2), sale(3)], TODAY)
        self.assertIsNone(result.value)
        self.assertEqual(len(result.rejected), 1)

    def test_reject_non_sales_and_duplicates(self):
        records = [sale(1), replace(sale(2), sold=False), sale(1), sale(3)]
        result = evaluate(CARD, records, TODAY)
        self.assertIsNone(result.value)
        self.assertEqual(len(result.rejected), 2)

    def test_reject_graded_bundle_and_old(self):
        records = [replace(sale(1), graded=True), replace(sale(2), bundle=True),
                   replace(sale(3), sold_on=date(2026, 1, 1))]
        result = evaluate(CARD, records, TODAY)
        self.assertEqual(len(result.rejected), 3)
        self.assertIsNone(result.value)

if __name__ == "__main__":
    unittest.main()

