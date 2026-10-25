param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$i=$InstalledRoot
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $i $name))}
$output=@()
foreach($face in 0..5) {
$coll=[ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
$mat=[Activator]::CreateInstance([Objects.Material.MasonryMaterial]);[Objects.Material.MasonryMaterial].GetProperty('Key').SetValue($mat,[int]1,$null)
$coll.Templates.Add(1,$mat)
$q1=[Activator]::CreateInstance([Objects.Quad]);$q1.MaterialKey=1
$q2=[Activator]::CreateInstance([Objects.Quad]);$q2.MaterialKey=1
$q1.ReferenceSystem.Set([Microsoft.Xna.Framework.Vector3]::UnitX,[Microsoft.Xna.Framework.Vector3]::UnitY,[Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::Zero)
$q2.ReferenceSystem.Set([Microsoft.Xna.Framework.Vector3]::new([single]0.6,[single]0.8,[single]0.0),[Microsoft.Xna.Framework.Vector3]::UnitX,[Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::Zero)
$interface=[Activator]::CreateInstance([Objects.Interface])
[Objects.Interface].GetProperty('Nrow').SetValue($interface,[int]0,$null)
[Objects.Interface].GetProperty('Ncol').SetValue($interface,[int]0,$null)
$law1=[Activator]::CreateInstance([Collections.Generic.SortedList[int,Objects.ConstitutiveLaw.ConstitutiveLawBase]])
$law2=[Activator]::CreateInstance([Collections.Generic.SortedList[int,Objects.ConstitutiveLaw.ConstitutiveLawBase]])
for($j=0;$j -lt 8;$j++) {foreach($ls in @($law1,$law2)) {$law=[Activator]::CreateInstance([Objects.ConstitutiveLaw.ConstitutiveLawCoulomb]);$law.E=10+$j;$law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::Coulomb03;$ls.Add($j,$law)}}
$n=[Activator]::CreateInstance([Objects.Node])
$m=[Objects.Interface].GetMethods()|Where-Object {$_.Name -eq 'SetSpring' -and $_.GetParameters().Length -eq 12}
try {[void]$m.Invoke($interface,[object[]]@($coll,$interface,$q1,$q2,$n,$n,$law1,$law2,[int]$face,[int]$face,$false,$false))}catch{throw}
$output += @{face=$face;first_side_E=$law1[5].E;second_side_E=$law2[5].E;second_is_vertical=[object]::ReferenceEquals($law2[5],$law2[6]);second_is_dir3=[object]::ReferenceEquals($law2[5],$law2[7])}
}
@{source="Original node-based Interface.SetSpring, zero transverse cells to isolate law selection; not a physical analysis";cases=$output}|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $OutputPath -Encoding UTF8
