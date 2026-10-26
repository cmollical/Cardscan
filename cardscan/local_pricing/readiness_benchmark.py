"""Offline expanded-catalog latency, cached-import, and concurrent-read benchmark."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
import threading
from time import perf_counter

from cardscan.structured_prices import json_text
from .benchmark import run,timing,ASOF
from .database import Database,utc
from .discovery import cached_document
from .importers import Importer,decode
from .lookup import Lookup
from .sync import sync_lock


def observations_hash(db):
    digest=sha256()
    with db.connect(readonly=True) as c:
        for row in c.execute('SELECT * FROM observations ORDER BY id'):
            digest.update(json.dumps(tuple(row),ensure_ascii=False).encode());digest.update(b'\n')
    return digest.hexdigest()


def measure(db):
    baseline=observations_hash(db);lookup=Lookup(db);report=run(db)
    card=lookup.product(42382);sku=next(v['id'] for v in card['variants'] if v['provider_sku_id']=='2999653')
    report['results']['100_catalog_search']=timing(lambda _:lookup.search('Charizard',limit=25)['total']>=3,100)
    report['results']['100_exact_number_search']=timing(lambda _:lookup.search('',set_name='base set',number='4/102')['total']>=1,100)
    report['results']['100_history_queries']=timing(lambda _:lookup.history(sku)['total']>=1,100)
    jobs=[]
    with db.connect(readonly=True) as c:
        mappings=[dict(x) for x in c.execute('SELECT * FROM set_mappings ORDER BY category_id,source_set_id,provider')]
    for row in mappings:
        cat,g,provider=row['category_id'],row['source_set_id'],row['provider']
        root=f'https://tcgcsv.com/tcgplayer/{cat}/{g}' if provider=='tcgcsv' else f'https://openapi.tcgtracking.com/v1/{cat}/sets/{g}'
        keys=('products','prices') if provider=='tcgcsv' else ('cards','skus')
        try:docs={k:cached_document(db,root+'/'+k) for k in keys}
        except ValueError:continue
        group=None
        if provider=='tcgcsv':
            groups=decode(cached_document(db,f'https://tcgcsv.com/tcgplayer/{cat}/groups')['payload'])['results']
            group=next(x for x in groups if x['groupId']==int(g))
        jobs.append((provider,int(cat),int(g),docs,group))
    started=perf_counter();gate=threading.Event();read_times=[];failures=[]
    def writer():
        with sync_lock(db):
            gate.set()
            for provider,cat,g,docs,metadata in jobs:
                Importer(db).import_set(provider,cat,g,docs,set_metadata=metadata,captured_at=utc(),capture_kind='offline_cached_replay')
    def reader(_):
        gate.wait();start=perf_counter();r=lookup.lookup_sku('tcgtracking','2999653',now=ASOF)
        duration=(perf_counter()-start)*1000
        return duration,r['market_price']=='527.7'
    with ThreadPoolExecutor(max_workers=5) as pool:
        writing=pool.submit(writer)
        values=list(pool.map(reader,range(400)));writing.result()
    times=sorted(x[0] for x in values)
    report['concurrent_reads']={'readers':4,'lookups':len(values),'correct':sum(x[1] for x in values),
                                'median_ms':median(times),'p95_ms':times[(95*len(times)+99)//100-1],'maximum_ms':max(times),
                                'cached_provider_set_imports':len(jobs),'combined_wall_seconds':perf_counter()-started}
    report['import_idempotency']={'observations_unchanged':observations_hash(db)==baseline,'provider_set_imports':len(jobs),'network_requests':0}
    with db.connect() as c:
        c.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        report['database_bytes_after']=db.path.stat().st_size
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=measure(Database(a.db));a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json_text(result));print(json_text(result),end='')


if __name__=='__main__':main()
