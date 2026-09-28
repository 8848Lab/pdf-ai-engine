import sys, time; sys.path.insert(0,"/home/user/pdf-ai-engine")
import pymupdf as fitz
from engine.parser import parse
from engine.operations import replace_text
from engine.export import export
def spans(page):
    out=[]
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines",[]):
            for s in l["spans"]:
                if s["text"].strip(): out.append((s["text"],round(s["size"],2),tuple(round(v,1) for v in s["bbox"]),round(s["origin"][1],2)))
    return out
# form: label + value inside a box, box right edge at 400
d=fitz.open(); p=d.new_page(width=612,height=792)
p.insert_text((72,100),"Student Name:",fontsize=12,fontname="helv")
p.draw_rect(fitz.Rect(160,86,400,106),color=(0,0,0),width=0.8)
p.insert_text((164,100),"Jo Lee",fontsize=14,fontname="helv")
p.insert_text((72,140),"Date: 2026-01-01",fontsize=12)
# paragraph
lines=["The quick brown fox jumps over the lazy dog near","the river bank while the farmer watches from the","old wooden porch of the house on the hill today."]
for i,t in enumerate(lines): p.insert_text((72,300+i*15),t,fontsize=11)
doc,h=parse(d.tobytes())
for b in doc.pages[0].text_blocks: print("BLOCK",repr(b.text),b.bbox,b.size)
t0=time.time(); dr=h[0].get_drawings(); print("drawings",len(dr),f"{(time.time()-t0)*1000:.1f}ms",[ (x['rect']) for x in dr])
val=next(b for b in doc.pages[0].text_blocks if b.text=="Jo Lee")
replace_text(h,0,val,"Jonathan Lee")
par=next(b for b in doc.pages[0].text_blocks if b.text.startswith("the river"))
replace_text(h,0,par,"the river bank while the farmer quietly watches from the")
out=fitz.open(stream=export(h),filetype="pdf")
for s in spans(out[0]): print(s)
