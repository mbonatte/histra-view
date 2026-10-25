"""Backward-compat re-export — springs now live in ``histra.springs``."""
from histra.types.phase_enum import PhaseEnum
from histra.types.hysteretic_curve_types import (
    HystereticTensileCurveTypeEnum,
    HystereticCompressiveCurveTypeEnum,
)
from histra.springs.base import Spring
from histra.springs.elastic import SpringElastic
from histra.springs.coulomb import SpringCoulomb
from histra.springs.coulomb03 import SpringCoulomb03
from histra.springs.hysteretic import SpringHysteretic
from histra.springs.multilinear import SpringMultiLinear
from histra.springs.registry import _SPRING_REGISTRY, _register_spring, spring_from_xml
from histra.springs.transverse_fiber_group import TransverseFiberGroup

__all__ = [
    "PhaseEnum",
    "HystereticTensileCurveTypeEnum",
    "HystereticCompressiveCurveTypeEnum",
    "Spring",
    "SpringElastic",
    "SpringCoulomb",
    "SpringCoulomb03",
    "SpringHysteretic",
    "SpringMultiLinear",
    "TransverseFiberGroup",
    "_SPRING_REGISTRY",
    "_register_spring",
    "spring_from_xml",
]
