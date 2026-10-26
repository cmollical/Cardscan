"""Synthetic contract tests, plus hash-bound minimal real observation regression.

Synthetic prices exercise parsing only; they are not evidence of market accuracy.
"""
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from email.message import Message
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

from cardscan.references.transport import SourceDocument, SourceRetrievalError
from cardscan.structured_prices import (CatalogBinding, PublicExportTransport,
    TCGCSVProvider, TCGTrackingProvider, json_text, number_key, price)
from cardscan.structured_price_experiment import InvestigationDocuments, run

NOW = '2026-10-26T15:30:00+00:00'
ROOT = 'https://openapi.tcgtracking.com/v1/3/sets/604'
TARGET = dict(game='pokemon',name='Charizard',set_name='base set',number='4/102',
              language='english',edition='unlimited',finish='holo',condition='LP',graded=False)
B = CatalogBinding('synthetic',3,604,42382,'Charizard','Base Set','004/102',TARGET,'https://fixture.example/review')


def doc(url, data):
    return SourceDocument(url, NOW, sha256(json_text(data).encode()).hexdigest(), data)


def data():
    cards = {'set_id':604,'set_name':'Base Set','products':[{'id':42382,'name':'Charizard',
             'number':'004/102','ext_data':{'TCGplayer Tip':'This version from the Unlimited print run has a shadow.'}}]}
    skus = {'set_id':604,'updated':'2026-10-25T13:36:43-04:00','products':{'42382':{
        '123':{'cnd':'LP','var':'Holofoil','lng':'EN','mkt':Decimal('123.45')},
        '124':{'cnd':'MP','var':'Holofoil','lng':'EN','mkt':Decimal('90.00')}}}}
    return cards, skus


def extract(cards=None, skus=None, binding=B):
    a,b = data()
    return TCGTrackingProvider().extract(binding, doc(ROOT+'/cards', cards if cards is not None else a),
                                         doc(ROOT+'/skus', skus if skus is not None else b))


class StructuredPriceTests(unittest.TestCase):
    def test_success_is_reference_not_transaction_or_automatic_valuation(self):
        r=extract()
        self.assertEqual(r.status,'retrieved_condition_reference')
        self.assertEqual(r.fields['market_price'].value,'123.45')
        self.assertEqual(r.fields['edition'].value,'unlimited')
        self.assertEqual(r.fields['condition'].value,'LP')
        self.assertTrue(r.fields['condition'].substantiated)
        self.assertFalse(r.fields['currency'].substantiated)
        self.assertIsNone(r.fields['shipping_excluded'].value)
        self.assertFalse(r.independent_upstream_verification)
        self.assertFalse(r.eligible_for_automatic_valuation)
        self.assertNotIn('transaction_id',r.fields)
        self.assertNotIn('sold_on',r.fields)

    def test_wrong_printing_set_number_name_and_document_rejected(self):
        for field,value in [('name','Blastoise'),('number','4'),('number','4/130')]:
            a,b=data();a['products'][0][field]=value
            self.assertEqual(extract(a,b).status,'rejected')
        a,b=data();a['set_id']=605
        self.assertEqual(extract(a,b).status,'rejected')
        a,b=data();a['set_name']='Base Set 2'
        self.assertEqual(extract(a,b).status,'rejected')
        with self.assertRaises(ValueError):
            TCGTrackingProvider().extract(B,doc(ROOT+'/wrong',a),doc(ROOT+'/skus',b))

    def test_wrong_condition_language_finish_and_edition_not_selected(self):
        for key,value in [('cnd','MP'),('cnd','raw'),('cnd',None),('lng','JP'),('lng',None),
                          ('var','Reverse Holofoil'),('var','1st Edition Holofoil'),('var','Unknown')]:
            a,b=data();b['products']['42382']['123'][key]=value
            self.assertEqual(extract(a,b).status,'unavailable',(key,value))

    def test_missing_edition_is_not_filled_or_cardtrader_default_used(self):
        a,b=data();a['products'][0]['ext_data']={}
        a['products'][0]['cardtrader']=[{'properties':[{'name':'first_edition','default_value':'false'}]}]
        r=extract(a,b)
        self.assertEqual(r.status,'retrieved_condition_reference')
        self.assertIsNone(r.fields['edition'].value)
        self.assertTrue(any('Edition unspecified' in x for x in r.limitations))

    def test_graded_target_excluded(self):
        r=extract(binding=replace(B,target={**TARGET,'graded':True}))
        self.assertEqual(r.status,'unavailable')

    def test_duplicate_product_or_matching_sku_fail_closed(self):
        a,b=data();a['products']*=2
        self.assertEqual(extract(a,b).status,'rejected')
        a,b=data();b['products']['42382']['999']=deepcopy(b['products']['42382']['123'])
        self.assertEqual(extract(a,b).status,'rejected')

    def test_missing_price_and_zero_invalid_never_substitute_listing_low(self):
        for value in (None,Decimal('0'),Decimal('-1'),Decimal('NaN'),True,1.25,'broken'):
            a,b=data();b['products']['42382']['123']['mkt']=value
            b['products']['42382']['123']['low']=Decimal('100')
            self.assertEqual(extract(a,b).status,'unavailable',value)

    def test_precise_prices_and_full_numbers(self):
        self.assertEqual(price(Decimal('0.123456789123456789')),'0.123456789123456789')
        self.assertEqual(number_key('004/102'),(4,102))
        self.assertIsNone(number_key('4'))
        with self.assertRaises(ValueError):price(0.35)
        self.assertIn('0.123456789123456789',json_text({'v':Decimal('0.123456789123456789')}))

    def test_date_freshness_and_missing_source_values(self):
        for value,label in [('2026-10-27T12:00:00Z','future'),('2026-09-01T00:00:00Z','48 hours'),
                            (None,'timestamp'),('2026-10-25','timestamp')]:
            a,b=data();b['updated']=value;r=extract(a,b)
            self.assertTrue(any(label in x for x in r.issues))
            if label=='future':self.assertEqual(r.status,'rejected')

    def test_inversion_preserved_not_smoothed(self):
        a,b=data();b['products']['42382']['123']['var']='1st Edition Holofoil'
        b['products']['42382']['124'].update(cnd='NM',var='1st Edition Holofoil',mkt=Decimal('90'))
        r=extract(a,b,replace(B,target={**TARGET,'edition':'first edition'}))
        self.assertEqual(r.fields['market_price'].value,'123.45')
        self.assertTrue(any('inversion' in x for x in r.issues))

    def test_csv_stays_generic_and_low_is_not_market(self):
        root='https://tcgcsv.com/tcgplayer/3/604'
        products={'success':True,'results':[{'productId':42382,'name':'Charizard','groupId':604,
             'categoryId':3,'extendedData':[{'name':'Number','value':'004/102'}]}]}
        prices={'success':True,'results':[{'productId':42382,'subTypeName':'Holofoil',
                                         'marketPrice':Decimal('200.01'),'lowPrice':Decimal('1')}]}
        r=TCGCSVProvider().extract(B,doc(root+'/products',products),doc(root+'/prices',prices))
        self.assertEqual(r.status,'retrieved_generic_reference')
        self.assertEqual(r.fields['market_price'].value,'200.01')
        for key in ['condition','language','edition','graded']:self.assertIsNone(r.fields[key].value)
        self.assertFalse(r.eligible_for_automatic_valuation)

    def test_research_only_purpose(self):
        for provider in (TCGCSVProvider,TCGTrackingProvider):
            with self.assertRaises(ValueError):provider(purpose='commercial')

    def test_transport_no_unapproved_hosts_query_credentials_or_redirects(self):
        transport=PublicExportTransport(opener=Mock())
        for url in ['http://openapi.tcgtracking.com/v1/3/sets/604/skus',ROOT+'/skus?key=x',
                    'https://user:pass@openapi.tcgtracking.com/v1/3/sets/604/skus',
                    'https://api.tcgplayer.com/pricing/sku/123',ROOT+'/internal']:
            with self.assertRaises(SourceRetrievalError):transport.get(url)
        transport.opener.open.assert_not_called()

    def test_mock_http_precision_json_duplicates_failures_and_limits(self):
        def response(body,kind='application/json',url=ROOT+'/skus'):
            obj=BytesIO(body);obj.status=200;obj.headers=Message();obj.headers['Content-Type']=kind
            obj.geturl=lambda:url
            return obj
        opener=Mock();opener.open.return_value=response(b'{"price":0.123456789123456789}')
        result=PublicExportTransport(opener=opener).get(ROOT+'/skus')
        self.assertEqual(result.data['price'],Decimal('0.123456789123456789'))
        for body,kind,url,limit in [(b'{"a":1,"a":2}','application/json',ROOT+'/skus',100),
             (b'{}','text/html',ROOT+'/skus',100),(b'{}','application/json',ROOT+'/else',100),
             (b'{"x":NaN}','application/json',ROOT+'/skus',100),(b'{}','application/json',ROOT+'/skus',1)]:
            opener.open.return_value=response(body,kind,url)
            with self.assertRaises(SourceRetrievalError):PublicExportTransport(opener=opener,max_bytes=limit).get(ROOT+'/skus')
        for exc in [TimeoutError(),URLError('offline'),HTTPError(ROOT+'/skus',429,'limit',{},None)]:
            opener.open.side_effect=exc
            with self.assertRaises(SourceRetrievalError):PublicExportTransport(opener=opener).get(ROOT+'/skus')

    def test_real_minimal_audit_five_condition_rows_and_manual_match(self):
        # These are retained observations, not synthetic accuracy ground truth.
        p=Path('research/results/structured-prices-2026-10-26.json')
        if not p.exists():self.fail('Real investigation audit missing')
        report=json.loads(p.read_text());rows=[x for x in report['observations'] if x['provider']=='tcgtracking']
        self.assertEqual(len(rows),5)
        vintage=next(x for x in rows if x['case_id']=='vintage-charizard-lp')
        self.assertEqual(Decimal(vintage['fields']['market_price']['value']),Decimal('527.70'))
        self.assertEqual(vintage['fields']['condition']['value'],'LP')
        self.assertFalse(any(x['eligible_for_automatic_valuation'] for x in rows))
        self.assertTrue(all(x['original_ai_proposal_usd'] is not None for x in rows))

    def test_original_document_hash_replay_and_duplicate_request_guard(self):
        with TemporaryDirectory() as directory:
            p=Path(directory);url=ROOT+'/skus';key=sha256(url.encode()).hexdigest()[:12];body=b'{"a":1}'
            (p/(key+'.body')).write_bytes(body)
            (p/(key+'.json')).write_text(json.dumps(dict(url=url,status=200,file=key+'.body',
                 sha256=sha256(body).hexdigest(),retrieved_at=NOW)))
            transport=Mock();d=InvestigationDocuments(p,transport)
            self.assertEqual(d.get(url).data,{'a':1});transport.get.assert_not_called()
            with self.assertRaises(ValueError):d.get(url)
            (p/(key+'.body')).write_bytes(b'{}')
            with self.assertRaises(ValueError):InvestigationDocuments(p,transport).get(url)


if __name__=='__main__':unittest.main()
