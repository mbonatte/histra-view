param([Parameter(Mandatory=$true)][string]$InstalledRoot,
      [Parameter(Mandatory=$true)][string]$InputPath,
      [Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','ModelLibrary.dll')) {
    [void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))
}
$model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model])
[ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
$output=@()
foreach($case in (Get-Content -LiteralPath $InputPath -Raw | ConvertFrom-Json)) {
    $p=$case.law
    $law=[Activator]::CreateInstance([Objects.ConstitutiveLaw.ConstitutiveLawHysteretic])
    $law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::Hysteretic
    $law.E=$p.E; $law.Fy_t=$p.fy_t; $law.Fy_c=$p.fy_c
    $law.RatioEttrac=$p.ratio_et_t; $law.RatioEtcomp=$p.ratio_et_c
    $law.Eps_u_t=$p.eps_u_t; $law.Eps_u_c=$p.eps_u_c
    $law.G[0]=$p.G_t; $law.G[1]=$p.G_c
    $law.Alfa_r[0]=$p.alfa_r_t; $law.Alfa_r[1]=$p.alfa_r_c
    $law.Alfa_u[0]=$p.alfa_u_t; $law.Alfa_u[1]=$p.alfa_u_c
    $law.TensileCurveType=[enum]::Parse([UtilityLibrary.Tipi.HystereticTensileCurveTypeEnum],$p.tensile_curve)
    $law.CompressiveCurveType=[enum]::Parse([UtilityLibrary.Tipi.HystereticCompressiveCurveTypeEnum],$p.compressive_curve)
    $s=[Activator]::CreateInstance([Objects.SpringHysteretic])
    $s.SetQuadTrasvSpring([double]$case.k,[double]$case.area,[double]$case.length,$law)
    $secondLaw=$law
    if($case.law2) {
        $secondLaw=[Activator]::CreateInstance([Objects.ConstitutiveLaw.ConstitutiveLawHysteretic])
        $secondLaw.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::Hysteretic
        $secondLaw.E=$case.law2.E; $secondLaw.Fy_t=$case.law2.fy_t; $secondLaw.Fy_c=$case.law2.fy_c
        $secondLaw.Eps_u_t=$case.law2.eps_u_t; $secondLaw.Eps_u_c=$case.law2.eps_u_c
        $secondLaw.TensileCurveType=[enum]::Parse([UtilityLibrary.Tipi.HystereticTensileCurveTypeEnum],$case.law2.tensile_curve)
        $secondLaw.CompressiveCurveType=[enum]::Parse([UtilityLibrary.Tipi.HystereticCompressiveCurveTypeEnum],$case.law2.compressive_curve)
    }
    $s.SetUltimateDisplacement($law,$secondLaw); $s.initialize()
    $initial=@{Fy=@($s.Fy);Kt=@($s.Kt);Ur=@($s.Ur)}
    $states=@()
    foreach($strain in $case.strains) {
        $s.U=[double]$strain; [void]$s.setTrialStrain([double]$strain); $s.Commit()
        $states += @{U=$s.U;F=$s.GetForce();K_tang=$s.K_tang;Phase=[int]$s.Phase;
            Umax=@($s.Umax);CenergyD=$s.CenergyD;Cstrain=$s.Cstrain;Cstress=$s.Cstress}
    }
    $case|Add-Member -NotePropertyName initial -NotePropertyValue $initial -Force
    $case|Add-Member -NotePropertyName states -NotePropertyValue $states -Force
    $output += $case
}
@{source='Original SpringHysteretic.SetQuadTrasvSpring, SetUltimateDisplacement, initialize, setTrialStrain and Commit';cases=$output} |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
