"""Single permitted research retrieval. No OpenAI call, cache or valuation."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import time

from ..ai.models import ResearchTarget
from .adapters import TCGdexAdapter
from .models import ReferenceCandidate
from .service import ReferenceVerifier, write_audit
from .transport import JsonTransport


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,help='New audit JSON file; refuses overwrite')
    p.add_argument('--purpose',choices=['research','commercial'],default='research')
    args=p.parse_args()
    target=ResearchTarget('pokemon','Charizard ex','151','199/165','english','standard','holo','NM',False)
    candidate=ReferenceCandidate('tcgdex','https://api.tcgdex.net/v2/en/cards/sv03.5-199','holofoil')
    start=time.monotonic()
    result=ReferenceVerifier([TCGdexAdapter()],JsonTransport(),purpose=args.purpose).verify(target,candidate)
    write_audit(result,args.output)
    print(json.dumps({'status':result.status,'eligible_for_condition_valuation':result.eligible_for_condition_valuation,
                      'source_price':asdict(result.fields['price']) if 'price' in result.fields else None,
                      'rejections':result.rejection_reasons,'latency_seconds':time.monotonic()-start,
                      'paid_openai_calls':0,'source_api_charge_usd':'0'},indent=2))


if __name__=='__main__': main()
