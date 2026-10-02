from fastapi import APIRouter,Depends,Query
from ..deps import get_db
router=APIRouter(prefix="/api/market-intelligence",tags=["Market Intelligence"])
@router.get("/health")
def health():return {"status":"ready","layer":"strength-relationship","tradingSignals":False}
@router.get("/matrix")
def matrix(db=Depends(get_db)):
 rows=db.execute("SELECT s.* FROM mi_strength_snapshot s JOIN (SELECT currency,timeframe,MAX(as_of) a FROM mi_strength_snapshot GROUP BY currency,timeframe)x ON x.currency=s.currency AND x.timeframe=s.timeframe AND x.a=s.as_of ORDER BY currency,timeframe").fetchall();return [dict(r) for r in rows]
@router.get("/strength/{currency}/history")
def strength_history(currency:str,timeframe:str=Query("H1"),limit:int=Query(96,ge=2,le=2000),db=Depends(get_db)):
 return [dict(r) for r in db.execute("SELECT * FROM mi_strength_snapshot WHERE currency=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",(currency.upper(),timeframe.upper(),limit)).fetchall()][::-1]
@router.get("/relationships")
def relationships(timeframe:str|None=None,state:str|None=None,db=Depends(get_db)):
 sql="SELECT r.* FROM mi_relationship_snapshot r JOIN (SELECT pair,timeframe,MAX(as_of) a FROM mi_relationship_snapshot GROUP BY pair,timeframe)x ON x.pair=r.pair AND x.timeframe=r.timeframe AND x.a=r.as_of WHERE 1=1";args=[]
 if timeframe:sql+=" AND r.timeframe=?";args.append(timeframe.upper())
 if state:sql+=" AND r.state=?";args.append(state.upper())
 sql+=" ORDER BY CASE r.inspection_priority WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'NORMAL' THEN 3 ELSE 4 END,r.abs_gap DESC"
 return [dict(r) for r in db.execute(sql,args).fetchall()]
@router.get("/relationships/{pair}/history")
def relationship_history(pair:str,timeframe:str=Query("H1"),limit:int=Query(96,ge=2,le=2000),db=Depends(get_db)):
 return [dict(r) for r in db.execute("SELECT * FROM mi_relationship_snapshot WHERE pair=? AND timeframe=? ORDER BY as_of DESC LIMIT ?",(pair.upper(),timeframe.upper(),limit)).fetchall()][::-1]
@router.get("/data-quality")
def quality(db=Depends(get_db)):
 return [dict(r) for r in db.execute("SELECT * FROM mi_data_quality ORDER BY symbol,timeframe").fetchall()]
