"""Probe the signed-out TCGplayer sales request; never solve request challenges.

Run: python -m cardscan.tcgplayer_probe
This is a diagnostic, not an enabled pricing provider. No credentials, request
validation tokens, pagination or sign-in-gated records are requested.
"""
from datetime import datetime, timezone
import hashlib
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SALES_URL = 'https://mpapi.tcgplayer.com/v2/product/42382/latestsales'
# IDs observed in the live product/categoryfilters response. Limit matches the
# signed-out five-row view in the first-party client, not its signed-in pagination.
PAYLOAD = {'conditions': [3], 'variants': [11], 'languages': [1],
           'listingType': 'All', 'limit': 5}


def probe(opener=urlopen):
    request = Request(SALES_URL, data=json.dumps(PAYLOAD).encode(), method='POST',
                      headers={'User-Agent': 'CardScanResearch/0.4 (personal pricing research)',
                               'Accept': 'application/json', 'Content-Type': 'application/json'})
    report = {'product_id': 42382, 'method': 'POST', 'url': SALES_URL,
              'payload': PAYLOAD, 'observed_at': datetime.now(timezone.utc).isoformat(),
              'live_sales_retrieved': False}
    try:
        with opener(request, timeout=20) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return {**report, 'status': 'invalid_response', 'reason': 'response too large'}
            report.update(http_status=response.status, response_sha256=hashlib.sha256(raw).hexdigest())
            # Do not mark an HTML challenge page with HTTP 200 as a success.
            if 'application/json' not in response.headers.get('Content-Type', ''):
                return {**report, 'status': 'invalid_response', 'reason': 'expected JSON; no challenge bypass'}
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                return {**report, 'status': 'schema_review_required'}
            # A future successful response must be inspected and an adapter
            # validated before exposing any numbers as a CardScan valuation.
            return {**report, 'status': 'response_available_for_schema_review',
                    'returned_row_count': len(payload['data']),
                    'live_sales_retrieved': bool(payload['data']), 'valuation': None}
    except HTTPError as exc:
        raw = exc.read(2_000_000)
        return {**report, 'http_status': exc.code,
                'response_sha256': hashlib.sha256(raw).hexdigest(),
                'status': 'access_denied' if exc.code in (401, 403) else 'http_error',
                'reason': 'No retry, credential injection or request-validation bypass attempted'}
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {**report, 'status': 'retrieval_error', 'reason': str(exc)}


def main():
    print(json.dumps(probe(), indent=2, allow_nan=False))


if __name__ == '__main__':
    main()
