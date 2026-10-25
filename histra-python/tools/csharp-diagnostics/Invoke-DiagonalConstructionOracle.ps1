param([Parameter(Mandatory=$true)][string]$InstalledRoot,[Parameter(Mandatory=$true)][string]$OutputPath)
$ErrorActionPreference='Stop'
$i=$InstalledRoot
foreach($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll')) {[void][Reflection.Assembly]::LoadFrom((Join-Path $i $name))}
$output=@()
$geometries=@(
    @{name='rectangle';points=@(@(0.,0.),@(100.,0.),@(100.,200.),@(0.,200.));thickness=@(10,10,10,10)},
    @{name='tapered-skew';points=@(@(0.,0.),@(137.2,0.),@(129.4,211.3),@(-13.1,183.7));thickness=@(8.3,10.1,12.4,9.7)}
)
foreach($geometry in $geometries) {foreach($fc in @(2.7,0.01)) {
$coll=[ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
$model=[Runtime.Serialization.FormatterServices]::GetUninitializedObject([ModelLibrary.Model]);$model.Collections=$coll
[ModelLibrary.Model].GetField('_model',[Reflection.BindingFlags]'Static,NonPublic').SetValue($null,$model)
$mat=[Activator]::CreateInstance([Objects.Material.MasonryMaterial]);[Objects.Material.MasonryMaterial].GetProperty('Key').SetValue($mat,[int]1,$null);$coll.Templates.Add(1,$mat)
foreach($kind in @('HorizontalFlexional','VerticalFlexional','Shear')) {
 if($kind -eq 'Shear') {$law=[Activator]::CreateInstance([Objects.ConstitutiveLaw.ConstitutiveLawCoulomb]);$law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::Coulomb03;$law.E=230.;$law.Fy_0=.5;$law.Mu=.45;$law.U_r=1.5;$law.IsDuctilityFixed=$true;$law.PlasticStiffnessRatio=.001;$law.ReloadStiffnessRatio=.8;$law.MaxTensileRatio=.4;$law.SubLaw=[UtilityLibrary.Tipi.ShearYieldingDomainEnum]::Coulomb}
 else {$law=[Activator]::CreateInstance([Objects.ConstitutiveLaw.ConstitutiveLawHysteretic]);$law.Type=[UtilityLibrary.Tipi.SpringTypeEnum]::Hysteretic;$law.E=if($kind -eq 'HorizontalFlexional'){500.}else{321.25};$law.Fy_t=.23;$law.Fy_c=[double]$fc;$law.Eps_u_t=.06;$law.Eps_u_c=.08;$law.TensileCurveType=[UtilityLibrary.Tipi.HystereticTensileCurveTypeEnum]::LinearSoftening;$law.CompressiveCurveType=[UtilityLibrary.Tipi.HystereticCompressiveCurveTypeEnum]::LinearSoftening}
 $law.MaterialKey=1;$law.Collocation=[enum]::Parse([UtilityLibrary.Tipi.ConstitutiveLawCollocation],$kind);$coll.ConstitutiveLaws.Insert($law);if($kind -eq "HorizontalFlexional"){$horizontal=$law};if($kind -eq "VerticalFlexional"){$vertical=$law}
}
$q=[Activator]::CreateInstance([Objects.Quad]);$q.MaterialKey=1
$nodes=[Activator]::CreateInstance([Collections.Generic.List[Objects.Node]])
foreach($xy in $geometry.points) {$n=[Activator]::CreateInstance([Objects.Node]);[Objects.Node].GetProperty('Point').SetValue($n,[Microsoft.Xna.Framework.Vector3]::new([single]$xy[0],[single]$xy[1],[single]0.),$null);$nodes.Add($n)}
$q.Thickness=[single[]]$geometry.thickness;$q.Normal=[Microsoft.Xna.Framework.Vector3[]]@([Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ,[Microsoft.Xna.Framework.Vector3]::UnitZ)
[void]$q.SetGeometry($nodes,$false,$false);$q.SetDiagonalQuad()
$blend=$vertical.Clone();$c=0.5*[math]::Pow(2.0,0.5);$blend.PropOrthotropyParameter($c,$c,$horizontal)
$output += @{geometry=$geometry.name;thickness=@($q.Thickness|ForEach-Object{[double]$_});volume=$q.GetVolume();K=$q.Spring.K;Fy=$q.Spring.Fy;Ur=$q.Spring.Ur;Area=$q.Spring.Area;Length=$q.Length;Diago=$q.Diago;Sin=$q.Sin;Cos=$q.Cos;input_fy_c=$fc;flex_type=$vertical.Type.ToString();blend_E=$blend.E;blend_eps_t=$blend.Eps_u_t;blend_eps_c=$blend.Eps_u_c}
}}
@{source="Original Quad.SetDiagonalQuad with masonry Hysteretic flexural laws, including very weak compression";cases=$output}|ConvertTo-Json -Depth 7|Set-Content -LiteralPath $OutputPath -Encoding UTF8
