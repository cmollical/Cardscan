"""Metadata-only catalog discovery and offline sync planning; no card exports."""
import json
from .importers import decode


def cached_document(db,url):
    from .sync import DailyClient
    with db.connect(readonly=True) as c:
        row=c.execute('SELECT d.* FROM endpoints e JOIN documents d ON d.id=e.document_id WHERE e.url=?',(url,)).fetchone()
    if row is None:raise ValueError('Discovery metadata not cached: '+url)
    return DailyClient._document(row)


def discover(db,*,client=None):
    getter=client.get if client else lambda u:cached_document(db,u)
    categories=[];scopes=[];documents=[]
    for cat,label in [(3,'english_catalog'),(85,'japanese_catalog')]:
        csv=getter(f'https://tcgcsv.com/tcgplayer/{cat}/groups')
        tt=getter(f'https://openapi.tcgtracking.com/v1/{cat}/sets')
        a={int(x['groupId']):x for x in decode(csv['payload'])['results']}
        b={int(x['id']):x for x in decode(tt['payload'])['sets']}
        categories.append({'category':cat,'catalog_scope':label,'tcgcsv_sets':len(a),'tcgtracking_sets':len(b),
                           'shared_set_ids':len(a.keys()&b.keys()),'products_reported':sum(x.get('product_count',0) for x in b.values()),
                           'skus_reported':sum(x.get('sku_count',0) for x in b.values())})
        for group in sorted(a.keys()|b.keys()):
            scopes.append({'category':cat,'group':group,'name':(a.get(group) or b[group])['name'],
                           'providers':(['tcgcsv'] if group in a else [])+(['tcgtracking'] if group in b else []),
                           'products_reported':b.get(group,{}).get('product_count'),
                           'skus_reported':b.get(group,{}).get('sku_count')})
        documents.extend({'url':d['url'],'retrieved_at':d['retrieved_at'],'source_hash':d['original_hash']} for d in (csv,tt))
    return {'mode':'metadata_requests_only' if client else 'offline_cached_metadata','categories':categories,
            'sets':scopes,'documents':documents,'new_requests':client.requests if client else 0,
            'full_export_request_estimate':sum(2*len(s['providers']) for s in scopes),
            'notes':['Provider counts are reported metadata, not independently counted downloaded cards.',
                     'Provider category/set IDs are joined exactly; differing names are not fuzzy matched.',
                     'No full catalog download was performed.']}


def select_scopes(db,discovery,*,max_sets=20,explicit=None):
    if not 1<=max_sets<=1000:raise ValueError('max_sets must be 1..1000')
    if explicit is not None:
        selected=sorted(set((int(a),int(b)) for a,b in explicit))
        if len(selected)>max_sets:raise ValueError('Explicit scope exceeds max_sets')
    else:
        status={(int(r['category_id']),int(r['source_set_id'])):r['last_success_at'] or '' for r in db.sync_status() if r['provider']=='tcgtracking'}
        selected=sorted(((x['category'],x['group']) for x in discovery['sets']),key=lambda x:(status.get(x,''),x))[:max_sets]
    if any(cat not in (3,85) or group<=0 for cat,group in selected):raise ValueError('Only explicit Pokemon category/set IDs allowed')
    by_id={(x['category'],x['group']):x for x in discovery['sets']}
    return {'dry_run':True,'selected_sets':[by_id.get(x,{'category':x[0],'group':x[1],'providers':['tcgcsv','tcgtracking'],'metadata_unknown':True}) for x in selected],
            'maximum_export_requests':sum(2*len(by_id.get(x,{'providers':[1,2]})['providers']) for x in selected),
            'network_requests':0,'imports':0,'scope_count':len(selected)}
