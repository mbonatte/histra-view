param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
function Bits($values) {return @($values|ForEach-Object{[BitConverter]::DoubleToInt64Bits([double]$_).ToString()})}
function Vector($a) {return [Microsoft.Xna.Framework.Vector3]::new([single]$a[0],[single]$a[1],[single]$a[2])}
function Set-Material($m,$name,$value) {$p=[Objects.Material.MasonryMaterial].GetProperty($name);if($null -eq $p){throw ('Unknown material property '+$name)};$v=if($p.PropertyType.IsEnum){[enum]::Parse($p.PropertyType,[string]$value)}else{[Convert]::ChangeType($value,$p.PropertyType)};$p.SetValue($m,$v,$null)}
$axes=@(@{p2=@(100.,0.,0.);i=@(1.,0.,0.)},@{p2=@(0.,100.,0.);i=@(0.,1.,0.)},@{p2=@(3.,4.,0.);i=@(1.,0.,0.)},@{p2=@(.1234567,.2345678,.3456789);i=@(.6,.8,0.)})
$rows=@()
foreach($axis in $axes) {foreach($elastic in @('none','horizontal','vertical')) {
 $coll=[ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
 $mat=[Objects.Material.MasonryMaterial]::new()
 $props=@{Ehor=5.3;Ever=17.7;FmHor=2.7;FmVer=4.3;FtmHor=.23;FtmVer=.31;IsDuctCompr=$false;IsDuctTraz=$false;DuctComprRockingHor=3.1;DuctComprRockingVer=4.7;DuctTrazRockingHor=5.2;DuctTrazRockingVer=6.3;RatioEtTraction=.001;RatioEtCompression=.0001;Gt=.03;Gc=.05;GtVer=.07;GcVer=.11;BetaUnloadTractionRockingHor=.2;BetaUnloadCompressionRockingHor=.3;BetaUnloadTractionRockingVer=.4;BetaUnloadCompressionRockingVer=.5;TensileCurveType='LinearSoftening';CompressiveCurveType='LinearHardening';TensileCurveTypeVertical='Exponential';CompressiveCurveTypeVertical='Parabolic';Gd=184.;AlfaShearUser=.8;scorrhor=$true;scorrvert=$true;CriterioSnervamento='Coulomb';SlidingYieldingDomainHor='Coulomb';SlidingYieldingDomainVert='Coulomb';CohesionSlidingHor=.2;CohesionSlidingVert=.7;FrictionRatioSlidingHor=.3;FrictionRatioSlidingVert=.6;SlidingPlasticStiffnessRatioHor=.001;SlidingPlasticStiffnessRatioVer=.002;SlidingMaxTensileRatioHor=.4;SlidingMaxTensileRatioVer=.8;SlidingFractureEnergy=$false;SlidingFractureEnergyVer=$false}
 if($elastic -eq 'horizontal') {$props.TensileCurveType='Elastic';$props.CompressiveCurveType='Elastic';$props.scorrhor=$false}
 if($elastic -eq 'vertical') {$props.TensileCurveTypeVertical='Elastic';$props.CompressiveCurveTypeVertical='Elastic';$props.scorrvert=$false}
 foreach($name in $props.Keys) {Set-Material $mat $name $props[$name]}
 foreach($name in @('SetFlexionalConstitutiveLaw','SetInPlaneSlidingConstitutiveLaw','SetOutOfPlaneSlidingConstitutiveLaw')) {$method=[ModelManagement.ComputationalElementsOperations.ConstitutiveLawOperations].GetMethods([Reflection.BindingFlags]'Static,NonPublic')|Where-Object{$_.Name -eq $name -and $_.GetParameters()[0].ParameterType -eq [Objects.Material.MasonryMaterial]};[void]$method.Invoke($null,[object[]]@($mat,$coll))}
 $r=[Objects.Restraint]::new(0,[UtilityLibrary.Tipi.ElementTypeEnum]::Quad,1,[UtilityLibrary.Tipi.ElementTypeEnum]::Quad,0,(Vector @(0.,0.,0.)),(Vector $axis.p2),1,2,[single]0.)
 $intf=[Objects.Interface]::new();$irs=[Objects.Interface].GetProperty('ReferenceSystem').GetValue($intf,$null);$irs.e1=Vector $axis.i
 $laws=@{};foreach($law in $coll.ConstitutiveLaws) {$laws[$law.Collocation.ToString()]=$law}
 $expected=@{}
 foreach($pair in @(@('HorizontalFlexional','VerticalFlexional'),@('InplaneSlidingHorizontal','InplaneSlidingVertical'),@('OutOfPlaneSlidingHorizontal','OutOfPlaneSlidingVertical'))) {
  $first=$laws[$pair[0]];$second=$laws[$pair[1]]
  if($null -eq $first -or $null -eq $second){throw ('Missing law slots '+($laws.Keys -join ','))}
  $first.PropOrthotropyParameter($r,$intf,$second)
  $fields=@{E=(Bits $first.E);type=$first.GetType().Name}
  if($second -is [Objects.ConstitutiveLaw.ConstitutiveLawCoulomb]) {$fields.secondary_plastic_ratio=Bits $second.PlasticStiffnessRatio}
  if($first -is [Objects.ConstitutiveLaw.ConstitutiveLawHysteretic]) {
   foreach($n in @('Fy_t','Fy_c','Eps_u_t','Eps_u_c','RatioEttrac','RatioEtcomp')) {$fields[$n]=Bits $first.$n}
   $fields.G=Bits $first.G;$fields.Alfa_r=Bits $first.Alfa_r;$fields.Alfa_u=Bits $first.Alfa_u
   $fields.TensileCurveType=$first.TensileCurveType.ToString();$fields.CompressiveCurveType=$first.CompressiveCurveType.ToString()
  } elseif($first -is [Objects.ConstitutiveLaw.ConstitutiveLawCoulomb]) {$fields.is_ductility_fixed=$first.IsDuctilityFixed;foreach($n in @('Fy_0','Mu','U_r','PlasticStiffnessRatio')) {$fields[$n]=Bits $first.$n}}
  $expected[$pair[0]]=$fields
 }
 $rows+=@{p1=@(0.,0.,0.);p2=$axis.p2;interface_e1=$axis.i;restraint_e1_bits=Bits @([double]$r.ReferenceSystem.e1.X,[double]$r.ReferenceSystem.e1.Y,[double]$r.ReferenceSystem.e1.Z);properties=$props;expected=$expected}
}}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');generator='tools/csharp-diagnostics/Invoke-RestraintOrientationOracle.ps1';assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();source='Original line-Restraint constructor; native material law builders; ConstitutiveLawBase.PropOrthotropyParameter(Element,Element,law)';cases=$rows}|ConvertTo-Json -Depth 9|Set-Content -LiteralPath $OutputPath -Encoding UTF8
