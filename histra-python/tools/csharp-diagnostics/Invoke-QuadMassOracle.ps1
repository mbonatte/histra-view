param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath,[double]$Thickness=.2,[double[]]$Normal=@(0,0,1),[double]$Weight=.0000224)
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$coll=[ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
$model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model]);$model.Collections=$coll
[ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
$mat=[Objects.Material.MasonryMaterial]::new();[Objects.Material.MasonryMaterial].GetProperty('Key').SetValue($mat,[int]1,$null);[Objects.Material.MasonryMaterial].GetProperty('w').SetValue($mat,[single]$Weight,$null);$coll.Templates.Add(1,$mat)
$q=[Objects.Quad]::new();$q.MaterialKey=1
$nodes=[Collections.Generic.List[Objects.Node]]::new();$key=0
foreach($xy in @(@(-.5,0.),@(.5,0.),@(.5,1.),@(-.5,1.))) {
 $key++;$n=[Objects.Node]::new();[Objects.Node].GetProperty('Key').SetValue($n,[int]$key,$null)
 [Objects.Node].GetProperty('Point').SetValue($n,[Microsoft.Xna.Framework.Vector3]::new([single]$xy[0],[single]$xy[1],0),$null)
 $nodes.Add($n);$coll.Nodes.Insert($n)
}
$q.NodeKeys=[int[]]@(1,2,3,4)
$q.Thickness=[single[]]@($Thickness,$Thickness,$Thickness,$Thickness)
$normalVector=[Microsoft.Xna.Framework.Vector3]::new([single]$Normal[0],[single]$Normal[1],[single]$Normal[2])
$q.Normal=[Microsoft.Xna.Framework.Vector3[]]@($normalVector,$normalVector,$normalVector,$normalVector)
[void]$q.SetGeometry($nodes,$false,$false)
$affType=[Objects.Quad].GetProperty('Aff').PropertyType.GetGenericArguments()[0]
for($j=0;$j -lt 7;$j++) {$q.Aff.Add([Activator]::CreateInstance($affType))}
$mass=$null;$q.ComputeLocalMassfromSelfWeight([ref]$mass,$false)
$values=@();for($j=0;$j -lt 7;$j++){for($k=0;$k -lt 7;$k++){$values+=$mass.Read($j,$k)}}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');generator='tools/csharp-diagnostics/Invoke-QuadMassOracle.ps1';assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();source='Original Quad.ComputeLocalMassfromSelfWeight';length=@($q.Length);cos=@($q.Cos);sin=@($q.Sin);centre=@([double]$q.G.X,[double]$q.G.Y,[double]$q.G.Z);input_weight=$Weight;input_thickness=$Thickness;input_normal=$Normal;gravity=[double][UtilityLibrary.Matematics.Operations]::g;weight=[double][Objects.Material.MasonryMaterial].GetProperty('w').GetValue($mat,$null);thickness=@($q.Thickness|ForEach-Object{[double]$_});mass=$values}|ConvertTo-Json -Depth 5|Set-Content -LiteralPath $OutputPath -Encoding UTF8
