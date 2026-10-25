param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$rows=@()
foreach($axes in @(@(@(1.,0.,0.),@(0.,1.,0.),@(0.,0.,1.)),@(@(.1,.7,.3),@(.6,-.2,.8),@(-.7,.3,.2)))) {foreach($direction in 0..7) {
 $q=[Objects.Quad]::new();$rs=$q.ReferenceSystem;$vectors=@();foreach($a in $axes){$vectors+=,[Microsoft.Xna.Framework.Vector3]::new([single]$a[0],[single]$a[1],[single]$a[2])};$rs.e1=$vectors[0];$rs.e2=$vectors[1];$rs.e3=$vectors[2]
 $item=[Objects.Loads.LoadTemplateItem]::new();$item.IdLoadDirection=$direction;[Objects.Loads.LoadTemplateItem].GetProperty('DirX').SetValue($item,[single]0.27,$null);[Objects.Loads.LoadTemplateItem].GetProperty('DirY').SetValue($item,[single](-0.13),$null);[Objects.Loads.LoadTemplateItem].GetProperty('DirZ').SetValue($item,[single](-0.57),$null)
 $v=$item.Dir($q)
 $rows+=@{direction=$direction;axes=$axes;custom=@(.27,-.13,-.57);expected_bits=@([BitConverter]::DoubleToInt64Bits([double]$v.X).ToString(),[BitConverter]::DoubleToInt64Bits([double]$v.Y).ToString(),[BitConverter]::DoubleToInt64Bits([double]$v.Z).ToString())}
}}
@{schema_version=1;generator='tools/csharp-diagnostics/Invoke-LoadDirectionOracle.ps1';generated_at=[DateTime]::UtcNow.ToString('o');assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLower();cases=$rows}|ConvertTo-Json -Depth 7|Set-Content -Encoding UTF8 $OutputPath
