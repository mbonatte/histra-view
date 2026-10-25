"""Fresh Quad geometry, matching C# SetGeometry and ComputeG.

The centre is the centroid of the thickness-weighted volume, not the mean
of the vertices. Two-point Gauss integration exactly integrates the bilinear
geometry/thickness polynomial. XNA Vector3 arithmetic remains Single.
"""
from __future__ import annotations
import math
import numpy as np
from numba import njit
from histra.types.point import Point
from .errors import ModelPreparationError
from .csharp_math import csharp_pow


@njit(cache=True)
def _norm(v):
    a=np.float32(v[0]*v[0]);b=np.float32(v[1]*v[1]);c=np.float32(v[2]*v[2])
    return np.float32(math.sqrt(float(np.float32(np.float32(a+b)+c))))


@njit(cache=True)
def _unit(v):
    n=_norm(v)
    if n<=0:raise ValueError('Degenerate Quad direction')
    scale=np.float32(np.float32(1.)/n)
    return np.array([np.float32(v[j]*scale) for j in range(3)],dtype=np.float32)


@njit(cache=True)
def _cross(a,b):
    return np.array([np.float32(np.float32(a[1]*b[2])-np.float32(a[2]*b[1])),
                     np.float32(np.float32(a[2]*b[0])-np.float32(a[0]*b[2])),
                     np.float32(np.float32(a[0]*b[1])-np.float32(a[1]*b[0]))],dtype=np.float32)


@njit(cache=True)
def compute_quad_geometry_batch(points,thickness):
    count=len(points)
    lengths=np.zeros((count,4));diagonals=np.zeros((count,2))
    cosines=np.zeros((count,4));sines=np.zeros((count,4))
    axes=np.zeros((count,3,3),dtype=np.float32)
    centres=np.zeros((count,3),dtype=np.float32)
    volumes=np.zeros(count)
    gp=1./math.sqrt(3.)
    for k in range(count):
        p=points[k]
        for j in range(4):lengths[k,j]=float(_norm(p[(j+1)%4]-p[j]))
        diagonals[k,0]=float(_norm(p[2]-p[0]));diagonals[k,1]=float(_norm(p[3]-p[1]))
        l=lengths[k];d=diagonals[k]
        if min(l)<=0:raise ValueError('Degenerate Quad edge')
        cosines[k,0]=(l[0]**2+l[3]**2-d[1]**2)/(2*l[0]*l[3])
        cosines[k,1]=(l[0]**2+l[1]**2-d[0]**2)/(2*l[0]*l[1])
        cosines[k,2]=(l[1]**2+l[2]**2-d[1]**2)/(2*l[1]*l[2])
        cosines[k,3]=(l[2]**2+l[3]**2-d[0]**2)/(2*l[2]*l[3])
        for j in range(4):
            value=1.-csharp_pow(cosines[k,j],2.)
            if value<0:raise ValueError('Invalid Quad corner angle')
            sines[k,j]=csharp_pow(value,.5)
        e1=_unit(p[1]-p[0]);e3=_unit(_cross(e1,p[2]-p[0]));e2=_cross(e3,e1)
        axes[k,0]=e1;axes[k,1]=e2;axes[k,2]=e3
        xy=np.array([[-l[0]/2.,0.],[l[0]/2.,0.],
            [l[0]/2.-l[1]*cosines[k,1],l[1]*sines[k,1]],
            [-l[0]/2.+l[3]*cosines[k,0],l[3]*sines[k,0]]])
        volume=0.;moment_x=0.;moment_y=0.
        for xi in (gp,-gp):
            for eta in (gp,-gp):
                n=np.array([(1-xi)*(1-eta),(1+xi)*(1-eta),(1+xi)*(1+eta),(1-xi)*(1+eta)])/4.
                nx=np.array([-(1-eta),1-eta,1+eta,-(1+eta)])/4.
                ny=np.array([-(1-xi),-(1+xi),1+xi,1-xi])/4.
                dx=0.;dy=0.;ex=0.;ey=0.;t=0.;x=0.;y=0.
                for j in range(4):
                    dx+=nx[j]*xy[j,0];dy+=nx[j]*xy[j,1]
                    ex+=ny[j]*xy[j,0];ey+=ny[j]*xy[j,1]
                    t+=n[j]*float(thickness[k,j]);x+=n[j]*xy[j,0];y+=n[j]*xy[j,1]
                dv=(dx*ey-dy*ex)*t
                if dv<=0:raise ValueError('Quad has nonpositive volume Jacobian')
                volume+=dv;moment_x+=dv*x;moment_y+=dv*y
        volumes[k]=volume
        for j in range(3):
            mid=np.float32(np.float32(p[0,j]+p[1,j])/np.float32(2.))
            centres[k,j]=np.float32(float(mid)+moment_x/volume*float(e1[j])+moment_y/volume*float(e2[j]))
    return lengths,diagonals,cosines,sines,axes,centres,volumes


def refresh_quad_geometry(model):
    """Recompute derived geometry before any afference or spring generation."""
    c=model.collections
    quads=list(c.quads.values())
    if not quads:
        return
    points=np.array([[(c.nodes[n].point.x,c.nodes[n].point.y,c.nodes[n].point.z)
                      for n in q.node_keys] for q in quads],dtype=np.float32)
    thickness=np.array([q.thickness for q in quads],dtype=np.float32)
    normals=np.array([[(n.x,n.y,n.z) for n in q.normal] for q in quads],dtype=np.float32)
    from .quad_faces import compute_quad_faces_batch
    faces=compute_quad_faces_batch(points,normals,thickness)
    try:
        lengths,diagonals,cosines,sines,axes,centres,volumes=compute_quad_geometry_batch(points,thickness)
    except ValueError as error:
        raise ModelPreparationError(str(error)) from error
    for key,node in c.nodes.items():
        node.point=Point(float(np.float32(node.point.x)),float(np.float32(node.point.y)),float(np.float32(node.point.z)))
    for i,q in enumerate(quads):
        q._prep_vint=tuple(face.astype(np.float64) for face in faces[i])
        q.length=lengths[i].tolist();q.diago=diagonals[i].tolist()
        q.cos=cosines[i].tolist();q.sin=sines[i].tolist();q.thickness=thickness[i].tolist()
        q.reference_e1=tuple(float(x) for x in axes[i,0]);q.reference_e2=tuple(float(x) for x in axes[i,1]);q.reference_e3=tuple(float(x) for x in axes[i,2])
        q.reference_origin=c.nodes[q.node_keys[0]].point
        q.g=Point(*(float(x) for x in centres[i]))
