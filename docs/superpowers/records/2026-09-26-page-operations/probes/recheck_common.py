"""Shared helpers for the Codex (gpt-6-astra) re-check probes, 2026-09-26.

Provenance: written by the Codex critic via the SQUID session, run offline on
PyMuPDF 1.28.2, then re-run by the coordinator on Windows. Kept verbatim as
the evidence behind rulings R2, R5 and R11-R16 in
docs/superpowers/specs/2026-09-26-page-operations-design.md, and as the
source Merge A ports into tests/test_geometry.py.

These are reference probes, not tests: they print, they do not assert.
"""
import pymupdf as f
from itertools import product
ROTS=(0,90,180,270)
def tup(x): return tuple(round(v,4) for v in x)
def bounds(p):
 w,h=p.rect.width,p.rect.height
 if p.rotation in (90,270): w,h=h,w
 return f.Rect(0,0,w,h)
def matrix(p):
 m=f.Matrix(p.rotation); r=bounds(p)*m
 return m*f.Matrix(1,0,0,1,-r.x0,-r.y0)
def reopen(d): return f.open(stream=d.tobytes(garbage=3),filetype='pdf')
def cases(units=(1,)):
 for (ox,oy),mask,u,rot in product(((0,0),(100,200),(-100,-200),(13.125,-27.375)),range(16),units,ROTS):
  m=f.Rect(ox,oy,ox+300,oy+400)
  c=f.Rect(ox+(-17.5 if mask&1 else 20.25),oy+(-23.75 if mask&2 else 20.25),ox+300+(31.25 if mask&4 else -20.25),oy+400+(11.125 if mask&8 else -20.25))
  yield f'o={ox},{oy};mask={mask};u={u};r={rot}',m,c,u,rot
def make(m,c,u,rot,seed=False):
 d=f.open(); p=d.new_page(width=300,height=400); p.insert_font(fontname='helv')
 for k,v in [('MediaBox',m),('CropBox',c)]: d.xref_set_key(p.xref,k,'['+' '.join(map(str,v))+']')
 d.xref_set_key(p.xref,'UserUnit',str(u)); p=d.reload_page(p); p.set_rotation(rot)
 if seed:
  e=m&c; x=e.x0+40/u; y=e.y1-80/u
  s=f'q 0.7 0.85 1 rg {x-5/u} {y-8/u} {100/u} {30/u} re f Q BT /helv {10/u} Tf 1 0 0 1 {x} {y} Tm (VISIBLE) Tj ET\nBT /helv {10/u} Tf 1 0 0 1 {e.x1+40/u} {y} Tm (OFFPAGE) Tj ET'
  xr=d.get_new_xref(); d.update_object(xr,'<<>>'); d.update_stream(xr,s.encode()); p.set_contents(xr)
 return d
def origins(p):
 return {s['text']: f.Point(s['origin']) for b in p.get_text('dict',clip=f.INFINITE_RECT(),flags=f.TEXTFLAGS_DICT & ~f.TEXT_MEDIABOX_CLIP)['blocks'] if 'lines' in b for l in b['lines'] for s in l['spans']}
def sample(p,q,mat=None):
 pix=p.get_pixmap(); q=f.Point(q)*(matrix(p) if mat is None else mat)
 return pix.pixel(max(0,min(pix.width-1,int(q.x-pix.x))),max(0,min(pix.height-1,int(q.y-pix.y))))
def near(a,b,tol=.003): return max(abs(x-y) for x,y in zip(a,b))<tol
