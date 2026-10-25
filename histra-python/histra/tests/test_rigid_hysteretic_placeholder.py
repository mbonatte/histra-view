"""Rigid support metadata cannot erase a deformable spring's strength."""
import numpy as np
import pytest
from histra.preprocessing.constitutive_laws import HystereticLaw
from histra.preprocessing.spring_factory import _configure_hysteretic,_new_hysteretic_spring,_combine_hysteretic


@pytest.mark.parametrize('rigid_first',[True,False])
def test_rigid_hysteretic_placeholder_preserves_deformable_envelope(rigid_first):
    law=HystereticLaw(E=3100.,fy_t=.08,fy_c=3.87,tensile_curve='LinearHardening',compressive_curve='LinearHardening',ratio_et_t=.01,ratio_et_c=.01,alfa_r_t=1.,alfa_r_c=1.,alfa_u_t=1.,alfa_u_c=1.,G_t=.005,G_c=10.,eps_u_t=.1,eps_u_c=.1,law_type='ElastoPlasticDuctilityFixed')
    deformable=_configure_hysteretic(100.,10.,1.,law)
    placeholder=_new_hysteretic_spring()
    placeholder.k=-1.;placeholder.fy=[0.,0.];placeholder.area=10.
    sides=(placeholder,deformable) if rigid_first else (deformable,placeholder)
    result=_combine_hysteretic(*sides,True,law,law)
    assert result is not deformable
    assert result.k==deformable.k
    assert result.fy==deformable.fy
    assert result.fy[0]>0 and result.fy[1]<0
    assert np.isfinite(result.k_tang) and result.k_tang>0
    # Legacy C# SetSpringYieldingForce selected these placeholder zeros.
    assert min(sides[0].fy[0],sides[1].fy[0])==0.
    assert max(sides[0].fy[1],sides[1].fy[1])==0.
