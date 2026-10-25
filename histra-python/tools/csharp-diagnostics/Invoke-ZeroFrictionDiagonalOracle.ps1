param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
function Set-Material($m,$name,$value) {$p=[Objects.Material.MasonryMaterial].GetProperty($name);$p.SetValue($m,[Convert]::ChangeType($value,$p.PropertyType),$null)}
function Bits($values) {return @($values|ForEach-Object{[BitConverter]::DoubleToInt64Bits([double]$_).ToString()})}
$geometries=@(
 @{name='rectangle';points=@(@(0.,0.),@(100.,0.),@(100.,200.),@(0.,200.));thickness=@(10,10,10,10)},
 @{name='tapered-skew';points=@(@(0.,0.),@(137.2,0.),@(129.4,211.3),@(-13.1,183.7));thickness=@(8.3,10.1,12.4,9.7)}
)
$rows=@()
foreach($geometry in $geometries) {foreach($fracture in @($false,$true)) {foreach($fc in @(2.7,.01)) {
 $coll=[ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
 $model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model]);$model.Collections=$coll
 [ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
 $mat=[Objects.Material.MasonryMaterial]::new();[Objects.Material.MasonryMaterial].GetProperty('Key').SetValue($mat,[int]1,$null);$coll.Templates.Add(1,$mat)
 $properties=@{Gd=184.;AlfaShearUser=.8;FrictionRatioShear=0.;FmHor=$fc;fvk0d=.5;ShearUltimateStrain=.015;RatioEtCompression=.0001;RatioEtTraction=.001;FractureEnergyShear=.03}
 foreach($name in $properties.Keys) {Set-Material $mat $name $properties[$name]}
 [Objects.Material.MasonryMaterial].GetProperty('CriterioSnervamento').SetValue($mat,[UtilityLibrary.Tipi.ShearYieldingDomainEnum]::Coulomb,$null)
 $shearType=if($fracture){'ElastoPlasticFractureEnergyFixed'}else{'ElastoPlasticDuctilityFixed'}
 [Objects.Material.MasonryMaterial].GetProperty('ConstitutiveLawMasonryShear').SetValue($mat,[enum]::Parse([UtilityLibrary.Tipi.ConstitutiveLawMasonryShearEnum],$shearType),$null)
 [void][ModelManagement.ComputationalElementsOperations.ConstitutiveLawOperations].GetMethod('SetShearConstitutiveLaw',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,[object[]]@($mat,$coll))
 $shear=@($coll.ConstitutiveLaws|Where-Object{$_.Collocation.ToString() -eq 'Shear'})[0]
 foreach($kind in @('HorizontalFlexional','VerticalFlexional')) {
  $law=[Objects.ConstitutiveLaw.ConstitutiveLawHysteretic]::new();$law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::Hysteretic;$law.E=if($kind -eq 'HorizontalFlexional'){500.}else{321.25}
  $law.MaterialKey=1;$law.Collocation=[enum]::Parse([UtilityLibrary.Tipi.ConstitutiveLawCollocation],$kind);$coll.ConstitutiveLaws.Insert($law)
 }
 $q=[Objects.Quad]::new();$q.MaterialKey=1;$nodes=[Collections.Generic.List[Objects.Node]]::new()
 foreach($xy in $geometry.points) {$n=[Objects.Node]::new();[Objects.Node].GetProperty('Point').SetValue($n,[Microsoft.Xna.Framework.Vector3]::new([single]$xy[0],[single]$xy[1],0),$null);$nodes.Add($n)}
 $q.Thickness=[single[]]$geometry.thickness;$q.Normal=[Microsoft.Xna.Framework.Vector3[]]@([Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ)
 [void]$q.SetGeometry($nodes,$false,$false);$q.SetDiagonalQuad();$s=$q.Spring;$s.SetInitial()
 $initial=@{K=(Bits $s.K);Area=(Bits $s.Area);Length=(Bits $s.Length);Fy=(Bits $s.Fy);Ur=(Bits $s.Ur);Kt=(Bits $s.Kt);Alfar=(Bits $s.Alfar);Alfau=(Bits $s.Alfau);type=$s.GetType().Name}
 $yield=$s.Fy[0]/$s.K;$strains=@(0.,(.2*$yield),(1.2*$yield),(.8*$yield),(-.3*$yield),(-1.5*$yield),(-.4*$yield),(.4*$yield),(1.5*$yield),0.,(1.05*$s.Ur[0]),0.,(1.05*$s.Ur[1]),0.)
 $accepted=.5*$yield;$failed=1.05*$s.Ur[0]
 $s.U=$accepted;[void]$s.setTrialStrain($accepted);$s.Commit()
 $s.U=$failed;[void]$s.setTrialStrain($failed);$s.RevertToLastCommit()
 $rollback=@{accepted=(Bits $accepted);failed=(Bits $failed);F=(Bits $s.GetForce());K_tang=(Bits $s.K_tang);Cstrain=(Bits $s.Cstrain);Tstrain=(Bits $s.Tstrain);Phase=[int]$s.Phase;TPhase=[int]$s.TPhase}
 $s.SetInitial()
 $states=@()
 foreach($u in $strains) {$s.U=[double]$u;[void]$s.setTrialStrain([double]$u);$s.Commit();$states+=@{u=(Bits $u);F=(Bits $s.GetForce());K_tang=(Bits $s.K_tang);Phase=[int]$s.Phase;Umax=(Bits $s.Umax);energy=(Bits $s.CenergyD)}}
 $rows+=@{geometry=$geometry.name;properties=$properties;shear_type=$shearType;law_type=$shear.GetType().Name;law_E=(Bits $shear.E);law_Fyt=(Bits $shear.Fy_t);law_Fyc=(Bits $shear.Fy_c);law_eps=(Bits @($shear.Eps_u_t,$shear.Eps_u_c));initial=$initial;states=$states;rollback=$rollback;geometry_bits=@{Length=(Bits $q.Length);Diago=(Bits $q.Diago);Sin=(Bits $q.Sin);Cos=(Bits $q.Cos);thickness=(Bits @($q.Thickness|ForEach-Object{[double]$_}))}}
}}}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');generator='tools/csharp-diagnostics/Invoke-ZeroFrictionDiagonalOracle.ps1';assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();source='Original SetShearConstitutiveLaw, Quad.SetDiagonalQuad, SpringHysteretic setTrialStrain and Commit; double fields encoded as int64 bit strings';cases=$rows}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $OutputPath -Encoding UTF8
