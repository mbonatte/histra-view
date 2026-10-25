param([Parameter(Mandatory=$true)][string]$OutputPath,[string]$InstallDirectory='C:\Program Files\Gruppo Sismica\HiStrA Bridges 2026.1.1')
$ErrorActionPreference='Stop'
foreach($name in @('MonoGame.Framework.dll','UtilityLibrary.dll','SirioCommon.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $InstallDirectory $name))}
$primary=@('Number','Psi0','Psi1','Psi2','GammaFavSTR','GammaUnfavSTR','GammaFavGEO','GammaUnfavGEO','GammaFavSTR_Psi0','GammaUnfavSTR_Psi0','GammaFavGEO_Psi0','GammaUnfavGEO_Psi0','GC','Psi0_GC','Psi1_GC','Psi2_GC','GammaFavSTR_GC','GammaUnfavSTR_GC','GammaFavGEO_GC','GammaUnfavGEO_GC','GammaFavSTR_Psi0_GC','GammaUnfavSTR_Psi0_GC','GammaFavGEO_Psi0_GC','GammaUnfavGEO_Psi0_GC','GammaFavSTR_Psi1_GC','GammaUnfavSTR_Psi1_GC')
$secondary=$primary[0..11]
$inputs=@(@(.75,.9,1.35,.8,1.25,.6,.4,.2),@(.71362591,1.2000001,1.4999999,.91234567,1.5123456,.71234567,.41234567,.21234567),@(-.123456789,.987654321,1.33333333,.77777777,1.6666667,.87654321,.54321098,.32109876))
$rows=[Collections.Generic.List[object]]::new()
foreach($inputValues in $inputs) {
 $lc=[Objects.Loads.LoadCondition]::new();$lc.Name='Test'
 $lc.GammaFavSTR=[single]$inputValues[1];$lc.GammaUnfavSTR=[single]$inputValues[2];$lc.GammaFavGEO=[single]$inputValues[3];$lc.GammaUnfavGEO=[single]$inputValues[4]
 $lti=[Objects.Loads.LoadTemplateItem]::new();$lti.Psi0=[single]$inputValues[5];$lti.Psi1=[single]$inputValues[6];$lti.Psi2=[single]$inputValues[7]
 $combo=[Objects.Loads.LoadCombination]::new();$table=[Data.DataTable]::new();[void]$table.Columns.Add('Test',[Objects.Loads.CombinationCoefficientData]);$row=$table.NewRow();$table.Rows.Add($row);$combo.Coefficient=$table
 foreach($p in $primary) {
  $secondaries=if($p -eq 'GC' -or $p.EndsWith('_GC')) {$secondary} else {@('Number')}
  foreach($s in $secondaries) {
   $coefficient=[Objects.Loads.CombinationCoefficientData]::new([enum]::Parse([UtilityLibrary.Tipi.TypeDataEnum],$p),[single]$inputValues[0],[enum]::Parse([UtilityLibrary.Tipi.TypeDataEnum],$s));$row['Test']=$coefficient
   $value=[CommonObjectManagement.LoadTemplateManager]::GetCoefficient($combo,1,$lc,$lti)
   $rows.Add(@{primary=$p;secondary=$s;inputs=$inputValues;value=[double]$value})
  }
 }
}
@{schema_version=1;generated_at=[DateTime]::UtcNow.ToString('o');source_commit=(& git -C (Join-Path $PSScriptRoot '../..') rev-parse HEAD);generator='tools/csharp-diagnostics/Invoke-LoadCoefficientOracle.ps1';benchmark_id='native-load-coefficients-2026.1.1';assembly_sha256=(Get-FileHash (Join-Path $InstallDirectory 'ModelLibrary.dll') -Algorithm SHA256).Hash.ToLowerInvariant();cases=$rows}|ConvertTo-Json -Depth 6 -Compress|Set-Content -LiteralPath $OutputPath -Encoding UTF8
