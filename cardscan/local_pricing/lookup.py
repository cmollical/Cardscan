"""Indexed read-only local lookups. No provider imports or network I/O."""
from datetime import datetime, timezone
import json

from .database import utc
from .importers import canonical_number


def page(rows):
    return [dict(r) for r in rows]


class Lookup:
    def __init__(self, db, *, max_age_hours=48):
        if max_age_hours <= 0:raise ValueError('Positive freshness window required')
        self.db,self.max_age_hours=db,max_age_hours

    def search(self, q='', *, game='pokemon', limit=25, offset=0):
        if not 1<=limit<=100 or offset<0:raise ValueError('Invalid pagination')
        # Substring catalog search is discovery, never an exact identity join.
        with self.db.connect(readonly=True) as c:
            where='WHERE g.name=? AND instr(lower(p.name),lower(?))>0'
            total=c.execute('SELECT COUNT(*) FROM products p JOIN games g ON g.id=p.game_id '+where,(game,q)).fetchone()[0]
            items=page(c.execute('SELECT p.*,s.name AS set_name FROM products p JOIN games g ON g.id=p.game_id JOIN sets s ON s.id=p.set_id '+where+' ORDER BY p.id LIMIT ? OFFSET ?',(game,q,limit,offset)))
            return {'items':items,'total':total,'limit':limit,'offset':offset}

    def card(self, card_id):
        with self.db.connect(readonly=True) as c:
            r=c.execute('SELECT p.*,s.name AS set_name,g.name AS game FROM products p JOIN sets s ON s.id=p.set_id JOIN games g ON g.id=p.game_id WHERE p.id=?',(card_id,)).fetchone()
            if not r:return None
            result=dict(r)
            result['variants']=page(c.execute('SELECT * FROM skus WHERE product_id=? ORDER BY provider,provider_sku_id',(card_id,)))
            result['generic_references']=page(c.execute("SELECT * FROM observations WHERE product_id=? AND price_type='generic_market_reference' ORDER BY snapshot_date DESC,retrieved_at DESC,id DESC",(card_id,)))
            return result

    def history(self, sku_id, *, limit=100, offset=0):
        if not 1<=limit<=500 or offset<0:raise ValueError('Invalid pagination')
        with self.db.connect(readonly=True) as c:
            if not c.execute('SELECT 1 FROM skus WHERE id=?',(sku_id,)).fetchone():return None
            return {'sku_id':sku_id,'items':page(c.execute('SELECT * FROM observations WHERE sku_id=? ORDER BY snapshot_date DESC,retrieved_at DESC,id DESC LIMIT ? OFFSET ?',(sku_id,limit,offset))),
                    'total':c.execute('SELECT COUNT(*) FROM observations WHERE sku_id=?',(sku_id,)).fetchone()[0], 'limit':limit,'offset':offset}

    def _candidate(self,c,row,now):
        result=dict(row)
        for key in ['provenance_json','completeness_json','raw_variant_json']:
            result[key.removesuffix('_json')]=json.loads(result.pop(key))
        latest=c.execute("SELECT * FROM observations WHERE sku_id=? AND price_type='sku_market_reference' ORDER BY snapshot_date DESC,retrieved_at DESC,id DESC LIMIT 1",(row['id'],)).fetchone()
        result['observation']=dict(latest) if latest else None
        warnings=[];age=None
        if latest:
            warnings=json.loads(latest['warnings_json'])
            basis=latest['source_updated_at'] or latest['retrieved_at']
            age=(datetime.fromisoformat(now)-datetime.fromisoformat(basis)).total_seconds()/3600
            result['observation']['missing_fields']=json.loads(latest['missing_json'])
        result['warnings']=warnings+['provider_reported_reference_not_verified_transaction','shipping_and_tax_basis_unconfirmed']
        if row['edition'] is None:result['warnings'].append('edition_unknown')
        result['identity_complete']=all(result['completeness'].values())
        result['freshness']={'age_hours':age,'max_age_hours':self.max_age_hours,
                             'basis':'set_export_update_or_retrieval','individual_price_age_known':False,
                             'stale':age is None or age>self.max_age_hours or age<0}
        return result

    def _result(self,c,rows,now,*,by_sku=False,requested=None):
        result={'status':'not_found','requested_identity':requested,'market_price':None,'currency':None,
                'price_type':None,'candidates':[],'approved_inventory_price':False}
        if not rows:return result
        candidates=[self._candidate(c,r,now) for r in rows]
        result['candidates']=candidates
        if len({x['provider'] for x in candidates})>1:
            amounts={x['observation']['market_price'] for x in candidates if x['observation'] and x['observation']['market_price'] is not None}
            result['warnings']=['conflicting_provider_references' if len(amounts)>1 else 'multiple_provider_references_not_combined']
        unknown=any(any(v is None for v in [r['condition'],r['language'],r['edition'],r['finish'],r['graded']]) for r in rows)
        if len(rows)>1 or (unknown and not by_sku):
            result['status']='ambiguous_match';return result
        r=candidates[0];obs=r['observation']
        result.update(card_id=r['product_id'],sku_id=r['id'],provider_sku_id=r['provider_sku_id'],
                      tcgplayer_product_id=r['tcgplayer_product_id'],condition=r['condition'],language=r['language'],
                      edition=r['edition'],finish=r['finish'],graded=bool(r['graded']) if r['graded'] is not None else None,
                      card_name=r['name'],collector_number=r['collector_number'],set_name=r['set_name'],
                      source=r['provider'],identity_complete=r['identity_complete'],warnings=r['warnings'],freshness=r['freshness'])
        if not r['active'] or obs is None or obs['market_price'] is None:
            result['status']='price_unavailable';return result
        result.update(market_price=obs['market_price'],currency=obs['currency'],price_type=obs['price_type'],
                      source_updated_at=obs['source_updated_at'],retrieved_at=obs['retrieved_at'],source_url=obs['source_url'],
                      evidence_document_id=obs['document_id'],snapshot_date=obs['snapshot_date'],captured_at=obs['captured_at'],capture_kind=obs['capture_kind'],status='stale_price' if r['freshness']['stale'] else 'exact_match')
        return result

    def lookup_sku(self, provider, provider_sku_id, *, now=None):
        """Exact provider-ID retrieval; does not assert missing printing attributes."""
        with self.db.connect(readonly=True) as c:
            rows=c.execute(self._select()+ ' WHERE v.provider=? AND v.provider_sku_id=?',(provider,str(provider_sku_id))).fetchall()
            return self._result(c,rows,utc(now),by_sku=True,requested={'provider':provider,'provider_sku_id':str(provider_sku_id)})

    @staticmethod
    def _select():
        return '''SELECT v.*,p.name,p.collector_number,p.tcgplayer_product_id,s.name AS set_name
                  FROM skus v JOIN products p ON p.id=v.product_id JOIN sets s ON s.id=p.set_id JOIN games g ON g.id=p.game_id'''

    def lookup(self, *, game, set_name, number, language, edition, finish, condition, graded, now=None, tcgplayer_product_id=None):
        if condition not in {'NM','LP','MP','HP','DMG'} or type(graded) is not bool:raise ValueError('Explicit condition and grading required')
        if not all(isinstance(v,str) and v.strip() for v in (game,set_name,number,language,finish)):raise ValueError('Identity fields required')
        identity=dict(game=game,set_name=set_name,number=number,language=language,edition=edition,finish=finish,condition=condition,graded=graded)
        filters=['g.name=?','p.collector_number=?','EXISTS(SELECT 1 FROM set_aliases a WHERE a.set_id=s.id AND a.alias=?)']
        values=[game.casefold(),canonical_number(number),set_name.casefold()]
        for column,value in [('language',language.casefold()),('finish',finish.casefold()),('condition',condition),('graded',int(graded))]:
            filters.append(f'(v.{column}=? OR v.{column} IS NULL)');values.append(value)
        if tcgplayer_product_id is not None:
            filters.append('p.tcgplayer_product_id=?');values.append(str(tcgplayer_product_id))
        if edition is not None:
            filters.append('(v.edition=? OR v.edition IS NULL)');values.append(edition.casefold())
        with self.db.connect(readonly=True) as c:
            rows=c.execute(self._select()+' WHERE '+' AND '.join(filters)+' ORDER BY v.id',values).fetchall()
            result=self._result(c,rows,utc(now),requested=identity)
            if edition is None and rows:
                result.update(status='ambiguous_match',market_price=None,currency=None)
            return result

    def generic_history(self,card_id,subtype,*,limit=100,offset=0):
        if not 1<=limit<=500 or offset<0:raise ValueError('Invalid pagination')
        with self.db.connect(readonly=True) as c:
            if not c.execute('SELECT 1 FROM products WHERE id=?',(card_id,)).fetchone():return None
            params=(card_id,subtype)
            where=" WHERE product_id=? AND subtype=? AND price_type='generic_market_reference'"
            return {'card_id':card_id,'subtype':subtype,'condition':None,'price_type':'generic_market_reference',
                    'items':page(c.execute('SELECT * FROM observations'+where+' ORDER BY snapshot_date DESC,id DESC LIMIT ? OFFSET ?',(*params,limit,offset))),
                    'total':c.execute('SELECT COUNT(*) FROM observations'+where,params).fetchone()[0], 'limit':limit,'offset':offset}

    def comparisons(self,*,sku_id=None,card_id=None,subtype=None):
        from datetime import date,timedelta
        from decimal import Decimal
        if (sku_id is None)==(card_id is None) or (card_id is not None and not subtype):raise ValueError('Select one exact history series')
        where='sku_id=?' if sku_id is not None else "product_id=? AND subtype=? AND price_type='generic_market_reference'"
        params=(sku_id,) if sku_id is not None else (card_id,subtype)
        with self.db.connect(readonly=True) as c:
            latest=c.execute('SELECT * FROM observations WHERE '+where+' ORDER BY snapshot_date DESC,id DESC LIMIT 1',params).fetchone()
            result={'comparisons':{},'interpolation':False,'latest_snapshot_date':latest['snapshot_date'] if latest else None}
            for days in (7,30,90):
                past_date=(date.fromisoformat(latest['snapshot_date'])-timedelta(days=days)).isoformat() if latest else None
                old=c.execute('SELECT * FROM observations WHERE '+where+' AND snapshot_date=? ORDER BY id DESC LIMIT 1',(*params,past_date)).fetchone() if past_date else None
                change=None
                if latest and old and latest['market_price'] and old['market_price'] and latest['currency']==old['currency']:
                    change=format((Decimal(latest['market_price'])/Decimal(old['market_price'])-1)*100,'f')
                result['comparisons'][str(days)]={'snapshot_date':past_date,'percentage_change':change,'status':'available' if change is not None else 'insufficient_history'}
            return result
