param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$GeometryPath,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$geometry=Get-Content -LiteralPath $GeometryPath -Raw | ConvertFrom-Json
$rows=@()
foreach($case in $geometry.cases) {
 $q=[Activator]::CreateInstance([Objects.Quad])
 for($j=0;$j -lt 4;$j++) {$q.Length[$j]=[double]$case.Length[$j];$q.Cos[$j]=[double]$case.Cos[$j];$q.Sin[$j]=[double]$case.Sin[$j]}
 for($j=0;$j -lt 2;$j++) {$q.Diago[$j]=[double]$case.Diago[$j]}
 $k=1000.0+[double]$case.key;$E=500.0;$G=230.0;$fyt=0.5;$fyc=5.0
 $fy=$q.SetNonLinearProperties($k,$E,$G,$fyt,$fyc)
 $rows += @{key=$case.key;Length=$q.Length;Cos=$q.Cos;Sin=$q.Sin;dalfa=$q.DAlfa2DDiag();k=$k;E=$E;G=$G;Fyt=$fyt;Fyc=$fyc;Fy=$fy}
}
@{source='Original Quad.SetNonLinearProperties, distorted geometries from fresh Dhir native construction';cases=$rows}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $OutputPath -Encoding UTF8
