param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$env:PATH=(Join-Path $InstalledRoot 'x64')+';'+$env:PATH
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$flags=[Reflection.BindingFlags]'Instance,Public,NonPublic'
$static=[Reflection.BindingFlags]'Static,Public,NonPublic'
$type=[SolverRuntime.Program].Assembly.GetType('SolverRuntime.Integrator.ArcLength')
$base=$type.BaseType.BaseType
$ctor=[ModelLibrary.Model].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 2}|Select-Object -First 1
$model=$ctor.Invoke([object[]]@([enum]::Parse($ctor.GetParameters()[0].ParameterType,'RailBridge'),$false))
$model.GDL=1
[ModelLibrary.Model].GetField('_model',$static).SetValue($null,$model)
$p=[Activator]::CreateInstance([SolverRuntime.Program])
[SolverRuntime.Program].GetField('model',$flags).SetValue($p,$model)
$ls=[MatrixManager.LinearSystem]::new();$ls.K=[MatrixManager.SparseMatrix]::new(1)
$ls.K.Set(0,0,1.0);$ls.InitVectors()
if(!$ls.SymbolicFactorization() -or $ls.K.NumericFactorization() -ne 0) {throw 'Native identity factorization failed'}
[SolverRuntime.Program].GetField('_LS',$flags).SetValue($p,$ls)
[SolverRuntime.ModelManager].GetField('_Ptarget',$static).SetValue($null,[MatrixManager.Vector]::new(1))
[SolverRuntime.ModelManager].GetField('_Fext',$static).SetValue($null,[MatrixManager.Vector]::new(1))
$an=[Objects.Analyses.Analysis]::new()
$rows=@()
$cases=@(@(0.0,1.1,0.3,0.01),@(0.0,0.0037,1.8e-8,0.01),@(0.2,1.1,-0.3,0.4),@(0.0,1.3,-0.7,-0.02),@(1.0,1.0,1.0,0.1),@(0.0,1e-16,0.3,0.1),@(0.0,0.0,0.3,0.1,-10),@(1.0,1.0,1.0,0.0,-10))
$cases+=@(@(0.0,2.0,0.5,0.02),@(1.0,1.5,-0.2,0.05),@(0.5,3.0,1.2,-0.01))
foreach($case in $cases) {
 $arc=[Activator]::CreateInstance($type,$true)
 foreach($name in @('deltaUhat','deltaUbar','deltaU','deltaUstep','phat')) {$v=[MatrixManager.Vector]::new(1);$type.GetField($name,$flags).SetValue($arc,$v)}
 $type.GetField('alpha2',$flags).SetValue($arc,[double]$case[0])
 $type.GetField('phat',$flags).GetValue($arc).Set(0,[double]$case[1])
 $type.GetField('deltaUstep',$flags).GetValue($arc).Set(0,[double]$case[3])
 $type.GetField('dofs',$flags).SetValue($arc,[int[]]@(0))
 $base.GetField('U',$flags).SetValue($arc,[MatrixManager.Vector]::new(1))
 $ls.SetX(0,[double]$case[2])
 $code=$type.GetMethod('Update',$flags).Invoke($arc,[object[]]@($model.Collections,$p,$an))
 $expected=0;if($case.Length -eq 5) {$expected=[int]$case[4]}
 if($code -ne $expected) {throw "Unexpected native Update status: $code"}
 if($type.GetField('deltaUhat',$flags).GetValue($arc).Get(0) -ne [double]$case[1]) {throw 'Native reference solve did not return the identity solution'}
 $dl=[double]$type.GetField('deltaLambdaStep',$flags).GetValue($arc)
 $du=[double]$type.GetField('deltaU',$flags).GetValue($arc).Get(0)
 $rows+=@{alpha2=$case[0];hat=$case[1];bar=$case[2];step=$case[3];code=$code;lambda_bits=[BitConverter]::DoubleToInt64Bits($dl).ToString();du_bits=[BitConverter]::DoubleToInt64Bits($du).ToString()}
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');
 source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);
 generator='tools/csharp-diagnostics/Invoke-ArcLengthUpdateOracle.ps1';
 benchmark_id='native-arclength-identity-update-2026.1.1';
 assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'SolverRuntime.dll') -Algorithm SHA256).Hash.ToLowerInvariant();
 source='Original SolverRuntime.Integrator.ArcLength.Update; identity native UMFPACK system';cases=$rows}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $OutputPath -Encoding UTF8
