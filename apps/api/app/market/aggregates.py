def average_strength(points):
 vals=[p.value for p in points if p.quality!="MISSING"]
 return sum(vals)/len(vals) if vals else 0.0
def rank_currencies(points): return sorted(points,key=lambda p:p.value,reverse=True)
def matrix_health(points):
 if not points:return {"coverage":0,"fresh":0,"missing":0}
 fresh=sum(p.quality=="FRESH" for p in points); missing=sum(p.quality=="MISSING" for p in points)
 return {"coverage":round((len(points)-missing)/len(points)*100,1),"fresh":fresh,"missing":missing}
