// Field groups follow IDEcontrols.Material.MasonryMaterialUserControl.InitAdvancedMode.
export const rockingGroups = [
  ['Elastic properties', [
    ["Young’s modulus, E", 'Ehor', 'Ever'],
  ]],
  ['Tensile', [
    ['Constitutive law', 'TensileCurveType', 'TensileCurveTypeVertical'],
    ['Tensile strength, ft', 'FtmHor', 'FtmVer'],
    ['Fracture energy, Gt', 'Gt', 'GtVer'],
    ['Tangent stiffness ratio', 'RatioEtTraction', 'RatioEtTractionVer'],
    ['Tensile ductility', 'DuctTrazRockingHor', 'DuctTrazRockingVer'],
    ['Unload behavior', 'UnloadTractionRockingHor', 'UnloadTractionRockingVer'],
    ['Unload parameter, β', 'BetaUnloadTractionRockingHor', 'BetaUnloadTractionRockingVer'],
  ]],
  ['Compression', [
    ['Constitutive law', 'CompressiveCurveType', 'CompressiveCurveTypeVertical'],
    ['Compressive strength, fm', 'FmHor', 'FmVer'],
    ['Fracture energy, Gc', 'Gc', 'GcVer'],
    ['Tangent stiffness ratio', 'RatioEtCompression', 'RatioEtCompressionVer'],
    ['Compressive ductility', 'DuctComprRockingHor', 'DuctComprRockingVer'],
    ['Unload behavior', 'UnloadCompressionRockingHor', 'UnloadCompressionRockingVer'],
    ['Unload parameter, β', 'BetaUnloadCompressionRockingHor', 'BetaUnloadCompressionRockingVer'],
    ['Rocking rotation limit', 'RotationLimitRockingHor', 'RotationLimitRockingVer'],
  ]],
];

export const shearGroups = [
  ['Constitutive model', [
    ['Constitutive law', 'ConstitutiveLawMasonryShear'],
    ['Yielding domain', 'CriterioSnervamento'],
    ['Shear modulus, G', 'Gd'],
    ['Shear strength, τ₀', 'fvk0d'],
    ['Friction ratio, μ', 'FrictionRatioShear'],
    ['Stiffness shear/sliding ratio, α', 'AlfaShearUser'],
  ]],
  ['Nonlinear parameters', [
    ['Ductility', 'DuctilityShear'],
    ['Strain energy', 'FractureEnergyShear'],
    ['Plastic stiffness ratio', 'ShearPlasticStiffnessRatio'],
    ['Second plastic stiffness ratio', 'ShearPlasticStiffnessRatio2'],
    ['Reload stiffness ratio', 'ShearReloadStiffnessRatio'],
    ['Maximum tensile ratio', 'ShearMaxTensileRatio'],
    ['Plastic shear strain', 'ShearPlasticStrain'],
    ['Ultimate shear strain', 'ShearUltimateStrain'],
    ['Cacovic coefficient, b', 'Bcacovic'],
  ]],
  ['Cyclic behavior', [
    ['Kinematic cycles enabled', 'HasKinCiclShear'], ['Kinematic parameter', 'AkinCiclShear'],
    ['Cyclic degradation enabled', 'CiclShear'], ['Cyclic parameter, α', 'AlfaCiclShear'],
    ['Cyclic parameter, γ', 'GammaCiclShear'], ['Unload behavior', 'UnloadShear'],
    ['Unload parameter, β', 'BetaUnloadShear'],
  ]],
];

export const slidingGroups = [
  ['Directional properties', [
    ['Nonlinear sliding', 'scorrhor', 'scorrvert', 'scorrDir3'],
    ['Fracture energy formulation', 'SlidingFractureEnergy', 'SlidingFractureEnergyVer', 'SlidingFractureEnergyDir3'],
    ['Yielding domain', 'SlidingYieldingDomainHor', 'SlidingYieldingDomainVert', 'SlidingYieldingDomainDir3'],
    ['Cohesion, c', 'CohesionSlidingHor', 'CohesionSlidingVert', 'CohesionSlidingDir3'],
    ['Friction ratio, μ', 'FrictionRatioSlidingHor', 'FrictionRatioSlidingVert', 'FrictionRatioSlidingDir3'],
    ['Plastic stiffness ratio', 'SlidingPlasticStiffnessRatioHor', 'SlidingPlasticStiffnessRatioVer', 'SlidingPlasticStiffnessRatioDir3'],
    ['Maximum tensile ratio', 'SlidingMaxTensileRatioHor', 'SlidingMaxTensileRatioVer', 'SlidingMaxTensileRatioDir3'],
    ['Fracture energy, Gs', 'Gs', 'GsVer', 'GsDir3'],
  ]],
];

export function displayValue(attributes, key) {
  const value = attributes[key];
  if (value === undefined || value === '') return '—';
  if (value === 'true') return 'Yes';
  if (value === 'false') return 'No';
  if (key.startsWith('DuctTrazRocking') && attributes.IsDuctTraz === 'false') return '∞';
  if (key.startsWith('DuctComprRocking') && attributes.IsDuctCompr === 'false') return '∞';
  // Preserve serialized numeric precision, zero values, and sentinel values.
  if (Number.isFinite(Number(value))) return String(value);
  return String(value).replace(/([a-z])([A-Z])/g, '$1 $2');
}

export function curveImage(kind, curve) {
  const names = { Elastic: 'elastic', LinearHardening: 'linear_hardening',
    LinearSoftening: 'linear_softening', Exponential: 'exponential_softening', Parabolic: 'parabolic' };
  return names[curve] ? `${kind}_${names[curve]}.png` : null;
}

export function shearImage(law) {
  const names = { Elastic: 'shear_elastic.png', ElastoPlastic: 'shear_plastic.png',
    ElastoPlasticAndSoftening: 'shear_linear_softening.png',
    ElastoPlasticDuctilityFixed: 'shear_ductility_fixed.png',
    ElastoPlasticFractureEnergyFixed: 'shear_ductility_fixed.png',
    ElastoPlasticEnergySigmaInterpolation: 'shear_ductility_fixed.png' };
  return names[law] ?? null;
}

export function slidingImage(attributes, nonlinear = 'scorrhor', energy = 'SlidingFractureEnergy') {
  if (attributes[nonlinear] === 'false') return 'shear_elastic.png';
  if (attributes[nonlinear] !== 'true') return null;
  return attributes[energy] === 'true' ? 'sliding_linear_softening.png' : 'shear_plastic.png';
}
