param([Parameter(Mandatory=$true)][string]$InstalledRoot,
      [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {
    [void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))
}
$cases=@(
    @{initial=1e16;x=@(-1e16,1.0);coefficients=@(1.0,1.0)},
    @{initial=0.1;x=@(1e-17,-1e-17);coefficients=@(1.0,1.0)},
    @{initial=-0.38483884860077533;x=@(0.273435095827634,-0.137656839215837);coefficients=@(0.8364628553390503,0.5480235815048218)},
    @{initial=2.0;x=@(0.125,-0.25);coefficients=@(1.0,0.5)}
)
$output=@()
foreach($case in $cases) {
    $quad=[Activator]::CreateInstance([Objects.Quad])
    $quad.Status=[Activator]::CreateInstance([Objects.ElementStates.QuadState])
    $quad.Status.U[0]=$case.initial
    $quad.Aff.Clear()
    for($j=0;$j -lt 7;$j++) {$quad.Aff.Add([Activator]::CreateInstance([MatrixManager.AfferenceMatrix]))}
    $ls=[Activator]::CreateInstance([MatrixManager.LinearSystem])
    $ls.x=[MatrixManager.Vector].GetConstructor([Type[]]@([int])).Invoke([object[]]@([int]$case.x.Count))
    for($j=0;$j -lt $case.x.Count;$j++) {
        $ls.SetX($j,[double]$case.x[$j])
        $quad.Aff[0].Add_Gdl($j+1); $quad.Aff[0].Add_Alfa([double]$case.coefficients[$j])
    }
    $quad.UpdateUElem($ls)
    $case.expected=$quad.Status.U[0]
    $output += $case
}
@{source='Original Objects.Quad.UpdateUElem; Interface.UpdateDomain uses the same ordered Status.U additions';cases=$output} |
    ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
