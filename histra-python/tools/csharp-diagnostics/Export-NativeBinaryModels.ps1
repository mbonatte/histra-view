param([Parameter(Mandatory=$true)][string]$InputDirectory,
      [Parameter(Mandatory=$true)][string]$OutputDirectory,
      [string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath($InputDirectory).TrimEnd([char[]]'\/')
$out=[IO.Path]::GetFullPath($OutputDirectory)
if(Test-Path -LiteralPath $out) {throw 'Use a new output directory; reference files are never overwritten'}
# Windows wildcard matching may also include .hrbk: require the exact extension.
$files=@(Get-ChildItem -LiteralPath $root -Recurse -File -Filter '*.hrb'|Where-Object Extension -eq '.hrb')
if($files.Count -eq 0) {throw 'No .hrb model files were found'}
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {
 [void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))
}
[void][IO.Directory]::CreateDirectory($out)
$ctor=[ModelLibrary.Model].GetConstructors()|Where-Object{$_.GetParameters().Length -eq 2}|Select-Object -First 1
$rows=@()
foreach($file in $files) {
 $before=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
 $model=$ctor.Invoke([object[]]@([enum]::Parse($ctor.GetParameters()[0].ParameterType,'RailBridge'),$false))
 [ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,Public,NonPublic').SetValue($null,$model)
 [SirioSoft.SerializeBinaryReader]::ReadFromFile($file.FullName,'HiStrA',$model)
 $relative=$file.FullName.Substring($root.Length+1)
 $target=Join-Path $out ([IO.Path]::ChangeExtension($relative,'.hrx'))
 [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($target))
 [SirioSoft.SerializeXmlWriter]::WriteToFile($target,'HiStrA',$model,$false,$false)
 if((Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne $before) {throw 'Source model changed during export'}
 $rows+=@{input=$relative;input_sha256=$before;output_sha256=(Get-FileHash $target -Algorithm SHA256).Hash.ToLowerInvariant()}
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');
 source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);
 generator='tools/csharp-diagnostics/Export-NativeBinaryModels.ps1';
 benchmark_id='read-only-native-binary-model-export';
 serializer_assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'SirioCommon.dll') -Algorithm SHA256).Hash.ToLowerInvariant();
 models=$rows}|ConvertTo-Json -Depth 8|Set-Content -LiteralPath (Join-Path $out 'binary-export.json') -Encoding UTF8
