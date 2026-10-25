param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$env:PATH=(Join-Path $InstalledRoot 'x64')+';'+$env:PATH
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','SolverRuntime.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstalledRoot $name))}
$flags=[Reflection.BindingFlags]'Static,NonPublic,Public';$instance=[Reflection.BindingFlags]'Instance,NonPublic,Public'
$cases=@()
foreach($case in @(@{name='regular';k=10.;tangent=6.},@{name='fallback';k=10.;tangent=0.},@{name='singular';k=0.;tangent=0.})) {
 $coll=[ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
 $model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model]);$model.Collections=$coll
 [ModelLibrary.Model].GetField('_model',$flags).SetValue($null,$model)
 $q=[Objects.Quad]::new();$q.Key=1;$nodes=[Collections.Generic.List[Objects.Node]]::new()
 foreach($xy in @(@(0.,0.),@(100.,0.),@(100.,200.),@(0.,200.))) {$n=[Objects.Node]::new();[Objects.Node].GetProperty('Point').SetValue($n,[Microsoft.Xna.Framework.Vector3]::new([single]$xy[0],[single]$xy[1],0),$null);$nodes.Add($n)}
 $q.Thickness=[single[]]@(10,10,10,10);$q.Normal=[Microsoft.Xna.Framework.Vector3[]]@([Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ)
 [void]$q.SetGeometry($nodes,$false,$false)
 $spring=[Objects.SpringHysteretic]::new();$spring.K=$case.k;$spring.K_tang=$case.tangent;$q.Spring=$spring
 $aff=[Collections.Generic.List[MatrixManager.AfferenceMatrix]]::new();for($j=0;$j -lt 7;$j++){$row=[MatrixManager.AfferenceMatrix]::new();if($j -eq 6){$row.Add_Gdl(1);$row.Add_Alfa(1.)};$aff.Add($row)};$q.Aff=$aff
 $coll.Quads.Collection.Add(1,$q)
 [void][SolverRuntime.ModelManager].GetMethod('SetAffElements',$flags).Invoke($null,[object[]]@($coll,[int]1))
 $p=[SolverRuntime.Program]::new();$ls=[MatrixManager.LinearSystem]::new();[SolverRuntime.Program].GetField('_LS',$instance).SetValue($p,$ls)
 $ls.K=[MatrixManager.SparseMatrix]::new();$ls.K.Mask.SetDimension(1)
 [void][SolverRuntime.ModelManager].GetMethod('ComputeMaskK',$flags).Invoke($null,[object[]]@($p,$coll,$false));[void]$ls.K.MapSparseMatrix();$ls.InitVectors();if(!$ls.SymbolicFactorization()){throw 'Native symbolic factorization failed'};$ls.SetB(0,3.)
 $type=[SolverRuntime.Program].Assembly.GetType('SolverRuntime.Integrator.ArcLength');$integrator=[Activator]::CreateInstance($type,$true)
 $method=$type.GetMethod('UpdateK',$instance);$arguments=[object[]]@($p,$coll,[double]1.,$false)
 [void]$method.Invoke($integrator,$arguments)
 $fields=@{length=@($q.Length);diago=@($q.Diago);sin=@($q.Sin);cos=@($q.Cos);name=$case.name;k=$case.k;tangent=$case.tangent;alpha=[double]$arguments[2];status=[SolverRuntime.Program].GetProperty('IndexFactK',$instance).GetValue($p,$null);matrix=@($ls.K.Ax);x=@($ls.x.theData);b=@($ls.b.theData)}
 if($case.name -eq 'fallback') {$spring.K_tang=6.;$arguments[2]=[double]$arguments[2];[void]$method.Invoke($integrator,$arguments);$fields.next_alpha=[double]$arguments[2];$fields.next_matrix=@($ls.K.Ax);$fields.next_x=@($ls.x.theData)}
 foreach($field in @('matrix','x','b','next_matrix','next_x')) {if($fields.ContainsKey($field)) {$fields[$field+'_bits']=@($fields[$field]|ForEach-Object{[BitConverter]::DoubleToInt64Bits([double]$_).ToString()});$fields.Remove($field)}}
 if($case.name -eq 'fallback') {$fresh=[object[]]@($p,$coll,[double]1.,$false);[void]$method.Invoke($integrator,$fresh);$fields.new_call_alpha=[double]$fresh[2];$fields.new_call_matrix_bits=@($ls.K.Ax|ForEach-Object{[BitConverter]::DoubleToInt64Bits([double]$_).ToString()});$fields.new_call_x_bits=@($ls.x.theData|ForEach-Object{[BitConverter]::DoubleToInt64Bits([double]$_).ToString()})}
 $cases+=$fields
}
@{schema_version=1;generator='tools/csharp-diagnostics/Invoke-StaticTangentFallbackOracle.ps1';generated_at=[DateTime]::UtcNow.ToString('o');assembly_sha256=(Get-FileHash (Join-Path $InstalledRoot 'SolverRuntime.dll') -Algorithm SHA256).Hash.ToLower();cases=$cases}|ConvertTo-Json -Depth 7|Set-Content -Encoding UTF8 $OutputPath
