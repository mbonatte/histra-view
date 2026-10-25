param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
function Bits($values) {return @($values|ForEach-Object{[BitConverter]::DoubleToInt64Bits([double]$_).ToString()})}
function Set-I($i,$name,$v) {[Objects.Interface].GetProperty($name).SetValue($i,$v,$null)}
$cases=@();$flags=[Reflection.BindingFlags]'Instance,Public,NonPublic'
foreach($parent in @('free','first','second')) {foreach($variant in 0..2) {
 $coll=[ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
 $model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model]);$model.Collections=$coll
 [ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
 $ls=[MatrixManager.LinearSystem]::new();$ls.x=[MatrixManager.Vector]::new([int]8)
 $x=if($variant -eq 1){@(1e16,1.,-1e16,.273435095827634,-.137656839215837,1e-17,-.25,.7)}elseif($variant -eq 2){@(.1,1e-17,-1e-17,-.2,.3,.001,-.0001,.7)}else{@(.27,-.13,.39,-.57,.87,-.021,.034,-.078)}
 for($j=0;$j -lt 8;$j++) {$ls.SetX($j,[double]$x[$j])}
 $q=[Objects.Quad]::new();[Objects.Quad].GetProperty('Key').SetValue($q,[int]17,$null)
 $records=@()
 foreach($key in 1..3) {
  $intf=[Objects.Interface]::new();Set-I $intf 'Key' ([int]$key);Set-I $intf 'Nrow' ([int]2);Set-I $intf 'Ncol' ([int]3);Set-I $intf 'DimAff' ([int[]]@(6,2,4));Set-I $intf 'Length' ([double](2.718281828459045+$key*.13))
  $p1=if($parent -eq 'first'){[UtilityLibrary.Tipi.ElementTypeEnum]::Restraint}else{[UtilityLibrary.Tipi.ElementTypeEnum]::Quad}
  $p2=if($parent -eq 'second'){[UtilityLibrary.Tipi.ElementTypeEnum]::Restraint}else{[UtilityLibrary.Tipi.ElementTypeEnum]::Quad}
  Set-I $intf 'ParentTypeElement1' $p1;Set-I $intf 'ParentTypeElement2' $p2
  Set-I $intf 'ParentElementKey1' ([int]$(if($parent -eq 'first'){33}else{17}));Set-I $intf 'ParentElementKey2' ([int]$(if($parent -eq 'first'){17}else{33}))
  if($key -eq 3) {Set-I $intf 'ParentElementKey1' ([int]91);Set-I $intf 'ParentElementKey2' ([int]92)}
  $vertices=[Microsoft.Xna.Framework.Vector2[]]@([Microsoft.Xna.Framework.Vector2]::new(0,0),[Microsoft.Xna.Framework.Vector2]::new([single]$key,0),[Microsoft.Xna.Framework.Vector2]::new([single]$key,[single].7),[Microsoft.Xna.Framework.Vector2]::new(0,[single].7));Set-I $intf 'VInt2D' $vertices
  $state=[Objects.InterfaceState].GetConstructor([Type[]]@([Objects.Interface],[bool])).Invoke([object[]]@($intf,$false));Set-I $intf 'Status' $state
  $matrix=@();for($j=0;$j -lt 6;$j++){for($k=$j;$k -lt 6;$k++){$state.K.Set($j,$k,[double](137.56+($j*6+$k)*.273435095827634))}}
  for($j=0;$j -lt 6;$j++){for($k=0;$k -lt 6;$k++){$matrix+= $state.K.Read($j,$k)};$state.U[$j]=1e100}
  $aff=[Collections.Generic.List[MatrixManager.AfferenceMatrix]]::new();$maps=@()
  for($j=0;$j -lt 12;$j++){
   $a=[MatrixManager.AfferenceMatrix]::new();$entries=@()
   if($j -lt 5){foreach($pair in @(@((($j%8)+1),1.),@(((($j+1)%8)+1),.5),@(((($j+2)%8)+1),-.137656839215837))){$a.Add_Gdl([int]$pair[0]);$a.Add_Alfa([double]$pair[1]);$entries+=,@([int]$pair[0],[double]$pair[1])}}
   if($variant -eq 1 -and $j -eq 0){$a.Clear();$entries=@();foreach($g in @(1,2,3,2)){$a.Add_Gdl($g);$a.Add_Alfa([double]1.);$entries+=,@($g,1.)}}
   $aff.Add($a);$maps+=,@($entries)
  };Set-I $intf 'Aff' $aff
  $springs=[Collections.Generic.List[Objects.Spring]]::new();$force=@();$increment=@();$committed=@()
  for($j=0;$j -lt 6;$j++){$s=[Objects.SpringHysteretic]::new();$s.Cstress=[double](($j+1)*.27);$t=if($j -eq 0){1e16}else{-.11*$j};[Objects.SpringHysteretic].GetField('_Tstress',$flags).SetValue($s,[double]$t);$springs.Add($s);$force+=$s.GetForce();$increment+=$s.GetIncrForce();$committed+=$s.Cstress};Set-I $intf 'Trasv_1' $springs
  $du=[double[]]@(0.,0.,0.);[void][Objects.Interface].GetMethod('ComputeFlexdef').Invoke($intf,[object[]]@($intf,$ls,$du))
  $dn=[Objects.Interface].GetMethod('ComputeDN').Invoke($intf,[object[]]@($ls,$false))
  $coll.Interfaces.Collection.Add($key,$intf)
  $records+=@{key=$key;belongs=($key -ne 3);area=[double][Objects.Interface].GetMethod('Area').Invoke($intf,[object[]]@());length=[double][Objects.Interface].GetProperty('Length').GetValue($intf,$null);aff=$maps;matrix_bits=(Bits $matrix);force_bits=(Bits $force);committed_bits=(Bits $committed);increment_bits=(Bits $increment);flex_bits=(Bits $du);dn_bits=(Bits $dn)}
 }
 $edges=@(@(1,1,999),@(2),@(3,2),@())
 for($j=0;$j -lt 4;$j++){foreach($key in $edges[$j]){$q.Interfaces[$j].Add([int]$key)}}
 $method=[Objects.Quad].GetMethods()|Where-Object{$_.Name -eq 'ComputeDN' -and $_.GetParameters().Length -eq 3};$args=[object[]]@($ls,[double]0.,$false);$dn=$method.Invoke($q,$args)
 $cases+=@{parent=$parent;variant=$variant;x_bits=(Bits $x);interfaces=$records;edges=$edges;quad_dn_bits=(Bits $dn);sigma_bits=(Bits $args[1])}
}}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');generator='tools/csharp-diagnostics/Invoke-LinearNormalForceOracle.ps1';assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();source='Original Interface.ComputeFlexdef and ComputeDN(NR=false), Quad.ComputeDN(out sigma,NR=false)';cases=$cases}|ConvertTo-Json -Depth 12|Set-Content -LiteralPath $OutputPath -Encoding UTF8
