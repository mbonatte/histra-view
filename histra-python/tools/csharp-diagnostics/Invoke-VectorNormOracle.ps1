param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$cases=@()
foreach($values in @([double[]]@(3.0,-4.0,12.0,-8.0,0.5),[double[]]@(1e16,1.0,-1e16,3.0,4.0,1e-16),[double[]]@(0.0),[double[]]@())) {
 $ls=[MatrixManager.LinearSystem]::new();$ls.K=[MatrixManager.SparseMatrix]::new();$ls.K.N=$values.Length;$ls.InitVectors()
 $ls.b=[MatrixManager.Vector]::new($values)
 $reversed=[double[]]$values.Clone();[Array]::Reverse($reversed);$ls.x=[MatrixManager.Vector]::new($reversed)
 foreach($norm in @(-1,0,1,2,3,4)) {
  $cases+=@{b_bits=@($values|ForEach-Object{[BitConverter]::DoubleToInt64Bits($_).ToString()});x_bits=@($reversed|ForEach-Object{[BitConverter]::DoubleToInt64Bits($_).ToString()});norm=$norm;b_norm_bits=[BitConverter]::DoubleToInt64Bits($ls.GetbNorm($norm)).ToString();x_norm_bits=[BitConverter]::DoubleToInt64Bits($ls.GetxNorm($norm)).ToString()}
 }
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');generator='tools/csharp-diagnostics/Invoke-VectorNormOracle.ps1';assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'MatrixManager.dll') -Algorithm SHA256).Hash.ToLower();cases=$cases}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $OutputPath -Encoding UTF8
