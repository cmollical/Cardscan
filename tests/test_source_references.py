"""All source HTTP responses here are mocked. Fixtures are not market evidence."""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock
from email.message import Message
from urllib.error import HTTPError, URLError

from cardscan.ai.models import ResearchTarget
from cardscan.references import FieldEvidence, ReferenceCandidate, SourcePermission, ReferenceVerifier
from cardscan.references.adapters import TCGdexAdapter, restricted_sources
from cardscan.references.service import write_audit
from cardscan.references.transport import JsonTransport, NoRedirects, SourceDocument, SourceRetrievalError

FIXTURES=Path(__file__).parent/'fixtures'
NOW=datetime(2026,10,25,1,tzinfo=timezone.utc)
TARGET=ResearchTarget('pokemon','Charizard ex','151','199/165','english','standard','holo','NM')
URL='https://fixture.example/reference'
TCGURL='https://api.tcgdex.net/v2/en/cards/sv03.5-199'


class SyntheticAdapter:
    """Only a test implementation of the modular interface. Never registered live."""
    source='synthetic'
    method='synthetic_json_fixture'
    permission=SourcePermission('synthetic',True,True,True,('https://fixture.example/permission',),'2026-10-25','Synthetic test-only permission')
    def accepts(self,url): return url==URL
    def extract(self,document,variant):
        return {k:FieldEvidence(v,'structured_metadata','/'+k,self.method,document.url,document.sha256)
                for k,v in document.data.items() if not k.startswith('_')}


class SourceVerificationTests(unittest.TestCase):
    def fixture(self,tcgdex=False):
        return json.loads((FIXTURES/('reference-synthetic-tcgdex.json' if tcgdex else 'reference-synthetic-explicit.json')).read_text())

    def setup_verifier(self,data=None,adapter=None,claims=None,purpose='research'):
        adapter=adapter or SyntheticAdapter(); data=self.fixture() if data is None else data
        url=TCGURL if adapter.source=='tcgdex' else URL
        body=json.dumps(data).encode()
        doc=SourceDocument(url,NOW.isoformat(),sha256(body).hexdigest(),data)
        transport=Mock();transport.get.return_value=doc
        verifier=ReferenceVerifier([adapter],transport,purpose=purpose)
        return verifier,ReferenceCandidate(adapter.source,url,'holofoil',claims or {}),transport

    def test_successful_synthetic_contract_and_status_transitions(self):
        v,c,t=self.setup_verifier()
        r=v.verify(TARGET,c,now=NOW)
        self.assertEqual(r.status,'verified');self.assertTrue(r.eligible_for_condition_valuation)
        self.assertEqual(r.transitions,['discovered','permission_checked','retrieved','extracted','verified'])
        self.assertEqual(r.fields['condition'].value,'NM')
        self.assertNotIn('sold_on',r.fields)

    def test_wrong_identity_dimensions_rejected(self):
        for field,value in [('number','6/165'),('set_name','base set'),('name','Blastoise ex'),
                            ('language','japanese'),('edition','first edition'),('finish','reverse holo'),('graded',True)]:
            data=self.fixture();data[field]=value
            v,c,_=self.setup_verifier(data)
            r=v.verify(TARGET,c,now=NOW)
            self.assertEqual(r.status,'rejected',field)
            self.assertFalse(r.eligible_for_condition_valuation)

    def test_unknown_generic_and_descriptive_conditions_do_not_become_nm(self):
        for condition in (None,'ungraded','unknown','excellent condition','Near mint or better','LP','MP','HP','DMG'):
            data=self.fixture();data['condition']=condition
            v,c,_=self.setup_verifier(data)
            r=v.verify(TARGET,c,now=NOW)
            self.assertNotEqual(r.status,'verified')
            self.assertEqual(r.fields['condition'].value,condition)
            if condition in ('ungraded','raw'):
                self.assertEqual(r.condition_scope,'generic_ungraded')
                self.assertEqual(r.status,'context_only')

    def test_condition_claim_contradictions_rejected(self):
        for claims in ({'condition':'NM','missing_information':['exact condition']},
                       {'condition':'NM','summary':'only raw status known'}, {'condition':'LP'}):
            v,c,_=self.setup_verifier(claims=claims)
            r=v.verify(TARGET,c,now=NOW)
            self.assertEqual(r.status,'rejected');self.assertTrue(r.claim_issues)

    def test_actual_source_cannot_be_overridden_by_ai_claim(self):
        data=self.fixture();data['condition']=None
        v,c,_=self.setup_verifier(data,claims={'condition':'NM','price':'100.00'})
        r=v.verify(TARGET,c,now=NOW)
        self.assertEqual(r.status,'context_only')
        self.assertIsNone(r.fields['condition'].value)
        self.assertIn('condition AI claim not source-supported',r.claim_issues)

    def test_missing_invalid_prices_and_wrong_currency(self):
        for price in (None,'','NaN','Infinity','-1','0',True):
            data=self.fixture();data['price']=price
            v,c,_=self.setup_verifier(data);self.assertEqual(v.verify(TARGET,c,now=NOW).status,'rejected')
        for currency in (None,'EUR','usd'):
            data=self.fixture();data['currency']=currency
            v,c,_=self.setup_verifier(data);self.assertEqual(v.verify(TARGET,c,now=NOW).status,'rejected')

    def test_active_price_and_unknown_shipping_basis_not_market_value(self):
        data=self.fixture();data['price_type']='active_listing'
        v,c,_=self.setup_verifier(data);self.assertEqual(v.verify(TARGET,c,now=NOW).status,'rejected')
        data=self.fixture();data['price_basis']=None
        v,c,_=self.setup_verifier(data);self.assertEqual(v.verify(TARGET,c,now=NOW).status,'context_only')

    def test_retrieval_failure_timeout_and_unavailable_page(self):
        for error in (SourceRetrievalError('HTTP 404'),OSError('offline'),TimeoutError()):
            v,c,t=self.setup_verifier();t.get.side_effect=error
            r=v.verify(TARGET,c,now=NOW)
            self.assertEqual(r.status,'retrieval_failed');self.assertIsNone(r.content_sha256)
            self.assertFalse(r.eligible_for_condition_valuation)

    def test_source_and_purpose_permission_precedes_network(self):
        for attr,value in [('retrieval_allowed',False),('minimal_retention_allowed',False),('commercial_allowed',False)]:
            a=SyntheticAdapter();a.permission=replace(a.permission,**{attr:value})
            v,c,t=self.setup_verifier(adapter=a,purpose='commercial')
            self.assertEqual(v.verify(TARGET,c,now=NOW).status,'permission_blocked');t.get.assert_not_called()
        v,c,t=self.setup_verifier(adapter=TCGdexAdapter(),purpose='commercial')
        self.assertEqual(v.verify(TARGET,c,now=NOW).status,'permission_blocked');t.get.assert_not_called()

    def test_restricted_marketplaces_never_retrieve(self):
        for a in restricted_sources():
            transport=Mock()
            c=ReferenceCandidate(a.source,'https://'+a.host+'/product','holofoil')
            r=ReferenceVerifier([a],transport).verify(TARGET,c,now=NOW)
            self.assertEqual(r.status,'permission_blocked');transport.get.assert_not_called()

    def test_duplicates_do_not_fetch_or_count_twice(self):
        v,c,t=self.setup_verifier();self.assertEqual(v.verify(TARGET,c,now=NOW).status,'verified')
        self.assertEqual(v.verify(TARGET,c,now=NOW).status,'duplicate');self.assertEqual(t.get.call_count,1)

    def test_provenance_and_minimal_audit_are_bound_and_immutable(self):
        v,c,_=self.setup_verifier();r=v.verify(TARGET,c,now=NOW)
        for name,proof in r.fields.items():
            self.assertEqual(proof.content_sha256,r.content_sha256)
            self.assertEqual(proof.source_url,r.canonical_url);self.assertTrue(proof.locator)
        with TemporaryDirectory() as d:
            p=Path(d)/'audit.json';write_audit(r,p);saved=json.loads(p.read_text())
            self.assertEqual(saved['record_sha256'],r.audit_hash())
            self.assertNotIn('body',saved['record']);self.assertNotIn('data',saved['record'])
            with self.assertRaises(FileExistsError):write_audit(r,p)

    def test_bad_provenance_and_non_direct_fields_cannot_verify(self):
        for basis in ('inferred','ai_claim','contradictory'):
            a=SyntheticAdapter();original=a.extract
            def extract(doc,variant):
                f=original(doc,variant);f['condition']=replace(f['condition'],basis=basis);return f
            a.extract=extract
            v,c,_=self.setup_verifier(adapter=a);self.assertNotEqual(v.verify(TARGET,c,now=NOW).status,'verified')
        a=SyntheticAdapter();original=a.extract
        def bad_hash(doc,variant):
            f=original(doc,variant);f['price']=replace(f['price'],content_sha256='f'*64);return f
        a.extract=bad_hash
        v,c,_=self.setup_verifier(adapter=a);self.assertEqual(v.verify(TARGET,c,now=NOW).status,'rejected')

    def test_stale_missing_and_future_publisher_dates_require_review(self):
        for updated in (None,'2026-10-01T00:00:00Z','2026-11-01T00:00:00Z','2026-10-25'):
            data=self.fixture();data['published_at']=updated
            v,c,_=self.setup_verifier(data);self.assertEqual(v.verify(TARGET,c,now=NOW).status,'context_only')

    def test_tcgdex_preserves_missing_fields_and_never_copies_target_nm(self):
        v,c,_=self.setup_verifier(self.fixture(True),TCGdexAdapter())
        r=v.verify(TARGET,c,now=NOW)
        self.assertEqual(r.status,'context_only')
        self.assertEqual(r.fields['price'].value,100.0)
        self.assertEqual(r.fields['number'].value,'199/165')
        for field in ('condition','language','edition','graded','price_basis'):
            self.assertIsNone(r.fields[field].value)
        self.assertEqual(r.fields['metadata_language'].value,'en')
        self.assertFalse(r.eligible_for_condition_valuation)

    def test_price_claim_compares_decimal_amounts_not_string_vs_float(self):
        v,c,_=self.setup_verifier(claims={'price':100.0})
        self.assertEqual(v.verify(TARGET,c,now=NOW).status,'verified')

    def test_ai_candidate_bridge_preserves_claims_without_promoting_provenance(self):
        c=ReferenceCandidate.from_ai({'source_name':'tcgdex','url':TCGURL,'identity':{'condition':'NM'},
                                     'item_price':'100.00','currency':'USD','evidence_summary':'AI only'},variant='holofoil')
        self.assertEqual(c.claims['condition'],'NM')
        v,_,_=self.setup_verifier(self.fixture(True),TCGdexAdapter())
        r=v.verify(TARGET,c,now=NOW);self.assertFalse(r.eligible_for_condition_valuation)


class TransportTests(unittest.TestCase):
    def response(self,body=b'{}',url=TCGURL,ctype='application/json',status=200):
        r=Mock();r.__enter__=Mock(return_value=r);r.__exit__=Mock(return_value=False)
        r.status=status;r.geturl.return_value=url;r.read.return_value=body
        r.headers=Message();r.headers['Content-Type']=ctype
        return r

    def test_document_hash_and_timestamp_from_actual_transport_bytes(self):
        opener=Mock();opener.open.return_value=self.response(b'{"id":"synthetic"}')
        d=JsonTransport(opener=opener).get(TCGURL)
        self.assertEqual(d.sha256,sha256(b'{"id":"synthetic"}').hexdigest())
        self.assertEqual(d.data['id'],'synthetic');self.assertIsNotNone(datetime.fromisoformat(d.retrieved_at).tzinfo)

    def test_arbitrary_hosts_credentials_query_and_unapproved_paths_refused(self):
        opener=Mock()
        for url in ('http://api.tcgdex.net/v2/en/cards/x','https://127.0.0.1/x',
                    'https://api.tcgdex.net.evil.test/v2/en/cards/x','https://user:key@api.tcgdex.net/v2/en/cards/x',
                    TCGURL+'?api_key=secret',TCGURL+'#fragment','https://api.tcgdex.net/other'):
            with self.assertRaises(ValueError):JsonTransport(opener=opener).get(url)
        opener.open.assert_not_called()

    def test_non_json_challenges_malformed_oversized_duplicate_and_nonfinite_json_refused(self):
        for response in (self.response(b'<html>captcha</html>',ctype='text/html'),self.response(b'{'),
                         self.response(b'[]'),self.response(b'{"a":1,"a":2}'),
                         self.response(b'{"a":NaN}'),self.response(b'x'*11)):
            opener=Mock();opener.open.return_value=response
            with self.assertRaises(SourceRetrievalError):JsonTransport(opener=opener,max_bytes=10).get(TCGURL)

    def test_redirects_and_http_errors_fail_without_retry(self):
        with self.assertRaises(SourceRetrievalError):NoRedirects().redirect_request(None,None,None,None,None,None)
        for error in (HTTPError(TCGURL,403,'forbidden',{},None),URLError('offline'),TimeoutError()):
            opener=Mock();opener.open.side_effect=error
            with self.assertRaises(SourceRetrievalError):JsonTransport(opener=opener).get(TCGURL)
            self.assertEqual(opener.open.call_count,1)
