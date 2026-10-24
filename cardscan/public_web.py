"""Personal-research retrieval of public pages. No credentials or challenge bypass.

PriceCharting supplies candidate links only. Prices used in a quote come from
an individually checked eBay sold page, never a search snippet or guide estimate.
"""
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, parse_qs
from urllib.request import HTTPRedirectHandler, Request, build_opener
import unicodedata

from .pricing import Card, Sale, evaluate


class RetrievalError(ValueError):
    pass


@dataclass
class Node:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def text(self):
        return ' '.join(' '.join(c.text() if isinstance(c, Node) else c for c in self.children).split())

    def walk(self):
        yield self
        for child in self.children:
            if isinstance(child, Node):
                yield from child.walk()


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Node('document')
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.stack[-1].children.append(Node(tag, dict(attrs)))

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, value):
        self.stack[-1].children.append(value)

    def nodes(self, tag):
        return [node for node in self.root.walk() if node.tag == tag]

    def visible_text(self):
        def texts(node):
            if node.tag in {'script', 'style', 'noscript'}:
                return []
            result = []
            for child in node.children:
                result.extend(texts(child) if isinstance(child, Node) else [child])
            return result
        return ' '.join(' '.join(texts(self.root)).split())


def _host_allowed(url):
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.hostname not in {'www.ebay.com', 'www.pricecharting.com', 'www.tcgplayer.com'}
            or parts.username or parts.password or parts.port not in (None, 443)):
        raise RetrievalError('Only approved public HTTPS source hosts are supported')


class _Redirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _host_allowed(newurl)
        if any(word in urlsplit(newurl).path.lower() for word in ('captcha', 'splashui', 'signin')):
            raise RetrievalError('Access challenge or sign-in required; retrieval stopped')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True)
class Snapshot:
    requested_url: str
    final_url: str
    observed_at: str
    sha256: str
    html: str

    def provenance(self):
        return {key: getattr(self, key) for key in ('requested_url', 'final_url', 'observed_at', 'sha256')}


class PublicClient:
    """At most one request/sec; bounded reads, explicit failures, hash-addressed cache."""
    def __init__(self, cache: Path, interval=1.0):
        if interval < 1:
            raise ValueError('Request interval must be at least one second')
        self.cache = Path(cache)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.interval = interval
        self.last_request = 0.0
        self.opener = build_opener(_Redirects())

    def get(self, url):
        _host_allowed(url)
        time.sleep(max(0, self.interval - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        try:
            request = Request(url, headers={'User-Agent': 'CardScanResearch/0.3 (personal research; no automated purchasing)'})
            with self.opener.open(request, timeout=20) as response:
                body = response.read(3_000_001)
                final_url = response.geturl()
                if len(body) > 3_000_000:
                    raise RetrievalError('Source page exceeds maximum size')
                if 'text/html' not in response.headers.get('Content-Type', ''):
                    raise RetrievalError('Source did not return HTML')
                html = body.decode('utf-8')
        except (HTTPError, URLError, TimeoutError, UnicodeError, OSError) as exc:
            raise RetrievalError(f'Public page unavailable: {exc}') from exc
        _host_allowed(final_url)
        if re.search(r'(captcha|pardon our interruption|verify (?:you are|yourself)|checking your browser)',
                     Document(html).visible_text(), re.I):
            raise RetrievalError('Access challenge detected; retrieval stopped')
        snapshot = Snapshot(url, final_url, datetime.now(timezone.utc).isoformat(), hashlib.sha256(body).hexdigest(), html)
        (self.cache / (snapshot.sha256 + '.html')).write_bytes(body)
        (self.cache / (snapshot.sha256 + '.json')).write_text(json.dumps(snapshot.provenance(), indent=2) + '\n')
        return snapshot


def _module(document, name):
    """Decode a JSON object embedded in delivered HTML; never execute Javascript."""
    pattern = re.compile(r'"' + re.escape(name) + r'"\s*:\s*')
    for script in document.nodes('script'):
        text = ''.join(c for c in script.children if isinstance(c, str))
        for match in pattern.finditer(text):
            try:
                value, _ = json.JSONDecoder().raw_decode(text[match.end():])
                if isinstance(value, dict):
                    return value
            except ValueError:
                continue
    return {}


def _label_text(value):
    if isinstance(value, list):
        return ' '.join(filter(None, (_label_text(item) for item in value)))
    if isinstance(value, dict):
        if value.get('_type') == 'TextSpan':
            return value.get('text', '')
        return ' '.join(filter(None, (_label_text(item) for item in value.values())))
    return ''


def _specifics(value):
    result = {}
    if isinstance(value, dict):
        if value.get('_type') == 'LabelsValues':
            result[_label_text(value.get('labels', [])).strip()] = _label_text(value.get('values', [])).strip()
        else:
            for child in value.values():
                result.update(_specifics(child))
    elif isinstance(value, list):
        for child in value:
            result.update(_specifics(child))
    return result


def _money(value):
    try:
        amount = Decimal(str(value))
        return amount if amount.is_finite() and amount > 0 else None
    except (InvalidOperation, ValueError):
        return None


def _canonical_item(url):
    parts = urlsplit(url)
    match = re.fullmatch(r'/itm/(?:[^/]+/)?(\d{9,15})/?', parts.path)
    if parts.hostname != 'www.ebay.com' or not match:
        raise RetrievalError('URL is not an individual eBay item page')
    return 'https://www.ebay.com/itm/' + match.group(1), match.group(1)


@dataclass(frozen=True)
class Listing:
    url: str
    item_id: str
    title: str
    item_price: Decimal | None
    currency: str | None
    sold_on: date | None
    sold: bool
    best_offer: bool
    specifics: dict
    shipping_quote: str
    evidence: dict
    parse_issues: tuple


def parse_ebay(snapshot: Snapshot):
    canonical, item_id = _canonical_item(snapshot.requested_url)
    # A product-page redirect must never substitute a current asking price.
    final_canonical, final_id = _canonical_item(snapshot.final_url)
    if final_id != item_id:
        raise RetrievalError('Item URL redirected to a different listing')
    document = Document(snapshot.html)
    semantic = _module(document, 'SEMANTIC_DATA')
    if str(semantic.get('listingId', '')) != item_id:
        raise RetrievalError('Missing or mismatched listing identity in page')
    products = []
    for script in document.nodes('script'):
        if script.attrs.get('type') == 'application/ld+json':
            try:
                data = json.loads(''.join(c for c in script.children if isinstance(c, str)))
            except ValueError:
                continue
            if isinstance(data, dict) and data.get('@type') == 'Product':
                products.append(data)
    if len(products) != 1:
        raise RetrievalError('Expected exactly one structured listing product')
    product = products[0]
    offers = product.get('offers', {})
    if not isinstance(offers, dict) or offers.get('url', '').split('?')[0] != canonical:
        raise RetrievalError('Structured product offer belongs to another URL')
    visible = document.visible_text()
    # A global "N sold" counter or OutOfStock alone does NOT prove this sale.
    sold = bool(re.search(r'(?:This (?:Buy It Now )?listing|Item) sold on\b', visible, re.I))
    sold = sold and semantic.get('listingStatus') == 'ENDED'
    raw_date = semantic.get('endDate', {}).get('value')
    issues = []
    sold_on = None
    if raw_date:
        try:
            sold_on = datetime.fromisoformat(raw_date.replace('Z', '+00:00')).date()
        except (ValueError, TypeError):
            issues.append('invalid explicit sale end date')
    else:
        issues.append('sale year/date unavailable; not inferred from listing update date')
    # Only inspect sale-price/status modules; seller feedback and recommendations
    # elsewhere on the page must not contaminate this transaction's status.
    price_nodes = [n for n in document.root.walk() if n.attrs.get('data-testid') == 'x-price-section']
    price_text = ' '.join(n.text() for n in price_nodes)
    sold_nodes = [n for n in document.root.walk() if 'ux-layout-section--status' in n.attrs.get('class', '')]
    best_offer = bool(re.search(r'best offer accepted', price_text + ' ' + ' '.join(n.text() for n in sold_nodes), re.I))
    if not price_nodes:
        issues.append('primary price module unavailable')
    price = _money(offers.get('price'))
    # Verify price is also visible in the primary module, not just SEO markup.
    visible_amounts = {_money(v.replace(',', '')) for v in re.findall(r'\$\s*([\d,]+\.\d{2})', price_text)}
    if price is None or price not in visible_amounts:
        issues.append('structured price not corroborated by primary visible price')
    specifics = _specifics(_module(document, 'ABOUT_THIS_ITEM'))
    shipping_nodes = [n for n in document.root.walk() if 'ux-labels-values--shipping' in n.attrs.get('class', '').split()]
    return Listing(canonical, item_id, unescape(product.get('name', '')), price,
                   offers.get('priceCurrency'), sold_on, sold, best_offer, specifics,
                   ' '.join(n.text() for n in shipping_nodes), snapshot.provenance(), tuple(issues))


def discover_pricecharting(snapshot: Snapshot):
    if urlsplit(snapshot.final_url).hostname != 'www.pricecharting.com':
        raise RetrievalError('Discovery response is not PriceCharting')
    document = Document(snapshot.html)
    sections = [n for n in document.root.walk() if n.attrs.get('id') == 'completed-auctions-used' or
                (n.tag == 'div' and 'completed-auctions-used' in n.attrs.get('class', '').split()
                 and 'tab' not in n.attrs.get('class', '').split())]
    if len(sections) != 1:
        raise RetrievalError('Ungraded sold-listing section unavailable; page schema may have changed')
    urls = []
    for row in sections[0].walk():
        if row.tag != 'tr' or not row.attrs.get('id', '').startswith('ebay-'):
            continue
        for node in row.walk():
            if node.tag == 'a' and 'js-ebay-completed-sale' in node.attrs.get('class', '').split():
                canonical, _ = _canonical_item(unescape(node.attrs.get('href', '')))
                # Retain the source's public original-listing link option.
                query = parse_qs(urlsplit(unescape(node.attrs.get('href', ''))).query)
                original_link = canonical + ('?nordt=true&rt=nc' if query.get('nordt') == ['true'] else '')
                if original_link not in urls:
                    urls.append(original_link)
    if not urls:
        raise RetrievalError('No public ungraded eBay sold links found')
    return tuple(urls)


def normalized(value):
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode().lower()
    return ' '.join(re.findall(r'[a-z0-9]+', value))


def _number(value):
    match = re.fullmatch(r'\s*([A-Za-z]*)(\d+)\s*/\s*([A-Za-z]*)(\d+)\s*', value)
    return (match[1].upper(), int(match[2]), match[3].upper(), int(match[4])) if match else value.strip().upper()


def qualify(target: Card, listing: Listing, *, set_aliases=(), standard_edition=False):
    """Deterministic exact dimensions; records are explicitly seller-reported."""
    reasons = list(listing.parse_issues)
    values = {normalized(k): v for k, v in listing.specifics.items()}
    title = listing.title
    if re.search(r'\b(proxy|replica|reproduction|custom|metal|jumbo|oversized|lot|bundle|signed|autograph|error|misprint)\b', title, re.I):
        reasons.append('nonstandard, reproduction, signed or bundled card')
    # A grader-name field alone is not a numeric grade. eBay seller templates
    # may contain it alongside an explicit Ungraded condition or Graded=No.
    if (re.search(r'\b(PSA|BGS|CGC|SGC|TAG|ACE)\s*\d|\bgraded\b', title, re.I)
            or re.search(r'\d', values.get('grade', ''))
            or normalized(values.get('graded', '')) == 'yes'):
        reasons.append('graded card')
    if not listing.sold:
        reasons.append('no explicit completed-sale confirmation')
    if listing.best_offer:
        reasons.append('accepted offer amount requires independent confirmation')
    if listing.currency != 'USD':
        reasons.append('not a USD transaction; no FX conversion')
    if listing.item_price is None:
        reasons.append('item price unavailable')
    if listing.sold_on is None:
        reasons.append('explicit sale date unavailable')
    if normalized(values.get('game', '')) not in {'pokemon tcg', 'pokemon trading card game'} or target.game != 'pokemon':
        reasons.append('game mismatch or missing')
    allowed_sets = {normalized(v) for v in (target.set_name, *set_aliases)}
    if normalized(values.get('set', '')) not in allowed_sets:
        reasons.append('set mismatch or missing')
    if _number(values.get('card number', '')) != _number(target.number):
        reasons.append('collector number mismatch or missing')
    if normalized(values.get('language', '')) != normalized(target.language):
        reasons.append('language mismatch or missing')
    raw_finish = normalized(values.get('finish', ''))
    finishes = {'holo': 'holo', 'holofoil': 'holo', 'non holo': 'non-holo',
                'regular': 'non-holo', 'reverse holo': 'reverse holo', 'reverse holofoil': 'reverse holo'}
    finish = finishes.get(raw_finish)
    if re.search(r'\b(reverse|cracked ice|cosmos|stamped|prize pack|pokeball|masterball)\b', title, re.I):
        # Special variants require explicit detailed matching, not generic Holo.
        if 'reverse' in title.lower() and finish == 'reverse holo':
            pass
        else:
            finish = None
    if finish != target.finish:
        reasons.append('finish mismatch, special variant or missing')
    edition = normalized(values.get('edition', ''))
    # Vintage Unlimited must be explicitly stated; absence of a 1st-edition
    # marker is never treated as evidence of Unlimited.
    if target.edition == 'unlimited' and not edition:
        edition_text = values.get('features', '') + ' ' + title
        if re.search(r'\bunlimited\b', edition_text, re.I) and not re.search(
                r'\b(first edition|1st edition|shadowless)\b', edition_text, re.I):
            edition = 'unlimited'
    if not (edition == normalized(target.edition) or
            (target.edition == 'standard' and standard_edition and not edition
             and not re.search(r'\b(first edition|1st edition|shadowless|stamped|prize pack)\b', title, re.I))):
        reasons.append('edition unconfirmed; no vintage edition inference')
    raw_condition = (values.get('condition', '') + ' ' + values.get('condition ungraded', '')
                     + ' ' + values.get('card condition', ''))
    conditions = [('NM', r'near[ -]?mint|\bNM\b'), ('LP', r'light(?:ly)?[ -]?play(?:ed)?|\bLP\b'),
                  ('MP', r'moderat(?:e|ely)[ -]?play(?:ed)?|\bMP\b'), ('HP', r'heavil?y?[ -]?play(?:ed)?|\bHP\b'),
                  ('DMG', r'\bdamaged\b|\bDMG\b')]
    declared = {condition for condition, pattern in conditions if re.search(pattern, raw_condition, re.I)}
    # Title condition is corroborating evidence and can contradict item specifics.
    title_conditions = {condition for condition, pattern in conditions if re.search(pattern, title, re.I)}
    if len(declared) != 1 or declared != {target.condition} or (title_conditions and title_conditions != declared):
        reasons.append('condition missing, mismatched or contradictory')
    if reasons:
        return None, tuple(dict.fromkeys(reasons))
    observed = datetime.fromisoformat(listing.evidence['observed_at']).date()
    sale = Sale(target, listing.item_price, None, listing.sold_on, listing.url,
                source='ebay_public', transaction_id=listing.item_id,
                verified_by='parser:ebay_public_v1', verified_on=observed,
                verification_notes='Public listing reports sold at visible price. Exact fields matched against seller item specifics; physical condition, payment settlement and later refunds unverified. Shipping excluded.',
                permission_reference='personal research requested by user; no commercial license asserted',
                price_confirmed=True, condition_confirmed=True, verification_level='seller_reported')
    return sale, ()


def research_quote(target, urls, client, as_of, *, set_aliases=(), standard_edition=False,
                   minimum_sales=3, max_age_days=90, discovery=None):
    sales, observations = [], []
    for url in dict.fromkeys(urls):
        try:
            snapshot = client.get(url)
            listing = parse_ebay(snapshot)
            sale, reasons = qualify(target, listing, set_aliases=set_aliases, standard_edition=standard_edition)
            row = {**listing.evidence, 'url': listing.url, 'item_id': listing.item_id,
                   'title': listing.title, 'item_price': str(listing.item_price) if listing.item_price else None,
                   'currency': listing.currency, 'sold_on': str(listing.sold_on) if listing.sold_on else None,
                   'seller_specifics': listing.specifics, 'shipping_quote_context_only': listing.shipping_quote,
                   'rejections': list(reasons)}
            if sale:
                sales.append(sale)
            observations.append(row)
        except (RetrievalError, ValueError, TypeError, KeyError) as exc:
            observations.append({'url': url, 'retrieval_error': str(exc)})
    result = evaluate(target, sales, as_of, minimum_sales=minimum_sales,
                      max_age_days=max_age_days, allow_seller_reported=True)
    return {'scope': 'personal_research', 'price_basis': 'card_sale_price_only_excluding_shipping_and_tax',
            'discovery': discovery, 'valuation': result.to_dict(), 'observations': observations,
            'limitations': ['Seller-reported condition, not physical inspection',
                           'Public sold status does not establish payment settlement or later refunds',
                           'Discovery is incomplete; this is not a census of recent sales',
                           'Market accuracy and +/-10% target have not been independently validated']}


def reported_sales_estimates(snapshot, target, card_name, *, mapping_reviewed=False,
                             as_of, max_age_days=30, minimum_sales=3):
    """Secondary public transaction reports, kept separate by original marketplace.

    These are NOT verified direct transactions or PriceCharting's guide price.
    Product-page mapping is a reviewed configuration, never inferred from a slug.
    Publisher row IDs are not claimed to be original marketplace transaction IDs.
    """
    from urllib.parse import quote
    from .pricing import median_and_outliers
    if not mapping_reviewed:
        return {'status': 'product_page_mapping_requires_review', 'groups': {}}
    if minimum_sales < 3 or max_age_days < 0:
        raise ValueError('At least three reports and a nonnegative window required')
    document = Document(snapshot.html)
    sections = [n for n in document.root.walk() if n.tag == 'div'
                and 'completed-auctions-used' in n.attrs.get('class', '').split()
                and 'tab' not in n.attrs.get('class', '').split()]
    if len(sections) != 1:
        raise RetrievalError('Ungraded sale report section missing')
    groups = {'ebay': [], 'tcgplayer': []}
    rejected, seen = [], set()
    page_text = document.visible_text()
    # Context corroboration is essential because titles alone omit the set.
    headings = [n.text() for n in document.nodes('h1')]
    if not headings or normalized(card_name) not in normalized(headings[0]):
        raise RetrievalError('Reviewed product mapping conflicts with page heading')
    for row in sections[0].walk():
        row_id = row.attrs.get('id', '')
        if row.tag != 'tr' or not row_id.startswith(('ebay-', 'tcgplayer-')):
            continue
        marketplace = row_id.split('-', 1)[0]
        cells = [n for n in row.children if isinstance(n, Node) and n.tag == 'td']
        def cell(cls):
            return next((n for n in cells if cls in n.attrs.get('class', '').split()), None)
        date_cell, title_cell, amount_cell = cell('date'), cell('title'), cell('numeric')
        if date_cell is None or title_cell is None or amount_cell is None:
            rejected.append({'publisher_record_id': row_id, 'reason': 'missing report columns'})
            continue
        title = title_cell.text()
        # Detect multiple displayed amounts (offers/currency translations) and
        # refuse to choose one without proving its semantics.
        raw_amounts = re.findall(r'\$\s*([\d,]+\.\d{2})', amount_cell.text())
        reason = None
        try:
            sold_on = date.fromisoformat(date_cell.text())
        except ValueError:
            rejected.append({'publisher_record_id': row_id, 'reason': 'invalid report sale date'})
            continue
        if row_id in seen:
            reason = 'duplicate publisher record'
        elif not 0 <= (as_of - sold_on).days <= max_age_days:
            reason = 'outside report window'
        elif len(raw_amounts) != 1 or _money(raw_amounts[0].replace(',', '')) is None:
            reason = 'ambiguous or missing reported amount'
        elif normalized(card_name) not in normalized(title):
            reason = 'card name mismatch'
        elif target.number.lower() not in title.lower():
            reason = 'full collector number missing'
        elif re.search(r'\b(proxy|replica|custom|metal|lot|bundle|graded|PSA|CGC|TAG|BGS|SGC|error|misprint|signed)\b', title, re.I):
            reason = 'nonstandard or graded report'
        else:
            condition_patterns = {'NM': r'near[ -]?mint|\bNM\b', 'LP': r'light(?:ly)?[ -]?played|\bLP\b',
                                  'MP': r'moderately[ -]?played|\bMP\b', 'HP': r'heavily[ -]?played|\bHP\b',
                                  'DMG': r'\bdamaged\b|\bDMG\b'}
            labels = {key for key, pattern in condition_patterns.items() if re.search(pattern, title, re.I)}
            if labels != {target.condition}:
                reason = 'condition missing, contradictory or mismatched'
            elif not re.search(r'\b(?:English|Eng|EN)\b', title, re.I) or target.language != 'english':
                reason = 'language missing or mismatched'
            elif re.search(r'\b(first edition|1st edition|shadowless|stamped|prize pack|reverse|cracked ice|cosmos|pokeball|masterball)\b', title, re.I):
                reason = 'edition or finish requires separate product mapping'
            elif target.edition != 'standard' or target.finish != 'holo':
                reason = 'reported mapping currently supports standard holo printings only'
        if reason:
            rejected.append({'publisher_record_id': row_id, 'reason': reason})
            continue
        seen.add(row_id)
        # Store extracted facts, not copied listing prose or a fabricated sale ID.
        groups[marketplace].append({
            'publisher_record_id': row_id, 'reported_marketplace': marketplace,
            'sold_on': sold_on.isoformat(), 'item_price': raw_amounts[0].replace(',', ''),
            'currency': 'USD', 'condition': target.condition, 'language': target.language,
            'printing_mapping': list(target.printing),
            'source_url': snapshot.final_url + '#' + quote(row_id, safe=''),
            'row_sha256': hashlib.sha256(row.text().encode()).hexdigest(),
            'verification_level': 'secondary_publisher_report',
        })
    summaries = {}
    for source, records in groups.items():
        value, flagged = None, ()
        if len(records) >= minimum_sales:
            value, flagged = median_and_outliers([Decimal(r['item_price']) for r in records], Decimal('3'))
            if flagged:
                value = None
        summaries[source] = {'status': 'secondary_research_estimate' if value is not None else
                             ('review_required' if flagged else 'insufficient_evidence'),
                             'value': str(value) if value is not None else None,
                             'count': len(records), 'records': records,
                             'outlier_publisher_record_ids': [records[i]['publisher_record_id'] for i in flagged]}
    return {'status': 'secondary_reports_only', 'as_of': str(as_of),
            'max_age_days': max_age_days, 'minimum_sales': minimum_sales,
            'price_basis': 'publisher_reported_card_sale_price_excluding_shipping_and_tax',
            'source': snapshot.provenance(), 'groups': summaries, 'rejected_reports': rejected,
            'limitations': ['Not independently verified at originating marketplace',
                           'Publisher row IDs are not proof of original transaction uniqueness',
                           'Product mapping supplies set, edition and finish; publisher mapping errors remain possible',
                           'Publisher USD amounts may be conversions; original currency is not established',
                           'No independent accuracy validation; do not pool this with the same direct eBay sales']}
