param([Parameter(Mandatory=$true)][string]$InputPath,[Parameter(Mandatory=$true)][string]$OutputPath,[string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','UtilityLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))}
$rows=[Collections.Generic.List[object]]::new()
foreach($case in (Get-Content -LiteralPath $InputPath -Raw | ConvertFrom-Json).cases) {
 $points=[Collections.Generic.List[Microsoft.Xna.Framework.Vector3]]::new()
 foreach($point in $case.points) {$points.Add([Microsoft.Xna.Framework.Vector3]::new([single]$point[0],[single]$point[1],[single]$point[2]))}
 $rows.Add(@{points=$case.points;area=[double][UtilityLibrary.Matematics.Operations]::Area([Microsoft.Xna.Framework.Vector3[]]$points.ToArray(),$true)})
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);generator='tools/csharp-diagnostics/Invoke-PolygonAreaOracle.ps1';benchmark_id='native-single-polygon-area-2026.1.1';assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'UtilityLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();cases=$rows}|ConvertTo-Json -Depth 7|Set-Content -LiteralPath $OutputPath -Encoding UTF8
