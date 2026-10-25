param([Parameter(Mandatory=$true)][string]$ModelPath,
      [Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$AnalysisKeys='1',
      [string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
$out=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $out) {throw 'Use a new output directory; existing results are never overwritten'}
[void][IO.Directory]::CreateDirectory($out)
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {
 [void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))
}
Add-Type -TypeDefinition 'using System.Runtime.InteropServices; public static class NativeAnalysisLibraryPath { [DllImport("kernel32", CharSet=CharSet.Unicode)] public static extern bool SetDllDirectory(string path); }'
[void][NativeAnalysisLibraryPath]::SetDllDirectory((Join-Path $InstallDirectory 'x64'))
$flags=[Reflection.BindingFlags]'Static,Public,NonPublic'
$instance=[Reflection.BindingFlags]'Instance,Public,NonPublic'
$ctor=[ModelLibrary.Model].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 2}|Select-Object -First 1
$model=$ctor.Invoke([object[]]@([enum]::Parse($ctor.GetParameters()[0].ParameterType,'RailBridge'),$false))
[void][SirioSoft.SerializeXmlReader].GetMethod('ReadFromFile',[Type[]]@([string],[string],[object])).Invoke($null,[object[]]@([IO.Path]::GetFullPath($ModelPath),'HiStrA',$model))
[ModelLibrary.Model].GetField('_model',$flags).SetValue($null,$model)
$model.IsLocked=$false
$p=[SolverRuntime.Program]::new()
[SolverRuntime.Program].GetField('model',$instance).SetValue($p,$model)
[SolverRuntime.Program].GetField('_LS',$instance).SetValue($p,[MatrixManager.LinearSystem]::new())
$results=Join-Path $out 'native.Results'
[DBManagement.DatabaseManager]::Init($results)
[DBManagement.DatabaseManager]::database.Open()
try {
 [SolverRuntime.ModelManager]::PrepareModel_Nuovo($p,$model,$false,$null)
 $states=@()
 foreach($keyText in $AnalysisKeys.Split(',')) {
  $key=[int]$keyText;$an=$model.Collections.Analyses[$key]
  $an.States.Clear()
  $state=[Objects.Analyses.AnalysisState]::new();$state.Key=$key;$state.Combination=1
  $an.States.Add(1,$state)
  $an.SetDirectionAngleInSimpleMode()
  $lock=[DBManagement.DatabaseManager]::database.Lock()
  try {
   [void][SolverRuntime.ModelManager].GetMethod('PrepareModelForAnalysis',$flags).Invoke($null,[object[]]@($p,$model.Collections,$an,[int]1,$null))
   $index=[SolverRuntime.Program].GetProperty('IndexFactK',$instance).GetValue($p,$null)
   if($index -ne 0) {throw "Initial native factorization failed: $index"}
   [void][SolverRuntime.Program].GetMethod('ExecuteAnalysis',$instance).Invoke($p,[object[]]@($model.Collections,$an,[int]1))
  } finally {$lock.Dispose()}
  [DBManagement.DatabaseManager]::database.FlushAndWait()
  $states+=@{key=$key;step=$state.Step;state=[string]$state.State;exit=[string]$state.Exit}
  Write-Output "Analysis $key finished: state_saved_step=$($state.Step), exit=$($state.Exit)"
 }
 @{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);
 generator='tools/csharp-diagnostics/Invoke-NativeAnalysisOracle.ps1';benchmark_id='independent-native-analysis-2026.1.1';
 model_sha256=(Get-FileHash $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant();
 assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'SolverRuntime.dll') -Algorithm SHA256).Hash.ToLowerInvariant();
  state_step_semantics='AnalysisState.Step is the last regular saved step, not necessarily the final committed step.';
  process_id=$PID;analyses=$states} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $out 'execution.json') -Encoding UTF8
} finally {[DBManagement.DatabaseManager]::Close()}
