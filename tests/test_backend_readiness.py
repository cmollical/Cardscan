"""Offline bounded-expansion/streaming contracts; synthetic archives are not market evidence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch,Mock

from fastapi.testclient import TestClient
from cardscan.local_pricing.api import create_app
from cardscan.local_pricing.archive_stream import stream_members,file_hash
from cardscan.local_pricing.backfill import import_entry
from cardscan.local_pricing.cli import seed
from cardscan.local_pricing.database import Database
from cardscan.local_pricing.discovery import discover,select_scopes
from cardscan.local_pricing.importers import Importer,canonical_number
from cardscan.local_pricing.lookup import Lookup
from cardscan.local_pricing.sync import synchronize
from cardscan.structured_prices import json_text
import test_local_pricing as fixtures
entry,NOW=fixtures.entry,fixtures.NOW


class StreamingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.db=Database(self.root/'stream.sqlite');self.db.migrate();seed(self.db)

    def archive(self):
        import py7zr
        price=json_text({'success':True,'results':[{'productId':42382,'subTypeName':'Holofoil','marketPrice':'900.123456789'}]}).encode()
        f=self.root/'prices';f.write_bytes(price);archive=self.root/'sample.7z'
        with py7zr.SevenZipFile(archive,'w',filters=[{'id':py7zr.FILTER_PPMD}]) as z:
            z.write(f,'2026-10-25/3/604/prices');z.write(f,'2026-10-25/85/999/prices');z.write(f,'2026-10-25/1/999/prices')
        return archive,price

    def test_streamed_ppmd_filters_categories_preserves_dates_and_is_idempotent(self):
        archive,payload=self.archive();calls=[]
        def consume(member,body,stats):
            calls.append(member);parts=member.split('/')
            import_entry(self.db,parts[0],int(parts[1]),int(parts[2]),body,archive_hash=file_hash(archive),retrieved_at=NOW,member=member,archive_path=archive)
        r=stream_members(archive,'2026-10-25',consume)
        self.assertEqual(len(calls),2);self.assertEqual(r['completed_members'],2)
        self.assertFalse(any('/1/' in x for x in calls))
        self.assertEqual(r['pokemon_uncompressed_bytes'],2*len(payload))
        self.assertEqual(r['total_uncompressed_bytes'],3*len(payload))
        with self.db.connect(readonly=True) as c:before=c.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
        stream_members(archive,'2026-10-25',consume)
        with self.db.connect(readonly=True) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM observations').fetchone()[0],before)
            row=c.execute("SELECT * FROM observations WHERE snapshot_date='2026-10-25'").fetchone()
        self.assertEqual(row['market_price'],'900.123456789');self.assertIsNone(row['sku_id']);self.assertIsNone(row['source_updated_at'])
        self.assertTrue(row['retrieved_at'].startswith('2026-10-26'))
        self.assertFalse((self.root/'2026-10-25').exists())

    def test_crc_failure_does_not_commit_failed_member(self):
        import py7zr
        from py7zr.py7zr import Worker
        archive,_=self.archive();calls=[];original=Worker.decompress
        def corrupt(self,*args,**kwargs):return original(self,*args,**kwargs)^1
        with patch.object(Worker,'decompress',corrupt):
            with self.assertRaises(Exception):stream_members(archive,'2026-10-25',lambda *args:calls.append(args))
        self.assertEqual(calls,[])

    def test_declared_member_size_bound_before_extraction(self):
        archive,_=self.archive();callback=Mock()
        with self.assertRaises(ValueError):stream_members(archive,'2026-10-25',callback,max_member_bytes=1)
        callback.assert_not_called()


class ExpansionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Database(Path(self.tmp.name)/'ready.sqlite');self.db.migrate();seed(self.db)
        self.lookup=Lookup(self.db)

    def test_candidate_filters_exact_product_and_cross_language(self):
        self.assertEqual(self.lookup.search('Charizard',set_name='151',number='0199/0165')['total'],1)
        self.assertEqual(self.lookup.search('',tcgplayer_product_id=42382)['items'][0]['collector_number'],'4/102')
        self.assertEqual(self.lookup.search('Charizard',language='japanese')['total'],1)
        self.assertEqual(self.lookup.search('',set_name='151',number='201/165')['total'],0)
        self.assertIsNone(self.lookup.product(999999))
        self.assertEqual(self.lookup.product(566544)['collector_number'],'201/165')
        self.assertEqual(canonical_number('tg01/tg30'),'TG1/TG30')
        self.assertEqual(canonical_number('26'),'26')

    def test_http_candidate_routes_and_ascending_history(self):
        e,docs=entry(5)
        Importer(self.db).import_set(**e,documents=docs,snapshot_date='2026-10-27',captured_at='2026-10-27T18:00:00Z')
        e,docs=entry(4)
        Importer(self.db).import_set(**e,documents=docs,snapshot_date='2026-10-27',captured_at='2026-10-27T18:00:00Z')
        sku=self.lookup.lookup_sku('tcgtracking','2999653',now=NOW)
        with TestClient(create_app(self.db.path)) as c:
            card=c.get('/cards/product/42382')
            self.assertEqual(card.status_code,200)
            self.assertEqual(len(card.json()['generic_references']),1)
            self.assertEqual(card.json()['generic_references'][0]['snapshot_date'],'2026-10-27')
            self.assertEqual(self.lookup.generic_history(sku['card_id'],'Holofoil')['total'],2)
            self.assertEqual(c.get('/cards/search',params={'set_name':'151','number':'199/165'}).json()['total'],1)
            dates=[x['snapshot_date'] for x in c.get('/prices/history/'+str(sku['sku_id']),params={'order':'asc'}).json()['items']]
            self.assertEqual(dates,sorted(dates));self.assertEqual(len(dates),2)
            self.assertEqual(c.get('/prices/history/'+str(sku['sku_id']),params={'order':'bad'}).status_code,422)
        self.assertEqual(self.lookup.generic_history(sku['card_id'],'Holofoil',order='asc')['items'][0]['snapshot_date'],'2026-10-26')

    def test_cached_discovery_and_dry_plan_do_not_fetch(self):
        from datetime import datetime,timedelta
        from cardscan.local_pricing.database import utc
        with self.db.transaction() as c:
            for cat in (3,85):
                for provider in ('tcgcsv','tcgtracking'):
                    url=f'https://tcgcsv.com/tcgplayer/{cat}/groups' if provider=='tcgcsv' else f'https://openapi.tcgtracking.com/v1/{cat}/sets'
                    data={'results':[{'groupId':1,'name':'Synthetic set'}]} if provider=='tcgcsv' else {'sets':[{'id':1,'name':'Synthetic set','product_count':10,'sku_count':50}]}
                    doc=self.db.document(c,url=url,payload=json_text(data).encode(),retrieved_at=NOW)
                    c.execute("INSERT INTO endpoints(url,document_id,status) VALUES(?,?,'success')",(url,doc))
        with patch('urllib.request.OpenerDirector.open',side_effect=AssertionError('Dry run must be offline')):
            d=discover(self.db);p=select_scopes(self.db,d,max_sets=2)
        self.assertEqual(p['maximum_export_requests'],8);self.assertEqual(p['network_requests'],0)
        self.assertEqual(len(d['sets']),2)
        with self.assertRaises(ValueError):select_scopes(self.db,d,max_sets=1,explicit=[(3,1),(85,1)])

    def test_edition_migration_enriches_only_explicit_literal_not_finish(self):
        with self.db.transaction() as c:
            row=dict(c.execute("SELECT * FROM skus WHERE provider_sku_id='2999653'").fetchone());row.pop('id')
            row.update(provider_sku_id='9876543',edition=None,finish=None,raw_variant_json=json_text({'var':'1st Edition'}))
            c.execute('INSERT INTO skus('+','.join(row)+') VALUES('+','.join('?' for _ in row)+')',tuple(row.values()))
            # Recreate the exact version-3 state for testing the upgrade only.
            c.execute('DROP TABLE sku_attribute_reviews');c.execute('PRAGMA user_version=3')
            before=[tuple(x) for x in c.execute('SELECT * FROM observations ORDER BY id')]
        self.db.migrate()
        with self.db.connect(readonly=True) as c:
            row=c.execute("SELECT * FROM skus WHERE provider_sku_id='9876543'").fetchone()
            self.assertEqual(row['edition'],'first edition');self.assertIsNone(row['finish'])
            self.assertEqual(before,[tuple(x) for x in c.execute('SELECT * FROM observations ORDER BY id')])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sku_attribute_reviews').fetchone()[0],1)

    def test_concurrent_readers_during_atomic_import_keep_exact_prices(self):
        e,docs=entry(5);gate=threading.Event()
        def writer():
            gate.set();Importer(self.db).import_set(**e,documents=docs,snapshot_date='2026-10-27',captured_at='2026-10-27T18:00:00Z')
        def reader(_):
            gate.wait();return self.lookup.lookup_sku('tcgtracking','2999653',now=NOW)['market_price']
        with ThreadPoolExecutor(max_workers=5) as pool:
            future=pool.submit(writer);values=list(pool.map(reader,range(100)));future.result()
        self.assertEqual(set(values),{'527.7'})

    def test_large_catalog_pagination_and_full_number_isolation(self):
        with self.db.transaction() as c:
            product=c.execute('SELECT * FROM products LIMIT 1').fetchone()
            for i in range(2000):
                c.execute('INSERT INTO products(game_id,set_id,name,collector_number,tcgplayer_product_id) VALUES(?,?,?,?,?)',(product['game_id'],product['set_id'],f'Synthetic searchable {i}',f'{i}/3000',str(9000000+i)))
        self.assertEqual(self.lookup.search('Synthetic searchable',limit=100,offset=100)['total'],2000)
        self.assertEqual(self.lookup.search('',number='1/3000')['total'],1)
        self.assertEqual(self.lookup.search('',number='1/300')['total'],0)


class RecoveryTests(unittest.TestCase):
    setUp=fixtures.SyncTests.setUp
    response=fixtures.SyncTests.response
    client=fixtures.SyncTests.client

    def test_interrupt_after_provider_commit_resumes_without_repeating_success(self):
        def interrupt(_):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):synchronize(self.db,[(3,23228)],client=self.client(),progress=interrupt)
        client=self.client();result=synchronize(self.db,[(3,23228)],client=client,resume=True)
        self.assertEqual(result['status'],'success');self.assertEqual(client.requests,2)
        self.assertEqual(result['sets'][0]['status'],'checkpoint_skipped')

    def test_request_budget_defers_remaining_work_and_resumes_cached_pair(self):
        client=self.client();client.max_requests=3
        result=synchronize(self.db,[(3,23228)],client=client)
        self.assertEqual(result['status'],'budget_exhausted')
        client=self.client();client.max_requests=3
        result=synchronize(self.db,[(3,23228)],client=client,resume=True)
        self.assertEqual(result['status'],'success');self.assertEqual(client.requests,3)

    def test_multiple_english_and_japanese_sets_sync_by_exact_ids(self):
        for index in (8,9):
            e,docs=entry(index)
            for doc in docs.values():self.exports[doc['url']]=doc['payload']
        self.exports['https://tcgcsv.com/tcgplayer/85/groups']=json_text({'results':[fixtures.BUNDLE['imports'][8]['set_metadata']]}).encode()
        client=self.client();result=synchronize(self.db,[(3,23228),(85,23599)],client=client)
        self.assertEqual(result['status'],'success');self.assertEqual(client.requests,11)
        lookup=Lookup(self.db)
        self.assertEqual(lookup.lookup_sku('tcgtracking','8115821',now=NOW)['language'],'japanese')
        self.assertEqual(lookup.lookup_sku('tcgtracking','7335315',now=NOW)['language'],'english')
        self.assertEqual(len(self.db.sync_status()),4)
