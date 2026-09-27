"""R5 drawing probe: drift predicate, draw_rect and image, translation vs
normalisation, redaction. Provenance as in recheck_common.py.

Unit-1 expectations on PyMuPDF 1.28.2: predicate_ok 256/256, rect_ok 64/256,
image_normal_ok 64/256, image_zero_ok 256/256, translate_ok 256/256,
normalize_ok 256/256, annot_ok 100/256.

NOTE for porting: this probe's redaction check samples one pixel and does not
hold rotation at 0. R11's tests use the stricter form instead -- text removed,
exactly one fill rect equal to the target, and the sampled pixel equal to the
fill colour, all on the exported bytes.
"""
from recheck_common import *
from collections import Counter
print('PyMuPDF',f.VersionBind)
img=f.Pixmap(f.csRGB,f.IRect(0,0,8,8),False); img.clear_with(128); png=img.tobytes('png')
counts=Counter()
def text_draw(p,delta=(0,0)):
 dx,dy=delta; p.insert_text((100+dx,140+dy),'POINT',fontsize=10)
 p.insert_textbox(f.Rect(100+dx,180+dy,220+dx,215+dy),'BOX',fontsize=10)
def displacement(p):
 o=origins(p)
 return tup(o['POINT']-f.Point(100,140)),tup(o['BOX']-f.Point(100,190.75))
for name,m,c,u,rot in cases((1,1.5)):
 d=make(m,c,u,rot); p=d[0]; text_draw(p); p.draw_rect(f.Rect(100,240,140,260),color=None,fill=(1,0,0))
 p.insert_image(f.Rect(170,240,190,260),stream=png)
 p.set_rotation(0); p.insert_image(f.Rect(210,240,230,260),stream=png); p.set_rotation(rot)
 d=reopen(d); p=d[0]; dt,db=displacement(p); pred=c.x0<m.x0 or c.y1>m.y1
 drift=not near(dt,(0,0)) or not near(db,(0,0)); imgs=[tup(r) for r in p.get_image_rects(p.get_images()[0][0])]
 rects=[tup(x['rect']) for x in p.get_drawings()]; drawok=any(near(r,(100,240,140,260)) for r in rects)
 imgnormal=any(near(r,(170,240,190,260)) for r in imgs); imgzero=any(near(r,(210,240,230,260)) for r in imgs)
 counts['cases']+=1; counts['predicate_mismatch']+=pred!=drift; counts['draw_rect_fail']+=not drawok; counts['image_normal_fail']+=not imgnormal; counts['image_zero_fail']+=not imgzero
 dc=make(m,c,u,rot); pc=dc[0]; text_draw(pc,(-dt[0],-dt[1])); dc=reopen(dc); ct,cb=displacement(dc[0]); compok=near(ct,(0,0)) and near(cb,(0,0)); counts['translation_fail']+=not compok
 dn=make(m,c,u,rot); pn=dn[0]; e=m&c; dn.xref_set_key(pn.xref,'CropBox','['+' '.join(map(str,e))+']'); pn=dn.reload_page(pn); text_draw(pn)
 dn.xref_set_key(pn.xref,'CropBox','['+' '.join(map(str,c))+']'); pn=dn.reload_page(pn); dn=reopen(dn); nt,nb=displacement(dn[0]); normok=near(nt,(0,0)) and near(nb,(0,0)); counts['normalize_fail']+=not normok
 dr=make(m,c,u,rot,True); pr=dr[0]; rr=f.Rect(35,65,95,90); a=pr.add_redact_annot(rr,fill=(0,1,0)); annotok=near(a.rect,rr)
 pr.apply_redactions(images=2,graphics=1,text=0); dr=reopen(dr); pr=dr[0]; removed='VISIBLE' not in origins(pr); fill=sample(pr,(60,80)); redok=removed and fill==(0,255,0)
 counts['annot_fail']+=not annotok; counts['redaction_fail']+=not redok
 print('DRAW',name,'predicate',pred,'delta_point',dt,'delta_box',db,'predicate_ok',pred==drift,'rect_ok',drawok,'image_normal_ok',imgnormal,'image_zero_ok',imgzero,'translate_ok',compok,'normalize_ok',normok,'annot_ok',annotok,'removed',removed,'redact_fill',fill)
 if not (drawok and imgzero and compok and normok and redok and annotok) or pred!=drift: print('DETAIL',name,'images',imgs,'rects',rects,'translated',ct,cb,'normalized',nt,nb)
 for doc in [d,dc,dn,dr]: doc.close()
print('SUMMARY',dict(counts))
