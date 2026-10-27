"""Atomic set-level exact-ID import. Generic references never become SKU prices."""
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
import json
import re

from cardscan.structured_prices import CONDITIONS, LANGUAGES, VARIANTS, number_key, price, json_text
from .database import utc


def canonical_number(raw):
    match=re.fullmatch(r'([A-Za-z]*)(\d+)/([A-Za-z]*)(\d+)',raw or '')
    return f'{match[1].upper()}{int(match[2])}/{match[3].upper()}{int(match[4])}' if match else raw or None


def full_number(raw):
    return bool(re.fullmatch(r'[A-Za-z]*\d+/[A-Za-z]*\d+',raw or ''))


def decode(payload):
    def unique(pairs):
        d = {}
        for k,v in pairs:
            if k in d: raise ValueError('Duplicate JSON key: ' + k)
            d[k]=v
        return d
    return json.loads(payload, parse_float=Decimal, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid number')))


class Importer:
    def __init__(self, db):
        self.db = db

    def import_set(self, provider, category, source_set, documents, *, aliases=(), game='pokemon', set_metadata=None, snapshot_date=None, captured_at=None, capture_kind='original_import'):
        """documents maps products/prices or cards/skus to payload+source metadata.

        Atomic per provider/set. Missing SKU prices are explicit observations;
        disappeared SKU rows become inactive so old quotes are not served as live.
        """
        if provider not in {'tcgcsv','tcgtracking'} or game != 'pokemon' or int(category) not in (3,85):
            raise ValueError('Only reviewed Pokemon categories/providers enabled')
        suffixes = ('products','prices') if provider=='tcgcsv' else ('cards','skus')
        if set(documents) != set(suffixes):raise ValueError('Complete provider/set pair required')
        parsed={k:decode(documents[k]['payload']) for k in suffixes}
        for k in suffixes:
            expected=(f'https://tcgcsv.com/tcgplayer/{category}/{source_set}/{k}' if provider=='tcgcsv'
                      else f'https://openapi.tcgtracking.com/v1/{category}/sets/{source_set}/{k}')
            if documents[k]['url'] != expected:raise ValueError('Wrong source document/set/category')
        catalog, prices = (parsed[k] for k in suffixes)
        if provider=='tcgcsv' and (catalog.get('success') is not True or prices.get('success') is not True):
            raise ValueError('Unsuccessful source response')
        if provider=='tcgtracking' and (catalog.get('set_id') != int(source_set) or prices.get('set_id') != int(source_set)):
            raise ValueError('Set mismatch')
        source_name=catalog.get('set_name') or (set_metadata or {}).get('name')
        if not source_name:raise ValueError('Observed set metadata required')
        stamp=max(utc(documents[k]['retrieved_at']) for k in suffixes)
        captured_at=utc(captured_at or stamp)
        snapshot_date=snapshot_date or captured_at[:10]
        from datetime import date
        if date.fromisoformat(snapshot_date)>datetime.fromisoformat(captured_at).date():raise ValueError('Future snapshot date')
        with self.db.transaction() as c:
            docids={k:self.db.document(c,**{key:v for key,v in documents[k].items() if key in
                    {'url','payload','retrieved_at','original_hash','kind'}}) for k in suffixes}
            c.execute('INSERT INTO games(name) VALUES(?) ON CONFLICT DO NOTHING',(game,))
            gid=c.execute('SELECT id FROM games WHERE name=?',(game,)).fetchone()[0]
            c.execute('INSERT INTO provider_categories VALUES(?,?,?,?) ON CONFLICT DO NOTHING',
                      (provider,str(category),gid,'Pokemon Japan' if int(category)==85 else 'Pokemon'))
            # Both adapters document that set/group and product IDs are TCGplayer IDs.
            existing=c.execute('SELECT DISTINCT set_id FROM set_mappings WHERE category_id=? AND source_set_id=?',
                               (str(category),str(source_set))).fetchall()
            if len(existing)>1:raise ValueError('Ambiguous provider set mapping')
            if existing:sid=existing[0][0]
            else:
                sid=c.execute('INSERT INTO sets(game_id,name,release_date,last_catalog_sync) VALUES(?,?,?,?)',
                              (gid,source_name,(set_metadata or {}).get('publishedOn') or catalog.get('set_released'),stamp)).lastrowid
            previous=c.execute('SELECT last_success_at FROM sync_state WHERE provider=? AND category_id=? AND source_set_id=?',(provider,str(category),str(source_set))).fetchone()
            if previous and previous[0] and previous[0]>captured_at:
                return {'provider':provider,'set_id':sid,'status':'older_snapshot_skipped','products':0}
            c.execute('UPDATE sets SET last_catalog_sync=MAX(COALESCE(last_catalog_sync,?),?) WHERE id=?',(captured_at,captured_at,sid))
            c.execute('INSERT INTO set_mappings VALUES(?,?,?,?) ON CONFLICT DO NOTHING',(provider,str(category),str(source_set),sid))
            metadata_aliases = [
                value
                for value in ((set_metadata or {}).get('abbreviation'),)
                if isinstance(value, str) and value.strip()
            ]
            for alias in {source_name.casefold(),*(a.casefold() for a in aliases),*(a.casefold() for a in metadata_aliases)}:
                c.execute('INSERT INTO set_aliases VALUES(?,?,?) ON CONFLICT DO NOTHING',(sid,alias,'explicit reviewed source-ID/set-alias mapping'))
            rows=catalog.get('results') if provider=='tcgcsv' else catalog.get('products')
            if not isinstance(rows,list):raise ValueError('Invalid catalog export')
            if not rows and c.execute('SELECT COUNT(*) FROM products WHERE set_id=?',(sid,)).fetchone()[0]:
                raise ValueError('Unexpected empty catalog export quarantined; prior data preserved')
            products={};seen=set()
            for i,p in enumerate(rows):
                source_id=str(p.get('productId') if provider=='tcgcsv' else p.get('id'))
                if not source_id.isdigit() or source_id in seen:raise ValueError('Invalid/duplicate product ID')
                seen.add(source_id)
                if provider=='tcgcsv' and (p.get('groupId')!=int(source_set) or p.get('categoryId')!=int(category)):
                    raise ValueError('Product category/group mismatch')
                name=p.get('name')
                if not isinstance(name,str) or not name.strip():raise ValueError('Product name missing')
                nums=[x.get('value') for x in p.get('extendedData',[]) if x.get('name')=='Number']
                raw_number=(nums[0] if len(nums)==1 else None) if provider=='tcgcsv' else p.get('number')
                old=c.execute('SELECT * FROM products WHERE tcgplayer_product_id=?',(source_id,)).fetchone()
                number=canonical_number(raw_number)
                if old and (old['set_id']!=sid or (number and old['collector_number'] and number!=old['collector_number'])):
                    raise ValueError('Conflicting exact product-to-set/number mapping; review required')
                if old:
                    pid=old['id']
                    c.execute('UPDATE products SET name=?,collector_number=COALESCE(?,collector_number),raw_collector_number=COALESCE(?,raw_collector_number) WHERE id=?',(name,number,raw_number,pid))
                else:
                    pid=c.execute('INSERT INTO products(game_id,set_id,name,collector_number,raw_collector_number,tcgplayer_product_id,metadata_json) VALUES(?,?,?,?,?,?,?)',
                                  (gid,sid,name,number,raw_number,source_id,json_text({'rarity':p.get('rarity'),'language_scope':'unknown'}))).lastrowid
                products[source_id]=(pid,p,i)
                c.execute('INSERT INTO product_sources VALUES(?,?,?,?,?) ON CONFLICT(provider,source_product_id) DO UPDATE SET document_id=excluded.document_id,locator=excluded.locator',
                          (provider,source_id,pid,docids[suffixes[0]],f'/{"results" if provider=="tcgcsv" else "products"}/{i}'))
            if provider=='tcgtracking':
                sku_products=prices.get('products')
                if not isinstance(sku_products,dict):raise ValueError('SKU product map missing')
                missing=set(sku_products)-set(products)
                if missing:
                    c.execute('INSERT INTO quality_issues(provider,source_set_id,document_id,reason,identifiers_json) VALUES(?,?,?,?,?) ON CONFLICT DO NOTHING',
                              (provider,str(source_set),docids['skus'],'SKU export products absent from cards-only catalog; not imported',json_text(sorted(missing))))
                if all(d.get('kind','original')=='original' for d in documents.values()):
                    c.execute('UPDATE skus SET active=0 WHERE provider=? AND product_id IN (SELECT id FROM products WHERE set_id=?)',(provider,sid))
                for source_id,sku_rows in sku_products.items():
                    if source_id not in products:continue
                    pid,p,i=products[source_id]
                    if not isinstance(sku_rows,dict):raise ValueError('Invalid SKU rows')
                    for sku,row in sku_rows.items():
                        if not str(sku).isdigit() or not isinstance(row,dict):raise ValueError('Invalid SKU')
                        condition=row.get('cnd') if row.get('cnd') in CONDITIONS else None
                        language=LANGUAGES.get(row.get('lng'))
                        finish,edition=VARIANTS.get(row.get('var'),(None,None))
                        edition_basis='variant_field' if edition else 'missing'
                        if row.get('var') in ('1st Edition','Unlimited'):
                            edition={'1st Edition':'first edition','Unlimited':'unlimited'}[row['var']]
                            edition_basis='explicit_variant_edition_label_v2'
                        if edition is None and 'This version from the Unlimited print run' in p.get('ext_data',{}).get('TCGplayer Tip',''):
                            edition='unlimited';edition_basis='explicit_product_print_run_sentence'
                        old=c.execute('SELECT * FROM skus WHERE provider=? AND provider_sku_id=?',(provider,str(sku))).fetchone()
                        identity=(pid,condition,language,edition,finish)
                        if old and tuple(old[k] for k in ['product_id','condition','language','edition','finish'])!=identity:
                            raise ValueError('Existing SKU identity changed; review required')
                        completeness={k:v is not None for k,v in dict(condition=condition,language=language,edition=edition,finish=finish,number=True if full_number(p.get('number')) else None,graded=False).items()}
                        provenance={'condition':'/cnd','language':'/lng','finish':'/var','edition':edition_basis,
                                    'graded':'raw reference scope from existing TCGTracking adapter contract; not an observed physical card grade'}
                        c.execute('''INSERT INTO skus(product_id,provider,provider_sku_id,condition,language,edition,finish,graded,raw_variant_json,completeness_json,provenance_json)
                                     VALUES(?,?,?,?,?,?,?,0,?,?,?) ON CONFLICT(provider,provider_sku_id) DO UPDATE SET active=1,raw_variant_json=excluded.raw_variant_json''',
                                  (pid,provider,str(sku),condition,language,edition,finish,json_text(row),json_text(completeness),json_text(provenance)))
                        sku_id=c.execute('SELECT id FROM skus WHERE provider=? AND provider_sku_id=?',(provider,str(sku))).fetchone()[0]
                        warnings=[]
                        if any(x.get('lng')==row.get('lng') and x.get('var')==row.get('var') and x.get('mkt') is not None
                               and row.get('mkt') is not None and x.get('cnd')=='NM' and condition!='NM'
                               and Decimal(str(x['mkt']))<Decimal(str(row['mkt'])) for x in sku_rows.values()):
                            warnings.append('condition_price_inversion')
                        if condition=='NM' and any(x.get('lng')==row.get('lng') and x.get('var')==row.get('var')
                            and x.get('cnd') in CONDITIONS-{'NM'} and x.get('mkt') is not None and row.get('mkt') is not None
                            and Decimal(str(x['mkt']))>Decimal(str(row['mkt'])) for x in sku_rows.values()):warnings.append('condition_price_inversion')
                        self._observation(c,pid,sku_id,provider,row.get('mkt'),prices.get('updated'),documents['skus'],docids['skus'],
                                          f'/products/{source_id}/{sku}',row,warnings,snapshot_date,captured_at,capture_kind)
            else:
                seen_prices=set()
                for i,row in enumerate(prices.get('results',[])):
                    source_id=str(row.get('productId'));key=(source_id,row.get('subTypeName'))
                    if key in seen_prices:raise ValueError('Duplicate product subtype')
                    seen_prices.add(key)
                    if source_id not in products:raise ValueError('Orphan product price')
                    self._observation(c,products[source_id][0],None,provider,row.get('marketPrice'),None,documents['prices'],docids['prices'],
                                      f'/results/{i}',row,['generic_condition_scope'],snapshot_date,captured_at,capture_kind)
            marker=':'.join(documents[k].get('original_hash') or sha256(documents[k]['payload']).hexdigest() for k in suffixes)
            c.execute('''INSERT INTO sync_state(provider,category_id,source_set_id,last_attempt_at,last_success_at,source_marker,status)
                         VALUES(?,?,?,?,?,?,'success') ON CONFLICT(provider,category_id,source_set_id) DO UPDATE SET
                         last_success_at=excluded.last_success_at,source_marker=excluded.source_marker,status='success',errors_json='[]',retry_after=NULL''',
                      (provider,str(category),str(source_set),captured_at,captured_at,marker))
            return {'products':len(products),'provider':provider,'set_id':sid}

    def _observation(self,c,pid,sku,provider,amount,updated,document,docid,locator,row,warnings,snapshot_date,captured_at,capture_kind):
        if row.get('currency') not in (None,'USD') or row.get('unit') not in (None,'USD'):
            raise ValueError('Currency contradicts reviewed USD export semantics')
        amount=price(amount)
        if updated is not None:updated=utc(updated)
        retrieved=utc(document['retrieved_at'])
        if updated and updated>retrieved:raise ValueError('Future source timestamp')
        missing=['shipping_exclusion','tax_exclusion','individual_price_age','upstream_verification']
        if not updated:missing.append('source_update_timestamp')
        if amount is None:missing.append('market_price')
        evidence={'source_row':row,'currency_basis':'TCGplayer USD convention; currency absent in export',
                  'update_scope':'set_export' if updated else 'unknown','independently_authenticated':False}
        fp=sha256(json_text([provider,sku,pid,document.get('original_hash') or sha256(document['payload']).hexdigest(),row.get('subTypeName') if sku is None else None,snapshot_date]).encode()).hexdigest()
        c.execute('''INSERT INTO observations(product_id,sku_id,provider,market_price,currency,price_type,source_updated_at,retrieved_at,
                     source_url,document_id,locator,evidence_json,warnings_json,missing_json,fingerprint,snapshot_date,captured_at,capture_kind,subtype) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fingerprint) DO NOTHING''',
                  (pid,sku,provider,amount,'USD','sku_market_reference' if sku else 'generic_market_reference',updated,retrieved,
                   document['url'],docid,locator,json_text(evidence),json_text(warnings),json_text(missing),fp,snapshot_date,captured_at,capture_kind,row.get('subTypeName') if sku is None else None))
