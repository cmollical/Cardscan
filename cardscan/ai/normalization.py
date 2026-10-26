"""Lossless, reviewed representation changes. Never creates source observations."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re

from .models import digest
from .provider import canonical_url

VERSION = 'lossless-normalization-v1'
CONDITION = {'nm':'NM','near mint':'NM','lp':'LP','lightly played':'LP','mp':'MP',
             'moderately played':'MP','hp':'HP','heavily played':'HP','dmg':'DMG','damaged':'DMG'}
ALIASES = {
    'game':{'pokemon':'pokemon','pokémon':'pokemon','pokemon tcg':'pokemon','pokémon tcg':'pokemon'},
    'condition':CONDITION,
    'finish':{'holo':'holo','holofoil':'holo','holo rare':'holo','non-holo':'non-holo',
              'non holo':'non-holo','normal':'non-holo','reverse holo':'reverse holo','reverse holofoil':'reverse holo'},
    'edition':{'1st edition':'first edition','first edition':'first edition','unlimited':'unlimited','standard':'standard',
               'shadowless':'shadowless'},
    'language':{'en':'english','english':'english','ja':'japanese','japanese':'japanese',
                'fr':'french','french':'french','de':'german','german':'german',
                'es':'spanish','spanish':'spanish','simplified chinese':'simplified chinese',
                'traditional chinese':'traditional chinese'},
}


@dataclass(frozen=True)
class MoneyNormalization:
    raw_value: object
    raw_currency: str | None
    amount: str | None
    currency: str | None
    transformations: tuple[str, ...]
    errors: tuple[str, ...]


def normalize_money(raw, currency=None):
    """USD only; no float, exponent, locale guessing, FX, shipping or tax inference.

    A bare dollar sign needs a separate USD currency field. An explicit USD prefix
    can establish currency when the field is missing. Grouped numbers require a
    dot-decimal suffix so comma-only locale notation remains ambiguous/rejected.
    """
    transforms=[];errors=[]
    code=currency.strip().upper() if isinstance(currency,str) else None
    if currency is not None and code!='USD':errors.append('Unsupported or invalid currency')
    if raw is None:return MoneyNormalization(raw,currency,None,code,(),tuple(errors))
    if type(raw) is int:text=str(raw);transforms.append('integer_to_decimal_text')
    elif isinstance(raw,str):text=raw.strip()
    else:return MoneyNormalization(raw,currency,None,code,(),('Unsupported monetary type; floats and booleans refused',))
    original=text
    if text.startswith('USD '):
        if code not in (None,'USD'):errors.append('Currency prefix contradicts explicit currency')
        code='USD';text=text[4:].strip();transforms.append('explicit_USD_prefix')
    elif text.startswith('$'):
        text=text[1:];transforms.append('dollar_symbol_removed_with_explicit_USD')
        if code!='USD':errors.append('Ambiguous dollar currency; explicit USD required')
    if code is None:errors.append('Missing explicit currency')
    plain=r'(?:0|[0-9]+)(?:\.[0-9]+)?'
    grouped=r'[0-9]{1,3}(?:,[0-9]{3})+\.[0-9]+'
    if not re.fullmatch(plain+'|'+grouped,text):errors.append('Ambiguous or invalid monetary format')
    if errors:return MoneyNormalization(raw,currency,None,code,tuple(transforms),tuple(dict.fromkeys(errors)))
    if ',' in text:text=text.replace(',','');transforms.append('validated_thousands_separators_removed')
    try:
        amount=Decimal(text)
        if not amount.is_finite() or amount<=0:raise ValueError('Positive finite amount required')
    except (InvalidOperation,ValueError):
        return MoneyNormalization(raw,currency,None,code,tuple(transforms),('Positive finite amount required',))
    canonical=format(amount,'f')
    if isinstance(raw,str) and raw!=canonical and not transforms:transforms.append('decimal_text_whitespace_or_leading_zeros')
    if isinstance(currency,str) and currency!=code:transforms.append('currency_code_case')
    return MoneyNormalization(raw,currency,canonical,code,tuple(transforms),())


class SetAliasRegistry:
    def __init__(self,document=None):
        self.document=document or json.loads(Path(__file__).with_name('set_aliases.json').read_text())
        self.version=self.document['version']

    def resolve(self,raw,game=None,language=None):
        matches=[e for e in self.document['entries'] if raw.strip().casefold() in {a.casefold() for a in e['aliases']}
                 and (game is None or e['game']==game) and (language is None or e['language']==language)]
        keys={(m['catalog_source'],m['canonical_set_name']) for m in matches}
        if len(keys)!=1:return None,None
        return matches[0]['canonical_set_name'],matches[0]['catalog_source']


def normalize_attribute(field,raw,*,registry=None,game=None,language=None):
    """Returns canonical value, explicit mapping evidence and an error if unknown."""
    if raw is None:return None,None,None
    if field=='graded':
        return (raw,'explicit_boolean',None) if type(raw) is bool else (None,None,'Invalid grading status')
    if not isinstance(raw,str) or not raw.strip():return None,None,'Unknown '+field+' label'
    token=raw.strip().casefold()
    if field=='name':return token,'case_and_outer_whitespace_only',None
    if field=='number':
        m=re.fullmatch(r'([a-zA-Z]*)([0-9]+)/([a-zA-Z]*)([0-9]+)',raw.strip())
        if not m:return raw.strip(),None,'Collector denominator missing or number unrecognized'
        return f'{m[1].upper()}{int(m[2])}/{m[3].upper()}{int(m[4])}','zero_padding_only',None
    if field=='set_name':
        canonical,source=(registry or SetAliasRegistry()).resolve(raw,game,language)
        return canonical,source,None if canonical else 'Unresolved or ambiguous catalog set label'
    if field=='condition' and token in {'raw','ungraded','generic ungraded','unknown'}:
        return None,'non_specific_condition_preserved',None
    canonical=ALIASES.get(field,{}).get(token)
    return canonical,'reviewed_literal_alias_v1' if canonical is not None else None,None if canonical is not None else 'Unknown '+field+' label'


def normalize_identity(identity,registry):
    normalized={};changes=[];errors=[]
    # Resolve game/language before set alias lookup; never obtain language from set.
    order=['game','language','name','number','edition','finish','condition','graded','set_name']
    for field in order:
        raw=identity.get(field)
        value,rule,error=normalize_attribute(field,raw,registry=registry,game=normalized.get('game'),language=normalized.get('language'))
        normalized[field]=value
        if raw!=value or error:
            changes.append({'field':field,'raw':raw,'canonical':value,'rule':rule,'error':error})
        if error:errors.append(field+': '+error)
    return normalized,changes,errors


def normalize_proposal(raw,response_id,*,registry=None,transaction_records=None):
    """Raw proposal stays untouched. Transaction records are external facts only.

    transaction_records is an optional row-position map supplied by a trusted source
    verifier, never by AI IDs or by normalization. URL item IDs remain listing IDs.
    """
    if not isinstance(response_id,str) or not response_id:raise ValueError('Original research response ID required')
    registry=registry or SetAliasRegistry();copy=deepcopy(raw);rows=[];all_changes=[];proposal_money={}
    for field in ('estimated_market_value','estimated_low','estimated_high'):
        value=normalize_money(raw.get(field),raw.get('currency'))
        proposal_money[field]=asdict(value);copy[field]=value.amount
        if value.transformations:all_changes.append({'field':field,**asdict(value)})
    for index,source in enumerate(raw.get('sources',[])):
        original=deepcopy(source)
        internal_id='row_'+digest({'response_id':response_id,'position':index,'raw_source':original})[:24]
        try:page=canonical_url(source['url']);page_error=None
        except (ValueError,TypeError):page=None;page_error='Invalid source URL'
        identity,changes,issues=normalize_identity(source['observed_identity'],registry)
        price=normalize_money(source['reported_price'],source.get('currency'))
        normalized=deepcopy(source);normalized.update(id=internal_id,observed_identity=identity,reported_price=price.amount,currency=price.currency)
        label,label_rule,label_error=normalize_attribute('condition',source.get('condition_label'),registry=registry)
        if source.get('condition_label')!=label:changes.append({'field':'condition_label','raw':source.get('condition_label'),'canonical':label,'rule':label_rule,'error':label_error})
        # The normalized label is separate; original text remains in raw_source.
        normalized['condition_label']=label
        transaction=(transaction_records or {}).get(index)
        if transaction is not None and (not transaction.get('source') or not transaction.get('id') or not transaction.get('provenance')):
            raise ValueError('Known transaction needs genuine ID, source and provenance')
        listing=None
        if page:
            m=re.fullmatch(r'https://www\.ebay\.com/itm/([0-9]{9,15})',page)
            if m:listing=m[1]
        rows.append({'internal_row_id':internal_id,'position':index,'research_response_id':response_id,
                     'original_reported_id':source['id'],'canonical_page_url':page,
                     'canonical_page_id':None if page is None else 'page_'+sha256(page.encode()).hexdigest()[:24],
                     'marketplace_listing_id':listing,'marketplace_transaction':deepcopy(transaction),
                     'raw_source':original,'normalized_source':normalized,'raw_source_sha256':digest(original),
                     'identity_transformations':changes,'monetary_normalization':asdict(price),
                     'normalization_errors':issues+list(price.errors)+([page_error] if page_error else []),
                     'condition_label_error':label_error})
        copy['sources'][index]=normalized
    support=[];unresolved=[];ambiguous=[]
    for original_id in raw.get('supporting_source_ids',[]):
        matches=[r['internal_row_id'] for r in rows if r['original_reported_id']==original_id]
        if not matches:unresolved.append(original_id)
        if len(matches)>1:ambiguous.append({'original_id':original_id,'internal_rows':matches})
        support.extend(matches)
    copy['supporting_source_ids']=list(dict.fromkeys(support))
    return {'normalization_version':VERSION,'set_alias_version':registry.version,
            'set_alias_registry_sha256':digest(registry.document),
            'research_response_id':response_id,'raw_proposal_sha256':digest(raw),'normalized_proposal':copy,
            'proposal_money':proposal_money,'proposal_transformations':all_changes,'rows':rows,
            'unresolved_support_ids':unresolved,'ambiguous_support_ids':ambiguous,
            'warning':'Row IDs identify extracted claims, not independent transactions or verified source facts.'}
