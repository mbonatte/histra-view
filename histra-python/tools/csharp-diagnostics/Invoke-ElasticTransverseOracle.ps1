param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model])
[ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
function New-Law($elastic) {
 if($elastic) {$law=[Objects.ConstitutiveLaw.ConstitutiveLawElastic]::new();$law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::LinearElastic}
 else {
  $law=[Objects.ConstitutiveLaw.ConstitutiveLawHysteretic]::new();$law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::Hysteretic
  $law.Fy_t=0.2;$law.Fy_c=3.0;$law.Eps_u_t=0.04;$law.Eps_u_c=0.06
  $law.G[0]=0.03;$law.G[1]=0.05;$law.Alfa_r[0]=1;$law.Alfa_r[1]=1
  $law.TensileCurveType=[UtilityLibrary.Tipi.HystereticTensileCurveTypeEnum]::LinearSoftening
  $law.CompressiveCurveType=[UtilityLibrary.Tipi.HystereticCompressiveCurveTypeEnum]::LinearSoftening
 }
 $law.E=500.0;return $law
}
$combiner=[ModelManagement.ComputationalElementsOperations.SpringOperations].GetMethod('CombinationSpring',[Type[]]@([Objects.Spring],[Objects.Spring],[bool]))
$rows=@()
foreach($pair in @(@($true,$true),@($true,$false),@($false,$true))) {
 foreach($restraint in @($false,$true)) {
  if($restraint -and -not $pair[0]) {continue}
  $l1=New-Law $pair[0];$l2=New-Law $pair[1]
  $s1=[ModelManagement.ComputationalElementsOperations.SpringOperations]::NewSpring($l1.Type)
  $s2=[ModelManagement.ComputationalElementsOperations.SpringOperations]::NewSpring($l2.Type)
  $k1=80.0;if($restraint) {$k1=-1.0}
  if($k1 -eq -1.0) {$s1.K=-1.0;$s1.Area=4.0} else {$s1.SetQuadTrasvSpring($k1,4.0,0.8,$l1)}
  $s2.SetQuadTrasvSpring(120.0,9.0,1.1,$l2)
  $s=$combiner.Invoke($null,[object[]]@($s1,$s2,$restraint))
  $s.SetUltimateDisplacement($l1,$l2)
  if($s -is [Objects.SpringHysteretic]) {$s.initialize()}
  $s.SetInitial()
  $initial=@{K=$s.K;Area=$s.Area;Length=$s.Length;type=$s.GetType().Name}
  $states=@()
  foreach($u in @(0.0001,0.001,0.01,0.2,-0.005,-0.02,-0.2,0.003,0.0)) {
   $s.U=[double]$u;[void]$s.setTrialStrain([double]$u);$s.Commit()
   $states+=@{u=$u;F=$s.GetForce();K_tang=$s.K_tang;Phase=[int]$s.Phase}
  }
  $rows+=@{elastic1=$pair[0];elastic2=$pair[1];restrained=$restraint;k1=$k1;k2=120.0;area1=4.0;area2=9.0;length1=0.8;length2=1.1;initial=$initial;states=$states}
 }
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');generator='tools/csharp-diagnostics/Invoke-ElasticTransverseOracle.ps1';assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();source='Original NewSpring, SetQuadTrasvSpring, CombinationSpring(Spring,Spring,bool), SetUltimateDisplacement, setTrialStrain and Commit';cases=$rows}|ConvertTo-Json -Depth 7|Set-Content -LiteralPath $OutputPath -Encoding UTF8
