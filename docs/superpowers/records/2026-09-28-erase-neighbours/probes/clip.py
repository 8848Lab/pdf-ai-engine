# Does clipping the erase rect to the neighbours' bbox edges still remove the target and keep neighbours?
import pymupdf as fitz
for pitch in (14.4,13,12,11):
    d=fitz.open(); p=d.new_page()
    for i,t in enumerate(["ABOVE line gyp","TARGET line gyp","BELOW line gyp"]): p.insert_text((72,100+i*pitch),t,fontsize=12)
    sp={s["text"].split()[0]:fitz.Rect(s["bbox"]) for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]}
    t=sp["TARGET"]; r=fitz.Rect(t.x0,max(t.y0,sp["ABOVE"].y1),t.x1,min(t.y1,sp["BELOW"].y0))
    frac=r.height/t.height
    p.add_redact_annot(r,fill=(1,1,1)); p.apply_redactions(images=2,graphics=1,text=0)
    print(pitch,"kept band",round(frac,3),"->",[x for x in p.get_text().split("\n") if x])
