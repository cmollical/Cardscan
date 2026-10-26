"""Explicit free API investigation, or replay of original locally retained exports.

No network without --live. Each URL is fetched once per invocation; no persistent
price cache/scheduler. TCGCSV permits one download daily: retain the originals and
use --documents for repeated analysis, never repeat --live on the same day.
"""
import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import time

from .references.transport import SourceDocument
from .structured_prices import CatalogBinding, TCGCSVProvider, TCGTrackingProvider, json_text


class InvestigationDocuments:
    def __init__(self, directory=None, transport=None):
        from .structured_prices import PublicExportTransport
        self.directory = Path(directory) if directory else None
        self.transport = transport or PublicExportTransport()
        self.seen = set()
        self.retrievals = []

    def get(self, url):
        if url in self.seen:
            raise ValueError('Duplicate endpoint in investigation; group cases by set before fetching')
        self.seen.add(url)
        if self.directory:
            key = sha256(url.encode()).hexdigest()[:12]
            meta = json.loads((self.directory / (key + '.json')).read_text())
            body = (self.directory / meta['file']).read_bytes()
            if meta['url'] != url or meta['status'] != 200 or sha256(body).hexdigest() != meta['sha256']:
                raise ValueError('Original document integrity failure')
            doc = SourceDocument(url, meta['retrieved_at'], meta['sha256'], json.loads(body, parse_float=Decimal))
        else:
            time.sleep(.15)
            doc = self.transport.get(url)
        self.retrievals.append({'url': doc.url, 'retrieved_at': doc.retrieved_at, 'sha256': doc.sha256})
        return doc


def run(bindings, documents):
    observations = []
    for b in bindings:
        for provider in (TCGCSVProvider(documents), TCGTrackingProvider(documents)):
            started = time.monotonic()
            try:
                result = provider.retrieve(b).to_dict()
                result.update(case_id=b.case_id, original_ai_proposal_usd={
                    'modern-common': '0.35', 'modern-chase': '345', 'vintage-charizard-lp': '365',
                    'first-edition-gengar': '320', 'japanese-charizard': '390'}.get(b.case_id))
                # AI proposals are comparison context, never reference ground truth.
                if not documents.directory:
                    result['request_latency_seconds'] = round(time.monotonic() - started, 6)
                observations.append(result)
            except (ValueError, OSError) as exc:
                observations.append({'provider': type(provider).__name__, 'case_id': b.case_id,
                                     'status': 'retrieval_failed', 'error_type': type(exc).__name__})
    return {'version': 'structured-price-investigation-v1', 'paid_api_calls': 0,
            'source_api_cost_usd': '0', 'mode': 'offline_original_responses' if documents.directory else 'live_free_endpoints',
            'observations': observations, 'documents': documents.retrievals,
            'condition_references': sum(r.get('status') == 'retrieved_condition_reference' for r in observations),
            'generic_references': sum(r.get('status') == 'retrieved_generic_reference' for r in observations),
            'approved_valuations': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--targets', type=Path, default=Path('experiments/structured-prices/targets.json'))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--live', action='store_true')
    mode.add_argument('--documents', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Refusing to overwrite an existing evidence record')
    bindings = [CatalogBinding.from_dict(b) for b in json.loads(args.targets.read_text())['bindings']]
    report = run(bindings, InvestigationDocuments(args.documents))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        f.write(json_text(report))
    print(f"Condition references: {report['condition_references']}; generic: {report['generic_references']}; no approved valuations")


if __name__ == '__main__':
    main()
