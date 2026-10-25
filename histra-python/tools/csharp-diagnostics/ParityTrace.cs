using System;
using System.Collections;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text;

public static class ParityTrace
{
    static readonly object Gate = new object();
    static StreamWriter Writer;
    static int LinearSequence;
    static void CaptureLinear(string label, object instance)
    {
        string directory = Environment.GetEnvironmentVariable("HISTRA_PARITY_CAPTURE_DIR");
        if (String.IsNullOrEmpty(directory) || label != "SolverRuntime.Program.NewGraphError/enter") return;
        object system = Get(instance, "LS");
        if (system == null) return;
        Directory.CreateDirectory(directory);
        string prefix = Path.Combine(directory, "newton-" + (LinearSequence++).ToString("D5"));
        object matrix = Get(system, "K");
        foreach (string name in new[] { "Ap", "Ai", "Ax", "b", "x" })
        {
            object value = name == "b" || name == "x" ? Get(Get(system, name), "theData") : Get(matrix, name);
            Array array = value as Array;
            if (array == null) continue;
            byte[] bytes = new byte[Buffer.ByteLength(array)];
            Buffer.BlockCopy(array, 0, bytes, 0, bytes.Length);
            File.WriteAllBytes(prefix + "-" + name + ".bin", bytes);
        }
    }
    static object Get(object value, string name)
    {
        if (value == null) return null;
        for (Type t = value.GetType(); t != null; t = t.BaseType)
        {
            var flags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly;
            foreach (var p in t.GetProperties(flags))
                if (p.Name == name && p.GetIndexParameters().Length == 0) return p.GetValue(value, null);
            var f = t.GetField(name, flags);
            if (f != null) return f.GetValue(value);
        }
        return null;
    }
    static string Format(object value)
    {
        if (value == null) return "null";
        if (value is double) return ((double)value).ToString("R", CultureInfo.InvariantCulture);
        if (value is float) return ((float)value).ToString("R", CultureInfo.InvariantCulture);
        if (value.GetType().FullName == "MatrixManager.Vector") return Format(Get(value, "theData"));
        if (value is string) return ((string)value).Replace("\r", " ").Replace("\n", " ").Replace("\t", " ");
        if (value is IEnumerable)
        {
            var b = new StringBuilder("["); int n = 0;
            foreach (var item in (IEnumerable)value) { if (n++ > 0) b.Append(','); b.Append(Format(item)); if (n >= 16) break; }
            return b.Append(']').ToString();
        }
        return Convert.ToString(value, CultureInfo.InvariantCulture);
    }
    static void Fields(StringBuilder b, object value, string prefix, params string[] names)
    {
        foreach (string name in names) b.Append('\t').Append(prefix).Append(name).Append('=').Append(Format(Get(value, name)));
    }
    static void Snapshots(StringBuilder b, object collections)
    {
        foreach (string family in new[] { "Interfaces", "Quads" })
        {
            var dictionary = Get(Get(collections, family), "Collection") as IDictionary;
            if (dictionary == null) continue;
            int[] keys = family == "Interfaces" ? new[] { 272, 356, 681, 1806, 863, 5818 } : new[] { 1111 };
            foreach (int key in keys)
            {
                if (!dictionary.Contains(key)) continue;
                var element = dictionary[key];
                b.Append("\nELEMENT\t").Append(family).Append('\t').Append(key);
                Fields(b, Get(element, "Status"), "status.", "U", "Forces", "BendingMoments");
                foreach (string list in new[] { "Trasv_1", "Trasv_2", "Slid", "SlidOutPlan", "Spring" })
                {
                    object springs = Get(element, list);
                    if (springs == null) continue;
                    var values = springs as IEnumerable;
                    if (values == null) values = new object[] { springs };
                    int index = 0;
                    foreach (object spring in values)
                    {
                        b.Append("\nSPRING\t").Append(family).Append('\t').Append(key).Append('\t').Append(list).Append('\t').Append(index++);
                        Fields(b, spring, "", "U", "F", "K_tang", "Phase", "N", "Fy", "Up", "Cstrain", "Tstrain", "Cstress", "Tstress", "CstressNormal", "CstressNormalPrev", "CmomMax");
                        if (family == "Interfaces" && (key == 272 || key == 356))
                            Fields(b, spring, "", "K", "Kt", "Ur", "Alfar", "Alfau",
                                "TPhase", "CenergyD", "Umax", "_CrotPu", "_CrotNu", "_CloadIndicator",
                                "_TrotPu", "_TrotNu", "_TrotMax", "_TrotMin", "_TloadIndicator",
                                "_mom1p", "_mom2p", "_mom3p", "_rot1p", "_rot2p", "_rot3p",
                                "_E1p", "_E2p", "_E3p", "_Eup", "_Eun");
                    }
                }
            }
        }
    }
    public static void Record(string label, object instance, object[] args)
    {
        try
        {
            lock (Gate)
            {
                CaptureLinear(label, instance);
                if (Writer == null)
                {
                    string dir = Path.Combine(Path.GetDirectoryName(typeof(ParityTrace).Assembly.Location), "parity-logs");
                    Directory.CreateDirectory(dir);
                    string path = Path.Combine(dir, "trace-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss-fff") + "-" + System.Diagnostics.Process.GetCurrentProcess().Id + ".tsv");
                    Writer = new StreamWriter(path, false, new UTF8Encoding(false)); Writer.AutoFlush = true;
                    Writer.WriteLine("TRACE_VERSION=1\tUTC\tAlways written, including successful runs. Step 0 is initial state.");
                }
                var b = new StringBuilder(DateTime.UtcNow.ToString("O")).Append('\t').Append(label);
                Fields(b, instance, "integrator.", "Step", "Iteration", "Mult", "IncrMult", "_t", "U", "U_commited");
                object collections = null;
                for (int i = 0; i < args.Length; i++)
                {
                    var a = args[i]; b.Append("\targ").Append(i).Append('=').Append(Format(a));
                    if (a != null && a.GetType().FullName == "ModelLibrary.Collections") collections = a;
                    if (a != null && a.GetType().FullName == "Objects.Analyses.Analysis") Fields(b, a, "analysis.", "Key", "Name", "InitialAnalysisKey", "LoadCombinationKey", "LoadFunctionKey");
                }
                if (collections != null) Snapshots(b, collections);
                Writer.WriteLine(b.ToString());
            }
        }
        catch (Exception e) { System.Diagnostics.Trace.WriteLine("ParityTrace logging failure: " + e); }
    }
    public static void RecordResult(object result, string label)
    {
        Record(label + "/result", null, new object[] { result });
    }
}
