"""Native C# ray projection and polygon-strip intrinsic coordinates."""
import numpy as np
from numba import njit
from histra.preprocessing.quad_faces import _dot,_inside_polygon,align_nodes,_plane_normal,_plane_w,_ray_project
from histra.preprocessing.quad_geometry import _unit,_cross

@njit(cache=True)
def native_intrinsic(vertices, point, node_tolerance):
    f=np.float32
    x=_unit(vertices[1]-vertices[0]);z=_unit(_cross(x,vertices[3]-vertices[0]));y=_cross(z,x)
    polygon=np.empty((4,2),dtype=np.float32)
    for i in range(4):
        delta=vertices[i]-vertices[0];polygon[i,0]=_dot(x,delta);polygon[i,1]=_dot(y,delta)
    delta=point-vertices[0];target=np.array([_dot(x,delta),_dot(y,delta)],dtype=np.float32)
    p=np.array([target[0],target[1],f(0)],dtype=np.float32)
    out=np.zeros(2,dtype=np.float32)
    for axis in range(2):
        a=0;b=3 if axis==0 else 1;c=1 if axis==0 else 3;d=2
        start=np.array([polygon[a,0],polygon[a,1],f(0)],dtype=np.float32);end=np.array([polygon[b,0],polygon[b,1],f(0)],dtype=np.float32)
        if align_nodes(p,start,end,node_tolerance)>0:out[axis]=f(-1);continue
        start=np.array([polygon[c,0],polygon[c,1],f(0)],dtype=np.float32);end=np.array([polygon[d,0],polygon[d,1],f(0)],dtype=np.float32)
        if align_nodes(p,start,end,node_tolerance)>0:out[axis]=f(1);continue
        if not _inside_polygon(polygon,target,node_tolerance):continue
        low=f(-1);high=f(1);value=f(0)
        mid_a=(polygon[0]+polygon[1 if axis==0 else 3])/f(2)
        mid_b=(polygon[2]+polygon[3 if axis==0 else 1])/f(2)
        strip=np.empty((4,2),dtype=np.float32)
        for iteration in range(1000):
            if f(high-low)<f(.001):break
            strip[0]=polygon[0]
            if axis==0:strip[1]=mid_a;strip[2]=mid_b;strip[3]=polygon[3]
            else:strip[1]=polygon[1];strip[2]=mid_b;strip[3]=mid_a
            if _inside_polygon(strip,target,node_tolerance):high=value;value=f(f(low+value)/f(2))
            else:low=value;value=f(f(high+value)/f(2))
            for j in range(2):
                mid_a[j]=f(f(f(polygon[0,j]*f(f(1)-value))/f(2))+f(f(polygon[1 if axis==0 else 3,j]*f(f(1)+value))/f(2)))
                if axis==0:mid_b[j]=f(f(f(polygon[2,j]*f(f(1)+value))/f(2))+f(f(polygon[3,j]*f(f(1)-value))/f(2)))
                else:mid_b[j]=f(f(f(polygon[1,j]*f(f(1)-value))/f(2))+f(f(polygon[2,j]*f(f(1)+value))/f(2)))
        out[axis]=value
    return out

@njit(cache=True)
def native_projected_intrinsic(vertices,point,node_tolerance):
    normal=_plane_normal(vertices[0],vertices[1],vertices[2])
    projected=_ray_project(point,normal,_plane_w(vertices[0],normal))
    return native_intrinsic(vertices,projected,node_tolerance)


@njit(cache=True)
def native_intrinsic_2d(polygon, target, node_tolerance):
    """Original float-array GetIntrinsecCoordinates overload, without reprojection."""
    f=np.float32
    p=np.array([target[0],target[1],f(0)],dtype=np.float32)
    out=np.zeros(2,dtype=np.float32)
    for axis in range(2):
        a=0;b=3 if axis==0 else 1;c=1 if axis==0 else 3;d=2
        start=np.array([polygon[a,0],polygon[a,1],f(0)],dtype=np.float32);end=np.array([polygon[b,0],polygon[b,1],f(0)],dtype=np.float32)
        if align_nodes(p,start,end,node_tolerance)>0:out[axis]=f(-1);continue
        start=np.array([polygon[c,0],polygon[c,1],f(0)],dtype=np.float32);end=np.array([polygon[d,0],polygon[d,1],f(0)],dtype=np.float32)
        if align_nodes(p,start,end,node_tolerance)>0:out[axis]=f(1);continue
        if not _inside_polygon(polygon,target,node_tolerance):continue
        low=f(-1);high=f(1);value=f(0)
        mid_a=(polygon[0]+polygon[1 if axis==0 else 3])/f(2)
        mid_b=(polygon[2]+polygon[3 if axis==0 else 1])/f(2)
        strip=np.empty((4,2),dtype=np.float32)
        for iteration in range(1000):
            if f(high-low)<f(.001):break
            strip[0]=polygon[0]
            if axis==0:strip[1]=mid_a;strip[2]=mid_b;strip[3]=polygon[3]
            else:strip[1]=polygon[1];strip[2]=mid_b;strip[3]=mid_a
            if _inside_polygon(strip,target,node_tolerance):high=value;value=f(f(low+value)/f(2))
            else:low=value;value=f(f(high+value)/f(2))
            for j in range(2):
                mid_a[j]=f(f(f(polygon[0,j]*f(f(1)-value))/f(2))+f(f(polygon[1 if axis==0 else 3,j]*f(f(1)+value))/f(2)))
                if axis==0:mid_b[j]=f(f(f(polygon[2,j]*f(f(1)+value))/f(2))+f(f(polygon[3,j]*f(f(1)-value))/f(2)))
                else:mid_b[j]=f(f(f(polygon[1,j]*f(f(1)-value))/f(2))+f(f(polygon[2,j]*f(f(1)+value))/f(2)))
        out[axis]=value
    return out
