param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$q=[Objects.Quad]::new()
$q.G=[Microsoft.Xna.Framework.Vector3]::new(1.25,-2.5,1.1)
$q.ReferenceSystem.e1=[Microsoft.Xna.Framework.Vector3]::new(0.6,0.8,0)
$q.ReferenceSystem.e2=[Microsoft.Xna.Framework.Vector3]::new(-0.8,0.6,0)
$q.Length[3]=123.456789
for($j=0;$j -lt 4;$j++) {$q.Sin[$j]=@(0.9,0.7,0.6,0.8)[$j];$q.Cos[$j]=@(0.4,0.3,0.2,0.1)[$j]}
$point=[Microsoft.Xna.Framework.Vector3]::new(31.25,-12.5,7.3)
$rows=@()
foreach($u in @(@(0.123456789,-0.345678912,0.567891234,0.00023456789,-0.00123456789,0.00345678912,0.001234567891),@(0.0,0.0,0.0,0.0,0.0,0.0,1.234567891e-8))) {
 $state=[Objects.ElementStates.QuadState]::new()
 for($j=0;$j -lt 7;$j++) {$state.U[$j]=[double]$u[$j]}
 for($vertex=0;$vertex -lt 4;$vertex++) {
  $d=$q.DisplacementsCurrent($state,[single]1.0,$point,[int]$vertex,$true)
  $rows+=@{u=$u;u_bits=@($u|ForEach-Object{[BitConverter]::DoubleToInt64Bits([double]$_).ToString()});vertex=$vertex;bits=@([BitConverter]::ToInt32([BitConverter]::GetBytes($d.X),0).ToString(),[BitConverter]::ToInt32([BitConverter]::GetBytes($d.Y),0).ToString(),[BitConverter]::ToInt32([BitConverter]::GetBytes($d.Z),0).ToString())}
 }
}
@{source='Original Quad.DisplacementsCurrent(QuadState, Single, Vector3, Int32, Boolean)';cases=$rows;sin_bits=@($q.Sin|ForEach-Object{[BitConverter]::DoubleToInt64Bits($_).ToString()});cos_bits=@($q.Cos|ForEach-Object{[BitConverter]::DoubleToInt64Bits($_).ToString()});length_bits=[BitConverter]::DoubleToInt64Bits($q.Length[3]).ToString();e1=$q.ReferenceSystem.e1;e2=$q.ReferenceSystem.e2}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $OutputPath -Encoding UTF8
