using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using System.Text.Json;
using MatrixManager;
using Microsoft.Xna.Framework;
using ModelLibrary;
using ModelLibrary.MacroKernel.MacroNumTools;
using Objects;
using Objects.Analyses;
using SolverRuntime.ConvergenceTest;
using SolverRuntime.Integrator;
using UtilityLibrary.Matematics;
using UtilityLibrary.Tipi;

namespace HiStrA.MicroRunner
{
    public class Program
    {
        public static int Main(string[] args)
        {
            if (args.Length == 0)
            {
                Console.Error.WriteLine("Usage: HiStrA.MicroRunner <command> [json_payload]");
                Console.Error.WriteLine("Commands: spring-coulomb, spring-multilinear, spring-hysteretic, polygon-clipping, polygon-area, gauss-quadrature, arc-length, convergence-criteria");
                return 1;
            }

            string command = args[0].ToLowerInvariant();
            string jsonInput;

            if (args.Length >= 2)
            {
                jsonInput = string.Join(" ", args, 1, args.Length - 1);
            }
            else
            {
                using var reader = new StreamReader(Console.OpenStandardInput());
                jsonInput = reader.ReadToEnd();
            }

            if (string.IsNullOrWhiteSpace(jsonInput))
            {
                jsonInput = "{}";
            }

            try
            {
                using var doc = JsonDocument.Parse(jsonInput);
                var root = doc.RootElement;

                string outputJson = command switch
                {
                    "spring-coulomb" => HandleSpringCoulomb(root),
                    "spring-multilinear" => HandleSpringMultiLinear(root),
                    "spring-hysteretic" => HandleSpringHysteretic(root),
                    "polygon-clipping" => HandlePolygonClipping(root),
                    "polygon-area" => HandlePolygonArea(root),
                    "gauss-quadrature" => HandleGaussQuadrature(root),
                    "arc-length" => HandleArcLength(root),
                    "convergence-criteria" => HandleConvergenceCriteria(root),
                    _ => throw new ArgumentException($"Unknown command: '{command}'")
                };

                Console.WriteLine(outputJson);
                return 0;
            }
            catch (Exception ex)
            {
                var errObj = new Dictionary<string, object>
                {
                    ["error"] = ex.Message,
                    ["stackTrace"] = ex.StackTrace ?? ""
                };
                Console.Error.WriteLine(JsonSerializer.Serialize(errObj));
                return 2;
            }
        }

        #region Helper Extraction Functions

        private static double GetDouble(JsonElement el, string propName, double defaultVal = 0.0)
        {
            if (el.TryGetProperty(propName, out var p) && p.ValueKind == JsonValueKind.Number)
            {
                return p.GetDouble();
            }
            return defaultVal;
        }

        private static int GetInt(JsonElement el, string propName, int defaultVal = 0)
        {
            if (el.TryGetProperty(propName, out var p) && p.ValueKind == JsonValueKind.Number)
            {
                return p.GetInt32();
            }
            return defaultVal;
        }

        private static bool GetBool(JsonElement el, string propName, bool defaultVal = false)
        {
            if (el.TryGetProperty(propName, out var p))
            {
                if (p.ValueKind == JsonValueKind.True) return true;
                if (p.ValueKind == JsonValueKind.False) return false;
            }
            return defaultVal;
        }

        private static string GetString(JsonElement el, string propName, string defaultVal = "")
        {
            if (el.TryGetProperty(propName, out var p) && p.ValueKind == JsonValueKind.String)
            {
                return p.GetString();
            }
            return defaultVal;
        }

        private static List<double> GetDoubleList(JsonElement el, string propName)
        {
            var list = new List<double>();
            if (el.TryGetProperty(propName, out var p) && p.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in p.EnumerateArray())
                {
                    if (item.ValueKind == JsonValueKind.Number)
                    {
                        list.Add(item.GetDouble());
                    }
                }
            }
            return list;
        }

        private static List<Vector3> ParseVector3List(JsonElement arrayEl)
        {
            var list = new List<Vector3>();
            if (arrayEl.ValueKind == JsonValueKind.Array)
            {
                foreach (var item in arrayEl.EnumerateArray())
                {
                    if (item.ValueKind == JsonValueKind.Array)
                    {
                        var coords = new List<float>();
                        foreach (var c in item.EnumerateArray())
                        {
                            coords.Add((float)c.GetDouble());
                        }
                        if (coords.Count >= 3)
                        {
                            list.Add(new Vector3(coords[0], coords[1], coords[2]));
                        }
                        else if (coords.Count == 2)
                        {
                            list.Add(new Vector3(coords[0], coords[1], 0f));
                        }
                    }
                }
            }
            return list;
        }

        #endregion

        #region Command Handlers

        private static string HandleSpringCoulomb(JsonElement root)
        {
            double k = GetDouble(root, "k", 1000.0);
            double cohesion = GetDouble(root, "cohesion", GetDouble(root, "fy_0", 0.0));
            double mu = GetDouble(root, "mu", GetDouble(root, "tan_phi", 0.0));
            double ur = GetDouble(root, "ur", 0.05);
            double ktang = GetDouble(root, "ktang", 0.0);
            double ktang2 = GetDouble(root, "ktang2", -1.0);
            double plasticStrainRatio = GetDouble(root, "plastic_strain_ratio", 0.0);
            string subLawStr = GetString(root, "sub_law", "Coulomb");
            string hystStr = GetString(root, "hysteretic_type", "Takeda");
            double normalForce = GetDouble(root, "normal_force", GetDouble(root, "n", GetDouble(root, "sigma", 0.0)));
            bool commitEach = GetBool(root, "commit_each_step", false);

            var subLaw = subLawStr.Equals("Cacovic", StringComparison.OrdinalIgnoreCase)
                ? ShearYieldingDomainEnum.Cacovic
                : ShearYieldingDomainEnum.Coulomb;

            var hystType = hystStr.Equals("Initial", StringComparison.OrdinalIgnoreCase)
                ? HystereticTypeEnum.Initial
                : HystereticTypeEnum.Takeda;

            var spring = new SpringCoulomb03(k, cohesion, mu, ur, ktang, ktang2, plasticStrainRatio, subLaw, hystType);
            if (normalForce != 0.0)
            {
                spring.TstressNormal = normalForce;
                spring.CstressNormal = normalForce;
            }

            var strains = GetDoubleList(root, "strains");
            if (strains.Count == 0 && root.TryGetProperty("strain", out var sSingle))
            {
                strains.Add(sSingle.GetDouble());
            }

            var forces = new List<double>();
            var forcesR = new List<string>();
            var forceBits = new List<long>();
            var tangents = new List<double>();
            var tangentsR = new List<string>();
            var tangentBits = new List<long>();
            var phases = new List<int>();
            var tphases = new List<int>();
            var codes = new List<int>();
            var displacements = new List<double>();

            foreach (double strain in strains)
            {
                int code = spring.setTrialStrain(strain);
                double f = spring.GetForce();
                double kt = spring.GetTangent();
                double u = spring.GetDisplacement();

                codes.Add(code);
                forces.Add(f);
                forcesR.Add(f.ToString("R", CultureInfo.InvariantCulture));
                forceBits.Add(BitConverter.DoubleToInt64Bits(f));

                tangents.Add(kt);
                tangentsR.Add(kt.ToString("R", CultureInfo.InvariantCulture));
                tangentBits.Add(BitConverter.DoubleToInt64Bits(kt));

                displacements.Add(u);
                phases.Add((int)spring.Phase);
                tphases.Add((int)spring.TPhase);

                if (commitEach)
                {
                    spring.Commit();
                }
            }

            var res = new Dictionary<string, object>
            {
                ["command"] = "spring-coulomb",
                ["forces"] = forces,
                ["forces_r"] = forcesR,
                ["force_bits"] = forceBits,
                ["tangents"] = tangents,
                ["tangents_r"] = tangentsR,
                ["tangent_bits"] = tangentBits,
                ["displacements"] = displacements,
                ["phases"] = phases,
                ["t_phases"] = tphases,
                ["codes"] = codes
            };

            return JsonSerializer.Serialize(res);
        }

        private static string HandleSpringMultiLinear(JsonElement root)
        {
            double k = GetDouble(root, "k", 1000.0);
            var fBackbone = GetDoubleList(root, "backbone_f");
            var uBackbone = GetDoubleList(root, "backbone_u");
            double ur = GetDouble(root, "ur", 0.05);
            double alfaR = GetDouble(root, "alfa_r", 0.1);
            double alfaU = GetDouble(root, "alfa_u", 0.1);
            bool commitEach = GetBool(root, "commit_each_step", false);

            if (fBackbone.Count == 0 || uBackbone.Count == 0)
            {
                fBackbone = new List<double> { 0.0, 10.0, 15.0, 5.0, 0.0 };
                uBackbone = new List<double> { 0.0, 0.01, 0.02, 0.03, 0.04 };
            }

            var spring = new SpringMultiLinearPlastic(k, fBackbone.ToArray(), uBackbone.ToArray(), ur, alfaR, alfaU);
            if (root.TryGetProperty("ur", out _))
            {
                spring.Ur = ur;
            }

            var strains = GetDoubleList(root, "strains");
            if (strains.Count == 0 && root.TryGetProperty("strain", out var sSingle))
            {
                strains.Add(sSingle.GetDouble());
            }

            var forces = new List<double>();
            var forcesR = new List<string>();
            var forceBits = new List<long>();
            var displacements = new List<double>();
            var tangents = new List<double>();
            var codes = new List<int>();

            foreach (double strain in strains)
            {
                int code = spring.setTrialStrain(strain);
                double f = spring.GetForce();
                double u = spring.GetDisplacement();
                double kt = spring.GetTangent();

                codes.Add(code);
                forces.Add(f);
                forcesR.Add(f.ToString("R", CultureInfo.InvariantCulture));
                forceBits.Add(BitConverter.DoubleToInt64Bits(f));
                displacements.Add(u);
                tangents.Add(kt);

                if (commitEach)
                {
                    spring.Commit();
                }
            }

            var res = new Dictionary<string, object>
            {
                ["command"] = "spring-multilinear",
                ["forces"] = forces,
                ["forces_r"] = forcesR,
                ["force_bits"] = forceBits,
                ["displacements"] = displacements,
                ["tangents"] = tangents,
                ["codes"] = codes
            };

            return JsonSerializer.Serialize(res);
        }

        private static string HandleSpringHysteretic(JsonElement root)
        {
            bool commitEach = GetBool(root, "commit_each_step", false);
            SpringHysteretic spring;

            if (root.TryGetProperty("m1p", out _))
            {
                double m1p = GetDouble(root, "m1p");
                double r1p = GetDouble(root, "r1p");
                double m2p = GetDouble(root, "m2p");
                double r2p = GetDouble(root, "r2p");
                double m3p = GetDouble(root, "m3p");
                double r3p = GetDouble(root, "r3p");
                double m1n = GetDouble(root, "m1n");
                double r1n = GetDouble(root, "r1n");
                double m2n = GetDouble(root, "m2n");
                double r2n = GetDouble(root, "r2n");
                double m3n = GetDouble(root, "m3n");
                double r3n = GetDouble(root, "r3n");
                double pinchXp = GetDouble(root, "pinchXp");
                double pinchYp = GetDouble(root, "pinchYp");
                double pinchXn = GetDouble(root, "pinchXn");
                double pinchYn = GetDouble(root, "pinchYn");
                double d1p = GetDouble(root, "d1p");
                double d2p = GetDouble(root, "d2p");
                double d1n = GetDouble(root, "d1n");
                double d2n = GetDouble(root, "d2n");
                double betap = GetDouble(root, "betap");
                double betan = GetDouble(root, "betan");

                spring = new SpringHysteretic(m1p, r1p, m2p, r2p, m3p, r3p, m1n, r1n, m2n, r2n, m3n, r3n,
                    pinchXp, pinchYp, pinchXn, pinchYn, d1p, d2p, d1n, d2n, betap, betan,
                    HystereticTensileCurveTypeEnum.LinearHardening, HystereticCompressiveCurveTypeEnum.LinearHardening);
            }
            else
            {
                double k = GetDouble(root, "k", 1000.0);
                double kt1 = GetDouble(root, "kt_1", 100.0);
                double kt2 = GetDouble(root, "kt_2", 50.0);
                double fy1 = GetDouble(root, "fy_1", 10.0);
                double fy2 = GetDouble(root, "fy_2", -10.0);
                double ur1 = GetDouble(root, "ur_1", 0.05);
                double ur2 = GetDouble(root, "ur_2", -0.05);
                double alfaR1 = GetDouble(root, "alfa_r_1", 0.1);
                double alfaR2 = GetDouble(root, "alfa_r_2", 0.1);
                double alfaU1 = GetDouble(root, "alfa_u_1", 0.1);
                double alfaU2 = GetDouble(root, "alfa_u_2", 0.1);

                spring = new SpringHysteretic(k, kt1, kt2, fy1, fy2, ur1, ur2, alfaR1, alfaR2, alfaU1, alfaU2);
            }

            var strains = GetDoubleList(root, "strains");
            if (strains.Count == 0 && root.TryGetProperty("strain", out var sSingle))
            {
                strains.Add(sSingle.GetDouble());
            }

            var forces = new List<double>();
            var forcesR = new List<string>();
            var forceBits = new List<long>();
            var displacements = new List<double>();
            var tangents = new List<double>();
            var codes = new List<int>();

            foreach (double strain in strains)
            {
                int code = spring.setTrialStrain(strain);
                double f = spring.GetForce();
                double u = spring.GetDisplacement();
                double kt = spring.GetTangent();

                codes.Add(code);
                forces.Add(f);
                forcesR.Add(f.ToString("R", CultureInfo.InvariantCulture));
                forceBits.Add(BitConverter.DoubleToInt64Bits(f));
                displacements.Add(u);
                tangents.Add(kt);

                if (commitEach)
                {
                    spring.Commit();
                }
            }

            var res = new Dictionary<string, object>
            {
                ["command"] = "spring-hysteretic",
                ["forces"] = forces,
                ["forces_r"] = forcesR,
                ["force_bits"] = forceBits,
                ["displacements"] = displacements,
                ["tangents"] = tangents,
                ["codes"] = codes
            };

            return JsonSerializer.Serialize(res);
        }

        private static string HandlePolygonClipping(JsonElement root)
        {
            var p1 = root.TryGetProperty("poly1", out var p1El) ? ParseVector3List(p1El) : new List<Vector3>();
            var p2 = root.TryGetProperty("poly2", out var p2El) ? ParseVector3List(p2El) : new List<Vector3>();
            bool includeExtreme = GetBool(root, "include_extreme_nodes", false);

            int code = Operations.FindIntersectionBetweenQuadrilaters(out List<Vector3> outNodes, p1, p2, includeExtreme);

            var vertices = new List<List<float>>();
            float area = 0f;
            if (outNodes != null)
            {
                foreach (var v in outNodes)
                {
                    vertices.Add(new List<float> { v.X, v.Y, v.Z });
                }
                if (outNodes.Count >= 3)
                {
                    area = Operations.Area(outNodes.ToArray(), true);
                }
            }

            double areaD = (double)area;
            var res = new Dictionary<string, object>
            {
                ["command"] = "polygon-clipping",
                ["code"] = code,
                ["count"] = outNodes?.Count ?? 0,
                ["vertices"] = vertices,
                ["area"] = areaD,
                ["area_r"] = areaD.ToString("R", CultureInfo.InvariantCulture),
                ["area_bits"] = BitConverter.DoubleToInt64Bits(areaD),
                ["area_single_bits"] = BitConverter.SingleToInt32Bits(area)
            };

            return JsonSerializer.Serialize(res);
        }

        private static string HandlePolygonArea(JsonElement root)
        {
            if (root.TryGetProperty("cases", out var casesEl) && casesEl.ValueKind == JsonValueKind.Array)
            {
                var caseResults = new List<Dictionary<string, object>>();
                foreach (var c in casesEl.EnumerateArray())
                {
                    var pts = ParseVector3List(c.GetProperty("points"));
                    float a = pts.Count >= 3 ? Operations.Area(pts.ToArray(), true) : 0f;
                    double aD = (double)a;
                    caseResults.Add(new Dictionary<string, object>
                    {
                        ["area"] = aD,
                        ["area_r"] = aD.ToString("R", CultureInfo.InvariantCulture),
                        ["area_bits"] = BitConverter.DoubleToInt64Bits(aD),
                        ["area_single_bits"] = BitConverter.SingleToInt32Bits(a)
                    });
                }
                return JsonSerializer.Serialize(new Dictionary<string, object>
                {
                    ["command"] = "polygon-area",
                    ["cases"] = caseResults
                });
            }

            var points = ParseVector3List(root.GetProperty("points"));
            float area = points.Count >= 3 ? Operations.Area(points.ToArray(), true) : 0f;
            double areaDouble = (double)area;

            var res = new Dictionary<string, object>
            {
                ["command"] = "polygon-area",
                ["area"] = areaDouble,
                ["area_r"] = areaDouble.ToString("R", CultureInfo.InvariantCulture),
                ["area_bits"] = BitConverter.DoubleToInt64Bits(areaDouble),
                ["area_single_bits"] = BitConverter.SingleToInt32Bits(area)
            };

            return JsonSerializer.Serialize(res);
        }

        private static string HandleGaussQuadrature(JsonElement root)
        {
            int order = GetInt(root, "order", GetInt(root, "n", 2));
            var g = new QuadraturaGaussiana(order);

            var zList = new List<double>();
            var zRList = new List<string>();
            var zBitsList = new List<long>();

            var wList = new List<double>();
            var wRList = new List<string>();
            var wBitsList = new List<long>();

            for (int i = 0; i < g.N; i++)
            {
                double zi = g.z[i];
                zList.Add(zi);
                zRList.Add(zi.ToString("R", CultureInfo.InvariantCulture));
                zBitsList.Add(BitConverter.DoubleToInt64Bits(zi));

                double wi = g.w[i];
                wList.Add(wi);
                wRList.Add(wi.ToString("R", CultureInfo.InvariantCulture));
                wBitsList.Add(BitConverter.DoubleToInt64Bits(wi));
            }

            var res = new Dictionary<string, object>
            {
                ["command"] = "gauss-quadrature",
                ["order"] = g.N,
                ["z"] = zList,
                ["z_r"] = zRList,
                ["z_bits"] = zBitsList,
                ["w"] = wList,
                ["w_r"] = wRList,
                ["w_bits"] = wBitsList
            };

            return JsonSerializer.Serialize(res);
        }

        private static string HandleArcLength(JsonElement root)
        {
            if (root.TryGetProperty("cases", out var casesEl) && casesEl.ValueKind == JsonValueKind.Array)
            {
                var caseResults = new List<Dictionary<string, object>>();
                foreach (var c in casesEl.EnumerateArray())
                {
                    caseResults.Add(ExecuteSingleArcLength(c));
                }
                return JsonSerializer.Serialize(new Dictionary<string, object>
                {
                    ["command"] = "arc-length",
                    ["cases"] = caseResults
                });
            }

            return JsonSerializer.Serialize(ExecuteSingleArcLength(root));
        }

        private static Dictionary<string, object> ExecuteSingleArcLength(JsonElement el)
        {
            double alpha2 = GetDouble(el, "alpha2", 0.0);
            var hatList = GetDoubleList(el, "hat");
            if (hatList.Count == 0 && el.TryGetProperty("hat", out var hVal)) hatList.Add(hVal.GetDouble());
            if (hatList.Count == 0 && el.TryGetProperty("phat", out var phVal))
            {
                if (phVal.ValueKind == JsonValueKind.Array) hatList = GetDoubleList(el, "phat");
                else hatList.Add(phVal.GetDouble());
            }

            var barList = GetDoubleList(el, "bar");
            if (barList.Count == 0 && el.TryGetProperty("bar", out var bVal)) barList.Add(bVal.GetDouble());
            if (barList.Count == 0 && el.TryGetProperty("deltau_bar", out var dbarVal))
            {
                if (dbarVal.ValueKind == JsonValueKind.Array) barList = GetDoubleList(el, "deltau_bar");
                else barList.Add(dbarVal.GetDouble());
            }

            var stepList = GetDoubleList(el, "step");
            if (stepList.Count == 0 && el.TryGetProperty("step", out var stVal)) stepList.Add(stVal.GetDouble());
            if (stepList.Count == 0 && el.TryGetProperty("deltau_step", out var dstepVal))
            {
                if (dstepVal.ValueKind == JsonValueKind.Array) stepList = GetDoubleList(el, "deltau_step");
                else stepList.Add(dstepVal.GetDouble());
            }

            int sz = Math.Max(1, Math.Max(hatList.Count, Math.Max(barList.Count, stepList.Count)));
            while (hatList.Count < sz) hatList.Add(0.0);
            while (barList.Count < sz) barList.Add(0.0);
            while (stepList.Count < sz) stepList.Add(0.0);

            double deltaLambdaStep = GetDouble(el, "delta_lambda_step", 0.0);

            var arc = new ArcLength();
            var prog = new ModelLibrary.Program();
            prog.LS.SetB(new Vector(hatList.ToArray()));
            prog.LS.SetX(new Vector(barList.ToArray()));

            var t = typeof(ArcLength);
            const BindingFlags flags = BindingFlags.NonPublic | BindingFlags.Instance;

            t.GetField("alpha2", flags)?.SetValue(arc, alpha2);
            t.GetField("phat", flags)?.SetValue(arc, new Vector(hatList.ToArray()));
            t.GetField("deltaUbar", flags)?.SetValue(arc, new Vector(barList.ToArray()));
            t.GetField("deltaUstep", flags)?.SetValue(arc, new Vector(stepList.ToArray()));
            t.GetField("deltaU", flags)?.SetValue(arc, new Vector(sz));
            t.GetField("deltaUhat", flags)?.SetValue(arc, new Vector(sz));
            t.GetField("deltaLambdaStep", flags)?.SetValue(arc, deltaLambdaStep);
            t.GetField("dofs", flags)?.SetValue(arc, new int[] { -1 });

            int code = arc.Update(new Collections(), prog, new Analysis());

            double newDeltaLambdaStep = (double)(t.GetField("deltaLambdaStep", flags)?.GetValue(arc) ?? 0.0);
            double deltaLambda = newDeltaLambdaStep - deltaLambdaStep;

            var duVector = (Vector)t.GetField("deltaU", flags)?.GetValue(arc);
            var duList = new List<double>();
            var duRList = new List<string>();

            if (duVector != null)
            {
                for (int i = 0; i < duVector.sz; i++)
                {
                    double val = duVector.Get(i);
                    duList.Add(val);
                    duRList.Add(val.ToString("R", CultureInfo.InvariantCulture));
                }
            }

            long lambdaBits = (code < 0) ? 0 : BitConverter.DoubleToInt64Bits(deltaLambda);
            long duBits = (code < 0 || duList.Count == 0) ? 0 : BitConverter.DoubleToInt64Bits(duList[0]);

            return new Dictionary<string, object>
            {
                ["code"] = code,
                ["delta_lambda"] = deltaLambda,
                ["delta_lambda_r"] = deltaLambda.ToString("R", CultureInfo.InvariantCulture),
                ["lambda_bits"] = lambdaBits,
                ["delta_u"] = duList,
                ["delta_u_r"] = duRList,
                ["du_bits"] = duBits
            };
        }

        private static string HandleConvergenceCriteria(JsonElement root)
        {
            string type = GetString(root, "type", "unbalance");
            double tol = GetDouble(root, "tol", 1e-4);
            int maxIter = GetInt(root, "max_iter", 25);
            double maxU = GetDouble(root, "max_u", 1000.0);
            int normType = GetInt(root, "norm_type", 2);
            bool absoluteApproach = GetBool(root, "absolute_approach", true);

            var residual = GetDoubleList(root, "residual");
            var disp = GetDoubleList(root, "displacement");

            var ls = new LinearSystem();
            if (residual.Count > 0) ls.SetB(new Vector(residual.ToArray()));
            if (disp.Count > 0) ls.SetX(new Vector(disp.ToArray()));

            var prog = new ModelLibrary.Program { LS = ls };

            ConvergenceTest ct;
            if (type.Equals("displacement", StringComparison.OrdinalIgnoreCase) ||
                type.Equals("disprotation", StringComparison.OrdinalIgnoreCase))
            {
                ct = new CTestNormDispIncr(tol, maxIter, maxU, normType);
            }
            else if (type.Equals("energy", StringComparison.OrdinalIgnoreCase) ||
                     type.Equals("work", StringComparison.OrdinalIgnoreCase))
            {
                ct = new CTestEnergyIncr(tol, maxIter, maxU);
            }
            else
            {
                ct = new CTestNormUnbalance(tol, maxIter, maxU, normType, absoluteApproach);
            }

            ct.start();
            int code = ct.test(prog, new Collections(), ls);
            double error = ct.getError();
            double toll = ct.getToll();

            var res = new Dictionary<string, object>
            {
                ["command"] = "convergence-criteria",
                ["type"] = type,
                ["code"] = code,
                ["error"] = error,
                ["error_r"] = error.ToString("R", CultureInfo.InvariantCulture),
                ["error_bits"] = BitConverter.DoubleToInt64Bits(error),
                ["tol"] = toll,
                ["converged"] = (code >= 0),
                ["num_tests"] = ct.getNumTests()
            };

            return JsonSerializer.Serialize(res);
        }

        #endregion
    }
}
