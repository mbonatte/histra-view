param([Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
if ($PSVersionTable.PSEdition -eq 'Core') { throw 'Use Windows PowerShell 5 to call the original .NET Framework.' }
$powers=@()
foreach($x in @(0.9999999999999921,0.9999999999999983,0.999999999999962,0.001,0.31,1.0,2.0,3.0,1000.0)) {
 foreach($y in @(0.5,2.0,1.8,-0.5)) {
  $powers += @{x=[double]$x;y=[double]$y;result=[Math]::Pow([double]$x,[double]$y)}
 }
}
$angles=@()
foreach($x in @(-1.5,-0.4,0.0,1e-8,0.4,1.5)) { $angles += @{x=[double]$x;result=[Math]::Atan([double]$x)} }
$libraries=@([Diagnostics.Process]::GetCurrentProcess().Modules | Where-Object {$_.ModuleName -match '^(ucrtbase|msvcr120)_clr0400\.dll$'} | ForEach-Object {@{name=$_.ModuleName;version=$_.FileVersionInfo.FileVersion}})
@{source='Original System.Math calls in Windows .NET Framework';runtime=[Environment]::Version.ToString();libraries=$libraries;powers=$powers;angles=$angles} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
