def relationship_diagnostic(rows):
 counts={}
 for r in rows: counts[r.state]=counts.get(r.state,0)+1
 return {"total":len(rows),"states":counts,"high_priority":sum(r.inspection_priority in ("HIGH","CRITICAL") for r in rows),"note":"Close-strength relationships remain eligible for structural inspection."}
