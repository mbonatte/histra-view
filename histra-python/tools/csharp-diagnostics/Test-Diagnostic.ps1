param([Parameter(Mandatory=$true)][string]$DiagnosticRoot)
$ErrorActionPreference = 'Stop'
$app = Join-Path $DiagnosticRoot 'app'
foreach ($name in @('MonoGame.Framework.dll','XNALibrary.dll','UtilityLibrary.dll','SirioCommon.dll','MatrixManager.dll','ModelLibrary.dll','ParityTrace.dll','SolverRuntime.dll')) {
    [void][Reflection.Assembly]::LoadFrom((Join-Path $app $name))
}
$program = New-Object SolverRuntime.Program
$program.add_LogAnalysisEvent({param($message) })
$flags = [Reflection.BindingFlags]'Instance,NonPublic,Public'
$program.GetType().GetMethod('LogAnalysisEvent_RaiseEvent',$flags).Invoke($program,[object[]]@('DIAGNOSTIC_SMOKE_SUCCESS'))
$program.GetType().GetMethod('NewGraphError',$flags).Invoke($program,[object[]]@('TLM_Constant_UDL',1.0,0.001))
$collections = [ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
$assembly = [SolverRuntime.Program].Assembly
$methodNames = @{
    'SolverRuntime.CommonOperations'=@('Commit','AddStateNonLinearAnalysis')
    'SolverRuntime.ModelManager'=@('SetStatus','PrepareModelForAnalysis','SetFextEqualToFint')
    'SolverRuntime.Program'=@('LogAnalysisEvent_RaiseEvent','NewGraphError')
    'SolverRuntime.NumericalProcedure.NewtonRaphson'=@('solveCurrentStep')
    'SolverRuntime.Integrator.LoadControl'=@('NewStep','Commit')
    'SolverRuntime.Integrator.StaticIntegrator'=@('revertToLastCommit')
}
$prepared = 0
foreach ($typeName in $methodNames.Keys) {
    foreach ($method in $assembly.GetType($typeName).GetMethods([Reflection.BindingFlags]'Instance,Static,Public,NonPublic,DeclaredOnly')) {
        if ($method.Name -in $methodNames[$typeName]) { [Runtime.CompilerServices.RuntimeHelpers]::PrepareMethod($method.MethodHandle); $prepared++ }
    }
}
if ($prepared -ne 12) { throw "Unexpected instrumented method count: $prepared" }
$common = $assembly.GetType('SolverRuntime.CommonOperations')
$common.GetMethod('Commit').Invoke($null,[object[]]@($collections,$null))
$interface = [Activator]::CreateInstance([Objects.Interface])
$spring = [Activator]::CreateInstance([Objects.SpringHysteretic])
$spring.U = 0.05217365161936875
$spring.Cstrain = 0.04868369273565119
$list = [Activator]::CreateInstance([Collections.Generic.List[Objects.Spring]])
$list.Add($spring)
[Objects.Interface].GetProperty('Trasv_1').SetValue($interface,$list,$null)
$dictionary = $collections.Interfaces.Collection
$dictionary.GetType().GetMethod('Add').Invoke($dictionary,[object[]]@([int]681,$interface))
$phaseInterface = [Activator]::CreateInstance([Objects.Interface])
$phaseSpring = [Activator]::CreateInstance([Objects.SpringHysteretic])
$phaseSpring.Cstress = -0.008999158310192793
[Objects.SpringHysteretic].GetField('_CrotNu',$flags).SetValue($phaseSpring,[double]0.00017782434173150004)
$phaseList = [Activator]::CreateInstance([Collections.Generic.List[Objects.Spring]])
$phaseList.Add($phaseSpring)
[Objects.Interface].GetProperty('Trasv_1').SetValue($phaseInterface,$phaseList,$null)
$dictionary.GetType().GetMethod('Add').Invoke($dictionary,[object[]]@([int]356,$phaseInterface))
[ParityTrace]::Record('NATIVE_SPRING_SNAPSHOT_TEST',$null,[object[]]@($collections))
$loadControlType = $assembly.GetType('SolverRuntime.Integrator.LoadControl')
$loadControl = [Activator]::CreateInstance($loadControlType,$true)
$incrementalType = $assembly.GetType('SolverRuntime.Integrator.IncrementalIntegrator')
$vectorConstructor = [MatrixManager.Vector].GetConstructor([Type[]]@([int]))
$incrementalType.GetField('U',$flags).SetValue($loadControl,$vectorConstructor.Invoke([object[]]@([int]0)))
$incrementalType.GetField('U_commited',$flags).SetValue($loadControl,$vectorConstructor.Invoke([object[]]@([int]0)))
$linearSystem = [Activator]::CreateInstance([MatrixManager.LinearSystem])
$emptyCollections = [ModelLibrary.Collections].GetConstructor([Type[]]@([bool])).Invoke([object[]]@($false))
$assembly.GetType('SolverRuntime.Integrator.StaticIntegrator').GetMethod('revertToLastCommit',$flags).Invoke($loadControl,[object[]]@($emptyCollections,$linearSystem))
$files = Get-ChildItem (Join-Path $app 'parity-logs') -Filter '*.tsv' | Sort-Object LastWriteTime -Descending
$text = Get-Content -LiteralPath $files[0].FullName -Raw
foreach ($marker in @('DIAGNOSTIC_SMOKE_SUCCESS','NewGraphError/enter','Commit/enter','Commit/exit','revertToLastCommit/enter','revertToLastCommit/exit','SPRING',"U=0.05217365161936875",'Cstrain=0.04868369273565119')) {
    if (-not $text.Contains($marker)) { throw "Missing diagnostic record: $marker" }
}
foreach ($marker in @("SPRING`tInterfaces`t356`tTrasv_1`t0", 'Cstress=-0.008999158310192793', '_CrotNu=0.00017782434173150004', '_Eup=', '_mom2p=')) {
    if (-not $text.Contains($marker)) { throw "Missing targeted phase diagnostic: $marker" }
}
Write-Output "PASS: all 12 instrumented methods JIT-compiled; success-only native calls wrote and flushed $($files[0].FullName)"
