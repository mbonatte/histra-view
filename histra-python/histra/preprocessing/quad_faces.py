"""Original Quad.SetGeometry face projection, verified against native DLL."""
import math
import numpy as np
from numba import njit
from .quad_geometry import _unit, _cross

@njit(cache=True)
def _dot(a,b):
    return np.float32(np.float32(np.float32(a[0]*b[0])+np.float32(a[1]*b[1]))+np.float32(a[2]*b[2]))

@njit(cache=True)
def _plane_w(p,n):
    return np.float32(np.float32(np.float32(-n[0]*p[0])-np.float32(n[1]*p[1]))-np.float32(n[2]*p[2]))

@njit(cache=True)
def _plane_normal(a,b,c):
    return _unit(_cross(b-a,c-a))

@njit(cache=True)
def _ray_project(p,n,w):
    axis=0
    for j in range(1,3):
        if abs(n[j])>abs(n[axis]):axis=j
    other=np.empty(2,dtype=np.int64); count=0
    for j in range(3):
        if j!=axis:other[count]=j;count+=1
    a=other[0];b=other[1]
    ca=np.float32(np.float32(n[a]*n[a])/n[axis])
    cb=np.float32(np.float32(n[b]*n[b])/n[axis])
    if axis==0:den=np.float32(np.float32(n[axis]+ca)+cb)
    elif axis==1:den=np.float32(np.float32(ca+n[axis])+cb)
    else:den=np.float32(np.float32(ca+cb)+n[axis])
    value=np.float32(np.float32(ca*p[axis])+np.float32(cb*p[axis]))
    value=np.float32(value-np.float32(n[a]*p[a]))
    value=np.float32(value-np.float32(n[b]*p[b]))
    value=np.float32(np.float32(value-w)/den)
    out=p.copy();out[axis]=value
    for j in range(3):
        if j!=axis:
            out[j]=np.float32(p[j]+np.float32(np.float32(n[j]/n[axis])*np.float32(value-p[axis])))
    return out

@njit(cache=True)
def compute_quad_faces_batch(points,normals,thickness):
    result=np.empty((len(points),6,4,3),dtype=np.float32)
    half=np.float32(2)
    for k in range(len(points)):
        p=points[k];normal=normals[k];th=thickness[k];faces=result[k]
        for face in range(6):
            if face<4:
                nex=(face+1)%4
                a=_plane_normal(p[face],p[nex],p[face]+normal[face])
                b=_plane_normal(p[face],p[nex],p[nex]+normal[nex])
                if _dot(a,b)<=np.float32(-1):b=-b
                direction=_unit(a+b)
                w=_plane_w(p[face],direction)
                if face==0 or face==3:first=face;second=nex
                else:first=nex;second=face
                faces[face,0]=p[first]-normal[first]*np.float32(th[first]/half)
                faces[face,1]=p[second]-normal[second]*np.float32(th[second]/half)
                faces[face,2]=p[second]+normal[second]*np.float32(th[second]/half)
                faces[face,3]=p[first]+normal[first]*np.float32(th[first]/half)
            else:
                if face==4:
                    faces[face,0]=faces[2,1];faces[face,1]=faces[0,1]
                    faces[face,2]=faces[0,0];faces[face,3]=faces[2,0]
                else:
                    faces[face,0]=faces[2,3];faces[face,1]=faces[0,3]
                    faces[face,2]=faces[0,2];faces[face,3]=faces[2,2]
                v=faces[face]
                a=_plane_normal(v[0],v[1],(v[2]+v[3])/half)
                b=_plane_normal(v[2],v[3],(v[0]+v[1])/half)
                if _dot(a,b)<np.float32(0):b=-b
                direction=_unit(a+b)
                w=_plane_w((v[0]+v[1])/half,direction)
            for j in range(4):faces[face,j]=_ray_project(faces[face,j],direction,w)
    return result

@njit(cache=True, error_model="numpy")
def align_nodes(point, first, second, tolerance):
    """Original Operations.AlignNodes, preserving Single subtraction order."""
    point=np.asarray(point,dtype=np.float32)
    first=np.asarray(first,dtype=np.float32)
    second=np.asarray(second,dtype=np.float32)
    tolerance=np.float32(tolerance)
    if np.all(np.abs(point-first)<tolerance):return 2
    if np.all(np.abs(point-second)<tolerance):return 3
    edge=(second-first).astype(np.float64)
    offset=(point-first).astype(np.float64)
    edge_norm=math.sqrt(edge[0]*edge[0]+edge[1]*edge[1]+edge[2]*edge[2])
    offset_norm=math.sqrt(offset[0]*offset[0]+offset[1]*offset[1]+offset[2]*offset[2])
    cosine=(edge[0]*offset[0]+edge[1]*offset[1]+edge[2]*offset[2])/(edge_norm*offset_norm)
    cosine=min(max(cosine,-1.),1.)
    distance=math.sqrt(1.-cosine*cosine)*offset_norm
    if distance>=float(tolerance) or distance<=-float(tolerance):return 0
    if cosine>0. and offset_norm<=edge_norm:return 1
    return -1


@njit(cache=True, error_model="numpy")
def _inside_polygon(vertices, point, tolerance):
    p=np.array([point[0],point[1],np.float32(0)],dtype=np.float32)
    inside=False
    previous=3
    for i in range(4):
        a=np.array([vertices[i,0],vertices[i,1],np.float32(0)],dtype=np.float32)
        b=np.array([vertices[(i+1)%4,0],vertices[(i+1)%4,1],np.float32(0)],dtype=np.float32)
        if align_nodes(p,a,b,tolerance)>0:return True
        current=vertices[i];prior=vertices[previous]
        if ((current[1]<=point[1] and point[1]<prior[1]) or (prior[1]<=point[1] and point[1]<current[1])):
            x=np.float32(np.float32(np.float32(prior[0]-current[0])*np.float32(point[1]-current[1]))/np.float32(prior[1]-current[1]))
            if point[0]<np.float32(x+current[0]):inside=not inside
        previous=i
    return inside

@njit(cache=True)
def classify_contained_contact(first, second, tolerance):
    """Original IntersectionTest's equality and containment branches."""
    first=first.astype(np.float32);second=second.astype(np.float32)
    x=_unit(first[1]-first[0]);z=_unit(_cross(x,first[3]-first[0]));y=_cross(z,x)
    a=np.empty((4,2),dtype=np.float32);b=np.empty((4,2),dtype=np.float32)
    for i in range(4):
        a[i,0]=_dot(x,first[i]-first[0]);a[i,1]=_dot(y,first[i]-first[0])
        b[i,0]=_dot(x,second[i]-first[0]);b[i,1]=_dot(y,second[i]-first[0])
    equal=True
    for i in range(4):
        found=False
        for j in range(4):
            if abs(np.float32(a[i,0]-b[j,0]))<tolerance and abs(np.float32(a[i,1]-b[j,1]))<tolerance:found=True
        if not found:equal=False
    if equal:return 3
    contained=True
    for i in range(4):
        if not _inside_polygon(b,a[i],tolerance):contained=False
    if contained:return 1
    contained=True
    for i in range(4):
        if not _inside_polygon(a,b[i],tolerance):contained=False
    if contained:return 2
    return 0


@njit(cache=True)
def distance_to_contact_plane(centre, vertices):
    """C# Quad.GetSlidingStiffness ray intersection and Single length."""
    normal = _plane_normal(vertices[0], vertices[1], vertices[2])
    projected = _ray_project(centre, normal, _plane_w(vertices[0], normal))
    delta = projected - centre
    squared = np.float32(np.float32(delta[0]*delta[0]) + np.float32(delta[1]*delta[1]))
    squared = np.float32(squared + np.float32(delta[2]*delta[2]))
    return float(np.float32(math.sqrt(float(squared))))
