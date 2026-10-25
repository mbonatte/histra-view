param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
[UtilityLibrary.Matematics.Operations]::ToleranceNode=[single]0.0002
$method=[UtilityLibrary.Matematics.Operations].GetMethods() | Where-Object {$_.Name -eq 'FindIntersectionBetweenQuadrilaters' -and $_.GetParameters()[0].ParameterType.GetElementType() -eq [Collections.Generic.List[Microsoft.Xna.Framework.Vector3]]}
$first=@(@(-1,-1,0),@(1,-1,0),@(1,1,0),@(-1,1,0))
$cases=@()
foreach($case in @(
 @{name='partial_rectangle';points=@(@(0,-1,0),@(2,-1,0),@(2,1,0),@(0,1,0))},
 @{name='crossing_diamond';points=@(@(0,-1.5,0),@(1.5,0,0),@(0,1.5,0),@(-1.5,0,0))},
 @{name='corner_overlap';points=@(@(.5,1,0),@(1,.5,0),@(2,1.5,0),@(1.5,2,0))},
 @{name='containing_diamond';points=@(@(-2,0,0),@(0,-2,0),@(2,0,0),@(0,2,0))}
)) {
 $a=[Collections.Generic.List[Microsoft.Xna.Framework.Vector3]]::new();$b=[Collections.Generic.List[Microsoft.Xna.Framework.Vector3]]::new()
 foreach($p in $first){$a.Add([Microsoft.Xna.Framework.Vector3]::new([single]$p[0],[single]$p[1],[single]$p[2]))}
 foreach($p in $case.points){$b.Add([Microsoft.Xna.Framework.Vector3]::new([single]$p[0],[single]$p[1],[single]$p[2]))}
 $arguments=[object[]]@($null,$a,$b,$true);$code=$method.Invoke($null,$arguments)
 $points=@();foreach($v in $arguments[0]){$points+=,@([double]$v.X,[double]$v.Y,[double]$v.Z)}
 $cases+=@{name=$case.name;first=$first;second=$case.points;code=$code;intersection=$points;native_count=$points.Count}
}
@{generator='tools/csharp-diagnostics/Invoke-QuadContactIntersectionOracle.ps1';generated_at=[DateTime]::UtcNow.ToString('o');node_tolerance=[double][UtilityLibrary.Matematics.Operations]::ToleranceNode;assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'UtilityLibrary.dll') -Algorithm SHA256).Hash.ToLower();cases=$cases} | ConvertTo-Json -Depth 12 | Set-Content -Encoding UTF8 $OutputPath
