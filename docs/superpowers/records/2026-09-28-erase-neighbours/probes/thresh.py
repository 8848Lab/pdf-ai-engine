import pymupdf as fitz
def run(size, sliver, side):
    d=fitz.open(); p=d.new_page(); p.insert_text((72,100),"WORD",fontsize=size)
    s=[s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
    x0,y0,x1,y1=s["bbox"]
    r={"bottom":fitz.Rect(60,y1-sliver,300,y1+20),"top":fitz.Rect(60,y0-20,300,y0+sliver),"left":fitz.Rect(x0-20,y0-5,x0+sliver,y1+5)}[side]
    p.add_redact_annot(r); p.apply_redactions(images=0,graphics=0,text=0)
    return p.get_text().strip()
for size in (12,24):
  for side in ("bottom","top"):
    h=None
    lo,hi=0.0,size*1.5
    for _ in range(30):
        m=(lo+hi)/2
        if run(size,m,side)=="WORD": lo=m
        else: hi=m
    d=fitz.open(); p=d.new_page(); p.insert_text((72,100),"WORD",fontsize=size)
    s=[s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
    print(size,side,"threshold overlap",round(hi,3),"bbox h",round(s["bbox"][3]-s["bbox"][1],3),"ratio",round(hi/(s["bbox"][3]-s["bbox"][1]),3))
print("left 1ch:",[ (sl,run(12,sl,"left")) for sl in (1,2,3,4,5)])
