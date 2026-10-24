"""SYNTHETIC research and review fixtures; never real comps or API results."""
from dataclasses import replace
from datetime import date
import json
from cardscan.ai.models import ResearchTarget, Candidate, claim_id
from cardscan.ai.verification import Verification

TODAY=date(2026,10,24)
TARGET=ResearchTarget('pokemon','Charizard','base set','4/102','english','unlimited','holo','LP')


def candidate(index=1, price='100.00', target=TARGET, **changes):
    data=dict(kind='completed_sale',identity=target.identity(),source_name='synthetic',
              source_record_id='SYNTHETIC-'+str(index),url='https://example.org/synthetic-sale/'+str(index),
              item_price=price,shipping=None,currency='USD',sold_on='2026-10-20',bundle=False,
              quantity=1,price_is_item_only=True,access='full_page',evidence_summary='SYNTHETIC TEST ONLY',
              missing_information=[])
    data.update(changes)
    return data


def response(candidates=None):
    candidates=candidates if candidates is not None else [candidate(i,str(100+i*10)) for i in range(3)]
    return dict(id='resp_SYNTHETIC',model='gpt-5.4-mini',status='completed',
                usage=dict(input_tokens=10000,output_tokens=1500,
                           input_tokens_details={'cached_tokens':2000},output_tokens_details={'reasoning_tokens':300}),
                output=[{'type':'web_search_call','status':'completed','action':{'type':'search','sources':[{'url':c['url']} for c in candidates]}},
                        {'type':'message','content':[{'type':'output_text','text':json.dumps({'candidates':candidates,'limitations':['Synthetic test only']}),'annotations':[]}]}])


def research(candidates=None,target=TARGET):
    r=response(candidates)
    return dict(status='researched',target=target.identity(),as_of=str(TODAY),
                sources=[s['url'] for s in r['output'][0]['action']['sources']],
                evidence=json.loads(r['output'][1]['content'][0]['text']),
                incremental_cost_usd='0.0229',usage={},cache_hit=False)


class SyntheticVerifier:
    def verify(self,target,candidate,as_of):
        return Verification(True,'synthetic independent fixture',str(as_of),'a'*64,'Synthetic source support only')


def review(c):
    return {claim_id(Candidate.model_validate(c)):dict(reviewer='synthetic human',reviewed_on=str(TODAY),
                                                     artifact_sha256='a'*64,substantiates=True)}
