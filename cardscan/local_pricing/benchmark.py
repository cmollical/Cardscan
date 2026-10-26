"""Repeatable local-only lookup benchmark; no identification/AI/network latency."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import platform
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from cardscan.structured_prices import json_text
from .database import Database
from .lookup import Lookup
from .cli import seed

CASES=[('7335315','0.32'),('7436747','294.42'),('2999653','527.7'),('2995236','458.05'),('8115821','388.35')]
ASOF='2026-10-26T16:00:00Z'


def timing(work,n):
    times=[];correct=0
    for i in range(n):
        start=perf_counter_ns();ok=work(i);times.append((perf_counter_ns()-start)/1_000_000);correct+=bool(ok)
    ordered=sorted(times)
    return {'lookups':n,'correct':correct,'median_ms':median(times),'p95_ms':ordered[max(0,(95*n+99)//100-1)],'maximum_ms':max(times)}


def run(db,*,import_seconds=None):
    look=Lookup(db)
    def exact(i):
        sku,amount=CASES[i%5];r=look.lookup_sku('tcgtracking',sku,now=ASOF)
        return r['status']=='exact_match' and r['market_price']==amount and r['provider_sku_id']==sku
    kwargs=dict(game='pokemon',set_name='fossil',number='5/62',language='english',edition=None,finish='holo',condition='LP',graded=False,now=ASOF)
    tests={'100_sequential_exact_sku':timing(exact,100),'1000_sequential_exact_sku':timing(exact,1000),
           '1000_same_card':timing(lambda _:exact(2),1000),
           '100_missing':timing(lambda _:look.lookup_sku('tcgtracking','999999999',now=ASOF)['status']=='not_found',100),
           '100_ambiguous_variant':timing(lambda _:look.lookup(**kwargs)['status']=='ambiguous_match',100),
           '100_full_identity':timing(lambda _:look.lookup(**{**kwargs,'set_name':'base set','number':'4/102','edition':'unlimited','tcgplayer_product_id':42382}).get('provider_sku_id')=='2999653',100)}
    with db.connect() as c:
        c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        counts={t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['games','sets','products','skus','observations']}
    return {'measured_at':datetime.now(timezone.utc).isoformat(),'python':platform.python_version(),'platform':platform.platform(),
            'scope':'Local indexed SQLite lookups including per-call read-only connection, JSON decode and freshness; warm OS cache. No HTTP/AI/camera latency.',
            'source_as_of':ASOF,'counts':counts,'database_bytes':db.path.stat().st_size,'import_seconds':import_seconds,
            'results':tests,'all_correct':all(x['correct']==x['lookups'] for x in tests.values()),
            'paid_api_calls':0,'accuracy_ground_truth':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path);p.add_argument('--documents',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.db:result=run(Database(a.db))
    else:
        with TemporaryDirectory() as tmp:
            db=Database(Path(tmp)/'benchmark.sqlite');started=perf_counter_ns();db.migrate()
            if a.documents:
                from .cli import replay_originals
                replay_originals(db,a.documents)
            else:seed(db)
            result=run(db,import_seconds=(perf_counter_ns()-started)/1_000_000_000)
    result['import_scope']='20 retained full provider exports, five sets, no network' if a.documents else 'existing database' if a.db else 'portable five-product dated evidence excerpts'
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json_text(result));print(json_text(result),end='')


if __name__=='__main__':main()
