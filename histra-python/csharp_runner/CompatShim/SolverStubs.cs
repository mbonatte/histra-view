using System;
using System.Collections.Generic;
using MatrixManager;
using Objects.Analyses;
using UtilityLibrary.Tipi;

namespace Microsoft.Xna.Framework.Design
{
    public class Vector2TypeConverter : System.ComponentModel.TypeConverter { }
    public class Vector3TypeConverter : System.ComponentModel.TypeConverter { }
    public class Vector4TypeConverter : System.ComponentModel.TypeConverter { }
    public class MatrixTypeConverter : System.ComponentModel.TypeConverter { }
}

namespace ModelLibrary
{
    public class Program
    {
        public LinearSystem LS { get; set; } = new LinearSystem();
        public double MaxU { get; set; }
        public int IndexFactK { get; set; }
        public void LogAnalysisEvent_RaiseEvent(string msg) { }
    }

    public class Collections
    {
        public List<ModelManagement.Load.LoadFunctionItem> GetListLoadFunctionItems(int key) =>
            new List<ModelManagement.Load.LoadFunctionItem>();

        public object TryGetElement(int key, ElementTypeEnum type) => null;
        public Dictionary<int, object> Templates { get; set; } = new Dictionary<int, object>();
        public Dictionary<int, object> LoadConditions { get; set; } = new Dictionary<int, object>();
    }

    public class ModelInstance
    {
        public bool disableGeoLinksOnLoadingLateralEarthPressure => false;
        public Collections Collections { get; set; } = new Collections();
    }

    public static class Model
    {
        private static readonly ModelInstance _instance = new ModelInstance();
        public static ModelInstance GetIstance() => _instance;
    }

    public static class ModelManager
    {
        public static Vector Ptarget { get; set; } = new Vector(0);
        public static Vector Fext { get; set; } = new Vector(0);

        public static void FindMaxU(Program p, Collections c) { }
        public static void updateDomain(Collections c, LinearSystem ls, State s) { }
        public static void AssembleLoad(Program p, Collections c) { }
        public static void AssemblePdeltaLoad(Program p, Collections c) { }
    }
}

namespace ModelManagement.Load
{
    public class LoadFunctionItem
    {
        public double multiplier { get; set; }
    }

    public static class ModelLoadOperations
    {
        public static void IncrLocalLoadsApplied(ModelLibrary.Collections c, double val) { }
    }
}

namespace ModelManagement.ComputationalElementsOperations
{
    public static class ModelPointOperations
    {
        public static int[] GetDofs(ModelLibrary.Collections c, Analysis a) => new int[] { -1 };
    }
}

namespace Objects.Analyses
{
    public class State
    {
        public Analysis Analysis { get; set; } = new Analysis();
        public int Combination { get; set; }
        public int Iteration { get; set; }
        public double IncrMult { get; set; }
        public double Mult { get; set; }
        public int Step { get; set; }
    }

    public class Analysis
    {
        public int LoadFunctionKey { get; set; }
        public double TargetDisplacement { get; set; }
        public double Dr2 { get; set; }
        public ArcLengthProcedureEnum ArcLengthProcedure { get; set; }
        public int MasterPoint { get; set; }
        public double LineSearchTolerance { get; set; } = 0.8;
        public double LineSearchMaxEta { get; set; } = 10.0;
        public double LineSearchMinEta { get; set; } = 0.1;
        public int LineSearchMaxIterations { get; set; } = 20;
        public bool UpdateDr2 { get; set; }
        public int DesiredIterations { get; set; } = 4;
        public bool IsMaxArcLengthRay { get; set; }
        public double MaxArcLengthRay { get; set; }
    }
}

namespace MatrixManager
{
    public class LinearSystem
    {
        private Vector _x = new Vector(0);
        private Vector _b = new Vector(0);

        public int N => _x?.sz ?? 0;

        public Vector GetX() => _x;
        public double GetX(int i) => _x.Get(i);
        public void SetX(Vector x) { _x = x; }

        public Vector GetB() => _b;
        public void SetB(Vector b) { _b = b; }

        public int Solve()
        {
            if (_b != null)
            {
                _x = new Vector(_b);
            }
            return 0;
        }

        public void numericFactorization() { }

        public double GetbNorm(int normType)
        {
            if (_b == null || _b.sz == 0) return 0.0;
            if (normType == 1)
            {
                double sum = 0.0;
                for (int i = 0; i < _b.sz; i++) sum += Math.Abs(_b.Get(i));
                return sum;
            }
            if (normType == 2)
            {
                double sum = 0.0;
                for (int i = 0; i < _b.sz; i++) sum += _b.Get(i) * _b.Get(i);
                return Math.Sqrt(sum);
            }
            double max = 0.0;
            for (int i = 0; i < _b.sz; i++) max = Math.Max(max, Math.Abs(_b.Get(i)));
            return max;
        }

        public double GetxNorm(int normType)
        {
            if (_x == null || _x.sz == 0) return 0.0;
            if (normType == 1)
            {
                double sum = 0.0;
                for (int i = 0; i < _x.sz; i++) sum += Math.Abs(_x.Get(i));
                return sum;
            }
            if (normType == 2)
            {
                double sum = 0.0;
                for (int i = 0; i < _x.sz; i++) sum += _x.Get(i) * _x.Get(i);
                return Math.Sqrt(sum);
            }
            double max = 0.0;
            for (int i = 0; i < _x.sz; i++) max = Math.Max(max, Math.Abs(_x.Get(i)));
            return max;
        }

        public double GetXperB()
        {
            if (_x == null || _b == null || _x.sz != _b.sz) return 0.0;
            return _x ^ _b;
        }

        public void ProductMatrixKi(Vector v, double value, double[] data) { }
    }

    public class SparseMatrix
    {
        public int GetAp(int i) => 0;
        public double GetAx(int i) => 0.0;
        public int GetAi(int i) => 0;
    }
}

namespace SolverRuntime.Integrator
{
    internal class IncrementalIntegrator
    {
        public State State { get; set; } = new State();
        public double IncrMult { get; set; }
        public double Mult { get; set; }
        public int Step { get; set; }
        public int Iteration { get; set; }
        public List<string> Error { get; set; } = new List<string>();
        internal Vector U_commited = new Vector(0);
        internal Vector U = new Vector(0);

        internal virtual int Update(ModelLibrary.Collections Collections, ModelLibrary.Program p, Analysis an) => 0;
        internal virtual bool UpdatePtarget(ModelLibrary.Program p, ModelLibrary.Collections Collections, Analysis an, int Combination, int iteration) => false;
        internal virtual void ApplyLoadDomain(ModelLibrary.Program p, ModelLibrary.Collections Collections, double mult) { }
        internal virtual void NewStep(ModelLibrary.Program p, ModelLibrary.Collections Collections, MatrixManager.LinearSystem LS, Analysis an, int Combination, int Step, int idDof) { }
        internal virtual bool Commit(ModelLibrary.Collections Collections, Analysis an, double disp, int idDofMaxDispl, ref bool HasDomainChanged) => false;
        internal virtual double GetTime() => 0.0;
        internal virtual double formUnbalance() => 0.0;
        internal virtual void formUnbalance(ModelLibrary.Program p, ModelLibrary.Collections collections, Analysis an) { }
    }

    internal class StaticIntegrator : IncrementalIntegrator
    {
        internal virtual void domainChanged(ModelLibrary.Program p, ModelLibrary.Collections Collections, int size) { }
    }
}

namespace SolverRuntime.LineSearch
{
    internal class LineSearch
    {
        public double tolerance = 0.8;
        public double maxEta = 10.0;
        public double minEta = 0.1;
        public int maxIter = 20;
        public int printFlag = 0;

        internal virtual int newStep(ModelLibrary.Program p) => 0;
        internal virtual int search(ModelLibrary.Collections collections, ModelLibrary.Program p, SolverRuntime.Integrator.IncrementalIntegrator theIntegrator, Analysis an, double s0, double s1) => 0;
    }
}
