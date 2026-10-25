from __future__ import annotations
from enum import Enum


class HystereticTensileCurveTypeEnum(Enum):
    Elastic = "Elastic"
    LinearHardening = "LinearHardening"
    LinearSoftening = "LinearSoftening"
    Exponential = "Exponential"


class HystereticCompressiveCurveTypeEnum(Enum):
    Elastic = "Elastic"
    LinearHardening = "LinearHardening"
    LinearSoftening = "LinearSoftening"
    Parabolic = "Parabolic"
