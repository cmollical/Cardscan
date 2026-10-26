"""Controlled CLI-only set sync: persisted daily endpoint budget, WAL readers, flock.

No automatic retries or hosted scheduler. Cached original responses are local
research evidence. Each daily snapshot is appended, including unchanged values; same-day replay is idempotent.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta
from hashlib import sha256
import fcntl
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

from cardscan.references.transport import NoRedirects
from .database import utc
from .importers import decode, Importer


@contextmanager
def sync_lock(db):
    lock=Path(str(db.path)+'.sync.lock')
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another synchronization is running')
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)


class RequestBudgetExceeded(ValueError):
    pass


class DailyClient:
    def __init__(self,db,*,now=None,max_requests=40,opener=None,sleeper=time.sleep):
        if not 1<=max_requests<=1000:raise ValueError('Request budget must be 1..1000')
        self.db=db;self.now=utc(now);self.max_requests=max_requests;self.requests=0
        self.opener=opener or build_opener(NoRedirects());self.sleep=sleeper

    def get(self,url):
        p=urlsplit(url)
        allowed=((p.hostname=='tcgcsv.com' and (p.path=='/last-updated.txt' or
                   re.fullmatch(r'/tcgplayer/(?:categories|\d+/groups|\d+/\d+/(?:products|prices))',p.path)))
                 or (p.hostname=='openapi.tcgtracking.com' and re.fullmatch(r'/v1/(?:categories|\d+/sets(?:/\d+/(?:cards|skus))?)',p.path)))
        if not allowed or p.scheme!='https' or p.query or p.fragment or p.username or p.password or p.port not in (None,443):
            raise ValueError('Endpoint not approved')
        with self.db.connect() as c:
            old=c.execute('SELECT * FROM endpoints WHERE url=?',(url,)).fetchone()
            old=dict(old) if old else {}
            cached=c.execute('SELECT * FROM documents WHERE id=?',(old.get('document_id'),)).fetchone()
        if old.get('next_attempt_at') and self.now<old['next_attempt_at']:
            if old.get('status')=='success' and cached:
                return self._document(cached)
            raise ValueError('Endpoint retry not eligible until '+old['next_attempt_at'])
        if self.requests>=self.max_requests:raise RequestBudgetExceeded('Sync request budget exhausted')
        next_time=(datetime.fromisoformat(self.now)+timedelta(hours=24)).isoformat()
        # Persist attempt BEFORE network I/O. Crash/restart cannot bypass cooldown.
        with self.db.transaction() as c:
            c.execute('''INSERT INTO endpoints(url,last_attempt_at,next_attempt_at,request_count,status) VALUES(?,?,?,1,'attempting')
                         ON CONFLICT(url) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,next_attempt_at=excluded.next_attempt_at,
                         request_count=request_count+1,status='attempting' ''',(url,self.now,next_time))
        self.requests+=1;self.sleep(.15)
        headers={'User-Agent':'CardScanLocalResearch/1.0','Accept':'application/json,text/plain;q=0.8'}
        if old.get('etag'):headers['If-None-Match']=old['etag']
        if old.get('last_modified'):headers['If-Modified-Since']=old['last_modified']
        try:
            try:
                with self.opener.open(Request(url,headers=headers),timeout=20) as response:
                    if response.status!=200 or response.geturl()!=url:raise ValueError('Unexpected response URL/status')
                    kind=response.headers.get_content_type()
                    if kind not in ({'text/plain'} if p.path=='/last-updated.txt' else {'application/json'}):
                        raise ValueError('Expected export content; HTML/challenge refused')
                    payload=response.read(5_000_001)
                    if len(payload)>5_000_000:raise ValueError('Response too large')
                    if p.path!='/last-updated.txt':
                        if not isinstance(decode(payload),dict):raise ValueError('Object export required')
                    etag=response.headers.get('ETag');modified=response.headers.get('Last-Modified')
            except HTTPError as exc:
                if exc.code==429:
                    from email.utils import parsedate_to_datetime
                    retry=exc.headers.get('Retry-After','')
                    try:
                        candidate=(datetime.fromisoformat(self.now)+timedelta(seconds=int(retry))).isoformat() if retry.isdigit() else utc(parsedate_to_datetime(retry).isoformat())
                        with self.db.transaction() as c:c.execute('UPDATE endpoints SET next_attempt_at=MAX(next_attempt_at,?) WHERE url=?',(candidate,url))
                    except (ValueError,TypeError,OverflowError):pass
                if exc.code==304 and cached:
                    with self.db.transaction() as c:
                        c.execute("UPDATE endpoints SET status='success',error=NULL,last_success_at=? WHERE url=?",(self.now,url))
                        c.execute('UPDATE documents SET last_checked_at=? WHERE id=?',(self.now,cached['id']))
                    return self._document(cached)
                raise
            with self.db.transaction() as c:
                docid=self.db.document(c,url=url,payload=payload,retrieved_at=self.now)
                c.execute("UPDATE endpoints SET document_id=?,status='success',error=NULL,last_success_at=?,etag=?,last_modified=? WHERE url=?",(docid,self.now,etag,modified,url))
            return dict(url=url,payload=payload,retrieved_at=self.now,kind='original',original_hash=sha256(payload).hexdigest())
        except Exception as exc:
            with self.db.transaction() as c:
                c.execute("UPDATE endpoints SET status='failed',error=? WHERE url=?",(type(exc).__name__+': '+str(exc) if isinstance(exc,ValueError) else type(exc).__name__,url))
            raise ValueError('Export request failed: '+type(exc).__name__+(': '+str(exc) if isinstance(exc,ValueError) else '')) from exc

    @staticmethod
    def _document(row):
        return dict(url=row['url'],payload=bytes(row['payload']),retrieved_at=row['retrieved_at'],
                    kind=row['payload_kind'],original_hash=row['original_source_hash'])


def synchronize(db,scopes,*,client=None,resume=False,progress=None,provider_scopes=None):
    """scopes are exact (category,group) pairs; sets imported atomically per provider.

    TCGCSV global marker avoids unchanged price downloads; endpoint cooldowns
    and conditional requests independently enforce daily collection guidance.
    """
    client=client or DailyClient(db)
    outcomes=[];importer=Importer(db)
    with sync_lock(db):
        metadata={};csv_ready=True
        try:
            marker=client.get('https://tcgcsv.com/last-updated.txt')['payload'].decode().strip()
            for cat in sorted({int(x[0]) for x in scopes}):
                doc=client.get(f'https://tcgcsv.com/tcgplayer/{cat}/groups')
                metadata[cat]={str(x['groupId']):x for x in decode(doc['payload'])['results']}
        except ValueError:
            csv_ready=False
        # Exact set scopes deduplicate requests. No individual-card HTTP calls.
        for category,group in sorted(set((int(a),int(b)) for a,b in scopes)):
            if category not in (3,85):raise ValueError('Pokemon categories only')
            for provider in ('tcgcsv','tcgtracking'):
                if provider_scopes is not None and provider not in provider_scopes.get((category,group),()):continue
                if resume:
                    with db.connect(readonly=True) as c:
                        prior=c.execute('SELECT status,last_success_at FROM sync_state WHERE provider=? AND category_id=? AND source_set_id=?',(provider,str(category),str(group))).fetchone()
                    if prior and prior['status']=='success' and prior['last_success_at'] and prior['last_success_at'][:10]==client.now[:10]:
                        outcomes.append({'provider':provider,'category':category,'source_set_id':group,'status':'checkpoint_skipped'});continue
                before=client.requests
                with db.transaction() as c:
                    c.execute("INSERT INTO sync_state(provider,category_id,source_set_id,last_attempt_at,status) VALUES(?,?,?,?,'attempting') ON CONFLICT(provider,category_id,source_set_id) DO UPDATE SET last_attempt_at=excluded.last_attempt_at,status='attempting'",(provider,str(category),str(group),client.now))
                try:
                    if provider=='tcgcsv' and not csv_ready:raise ValueError('Catalog metadata/update marker unavailable')
                    suffixes=('products','prices') if provider=='tcgcsv' else ('cards','skus')
                    root=(f'https://tcgcsv.com/tcgplayer/{category}/{group}' if provider=='tcgcsv'
                          else f'https://openapi.tcgtracking.com/v1/{category}/sets/{group}')
                    with db.connect(readonly=True) as c:
                        prior=c.execute('SELECT export_marker FROM sync_state WHERE provider=? AND category_id=? AND source_set_id=?',(provider,str(category),str(group))).fetchone()
                        cached=[c.execute('SELECT d.* FROM endpoints e JOIN documents d ON d.id=e.document_id WHERE e.url=?',(root+'/'+k,)).fetchone() for k in suffixes]
                    if provider=='tcgcsv' and prior and prior[0]==marker and all(cached):
                        docs={k:DailyClient._document(d) for k,d in zip(suffixes,cached)}
                    else:
                        docs={k:client.get(root+'/'+k) for k in suffixes}
                    bindings=json.loads((Path(__file__).resolve().parents[2]/'experiments/structured-prices/targets.json').read_text())['bindings']
                    aliases=[b['target']['set_name'] for b in bindings if (b['category_id'],b['set_id'])==(category,group)]
                    result=importer.import_set(provider,category,group,docs,aliases=aliases,set_metadata=metadata.get(category,{}).get(str(group)),snapshot_date=client.now[:10],captured_at=client.now,capture_kind='daily_snapshot')
                    with db.transaction() as c:
                        c.execute("UPDATE sync_state SET last_success_at=?,status='success',request_count=request_count+? WHERE provider=? AND category_id=? AND source_set_id=?",(client.now,client.requests-before,provider,str(category),str(group)))
                    if provider=='tcgcsv':
                        with db.transaction() as c:c.execute('UPDATE sync_state SET export_marker=? WHERE provider=? AND category_id=? AND source_set_id=?',(marker,provider,str(category),str(group)))
                    outcomes.append({**result,'status':'success','category':category,'source_set_id':group})
                    if progress:progress(outcomes[-1])
                except (ValueError,KeyError) as exc:
                    if isinstance(exc,RequestBudgetExceeded):
                        with db.transaction() as c:
                            c.execute("UPDATE sync_state SET status='deferred_budget',errors_json=?,retry_after=NULL,request_count=request_count+? WHERE provider=? AND category_id=? AND source_set_id=?",(json.dumps([str(exc)]),client.requests-before,provider,str(category),str(group)))
                        outcomes.append({'provider':provider,'category':category,'source_set_id':group,'status':'deferred_budget'})
                        if progress:progress(outcomes[-1])
                        return {'sets':outcomes,'requests':client.requests,'status':'budget_exhausted','resume_required':True}
                    retry=(datetime.fromisoformat(client.now)+timedelta(hours=24)).isoformat()
                    with db.transaction() as c:
                        c.execute("UPDATE sync_state SET status='failed',errors_json=?,retry_after=?,request_count=request_count+? WHERE provider=? AND category_id=? AND source_set_id=?",(json.dumps([str(exc)]),retry,client.requests-before,provider,str(category),str(group)))
                    outcomes.append({'provider':provider,'category':category,'source_set_id':group,'status':'failed','error':str(exc)})
                    if progress:progress(outcomes[-1])
    return {'sets':outcomes,'requests':client.requests,'status':'success' if all(x['status'] in ('success','checkpoint_skipped') for x in outcomes) else 'partial_failure'}
