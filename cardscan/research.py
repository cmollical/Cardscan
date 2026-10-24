"""Fetch actual public sold listings and produce a personal-research estimate."""
import argparse
from datetime import date
import json
from pathlib import Path
from .pricing import Card
from .providers import read_json
from .public_web import PublicClient, RetrievalError, discover_pricecharting, research_quote, reported_sales_estimates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--as-of', type=date.fromisoformat, required=True)
    parser.add_argument('--cache', type=Path, default=Path('local-evidence/public-cache'))
    parser.add_argument('--limit', type=int, default=12, help='Maximum individually fetched listings (1–30)')
    parser.add_argument('--reports-only', action='store_true', help='Fetch public secondary reports without individual eBay checks')
    parser.add_argument('--report-window-days', type=int, default=30)
    parser.add_argument('--minimum-sales', type=int, default=3)
    parser.add_argument('--max-age-days', type=int, default=90)
    args = parser.parse_args()
    if not 1 <= args.limit <= 30:
        parser.error('--limit must be between 1 and 30')
    try:
        config = read_json(args.config.read_text())
        target = Card(**config['target'])
        client = PublicClient(args.cache)
        urls = list(config.get('ebay_urls', []))
        discovery = None
        secondary = None
        if config.get('pricecharting_url'):
            try:
                snapshot = client.get(config['pricecharting_url'])
                secondary = reported_sales_estimates(
                    snapshot, target, config.get('card_name', ''),
                    mapping_reviewed=config.get('reported_page_mapping_reviewed') is True,
                    as_of=args.as_of, max_age_days=args.report_window_days, minimum_sales=args.minimum_sales)
                discovered = discover_pricecharting(snapshot)
                urls.extend(discovered)
                discovery = {**snapshot.provenance(), 'candidate_count': len(discovered),
                             'role': 'link_discovery_only_not_price_evidence'}
            except RetrievalError as exc:
                discovery = {'url': config['pricecharting_url'], 'retrieval_error': str(exc)}
        if not urls:
            raise RetrievalError('No candidate listings available; see discovery failure')
        if args.reports_only:
            print(json.dumps({'scope': 'personal_research', 'direct_verification': 'not_attempted',
                              'target': config['target'], 'secondary_reports': secondary, 'discovery': discovery},
                             indent=2, allow_nan=False))
            return
        report = research_quote(target, list(dict.fromkeys(urls))[:args.limit], client, args.as_of,
                                set_aliases=tuple(config.get('set_aliases', [])),
                                standard_edition=config.get('standard_edition_is_unambiguous') is True,
                                minimum_sales=args.minimum_sales, max_age_days=args.max_age_days,
                                discovery=discovery)
        report['secondary_reports'] = secondary
        print(json.dumps(report, indent=2, allow_nan=False))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f'Research error: {exc}\n')


if __name__ == '__main__':
    main()
