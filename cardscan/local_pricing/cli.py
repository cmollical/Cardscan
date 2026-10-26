"""SQLite init/dated-fixture import/provider sync. All administration stays CLI-only."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

from cardscan.structured_prices import json_text
from .database import Database
from .importers import Importer
from .sync import DailyClient, synchronize, sync_lock

FIXTURE=Path(__file__).resolve().parents[2]/'research/evidence/local-pricing/october-26-excerpts.json'


def seed(db,path=FIXTURE):
    data=json.loads(Path(path).read_text())
    if data['version']!='provider-excerpts-v1':raise ValueError('Unsupported evidence bundle')
    with sync_lock(db):
        for entry in data['imports']:
            entry=dict(entry);docs={}
            for key,d in entry.pop('documents').items():
                docs[key]={k:v for k,v in d.items() if k in ['url','retrieved_at','original_hash','kind']}
                docs[key]['payload']=json_text(d['data']).encode()
            Importer(db).import_set(**entry,documents=docs)
            from datetime import datetime,timedelta
            from .database import utc
            with db.transaction() as c:
                for d in docs.values():
                    stamp=utc(d['retrieved_at']);retry=(datetime.fromisoformat(stamp)+timedelta(hours=24)).isoformat()
                    c.execute("INSERT INTO endpoints(url,last_attempt_at,next_attempt_at,status) VALUES(?,?,?,'excerpt_only') ON CONFLICT(url) DO NOTHING",(d['url'],stamp,retry))
    return db.health()



def replay_originals(db,directory):
    """Import full retained set exports with original hash verification, no HTTP."""
    from datetime import datetime,timedelta
    from .database import utc
    directory=Path(directory)
    bindings=json.loads((Path(__file__).resolve().parents[2]/'experiments/structured-prices/targets.json').read_text())['bindings']
    def original(url):
        key=sha256(url.encode()).hexdigest()[:12];meta=json.loads((directory/(key+'.json')).read_text())
        payload=(directory/meta['file']).read_bytes()
        if meta['url']!=url or meta['status']!=200 or sha256(payload).hexdigest()!=meta['sha256']:raise ValueError('Original document integrity failure')
        return dict(url=url,payload=payload,retrieved_at=meta['retrieved_at'],original_hash=meta['sha256'],kind='original')
    results=[]
    with sync_lock(db):
        for b in bindings:
            cat,g=b['category_id'],b['set_id']
            groups=json.loads(original(f'https://tcgcsv.com/tcgplayer/{cat}/groups')['payload'])['results']
            group=next(x for x in groups if x['groupId']==g)
            for provider in ('tcgcsv','tcgtracking'):
                keys=('products','prices') if provider=='tcgcsv' else ('cards','skus')
                root=f'https://tcgcsv.com/tcgplayer/{cat}/{g}' if provider=='tcgcsv' else f'https://openapi.tcgtracking.com/v1/{cat}/sets/{g}'
                docs={k:original(root+'/'+k) for k in keys}
                results.append(Importer(db).import_set(provider,cat,g,docs,aliases=[b['target']['set_name']],set_metadata=group))
                with db.transaction() as c:
                    for d in docs.values():
                        stamp=utc(d['retrieved_at']);retry=(datetime.fromisoformat(stamp)+timedelta(hours=24)).isoformat()
                        docid=db.document(c,**d)
                        c.execute("INSERT INTO endpoints(url,document_id,last_attempt_at,last_success_at,next_attempt_at,status) VALUES(?,?,?,?,?,'success') ON CONFLICT(url) DO NOTHING",(d['url'],docid,stamp,stamp,retry))
    return {'imports':results,**db.health()}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',type=Path,default=Path('local-evidence/pricing.sqlite'))
    sub=p.add_subparsers(dest='command',required=True)
    r=sub.add_parser('replay');r.add_argument('--documents',type=Path,required=True)
    sub.add_parser('init');s=sub.add_parser('seed');s.add_argument('--fixture',type=Path,default=FIXTURE)
    s=sub.add_parser('sync');s.add_argument('--set',action='append',default=[],help='Exact category:group; repeatable. Defaults to five researched sets.')
    s.add_argument('--max-requests',type=int,default=40)
    s.add_argument('--all-pokemon',action='store_true');s.add_argument('--max-sets',type=int,default=20)
    sub.add_parser('status')
    args=p.parse_args();db=Database(args.db);db.migrate()
    if args.command=='replay':result=replay_originals(db,args.documents)
    elif args.command=='seed':result=seed(db,args.fixture)
    elif args.command=='sync':
        scopes=[tuple(map(int,value.split(':'))) for value in args.set] if args.set else [(3,23228),(3,23237),(3,604),(3,630),(85,23599)]
        client=DailyClient(db,max_requests=args.max_requests)
        if args.all_pokemon:
            if not 1<=args.max_sets<=1000:p.error('max-sets must be 1..1000')
            # Category metadata is fetched once/day. Scope selection is local and
            # least-recently-synced first to permit bounded incremental expansion.
            with sync_lock(db):
                all_scopes=[]
                for cat in (3,85):
                    from .importers import decode
                    groups=decode(client.get(f'https://tcgcsv.com/tcgplayer/{cat}/groups')['payload'])['results']
                    all_scopes.extend((cat,x['groupId']) for x in groups)
                status={(int(r['category_id']),int(r['source_set_id'])):r['last_success_at'] or '' for r in db.sync_status() if r['provider']=='tcgtracking'}
                scopes=sorted(all_scopes,key=lambda key:(status.get(key,''),key))[:args.max_sets]
        result=synchronize(db,scopes,client=client)
    elif args.command=='status':result={'items':db.sync_status()}
    else:result=db.health()
    print(json_text(result),end='')


if __name__=='__main__':main()
