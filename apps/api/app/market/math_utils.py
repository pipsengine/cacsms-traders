from math import sqrt
def mean(xs): return sum(xs)/len(xs) if xs else 0.0
def stdev(xs):
 if len(xs)<2:return 0.0
 m=mean(xs); return sqrt(sum((x-m)**2 for x in xs)/(len(xs)-1))
def clamp(v,lo,hi): return max(lo,min(hi,v))
def zscore(v,xs):
 s=stdev(xs); return 0.0 if not s else (v-mean(xs))/s
def linear_slope(xs):
 n=len(xs)
 if n<2:return 0.0
 xm=(n-1)/2; ym=mean(xs); den=sum((i-xm)**2 for i in range(n))
 return sum((i-xm)*(v-ym) for i,v in enumerate(xs))/den if den else 0.0
