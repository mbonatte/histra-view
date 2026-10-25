param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$env:PATH=(Join-Path $InstalledRoot 'x64')+';'+$env:PATH
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$matrix=[MatrixManager.SparseMatrix]::new(2)
$matrix.InitializeControl()
$control=[MatrixManager.SparseMatrix].GetField('_control',[Reflection.BindingFlags]'Instance,NonPublic').GetValue($matrix)
@{source='Original MatrixManager.SparseMatrix.InitializeControl with installed libumfpack.dll';strategy=$control[5];refinement=$control[7];ordering=$control[10]}|ConvertTo-Json|Set-Content -LiteralPath $OutputPath -Encoding UTF8
