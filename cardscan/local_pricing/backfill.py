"""Plan first; bounded resumable Pokémon-only generic TCGCSV archive import.

No downloads by default. A full-year run requires separate user authorization.
The archive contains all games; selective extraction saves disk, not bandwidth,
and a solid PPMd block may still require decoding non-Pokemon data.
"""
import argparse
from datetime import date,datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import re
from tempfile import TemporaryDirectory
import time
from urllib.request import Request,build_opener

from cardscan.references.transport import NoRedirects
from cardscan.structured_prices import json_text,price
from .database import Database,utc
from .importers import Importer,decode
from .sync import sync_lock

FIRST=date(2024,2,8)


def plan(days=365):
    if not 1<=days<=3650:raise ValueError('Days must be 1..3650')
    # Official docs say 2–4 MB/day, ALL categories. These are estimates, not HEAD measurements.
    rows_min=63623*days;rows_max=rows_min*2
    return {'days':days,'archive_bytes_estimate':[days*2_000_000,days*4_000_000],
            'archive_scope':'all games; no documented Pokemon-only download',
            'generic_observation_rows_estimate':[rows_min,rows_max],
            'database_bytes_estimate':[rows_min*1024,rows_max*2048],
            'working_disk_guidance':'For 365 days reserve ~40–150 GB including SQLite indexes, retained extracted price evidence, archives and WAL headroom; measure one real sample first.',
            'assumptions':['Current documented catalog sample: 32,882 English + 30,741 Japan products, not historical daily counts',
                           '1–2 generic subtypes/product, 1–2 KiB per stored observation including indexes (planning assumptions)',
                           'Archive 2–4 MB/day is documented, not a measured full-year total',
                           'Only category 3 and 85 price entries extracted; solid archive may decode other games',
                           'Processing time unmeasured for actual PPMd archives: allow hours, potentially a day; benchmark before bulk'],
            'time_model':'days * (archive_bytes / measured_download_rate + measured_PPMd_decode_time + measured_insert_time)',
            'downloads_executed':0,'requires_bulk_authorization':True}


def import_entry(db,day,category,group,payload,*,archive_hash,retrieved_at,member,archive_path):
    """Atomic member import, append-only generic history; unresolved exact IDs staged."""
    day=date.fromisoformat(day).isoformat()
    if date.fromisoformat(day)<FIRST or date.fromisoformat(day)>date.today():raise ValueError('Invalid archive date')
    if int(category) not in (3,85):raise ValueError('Pokemon categories only')
    rows=decode(payload)
    if rows.get('success') is not True or not isinstance(rows.get('results'),list):raise ValueError('Invalid historical price export')
    digest=sha256(payload).hexdigest();now=utc(retrieved_at)
    with db.transaction() as c:
        c.execute("INSERT INTO archive_imports(archive_date,archive_path,content_hash,status,last_attempt_at) VALUES(?,?,?,'importing',?) ON CONFLICT(archive_date) DO NOTHING",(day,str(archive_path),archive_hash,now))
        old=c.execute('SELECT content_hash FROM archive_members WHERE archive_date=? AND member=?',(day,member)).fetchone()
        if old:
            if old[0]!=digest:raise ValueError('Immutable archive member content changed')
            return {'rows':0,'unresolved':0,'already_imported':True}
        url=f'https://tcgcsv.com/archive/tcgplayer/prices-{day}.ppmd.7z#{member}'
        document=dict(url=url,payload=payload,retrieved_at=now,original_hash=archive_hash,kind='excerpt')
        docid=db.document(c,**document);count=0;unresolved=0;seen=set()
        for i,row in enumerate(rows['results']):
            source=str(row.get('productId'));subtype=row.get('subTypeName')
            if not source.isdigit() or not isinstance(subtype,str) or not subtype:raise ValueError('Historical product/subtype required')
            if (source,subtype) in seen:raise ValueError('Duplicate historical subtype')
            seen.add((source,subtype));amount=price(row.get('marketPrice'))
            if row.get('currency') not in (None,'USD'):raise ValueError('Currency mismatch')
            product=c.execute('''SELECT p.id FROM products p JOIN set_mappings m ON m.set_id=p.set_id
                                 WHERE p.tcgplayer_product_id=? AND m.provider='tcgcsv' AND m.category_id=? AND m.source_set_id=?''',(source,str(category),str(group))).fetchone()
            if not product:
                c.execute('INSERT INTO historical_unmatched VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING',
                          (day,str(category),str(group),source,subtype,amount,docid,json_text(row),'No exact catalog product/set join; historical generic reference retained for review'))
                unresolved+=1
            else:
                Importer(db)._observation(c,product[0],None,'tcgcsv',row.get('marketPrice'),None,document,docid,
                     f'/results/{i}',row,['historical_generic_reference','condition_unknown'],day,now,'historical_archive')
            count+=1
        c.execute('INSERT INTO archive_members VALUES(?,?,?,?,?)',(day,member,digest,now,count))
        c.execute('UPDATE archive_imports SET members_imported=members_imported+1,unresolved_rows=unresolved_rows+? WHERE archive_date=?',(unresolved,day))
        return {'rows':count,'unresolved':unresolved,'already_imported':False}


def download_archive(path,day,*,opener=None):
    """Immutable local files are never downloaded again. Atomic complete download."""
    if path.exists():
        metadata=path.with_suffix(path.suffix+'.json')
        if metadata.exists() and json.loads(metadata.read_text())['sha256']!=sha256(path.read_bytes()).hexdigest():
            raise ValueError('Cached archive hash mismatch; do not silently re-download')
        return False
    url=f'https://tcgcsv.com/archive/tcgplayer/prices-{day}.ppmd.7z'
    partial=path.with_suffix(path.suffix+'.part');path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with (opener or build_opener(NoRedirects())).open(Request(url,headers={'User-Agent':'CardScanHistoryResearch/1.0'}),timeout=30) as response:
            if response.status!=200 or response.geturl()!=url:raise ValueError('Unexpected archive response')
            total=0;digest=sha256()
            with partial.open('wb') as f:
                while chunk:=response.read(65536):
                    total+=len(chunk)
                    if total>16_000_000:raise ValueError('Archive exceeds configured 16 MB safety bound')
                    digest.update(chunk);f.write(chunk)
        if partial.read_bytes()[:6]!=b'7z\xbc\xaf\x27\x1c':raise ValueError('Not a 7z archive; no HTML/challenge handling')
        partial.replace(path)
        path.with_suffix(path.suffix+'.json').write_text(json.dumps({'url':url,'retrieved_at':utc(),'sha256':digest.hexdigest(),'bytes':total},indent=2))
        return True
    finally:
        partial.unlink(missing_ok=True)


def extract_members(path,day,directory):
    import py7zr
    pattern=re.compile(re.escape(day)+r'/(3|85)/(\d+)/prices$')
    with py7zr.SevenZipFile(path,'r') as archive:
        infos=archive.list();targets=[];total=0
        if len(infos)>50000:raise ValueError('Excessive archive member count')
        for info in infos:
            name=info.filename;p=PurePosixPath(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name:raise ValueError('Unsafe archive member')
            if getattr(info,'is_symlink',False):raise ValueError('Archive links refused')
            match=pattern.fullmatch(name)
            if match:
                total+=info.uncompressed
                if total>128_000_000:raise ValueError('Pokemon extracted size exceeds safety bound')
                targets.append((name,int(match[1]),int(match[2])))
        if not targets:raise ValueError('No documented Pokemon price paths in archive')
        archive.extract(path=directory,targets=[x[0] for x in targets])
    return targets


def run(db,start,end,directory,*,allow_download=False,max_archives=1):
    start=date.fromisoformat(start);end=date.fromisoformat(end)
    if start<FIRST or start>end or end>=date.today():raise ValueError('Use completed historical days since 2024-02-08')
    if not 1<=max_archives<=365:raise ValueError('max-archives must be 1..365')
    directory=Path(directory);out=[]
    with sync_lock(db):
        for offset in range((end-start).days+1):
            day=(start+timedelta(days=offset)).isoformat()
            with db.connect(readonly=True) as c:old=c.execute('SELECT * FROM archive_imports WHERE archive_date=?',(day,)).fetchone()
            if old and old['status']=='complete':continue
            if len(out)>=max_archives:break
            if old and old['status']=='failed' and old['last_attempt_at'][:10]==date.today().isoformat():
                out.append({'date':day,'status':'cooldown_until_next_day'});continue
            path=directory/f'prices-{day}.ppmd.7z';now=utc()
            with db.transaction() as c:
                c.execute("INSERT INTO archive_imports(archive_date,archive_path,status,last_attempt_at) VALUES(?,?,'attempting',?) ON CONFLICT(archive_date) DO UPDATE SET status='attempting',last_attempt_at=excluded.last_attempt_at,error=NULL",(day,str(path),now))
            try:
                downloaded=download_archive(path,day) if allow_download else False
                if not path.exists():raise ValueError('Archive absent locally; downloads disabled')
                digest=sha256(path.read_bytes()).hexdigest();members=0
                sidecar=path.with_suffix(path.suffix+'.json')
                if sidecar.exists() and json.loads(sidecar.read_text())['sha256']!=digest:raise ValueError('Cached archive hash mismatch')
                if old and old['content_hash'] and old['content_hash']!=digest:raise ValueError('Immutable archive content changed')
                with TemporaryDirectory(prefix='cardscan-pokemon-') as tmp:
                    for member,cat,group in extract_members(path,day,tmp):
                        payload=Path(tmp,member).read_bytes()
                        import_entry(db,day,cat,group,payload,archive_hash=digest,retrieved_at=now,member=member,archive_path=path)
                        members+=1
                with db.transaction() as c:
                    c.execute("UPDATE archive_imports SET status='complete',completed_at=?,content_hash=? WHERE archive_date=?",(utc(),digest,day))
                out.append({'date':day,'status':'complete','downloaded':downloaded,'members':members})
            except Exception as exc:
                with db.transaction() as c:c.execute("UPDATE archive_imports SET status='failed',error=? WHERE archive_date=?",(type(exc).__name__+': '+str(exc),day))
                out.append({'date':day,'status':'failed','error':str(exc)})
                break
    return out


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('plan');q.add_argument('--days',type=int,default=365)
    q=sub.add_parser('run');q.add_argument('--db',type=Path,default=Path('local-evidence/pricing.sqlite'))
    q.add_argument('--start',required=True);q.add_argument('--end',required=True);q.add_argument('--archives',type=Path,required=True)
    q.add_argument('--execute',action='store_true');q.add_argument('--download',action='store_true');q.add_argument('--max-archives',type=int,default=1)
    a=p.parse_args()
    if a.command=='plan':result=plan(a.days)
    else:
        if not a.execute:p.error('Review plan first; --execute required. Bulk downloads need separate user authorization.')
        db=Database(a.db);db.migrate();result=run(db,a.start,a.end,a.archives,allow_download=a.download,max_archives=a.max_archives)
    print(json_text(result),end='')


if __name__=='__main__':main()
