"""Offline storage/API/sync regressions. Saved observations are not accuracy ground truth."""
from copy import deepcopy
from datetime import datetime,timedelta
from decimal import Decimal
from email.message import Message
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError,URLError

from fastapi.testclient import TestClient
from cardscan.local_pricing.database import Database,utc
from cardscan.local_pricing.cli import seed,FIXTURE
from cardscan.local_pricing.importers import Importer
from cardscan.local_pricing.lookup import Lookup
from cardscan.local_pricing.api import create_app
from cardscan.local_pricing.sync import DailyClient,synchronize,sync_lock
from cardscan.local_pricing.backfill import import_entry,plan,run,extract_members,download_archive
from cardscan.structured_prices import json_text

NOW='2026-10-26T18:00:00Z'
EXPECTED={'7335315':('NM','english','0.32'),'7436747':('NM','english','294.42'),
          '2999653':('LP','english','527.7'),'2995236':('LP','english','458.05'),
          '8115821':('NM','japanese','388.35')}
BUNDLE=json.loads(FIXTURE.read_text())


def entry(index=1):
    e=deepcopy(BUNDLE['imports'][index]);docs={}
    for k,d in e.pop('documents').items():
        docs[k]={key:d[key] for key in ['url','retrieved_at','original_hash','kind']}
        docs[k]['payload']=json_text(d['data']).encode()
    return e,docs


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Database(Path(self.tmp.name)/'pricing.sqlite');self.db.migrate();seed(self.db)
        self.lookup=Lookup(self.db)

    def counts(self):
        with self.db.connect(readonly=True) as c:return {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['products','skus','observations','documents']}

    def test_migrations_idempotent_and_upgrade_from_version_one(self):
        self.db.migrate();self.assertEqual(self.db.health()['schema_version'],5)
        old=Database(Path(self.tmp.name)/'old.sqlite')
        with old.connect() as c:c.executescript(Path('cardscan/local_pricing/schema.sql').read_text())
        old.migrate();self.assertEqual(old.health()['schema_version'],5)
        newer=Database(Path(self.tmp.name)/'newer.sqlite')
        with newer.connect() as c:c.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):newer.migrate()

    def test_actual_five_skus_prices_condition_language_and_provenance(self):
        for sku,(condition,language,amount) in EXPECTED.items():
            r=self.lookup.lookup_sku('tcgtracking',sku,now=NOW)
            self.assertEqual(r['status'],'exact_match');self.assertEqual(r['market_price'],amount)
            self.assertEqual(r['condition'],condition);self.assertEqual(r['language'],language)
            self.assertEqual(r['price_type'],'sku_market_reference');self.assertFalse(r['approved_inventory_price'])
            self.assertIsNotNone(r['source_updated_at']);self.assertIsNotNone(r['retrieved_at'])
            self.assertTrue(r['evidence_document_id'])
        with self.db.connect(readonly=True) as c:
            d=c.execute('SELECT * FROM documents LIMIT 1').fetchone()
            self.assertEqual(d['payload_kind'],'excerpt');self.assertEqual(sha256(d['payload']).hexdigest(),d['content_hash'])
            self.assertNotEqual(d['content_hash'],d['original_source_hash'])

    def test_import_idempotent_and_exact_identifiers_distinct(self):
        before=self.counts();seed(self.db);self.assertEqual(before,self.counts())
        r=self.lookup.lookup_sku('tcgtracking','2999653',now=NOW)
        self.assertNotEqual(str(r['sku_id']),r['provider_sku_id'])
        self.assertEqual(r['tcgplayer_product_id'],'42382')

    def query(self,**changes):
        d=dict(game='pokemon',set_name='base set',number='4/102',language='english',edition='unlimited',finish='holo',condition='LP',graded=False,now=NOW)
        d.update(changes);return self.lookup.lookup(**d)

    def test_full_identity_exact_and_leading_zero_normalization(self):
        r=self.query(number='004/102');self.assertEqual(r['status'],'exact_match');self.assertEqual(r['provider_sku_id'],'2999653')
        self.assertEqual(r['market_price'],'527.7')

    def test_conditions_are_isolated_never_generic_substitution(self):
        r=self.query(condition='MP');self.assertEqual(r['provider_sku_id'],'2999654');self.assertEqual(r['market_price'],'364.73')
        self.assertNotEqual(r['market_price'],'954.65')
        r=self.lookup.lookup(game='pokemon',set_name='obsidian flames',number='26/197',language='english',edition='standard',finish='non-holo',condition='HP',graded=False,now=NOW)
        self.assertIsNone(r['market_price'])
        self.assertIn(r['status'],['ambiguous_match','price_unavailable'])

    def test_language_edition_finish_grading_and_number_isolation(self):
        for kwargs in [dict(language='japanese'),dict(edition='first edition'),dict(finish='reverse holo'),dict(graded=True),dict(number='4/130')]:
            self.assertEqual(self.query(**kwargs)['status'],'not_found',kwargs)
        self.assertEqual(self.query(edition=None)['status'],'ambiguous_match')
        r=self.lookup.lookup(game='pokemon',set_name='fossil',number='5/62',language='english',edition=None,finish='holo',condition='LP',graded=False,now=NOW)
        self.assertEqual(r['status'],'ambiguous_match');self.assertEqual(len(r['candidates']),2)

    def test_missing_modern_edition_not_copied_from_request(self):
        r=self.lookup.lookup(game='pokemon',set_name='151',number='199/165',language='english',edition='standard',finish='holo',condition='NM',graded=False,now=NOW)
        self.assertEqual(r['status'],'ambiguous_match');self.assertIsNone(r['market_price'])
        self.assertIsNone(r['candidates'][0]['edition'])
        self.assertEqual(r['candidates'][0]['observation']['market_price'],'294.42')

    def test_missing_sku_unknown_provider_and_stale_price(self):
        self.assertEqual(self.lookup.lookup_sku('tcgtracking','999',now=NOW)['status'],'not_found')
        self.assertEqual(self.lookup.lookup_sku('other','2999653',now=NOW)['status'],'not_found')
        r=self.lookup.lookup_sku('tcgtracking','2999653',now='2026-12-01T00:00:00Z')
        self.assertEqual(r['status'],'stale_price');self.assertEqual(r['market_price'],'527.7')

    def test_duplicate_sku_reassignment_rolls_back_entire_set(self):
        e,docs=entry(3);x=json.loads(docs['skus']['payload']);row=x['products']['517045'].pop('7436747');x['products']['517045']['2999653']=row
        docs['skus']['payload']=json_text(x).encode();before=self.counts()
        with self.assertRaisesRegex(ValueError,'identity changed'):Importer(self.db).import_set(**e,documents=docs)
        self.assertEqual(before,self.counts());self.assertEqual(self.query()['market_price'],'527.7')

    def test_negative_currency_and_future_timestamp_rejected_atomically(self):
        for mode in ['negative','currency','timestamp','duplicate_key']:
            e,docs=entry();x=json.loads(docs['skus']['payload']);row=x['products']['509703']['7335315']
            if mode=='negative':row['mkt']='-1'
            if mode=='currency':row['currency']='EUR'
            if mode=='timestamp':x['updated']='2030-01-01T00:00:00Z'
            docs['skus']['payload']=json_text(x).encode()
            if mode=='duplicate_key':docs['skus']['payload']=b'{"set_id":1,"set_id":2}'
            before=self.counts()
            with self.assertRaises(ValueError):Importer(self.db).import_set(**e,documents=docs)
            self.assertEqual(self.counts(),before)

    def test_missing_price_is_null_and_never_zero_or_old_price(self):
        e,docs=entry();x=json.loads(docs['skus']['payload']);x['products']['509703']['7335315'].pop('mkt')
        docs['skus']['payload']=json_text(x).encode();docs['skus']['original_hash']=sha256(docs['skus']['payload']).hexdigest()
        Importer(self.db).import_set(**e,documents=docs,snapshot_date='2026-10-27',captured_at='2026-10-27T18:00:00Z')
        r=self.lookup.lookup_sku('tcgtracking','7335315',now='2026-10-27T18:00:00Z')
        self.assertEqual(r['status'],'price_unavailable');self.assertIsNone(r['market_price'])
        self.assertEqual(self.lookup.history(r['sku_id'])['total'],2)

    def test_daily_unchanged_values_append_both_histories_same_day_idempotent(self):
        before=self.counts()['observations']
        for eindex in (0,1):
            e,docs=entry(eindex)
            for _ in range(2):Importer(self.db).import_set(**e,documents=docs,snapshot_date='2026-10-27',captured_at='2026-10-27T18:00:00Z',capture_kind='cached_daily_snapshot')
        self.assertEqual(self.counts()['observations'],before+12)
        r=self.lookup.lookup_sku('tcgtracking','7335315',now=NOW);h=self.lookup.history(r['sku_id'])['items']
        self.assertEqual([x['snapshot_date'] for x in h],['2026-10-27','2026-10-26'])
        self.assertEqual(h[0]['market_price'],h[1]['market_price'])
        self.assertEqual(h[0]['retrieved_at'],h[1]['retrieved_at']);self.assertNotEqual(h[0]['captured_at'],h[1]['captured_at'])
        self.assertEqual(self.lookup.generic_history(r['card_id'],'Normal')['total'],2)

    def test_append_only_triggers_and_product_guard(self):
        with self.db.transaction() as c:
            for sql in ['UPDATE observations SET market_price=\'1\'','DELETE FROM observations']:
                with self.assertRaises(sqlite3.IntegrityError):c.execute(sql)
            c.execute('PRAGMA foreign_keys')
        self.assertEqual(self.query()['market_price'],'527.7')

    def test_inversions_retained_and_not_liquidity_scores(self):
        for sku in ['7436747','2995236']:
            r=self.lookup.lookup_sku('tcgtracking',sku,now=NOW)
            self.assertIn('condition_price_inversion',r['warnings'])
            self.assertNotIn('liquidity',r)

    def test_search_pagination_card_details_and_generic_history_separate(self):
        self.assertEqual(self.lookup.search('Charizard',limit=1)['total'],3)
        self.assertEqual(len(self.lookup.search('',limit=2,offset=2)['items']),2)
        r=self.query();card=self.lookup.card(r['card_id']);self.assertEqual(len(card['variants']),5)
        self.assertTrue(all(x['sku_id'] is None for x in card['generic_references']))
        self.assertTrue(all(x['price_type']=='sku_market_reference' for x in self.lookup.history(r['sku_id'])['items']))
        self.assertIsNone(self.lookup.card(999));self.assertIsNone(self.lookup.history(999))

    def test_history_comparison_requires_actual_dated_values(self):
        e,docs=entry(5)
        Importer(self.db).import_set(**e,documents=docs,snapshot_date='2026-11-02',captured_at='2026-11-02T18:00:00Z')
        r=self.lookup.lookup_sku('tcgtracking','2999653',now=NOW);cmp=self.lookup.comparisons(sku_id=r['sku_id'])
        self.assertEqual(Decimal(cmp['comparisons']['7']['percentage_change']),0)
        self.assertIsNone(cmp['comparisons']['30']['percentage_change'])
        self.assertIsNone(cmp['comparisons']['90']['percentage_change'])

    def test_http_api_validation_and_no_network_or_writes(self):
        before=self.counts()
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('API must be offline')):
            with TestClient(create_app(self.db.path)) as c:
                self.assertEqual(c.get('/health').json()['status'],'ok')
                self.assertEqual(c.get('/cards/search?limit=101').status_code,422)
                self.assertEqual(c.get('/cards/999').status_code,404)
                self.assertEqual(c.post('/sync').status_code,404)
                self.assertEqual(c.get('/prices/lookup').status_code,422)
                self.assertEqual(c.get('/prices/sku/bad').status_code,422)
                r=c.get('/prices/sku/2999653').json();self.assertEqual(r['market_price'],'527.7')
                params=dict(game='pokemon',set_name='base set',number='4/102',language='english',edition='unlimited',finish='holo',condition='LP',graded='false')
                self.assertEqual(c.get('/prices/lookup',params=params).json()['provider_sku_id'],'2999653')
                self.assertEqual(c.get('/prices/history/'+str(r['sku_id'])).status_code,200)
                self.assertEqual(c.get('/prices/product-history/'+str(r['card_id']),params={'subtype':'Holofoil'}).status_code,200)
                self.assertEqual(c.get('/prices/comparisons/'+str(r['sku_id'])).status_code,200)
                self.assertEqual(len(c.get('/sync/status').json()['items']),10)
                self.assertIn('/prices/lookup',c.get('/openapi.json').json()['paths'])
        self.assertEqual(before,self.counts())

    def test_no_public_sync_and_database_unavailable_health(self):
        with TestClient(create_app(Path(self.tmp.name)/'absent.sqlite')) as c:
            self.assertEqual(c.get('/health').status_code,503)
        self.assertFalse((Path(self.tmp.name)/'absent.sqlite').exists())

    def test_sync_lock_rejects_overlap_and_releases_after_error(self):
        with sync_lock(self.db):
            with self.assertRaises(RuntimeError):
                with sync_lock(self.db):pass
        with sync_lock(self.db):pass


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.db=Database(Path(self.tmp.name)/'sync.sqlite');self.db.migrate()
        self.exports={}
        for index in (0,1):
            e,docs=entry(index)
            for d in docs.values():self.exports[d['url']]=d['payload']
        self.exports['https://tcgcsv.com/last-updated.txt']=b'2026-10-25T20:05:50+0000'
        self.exports['https://tcgcsv.com/tcgplayer/3/groups']=json_text({'results':[BUNDLE['imports'][0]['set_metadata']]}).encode()
        self.opener=Mock();self.opener.open.side_effect=self.response

    def response(self,request,timeout):
        url=request.full_url;body=self.exports[url];r=BytesIO(body);r.status=200;r.geturl=lambda:url;r.headers=Message()
        r.headers['Content-Type']='text/plain' if url.endswith('.txt') else 'application/json';r.headers['ETag']='"fixed"'
        return r

    def client(self,now=NOW):return DailyClient(self.db,now=now,opener=self.opener,sleeper=lambda _:None)

    def test_daily_cooldown_group_dedup_conditional_304_and_unchanged_history(self):
        r=synchronize(self.db,[(3,23228),(3,23228)],client=self.client());self.assertEqual(r['requests'],6);self.assertEqual(r['status'],'success')
        r=synchronize(self.db,[(3,23228)],client=self.client());self.assertEqual(r['requests'],0)
        def unchanged(req,timeout):raise HTTPError(req.full_url,304,'Not modified',{},None)
        self.opener.open.side_effect=unchanged
        r=synchronize(self.db,[(3,23228)],client=self.client('2026-10-27T18:00:01Z'));self.assertEqual(r['status'],'success')
        self.assertEqual(r['requests'],4) # unchanged global marker avoids both CSV export requests
        request=self.opener.open.call_args.args[0];self.assertEqual(request.get_header('If-none-match'),'"fixed"')
        lookup=Lookup(self.db);r=lookup.lookup_sku('tcgtracking','7335315',now=NOW)
        h=lookup.history(r['sku_id'])['items'];self.assertEqual(len(h),2);self.assertEqual(h[0]['market_price'],h[1]['market_price'])

    def test_provider_failure_preserves_prior_prices_partial_state_and_no_retry(self):
        synchronize(self.db,[(3,23228)],client=self.client())
        original=self.response
        def fail(req,timeout):
            if req.full_url.endswith('/skus'):raise URLError('offline')
            return original(req,timeout)
        self.opener.open.side_effect=fail
        r=synchronize(self.db,[(3,23228)],client=self.client('2026-10-27T18:00:01Z'));self.assertEqual(r['status'],'partial_failure')
        self.assertEqual(Lookup(self.db).lookup_sku('tcgtracking','7335315',now=NOW)['market_price'],'0.32')
        self.assertTrue(any(x['status']=='failed' and x['last_success_at'] for x in self.db.sync_status()))
        before=self.opener.open.call_count
        synchronize(self.db,[(3,23228)],client=self.client('2026-10-27T19:00:00Z'))
        self.assertEqual(before,self.opener.open.call_count)

    def test_rate_limit_budget_and_unsafe_endpoints(self):
        client=self.client();client.max_requests=1
        client.get('https://tcgcsv.com/last-updated.txt')
        with self.assertRaises(ValueError):client.get('https://tcgcsv.com/tcgplayer/3/groups')
        with self.assertRaises(ValueError):client.get('https://api.tcgplayer.com/internal')
        self.opener.open.side_effect=HTTPError('https://tcgcsv.com/tcgplayer/3/groups',429,'rate',{'Retry-After':'172800'},None)
        with self.assertRaises(ValueError):self.client().get('https://tcgcsv.com/tcgplayer/3/groups')
        with self.db.connect(readonly=True) as c:r=c.execute("SELECT next_attempt_at FROM endpoints WHERE url LIKE '%/groups'").fetchone()
        self.assertTrue(r[0].startswith('2026-10-28'))


class BackfillTests(unittest.TestCase):
    setUp=DatabaseTests.setUp

    def historical(self,*,payload=None,member='2026-10-25/3/604/prices'):
        payload=payload or json_text({'success':True,'results':[{'productId':42382,'subTypeName':'Holofoil','marketPrice':'900.00'}]}).encode()
        return import_entry(self.db,'2026-10-25',3,604,payload,archive_hash='a'*64,retrieved_at=NOW,member=member,archive_path='synthetic.7z')

    def test_historical_date_preservation_generic_only_and_idempotency(self):
        self.assertEqual(self.historical()['rows'],1);self.assertTrue(self.historical()['already_imported'])
        r=self.lookup.lookup_sku('tcgtracking','2999653',now=NOW)
        self.assertEqual(r['market_price'],'527.7')
        items=self.lookup.generic_history(r['card_id'],'Holofoil')['items'];old=items[-1]
        self.assertEqual(old['snapshot_date'],'2026-10-25');self.assertIsNone(old['source_updated_at'])
        self.assertTrue(old['retrieved_at'].startswith('2026-10-26'));self.assertIsNone(old['sku_id'])
        changed=json_text({'success':True,'results':[{'productId':42382,'subTypeName':'Holofoil','marketPrice':'1'}]}).encode()
        with self.assertRaises(ValueError):self.historical(payload=changed)

    def test_unmapped_product_history_retained_for_review_without_name_join(self):
        payload=json_text({'success':True,'results':[{'productId':999999,'subTypeName':'Normal','marketPrice':'1.25'}]}).encode()
        self.assertEqual(self.historical(payload=payload)['unresolved'],1)
        with self.db.connect(readonly=True) as c:
            r=c.execute('SELECT * FROM historical_unmatched').fetchone();self.assertEqual(r['source_product_id'],'999999')
            self.assertEqual(r['market_price'],'1.25')

    def test_archive_plan_no_download_and_existing_archive_never_refetched(self):
        self.assertEqual(plan()['archive_bytes_estimate'],[730000000,1460000000])
        path=Path(self.tmp.name)/'already.7z';path.write_bytes(b'synthetic')
        opener=Mock();self.assertFalse(download_archive(path,'2026-10-25',opener=opener));opener.open.assert_not_called()
        meta=path.with_suffix(path.suffix+'.json');meta.write_text(json.dumps({'sha256':'0'*64}))
        with self.assertRaises(ValueError):download_archive(path,'2026-10-25',opener=opener)

    def test_actual_7z_extraction_filters_pokemon_and_resumes_without_download(self):
        import py7zr
        root=Path(self.tmp.name);source=root/'source';source.mkdir()
        payload=json_text({'success':True,'results':[{'productId':42382,'subTypeName':'Holofoil','marketPrice':'900.00'}]}).encode()
        f=source/'prices';f.write_bytes(payload)
        archive=root/'prices-2026-10-25.ppmd.7z'
        with py7zr.SevenZipFile(archive,'w',filters=[{'id':py7zr.FILTER_PPMD}]) as z:
            z.write(f,'2026-10-25/3/604/prices');z.write(f,'2026-10-25/1/999/prices')
        with TemporaryDirectory() as out:
            targets=extract_members(archive,'2026-10-25',out)
            self.assertEqual(targets,[('2026-10-25/3/604/prices',3,604)])
            self.assertFalse(Path(out,'2026-10-25/1/999/prices').exists())
        with patch('cardscan.local_pricing.backfill.download_archive',side_effect=AssertionError('No network')):
            r=run(self.db,'2026-10-25','2026-10-25',root)
            self.assertEqual(r[0]['status'],'complete')
            self.assertEqual(run(self.db,'2026-10-25','2026-10-25',root),[])

    def test_missing_archive_failure_resumable_and_no_download_by_default(self):
        with patch('cardscan.local_pricing.backfill.download_archive',side_effect=AssertionError('No network')):
            r=run(self.db,'2026-10-25','2026-10-25',self.tmp.name)
        self.assertEqual(r[0]['status'],'failed')
        self.assertEqual(run(self.db,'2026-10-25','2026-10-25',self.tmp.name)[0]['status'],'cooldown_until_next_day')

    def test_malformed_archive_prices_roll_back(self):
        with self.assertRaises(ValueError):self.historical(payload=b'{"success":true,"results":[{"productId":42382,"subTypeName":"Holofoil","marketPrice":-1}]}')
        with self.db.connect(readonly=True) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM archive_members').fetchone()[0],0)

class BenchmarkTests(unittest.TestCase):
    def test_small_repeated_benchmark_measures_correctness_not_market_accuracy(self):
        from cardscan.local_pricing.benchmark import run
        with TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'bench.sqlite');db.migrate();seed(db);r=run(db)
            self.assertTrue(r['all_correct']);self.assertFalse(r['accuracy_ground_truth'])
            self.assertEqual(r['results']['1000_sequential_exact_sku']['correct'],1000)
            self.assertGreater(r['results']['1000_sequential_exact_sku']['median_ms'],0)
            self.assertGreater(r['database_bytes'],0)

    def test_generic_variant_identity_and_unknown_edition_ambiguity(self):
        with TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'lookup.sqlite');db.migrate();seed(db)
            with db.transaction() as c:
                original=c.execute("SELECT * FROM products WHERE tcgplayer_product_id='42382'").fetchone()
                new=c.execute("INSERT INTO products(game_id,set_id,name,collector_number,raw_collector_number,tcgplayer_product_id) VALUES(?,?,'Charizard error variant','4/102','004/102','9999999')",(original['game_id'],original['set_id'])).lastrowid
                c.execute("INSERT INTO skus(product_id,provider,provider_sku_id,condition,language,edition,finish,graded,raw_variant_json,completeness_json,provenance_json) VALUES(?,'tcgtracking','999999','LP','english',NULL,'holo',0,'{}','{}','{}')",(new,))
            q=dict(game='pokemon',set_name='base set',number='4/102',language='english',edition='unlimited',finish='holo',condition='LP',graded=False,now=NOW)
            self.assertEqual(Lookup(db).lookup(**q)['status'],'ambiguous_match')
            self.assertEqual(Lookup(db).lookup(**q,tcgplayer_product_id=42382)['provider_sku_id'],'2999653')

class AdditionalIntegrityTests(unittest.TestCase):
    setUp=DatabaseTests.setUp

    def test_observation_database_trigger_prevents_wrong_product_join(self):
        with self.db.transaction() as c:
            row=dict(c.execute("SELECT * FROM observations WHERE sku_id IS NOT NULL LIMIT 1").fetchone())
            row.pop('id');row['product_id']=c.execute('SELECT id FROM products WHERE id!=? LIMIT 1',(row['product_id'],)).fetchone()[0]
            row['fingerprint']='synthetic-wrong-product'
            names=list(row)
            with self.assertRaisesRegex(sqlite3.IntegrityError,'SKU/product mismatch'):
                c.execute('INSERT INTO observations('+','.join(names)+') VALUES('+','.join('?' for _ in names)+')',tuple(row.values()))

    def test_empty_catalog_and_malformed_sku_set_preserve_current_data(self):
        e,docs=entry(5);data=json.loads(docs['cards']['payload']);data['products']=[];docs['cards']['payload']=json_text(data).encode()
        with self.assertRaises(ValueError):Importer(self.db).import_set(**e,documents=docs)
        self.assertEqual(self.lookup.lookup_sku('tcgtracking','2999653',now=NOW)['market_price'],'527.7')

    def test_conflicting_providers_remain_separate_candidates(self):
        with self.db.transaction() as c:
            row=dict(c.execute("SELECT * FROM skus WHERE provider_sku_id='2999653'").fetchone());row.pop('id');row['provider']='synthetic_other'
            c.execute('INSERT INTO skus('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        q=dict(game='pokemon',set_name='base set',number='4/102',language='english',edition='unlimited',finish='holo',condition='LP',graded=False,now=NOW)
        result=self.lookup.lookup(**q)
        self.assertEqual(result['status'],'ambiguous_match');self.assertEqual(len(result['candidates']),2)
        self.assertIsNone(result['market_price'])

    def test_partial_seed_does_not_deactivate_other_retained_skus(self):
        with self.db.transaction() as c:
            row=dict(c.execute("SELECT * FROM skus WHERE provider_sku_id='2999653'").fetchone());row.pop('id');row['provider_sku_id']='999998'
            c.execute('INSERT INTO skus('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
        seed(self.db)
        with self.db.connect(readonly=True) as c:self.assertEqual(c.execute("SELECT active FROM skus WHERE provider_sku_id='999998'").fetchone()[0],1)

    def test_complete_snapshot_marks_disappeared_skus_inactive_without_erasing_history(self):
        e,docs=entry(5)
        for d in docs.values():d['kind']='original';d['original_hash']=sha256(d['payload']).hexdigest()
        x=json.loads(docs['skus']['payload']);x['products']['42382'].pop('2999653');docs['skus']['payload']=json_text(x).encode();docs['skus']['original_hash']=sha256(docs['skus']['payload']).hexdigest()
        Importer(self.db).import_set(**e,documents=docs,snapshot_date='2026-10-27',captured_at='2026-10-27T18:00:00Z')
        result=self.lookup.lookup_sku('tcgtracking','2999653',now=NOW)
        self.assertEqual(result['status'],'price_unavailable');self.assertIsNone(result['market_price'])
        self.assertGreater(self.lookup.history(result['sku_id'])['total'],0)
