import json
from pathlib import Path
import numpy as np
import pytest
from histra.preprocessing.quad_geometry import compute_quad_geometry_batch


def test_native_returned_distorted_quad_geometry():
    data=json.loads((Path(__file__).parent/'fixtures/csharp_dhir_geometry.json').read_text())
    for case in data['fixtures']:
        points=np.array([[float(x) for x in p.split(';')] for p in case['points']],dtype=np.float32)[None,:,:]
        thickness=np.array([[float(case['expected']['Thickness'+str(j)]) for j in range(1,5)]],dtype=np.float32)
        lengths,diagonals,cosines,sines,axes,centres,volume=compute_quad_geometry_batch(points,thickness)
        for arr,prefix,n in [(lengths,'Length',4),(diagonals,'Diago',2),(cosines,'Cos',4),(sines,'Sin',4)]:
            np.testing.assert_allclose(arr[0],[float(case['expected'][prefix+str(j)]) for j in range(1,n+1)],rtol=1e-12,atol=1e-12)
        np.testing.assert_array_equal(centres[0],np.array([float(v) for v in case['expected']['G'].split(';')],dtype=np.float32))
        for j in range(3):
            np.testing.assert_array_equal(axes[0,j],np.array([float(v) for v in case['reference']['E'+str(j+1)].split(';')],dtype=np.float32))


def test_volume_weighted_centroid_for_distorted_quad():
    p=np.array([[[0,0,0],[10,0,0],[6,0,10],[0,0,10]]],dtype=np.float32)
    *_,g,volume=compute_quad_geometry_batch(p,np.full((1,4),2,dtype=np.float32))
    # Independent polygon centroid: trapezoid area 80, volume 160.
    assert volume[0]==pytest.approx(160,rel=1e-6)
    np.testing.assert_allclose(g[0],[49/12,0,55/12],rtol=1e-6)
    assert np.linalg.norm(g[0]-p[0].mean(axis=0)) > .4


def test_variable_thickness_centroid():
    p=np.array([[[0,0,0],[10,0,0],[10,0,10],[0,0,10]]],dtype=np.float32)
    *_,g,volume=compute_quad_geometry_batch(p,np.array([[1,1,2,2]],dtype=np.float32))
    assert volume[0]==pytest.approx(150)
    np.testing.assert_allclose(g[0],[5,0,50/9],rtol=1e-6)


def test_degenerate_quad_fails_before_spring_generation():
    p=np.zeros((1,4,3),dtype=np.float32)
    with pytest.raises(ValueError,match='Degenerate Quad edge'):
        compute_quad_geometry_batch(p,np.ones((1,4),dtype=np.float32))
