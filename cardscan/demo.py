"""Synthetic example. NOT a live market valuation."""
from datetime import date
from decimal import Decimal
from .pricing import Card, Sale, evaluate

def main():
    card = Card("pokemon", "base set", "4/102", "english", "unlimited", "holo", "LP")
    amounts = ["100", "110", "120"]
    sales = [
        Sale(card, Decimal(amount), Decimal("5"), date(2026, 10, 20),
             f"https://example.com/synthetic-sale-{index}",
             source="synthetic", transaction_id=str(index), verified_by="synthetic fixture",
             verified_on=date(2026, 10, 24), verification_notes="Synthetic example only",
             permission_reference="synthetic", price_confirmed=True, condition_confirmed=True)
        for index, amount in enumerate(amounts, 1)
    ]
    result = evaluate(card, sales, as_of=date(2026, 10, 24))
    print(f"SYNTHETIC EXAMPLE ONLY: {result.value} | {result.reason}")

if __name__ == "__main__":
    main()

