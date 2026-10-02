WEIGHTS={"ROTATION":5,"TRANSITIONING":5,"DIVERGENCE":4,"EQUILIBRIUM":4,"CONVERGENCE":3,"UNCERTAIN":1}
def inspection_score(points):
 score=0; reasons=[]
 for p in points:
  score+=WEIGHTS.get(p.state,0)
  if p.inspection_priority=="HIGH":score+=2
  reasons.extend(p.reason_codes)
 # reward hierarchical disagreement: equilibrium HTF + rotation/divergence LTF is intentionally interesting
 states=[p.state for p in points]
 if "EQUILIBRIUM" in states and any(s in states for s in ("ROTATION","DIVERGENCE","TRANSITIONING")):
  score+=8; reasons.append("HTF_LTF_RELATIONSHIP_TRANSITION")
 return {"score":score,"priority":"CRITICAL" if score>=25 else "HIGH" if score>=16 else "NORMAL" if score>=8 else "LOW","reasons":sorted(set(reasons))}
