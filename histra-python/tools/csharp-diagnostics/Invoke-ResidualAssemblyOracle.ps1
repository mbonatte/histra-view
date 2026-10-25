param([Parameter(Mandatory=$true)][string]$ModelPath,[Parameter(Mandatory=$true)][string]$OutputDirectory,[string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1',[switch]$ReapplySavedMaterials,[Parameter(Mandatory=$true)][string]$InputDirectory)
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
$flags=[Reflection.BindingFlags]'Static,NonPublic,Public'
$instance=[Reflection.BindingFlags]'Instance,NonPublic,Public'
Add-Type -ReferencedAssemblies @((Join-Path $i 'ModelLibrary.dll'),(Join-Path $i 'MonoGame.Framework.dll'),(Join-Path $i 'MatrixManager.dll')) -TypeDefinition @'
using System;
using System.IO;
using System.Collections.Generic;
public class FixedResidualForce : Objects.Spring {
 public double Value;
 public override double GetForce() { return Value; }
 public override void TurnOn() {} public override void TurnOff() {}
 protected override double TrialStrain { get { return 0; } }
 protected override double CommitStrain { get { return 0; } }
 protected override double TrialStress { get { return Value; } }
 protected override double CommitStress { get { return Value; } }
}
public static class ResidualProbe {
 public static int Apply(ModelLibrary.Collections c, string path) {
  int count=0;
  var seen=new HashSet<string>();
  using(var input=new BinaryReader(File.OpenRead(path))) {
   while(input.BaseStream.Position < input.BaseStream.Length) {
    int family=input.ReadInt32(),key=input.ReadInt32(),purpose=input.ReadInt32(),local=input.ReadInt32();
    var spring=new FixedResidualForce { Value=input.ReadDouble() };
    if(!seen.Add(family+":"+key+":"+purpose+":"+local)) throw new Exception("Duplicate force identity");
    if(family==106 && purpose==30 && local==0) c.Quads.Collection[key].Spring=spring;
    else if(family==102) {
     var element=c.Interfaces.Collection[key];
     List<Objects.Spring> group=purpose==1 ? element.Trasv_1 : purpose==11 ? element.Slid : purpose==21 ? element.SlidOutPlan : null;
     if(group==null) throw new Exception("Unknown spring purpose");
     group[local]=spring;
    } else throw new Exception("Unknown spring family");
    count++;
   }
  }
  return count;
 }
 public static double[] Read(string path) {
  byte[] bytes=File.ReadAllBytes(path);
  if(bytes.Length%8!=0) throw new Exception("Invalid vector bytes");
  double[] result=new double[bytes.Length/8];Buffer.BlockCopy(bytes,0,result,0,bytes.Length);return result;
 }
 public static void Write(string path,double[] values) {
  byte[] bytes=new byte[values.Length*8];Buffer.BlockCopy(values,0,bytes,0,bytes.Length);File.WriteAllBytes(path,bytes);
 }
}
'@
[void][SolverRuntime.ModelManager].GetMethod('ComputeAff',$flags).Invoke($null,[object[]]@($p,$model.Collections))
[void][SolverRuntime.ModelManager].GetMethod('SetAffElements',$flags).Invoke($null,[object[]]@($model.Collections,[int]$model.GDL))
$ls=[SolverRuntime.Program].GetField('_LS',$instance).GetValue($p)
$ls.K=[MatrixManager.SparseMatrix]::new();$ls.K.N=[int]$model.GDL;$ls.InitVectors()
$rows=@()
foreach($case in (Get-Content (Join-Path $InputDirectory 'cases.json') -Raw|ConvertFrom-Json)) {
 $name=$case.name
 $count=[ResidualProbe]::Apply($model.Collections,(Join-Path $InputDirectory ($name+'-forces.bin')))
 if($count -ne [int]$case.spring_records) {throw 'Spring count mismatch'}
 $fext=[ResidualProbe]::Read((Join-Path $InputDirectory ($name+'-fext.bin')))
 [SolverRuntime.ModelManager].GetField('_Fext',$flags).SetValue($null,[MatrixManager.Vector]::new($fext))
 $analysis=$model.Collections.Analyses[[int]$case.analysis_key]
 [void][SolverRuntime.ModelManager].GetMethod('formUnbalance',$flags).Invoke($null,[object[]]@($model.Collections,$ls,$analysis))
 [ResidualProbe]::Write((Join-Path $a ($name+'-native-b.bin')),$ls.b.theData)
 $ls.x=[MatrixManager.Vector]::new([ResidualProbe]::Read((Join-Path $InputDirectory ($name+'-x.bin'))))
 $values=@{name=$name;analysis_key=[int]$case.analysis_key;step=[int]$case.step;spring_records=$count;native_b_norm=$ls.GetbNorm(2);native_work=(0.5*[Math]::Abs($ls.GetXperB()))}
 foreach($label in @('CTestEnergyIncr','CTestNormUnbalance')) {
  $type=[SolverRuntime.Program].Assembly.GetType('SolverRuntime.ConvergenceTest.'+$label)
  if($label -eq 'CTestEnergyIncr') {$types=[Type[]]@([double],[int],[double]);$parameters=[object[]]@([double]0.002,[int]3000,[double]10)}
  else {$types=[Type[]]@([double],[int],[double],[int],[bool]);$parameters=[object[]]@([double]0.002,[int]3000,[double]10,[int]2,$true)}
  $test=$type.GetConstructor($instance,$null,$types,$null).Invoke($parameters)
  [void]$type.GetMethod('start',$instance).Invoke($test,@())
  $values[$label+'_result']=$type.GetMethod('test',$instance,$null,[Type[]]@([SolverRuntime.Program],[ModelLibrary.Collections],[MatrixManager.LinearSystem]),$null).Invoke($test,[object[]]@($p,$model.Collections,$ls))
  $errorValue=[double]$type.GetMethod('getError',$instance).Invoke($test,@())
  $values[$label+'_error_bits']=[BitConverter]::DoubleToInt64Bits($errorValue).ToString()
 }
 $rows+=$values
 Write-Output ('Original force assembly and convergence tests completed '+$name)
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');generator='Invoke-ResidualAssemblyOracle.ps1';assembly_sha256=(Get-FileHash (Join-Path $i 'SolverRuntime.dll') -Algorithm SHA256).Hash.ToLower();scope='Fresh native geometry and afference; controlled GetForce values from saved C# output isolate original residual assembly; exported Python correction and Fext are inputs. Routine replay, not an independent native nonlinear solve.';cases=$rows}|ConvertTo-Json -Depth 6|Set-Content (Join-Path $a 'native-residual-summary.json') -Encoding UTF8
