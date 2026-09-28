import pymupdf as fitz
def page(pitch):
    d=fitz.open(); p=d.new_page(width=612,height=792)
    for i,t in enumerate(["ABOVE line gyp here","TARGET line gyp here","BELOW line gyp here"]):
        p.insert_text((72,100+i*pitch),t,fontsize=12)
    return d
for pitch in (18,16.5,15,14.4,13,12):
    d=page(pitch); p=d[0]
    sp=[s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]]
    tgt=[s for s in sp if s["text"].startswith("TARGET")][0]
    r=fitz.Rect(tgt["bbox"])
    ab=[s for s in sp if s["text"].startswith("ABOVE")][0]; be=[s for s in sp if s["text"].startswith("BELOW")][0]
    p.add_redact_annot(r); p.apply_redactions(images=0,graphics=0,text=0)
    left=p.get_text().split("\n")
    print(f"pitch {pitch}: tgt bbox y {r.y0:.2f}-{r.y1:.2f}; above y1 {ab['bbox'][3]:.2f}; below y0 {be['bbox'][1]:.2f} -> remaining {left}")
# rule probe: does a char get removed if its bbox overlaps the rect by a sliver?
for sliver in (0.1,1,3,6):
    d=fitz.open(); p=d.new_page(); p.insert_text((72,100),"WORD",fontsize=12)
    s=[s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
    y1=s["bbox"][3]; r=fitz.Rect(60,y1-sliver,200,y1+20)
    p.add_redact_annot(r); p.apply_redactions(images=0,graphics=0,text=0)
    print("bottom sliver",sliver,"->",repr(p.get_text().strip()))
