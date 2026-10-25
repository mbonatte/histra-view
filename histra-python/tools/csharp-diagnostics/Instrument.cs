using System;
using System.Collections.Generic;
using System.Linq;
using dnlib.DotNet;
using dnlib.DotNet.Emit;
using dnlib.DotNet.Writer;

public static class Instrument
{
    static IMethod Hook;
    static IMethod ResultHook;
    static List<Instruction> Trace(MethodDef m, string suffix)
    {
        var il = new List<Instruction>();
        il.Add(Instruction.Create(OpCodes.Ldstr, m.DeclaringType.FullName + "." + m.Name + "/" + suffix));
        il.Add(m.IsStatic ? Instruction.Create(OpCodes.Ldnull) : Instruction.Create(OpCodes.Ldarg_0));
        var args = m.Parameters.Where(p => !p.IsHiddenThisParameter).ToArray();
        il.Add(Instruction.CreateLdcI4(args.Length));
        il.Add(Instruction.Create(OpCodes.Newarr, m.Module.CorLibTypes.Object.TypeDefOrRef));
        for (int i = 0; i < args.Length; i++)
        {
            il.Add(Instruction.Create(OpCodes.Dup)); il.Add(Instruction.CreateLdcI4(i));
            il.Add(Instruction.Create(OpCodes.Ldarg, args[i]));
            TypeSig type = args[i].Type;
            if (type is ByRefSig)
            {
                type = type.Next;
                if (type.IsValueType) il.Add(Instruction.Create(OpCodes.Ldobj, type.ToTypeDefOrRef()));
                else il.Add(Instruction.Create(OpCodes.Ldind_Ref));
            }
            if (type.IsValueType) il.Add(Instruction.Create(OpCodes.Box, type.ToTypeDefOrRef()));
            il.Add(Instruction.Create(OpCodes.Stelem_Ref));
        }
        il.Add(Instruction.Create(OpCodes.Call, Hook)); return il;
    }
    public static int Main(string[] args)
    {
        var module = ModuleDefMD.Load(args[0]);
        var helper = ModuleDefMD.Load(args[2]);
        Hook = module.Import(helper.GetTypes().Single(t => t.Name == "ParityTrace").Methods.Single(m => m.Name == "Record")); int count = 0;
        ResultHook = module.Import(helper.GetTypes().Single(t => t.Name == "ParityTrace").Methods.Single(m => m.Name == "RecordResult"));
        foreach (var type in module.GetTypes()) foreach (var m in type.Methods)
        {
            if (!m.HasBody) continue;
            bool chosen =
                (type.FullName == "SolverRuntime.Program" && (m.Name == "LogAnalysisEvent_RaiseEvent" || m.Name == "NewGraphError")) ||
                (type.FullName == "SolverRuntime.ModelManager" && (m.Name == "SetStatus" || m.Name == "PrepareModelForAnalysis" || m.Name == "SetFextEqualToFint")) ||
                (type.FullName == "SolverRuntime.Integrator.StaticIntegrator" && m.Name == "revertToLastCommit") ||
                (type.FullName == "SolverRuntime.CommonOperations" && (m.Name == "Commit" || m.Name == "AddStateNonLinearAnalysis")) ||
                (type.FullName == "SolverRuntime.Integrator.LoadControl" && (m.Name == "NewStep" || m.Name == "Commit")) ||
                (type.FullName == "SolverRuntime.NumericalProcedure.NewtonRaphson" && m.Name == "solveCurrentStep");
            if (!chosen) continue;
            m.Body.SimplifyBranches(); m.Body.KeepOldMaxStack = false;
            // Keep original ret instruction objects as branch targets. A nop executes the exit hook then a new ret.
            foreach (var ret in m.Body.Instructions.Where(i => i.OpCode == OpCodes.Ret).ToArray())
            {
                int pos = m.Body.Instructions.IndexOf(ret); ret.OpCode = OpCodes.Nop;
                var log = new List<Instruction>();
                if (m.ReturnType.ElementType != ElementType.Void)
                {
                    log.Add(Instruction.Create(OpCodes.Dup));
                    if (m.ReturnType.IsValueType) log.Add(Instruction.Create(OpCodes.Box, m.ReturnType.ToTypeDefOrRef()));
                    log.Add(Instruction.Create(OpCodes.Ldstr, m.DeclaringType.FullName + "." + m.Name));
                    log.Add(Instruction.Create(OpCodes.Call, ResultHook));
                }
                log.AddRange(Trace(m, "exit")); log.Add(Instruction.Create(OpCodes.Ret));
                foreach (var ins in log) m.Body.Instructions.Insert(++pos, ins);
            }
            var entry = Trace(m, "enter");
            for (int i = 0; i < entry.Count; i++) m.Body.Instructions.Insert(i, entry[i]);
            m.Body.OptimizeBranches(); count++; Console.WriteLine(m.FullName);
        }
        if (count < 10) throw new Exception("Unexpected solver metadata; instrumentation refused.");
        module.Write(args[1], new ModuleWriterOptions(module));
        Console.WriteLine("Instrumented methods: " + count); return 0;
    }
}
