"""SYNTHETIC market-estimation fixtures. Never actual card prices or source proof."""
from datetime import date
import json
from cardscan.ai.models import ResearchTarget

AS_OF=date(2026,10,25)
TARGET=ResearchTarget('pokemon','Charizard ex','151','199/165','english','standard','holo','NM')


def estimate(target=TARGET):
    return dict(card_identity=target.identity(),requested_condition=target.condition,
        estimated_market_value='100.00',estimated_low='90.00',estimated_high='110.00',currency='USD',
        valuation_type='condition_specific_market_estimate',evidence_quality='limited',
        sources=[dict(id='s1',source_name='SYNTHETIC fixture only',url='https://example.org/synthetic/market',
                      reported_price='100.00',currency='USD',price_type='published_market_reference',
                      price_meaning='SYNTHETIC market benchmark',observed_identity=target.identity(),
                      condition_scope='explicit_condition',condition_label=target.condition,
                      source_date='2026-10-24',date_meaning='published_update',price_basis='item_only',
                      observation_kind='search_result',source_summary='SYNTHETIC fixture only',missing_information=[])],
        supporting_source_ids=['s1'],reasoning_summary='Synthetic estimate derived from synthetic benchmark.',
        assumptions=[],limitations=['Synthetic, unverified test fixture.'],recommendation='usable_estimate',
        review_recommended=False,insufficient_evidence=False)


def response(data=None,target=TARGET):
    data=estimate(target) if data is None else data
    return dict(id='resp_SYNTHETIC_market',model='gpt-5.4-mini-2026-03-17',status='completed',
        usage={'input_tokens':10000,'output_tokens':2000,'input_tokens_details':{'cached_tokens':0},
               'output_tokens_details':{'reasoning_tokens':300}},
        tool_usage={'web_search':{'num_requests':1}},
        output=[{'id':'ws_synthetic_1','type':'web_search_call','status':'completed',
                 'action':{'type':'search','sources':[{'url':s['url']} for s in data['sources']]}},
                {'type':'message','content':[{'type':'output_text','text':json.dumps(data),'annotations':[]}]}])
