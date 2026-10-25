param([Parameter(Mandatory=$true)][string]$OutputPath,[string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))}
$flags=[Reflection.BindingFlags]'Instance,Public,NonPublic';$static=[Reflection.BindingFlags]'Static,Public,NonPublic'
$searchType=[SolverRuntime.Program].Assembly.GetType('SolverRuntime.LineSearch.LineSearch')
$arcType=[SolverRuntime.Program].Assembly.GetType('SolverRuntime.Integrator.ArcLength')
$base=$arcType.BaseType.BaseType
$rows=[Collections.Generic.List[object]]::new()
foreach($values in @(@(.8,.1,10.,.0123456789,.1),@(.7123456789,.123456789,9.87654321,.123456789,.234567891),@(.9123456789,.2123456789,4.123456789,.234567891,.123456789))) {
 $an=[Objects.Analyses.Analysis]::new();$an.Method=[enum]::Parse($an.Method.GetType(),'StandardBisectionLineSearch')
 $an.LineSearchTolerance=[single]$values[0];$an.LineSearchMinEta=[single]$values[1];$an.LineSearchMaxEta=[single]$values[2]
 $an.IsMaxArcLengthRay=$true;$an.MaxArcLengthRay=[single]$values[3];$an.UpdateDr2=$false
 $an.LoadReductionRatioToStopValue=[single]$values[4]
 $search=$searchType.GetMethod('NewLineSearch',$static).Invoke($null,[object[]]@($an))
 $arc=[Activator]::CreateInstance($arcType,$true)
 $base.GetField('U',$flags).SetValue($arc,[MatrixManager.Vector]::new(1));$base.GetField('U_commited',$flags).SetValue($arc,[MatrixManager.Vector]::new(1))
 $lf=[Activator]::CreateInstance($arcType.GetField('LFitems',$flags).FieldType)
 foreach($key in @(0,1)) {$item=[Objects.Analyses.LoadFunctionItem]::new();$item.multiplier=$key;$lf.Add($item)}
 $arcType.GetField('LFitems',$flags).SetValue($arc,$lf);$arcType.GetField('currentLFitem',$flags).SetValue($arc,[int]1)
 $arcType.GetField('targetDisplacement',$flags).SetValue($arc,[double]1)
 $arcType.GetField('arcLength2',$flags).SetValue($arc,[double]0.5)
 $arguments=[object[]]@($null,$an,[double]0,[int]0,$false)
 $stop=$arcType.GetMethod('Commit',$flags).Invoke($arc,$arguments)
 $rows.Add(@{inputs=$values;tolerance=$searchType.GetField('tolerance',$flags).GetValue($search);min_eta=$searchType.GetField('minEta',$flags).GetValue($search);max_eta=$searchType.GetField('maxEta',$flags).GetValue($search);arc_length2=$arcType.GetField('arcLength2',$flags).GetValue($arc);stop=$stop;reduction_threshold=[double]$an.LoadReductionRatioToStopValue})
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);generator='tools/csharp-diagnostics/Invoke-AnalysisPrecisionOracle.ps1';benchmark_id='native-analysis-setting-precision-2026.1.1';assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'SolverRuntime.dll') -Algorithm SHA256).Hash.ToLowerInvariant();cases=$rows}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $OutputPath -Encoding UTF8
