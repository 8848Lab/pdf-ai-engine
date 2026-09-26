"""R2 attack matrix: 1,024 configurations. Provenance as in recheck_common.py.

Expected on PyMuPDF 1.28.2: bounds/visible/offpage/sample fails all 0;
library_sample_fail 640; matrix_different 732.
"""
from recheck_common import *
print('PyMuPDF',f.VersionBind)
counts=dict(cases=0,bounds_fail=0,visible_fail=0,offpage_fail=0,sample_fail=0,library_sample_fail=0,matrix_different=0)
for name,m,c,u,rot in cases((.5,1,1.5,2)):
 d=make(m,c,u,rot,True); d=reopen(d); p=d[0]; e=m&c; b=bounds(p)
 spans={s['text']: f.Rect(s['bbox']) for bl in p.get_text('dict',clip=f.INFINITE_RECT(),flags=f.TEXTFLAGS_DICT & ~f.TEXT_MEDIABOX_CLIP)['blocks'] if 'lines' in bl for l in bl['lines'] for s in l['spans']}
 checks=[near(b,(0,0,e.width*u,e.height*u)),b.contains(spans['VISIBLE']),not b.intersects(spans['OFFPAGE'])]
 q=(80,85); col=sample(p,q); lib=sample(p,q,p.rotation_matrix)
 counts['cases']+=1
 for k,ok in zip(('bounds_fail','visible_fail','offpage_fail'),checks): counts[k]+=not ok
 counts['sample_fail']+=col!=(178,216,255); counts['library_sample_fail']+=lib!=(178,216,255)
 counts['matrix_different']+=not near(matrix(p),p.rotation_matrix)
 print('GEOM',name,'bounds',tup(b),'visible',checks[1],'reject_offpage',checks[2],'extent',checks[0],'sample',col,'library',lib,'matrix_equal',near(matrix(p),p.rotation_matrix))
 d.close()
print('SUMMARY',counts)
