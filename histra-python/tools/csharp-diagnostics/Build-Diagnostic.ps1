param(
    [Parameter(Mandatory=$true)][string]$InstalledRoot,
    [Parameter(Mandatory=$true)][string]$DiagnosticRoot,
    [Parameter(Mandatory=$true)][string]$DnlibPath
)
$ErrorActionPreference = 'Stop'
$installedPath = (Resolve-Path -LiteralPath $InstalledRoot).Path.TrimEnd('\')
$diagnosticPath = [IO.Path]::GetFullPath($DiagnosticRoot).TrimEnd('\')
if ($diagnosticPath.Equals($installedPath,[StringComparison]::OrdinalIgnoreCase) -or $diagnosticPath.StartsWith($installedPath+'\',[StringComparison]::OrdinalIgnoreCase)) {
    throw 'Use a separate diagnostic output directory outside the installed application.'
}
$app = Join-Path $diagnosticPath 'app'
New-Item -ItemType Directory -Force $app | Out-Null
Get-ChildItem -LiteralPath $installedPath | Copy-Item -Destination $app -Recurse -Force
$compiler = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /target:library "/out:$app\ParityTrace.dll" (Join-Path $PSScriptRoot 'ParityTrace.cs')
if ($LASTEXITCODE -ne 0) { throw 'Trace helper compilation failed.' }
dotnet build (Join-Path $PSScriptRoot 'Instrument.csproj') --nologo -v quiet "-p:DnlibPath=$DnlibPath" "--output=$diagnosticPath\patcher"
if ($LASTEXITCODE -ne 0) { throw 'Instrumentation compiler build failed.' }
& (Join-Path $diagnosticPath 'patcher\Instrument.exe') (Join-Path $installedPath 'SolverRuntime.dll') (Join-Path $app 'SolverRuntime.dll') (Join-Path $app 'ParityTrace.dll')
if ($LASTEXITCODE -ne 0) { throw 'Solver instrumentation failed.' }
$manifest = foreach ($dll in @('SolverRuntime.dll','ModelLibrary.dll','MatrixManager.dll','UtilityLibrary.dll')) {
    [pscustomobject]@{Name=$dll;Original=(Get-FileHash -LiteralPath (Join-Path $installedPath $dll) -Algorithm SHA256).Hash;Diagnostic=(Get-FileHash -LiteralPath (Join-Path $app $dll) -Algorithm SHA256).Hash}
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $diagnosticPath 'assembly-hashes.json') -Encoding UTF8
& (Join-Path $PSScriptRoot 'Test-Diagnostic.ps1') -DiagnosticRoot $diagnosticPath
