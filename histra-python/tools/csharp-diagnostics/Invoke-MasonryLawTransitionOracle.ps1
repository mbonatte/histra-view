param([Parameter(Mandatory=$true)][string]$InputPath,
      [Parameter(Mandatory=$true)][string]$OutputPath,
      [string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $OutputPath) {throw 'Use a new output file; reference evidence is never overwritten'}
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','ModelLibrary.dll')) {
 [void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))
}
$model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model])
[ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
$ctor=[Objects.SpringHysteretic].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 24}
function New-Target($definition) {
 if($definition.law -eq 'Elastic') {
  $spring=[Objects.SpringLinearElastic]::new()
 } else {
  $u=$definition.u;$f=$definition.f
  $spring=$ctor.Invoke([object[]]@([double]$f[0],[double]$u[0],[double]$f[1],[double]$u[1],[double]$f[2],[double]$u[2],
   (-[double]$f[0]),(-[double]$u[0]),(-[double]$f[1]),(-[double]$u[1]),(-[double]$f[2]),(-[double]$u[2]),
   0.,0.,0.,0.,0.,0.,0.,0.,0.,0.,
   [UtilityLibrary.Tipi.HystereticTensileCurveTypeEnum]::LinearHardening,
   [UtilityLibrary.Tipi.HystereticCompressiveCurveTypeEnum]::LinearHardening))
 }
 $spring.K=[double]$definition.k;$spring.SetInitial()
 return $spring
}
function Get-State($spring) {
 $v=@{K=$spring.K;K_tang=$spring.K_tang;U=$spring.U;F=$spring.F;Force=$spring.GetForce();
      Increment=$spring.GetIncrForce();Cstrain=$spring.Cstrain;Cstress=$spring.Cstress;Phase=[double][int]$spring.Phase}
 if($spring -is [Objects.SpringHysteretic]) {
  $v.Umax0=$spring.Umax[0];$v.Umax1=$spring.Umax[1];$v.Uy0=$spring.Uy_corr[0];$v.Uy1=$spring.Uy_corr[1]
  $v.Fy0=$spring.Fy[0];$v.Fy1=$spring.Fy[1];$v.CrotPu=$spring.CrotPu;$v.CrotNu=$spring.CrotNu
  $v.CloadIndicator=[double]$spring.CloadIndicator;$v.F0=$spring.F0
 }
 $bits=@{};foreach($key in $v.Keys) {$bits[$key]=[BitConverter]::DoubleToInt64Bits([double]$v[$key]).ToString()}
 return @{values=$v;bits=$bits}
}
function Invoke-History($spring,$strains,$setBaseU=$false) {
 $rows=@()
 foreach($strain in $strains) {
  if($setBaseU) {$spring.U=[double]$strain}
  [void]$spring.setTrialStrain([double]$strain);$trial=Get-State $spring
  $spring.Commit();$committed=Get-State $spring
  $rows+=@{strain=$strain;trial=$trial;committed=$committed}
 }
 return ,$rows
}
$inputs=Get-Content -LiteralPath $InputPath -Raw|ConvertFrom-Json
$cases=@()
foreach($case in $inputs.cases) {
 $spring=New-Target $case.source
 [void](Invoke-History $spring $case.strains $case.set_base_u_before_trial)
 $before=Get-State $spring;$resets=@()
 foreach($stage in $case.stages) {
  $saved=[Objects.ElementStates.SpringStateDBclass]::new()
  $saved.SetFromSpring($spring,0,0,[UtilityLibrary.Tipi.ElementTypeEnum]::None)
  $target=New-Target $stage.target
  $arguments=[object[]]@($target,$false)
  [void][Objects.ElementStates.SpringStateDBclass].GetMethod('SetSpring').Invoke($saved,$arguments)
  $restored=Get-State $target
  $resets+=@{restored=$restored;history=(Invoke-History $target $stage.strains $case.set_base_u_before_trial)}
  $spring=$target
 }
 $cases+=@{name=$case.name;before=$before;resets=$resets}
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');
 source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);
 generator='tools/csharp-diagnostics/Invoke-MasonryLawTransitionOracle.ps1';
 benchmark_id='masonry-hysteretic-elastic-return-2026.1.1';
 input_sha256=(Get-FileHash $InputPath -Algorithm SHA256).Hash.ToLowerInvariant();
 input_lf_sha256=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText($InputPath).Replace("`r`n","`n"))))).Replace('-','').ToLowerInvariant();
 assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();
 oracle_lf_sha256=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText($PSCommandPath).Replace("`r`n","`n"))))).Replace('-','').ToLowerInvariant();
 source='Original constructors, SetFromSpring, SetSpring(false), setTrialStrain and Commit';
 exclusions=@('Energy-retention policy is not qualified by this fixture.');inputs=$inputs;cases=$cases}|
 ConvertTo-Json -Depth 20|Set-Content -LiteralPath $OutputPath -Encoding UTF8
