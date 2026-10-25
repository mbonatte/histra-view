using System;
using UtilityLibrary.Tipi;

namespace Objects
{
    public class ReferenceSystem { }
    public class Element { }
    public abstract class ComputationalElement : Element
    {
        public Microsoft.Xna.Framework.Vector2[] GetVInt2D() => Array.Empty<Microsoft.Xna.Framework.Vector2>();
    }

    public class Interface : ComputationalElement
    {
        public object GetParent(int i) => null;
    }

    public class Restraint : Element
    {
        public int GetMaterialKey() => 0;
        public int LoadConditionKey => 0;
    }
}

namespace Objects.ConstitutiveLaw
{
    public class ConstitutiveLawBase
    {
        public SpringTypeEnum Type { get; set; }
        public double E { get; set; }
        public ConstitutiveLawCollocation Collocation { get; set; }
    }

    public class ConstitutiveLawElastic : ConstitutiveLawBase
    {
    }

    public class ConstitutiveLawCoulomb : ConstitutiveLawBase
    {
        public double PlasticStiffnessRatio { get; set; }
        public double ReloadStiffnessRatio { get; set; }
        public double MaxTensileRatio { get; set; }
        public bool CheckContactArea { get; set; }
        public bool FractureEnergy { get; set; }
        public double FractureEnergyValue { get; set; }
        public double Cohesion { get; set; }
        public double FrictionAngle { get; set; }
        public double Mu { get; set; }
        public double Fy_0 { get; set; }
        public double G { get; set; }
    }

    public class ConstitutiveLawHysteretic : ConstitutiveLawBase
    {
        public double Poisson { get; set; }
        public double Fy_c { get; set; }
        public double Fy_t { get; set; }
        public double Fu_c { get; set; }
        public double Fu_t { get; set; }
        public double Eps_u_c { get; set; }
        public double Eps_u_t { get; set; }
        public double[] Alfa_u { get; set; } = new double[4];
        public double[] Alfa_r { get; set; } = new double[4];
        public double RatioEtcomp { get; set; }
        public double RatioEttrac { get; set; }
        public double[] G { get; set; } = new double[10];
        public HystereticCompressiveCurveTypeEnum CompressiveCurveType { get; set; }
        public HystereticTensileCurveTypeEnum TensileCurveType { get; set; }
    }
}

namespace Objects.Material
{
    public class MasonryMaterial
    {
        public ConstitutiveLawMasonryShearEnum ConstitutiveLawMasonryShear { get; set; }
        public double GetShearUltimateStrain(object a = null, object b = null, object c = null, object d = null) => 0.0;
    }
    public class GeotecnicalMaterial { }
}

namespace ModelManagement
{
    public static class ModelDrawer
    {
        public static ResponseTypeEnum ResponseType => ResponseTypeEnum.Displacements;
    }
}

namespace UtilityLibrary.Matematics
{
    internal static class RealPolynomialRootFinder
    {
        public static System.Numerics.Complex[] FindRoots(double[] coeffs) => Array.Empty<System.Numerics.Complex>();
    }
}

namespace Microsoft.Xna.Framework
{
    public struct Plane
    {
        public Vector3 Normal;
        public float D;

        public Plane(Vector4 value)
        {
            Normal = new Vector3(value.X, value.Y, value.Z);
            D = value.W;
        }

        public Plane(Vector3 normal, float d)
        {
            Normal = normal;
            D = d;
        }

        public Plane(Vector3 a, Vector3 b, Vector3 c)
        {
            Normal = Vector3.Normalize(Vector3.Cross(b - a, c - a));
            D = -Vector3.Dot(Normal, a);
        }

        public void Normalize()
        {
            float factor = 1f / Normal.Length();
            Normal *= factor;
            D *= factor;
        }

        public static void Normalize(ref Plane plane, out Plane result)
        {
            float factor = 1f / plane.Normal.Length();
            result = new Plane(plane.Normal * factor, plane.D * factor);
        }
    }

    public struct Ray
    {
        public Vector3 Position;
        public Vector3 Direction;

        public Ray(Vector3 position, Vector3 direction)
        {
            Position = position;
            Direction = direction;
        }
    }
}
