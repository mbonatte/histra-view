param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$output=@()
foreach($pair in @(@(1.,1e16),@(-1.,-1e16),@(.273435095827634,.137656839215837),@(.25,.25),@(0.,-.25))) {
    $s=[Activator]::CreateInstance([Objects.SpringHysteretic]);$s.Cstress=[double]$pair[0]
    [Objects.SpringHysteretic].GetField('_Tstress',[Reflection.BindingFlags]'Instance,NonPublic').SetValue($s,[double]$pair[1])
    $output += @{committed=$pair[0];trial=$pair[1];increment=$s.GetIncrForce();reconstructed_committed=($s.GetForce()-$s.GetIncrForce())}
}
@{source='Original SpringHysteretic.GetForce/GetIncrForce, used literally by Quad.ComputeDN';cases=$output}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $OutputPath -Encoding UTF8
