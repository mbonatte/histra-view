param([Parameter(Mandatory=$true)][string]$InputPath,
      [Parameter(Mandatory=$true)][string]$OutputPath,
      [string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','ModelLibrary.dll')) {
 [void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))
}
$model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model])
[ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
$ctor=[Objects.SpringHysteretic].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 24}
function Get-LfHash($path) {
 $bytes=[Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText([IO.Path]::GetFullPath($path)).Replace("`r`n","`n"))
 return ([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash($bytes))).Replace('-','').ToLowerInvariant()
}
function New-MasonrySpring($definition) {
 $u=$definition.u;$f=$definition.f
 $parameters=[object[]]@([double]$f[0],[double]$u[0],[double]$f[1],[double]$u[1],[double]$f[2],[double]$u[2],
  (-[double]$f[0]),(-[double]$u[0]),(-[double]$f[1]),(-[double]$u[1]),(-[double]$f[2]),(-[double]$u[2]),
  0.,0.,0.,0.,0.,0.,0.,0.,0.,0.,
  [UtilityLibrary.Tipi.HystereticTensileCurveTypeEnum]::LinearHardening,
  [UtilityLibrary.Tipi.HystereticCompressiveCurveTypeEnum]::LinearHardening)
 $spring=$ctor.Invoke($parameters)
 $spring.K=[double]$definition.k
 $spring.SetInitial()
 return $spring
}
function Get-SpringState($spring) {
 $values=@{K=$spring.K;K_tang=$spring.K_tang;U=$spring.U;F=$spring.F;
  Force=$spring.GetForce();Increment=$spring.GetIncrForce();Cstrain=$spring.Cstrain;Cstress=$spring.Cstress;
  Umax0=$spring.Umax[0];Umax1=$spring.Umax[1];Uy0=$spring.Uy_corr[0];Uy1=$spring.Uy_corr[1];
  Fy0=$spring.Fy[0];Fy1=$spring.Fy[1];CrotPu=$spring.CrotPu;CrotNu=$spring.CrotNu;
  F0=$spring.F0;CloadIndicator=[double]$spring.CloadIndicator;Phase=[double][int]$spring.Phase;
  TPhase=[double][int]$spring.TPhase}
 foreach($field in @('_TrotMax','_TrotMin','_TrotPu','_TrotNu','_TenergyD','_TloadIndicator','_Tstress','_Tstrain')) {
  $values[$field.Substring(1)]=[double][Objects.SpringHysteretic].GetField($field,[Reflection.BindingFlags]'Instance,NonPublic').GetValue($spring)
 }
 $values['CenergyD']=$spring.CenergyD
 $bits=@{}
 foreach($key in $values.Keys) {$bits[$key]=[BitConverter]::DoubleToInt64Bits([double]$values[$key]).ToString()}
 return @{values=$values;bits=$bits}
}
function Invoke-History($spring,$strains) {
 $states=@()
 foreach($strain in $strains) {
  [void]$spring.setTrialStrain([double]$strain)
  $trial=Get-SpringState $spring
  $spring.Commit()
  $states+=@{strain=$strain;trial=$trial;committed=(Get-SpringState $spring)}
 }
 return ,$states
}
$inputs=Get-Content -LiteralPath $InputPath -Raw|ConvertFrom-Json
$backbones=@();$transfers=@()
foreach($case in $inputs.backbones) {
 $spring=New-MasonrySpring $case.definition
 $backbones+=@{name=$case.name;initial=(Get-SpringState $spring);history=(Invoke-History $spring $case.strains)}
}
foreach($case in $inputs.transfers) {
 $spring=New-MasonrySpring $case.definition
 [void](Invoke-History $spring $case.strains)
 if($case.PSObject.Properties.Name -contains 'f0') {$spring.F0=[double]$case.f0}
 $before=Get-SpringState $spring;$resets=@()
 for($i=0;$i -lt $case.targets.Count;$i++) {
  $saved=[Objects.ElementStates.SpringStateDBclass]::new()
  $saved.SetFromSpring($spring,0,0,[UtilityLibrary.Tipi.ElementTypeEnum]::None)
  $target=New-MasonrySpring $case.targets[$i]
  $arguments=[object[]]@($target,$false)
  [void][Objects.ElementStates.SpringStateDBclass].GetMethod('SetSpring').Invoke($saved,$arguments)
  $restored=Get-SpringState $target
  $history=Invoke-History $target $case.continuations[$i]
  $resets+=@{restored=$restored;history=$history}
  $spring=$target
 }
 $transfers+=@{name=$case.name;before=$before;resets=$resets}
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');
 source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);
 generator='tools/csharp-diagnostics/Invoke-MasonrySpringStateOracle.ps1';
 benchmark_id='masonry-backbone-and-state-transfer-2026.1.1';
 input_sha256=(Get-FileHash $InputPath -Algorithm SHA256).Hash.ToLowerInvariant();
 input_lf_sha256=(Get-LfHash $InputPath);
 assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();
 oracle_sha256=(Get-FileHash $PSCommandPath -Algorithm SHA256).Hash.ToLowerInvariant();
 oracle_lf_sha256=(Get-LfHash $PSCommandPath);
 source='Original SpringHysteretic constructor/SetInitial/setTrialStrain/Commit and SpringStateDBclass.SetFromSpring/SetSpring(false)';
 exclusions=@('CenergyD: Python deliberately retains predecessor energy; native DB restoration omits it.','Not SpringMultiLinearPlastic or complete staged structural analysis.');
 inputs=$inputs;backbones=$backbones;transfers=$transfers}|ConvertTo-Json -Depth 20|
 Set-Content -LiteralPath $OutputPath -Encoding UTF8
