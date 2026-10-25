param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$ctor=[ModelLibrary.Model].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 2}|Select-Object -First 1
$model=$ctor.Invoke([object[]]@([enum]::Parse($ctor.GetParameters()[0].ParameterType,'RailBridge'),$false))
[ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
$node=[Objects.Node]::new();[Objects.Node].GetProperty('Key').SetValue($node,1,$null)
$rows=@()
foreach($inputs in @(@(@(1000000.0,1.2,0.3),@(-1000000.0,0.7,0.6),@(0.25,0.4,0.1)),@(@(0.1,0.2,0.3),@(0.4,0.5,0.6),@(0.7,0.8,0.9)))) {
 $model.Collections.Quads.Collection.Clear()
 for($j=0;$j -lt $inputs.Length;$j++) {
  $q=[Objects.Quad]::new();$q.Key=$j+1;$q.NodeKeys[0]=1
  for($k=0;$k -lt 3;$k++) {$q.Status.U[$k]=[double]$inputs[$j][$k]}
  $model.Collections.Quads.Collection.Add($q.Key,$q)
 }
 $args=[object[]]@($model.Collections,$node,[Microsoft.Xna.Framework.Vector3]::Zero)
 $method=[ModelManagement.GeometryElementsOperations.NodeOperations].GetMethod('GetDisplacements',[Type[]]@([ModelLibrary.Collections],[Objects.Node],[Microsoft.Xna.Framework.Vector3].MakeByRefType()))
 [void]$method.Invoke($null,$args);$d=$args[2]
 $rows+=@{inputs=$inputs;bits=@([BitConverter]::ToInt32([BitConverter]::GetBytes($d.X),0).ToString(),[BitConverter]::ToInt32([BitConverter]::GetBytes($d.Y),0).ToString(),[BitConverter]::ToInt32([BitConverter]::GetBytes($d.Z),0).ToString())}
}
@{source='Original NodeOperations.GetDisplacements(Collections, Node, out Vector3)';cases=$rows}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $OutputPath -Encoding UTF8
