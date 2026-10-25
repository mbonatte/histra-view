param([Parameter(Mandatory=$true)][string]$ModelPath,[Parameter(Mandatory=$true)][string]$OutputDirectory,[string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1',[switch]$ReapplySavedMaterials,[switch]$ExportAfference,[switch]$ExportAssembly,[string]$TrialIncrementPath,[int]$AnalysisKey=1)
$ErrorActionPreference='Stop'
$a=[IO.Path]::GetFullPath($OutputDirectory);$i=$InstallDirectory
[void][IO.Directory]::CreateDirectory($a)
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $i $name))}
$ctor=[ModelLibrary.Model].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 2}|Select-Object -First 1
$model=$ctor.Invoke([object[]]@([enum]::Parse($ctor.GetParameters()[0].ParameterType,'RailBridge'),$false))
$path=[IO.Path]::GetFullPath($ModelPath)
[void][SirioSoft.SerializeXmlReader].GetMethod('ReadFromFile',[Type[]]@([string],[string],[object])).Invoke($null,[object[]]@([string]$path,[string]'HiStrA',$model))
function Get-InterfaceLocation($iface) {
 $parts=@()
 foreach($name in @('ParentTypeElement1','ParentElementKey1','Face1','ParentTypeElement2','ParentElementKey2','Face2')) {$parts += [string][Objects.Interface].GetProperty($name).GetValue($iface,$null)}
 $parts += ([Objects.Interface].GetProperty('NodeKeys').GetValue($iface,$null) -join ',')
 return $parts -join ':'
}
function Get-SpringBits($spring) {
 $bits=@{}
 foreach($name in @('K','Area','Fy','Ur','E3p')) {
  $v=$spring.$name
  if($null -eq $v) {continue}
  if($v -is [Array]) {$bits[$name]=@($v | ForEach-Object {[BitConverter]::DoubleToInt64Bits([double]$_).ToString()})}
  else {$bits[$name]=[BitConverter]::DoubleToInt64Bits([double]$v).ToString()}
 }
 return $bits
}
$selections=[Collections.Generic.Dictionary[string,int]]::new()
if($ReapplySavedMaterials) {
 foreach($iface in $model.Collections.Interfaces.Collection.Values) {
  $key=[int][Objects.Interface].GetProperty('MaterialKey').GetValue($iface,$null)
  if($key -gt 0) {$selections.Add((Get-InterfaceLocation $iface),$key)}
 }
}
[ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
$model.IsLocked=$false
$p=[Activator]::CreateInstance([SolverRuntime.Program])
[SolverRuntime.Program].GetField('model',[Reflection.BindingFlags]'Instance,NonPublic').SetValue($p,$model)
[SolverRuntime.Program].GetField('_LS',[Reflection.BindingFlags]'Instance,NonPublic,Public').SetValue($p,[Activator]::CreateInstance([MatrixManager.LinearSystem]))
Write-Output 'Calling original material extraction, geometry and interface generation'
[ModelManagement.ComputationalElementsOperations.ConstitutiveLawOperations]::ExtractInfoFromMaterials($model.Collections)
[void][SolverRuntime.ModelManager].GetMethod('PreliminaryOperations',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,@())
[ModelManagement.ComputationalElementsOperations.InterfaceOperations]::GenerateInterfaces($model)
Write-Output ('Generated '+$model.Collections.Quads.Count+' quads; '+$model.Collections.Interfaces.Count+' interfaces')
if($ReapplySavedMaterials) {
 $count=0
 foreach($iface in $model.Collections.Interfaces.Collection.Values) {
  $location=Get-InterfaceLocation $iface
  if($selections.ContainsKey($location)) {
   [Objects.Interface].GetProperty('MaterialKey').SetValue($iface,[int]$selections[$location],$null)
   [Objects.Interface].GetProperty('IsPropertyModified').SetValue($iface,$true,$null)
   $count++
  }
 }
 if($count -ne $selections.Count) {throw 'Could not locate every saved material selection on fresh geometry'}
 [void][ModelManagement.ComputationalElementsOperations.InterfaceOperations]::ReSetInterfaces($model.Collections)
 Write-Output ('Reapplied '+$count+' material selections using original ReSetInterfaces')
}
if($ExportAfference -or $ExportAssembly) {
 [void][SolverRuntime.ModelManager].GetMethod('ComputeAff',[Reflection.BindingFlags]'Static,NonPublic').Invoke($null,[object[]]@($p,$model.Collections))
 [void][SolverRuntime.ModelManager].GetMethod('SetAffElements',[Reflection.BindingFlags]'Static,NonPublic,Public').Invoke($null,[object[]]@($model.Collections,[int]$model.GDL))
 $affRows=[Collections.Generic.List[object]]::new()
 foreach($family in @('Quads','Interfaces')) {
  $collection=$model.Collections.$family.Collection
  foreach($entry in $collection.GetEnumerator()) {
   $element=$entry.Value
   $aff=[Objects.ComputationalElement].GetProperty('Aff').GetValue($element,$null)
   for($j=0;$j -lt $aff.Count;$j++) {
    $entries=@()
    for($n=0;$n -lt $aff[$j].N;$n++) {$entries += @{gdl=$aff[$j].Read_Gdl($n);alfa_bits=[BitConverter]::DoubleToInt64Bits([double]$aff[$j].Read_Alfa($n)).ToString()}}
    $affRows.Add(@{family=$family;key=$entry.Key;local=$j;entries=$entries})
   }
  }
 }
 @{gdl=$model.GDL;rows=$affRows}|ConvertTo-Json -Depth 7|Set-Content (Join-Path $a 'native-generated-afference.json') -Encoding UTF8
 Write-Output ('Original ComputeAff and SetAffElements succeeded; GDL='+$model.GDL)
 if($ExportAssembly) {
  $ls=[SolverRuntime.Program].GetField('_LS',[Reflection.BindingFlags]'Instance,NonPublic,Public').GetValue($p)
  $ls.K=[MatrixManager.SparseMatrix]::new()
  $ls.K.Mask.SetDimension([int]$model.GDL)
  $flags=[Reflection.BindingFlags]'Static,NonPublic,Public'
  $ok=[SolverRuntime.ModelManager].GetMethod('ComputeMaskK',$flags).Invoke($null,[object[]]@($p,$model.Collections,$false))
  if(!$ok -or !$ls.K.MapSparseMatrix()) {throw 'Native stiffness mask construction failed'}
  $ls.InitVectors()
  [void][SolverRuntime.ModelManager].GetMethod('ComputeK',$flags).Invoke($null,[object[]]@($p,$model.Collections,$false,[double]0.0))
  [void][SolverRuntime.ModelManager].GetMethod('AssembleK',$flags).Invoke($null,[object[]]@($p,$false,$true))
  foreach($field in @('Ap','Ai','Ax')) {
   $values=$ls.K.$field
   $bytes=New-Object byte[] ([Buffer]::ByteLength($values))
   [Buffer]::BlockCopy($values,0,$bytes,0,$bytes.Length)
   [IO.File]::WriteAllBytes((Join-Path $a ('native-K-'+$field+'.bin')),$bytes)
  }
  Write-Output ('Original initial ComputeK and AssembleK succeeded; stored entries='+$ls.K.Ax.Length)
  $analysis=$model.Collections.Analyses[$AnalysisKey]
  # An unrun HRX has no AnalysisState yet. The desktop initializes it before
  # load generation; create only that empty transient state in this oracle.
  if(!$analysis.States.ContainsKey(1)) {
   $state=[Objects.Analyses.AnalysisState]::new()
   $state.Key=$AnalysisKey;$state.Combination=1
   $analysis.States.Add(1,$state)
  }
  $loadsGenerated=[ModelManagement.Load.ModelLoadOperations]::GenerateLoadsForPushOverAnalysis($model.Collections,$analysis,1,$false)
  # The original method returns false even after its normal successful path.
  # Report the result without interpreting it as a success/failure indicator.
  Write-Output ('Original load-generation return value='+$loadsGenerated)
  [SolverRuntime.ModelManager].GetField('_Ptarget',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,[MatrixManager.Vector]::new([int]$model.GDL))
  [void][SolverRuntime.ModelManager].GetMethod('AssembleLoad',$flags).Invoke($null,[object[]]@($p,$model.Collections))
  $values=[SolverRuntime.ModelManager]::Ptarget.theData
  $bytes=New-Object byte[] ([Buffer]::ByteLength($values))
  [Buffer]::BlockCopy($values,0,$bytes,0,$bytes.Length)
  [IO.File]::WriteAllBytes((Join-Path $a 'native-Vert-Ptarget.bin'),$bytes)
  Write-Output ('Original load-generation call and AssembleLoad exported '+$values.Length+' target entries; analysis='+$AnalysisKey)
  if($TrialIncrementPath) {
   $u=[MatrixManager.Vector]::new([int]$model.GDL);$v=[MatrixManager.Vector]::new([int]$model.GDL)
   [void][SolverRuntime.CommonOperations].GetMethod('SetInitial',$flags).Invoke($null,[object[]]@($model.Collections,$ls,$u,$v))
   $bytes=[IO.File]::ReadAllBytes([IO.Path]::GetFullPath($TrialIncrementPath))
   if(!$bytes.Length -or $bytes.Length % (8*$model.GDL)) {throw 'Trial increments do not match fresh GDL'}
   $inputBytes=$bytes
   $frames=$inputBytes.Length/(8*$model.GDL)
   $values=New-Object double[] $model.GDL
   for($frame=0;$frame -lt $frames;$frame++) {
   [Buffer]::BlockCopy($inputBytes,$frame*8*$model.GDL,$values,0,8*$model.GDL)
   $ls.x=[MatrixManager.Vector]::new($values)
   $state=[Objects.Analyses.IntegratorState]::new();$state.Step=$frame+1;$state.Iteration=1;$state.Mult=0.05*($frame+1);$state.IncrMult=0.05;$state.Analysis=$analysis;$state.Combination=1
   [void][SolverRuntime.ModelManager].GetMethod('updateDomain',$flags).Invoke($null,[object[]]@($model.Collections,$ls,$state))
   [void][SolverRuntime.ModelManager].GetMethod('GetResistingForce',$flags).Invoke($null,[object[]]@($model.Collections,$ls))
   [void][SolverRuntime.CommonOperations].GetMethod('Commit',$flags).Invoke($null,[object[]]@($model.Collections,$ls))
   $keys=[Collections.Generic.List[int]]::new();$data=[Collections.Generic.List[double]]::new()
   foreach($entry in $model.Collections.Interfaces.Collection.GetEnumerator()) {
    foreach($pair in @(@('Trasv_1',1),@('Slid',11),@('SlidOutPlan',21))) {
     $group=[Objects.Interface].GetProperty($pair[0]).GetValue($entry.Value,$null)
     for($j=0;$j -lt $group.Count;$j++) {
      $spring=$group[$j];$keys.Add(102);$keys.Add($entry.Key);$keys.Add([int]$pair[1]);$keys.Add($j)
      $data.Add($spring.U);$data.Add($spring.GetForce());$data.Add($spring.K_tang);$data.Add([int]$spring.Phase)
     }
    }
   }
   foreach($entry in $model.Collections.Quads.Collection.GetEnumerator()) {$keys.Add(106);$keys.Add($entry.Key);$keys.Add(30);$keys.Add(0);$data.Add($entry.Value.Spring.U);$data.Add($entry.Value.Spring.GetForce());$data.Add($entry.Value.Spring.K_tang);$data.Add([int]$entry.Value.Spring.Phase)}
   foreach($pair in @(@('trial-keys',[int[]]$keys.ToArray()),@('trial-values',[double[]]$data.ToArray()),@('trial-b',$ls.b.theData))) {
    $values=$pair[1];$bytes=New-Object byte[] ([Buffer]::ByteLength($values));[Buffer]::BlockCopy($values,0,$bytes,0,$bytes.Length)
    [IO.File]::WriteAllBytes((Join-Path $a ($pair[0]+'-'+$frame+'.bin')),$bytes)
   }
   [void][SolverRuntime.ModelManager].GetMethod('ComputeK',$flags).Invoke($null,[object[]]@($p,$model.Collections,$false,[double]1.0))
   [void][SolverRuntime.ModelManager].GetMethod('AssembleK',$flags).Invoke($null,[object[]]@($p,$false,$true))
   $values=$ls.K.Ax;$bytes=New-Object byte[] ([Buffer]::ByteLength($values));[Buffer]::BlockCopy($values,0,$bytes,0,$bytes.Length)
   [IO.File]::WriteAllBytes((Join-Path $a ('trial-K-Ax-'+$frame+'.bin')),$bytes)
   Write-Output ('Original updateDomain, GetResistingForce and Commit replay frame '+$frame+' succeeded')
   }
  }
 }
 return
}
$rows=[Collections.Generic.List[object]]::new()
foreach($entry in $model.Collections.Quads.Collection.GetEnumerator()) {
 $q=$entry.Value;$rows.Add(@{family='Quad';key=$entry.Key;node_keys=@($q.NodeKeys);Length=@($q.Length);Diago=@($q.Diago);Cos=@($q.Cos);Sin=@($q.Sin);thickness=@($q.Thickness|ForEach-Object{[double]$_});K=$q.Spring.K;Fy=$q.Spring.Fy;Area=$q.Spring.Area;Ur=$q.Spring.Ur;bits=(Get-SpringBits $q.Spring)})
}
foreach($entry in $model.Collections.Interfaces.Collection.GetEnumerator()) {
 $iface=$entry.Value
 foreach($groupName in @('Trasv_1','Trasv_2','Slid','SlidOutPlan')) {
 $group=[Objects.Interface].GetProperty($groupName).GetValue($iface,$null)
 for($j=0;$j -lt $group.Count;$j++) {
  $spring=$group[$j]
  $rows.Add(@{family='Interface';key=$entry.Key;group=$groupName;geometry=@([string]([Objects.Interface].GetProperty('ParentTypeElement1').GetValue($iface,$null)),([Objects.Interface].GetProperty('ParentElementKey1').GetValue($iface,$null)),([Objects.Interface].GetProperty('Face1').GetValue($iface,$null)),[string]([Objects.Interface].GetProperty('ParentTypeElement2').GetValue($iface,$null)),([Objects.Interface].GetProperty('ParentElementKey2').GetValue($iface,$null)),([Objects.Interface].GetProperty('Face2').GetValue($iface,$null)));node_keys=@(([Objects.Interface].GetProperty('NodeKeys').GetValue($iface,$null)));index=$j;K=$spring.K;Area=$spring.Area;Fy=$spring.Fy;Ur=$spring.Ur;E3p=$spring.E3p;bits=(Get-SpringBits $spring)})
 }
 }
}
$rows|ConvertTo-Json -Depth 6|Set-Content (Join-Path $a 'native-generated-spring-definitions.json') -Encoding UTF8
