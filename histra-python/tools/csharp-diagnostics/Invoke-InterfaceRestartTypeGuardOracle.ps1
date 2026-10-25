param([Parameter(Mandatory=$true)][string]$ModelPath,
      [Parameter(Mandatory=$true)][string]$OutputPath,
      [string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
if(Test-Path -LiteralPath $OutputPath) {throw 'Use a new output file'}
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {
 [void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))
}
$flags=[Reflection.BindingFlags]'Static,Public,NonPublic'
$ctor=[ModelLibrary.Model].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 2}|Select-Object -First 1
$model=$ctor.Invoke([object[]]@([enum]::Parse($ctor.GetParameters()[0].ParameterType,'RailBridge'),$false))
[ModelLibrary.Model].GetField('_model',$flags).SetValue($null,$model)
[SirioSoft.SerializeXmlReader]::ReadFromFile([IO.Path]::GetFullPath($ModelPath),'HiStrA',$model)
[ModelManagement.ComputationalElementsOperations.ConstitutiveLawOperations]::ExtractInfoFromMaterials($model.Collections)
[void][SolverRuntime.ModelManager].GetMethod('PreliminaryOperations',$flags).Invoke($null,@())
[ModelManagement.ComputationalElementsOperations.InterfaceOperations]::GenerateInterfaces($model)
$method=[DBModelManager.dbOutputManager].GetMethods($flags)|Where-Object{
 $_.Name -eq 'UpdateSpringStates' -and $_.GetParameters().Length -eq 2 -and $_.GetParameters()[1].ParameterType -eq [bool]
}
function Get-State($spring) {return @{U=$spring.U;F=$spring.F;K_tang=$spring.K_tang;Force=$spring.GetForce();type=[int]$spring.Type}}
$iface=$model.Collections.Interfaces[4]
$transverse=[Objects.Interface].GetProperty('Trasv_1').GetValue($iface,$null)
$control=[Objects.Interface].GetProperty('Trasv_1').GetValue($model.Collections.Interfaces[3],$null)
$hysteretic=$transverse[0]
$elastic=[Objects.SpringLinearElastic]::new();$elastic.K=$hysteretic.K;$elastic.SetInitial()
$cases=@()
foreach($name in @('HystereticToElastic','ElasticToHysteretic','HystereticToHystereticControl')) {
 $hysteretic.SetInitial();$elastic.SetInitial()
 if($name -eq 'ElasticToHysteretic') {$source=$elastic;$target=$hysteretic}
 elseif($name -eq 'HystereticToElastic') {$source=$hysteretic;$target=$elastic}
 else {$source=$hysteretic;$target=$control[0];$target.SetInitial()}
 [void]$source.setTrialStrain(-0.005);$source.Commit()
 $saved=[Objects.ElementStates.SpringStateDBclass]::new()
 $saved.SetFromSpring($source,0,4,[UtilityLibrary.Tipi.ElementTypeEnum]::Interface)
 $rows=[Collections.Generic.List[Objects.ElementStates.SpringStateDBclass]]::new();$rows.Add($saved)
 $transverse[0]=$target
 $before=Get-State $target
 [void]$method.Invoke($null,[object[]]@($rows,$false))
 $cases+=@{name=$name;source=(Get-State $source);target_before=$before;target_after=(Get-State $target)}
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');
 source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);
 generator='tools/csharp-diagnostics/Invoke-InterfaceRestartTypeGuardOracle.ps1';
 benchmark_id='original-db-restart-type-guard-2026.1.1';
 source='Original dbOutputManager.UpdateSpringStates(IEnumerable<SpringStateDBclass>, bool), including type guard';
 input_sha256=(Get-FileHash $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant();
 assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();
 oracle_lf_sha256=([BitConverter]::ToString([Security.Cryptography.SHA256]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes([IO.File]::ReadAllText($PSCommandPath).Replace("`r`n","`n"))))).Replace('-','').ToLowerInvariant();
 cases=$cases}|ConvertTo-Json -Depth 10|Set-Content -LiteralPath $OutputPath -Encoding UTF8
