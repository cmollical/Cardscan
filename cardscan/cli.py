"""Run: python -m cardscan.cli TARGET.json COMPS.jsonl PERMISSIONS.json --as-of YYYY-MM-DD"""
import argparse
from datetime import date
import json
from pathlib import Path
from .pricing import Card, evaluate
from .providers import ManualCompsProvider, read_json


def main():
    parser = argparse.ArgumentParser(description="Offline verified-comps valuation; no live pricing")
    parser.add_argument("target", type=Path)
    parser.add_argument("comps", type=Path)
    parser.add_argument("permissions", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat, required=True)
    parser.add_argument("--minimum-sales", type=int, default=3)
    args = parser.parse_args()
    try:
        target = Card(**read_json(args.target.read_text()))
        provider = ManualCompsProvider(args.comps, read_json(args.permissions.read_text()))
        result = evaluate(target, provider.retrieve(target, args.as_of), args.as_of,
                          minimum_sales=args.minimum_sales)
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(2, f"Input error: {exc}\n")
    print(json.dumps(result.to_dict(), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
