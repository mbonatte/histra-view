param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$flags=[Reflection.BindingFlags]'Instance,Public,NonPublic'
$type=[SolverRuntime.Program].Assembly.GetType('SolverRuntime.Integrator.LoadControl')
$lf=[Objects.Analyses.LoadFunction]::new();$lf.DiscrVal=0.1
$items=[Collections.Generic.SortedList[int,Objects.Analyses.LoadFunctionItem]]::new()
$first=[Objects.Analyses.LoadFunctionItem]::new();$first.pseudoTime=0;$first.multiplier=0
$last=[Objects.Analyses.LoadFunctionItem]::new();$last.pseudoTime=1;$last.multiplier=1
$items.Add(1,$first);$items.Add(2,$last)
$rows=@()
foreach($case in @(@(0.8999999999999999,0.8999999999999999,1.0),@(0.95,0.94,1.0),@(0.9,1.7,2.0),@(1.0,1.0,1.0))) {
 $control=[Activator]::CreateInstance($type,$true)
 $type.GetField('LF',$flags).SetValue($control,$lf)
 $type.GetField('LFitems',$flags).SetValue($control,$items)
 $an=[Objects.Analyses.Analysis]::new();$an.Mult=[double]$case[2]
 $type.GetField('State',$flags).GetValue($control).Analysis=$an
 $dt=[double]$type.GetMethod('GetDt',$flags).Invoke($control,[object[]]@([double]$case[0],[double]$case[1]))
 $df=[double]$type.GetMethod('GetIncrMult',$flags).Invoke($control,[object[]]@([double]$case[0],[double]$case[1]))
 $rows+=@{time=$case[0];mult=$case[1];analysis_mult=$case[2];dt_bits=[BitConverter]::DoubleToInt64Bits($dt).ToString();df_bits=[BitConverter]::DoubleToInt64Bits($df).ToString()}
}
@{source='Original LoadControl.GetDt and GetIncrMult final-interval branch';cases=$rows}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $OutputPath -Encoding UTF8
