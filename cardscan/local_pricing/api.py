"""TallyBinder local pricing and personal intake API. Never syncs on requests."""
import os
import sqlite3
from fastapi.responses import JSONResponse
from typing import Literal
from fastapi import FastAPI, Query, Path, HTTPException

from .database import Database
from .lookup import Lookup


def create_app(path=None,*,media_root=None,vision_settings=None,vision_provider=None):
    db=Database(path or os.environ.get('TALLYBINDER_DB',os.environ.get('CARDSCAN_PRICING_DB','local-evidence/pricing.sqlite')))
    lookup=Lookup(db)
    app=FastAPI(title='TallyBinder API',version='1.0',
                description='Pokémon catalog, auditable market references, card intake and personal inventory. AI results require human confirmation.')

    @app.exception_handler(sqlite3.Error)
    async def database_error(request,exc):
        return JSONResponse(status_code=503,content={'detail':{'code':'database_unavailable'}})

    @app.get('/health')
    def health():
        try:
            result=db.health()
            if result['status']!='ok':raise ValueError('Database migration required')
            return result
        except Exception:raise HTTPException(503,detail={'code':'database_unavailable'})

    @app.get('/cards/search')
    def search(q:str=Query('',max_length=200),game:Literal['pokemon']='pokemon',limit:int=Query(25,ge=1,le=100),offset:int=Query(0,ge=0),set_name:str|None=Query(None,max_length=200),number:str|None=Query(None,max_length=40),language:str|None=Query(None,max_length=50),tcgplayer_product_id:int|None=Query(None,gt=0)):
        return lookup.search(q,game=game,limit=limit,offset=offset,set_name=set_name,number=number,language=language,tcgplayer_product_id=tcgplayer_product_id)

    @app.get('/cards/product/{tcgplayer_product_id}')
    def product(tcgplayer_product_id:int):
        result=lookup.product(tcgplayer_product_id)
        if result is None:raise HTTPException(404,detail={'code':'product_not_found'})
        return result

    @app.get('/cards/{card_id}')
    def card(card_id:int):
        result=lookup.card(card_id)
        if result is None:raise HTTPException(404,detail={'code':'card_not_found'})
        return result

    @app.get('/prices/lookup')
    def price_lookup(*,game:Literal['pokemon'],set_name:str=Query(min_length=1,max_length=200),
                     number:str=Query(pattern=r'^[A-Za-z]*\d+/[A-Za-z]*\d+$',max_length=30),language:str=Query(min_length=1,max_length=50),
                     finish:Literal['holo','non-holo','reverse holo'],condition:Literal['NM','LP','MP','HP','DMG'],
                     graded:bool,edition:Literal['standard','unlimited','first edition','shadowless']|None=None,tcgplayer_product_id:int|None=Query(None,gt=0)):
        return lookup.lookup(game=game,set_name=set_name,number=number,language=language,edition=edition,finish=finish,condition=condition,graded=graded,tcgplayer_product_id=tcgplayer_product_id)

    @app.get('/prices/sku/{provider_sku_id}')
    def sku_lookup(provider_sku_id:str=Path(pattern=r'^\d+$'),provider:Literal['tcgtracking']='tcgtracking'):
        return lookup.lookup_sku(provider,provider_sku_id)

    @app.get('/prices/history/{sku_id}')
    def history(sku_id:int,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),order:Literal['asc','desc']='desc'):
        result=lookup.history(sku_id,limit=limit,offset=offset,order=order)
        if result is None:raise HTTPException(404,detail={'code':'sku_not_found'})
        return result

    @app.get('/prices/product-history/{card_id}')
    def product_history(card_id:int,subtype:str=Query(min_length=1,max_length=100),limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),order:Literal['asc','desc']='desc'):
        result=lookup.generic_history(card_id,subtype,limit=limit,offset=offset,order=order)
        if result is None:raise HTTPException(404,detail={'code':'card_not_found'})
        return result

    @app.get('/prices/comparisons/{sku_id}')
    def comparisons(sku_id:int):
        if lookup.history(sku_id,limit=1) is None:raise HTTPException(404,detail={'code':'sku_not_found'})
        return lookup.comparisons(sku_id=sku_id)

    @app.get('/prices/product-comparisons/{card_id}')
    def product_comparisons(card_id:int,subtype:str=Query(min_length=1,max_length=100)):
        if lookup.card(card_id) is None:raise HTTPException(404,detail={'code':'card_not_found'})
        return lookup.comparisons(card_id=card_id,subtype=subtype)

    @app.get('/sync/status')
    def sync_status():
        return {'items':db.sync_status(),'freshness_basis':'set export, not individual sale age','commercial_rights_established':False}

    from cardscan.app.routes import register
    from cardscan.app.limits import BodyLimits
    register(app,db,media_root=media_root,settings=vision_settings,vision_provider=vision_provider)
    app.add_middleware(BodyLimits)
    from cardscan.app.security import configure
    configure(app)
    return app


app=create_app()
