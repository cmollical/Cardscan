"""Source-specific extraction. No requested-card fields are copied into evidence."""
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
import re

from .models import FieldEvidence, SourcePermission
from .transport import canonical_source_url


class ReferenceSourceAdapter(Protocol):
    source: str
    method: str
    permission: SourcePermission
    def accepts(self, url: str) -> bool: ...
    def extract(self, document, variant: str) -> dict[str, FieldEvidence]: ...


@dataclass(frozen=True)
class DisabledSourceAdapter:
    """Return an auditable policy refusal before any marketplace retrieval."""
    source: str
    host: str
    permission: SourcePermission
    method: str = 'disabled_pending_permission_or_credentials'

    def accepts(self, url):
        return urlsplit(canonical_source_url(url)).hostname == self.host

    def extract(self, document, variant):
        raise ValueError('Disabled source cannot extract evidence')


def restricted_sources():
    return [DisabledSourceAdapter('tcgplayer','www.tcgplayer.com',SourcePermission(
                'tcgplayer',False,False,False,
                ('https://help.tcgplayer.com/hc/en-us/articles/360061115874-TCGplayer-API-Terms-Conditions',),
                '2026-10-25','No approved API access; automated website collection not permitted by reviewed terms.')),
            DisabledSourceAdapter('pricecharting','www.pricecharting.com',SourcePermission(
                'pricecharting',False,False,False,('https://www.pricecharting.com/api-documentation',),
                '2026-10-25','No API subscription or applicable commercial permission established; no raw-condition benchmark documented.')),
            DisabledSourceAdapter('justtcg','api.justtcg.com',SourcePermission(
                'justtcg',False,False,False,('https://justtcg.com/terms','https://justtcg.com/docs/quickstart'),
                '2026-10-25','No JustTCG key/subscription configured; free tier excludes commercial use.'))]


class TCGdexAdapter:
    source = 'tcgdex'
    method = 'tcgdex_card_json_v1'
    permission = SourcePermission(
        source, True, True, False,
        ('https://tcgdex.dev/faq', 'https://tcgdex.dev/markets-prices'),
        '2026-10-25',
        'Documented public API for limited research; retain only minimal extracted facts. '
        'This is not an upstream marketplace commercial license; commercial reuse unresolved.')

    def accepts(self, url):
        p = urlsplit(canonical_source_url(url))
        return p.hostname == 'api.tcgdex.net' and bool(re.fullmatch(r'/v2/(?:en|ja|fr|de|es|it|pt)/cards/[A-Za-z0-9.-]+', p.path))

    def extract(self, document, variant):
        if variant not in {'normal', 'reverse', 'holofoil', 'holo'}:
            raise ValueError('Unsupported explicit source pricing variant')
        d = document.data
        fields = {}
        def field(key, path, *, basis='structured_metadata', value=None):
            current = d
            if value is None:
                try:
                    for part in path.split('/'):
                        if part: current = current[part]
                    value = current
                except (KeyError, TypeError): value = None
            fields[key] = FieldEvidence(value, basis if value is not None else 'missing',
                                        '/' + path, self.method, document.url, document.sha256)
        for key,path in [('source_product_id','id'),('name','name'),('set_name','set/name'),
                         ('local_number','localId'),('set_official_count','set/cardCount/official'),
                         ('first_edition_flag','variants/firstEdition')]:
            field(key,path)
        # The joined collector number is a lossless representation of two source
        # fields; its locator records both components for review.
        n, total = fields['local_number'].value, fields['set_official_count'].value
        if isinstance(n,str) and type(total) is int and total > 0:
            field('number','localId + /set/cardCount/official',value=f'{n}/{total}')
        else: field('number','number')
        for key,path in [('price',f'pricing/tcgplayer/{variant}/marketPrice'),
                         ('currency','pricing/tcgplayer/unit'),('published_at','pricing/tcgplayer/updated'),
                         ('marketplace_product_id',f'pricing/tcgplayer/{variant}/productId')]:
            field(key,path)
        pricing = d.get('pricing', {}).get('tcgplayer', {})
        if not isinstance(pricing,dict): raise ValueError('Malformed source pricing')
        if variant in pricing and isinstance(pricing[variant],dict):
            field('price_type',f'pricing/tcgplayer/{variant}/marketPrice',value='published_market_reference')
            field('finish',f'pricing/tcgplayer/{variant}',value={'normal':'non-holo','reverse':'reverse holo','holofoil':'holo','holo':'holo'}[variant])
        # A locale supplies metadata language, not proof of the priced item language.
        field('metadata_language','endpoint locale',value=urlsplit(document.url).path.split('/')[2])
        for key in ('game','language','edition','graded','condition','price_basis'):
            field(key,key)
        # Current documented TCGdex price payload has no condition field. If one
        # appears unexpectedly, do not silently give it new semantic authority.
        fields['condition'] = FieldEvidence(None,'missing','/pricing/tcgplayer (no condition scope in supported schema)',
                                             self.method,document.url,document.sha256)
        # Do not infer raw, standard edition, currency basis, or price condition
        # from card rarity, endpoint locale, requested identity or absence of a slab.
        return fields
