"""Check that existing spring types still work after adding SpringHysteretic."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import xml.etree.ElementTree as ET
from histra.model.spring import (
    Spring, SpringElastic, SpringCoulomb03, SpringCoulomb,
    SpringMultiLinear, SpringHysteretic, spring_from_xml,
    _SPRING_REGISTRY, PhaseEnum,
)

# Test existing subclass hierarchy
xml = '<Spring TypeOf="HiStrA.Objects.SpringElastic" K="1000" Key="1"/>'
elem = ET.fromstring(xml)
s = spring_from_xml(elem)
assert isinstance(s, SpringElastic), f'Expected SpringElastic, got {type(s).__name__}'
assert s.k == 1000.0, f'K should be 1000, got {s.k}'
print('[OK] SpringElastic loads correctly')

xml_linear = '<Spring TypeOf="HiStrA.Objects.SpringLinearElastic" K="1000" Key="2"/>'
spring_linear = Spring.from_xml(ET.fromstring(xml_linear))
assert isinstance(spring_linear, SpringElastic), type(spring_linear).__name__

# Test Coulomb03 still works
xml2 = '<Spring TypeOf="HiStrA.Objects.SpringCoulomb03" K="2000" Mu="0.5" C="10" Kt="500" Kn="2000"/>'
elem2 = ET.fromstring(xml2)
s2 = spring_from_xml(elem2)
assert isinstance(s2, SpringCoulomb03)
assert s2.mu == 0.5
assert s2.c == 10.0
print('[OK] SpringCoulomb03 loads correctly')

# Test PhaseEnum
assert int(PhaseEnum.Elastic) == 0
assert int(PhaseEnum.Plastic_t) == 1
print('[OK] PhaseEnum has correct values')

# Test base class fields
sp = Spring()
assert sp.is_on is True
assert sp.phase == 0
assert sp.t_phase == 0
sp.revert_to_start()
assert sp.u == 0.0
assert sp.f == 0.0
sp.set_trial_strain(0.5)
assert sp.u == 0.5
assert sp.f == sp.k * sp.u
sp.commit()
assert sp.f == sp.k * sp.u
print('[OK] Base Spring lifecycle methods work')

# Test SpringHysteretic register
assert 'HiStrA.Objects.SpringHysteretic' in _SPRING_REGISTRY
assert _SPRING_REGISTRY['HiStrA.Objects.SpringHysteretic'] is SpringHysteretic
print('[OK] SpringHysteretic registered correctly')

# Test SpringHysteretic XML parsing
xml3 = '''
<Spring TypeOf="HiStrA.Objects.SpringHysteretic"
    Key="60" ParentKey="552" ParentType="Interface"
    SpringPurpose="Transversal1" Type="Hysteretic"
    Area="78.222560882569" Length="0" K="10861.7713646576"
    PinchXp="0" PinchYp="0" PinchXn="0" PinchYn="0"
    Damfc1p="0" Damfc2p="0" Damfc1n="0" Damfc2n="0"
    Betap="1" Betan="0"
    Rot1p="0.000144032760999385" Mom1p="1.56441418012051"
    Rot2p="0.0201440327027917" Mom2p="0"
    Rot3p="0.0203454730298196" Mom3p="0"
    Mom1n="-209.631510043573" Rot1n="-0.0193003908860762"
    Rot2n="-0.0416884495294834" Mom2n="-2.8421709430404E-14"
    Rot3n="-0.0421053340247782" Mom3n="0"
    E1n="10861.5162916108" E1p="10861.5162916108"
    E2n="-9363.54122447794" E2p="-78.2207092336776"
    E3n="-6.8176460749166E-11" E3p="0"
    Eun="10861.5162916108" Eup="10861.5162916108"
    EnergyA="4.38536311832298"
    TensileCurveType="LinearSoftening"
    CompressiveCurveType="LinearSoftening"
    Kt1="-78.2207092336776" Kt2="-9363.54122447794"
    Fy1="1.56441418012051" Fy2="-209.631510043573"
    Ur1="0.0201440327027917" Ur2="-0.0416884495294834"
    AlfaU1="1" AlfaU2="0" AlfaR1="1" AlfaR2="1"/>
'''
elem3 = ET.fromstring(xml3)
s3 = spring_from_xml(elem3)
assert isinstance(s3, SpringHysteretic), f'Expected SpringHysteretic, got {type(s3).__name__}'
assert s3.k == 10861.7713646576
assert s3.pinch_xp == 0.0
assert s3.rot1p == 0.000144032760999385
assert s3.mom1n == -209.631510043573
assert s3.fy[0] == 1.56441418012051
assert s3.fy[1] == -209.631510043573
assert s3.kt[0] == -78.2207092336776
assert s3.ur[0] == 0.0201440327027917
assert s3.alfau[0] == 1.0
assert s3.alfar[1] == 1.0
assert s3.tensile_curve_type == "LinearSoftening"
assert s3.compressive_curve_type == "LinearSoftening"
assert s3.is_on is True
print('[OK] SpringHysteretic XML parsing correct')

# Test a quick revert_to_start + set_trial_strain
s3.revert_to_start()
assert s3._tstress == 0.0
assert s3._tstrain == 0.0
assert s3.phase == PhaseEnum.Elastic
s3.set_trial_strain(0.00001)
assert s3._tstrain == 0.00001
assert s3._tstress > 0.0
assert s3.get_force() == s3._tstress
s3.commit()
assert s3._cstress == s3._tstress
print('[OK] SpringHysteretic revert + trial + commit OK')

print('\nAll backward-compatibility checks PASSED')
