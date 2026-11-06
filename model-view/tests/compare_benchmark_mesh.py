"""Compare regenerated benchmark geometry without earth-pressure restraints.

Run as ``.venv/bin/python -m tests.compare_benchmark_mesh``. The original HRX
is read-only; only the imported in-memory support flags are changed.
"""
from tests.test_benchmark_model import BENCHMARK
from histra_builder.generator.csharp_import import spec_from_hrx
from histra_builder.generator.csharp_mesher import build_csharp_bridge_mesh
from histra_builder.generator.csharp_model import Abutment, Pier
from collections import Counter
from scipy.spatial import cKDTree
from lxml import etree
s=spec_from_hrx(BENCHMARK)
for v in s.elements:
 if isinstance(v,(Abutment,Pier)):v.spinta_passiva_sx=v.spinta_passiva_dx=False
m=build_csharp_bridge_mesh(s)
r=etree.parse(str(BENCHMARK)).getroot(); nodes={n.get('Key'):tuple(map(float,n.get('Point').split(';'))) for n in r.findall('Node')}
ref=[]
for q in r.findall('Quad'):
 pts=[nodes[q.get(f'NodeKey{i}')] for i in range(1,5)]; ref.append((pts,q.get('MaterialKey'),[float(q.get(f'Thickness{i}')) for i in range(1,5)]))
pts=[p for ps,_,_ in ref for p in ps]; tree=cKDTree(pts)
lookup={}
for i,(ps,mat,ts) in enumerate(ref):
 ids=tuple(sorted(min(tree.query_ball_point(p,.0001)) for p in ps)); lookup.setdefault((ids,mat),[]).append(i)
matched=Counter(); correct_thick=Counter(); generated=Counter()
for q in m.quads.values():
 generated[q.group]+=1; ids=[]; nearest=[]
 for k in q.node_keys:
  p=m.nodes[k]; pp=(p.x,p.y,p.z); hits=tree.query_ball_point(pp,.05)
  if not hits:break
  n=min(hits,key=lambda i:sum((pts[i][j]-pp[j])**2 for j in range(3))); nearest.append(n); ids.append(min(tree.query_ball_point(pts[n],.0001)))
 if len(ids)==4 and (tuple(sorted(ids)),str(q.material_key)) in lookup:
  idx=lookup[(tuple(sorted(ids)),str(q.material_key))].pop() if lookup[(tuple(sorted(ids)),str(q.material_key))] else None
  if idx is not None:
   matched[q.group]+=1
   rpts,_,ts=ref[idx]
   if all(abs(q.kinematics.thicknesses[i]-ts[min(range(4),key=lambda j:sum((rpts[j][k]-pts[nearest[i]][k])**2 for k in range(3)))])<.05 for i in range(4)):correct_thick[q.group]+=1
print('generated',len(m.nodes),len(m.quads),'native',len(nodes),len(ref),'triangles',len(r.findall('Vertex')))
print('generated groups',generated)
print('geometry material matches',matched,'with thickness',correct_thick)
