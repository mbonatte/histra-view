param([Parameter(Mandatory=$true)][string]$ModelPath,
      [Parameter(Mandatory=$true)][string]$OutputPath,
      [string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {
    [void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))
}
$flags=[Reflection.BindingFlags]'Static,Public,NonPublic'
$instance=[Reflection.BindingFlags]'Instance,Public,NonPublic'
$ctor=[ModelLibrary.Model].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 2}|Select-Object -First 1
$model=$ctor.Invoke([object[]]@([enum]::Parse($ctor.GetParameters()[0].ParameterType,'RailBridge'),$false))
[void][SirioSoft.SerializeXmlReader].GetMethod('ReadFromFile',[Type[]]@([string],[string],[object])).Invoke($null,[object[]]@([IO.Path]::GetFullPath($ModelPath),'HiStrA',$model))
[ModelLibrary.Model].GetField('_model',$flags).SetValue($null,$model)
$model.IsLocked=$false
$p=[SolverRuntime.Program]::new()
[SolverRuntime.Program].GetField('model',$instance).SetValue($p,$model)
[SolverRuntime.Program].GetField('_LS',$instance).SetValue($p,[MatrixManager.LinearSystem]::new())
[ModelManagement.ComputationalElementsOperations.ConstitutiveLawOperations]::ExtractInfoFromMaterials($model.Collections)
[void][SolverRuntime.ModelManager].GetMethod('PreliminaryOperations',$flags).Invoke($null,@())
[ModelManagement.ComputationalElementsOperations.InterfaceOperations]::GenerateInterfaces($model)
[void][SolverRuntime.ModelManager].GetMethod('ComputeAff',$flags).Invoke($null,[object[]]@($p,$model.Collections))
[void][SolverRuntime.ModelManager].GetMethod('SetAffElements',$flags).Invoke($null,[object[]]@($model.Collections,[int]$model.GDL))
[SolverRuntime.ModelManager].GetProperty('Pq',$flags).SetValue($null,[MatrixManager.Vector]::new([int]$model.GDL),$null)
$analysis=$model.Collections.Analyses[2]
$originalFrames=@{}
foreach($entry in $model.Collections.Interfaces.Collection.GetEnumerator()) {
 $rs=[Objects.Interface].GetProperty('ReferenceSystem').GetValue($entry.Value,$null)
 $originalFrames[$entry.Key]=@($rs.e1,$rs.e2,$rs.e3)
}
$rows=[Collections.Generic.List[object]]::new()
foreach($seismic in @($false,$true)) {
 foreach($oblique in @($false,$true)) {
 foreach($translation in @(0.0,0.123456789,1.23456789e8)) {
  foreach($interfaceForces in @($false,$true)) {
   $analysis.IsSeismic=$seismic
   $quadInputs=@();$forceInputs=@()
   foreach($q in $model.Collections.Quads.Collection.Values) {
    $q.Status=[Objects.ElementStates.QuadState]::new($q.Key)
    $u=@($translation,(-2*$translation),(3*$translation),(0.00023456789*$q.Key),(-0.00123456789*$q.Key),(0.00345678912*$q.Key),0.001234567891)
    for($j=0;$j -lt 7;$j++) {$q.Status.U[$j]=[double]$u[$j]}
    $quadInputs+=@{key=$q.Key;u=$u}
   }
   foreach($entry in $model.Collections.Interfaces.Collection.GetEnumerator()) {
    $iface=$entry.Value;$key=$entry.Key
    $force=[Microsoft.Xna.Framework.Vector3]::Zero
    if($interfaceForces) {$force=[Microsoft.Xna.Framework.Vector3]::new(.123456789*$key,-.345678912*$key,.567891234*$key)}
    $status=[Objects.Interface].GetProperty('Status').GetValue($iface,$null)
    $status.Forces=$force
    $rs=[Objects.Interface].GetProperty('ReferenceSystem').GetValue($iface,$null)
    $axes=$originalFrames[$key]
    if($oblique) {$axes=@([Microsoft.Xna.Framework.Vector3]::new(.36,.48,-.8),[Microsoft.Xna.Framework.Vector3]::new(-.8,.6,0),[Microsoft.Xna.Framework.Vector3]::new(.48,.64,.6))}
    $rs.e1=$axes[0];$rs.e2=$axes[1];$rs.e3=$axes[2]
    $forceInputs+=@{key=$key;force=@([double]$force.X,[double]$force.Y,[double]$force.Z);axes=@(@([double]$rs.e1.X,[double]$rs.e1.Y,[double]$rs.e1.Z),@([double]$rs.e2.X,[double]$rs.e2.Y,[double]$rs.e2.Z),@([double]$rs.e3.X,[double]$rs.e3.Y,[double]$rs.e3.Z))}
   }
   [ModelManagement.Load.ModelLoadOperations]::ComputePDeltaLoads($analysis,1,$model.Collections)
   [void][SolverRuntime.ModelManager].GetMethod('AssemblePdeltaLoad',$flags).Invoke($null,[object[]]@($p,$model.Collections))
   $local=@();foreach($q in $model.Collections.Quads.Collection.Values) {$local+=@{key=$q.Key;pq=@($q.Pq)}}
   $rows.Add(@{is_seismic=$seismic;oblique=$oblique;translation=$translation;interface_forces=$interfaceForces;quads=$quadInputs;forces=$forceInputs;local=$local;global=@([SolverRuntime.ModelManager]::Pq.theData)})
  }
 }
}
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);
 generator='tools/csharp-diagnostics/Invoke-PDeltaOracle.ps1';benchmark_id='native-pdelta-2026.1.1';
 model_sha256=(Get-FileHash $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant();
 assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();
 cases=$rows} | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding UTF8
