"""Read-only structured benchmarks; never convert these records into Sale objects.

Only reviewed public export endpoints are enabled. No pricing cache, retries,
HTML parsing, credentials, challenge handling, or valuation logic lives here.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from .references.models import FieldEvidence
from .references.transport import NoRedirects, SourceDocument, SourceRetrievalError

TRACKING_DOCS = 'https://openapi.tcgtracking.com/'
CSV_DOCS = 'https://tcgcsv.com/docs'
LANGUAGES = {'EN': 'english', 'JP': 'japanese', 'FR': 'french', 'DE': 'german',
             'ES': 'spanish', 'IT': 'italian', 'PT': 'portuguese', 'KO': 'korean',
             'CS': 'simplified chinese', 'CT': 'traditional chinese', 'RU': 'russian'}
VARIANTS = {'Normal': ('non-holo', None), 'Holofoil': ('holo', None),
            'Reverse Holofoil': ('reverse holo', None),
            '1st Edition Holofoil': ('holo', 'first edition'),
            'Unlimited Holofoil': ('holo', 'unlimited')}
CONDITIONS = {'NM', 'LP', 'MP', 'HP', 'DMG'}


def json_text(value):
    """Decimal amounts are serialized as exact strings, never binary floats."""
    return json.dumps(value, default=lambda x: format(x, 'f') if isinstance(x, Decimal)
                      else (_ for _ in ()).throw(TypeError(type(x).__name__)),
                      ensure_ascii=False, indent=2, allow_nan=False) + '\n'


def number_key(value):
    m = re.fullmatch(r'(\d+)/(\d+)', value or '')
    return (int(m[1]), int(m[2])) if m else None


def price(value):
    if value is None:
        return None
    if isinstance(value, bool) or isinstance(value, float):
        raise ValueError('JSON prices require Decimal parsing; floats/bools refused')
    try:
        amount = Decimal(value)
    except (TypeError, InvalidOperation) as exc:
        raise ValueError('Invalid source amount') from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError('Price must be positive and finite')
    return format(amount, 'f')


@dataclass(frozen=True)
class CatalogBinding:
    """Explicit reviewed crosswalk. Expected metadata must agree with source.

    Edition is deliberately not filled from this crosswalk. Language, condition,
    and finish come from the SKU row, not the requested target.
    """
    case_id: str
    category_id: int
    set_id: int
    product_id: int
    source_name: str
    source_set_name: str
    source_number: str
    target: dict
    review_source: str

    def __post_init__(self):
        if any(type(v) is not int or v <= 0 for v in (self.category_id, self.set_id, self.product_id)):
            raise ValueError('Positive explicit category, set and product identifiers required')
        if number_key(self.source_number) is None or number_key(self.target.get('number')) != number_key(self.source_number):
            raise ValueError('Reviewed binding must preserve the full collector number')
        if self.target.get('condition') not in CONDITIONS or type(self.target.get('graded')) is not bool:
            raise ValueError('Explicit condition and grading status required')

    @classmethod
    def from_dict(cls, value):
        return cls(**value)


@dataclass
class PriceObservation:
    provider: str
    requested_identity: dict
    product_id: int
    source_urls: list[str]
    status: str = 'context_only'
    price_type: str = 'published_market_reference'
    independent_upstream_verification: bool = False
    eligible_for_automatic_valuation: bool = False
    fields: dict[str, FieldEvidence] = field(default_factory=dict)
    related_rows: list[dict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    retrieved_at: str | None = None

    def to_dict(self):
        return asdict(self)


class StructuredPriceProvider(Protocol):
    """Multi-game-ready retrieval contract; no generic-to-condition conversion."""
    def retrieve(self, binding: CatalogBinding) -> PriceObservation: ...


class PublicExportTransport:
    """Bounded keyless GET. Endpoint allowlist prevents arbitrary URLs/redirects."""
    def __init__(self, *, timeout=20, max_bytes=5_000_000, opener=None):
        if not 1 <= timeout <= 30 or not 1 <= max_bytes <= 5_000_000:
            raise ValueError('Bounded transport limits required')
        self.timeout, self.max_bytes = timeout, max_bytes
        self.opener = opener or build_opener(NoRedirects())

    def get(self, url):
        p = urlsplit(url)
        if (p.scheme != 'https' or p.username or p.password or p.port not in (None, 443)
                or p.query or p.fragment):
            raise SourceRetrievalError('Plain approved HTTPS endpoint required')
        valid = ((p.hostname == 'tcgcsv.com' and re.fullmatch(r'/tcgplayer/\d+/\d+/(?:products|prices)', p.path))
                 or (p.hostname == 'openapi.tcgtracking.com' and re.fullmatch(r'/v1/\d+/sets/\d+/(?:cards|skus)', p.path)))
        if not valid:
            raise SourceRetrievalError('Endpoint not approved')
        try:
            req = Request(url, headers={'User-Agent': 'CardScanResearch/1.0', 'Accept': 'application/json'})
            with self.opener.open(req, timeout=self.timeout) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError('Unexpected response URL/status')
                if response.headers.get_content_type() != 'application/json':
                    raise ValueError('JSON required; HTML/challenges refused')
                body = response.read(self.max_bytes + 1)
                if len(body) > self.max_bytes:
                    raise ValueError('Oversized response')
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError('Duplicate JSON key')
                    result[key] = value
                return result
            data = json.loads(body, parse_float=Decimal, object_pairs_hook=unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite number')))
            if not isinstance(data, dict):
                raise ValueError('JSON object required')
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            raise SourceRetrievalError('Export retrieval failed: ' + type(exc).__name__) from exc
        return SourceDocument(url, datetime.now(timezone.utc).isoformat(), sha256(body).hexdigest(), data)


def evidence(doc, value, pointer, basis='structured_metadata', method='documented_json_field'):
    return FieldEvidence(value, 'missing' if value is None else basis, pointer, method, doc.url, doc.sha256)


def identity_check(binding, target, name, set_name, number):
    errors = []
    if target != binding.target:
        errors.append('Requested identity differs from reviewed catalog binding')
    if (name != binding.source_name or set_name != binding.source_set_name
            or number_key(number) is None or number_key(number) != number_key(binding.source_number)):
        errors.append('Source catalog identity does not match reviewed name/set/full number')
    return errors


class TCGTrackingProvider:
    """Condition/printing/language benchmarks from documented public SKU exports.

    Research permission is the provider's explicit open-API invitation. No claim
    is made about upstream licensing, billing accuracy, or individual sales.
    """
    def __init__(self, transport=None, *, purpose='personal_research'):
        if purpose != 'personal_research':
            raise ValueError('Commercial rights unresolved; research only')
        self.transport = transport or PublicExportTransport()

    def retrieve(self, binding):
        root = f'https://openapi.tcgtracking.com/v1/{binding.category_id}/sets/{binding.set_id}'
        return self.extract(binding, self.transport.get(root + '/cards'), self.transport.get(root + '/skus'))

    def extract(self, b, cards, skus):
        root = f'https://openapi.tcgtracking.com/v1/{b.category_id}/sets/{b.set_id}'
        if cards.url != root + '/cards' or skus.url != root + '/skus':
            raise ValueError('Document provenance does not match catalog binding')
        r = PriceObservation('tcgtracking', dict(b.target), b.product_id, [cards.url, skus.url], retrieved_at=skus.retrieved_at)
        products = cards.data.get('products', [])
        matches = [(i, p) for i, p in enumerate(products) if p.get('id') == b.product_id]
        if len(matches) != 1:
            r.status = 'rejected'; r.issues = ['Missing or duplicate catalog product']; return r
        i, p = matches[0]
        r.issues += identity_check(b, r.requested_identity, p.get('name'), cards.data.get('set_name'), p.get('number'))
        if cards.data.get('set_id') != b.set_id or skus.data.get('set_id') != b.set_id:
            r.issues.append('Source set ID mismatch')
        for key, value, pointer in [('name', p.get('name'), f'/products/{i}/name'),
                                    ('number', p.get('number'), f'/products/{i}/number'),
                                    ('set_name', cards.data.get('set_name'), '/set_name')]:
            r.fields[key] = evidence(cards, value, pointer)
        rows = skus.data.get('products', {}).get(str(b.product_id), {})
        if not isinstance(rows, dict):
            r.status = 'rejected'; r.issues.append('Invalid SKU map'); return r
        t = b.target
        eligible = []
        for sku_id, row in rows.items():
            finish, edition = VARIANTS.get(row.get('var'), (None, None))
            # Edition observed in this specific product's source text; not a general
            # Holofoil -> Unlimited default, and never CardTrader's property default.
            tip = p.get('ext_data', {}).get('TCGplayer Tip', '')
            edition_pointer = None
            if edition is None and 'This version from the Unlimited print run' in tip:
                edition = 'unlimited'; edition_pointer = f'/products/{i}/ext_data/TCGplayer Tip'
            exclusions = []
            if row.get('cnd') not in CONDITIONS or row.get('cnd') != t['condition']:
                exclusions.append('condition mismatch or unknown')
            if LANGUAGES.get(row.get('lng')) != t['language']:
                exclusions.append('language mismatch or unknown')
            if finish != t['finish']:
                exclusions.append('finish mismatch or unknown')
            if edition is not None and edition != t['edition']:
                exclusions.append('edition mismatch')
            if t['graded']:
                exclusions.append('Raw SKU reference cannot value graded card')
            try:
                amount = price(row.get('mkt'))
            except ValueError:
                amount = None; exclusions.append('invalid source market amount')
            if amount is None:
                exclusions.append('no reported market price')
            r.related_rows.append({'sku_id': sku_id, 'source_row': row,
                                   'selection_exclusions': exclusions})
            if not exclusions:
                eligible.append((sku_id, row, amount, finish, edition, edition_pointer))
        if r.issues or len(eligible) != 1:
            r.status = 'rejected' if r.issues or len(eligible) > 1 else 'unavailable'
            if len(eligible) != 1:
                r.issues.append('Expected exactly one matching priced SKU; found ' + str(len(eligible)))
            return r
        sku_id, row, amount, finish, edition, edition_pointer = eligible[0]
        base = f'/products/{b.product_id}/{sku_id}'
        for key, value, pointer in [('market_price', amount, base + '/mkt'), ('sku_id', sku_id, base),
                                    ('condition', row['cnd'], base + '/cnd'),
                                    ('language', LANGUAGES.get(row.get('lng')), base + '/lng'),
                                    ('finish', finish, base + '/var'),
                                    ('edition', edition, base + '/var'),
                                    ('updated_at', skus.data.get('updated'), '/updated')]:
            r.fields[key] = evidence(skus, value, pointer)
        if edition_pointer:
            r.fields['edition'] = evidence(cards, edition, edition_pointer, method='explicit_print_run_sentence')
        r.fields['currency'] = evidence(skus, 'USD', base + '/mkt', 'inferred',
                                       'TCGplayer-price convention; API does not emit currency')
        r.fields['shipping_excluded'] = evidence(skus, None, '')
        r.fields['tax_excluded'] = evidence(skus, None, '')
        r.fields['graded'] = evidence(skus, None, '')
        r.status = 'retrieved_condition_reference'
        try:
            updated = datetime.fromisoformat((skus.data.get('updated') or '').replace('Z', '+00:00'))
            retrieved = datetime.fromisoformat(skus.retrieved_at.replace('Z', '+00:00'))
            if updated.utcoffset() is None or retrieved.utcoffset() is None:
                raise ValueError('Timezone missing')
            age = (retrieved - updated).total_seconds()
            if age < -300:
                r.status = 'rejected'; r.issues.append('Source update time is in the future')
            elif age > 172800:
                r.issues.append('Set export older than 48 hours; freshness review required')
        except (ValueError, TypeError):
            r.issues.append('Missing or invalid timezone-aware set update timestamp')
        r.limitations = ['Provider-reported benchmark, not independently authenticated TCGplayer data or transactions',
                         'Currency USD follows upstream convention; response has no currency field',
                         'No per-SKU sale date, sold count, methodology, shipping/tax definition or price-observation timestamp',
                         'Set update time is not proof of a recent sale or a fresh individual price',
                         'No automatic valuation; commercial reuse and upstream redistribution rights unresolved']
        if edition is None:
            r.limitations.append('Edition unspecified in source; not filled from requested standard edition')
        if row.get('var') == '1st Edition Holofoil':
            nm = [x.get('mkt') for x in rows.values() if x.get('cnd') == 'NM'
                  and x.get('var') == row.get('var') and x.get('lng') == row.get('lng')]
            if nm and nm[0] is not None and Decimal(str(nm[0])) < Decimal(amount) and row['cnd'] != 'NM':
                r.issues.append('Condition price inversion: NM below selected played condition; review liquidity/methodology')
        if row['cnd'] == 'NM':
            if any(x.get('cnd') in {'LP', 'MP', 'HP', 'DMG'} and x.get('var') == row.get('var')
                   and x.get('lng') == row.get('lng') and x.get('mkt') is not None
                   and Decimal(str(x['mkt'])) > Decimal(amount) for x in rows.values()):
                r.issues.append('Condition price inversion: a played condition exceeds NM; retained without adjustment')
        return r


class TCGCSVProvider:
    """Catalog + subtype-level prices. Condition is always unknown, never NM."""
    def __init__(self, transport=None, *, purpose='personal_research'):
        if purpose != 'personal_research':
            raise ValueError('Commercial upstream rights require separate review')
        self.transport = transport or PublicExportTransport()

    def retrieve(self, binding):
        root = f'https://tcgcsv.com/tcgplayer/{binding.category_id}/{binding.set_id}'
        return self.extract(binding, self.transport.get(root + '/products'), self.transport.get(root + '/prices'))

    def extract(self, b, products, prices):
        root = f'https://tcgcsv.com/tcgplayer/{b.category_id}/{b.set_id}'
        if products.url != root + '/products' or prices.url != root + '/prices':
            raise ValueError('Document provenance mismatch')
        r = PriceObservation('tcgcsv', dict(b.target), b.product_id, [products.url, prices.url], retrieved_at=prices.retrieved_at)
        found = [(i, p) for i, p in enumerate(products.data.get('results', [])) if p.get('productId') == b.product_id]
        if len(found) != 1 or not products.data.get('success') or not prices.data.get('success'):
            r.status = 'rejected'; r.issues = ['Missing/duplicate product or unsuccessful source response']; return r
        i, p = found[0]
        numbers = [x.get('value') for x in p.get('extendedData', []) if x.get('name') == 'Number']
        number = numbers[0] if len(numbers) == 1 else None
        r.issues += identity_check(b, r.requested_identity, p.get('name'), b.source_set_name, number)
        if p.get('groupId') != b.set_id or p.get('categoryId') != b.category_id:
            r.issues.append('Product category/group mismatch')
        rows = [(j, row) for j, row in enumerate(prices.data.get('results', [])) if row.get('productId') == b.product_id
                and VARIANTS.get(row.get('subTypeName'), (None, None))[0] == b.target['finish']
                and VARIANTS.get(row.get('subTypeName'), (None, None))[1] in (None, b.target['edition'])]
        r.related_rows = [row for row in prices.data.get('results', []) if row.get('productId') == b.product_id]
        if r.issues or len(rows) != 1:
            r.status = 'rejected'; r.issues.append('No unique matching product subtype'); return r
        j, row = rows[0]
        try:
            amount = price(row.get('marketPrice'))
        except ValueError as exc:
            r.status = 'rejected'; r.issues.append(str(exc)); return r
        for key, value, pointer in [('name', p.get('name'), f'/results/{i}/name'),
                                    ('number', number, f'/results/{i}/extendedData'),
                                    ('product_url', p.get('url'), f'/results/{i}/url')]:
            r.fields[key] = evidence(products, value, pointer)
        for key, value, pointer in [('market_price', amount, f'/results/{j}/marketPrice'),
                                    ('finish', b.target['finish'], f'/results/{j}/subTypeName'),
                                    ('condition', None, ''), ('language', None, ''), ('edition', None, ''),
                                    ('graded', None, ''), ('updated_at', None, ''),
                                    ('shipping_excluded', None, ''), ('tax_excluded', None, '')]:
            r.fields[key] = evidence(prices, value, pointer)
        r.fields['currency'] = evidence(prices, 'USD', f'/results/{j}', 'inferred', 'USD explicitly documented at ' + CSV_DOCS)
        r.status = 'retrieved_generic_reference' if amount else 'unavailable'
        r.limitations = ['Product/subtype benchmark mixes conditions; cannot value requested condition',
                         'Language/edition/grading not established by price row',
                         'No per-price update timestamp; export build/HTTP dates are distinct',
                         'USD documented externally; no shipping/tax exclusion flag on marketPrice',
                         'Upstream commercial redistribution rights not established']
        return r
