from math import log
def log_returns(closes):
 out=[]
 for a,b in zip(closes,closes[1:]):
  if a>0 and b>0: out.append(log(b/a))
 return out
def normalized_return(closes):
 r=log_returns(closes)
 if not r:return 0.0
 vol=(sum(x*x for x in r)/len(r))**0.5
 return sum(r)/(vol*(len(r)**0.5)) if vol else 0.0
