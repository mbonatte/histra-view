param([Parameter(Mandatory=$true)][string]$InstalledRoot,
      [Parameter(Mandatory=$true)][string]$InputPath,
      [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','ModelLibrary.dll')) {
    [void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))
}
function NativeLaw($data) {
    if($data.is_elastic) {
        $law=[Activator]::CreateInstance([Objects.ConstitutiveLaw.ConstitutiveLawElastic])
        $law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::LinearElastic
    } else {
        $law=[Activator]::CreateInstance([Objects.ConstitutiveLaw.ConstitutiveLawCoulomb])
        $law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::Coulomb03
        $law.Fy_0=$data.cohesion; $law.Mu=$data.mu; $law.U_r=$data.ductility
    }
    $law.E=$data.E
    return $law
}
$output=@()
foreach($case in (Get-Content -LiteralPath $InputPath -Raw | ConvertFrom-Json)) {
    $primary=NativeLaw $case.primary; $secondary=NativeLaw $case.secondary
    $a=[Microsoft.Xna.Framework.Vector3]::new([single]$case.interface_e1[0],[single]$case.interface_e1[1],[single]$case.interface_e1[2])
    $b=[Microsoft.Xna.Framework.Vector3]::new([single]$case.quad_e1[0],[single]$case.quad_e1[1],[single]$case.quad_e1[2])
    $c1=[Math]::Min(1.0,[Math]::Abs([double][Microsoft.Xna.Framework.Vector3]::Dot($a,$b)))
    $c2=[Math]::Sqrt(1.0-$c1*$c1)
    $primary.PropOrthotropyParameter([double]$c1,[double]$c2,$secondary)
    $expected=@{E=$primary.E;cohesion=$case.primary.cohesion;mu=$case.primary.mu;ductility=$case.primary.ductility;c1=$c1;c2=$c2}
    if(-not $case.primary.is_elastic) {
        $expected.cohesion=$primary.Fy_0; $expected.mu=$primary.Mu; $expected.ductility=$primary.U_r
    }
    $case|Add-Member -NotePropertyName expected -NotePropertyValue $expected -Force
    $output += $case
}
@{source='Original ConstitutiveLawCoulomb/Elastic.PropOrthotropyParameter and native Vector3.Dot';cases=$output} |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
