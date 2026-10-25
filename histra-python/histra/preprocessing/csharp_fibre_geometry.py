"""Original C# Quad fibre geometry, validated against the 2026.1.1 DLL.

Operations.GetIntrinsecCoordinates uses projected edge intersections, not a
Newton inverse mapping. Float32 boundaries follow the original IL; in particular
all three coefficient expressions are promoted only after float arithmetic.
The decompiler inserts misleading inner double casts in coefficients 0 and 2.
"""
import math
from histra.preprocessing.csharp_math import csharp_pow, csharp_atan
import numpy as np
from histra.elements.interface import Interface
from histra.preprocessing.contact_geometry import _v
from histra.preprocessing.errors import ModelPreparationError
try:
    from numba import njit
except ImportError:  # scalar preparation fallback
    def njit(**kwargs):
        return lambda function: function

@njit(cache=True)
def _csharp_dot(a,b):
    f=np.float32
    return f(f(f(a[0]*b[0])+f(a[1]*b[1]))+f(a[2]*b[2]))

@njit(cache=True)
def _csharp_cross(a,b):
    f=np.float32
    return np.array([f(f(a[1]*b[2])-f(a[2]*b[1])),f(f(a[2]*b[0])-f(a[0]*b[2])),f(f(a[0]*b[1])-f(a[1]*b[0]))],dtype=np.float32)

@njit(cache=True)
def _csharp_norm(a):
    return np.float32(math.sqrt(np.float64(_csharp_dot(a,a))))

@njit(cache=True)
def _csharp_unit(a):
    return a*np.float32(np.float32(1)/_csharp_norm(a))

@njit(cache=True)
def _csharp_polygon_area(points):
    """Original Operations.Area(Vector3[], true), including Single projection."""
    f = np.float32
    x = _csharp_unit(points[1] - points[0])
    z = _csharp_unit(_csharp_cross(x, points[2] - points[0]))
    y = _csharp_cross(z, x)
    projected = np.empty((len(points), 2), dtype=np.float32)
    for i in range(len(points)):
        delta = points[i] - points[0]
        projected[i, 0] = f(_csharp_dot(delta, x) + f(0))
        projected[i, 1] = f(_csharp_dot(delta, y) + f(0))
    area = f(0)
    for i in range(len(points)):
        following = (i + 1) % len(points)
        area = f(area + f(f(projected[i, 0] * projected[following, 1])
                         - f(projected[following, 0] * projected[i, 1])))
    return abs(f(area * f(0.5)))

@njit(cache=True)
def _csharp_polygon_areas(cells):
    areas = np.empty(len(cells), dtype=np.float64)
    for i in range(len(cells)):
        areas[i] = _csharp_polygon_area(cells[i])
    return areas

@njit(cache=True)
def _csharp_rotation(face):
    x=_csharp_unit(face[1]-face[0])
    corner=face[3] if _csharp_norm(face[0]-face[3])>np.float32(1) else face[2]
    z=_csharp_unit(_csharp_cross(x,corner-face[0])); y=_csharp_cross(z,x)
    return x,y,z

@njit(cache=True)
def _csharp_project(face,points):
    x,y,z=_csharp_rotation(face)
    out=np.empty((len(points),2),dtype=np.float32)
    for i in range(len(points)):
        p=points[i]-face[0]
        out[i,0]=_csharp_dot(x,p);out[i,1]=_csharp_dot(y,p)
    return out

@njit(cache=True)
def _csharp_intersection(a,b,c,d):
    f=np.float32
    if _csharp_norm(np.array([a[0]-c[0],a[1]-c[1],f(0)],dtype=np.float32))<f(1) or _csharp_norm(np.array([b[0]-c[0],b[1]-c[1],f(0)],dtype=np.float32))<f(1):return c.copy()
    if _csharp_norm(np.array([a[0]-d[0],a[1]-d[1],f(0)],dtype=np.float32))<f(1) or _csharp_norm(np.array([b[0]-d[0],b[1]-d[1],f(0)],dtype=np.float32))<f(1):return d.copy()
    # GetPlane(c,d,(c.X,c.Y,1)): normalized (dy,-dx,0).
    n=_csharp_unit(np.array([d[1]-c[1],-(d[0]-c[0]),f(0)],dtype=np.float32))
    w=f(f(-n[0]*c[0])-f(n[1]*c[1]))
    direction=b-a;x=direction[0];y=direction[1]
    out=np.zeros(2,dtype=np.float32)
    if abs(x)>=abs(y):
        denominator=f(n[0]+f(f(n[1]*y)/x))
        if denominator==f(0):return out
        out[0]=f(f(f(f(f(n[1]*y)/x)*a[0])-f(n[1]*a[1])-w)/denominator)
        out[1]=f(a[1]+f(f(y/x)*f(out[0]-a[0])))
    else:
        denominator=f(f(f(n[0]*x)/y)+n[1])
        if denominator==f(0):return out
        out[1]=f(f(f(f(f(n[0]*x)/y)*a[1])-f(n[0]*a[0])-w)/denominator)
        out[0]=f(a[0]+f(f(x/y)*f(out[1]-a[1])))
    return out

@njit(cache=True)
def _csharp_intrinsic(face,points):
    f=np.float32
    verts=_csharp_project(face,face); pts=_csharp_project(face,points)
    uv=np.zeros((4,2),dtype=np.float32)
    for i,j,k in ((0,0,3),(1,1,2)):
        p=_csharp_intersection(verts[0],verts[1],pts[j],pts[k])
        dist=f(math.sqrt(np.float64(f(f(p[0]-verts[0,0])**f(2)+f(p[1]-verts[0,1])**f(2)))))
        base=f(math.sqrt(np.float64(f(f(verts[1,0]-verts[0,0])**f(2)+f(verts[1,1]-verts[0,1])**f(2)))))
        value=f(f(-1)+f(f(f(2)*dist)/base))
        uv[j,0]=value;uv[k,0]=value
    a=0;b=3
    if _csharp_norm(face[0]-face[3])<f(1e-8):a=1;b=2
    for j,k in ((0,1),(2,3)):
        p=_csharp_intersection(verts[a],verts[b],pts[j],pts[k])
        dist=f(math.sqrt(np.float64(f(f(p[0]-verts[a,0])**f(2)+f(p[1]-verts[a,1])**f(2)))))
        base=f(math.sqrt(np.float64(f(f(verts[b,0]-verts[a,0])**f(2)+f(verts[b,1]-verts[a,1])**f(2)))))
        value=f(f(-1)+f(f(f(2)*dist)/base))
        uv[j,1]=value;uv[k,1]=value
    return uv

@njit(cache=True)
def _csharp_mapped(face,u,v):
    f=np.float32
    verts=_csharp_project(face,face);x,y,z=_csharp_rotation(face)
    weights=np.array([f(f(f(f(1)-u)*f(f(1)-v))/f(4)),f(f(f(f(1)+u)*f(f(1)-v))/f(4)),f(f(f(f(1)+u)*f(f(1)+v))/f(4)),f(f(f(f(1)-u)*f(f(1)+v))/f(4))],dtype=np.float32)
    local=np.zeros(2,dtype=np.float32)
    for j in range(2):
        local[j]=f(f(f(f(verts[0,j]*weights[0])+f(verts[1,j]*weights[1]))+f(verts[2,j]*weights[2]))+f(verts[3,j]*weights[3]))
    out=np.empty(3,dtype=np.float32)
    for j in range(3):out[j]=f(f(f(f(local[0]*x[j])+f(local[1]*y[j]))+f(f(0)*z[j]))+face[0,j])
    return out

@njit(cache=True)
def _csharp_properties(near,far,cell):
    f=np.float32;d=np.float64
    points=cell.copy()
    if _csharp_dot(_csharp_cross(near[1]-near[0],near[3]-near[0]),_csharp_cross(points[1]-points[0],points[3]-points[0]))<f(0):
        tmp=points[1].copy();points[1]=points[3];points[3]=tmp
    scores=np.zeros(4,dtype=np.float32)
    for shift in range(4):
        for k in range(4):scores[shift]=f(scores[shift]+_csharp_norm(points[(shift+k)%4]-near[k]))
    shift=np.argmin(scores);ordered=points.copy()
    for k in range(4):ordered[k]=points[(shift+k)%4]
    uv=_csharp_intrinsic(near,ordered)
    uc=f(f(f(f(uv[0,0]+uv[1,0])+uv[2,0])+uv[3,0])/f(4))
    vc=f(f(f(f(uv[0,1]+uv[1,1])+uv[2,1])+uv[3,1])/f(4))
    center=_csharp_mapped(near,uc,vc);opposite=_csharp_mapped(far,uc,vc)
    length=d(_csharp_norm(opposite-center));axis=_csharp_unit(opposite-center)
    transverse=_csharp_unit(ordered[0]-center-f(_csharp_dot(ordered[0]-center,axis))*axis)
    perpendicular=_csharp_cross(transverse,axis)
    a5=np.empty((4,3),dtype=np.float32);a7=np.empty((4,3),dtype=np.float32)
    for i in range(4):
        p=ordered[i]-center;q=_csharp_mapped(far,uv[i,0],uv[i,1])-center
        a=np.array([_csharp_dot(perpendicular,p),_csharp_dot(transverse,p),_csharp_dot(axis,p)],dtype=np.float32)
        b=np.array([_csharp_dot(perpendicular,q),_csharp_dot(transverse,q),_csharp_dot(axis,q)],dtype=np.float32)
        denominator=f(a[2]-b[2]);alpha=f(a[2]/denominator);beta=f(-(length-d(a[2]))/d(denominator))
        a5[i]=a+(b-a)*alpha;a7[i]=a+(b-a)*beta
    # Original IL: float arithmetic, then conv.r8 and multiplication by 0.5.
    c0=.5*d(-(a5[1,0]-a5[3,0]-a7[1,0]+a5[3,0])*(a5[0,1]-a5[2,1]-a7[0,1]+a5[2,1])+(a5[0,0]-a5[2,0]-a7[0,0]+a5[2,0])*(a5[1,1]-a5[3,1]-a7[1,1]+a5[3,1]))
    c1=.5*d(-f(2)*a5[0,0]*a5[1,1]+f(2)*a5[2,0]*a5[1,1]+a7[0,0]*a5[1,1]-a7[2,0]*a5[1,1]-(a7[1,0]-a7[3,0])*(a5[0,1]-a5[2,1])+f(2)*a5[0,0]*a5[3,1]-f(2)*a5[2,0]*a5[3,1]-a7[0,0]*a5[3,1]+a7[2,0]*a5[3,1]+a5[0,0]*a7[1,1]-a5[2,0]*a7[1,1]+a5[3,0]*(-f(2)*a5[0,1]+f(2)*a5[2,1]+a7[0,1]-a7[2,1])-a5[1,0]*(-f(2)*a5[0,1]+f(2)*a5[2,1]+a7[0,1]-a7[2,1])-a5[0,0]*a7[3,1]+a5[2,0]*a7[3,1])
    c2=.5*d(-(a5[1,0]-a5[3,0])*(a5[0,1]-a5[2,1])+(a5[0,0]-a5[2,0])*(a5[1,1]-a5[3,1]))
    area=.5*((d(a5[3,0])-d(a5[1,0]))*(d(a5[0,1])-d(a5[2,1]))+(d(a5[0,0])-d(a5[2,0]))*(d(a5[1,1])-d(a5[3,1])))
    if area<0:c0=-c0;c1=-c1;c2=-c2;area=-area
    return np.array([c0,c1,c2],dtype=np.float64),length,axis,area

@njit(cache=True)
def _csharp_stiffness(near,far,cell,E,e2):
    coeff,length,axis,area=_csharp_properties(near,far,cell)
    a,b,c=coeff
    upper=.5
    if a<=1e-10:
        integral=upper/c if abs(b)<=1e-10 else (math.log(abs(upper+c/b))-math.log(abs(c/b)))/b
    else:
        disc=csharp_pow(b,2.)-4.*a*c
        if disc>0:
            root=csharp_pow(disc,.5);r1=(-b+root)/(2.*a);r2=(-b-root)/(2.*a)
            integral=(math.log(abs((upper-r1)/(upper-r2)))-math.log(abs((-r1)/(-r2))))/root
        elif disc<0:
            root=csharp_pow(-disc,.5)
            integral=2.*(csharp_atan((2.*a*upper+b)/root)-csharp_atan(b/root))/root
        else:integral=-(1./(upper+b/(2.*a))-2.*a/b)/a
    return abs(E/(length*integral)*np.float64(_csharp_dot(axis,e2))),min(abs(a*csharp_pow(upper,2.)+b*upper+c),abs(c)),length*upper



def _csharp_cell_vertices(intf: Interface, index: int) -> list[np.ndarray]:
    """C# Interface.GetSpringCoordinate: local Vector2 cells, then global."""
    f = np.float32
    row, col = divmod(index, intf.ncol)
    vertices = np.asarray([(p.x, p.y) for p in intf.vint2d], dtype=np.float32)
    axes = np.asarray([intf.reference_e1, intf.reference_e2, intf.reference_e3], dtype=np.float32).T
    origin = np.asarray(_v(intf.reference_origin), dtype=np.float32)
    result = []
    for c, r in ((col, row), (col+1, row), (col+1, row+1), (col, row+1)):
        u = f(f(f(c)*f(2))/f(intf.ncol)-f(1))
        v = f(f(f(r)*f(2))/f(intf.nrow)-f(1))
        terms = [
            f(f(f(vertices[k]*f(f(1)+f(su)*u))*f(f(1)+f(sv)*v))/f(4))
            for k, (su, sv) in enumerate(((-1,-1),(1,-1),(1,1),(-1,1)))
        ]
        local = f(f(f(terms[0]+terms[1])+terms[2])+terms[3])
        # Operations.MatrixPerVector3 includes the zero local-Y term and
        # adds translation last; do not interpolate translated vertices.
        point = f(f(f(axes[:,0]*local[0]+axes[:,1]*f(0))+axes[:,2]*local[1])+origin)
        result.append(point)
    return result


@njit(cache=True, nogil=True)
def _csharp_interface_cells_nb(vertices, axes, origin, nrow, ncol):
    # Port Interface.GetAreaTrasvSpringIntrinsicCoordinates,
    # GetAreaTrasvSpringCoordinate and Operations.MatrixPerVector3.
    f = np.float32
    cells = np.empty((nrow*ncol, 4, 3), dtype=np.float32)
    local = np.empty(2, dtype=np.float32)
    for row in range(nrow):
        for col in range(ncol):
            index = row*ncol+col
            for corner in range(4):
                c = col + (1 if corner == 1 or corner == 2 else 0)
                r = row + (1 if corner == 2 or corner == 3 else 0)
                u = f(f(f(c)*f(2))/f(ncol)-f(1))
                v = f(f(f(r)*f(2))/f(nrow)-f(1))
                for j in range(2):
                    t0 = f(f(f(vertices[0,j]*f(f(1)-u))*f(f(1)-v))/f(4))
                    t1 = f(f(f(vertices[1,j]*f(f(1)+u))*f(f(1)-v))/f(4))
                    t2 = f(f(f(vertices[2,j]*f(f(1)+u))*f(f(1)+v))/f(4))
                    t3 = f(f(f(vertices[3,j]*f(f(1)-u))*f(f(1)+v))/f(4))
                    local[j] = f(f(f(t0+t1)+t2)+t3)
                for j in range(3):
                    cells[index,corner,j] = f(f(f(axes[j,0]*local[0]+axes[j,1]*f(0))+axes[j,2]*local[1])+origin[j])
    return cells


def _csharp_interface_cells(intf: Interface) -> np.ndarray:
    nrow = int(intf.nrow)
    ncol = int(intf.ncol)
    if nrow <= 0 or ncol <= 0:
        raise ModelPreparationError(
            f"Interface {intf.key} has invalid spring grid "
            f"Nrow={nrow}, Ncol={ncol}."
        )
    vertices = np.asarray([(p.x, p.y) for p in intf.vint2d], dtype=np.float32)
    axes = np.asarray([intf.reference_e1, intf.reference_e2, intf.reference_e3], dtype=np.float32).T
    origin = np.asarray(_v(intf.reference_origin), dtype=np.float32)
    if njit is not None:
        return _csharp_interface_cells_nb(vertices, axes, origin, nrow, ncol)
    return np.asarray(
        [_csharp_cell_vertices(intf, index) for index in range(nrow * ncol)],
        dtype=np.float32,
    )


@njit(cache=True, nogil=True)
def _csharp_fibre_stiffness_batch_nb(near_face, far_face, cells, E, reference_e2, output, errors):
    for index in range(len(cells)):
        k, area, length = _csharp_stiffness(near_face, far_face, cells[index], E, reference_e2)
        if not (math.isfinite(k) and math.isfinite(area) and math.isfinite(length)) or area <= 0 or length <= 0:
            errors[index] = 5
        else:
            output[index,0] = k
            output[index,1] = area
            output[index,2] = length
