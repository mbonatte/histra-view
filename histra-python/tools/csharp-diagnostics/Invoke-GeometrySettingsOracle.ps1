param([Parameter(Mandatory=$true)][string]$OutputPath,
      [string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {
    [void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))
}
$rows = foreach($value in @(.0123456789,.123456789,1.23456789)) {
    $options=[Objects.Defaults.AdvancedOptionsDefault]::new()
    $options.ToleranceNode=[single]$value
    $options.TolerancePlane=[single]$value
    $options.InterfaceImax=$value
    @{input=$value;node=[double]$options.ToleranceNode;plane=[double]$options.TolerancePlane;imax=$options.InterfaceImax}
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');
  source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);
  generator='tools/csharp-diagnostics/Invoke-GeometrySettingsOracle.ps1';
  benchmark_id='native-geometry-settings-2026.1.1';
  assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();
  cases=@($rows)} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
