import pymupdf as fitz
for rot in (0,90,180,270):
    d=fitz.open(); p=d.new_page(width=612,height=792); p.set_rotation(rot)
    p.insert_text((100,700),"ORIGIN",fontsize=12,fontname="helv")   # no rotate/morph args
    s=[s for b in p.get_text("dict")["blocks"] for l in b["lines"] for s in l["spans"]][0]
    f=fitz.Font("helv")
    print(rot,"origin",tuple(round(v,2) for v in s["origin"]),"bbox",tuple(round(v,1) for v in s["bbox"]),"dir",l["dir"] if False else [l["dir"] for b in p.get_text("dict")["blocks"] for l in b["lines"]][0],"len",round(f.text_length("ORIGIN",12),2))
