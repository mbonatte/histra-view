param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
Add-Type -ReferencedAssemblies @((Join-Path $InstalledRoot 'ModelLibrary.dll'),(Join-Path $InstalledRoot 'MonoGame.Framework.dll')) -TypeDefinition @'
public class EnergySpringProbe : Objects.Spring {
 public override void TurnOn() {} public override void TurnOff() {}
 protected override double TrialStrain { get { return 4.0; } }
 protected override double CommitStrain { get { return 0.0; } }
 protected override double TrialStress { get { return 1.0; } }
 protected override double CommitStress { get { return 0.0; } }
}
'@
$ctor=[ModelLibrary.Model].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 2}|Select-Object -First 1
$model=$ctor.Invoke([object[]]@([enum]::Parse($ctor.GetParameters()[0].ParameterType,'RailBridge'),$false))
for($j=1;$j -le 3;$j++) {$q=[Objects.Quad]::new();$q.Key=$j;$s=[EnergySpringProbe]::new();$s.K=0.5;$q.Spring=$s;$model.Collections.Quads.Collection.Add($j,$q)}
$method=[SolverRuntime.ModelManager].GetMethod('ComputeEnergy',[Reflection.BindingFlags]'Static,NonPublic')
$rows=@()
foreach($seed in @(0.0,1.0,1e16,-1e16)) {
 $args=[object[]]@($model.Collections,[double]$seed,[double]$seed)
 [void]$method.Invoke($null,$args)
 $rows+=@{seed=$seed;elastic_bits=[BitConverter]::DoubleToInt64Bits([double]$args[1]).ToString();plastic_bits=[BitConverter]::DoubleToInt64Bits([double]$args[2]).ToString()}
}
@{source='Original ModelManager.ComputeEnergy -> Quad.ComputeEnergy -> Spring.ComputeEnergy; three controlled unit increments, nonzero initial totals';cases=$rows}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $OutputPath -Encoding UTF8
