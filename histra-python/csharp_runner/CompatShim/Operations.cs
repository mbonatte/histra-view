using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Numerics;
using System.Text;
using EventLoggerAndDebug;
using Microsoft.Xna.Framework;
using UtilityLibrary.Tipi;

namespace UtilityLibrary.Matematics
{
	// Token: 0x0200001B RID: 27
	public static class Operations
	{
		// Token: 0x1700003C RID: 60
		// (get) Token: 0x06000129 RID: 297 RVA: 0x0000E0EE File Offset: 0x0000C2EE
		// (set) Token: 0x0600012A RID: 298 RVA: 0x0000E0F5 File Offset: 0x0000C2F5
		public static float ToleranceNode
		{
			get
			{
				return DefaultValues.ToleranceNode;
			}
			set
			{
				DefaultValues.ToleranceNode = value;
			}
		}

		// Token: 0x0600012B RID: 299 RVA: 0x0000E100 File Offset: 0x0000C300
		public static string ArrayToString(double[] array)
		{
			StringBuilder stringBuilder = new StringBuilder();
			for (int i = 0; i < array.Length; i++)
			{
				stringBuilder.AppendLine(array[i].ToString());
			}
			return stringBuilder.ToString();
		}

		// Token: 0x0600012C RID: 300 RVA: 0x0000E13A File Offset: 0x0000C33A
		public static bool IsValid(float val)
		{
			return !float.IsNaN(val) && !float.IsInfinity(val);
		}

		// Token: 0x0600012D RID: 301 RVA: 0x0000E14F File Offset: 0x0000C34F
		public static bool IsValid(double val)
		{
			return !double.IsNaN(val) && !double.IsInfinity(val);
		}

		// Token: 0x0600012E RID: 302 RVA: 0x0000E164 File Offset: 0x0000C364
		public static bool TryParseFloat(string txt, out float val)
		{
			bool flag = false;
			bool flag2 = false;
			if (txt.Contains("%"))
			{
				flag = true;
				txt = txt.Replace("%", "");
			}
			if (txt.Contains("‰"))
			{
				flag2 = true;
				txt = txt.Replace("‰", "");
			}
			txt = txt.Replace(',', '.');
			bool flag3 = float.TryParse(txt, NumberStyles.Any, CultureInfo.InvariantCulture, out val);
			if (flag && !flag2)
			{
				val /= 100f;
			}
			if (!flag && flag2)
			{
				val /= 1000f;
			}
			return flag3;
		}

		// Token: 0x0600012F RID: 303 RVA: 0x0000E1F8 File Offset: 0x0000C3F8
		public static bool TryParseDouble(string txt, out double val)
		{
			bool flag = false;
			bool flag2 = false;
			if (txt.Contains("%"))
			{
				flag = true;
				txt = txt.Replace("%", "");
			}
			if (txt.Contains("‰"))
			{
				flag2 = true;
				txt = txt.Replace("‰", "");
			}
			txt = txt.Replace(',', '.');
			bool flag3 = double.TryParse(txt, NumberStyles.Any, CultureInfo.InvariantCulture, out val);
			if (flag && !flag2)
			{
				val /= 100.0;
			}
			if (!flag && flag2)
			{
				val /= 1000.0;
			}
			return flag3;
		}

		// Token: 0x06000130 RID: 304 RVA: 0x0000E292 File Offset: 0x0000C492
		public static bool HasDecimal(float val)
		{
			return val == 0f || val % 1f != 0f;
		}

		// Token: 0x06000131 RID: 305 RVA: 0x0000E2AF File Offset: 0x0000C4AF
		public static bool HasDecimal(double val)
		{
			return val == 0.0 || val % 1.0 != 0.0;
		}

		// Token: 0x06000132 RID: 306 RVA: 0x0000E2D8 File Offset: 0x0000C4D8
		public static string ArrotondaNumero(float val, int MaxDecimal, string format = "F")
		{
			string text;
			if (MaxDecimal >= 0)
			{
				val = (float)Math.Round((double)val, MaxDecimal);
				if (val != 0f && Operations.HasDecimal(val) && Convert.ToInt32(((double)val - Math.Truncate((double)val)).ToString(string.Format("{0}{1}", format, MaxDecimal)).Replace(",", "").Replace(".", "")) == 0)
				{
					text = val.ToString("e" + MaxDecimal.ToString());
				}
				else
				{
					text = val.ToString(format + MaxDecimal.ToString());
				}
			}
			else if (Operations.HasDecimal(val))
			{
				text = val.ToString(format);
			}
			else
			{
				text = val.ToString("F0");
			}
			return text;
		}

		// Token: 0x06000133 RID: 307 RVA: 0x0000E3A4 File Offset: 0x0000C5A4
		public static string ArrotondaNumero(double val, int MaxDecimal, string format = "F")
		{
			if (double.IsNaN(val))
			{
				return "NaN";
			}
			if (double.IsInfinity(val))
			{
				return "Infinity";
			}
			string text;
			if (MaxDecimal >= 0)
			{
				val = Math.Round(val, MaxDecimal);
				if (val != 0.0 && Operations.HasDecimal(val) && Convert.ToInt32((val - Math.Truncate(val)).ToString(string.Format("{0}{1}", format, MaxDecimal)).Replace(",", "").Replace(".", "")) == 0)
				{
					text = val.ToString("e" + MaxDecimal.ToString());
				}
				else
				{
					text = val.ToString(format + MaxDecimal.ToString());
				}
			}
			else if (Operations.HasDecimal(val))
			{
				text = val.ToString(format);
			}
			else
			{
				text = val.ToString("F0");
			}
			return text;
		}

		// Token: 0x06000134 RID: 308 RVA: 0x0000E48C File Offset: 0x0000C68C
		public static double[] GenerateCycles(int NumCycle, int NumStepsPerSegment, double w0, double wf)
		{
			double[] array = new double[4 * NumCycle * NumStepsPerSegment + 1];
			double num = 0.0;
			double num2 = 0.0;
			double num3 = (wf - w0) / (double)(NumCycle - 1);
			double num4 = w0;
			for (int i = 0; i < NumCycle; i++)
			{
				for (int j = 0; j < 4; j++)
				{
					switch (j)
					{
					case 0:
						num = 0.0;
						num2 = num4;
						break;
					case 1:
						num = num4;
						num2 = 0.0;
						break;
					case 2:
						num = 0.0;
						num2 = -num4;
						break;
					case 3:
						num = -num4;
						num2 = 0.0;
						break;
					}
					for (int k = 0; k < NumStepsPerSegment; k++)
					{
						array[4 * i * NumStepsPerSegment + j * NumStepsPerSegment + k] = num + (double)k * (num2 - num) / (double)NumStepsPerSegment;
					}
				}
				num4 += num3;
			}
			return array;
		}

		// Token: 0x06000135 RID: 309 RVA: 0x0000E57C File Offset: 0x0000C77C
		public static double[] GenerateLinear(int NumCycle, int NumStepsPerSegment, double w0, double wf)
		{
			double[] array = new double[4 * NumCycle * NumStepsPerSegment + 1];
			double num = (wf - w0) / (double)(NumCycle - 1);
			for (int i = 0; i < NumCycle; i++)
			{
				for (int j = 0; j < 4; j++)
				{
					for (int k = 0; k < NumStepsPerSegment; k++)
					{
						array[4 * i * NumStepsPerSegment + j * NumStepsPerSegment + k] = w0 + (wf - w0) * (double)(4 * i * NumStepsPerSegment + j * NumStepsPerSegment + k) / (double)(4 * NumCycle * NumStepsPerSegment + 1);
					}
				}
			}
			array[4 * NumCycle * NumStepsPerSegment] = wf;
			return array;
		}

		// Token: 0x06000136 RID: 310 RVA: 0x0000E604 File Offset: 0x0000C804
		public static float Cos(float X, int precision = 6)
		{
			if (precision < 0)
			{
				return (float)Math.Cos((double)X);
			}
			return (float)Math.Round(Math.Cos((double)X), precision);
		}

		// Token: 0x06000137 RID: 311 RVA: 0x0000E621 File Offset: 0x0000C821
		public static float Cosd(float X, int precision = 6)
		{
			if (precision < 0)
			{
				return (float)Math.Cos((double)(X * 0.017453292f));
			}
			return (float)Math.Round(Math.Cos((double)(X * 0.017453292f)), precision);
		}

		// Token: 0x06000138 RID: 312 RVA: 0x0000E64A File Offset: 0x0000C84A
		public static float Acos(float X, int precision = 6)
		{
			if (precision < 0)
			{
				return (float)Math.Acos((double)X);
			}
			return (float)Math.Round(Math.Acos((double)X), precision);
		}

		// Token: 0x06000139 RID: 313 RVA: 0x0000E667 File Offset: 0x0000C867
		public static float Sin(float X, int precision = 6)
		{
			if (precision < 0)
			{
				return (float)Math.Sin((double)X);
			}
			return (float)Math.Round(Math.Sin((double)X), 6);
		}

		// Token: 0x0600013A RID: 314 RVA: 0x0000E684 File Offset: 0x0000C884
		public static float Sind(float X, int precision = 6)
		{
			if (precision < 0)
			{
				return (float)Math.Sin((double)(X * 0.017453292f));
			}
			return (float)Math.Round(Math.Sin((double)(X * 0.017453292f)), 6);
		}

		// Token: 0x0600013B RID: 315 RVA: 0x0000E6AD File Offset: 0x0000C8AD
		public static float Asin(float X, int precision = 6)
		{
			if (precision < 0)
			{
				return (float)Math.Asin(Convert.ToDouble(X));
			}
			return (float)Math.Round(Math.Asin(Convert.ToDouble(X)), 6);
		}

		// Token: 0x0600013C RID: 316 RVA: 0x0000E6D2 File Offset: 0x0000C8D2
		public static float Asind(float X, int precision = 6)
		{
			if (precision < 0)
			{
				return (float)Math.Asin((double)X);
			}
			return (float)Math.Round(Math.Asin((double)X) * 57.2957763671875, 6);
		}

		// Token: 0x0600013D RID: 317 RVA: 0x0000E6F9 File Offset: 0x0000C8F9
		public static float Acosd(float X, int precision = 6)
		{
			if (precision < 0)
			{
				return (float)Math.Acos((double)X) * 57.295776f;
			}
			return (float)Math.Round(Math.Acos((double)X) * 57.2957763671875, 6);
		}

		// Token: 0x0600013E RID: 318 RVA: 0x0000E728 File Offset: 0x0000C928
		public static Microsoft.Xna.Framework.Vector3 ComputeG(Microsoft.Xna.Framework.Vector3[] points)
		{
			Microsoft.Xna.Framework.Vector2[] array = new Microsoft.Xna.Framework.Vector2[points.Length];
			Microsoft.Xna.Framework.Vector3 vector = Microsoft.Xna.Framework.Vector3.Normalize(points[1] - points[0]);
			Microsoft.Xna.Framework.Vector3 vector2 = Microsoft.Xna.Framework.Vector3.Normalize(points[2] - points[0]);
			Microsoft.Xna.Framework.Vector3 vector3 = Microsoft.Xna.Framework.Vector3.Normalize(Microsoft.Xna.Framework.Vector3.Cross(vector, vector2));
			vector2 = Microsoft.Xna.Framework.Vector3.Cross(vector3, vector);
			Matrix rotationMatrix = Operations.GetRotationMatrix(vector, vector2, vector3, true);
			int i;
			for (i = 0; i < points.Length; i++)
			{
				array[i] = Operations.MatrixPerVector3_2d(rotationMatrix, points[i] - points[0]);
			}
			Microsoft.Xna.Framework.Vector3 vector4 = default(Microsoft.Xna.Framework.Vector3);
			Microsoft.Xna.Framework.Vector2 vector5 = default(Microsoft.Xna.Framework.Vector2);
			float num = 0f;
			float num2;
			float num3;
			float num4;
			float num5;
			float num6;
			for (i = 0; i < array.Length - 1; i++)
			{
				num2 = array[i].X;
				num3 = array[i].Y;
				num4 = array[i + 1].X;
				num5 = array[i + 1].Y;
				num6 = num2 * num5 - num4 * num3;
				num += num6;
				vector5.X += (num2 + num4) * num6;
				vector5.Y += (num3 + num5) * num6;
			}
			num2 = array[i].X;
			num3 = array[i].Y;
			num4 = array[0].X;
			num5 = array[0].Y;
			num6 = num2 * num5 - num4 * num3;
			num += num6;
			vector5.X += (num2 + num4) * num6;
			vector5.Y += (num3 + num5) * num6;
			num *= 0.5f;
			vector5.X /= 6f * num;
			vector5.Y /= 6f * num;
			Operations.ConvertVector2ToVector3(points[0], points[1], points[2], vector5, out vector4);
			return vector4;
		}

		// Token: 0x0600013F RID: 319 RVA: 0x0000E940 File Offset: 0x0000CB40
		public static Microsoft.Xna.Framework.Vector3 Vector3PerMatrix(Microsoft.Xna.Framework.Vector3 V, Matrix M)
		{
			return new Microsoft.Xna.Framework.Vector3
			{
				X = V.X * M.M11 + V.Y * M.M21 + V.Z * M.M31 + M.M41,
				Y = V.X * M.M12 + V.Y * M.M22 + V.Z * M.M32 + M.M42,
				Z = V.X * M.M13 + V.Y * M.M23 + V.Z * M.M33 + M.M43
			};
		}

		// Token: 0x06000140 RID: 320 RVA: 0x0000E9FC File Offset: 0x0000CBFC
		public static void SetZeroMatrix(ref Matrix M)
		{
			M.M11 = 0f;
			M.M12 = 0f;
			M.M13 = 0f;
			M.M14 = 0f;
			M.M21 = 0f;
			M.M22 = 0f;
			M.M23 = 0f;
			M.M24 = 0f;
			M.M31 = 0f;
			M.M32 = 0f;
			M.M33 = 0f;
			M.M34 = 0f;
			M.M41 = 0f;
			M.M42 = 0f;
			M.M43 = 0f;
			M.M44 = 0f;
		}

		// Token: 0x06000141 RID: 321 RVA: 0x0000EABC File Offset: 0x0000CCBC
		public static void SetZeroMatrix3D(ref Matrix M)
		{
			M.M11 = 0f;
			M.M12 = 0f;
			M.M13 = 0f;
			M.M14 = 0f;
			M.M21 = 0f;
			M.M22 = 0f;
			M.M23 = 0f;
			M.M24 = 0f;
			M.M31 = 0f;
			M.M32 = 0f;
			M.M33 = 0f;
			M.M34 = 0f;
			M.M41 = 0f;
			M.M42 = 0f;
			M.M43 = 0f;
			M.M44 = 1f;
		}

		// Token: 0x06000142 RID: 322 RVA: 0x0000EB7C File Offset: 0x0000CD7C
		public static Microsoft.Xna.Framework.Vector3 MatrixPerVector3(Matrix M, Microsoft.Xna.Framework.Vector3 V)
		{
			return new Microsoft.Xna.Framework.Vector3
			{
				X = V.X * M.M11 + V.Y * M.M12 + V.Z * M.M13 + M.M14,
				Y = V.X * M.M21 + V.Y * M.M22 + V.Z * M.M23 + M.M24,
				Z = V.X * M.M31 + V.Y * M.M32 + V.Z * M.M33 + M.M34
			};
		}

		// Token: 0x06000143 RID: 323 RVA: 0x0000EC38 File Offset: 0x0000CE38
		public static Microsoft.Xna.Framework.Vector2 MatrixPerVector3_2d(Matrix M, Microsoft.Xna.Framework.Vector3 V)
		{
			return new Microsoft.Xna.Framework.Vector2
			{
				X = V.X * M.M11 + V.Y * M.M12 + V.Z * M.M13 + M.M14,
				Y = V.X * M.M21 + V.Y * M.M22 + V.Z * M.M23 + M.M24
			};
		}

		// Token: 0x06000144 RID: 324 RVA: 0x0000ECBC File Offset: 0x0000CEBC
		public static Matrix GetRotationMatrixFrom3Points(Microsoft.Xna.Framework.Vector3 v1, Microsoft.Xna.Framework.Vector3 v2, Microsoft.Xna.Framework.Vector3 v3)
		{
			Microsoft.Xna.Framework.Vector3 vector = Microsoft.Xna.Framework.Vector3.Normalize(v2 - v1);
			Microsoft.Xna.Framework.Vector3 vector2 = Microsoft.Xna.Framework.Vector3.Normalize(Microsoft.Xna.Framework.Vector3.Cross(vector, v3 - v1));
			Microsoft.Xna.Framework.Vector3 vector3 = Microsoft.Xna.Framework.Vector3.Cross(vector2, vector);
			return new Matrix
			{
				M11 = vector.X,
				M21 = vector3.X,
				M31 = vector2.X,
				M12 = vector.Y,
				M22 = vector3.Y,
				M32 = vector2.Y,
				M13 = vector.Z,
				M23 = vector3.Z,
				M33 = vector2.Z,
				M44 = 1f
			};
		}

		// Token: 0x06000145 RID: 325 RVA: 0x0000ED7C File Offset: 0x0000CF7C
		public static Matrix GetRotationMatrix(Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, bool transpose = false)
		{
			Matrix matrix = default(Matrix);
			if (transpose)
			{
				matrix.M11 = e1.X;
				matrix.M12 = e1.Y;
				matrix.M13 = e1.Z;
				matrix.M21 = e2.X;
				matrix.M22 = e2.Y;
				matrix.M23 = e2.Z;
				matrix.M31 = e3.X;
				matrix.M32 = e3.Y;
				matrix.M33 = e3.Z;
				matrix.M44 = 1f;
			}
			else
			{
				matrix.M11 = e1.X;
				matrix.M12 = e2.X;
				matrix.M13 = e3.X;
				matrix.M21 = e1.Y;
				matrix.M22 = e2.Y;
				matrix.M23 = e3.Y;
				matrix.M31 = e1.Z;
				matrix.M32 = e2.Z;
				matrix.M33 = e3.Z;
				matrix.M44 = 1f;
			}
			return matrix;
		}

		// Token: 0x06000146 RID: 326 RVA: 0x0000EEA0 File Offset: 0x0000D0A0
		public static Matrix GetRotoTranslationMatrix(Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, Microsoft.Xna.Framework.Vector3 Origin)
		{
			Matrix matrix = default(Matrix);
			matrix = Operations.GetRotationMatrix(e1, e2, e3, false);
			matrix.M14 = Origin.X;
			matrix.M24 = Origin.Y;
			matrix.M34 = Origin.Z;
			return matrix;
		}

		// Token: 0x06000147 RID: 327 RVA: 0x0000EEE8 File Offset: 0x0000D0E8
		public static double DistanceBetween(Microsoft.Xna.Framework.Vector3 A, Microsoft.Xna.Framework.Vector3 B)
		{
			return (double)(A - B).Length();
		}

		// Token: 0x06000148 RID: 328 RVA: 0x0000EF05 File Offset: 0x0000D105
		public static float DistanceBetween(float x1, float y1, float x2, float y2)
		{
			return Operations.sqrt(Operations.sq(x1 - x2) + Operations.sq(y1 - y2));
		}

		// Token: 0x06000149 RID: 329 RVA: 0x0000EF20 File Offset: 0x0000D120
		public static int CheckIfPointsAreDistinct(List<Microsoft.Xna.Framework.Vector3> points, float toll, out List<int> chiaviDeiPuntiDistinti)
		{
			int num = 0;
			chiaviDeiPuntiDistinti = new List<int>();
			for (int i = 0; i < points.Count; i++)
			{
				chiaviDeiPuntiDistinti.Add(i);
			}
			for (int j = 0; j < points.Count; j++)
			{
				for (int k = 0; k < points.Count; k++)
				{
					if (j != k && (points[j] - points[k]).Length() < toll && chiaviDeiPuntiDistinti.Contains(j) && chiaviDeiPuntiDistinti.Contains(k))
					{
						chiaviDeiPuntiDistinti.Remove(j);
						num++;
					}
				}
			}
			return points.Count - chiaviDeiPuntiDistinti.Count;
		}

		// Token: 0x0600014A RID: 330 RVA: 0x0000EFC8 File Offset: 0x0000D1C8
		public static bool FindIntersectionTwoCircles(float x1, float y1, float R1, float x2, float y2, float R2, out float Xa, out float Ya, out float Xb, out float Yb)
		{
			bool flag = false;
			Xa = (Ya = (Xb = (Yb = 0f)));
			try
			{
				if (Math.Abs(x1 - x2) < Operations.ToleranceNode)
				{
					Xb = x1;
					Xa = x1;
					Ya = -(Operations.sqrt(-Operations.sq(Operations.sq(R1)) + 2f * Operations.sq(R1) * (Operations.sq(R2) + Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) - Operations.sq(Operations.sq(R2)) + (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (2f * Operations.sq(R2) - Operations.sq(x1) + 2f * x1 * x2 - Operations.sq(x2) - Operations.sq(y1) + y2 * (2f * y1 - y2))) * Math.Abs(x1 - x2) + Operations.sq(R1) * (y1 - y2) + Operations.sq(R2) * (y2 - y1) - (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (y1 + y2)) / (2f * (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)));
					Yb = (Operations.sqrt(-Operations.sq(Operations.sq(R1)) + 2f * Operations.sq(R1) * (Operations.sq(R2) + Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) - Operations.sq(Operations.sq(R2)) + (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (2f * Operations.sq(R2) - Operations.sq(x1) + 2f * x1 * x2 - Operations.sq(x2) - Operations.sq(y1) + y2 * (2f * y1 - y2))) * Math.Abs(x1 - x2) + Operations.sq(R1) * (y2 - y1) + Operations.sq(R2) * (y1 - y2) + (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (y1 + y2)) / (2f * (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)));
				}
				else
				{
					Xa = -((y1 - y2) * Operations.sqrt(-Operations.sq(Operations.sq(R1)) + 2f * Operations.sq(R1) * (Operations.sq(R2) + Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) - Operations.sq(Operations.sq(R2)) + (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (2f * Operations.sq(R2) - Operations.sq(x1) + 2f * x1 * x2 - Operations.sq(x2) - Operations.sq(y1) + y2 * (2f * y1 - y2))) * (float)Math.Sign(x1 - x2) + Operations.sq(R1) * (x1 - x2) + Operations.sq(R2) * (x2 - x1) - (x1 + x2) * (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2))) / (2f * (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)));
					Ya = (Operations.sqrt(-Operations.sq(Operations.sq(R1)) + 2f * Operations.sq(R1) * (Operations.sq(R2) + Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) - Operations.sq(Operations.sq(R2)) + (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (2f * Operations.sq(R2) - Operations.sq(x1) + 2f * x1 * x2 - Operations.sq(x2) - Operations.sq(y1) + y2 * (2f * y1 - y2))) * Math.Abs(x1 - x2) + Operations.sq(R1) * (y2 - y1) + Operations.sq(R2) * (y1 - y2) + (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (y1 + y2)) / (2f * (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)));
					Xb = ((y1 - y2) * Operations.sqrt(-Operations.sq(Operations.sq(R1)) + 2f * Operations.sq(R1) * (Operations.sq(R2) + Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) - Operations.sq(Operations.sq(R2)) + (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (2f * Operations.sq(R2) - Operations.sq(x1) + 2f * x1 * x2 - Operations.sq(x2) - Operations.sq(y1) + y2 * (2f * y1 - y2))) * (float)Math.Sign(x1 - x2) + Operations.sq(R1) * (x2 - x1) + Operations.sq(R2) * (x1 - x2) + (x1 + x2) * (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2))) / (2f * (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)));
					Yb = -(Operations.sqrt(-Operations.sq(Operations.sq(R1)) + 2f * Operations.sq(R1) * (Operations.sq(R2) + Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) - Operations.sq(Operations.sq(R2)) + (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (2f * Operations.sq(R2) - Operations.sq(x1) + 2f * x1 * x2 - Operations.sq(x2) - Operations.sq(y1) + y2 * (2f * y1 - y2))) * Math.Abs(x1 - x2) + Operations.sq(R1) * (y1 - y2) + Operations.sq(R2) * (y2 - y1) - (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)) * (y1 + y2)) / (2f * (Operations.sq(x1) - 2f * x1 * x2 + Operations.sq(x2) + Operations.sq(y1) - 2f * y1 * y2 + Operations.sq(y2)));
				}
				flag = true;
			}
			catch (Exception ex)
			{
				Logger.Log(ex.Message + "Stack: " + ex.StackTrace, DebugLevel.CRITICAL);
				flag = false;
			}
			return flag;
		}

		// Token: 0x0600014B RID: 331 RVA: 0x0000F8C4 File Offset: 0x0000DAC4
		public static Microsoft.Xna.Framework.Vector3 FindIntersectWithPlane(Microsoft.Xna.Framework.Vector4 Phi, Microsoft.Xna.Framework.Vector3 Far, Microsoft.Xna.Framework.Vector3 Near)
		{
			Ray ray = new Ray(Near, Microsoft.Xna.Framework.Vector3.Subtract(Far, Near));
			Microsoft.Xna.Framework.Vector3 vector;
			Operations.FindIntersectionRayAndPlane(Phi, ray, out vector);
			return vector;
		}

		// Token: 0x0600014C RID: 332 RVA: 0x0000F8EC File Offset: 0x0000DAEC
		public static bool IsIntersectWithPlane(Microsoft.Xna.Framework.Vector4 Phi, Microsoft.Xna.Framework.Vector3 Far, Microsoft.Xna.Framework.Vector3 Near)
		{
			Ray ray = new Ray(Near, Microsoft.Xna.Framework.Vector3.Subtract(Far, Near));
			Microsoft.Xna.Framework.Vector3 vector;
			return Operations.FindIntersectionRayAndPlane(Phi, ray, out vector);
		}

		// Token: 0x0600014D RID: 333 RVA: 0x0000F914 File Offset: 0x0000DB14
		public static Microsoft.Xna.Framework.Vector3 ProjectVector3ToPlane(Microsoft.Xna.Framework.Vector4 Phi, Microsoft.Xna.Framework.Vector3 p)
		{
			Ray ray = new Ray(p, new Microsoft.Xna.Framework.Vector3(Phi.X, Phi.Y, Phi.Z));
			Microsoft.Xna.Framework.Vector3 vector;
			Operations.FindIntersectionRayAndPlane(Phi, ray, out vector);
			return vector;
		}

		// Token: 0x0600014E RID: 334 RVA: 0x0000F94C File Offset: 0x0000DB4C
		public static bool IsNear(Microsoft.Xna.Framework.Vector3 p1, Microsoft.Xna.Framework.Vector3 p2, Microsoft.Xna.Framework.Vector3 p, out Microsoft.Xna.Framework.Vector3 near, float toll = 0.5f)
		{
			bool flag = false;
			near = Microsoft.Xna.Framework.Vector3.Zero;
			Microsoft.Xna.Framework.Vector3 vector = p2 - p1;
			Microsoft.Xna.Framework.Vector3 vector2 = vector;
			Microsoft.Xna.Framework.Vector3 vector3 = p - p1;
			vector2.Normalize();
			float num = Microsoft.Xna.Framework.Vector3.Dot(vector3, vector2);
			if (num >= 0f && num <= vector.Length())
			{
				Microsoft.Xna.Framework.Vector3 vector4 = Microsoft.Xna.Framework.Vector3.Cross(vector2, vector3);
				float num2 = vector4.Length();
				if (num2 < toll)
				{
					flag = true;
					Microsoft.Xna.Framework.Vector3 vector5 = Microsoft.Xna.Framework.Vector3.Cross(vector2, vector4);
					vector5.Normalize();
					vector5 *= num2;
					near = p + vector5;
				}
			}
			return flag;
		}

		// Token: 0x0600014F RID: 335 RVA: 0x0000F9E4 File Offset: 0x0000DBE4
		public static bool FindIntersectionTwoLines(Microsoft.Xna.Framework.Vector2 P1, Microsoft.Xna.Framework.Vector2 P2, Microsoft.Xna.Framework.Vector2 R1, Microsoft.Xna.Framework.Vector2 R2, out Microsoft.Xna.Framework.Vector2 PointOut, IntervalEnum PointOutIsInternalFirstSegment = IntervalEnum.Internal, IntervalEnum PointOutIsInternalSecondSegment = IntervalEnum.Internal, float toll = -1f)
		{
			Microsoft.Xna.Framework.Vector3 vector;
			bool flag = Operations.FindIntersectionTwoLines(new Microsoft.Xna.Framework.Vector3(P1, 0f), new Microsoft.Xna.Framework.Vector3(P2, 0f), new Microsoft.Xna.Framework.Vector3(R1, 0f), new Microsoft.Xna.Framework.Vector3(R2, 0f), out vector, PointOutIsInternalFirstSegment, PointOutIsInternalSecondSegment, toll);
			PointOut = new Microsoft.Xna.Framework.Vector2(vector.X, vector.Y);
			return flag;
		}

		// Token: 0x06000150 RID: 336 RVA: 0x0000FA44 File Offset: 0x0000DC44
		public static bool FindIntersectionTwoLines(Microsoft.Xna.Framework.Vector3 P1, Microsoft.Xna.Framework.Vector3 P2, Microsoft.Xna.Framework.Vector3 R1, Microsoft.Xna.Framework.Vector3 R2, out Microsoft.Xna.Framework.Vector3 PointOut, IntervalEnum PointOutIsInternalFirstSegment = IntervalEnum.Internal, IntervalEnum PointOutIsInternalSecondSegment = IntervalEnum.Internal, float toll = -1f)
		{
			bool flag = false;
			PointOut = Microsoft.Xna.Framework.Vector3.Zero;
			bool flag2 = false;
			Microsoft.Xna.Framework.Vector3 vector = Microsoft.Xna.Framework.Vector3.UnitZ;
			if (Microsoft.Xna.Framework.Vector3.Dot(P2 - P1, R2 - R1) == 0f)
			{
				vector = Microsoft.Xna.Framework.Vector3.Cross(P2 - P1, R2 - R1);
				flag2 = true;
			}
			else if ((P1 - P2).Length() > 0f && (P2 - R1).Length() > 0f && (P1 - R1).Length() > 0f && Operations.AlignNodes(P1, P2, R1, toll) == 0)
			{
				vector = Microsoft.Xna.Framework.Vector3.Cross(P2 - P1, R1 - P1);
				flag2 = true;
			}
			else if ((P1 - P2).Length() > 0f && (P2 - R2).Length() > 0f && (P1 - R2).Length() > 0f && Operations.AlignNodes(P1, P2, R2, toll) == 0)
			{
				vector = Microsoft.Xna.Framework.Vector3.Cross(P2 - P1, R2 - P1);
				flag2 = true;
			}
			if (flag2)
			{
				vector.Normalize();
				Microsoft.Xna.Framework.Vector4 plane = Operations.GetPlane(P1, P2, vector + P1);
				Ray ray = new Ray(R1, R2 - R1);
				if (Operations.FindIntersectionRayAndPlane(plane, ray, out PointOut))
				{
					int num = Operations.AlignNodes(PointOut, P1, P2, toll);
					switch (PointOutIsInternalFirstSegment)
					{
					case IntervalEnum.Internal:
						if (num == 1)
						{
							flag = true;
							goto IL_01C5;
						}
						goto IL_01C5;
					case IntervalEnum.Closed:
						if (num > 0)
						{
							flag = true;
							goto IL_01C5;
						}
						goto IL_01C5;
					case IntervalEnum.LeftOpen:
						if (num == 1 || num == 3)
						{
							flag = true;
							goto IL_01C5;
						}
						goto IL_01C5;
					case IntervalEnum.RightOpen:
						if (num == 1 || num == 2)
						{
							flag = true;
							goto IL_01C5;
						}
						goto IL_01C5;
					case IntervalEnum.NotIncluded:
						if (num < 0)
						{
							flag = true;
							goto IL_01C5;
						}
						goto IL_01C5;
					case IntervalEnum.External:
						if (num == 0)
						{
							flag = true;
							goto IL_01C5;
						}
						goto IL_01C5;
					}
					flag = true;
					IL_01C5:
					num = Operations.AlignNodes(PointOut, R1, R2, toll);
					switch (PointOutIsInternalSecondSegment)
					{
					case IntervalEnum.Internal:
						return num == 1 && flag;
					case IntervalEnum.Closed:
						return num > 0 && flag;
					case IntervalEnum.LeftOpen:
						return (num == 1 || num == 3) && flag;
					case IntervalEnum.RightOpen:
						return (num == 1 || num == 2) && flag;
					case IntervalEnum.NotIncluded:
						return num < 0 && flag;
					case IntervalEnum.External:
						return num == 0 && flag;
					}
					flag = flag;
				}
			}
			return flag;
		}

		// Token: 0x06000151 RID: 337 RVA: 0x0000FCA8 File Offset: 0x0000DEA8
		public static bool FindIntersectionRayAndPlane(Microsoft.Xna.Framework.Vector4 Phi, Ray Ray, out Microsoft.Xna.Framework.Vector3 Point)
		{
			bool flag = false;
			Point = default(Microsoft.Xna.Framework.Vector3);
			float x = Ray.Direction.X;
			float y = Ray.Direction.Y;
			float z = Ray.Direction.Z;
			Microsoft.Xna.Framework.Vector3 position = Ray.Position;
			int num = 1;
			float num2 = Math.Abs(x);
			if (num2 < Math.Abs(y))
			{
				num2 = Math.Abs(y);
				num = 2;
			}
			if (num2 < Math.Abs(z))
			{
				num2 = Math.Abs(z);
				num = 3;
			}
			switch (num)
			{
			case 1:
				if (Math.Abs(x) > 1E-45f)
				{
					float num3 = Phi.X + Phi.Y * y / x + Phi.Z * z / x;
					if (num3 != 0f)
					{
						float num4 = (Phi.Y * y / x * position.X + Phi.Z * z / x * position.X - Phi.Y * position.Y - Phi.Z * position.Z - Phi.W) / num3;
						if (!float.IsNaN(num4) && !float.IsInfinity(num4))
						{
							Point.X = num4;
							Point.Y = position.Y + y / x * (Point.X - position.X);
							Point.Z = position.Z + z / x * (Point.X - position.X);
							flag = true;
						}
					}
				}
				break;
			case 2:
				if (Math.Abs(y) > 1E-45f)
				{
					float num5 = Phi.X * x / y + Phi.Y + Phi.Z * z / y;
					if (num5 != 0f)
					{
						float num6 = (Phi.X * x / y * position.Y + Phi.Z * z / y * position.Y - Phi.X * position.X - Phi.Z * position.Z - Phi.W) / num5;
						if (!float.IsNaN(num6) && !float.IsInfinity(num6))
						{
							Point.Y = num6;
							Point.X = position.X + x / y * (Point.Y - position.Y);
							Point.Z = position.Z + z / y * (Point.Y - position.Y);
							flag = true;
						}
					}
				}
				break;
			case 3:
				if (Math.Abs(z) > 1E-45f)
				{
					float num7 = Phi.X * x / z + Phi.Y * y / z + Phi.Z;
					if (num7 != 0f)
					{
						float num8 = (Phi.X * x / z * position.Z + Phi.Y * y / z * position.Z - Phi.X * position.X - Phi.Y * position.Y - Phi.W) / num7;
						if (!float.IsNaN(num8) && !float.IsInfinity(num8))
						{
							Point.Z = num8;
							Point.X = position.X + x / z * (Point.Z - position.Z);
							Point.Y = position.Y + y / z * (Point.Z - position.Z);
							flag = true;
						}
					}
				}
				break;
			}
			return flag;
		}

		// Token: 0x06000152 RID: 338 RVA: 0x00010000 File Offset: 0x0000E200
		public static bool FindIntersectionEllipsoidAndPlane_GetPointsAtZfixed(float a, float b, float c, Microsoft.Xna.Framework.Vector3 q, Microsoft.Xna.Framework.Vector3 r, Microsoft.Xna.Framework.Vector3 s, float z, out Microsoft.Xna.Framework.Vector3 p0, out Microsoft.Xna.Framework.Vector3 p1)
		{
			p0 = default(Microsoft.Xna.Framework.Vector3);
			p1 = default(Microsoft.Xna.Framework.Vector3);
			if (!Operations.IsPointInternalEllipsoid(a, b, c, q))
			{
				return false;
			}
			Microsoft.Xna.Framework.Vector3 vector;
			float num;
			float num2;
			Operations.FindIntersectionEllipsoidAndPlane_GetCharacteristics(a, b, c, q, ref r, ref s, out vector, out num, out num2);
			if ((double)Math.Abs(z - num2) <= 0.01)
			{
				z = num2;
			}
			if (Math.Abs(z) <= num2)
			{
				float num3 = z;
				float num4 = -num * Operations.sqrt(1f - Operations.sq(num3 / num2));
				p0 = vector + num4 * r + num3 * s;
				num4 = num * Operations.sqrt(1f - Operations.sq(num3 / num2));
				p1 = vector + num4 * r + num3 * s;
				return true;
			}
			return false;
		}

		// Token: 0x06000153 RID: 339 RVA: 0x000100D8 File Offset: 0x0000E2D8
		public static bool FindIntersectionEllipsoidAndPlane_GetPointAtZmax(float a, float b, float c, Microsoft.Xna.Framework.Vector3 q, Microsoft.Xna.Framework.Vector3 r, Microsoft.Xna.Framework.Vector3 s, out Microsoft.Xna.Framework.Vector3 p0)
		{
			p0 = default(Microsoft.Xna.Framework.Vector3);
			if (!Operations.IsPointInternalEllipsoid(a, b, c, q))
			{
				return false;
			}
			Microsoft.Xna.Framework.Vector3 vector;
			float num;
			float num2;
			Operations.FindIntersectionEllipsoidAndPlane_GetCharacteristics(a, b, c, q, ref r, ref s, out vector, out num, out num2);
			float num3 = num2;
			float num4 = num;
			p0 = q + num4 * r + num3 * s;
			return true;
		}

		// Token: 0x06000154 RID: 340 RVA: 0x00010134 File Offset: 0x0000E334
		private static void FindIntersectionEllipsoidAndPlane_GetCharacteristics(float a, float b, float c, Microsoft.Xna.Framework.Vector3 q, ref Microsoft.Xna.Framework.Vector3 r, ref Microsoft.Xna.Framework.Vector3 s, out Microsoft.Xna.Framework.Vector3 center, out float A, out float B)
		{
			center = default(Microsoft.Xna.Framework.Vector3);
			A = (B = 0f);
			r -= q;
			r.Normalize();
			s -= q;
			s.Normalize();
			Matrix matrix = Operations.Diag(1f / a, 1f / b, 1f / c, 1f);
			Microsoft.Xna.Framework.Vector3 vector = Operations.MatrixPerVector3(matrix, q);
			Microsoft.Xna.Framework.Vector3 vector2 = Operations.MatrixPerVector3(matrix, r);
			Microsoft.Xna.Framework.Vector3 vector3 = Operations.MatrixPerVector3(matrix, s);
			float num = -Microsoft.Xna.Framework.Vector3.Dot(vector, vector2) / Microsoft.Xna.Framework.Vector3.Dot(vector2, vector2);
			float num2 = -Microsoft.Xna.Framework.Vector3.Dot(vector, vector3) / Microsoft.Xna.Framework.Vector3.Dot(vector3, vector3);
			center = q + num * r + num2 * s;
			float num3 = Microsoft.Xna.Framework.Vector3.Dot(vector, vector) - Operations.sq(Microsoft.Xna.Framework.Vector3.Dot(vector, vector2)) / Microsoft.Xna.Framework.Vector3.Dot(vector2, vector2) - Operations.sq(Microsoft.Xna.Framework.Vector3.Dot(vector, vector3)) / Microsoft.Xna.Framework.Vector3.Dot(vector3, vector3);
			A = Operations.sqrt((1f - num3) / Microsoft.Xna.Framework.Vector3.Dot(vector2, vector2));
			B = Operations.sqrt((1f - num3) / Microsoft.Xna.Framework.Vector3.Dot(vector3, vector3));
		}

		// Token: 0x06000155 RID: 341 RVA: 0x00010294 File Offset: 0x0000E494
		public static bool FindIntersectionEllipsoidAndPlane_GetPointsForPennacchio(float a, float b, float c, Microsoft.Xna.Framework.Vector3 q, Microsoft.Xna.Framework.Vector3 r, Microsoft.Xna.Framework.Vector3 s, float gammaMin, float gammaMax, float lmax, out float[] gam)
		{
			gam = null;
			SortedList<float, Microsoft.Xna.Framework.Vector3> sortedList = new SortedList<float, Microsoft.Xna.Framework.Vector3>();
			if (!Operations.IsPointInternalEllipsoid(a, b, c, q))
			{
				return false;
			}
			Microsoft.Xna.Framework.Vector3 vector;
			float num;
			float num2;
			Operations.FindIntersectionEllipsoidAndPlane_GetCharacteristics(a, b, c, q, ref r, ref s, out vector, out num, out num2);
			float num3 = Operations.LArcoEllisse(gammaMin, 1.5707964f, num, num2);
			float num4 = (float)Math.Max(1, (int)Math.Round((double)(num3 / lmax)));
			float num5 = num3 / num4;
			float num6 = gammaMin;
			float num7 = 1E-05f;
			int num8 = 0;
			while ((float)num8 <= num4)
			{
				float num9 = (float)num8 * num5;
				float num10 = 0f;
				float num11 = 1.5707964f;
				float num12 = 1f;
				while (Math.Abs(num12) > num7)
				{
					num6 = (num10 + num11) / 2f;
					float num13 = num9 - Operations.LArcoEllisse(gammaMin, num10, num, num2);
					float num14 = num9 - Operations.LArcoEllisse(gammaMin, num11, num, num2);
					num12 = num9 - Operations.LArcoEllisse(gammaMin, num6, num, num2);
					if (num11 - num10 < num7)
					{
						break;
					}
					if (num12 * num14 <= 0f)
					{
						num10 = num6;
					}
					else if (num12 * num13 <= 0f)
					{
						num11 = num6;
					}
					else
					{
						Logger.Log("Error in Operations>FindIntersectionEllipsoidAndPlane_GetPointsForPennacchio: il metodo della bisezione ha fallito", DebugLevel.CRITICAL);
					}
				}
				Microsoft.Xna.Framework.Vector3 vector2 = vector + num * Operations.Cos(num6, 6) * r + num2 * Operations.Sin(num6, 6) * s;
				float num15;
				if (num8 == 0)
				{
					num15 = gammaMin;
				}
				else if ((float)num8 == num4)
				{
					num15 = gammaMax;
				}
				else
				{
					float num16 = Operations.Atan(vector2.Z / Operations.sqrt(Operations.sq(vector2.X) + Operations.sq(vector2.Y)));
					num15 = Operations.GetTetaAngleEllipseFromAlfaAngle(c, a, num16);
				}
				if (!sortedList.ContainsKey(num15))
				{
					sortedList.Add(num15, vector2);
				}
				num8++;
			}
			gam = sortedList.Keys.ToArray<float>();
			return true;
		}

		// Token: 0x06000156 RID: 342 RVA: 0x00010464 File Offset: 0x0000E664
		public static void GetPointsInParabolaEquiSpaced(float A, float B, float C, float Xmin, float Xmax, int NumMin, float lmax, Microsoft.Xna.Framework.Vector3 Origin, Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, out SortedList<float, Microsoft.Xna.Framework.Vector3> ListPoints)
		{
			ListPoints = new SortedList<float, Microsoft.Xna.Framework.Vector3>();
			float num = Operations.LArcoParabola(Xmin, Xmax / 2f, A, B);
			float num2 = (float)(2 * Math.Max(NumMin, (int)Math.Round((double)(num / lmax))));
			float num3 = 2f * num / num2;
			float num4 = Xmin;
			float num5 = 0.1f;
			int num6 = 0;
			while ((float)num6 <= num2)
			{
				float num7 = (float)num6 * num3;
				float num8 = Xmin;
				float num9 = Xmax;
				float num10 = 1f;
				while (Math.Abs(num10) > num5)
				{
					num4 = (num8 + num9) / 2f;
					float num11 = num7 - Operations.LArcoParabola(Xmin, num8, A, B);
					float num12 = num7 - Operations.LArcoParabola(Xmin, num9, A, B);
					num10 = num7 - Operations.LArcoParabola(Xmin, num4, A, B);
					if (num9 - num8 < num5)
					{
						break;
					}
					if (num10 * num12 <= 0f)
					{
						num8 = num4;
					}
					else if (num10 * num11 <= 0f)
					{
						num9 = num4;
					}
					else
					{
						Logger.Log("Error in Operations>GetPointsInParabolaEquiSpaced: il metodo della bisezione ha fallito", DebugLevel.CRITICAL);
					}
				}
				if (num6 == 0)
				{
					num4 = Xmin;
				}
				else if ((float)num6 == num2)
				{
					num4 = Xmax;
				}
				Microsoft.Xna.Framework.Vector3 vector = Origin + num4 * e1 + (A * Operations.sq(num4) + B * num4 + C) * e3;
				if (!ListPoints.ContainsKey(num4))
				{
					ListPoints.Add(num4, vector);
				}
				num6++;
			}
		}

		// Token: 0x06000157 RID: 343 RVA: 0x000105B8 File Offset: 0x0000E7B8
		public static void GetPointsInEllipseFromZlevels(float A, float B, List<float> Zlevels, Microsoft.Xna.Framework.Vector3 Origin, Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, out SortedList<float, Microsoft.Xna.Framework.Vector3> ListPoints)
		{
			ListPoints = new SortedList<float, Microsoft.Xna.Framework.Vector3>();
			foreach (float num in Zlevels)
			{
				if (1f - Operations.sq(num / B) >= 0f)
				{
					float num2 = A * Operations.sqrt(1f - Operations.sq(num / B));
					Microsoft.Xna.Framework.Vector3 vector = Origin + num2 * e1 + num * e3;
					if (!ListPoints.ContainsKey(num))
					{
						ListPoints.Add(num, vector);
					}
				}
			}
		}

		// Token: 0x06000158 RID: 344 RVA: 0x00010664 File Offset: 0x0000E864
		public static Microsoft.Xna.Framework.Vector3 GetIntradossoArchEllipse(Microsoft.Xna.Framework.Vector3 p, Microsoft.Xna.Framework.Vector3 CentroEllisseEstradosso, float RxEstradosso, float RzEstradosso, float ThickBase, float ThicknessKey, float teta0)
		{
			Microsoft.Xna.Framework.Vector3 vector = p - CentroEllisseEstradosso;
			Microsoft.Xna.Framework.Vector3 normalEllipse = Operations.GetNormalEllipse(RxEstradosso, RzEstradosso, vector.X, vector.Z);
			Microsoft.Xna.Framework.Vector3 vector2 = new Microsoft.Xna.Framework.Vector3(Operations.Cos(teta0, 6) * RxEstradosso, 0f, Operations.Sin(teta0, 6) * RzEstradosso);
			Microsoft.Xna.Framework.Vector3 normalEllipse2 = Operations.GetNormalEllipse(RxEstradosso, RzEstradosso, vector2.X, vector2.Z);
			float thickness = Operations.GetThickness(ThickBase, ThicknessKey, normalEllipse2, Microsoft.Xna.Framework.Vector3.UnitZ, normalEllipse, ThicknessLawEnum.Linear);
			return p - normalEllipse * thickness;
		}

		// Token: 0x06000159 RID: 345 RVA: 0x000106E4 File Offset: 0x0000E8E4
		public static void GetParamsArchEllipse(float X1, float X2, float f, float L, float S1, float S2, float Tb, float Tt, float alfa, float Dz, out Microsoft.Xna.Framework.Vector3 centroEllisseEstradosso, out float RxEstradosso, out float RzEstradosso, out float teta)
		{
			Microsoft.Xna.Framework.Vector3 vector = default(Microsoft.Xna.Framework.Vector3);
			float num = f;
			float num2 = L / 2f;
			float num3 = num;
			alfa *= 0.017453292f;
			float num4 = 0f;
			float num5 = 2f * num2 + S1 + S2;
			if (alfa > DefaultValues.MesherAngularToll)
			{
				float num6 = Operations.Atan(num5 / (2f * num3)) * 0.999f;
				if (alfa > num6)
				{
					alfa = num6;
				}
				num = (num5 - num3 * Operations.Tan(alfa)) / (num5 - 2f * num3 * Operations.Tan(alfa)) * num3;
				num4 = num - num3;
				num2 = Operations.sqrt(num5 * Operations.sq(num) * Operations.Tan(alfa) / (2f * num4));
			}
			else
			{
				alfa = 0f;
			}
			if (Dz > 0f)
			{
				num4 += Dz;
			}
			bool flag = false;
			float num7 = 0f;
			if ((flag ? 1 : 0) % 2 == 0)
			{
				X2 += (S2 - S1) / 2f;
				vector = new Microsoft.Xna.Framework.Vector3(X2, num7, -num4);
			}
			else
			{
				X1 += (S2 - S1) / 2f;
				vector = new Microsoft.Xna.Framework.Vector3(X1, num7, -num4);
			}
			float num8 = num5 / 2f / num2;
			if (num8 > 1f)
			{
				num8 = 1f;
			}
			teta = Operations.Acos(num8, 6);
			Microsoft.Xna.Framework.Vector3 vector2 = new Microsoft.Xna.Framework.Vector3(num2 * Operations.Cos(teta, 6), 0f, num * Operations.Sin(teta, 6));
			Microsoft.Xna.Framework.Vector3 vector3 = new Microsoft.Xna.Framework.Vector3(vector2.X / Operations.sq(num2), 0f, vector2.Z / Operations.sq(num));
			vector3.Normalize();
			vector2 += Tb * vector3;
			Microsoft.Xna.Framework.Vector3 vector4 = new Microsoft.Xna.Framework.Vector3(0f, 0f, f + Tt - vector.Z);
			float num9 = Operations.sqrt(Operations.sq(vector2.X * vector4.Z) - Operations.sq(vector4.X * vector2.Z));
			RxEstradosso = num9 / Operations.sqrt(Operations.sq(vector4.Z) - Operations.sq(vector2.Z));
			RzEstradosso = num9 / Operations.sqrt(Operations.sq(vector2.X) - Operations.sq(vector4.X));
			vector4 += vector;
			centroEllisseEstradosso = vector4 - RzEstradosso * Microsoft.Xna.Framework.Vector3.UnitZ;
			teta = Operations.Acos(vector2.X / RxEstradosso, 6);
		}

		// Token: 0x0600015A RID: 346 RVA: 0x0001094C File Offset: 0x0000EB4C
		public static Microsoft.Xna.Framework.Vector3 GetEstradossoArchEllipse(Microsoft.Xna.Framework.Vector3 p, float X1, float X2, float f, float L, float S1, float S2, float Tb, float Tt, float alfa, float Dz, float ThickBase, float ThicknessKey)
		{
			Microsoft.Xna.Framework.Vector3 vector;
			float num;
			float num2;
			float num3;
			Operations.GetParamsArchEllipse(X1, X2, f, L, S1, S2, Tb, Tt, alfa, Dz, out vector, out num, out num2, out num3);
			return Operations.GetEstradossoArchEllipse(p, vector, num, num2, ThickBase, ThicknessKey, num3);
		}

		// Token: 0x0600015B RID: 347 RVA: 0x00010988 File Offset: 0x0000EB88
		public static Microsoft.Xna.Framework.Vector3 GetEstradossoArchEllipse(Microsoft.Xna.Framework.Vector3 p, Microsoft.Xna.Framework.Vector3 CentroEllisseEstradosso, float RxEstradosso, float RzEstradosso, float ThickBase, float ThicknessKey, float teta0)
		{
			Microsoft.Xna.Framework.Vector3 normalEllipse = Operations.GetNormalEllipse(RxEstradosso, RzEstradosso, p.X, p.Z);
			Microsoft.Xna.Framework.Vector3 vector = new Microsoft.Xna.Framework.Vector3(Operations.Cos(teta0, 6) * RxEstradosso, 0f, Operations.Sin(teta0, 6) * RzEstradosso);
			Microsoft.Xna.Framework.Vector3 normalEllipse2 = Operations.GetNormalEllipse(RxEstradosso, RzEstradosso, vector.X, vector.Z);
			float thickness = Operations.GetThickness(ThickBase, ThicknessKey, normalEllipse2, Microsoft.Xna.Framework.Vector3.UnitZ, normalEllipse, ThicknessLawEnum.Linear);
			return p + normalEllipse * thickness + CentroEllisseEstradosso;
		}

		// Token: 0x0600015C RID: 348 RVA: 0x00010A04 File Offset: 0x0000EC04
		public static float GetThickness(float Thickness0, float Thickness1, Microsoft.Xna.Framework.Vector3 Normal0, Microsoft.Xna.Framework.Vector3 Normal1, Microsoft.Xna.Framework.Vector3 Normal, ThicknessLawEnum ThicknessLaw)
		{
			float num = 0f;
			if ((double)(Normal - Normal1).Length() < 1E-05)
			{
				return Thickness1;
			}
			if (!Normal.Equals(Microsoft.Xna.Framework.Vector3.UnitZ))
			{
				Microsoft.Xna.Framework.Vector3 vector = Normal;
				vector.Z = 0f;
				vector.Normalize();
				float num2 = Microsoft.Xna.Framework.Vector3.Dot(Normal, vector);
				if (num2 > 1f)
				{
					num2 = 1f;
				}
				if (num2 < -1f)
				{
					num2 = -1f;
				}
				num2 = (float)Math.Acos((double)num2);
				Microsoft.Xna.Framework.Vector3 vector2 = Normal0;
				vector2.Z = 0f;
				vector2.Normalize();
				float num3 = Microsoft.Xna.Framework.Vector3.Dot(Normal0, vector2);
				if (num3 > 1f)
				{
					num3 = 1f;
				}
				if (num3 < -1f)
				{
					num3 = -1f;
				}
				num3 = (float)Math.Acos((double)num3);
				float num4 = Microsoft.Xna.Framework.Vector3.Dot(Normal1, vector2);
				if (num4 > 1f)
				{
					num4 = 1f;
				}
				if (num4 < -1f)
				{
					num4 = -1f;
				}
				num4 = (float)Math.Acos((double)num4);
				if (ThicknessLaw != ThicknessLawEnum.Constant)
				{
					if (ThicknessLaw == ThicknessLawEnum.Linear)
					{
						float num5 = num3;
						float num6 = num4;
						num = (Thickness1 - Thickness0) / (num6 - num5) * (num2 - num3) + Thickness0;
					}
				}
				else
				{
					num = Thickness0;
				}
				if (float.IsNaN(num))
				{
					Console.WriteLine("aaaa");
				}
				return num;
			}
			if (ThicknessLaw == ThicknessLawEnum.Constant)
			{
				return Thickness0;
			}
			return Thickness1;
		}

		// Token: 0x0600015D RID: 349 RVA: 0x00010B54 File Offset: 0x0000ED54
		public static Microsoft.Xna.Framework.Vector3 GetNormalEllipse(float r1, float s1, float xx, float yy)
		{
			Microsoft.Xna.Framework.Vector3 vector = new Microsoft.Xna.Framework.Vector3(xx / (r1 * r1), 0f, yy / (s1 * s1));
			vector.Normalize();
			return vector;
		}

		// Token: 0x0600015E RID: 350 RVA: 0x00010B80 File Offset: 0x0000ED80
		public static void GetPointsInEllipseEquiSpaced(Microsoft.Xna.Framework.Vector3 p1, Microsoft.Xna.Framework.Vector3 p2, float A, float B, Microsoft.Xna.Framework.Vector3 Origin, Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, float lmax, out List<Microsoft.Xna.Framework.Vector3> ListPoints)
		{
			Microsoft.Xna.Framework.Vector3 ptr = p1 - Origin;
			Microsoft.Xna.Framework.Vector3 vector = p2 - Origin;
			float num = Operations.Acos(ptr.X / A, 6);
			float num2 = Operations.Acos(vector.X / A, 6);
			SortedList<float, Microsoft.Xna.Framework.Vector3> sortedList;
			if (num > num2)
			{
				Operations.GetPointsInEllipseEquiSpaced(A, B, num2, num, lmax, Origin, e1, e2, e3, out sortedList);
			}
			else
			{
				Operations.GetPointsInEllipseEquiSpaced(A, B, num, num2, lmax, Origin, e1, e2, e3, out sortedList);
			}
			if (sortedList.Count > 0)
			{
				ListPoints = sortedList.Values.ToList<Microsoft.Xna.Framework.Vector3>();
				if (num > num2)
				{
					ListPoints.Reverse();
				}
				ListPoints[0] = p1;
				ListPoints[ListPoints.Count - 1] = p2;
				return;
			}
			Logger.Log("GetPointsInEllipseEquiSpaced(): Errore nella individuazione dei punti.", DebugLevel.CRITICAL);
			ListPoints = new List<Microsoft.Xna.Framework.Vector3>();
			ListPoints.Add(p1);
			ListPoints.Add(p2);
		}

		// Token: 0x0600015F RID: 351 RVA: 0x00010C54 File Offset: 0x0000EE54
		public static void GetPointsInEllipseEquiSpaced(float A, float B, float tetaMin, float tetaMax, float lmax, Microsoft.Xna.Framework.Vector3 Origin, Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, out SortedList<float, Microsoft.Xna.Framework.Vector3> ListPoints)
		{
			ListPoints = new SortedList<float, Microsoft.Xna.Framework.Vector3>();
			float num = Operations.LArcoEllisse(tetaMin, tetaMax, A, B);
			float num2 = (float)Math.Max(1, (int)Math.Round((double)(Math.Abs(num) / lmax)));
			float num3 = num / num2;
			float num4 = tetaMin;
			float num5 = 1E-05f;
			int num6 = 0;
			while ((float)num6 <= num2)
			{
				if (num6 == 0)
				{
					num4 = tetaMin;
				}
				else if ((float)num6 == num2)
				{
					num4 = tetaMax;
				}
				else
				{
					float num7 = (float)num6 * num3;
					float num8 = tetaMin;
					float num9 = tetaMax;
					float num10 = 1f;
					while (Math.Abs(num10) > num5)
					{
						num4 = (num8 + num9) / 2f;
						float num11 = num7 - Operations.LArcoEllisse(tetaMin, num8, A, B);
						float num12 = num7 - Operations.LArcoEllisse(tetaMin, num9, A, B);
						num10 = num7 - Operations.LArcoEllisse(tetaMin, num4, A, B);
						if (num9 - num8 < num5)
						{
							break;
						}
						if (num10 * num12 <= 0f)
						{
							num8 = num4;
						}
						else if (num10 * num11 <= 0f)
						{
							num9 = num4;
						}
						else
						{
							Logger.Log("Error in Operations>GetPointsInEllipseEquiSpaced: il metodo della bisezione ha fallito", DebugLevel.CRITICAL);
						}
					}
				}
				Microsoft.Xna.Framework.Vector3 vector = A * Operations.Cos(num4, 6) * e1 + B * Operations.Sin(num4, 6) * e3;
				Microsoft.Xna.Framework.Vector3 vector2 = Origin + vector;
				float num13;
				if (num6 == 0)
				{
					num13 = tetaMin;
				}
				else if ((float)num6 == num2)
				{
					num13 = tetaMax;
				}
				else
				{
					float num14 = Operations.Atan(vector.Z / Operations.sqrt(Operations.sq(vector.X) + Operations.sq(vector.Y)));
					if ((double)num4 > 1.5707963267948966)
					{
						num14 = 3.1415927f - num14;
					}
					num13 = Operations.GetTetaAngleEllipseFromAlfaAngle(A, B, num14);
				}
				if (!ListPoints.ContainsKey(num13))
				{
					ListPoints.Add(num13, vector2);
				}
				num6++;
			}
		}

		// Token: 0x06000160 RID: 352 RVA: 0x00010E0C File Offset: 0x0000F00C
		public static float GetTetaAngleEllipseFromPoint(float A, float B, Microsoft.Xna.Framework.Vector3 P, PlaneEnum plane = PlaneEnum.XY)
		{
			switch (plane)
			{
			default:
				return Operations.GetTetaAngleEllipseFromPoint(A, B, P.X, P.Y);
			case PlaneEnum.XZ:
				return Operations.GetTetaAngleEllipseFromPoint(A, B, P.X, P.Z);
			case PlaneEnum.YZ:
				return Operations.GetTetaAngleEllipseFromPoint(A, B, P.Y, P.Z);
			}
		}

		// Token: 0x06000161 RID: 353 RVA: 0x00010E68 File Offset: 0x0000F068
		public static float GetTetaAngleEllipseFromPoint(float A, float B, float X, float Y)
		{
			float num;
			if (X == 0f)
			{
				if (Y > 0f)
				{
					num = 1.5707964f;
				}
				else
				{
					num = 4.712389f;
				}
			}
			else if (X > 0f)
			{
				num = Operations.Atan(Y / X * A / B);
				if (Y < 0f)
				{
					num = 6.2831855f + num;
				}
			}
			else
			{
				num = 3.1415927f - Operations.Atan(-Y / X * A / B);
			}
			return num;
		}

		// Token: 0x06000162 RID: 354 RVA: 0x00010ED4 File Offset: 0x0000F0D4
		public static float GetAlfaAngleEllipseFromPoint(float A, float B, float X, float Y)
		{
			float num;
			if (X == 0f)
			{
				if (Y > 0f)
				{
					num = 1.5707964f;
				}
				else
				{
					num = 4.712389f;
				}
			}
			else if (X > 0f)
			{
				num = Operations.Atan(Y / X);
				if (Y < 0f)
				{
					num = 6.2831855f + num;
				}
			}
			else
			{
				num = 3.1415927f - Operations.Atan(-Y / X);
			}
			return num;
		}

		// Token: 0x06000163 RID: 355 RVA: 0x00010F38 File Offset: 0x0000F138
		public static float GetTetaAngleEllipseFromAlfaAngle(float A, float B, float alfa)
		{
			if (alfa > 6.2831855f)
			{
				alfa -= 6.2831855f;
			}
			float num;
			if (alfa == 1.5707964f)
			{
				num = 1.5707964f;
			}
			else if (alfa == 4.712389f)
			{
				num = 4.712389f;
			}
			else if (alfa > -1.5707964f && alfa < 1.5707964f)
			{
				num = Operations.Atan(Operations.Tan(alfa) * A / B);
			}
			else if (1.5707964f < alfa && alfa < 4.712389f)
			{
				num = 3.1415927f - Operations.Atan(-Operations.Tan(alfa) * A / B);
			}
			else
			{
				num = 6.2831855f + Operations.Atan(Operations.Tan(alfa) * A / B);
			}
			return num;
		}

		// Token: 0x06000164 RID: 356 RVA: 0x00010FD8 File Offset: 0x0000F1D8
		public static float LArcoEllisse(float teta1, float teta2, float r1, float r2)
		{
			float[] array = new float[] { 0.9324695f, 0.6612094f, 0.2386192f, -0.2386192f, -0.6612094f, -0.9324695f };
			float[] array2 = new float[] { 0.17132449f, 0.36076158f, 0.46791393f, 0.46791393f, 0.36076158f, 0.17132449f };
			float num = 0f;
			for (int i = 0; i < 6; i++)
			{
				float num2 = teta1 * (1f - array[i]) / 2f + teta2 * (1f + array[i]) / 2f;
				num += (teta2 - teta1) / 2f * array2[i] * Operations.sqrt(Operations.sq(r1 * Operations.Sin(num2, 6)) + Operations.sq(r2 * Operations.Cos(num2, 6)));
			}
			return num;
		}

		// Token: 0x06000165 RID: 357 RVA: 0x000110C4 File Offset: 0x0000F2C4
		public static float LArcoParabola(float x1, float x2, float aa, float bb)
		{
			float[] array = new float[] { 0.9324695f, 0.6612094f, 0.2386192f, -0.2386192f, -0.6612094f, -0.9324695f };
			float[] array2 = new float[] { 0.17132449f, 0.36076158f, 0.46791393f, 0.46791393f, 0.36076158f, 0.17132449f };
			float num = 0f;
			for (int i = 0; i < 6; i++)
			{
				float num2 = x1 * (1f - array[i]) / 2f + x2 * (1f + array[i]) / 2f;
				num += (x2 - x1) / 2f * array2[i] * Operations.sqrt(1f + Operations.sq(2f * aa * num2 + bb));
			}
			return num;
		}

		// Token: 0x06000166 RID: 358 RVA: 0x000111AC File Offset: 0x0000F3AC
		private static Matrix Diag(float m11, float m22, float m33, float m44)
		{
			return new Matrix
			{
				M11 = m11,
				M22 = m22,
				M33 = m33,
				M44 = m44
			};
		}

		// Token: 0x06000167 RID: 359 RVA: 0x000111E2 File Offset: 0x0000F3E2
		private static bool IsPointInternalEllipsoid(float a, float b, float c, Microsoft.Xna.Framework.Vector3 q)
		{
			return (double)(Operations.sq(q.X / a) + Operations.sq(q.Y / b) + Operations.sq(q.Z / c)) <= 1.000001;
		}

		// Token: 0x06000168 RID: 360 RVA: 0x0001121C File Offset: 0x0000F41C
		public static Microsoft.Xna.Framework.Vector3 CartesianoToPolare(Microsoft.Xna.Framework.Vector3 FirstPosition, Microsoft.Xna.Framework.Vector3 SecondPosition)
		{
			Microsoft.Xna.Framework.Vector3 vector = default(Microsoft.Xna.Framework.Vector3);
			Microsoft.Xna.Framework.Vector3 vector2 = SecondPosition - FirstPosition;
			Microsoft.Xna.Framework.Vector3 vector3 = new Microsoft.Xna.Framework.Vector3(vector2.X, vector2.Y, 0f);
			vector.X = vector2.Length();
			double num = Math.Atan((double)(vector2.Y / vector2.X));
			if (double.IsNaN(num))
			{
				num = 0.0;
			}
			if (vector2.X < 0f && vector2.Y > 0f)
			{
				num = 3.141592653589793 + num;
			}
			else if (vector2.X < 0f && vector2.Y < 0f)
			{
				num = 3.141592653589793 + num;
			}
			else if (vector2.X > 0f && vector2.Y < 0f)
			{
				num = 6.283185307179586 + num;
			}
			vector.Y = (float)num / 3.1415927f * 180f;
			double num2 = Math.Atan((double)(vector2.Z / vector3.Length()));
			if (double.IsNaN(num2))
			{
				num2 = 0.0;
			}
			vector.Z = (float)num2 / 3.1415927f * 180f;
			return vector;
		}

		// Token: 0x06000169 RID: 361 RVA: 0x00011354 File Offset: 0x0000F554
		public static Microsoft.Xna.Framework.Vector3 PolareToCartesiano(Microsoft.Xna.Framework.Vector3 RadialPosition)
		{
			return new Microsoft.Xna.Framework.Vector3
			{
				X = RadialPosition.X * Operations.Cosd(RadialPosition.Z, 6) * Operations.Cosd(RadialPosition.Y, 6),
				Y = RadialPosition.X * Operations.Cosd(RadialPosition.Z, 6) * Operations.Sind(RadialPosition.Y, 6),
				Z = RadialPosition.X * Operations.Sind(RadialPosition.Z, 6)
			};
		}

		// Token: 0x0600016A RID: 362 RVA: 0x000113D4 File Offset: 0x0000F5D4
		public static Microsoft.Xna.Framework.Vector3 GetParabolaEquation(float y1_, float y2_, float y3_, float x1_, float x2_, float x3_)
		{
			float num = (float)((double)(y3_ - y1_) - (Math.Pow((double)x3_, 2.0) - Math.Pow((double)x1_, 2.0)) / (Math.Pow((double)x2_, 2.0) - Math.Pow((double)x1_, 2.0)) * (double)(y2_ - y1_)) / ((x3_ - x1_) * (x2_ - x3_) / (x2_ + x1_));
			float num2 = (y2_ - y1_ - num * (x2_ - x1_)) / (float)(Math.Pow((double)x2_, 2.0) - Math.Pow((double)x1_, 2.0));
			float num3 = y1_ - num2 * (float)Math.Pow((double)x1_, 2.0) - num * x1_;
			return new Microsoft.Xna.Framework.Vector3(num2, num, num3);
		}

		// Token: 0x0600016B RID: 363 RVA: 0x00011493 File Offset: 0x0000F693
		public static Microsoft.Xna.Framework.Vector3 FramePolygonLocalToGlobal(Microsoft.Xna.Framework.Vector3 P1, Microsoft.Xna.Framework.Vector3 P2, Microsoft.Xna.Framework.Vector3 VertexPolygon, float LocalAxesAngle)
		{
			return Operations.MatrixPerVector3(Operations.GetLineRotationMatrixLocalToGlobal(P1, P2, LocalAxesAngle), VertexPolygon);
		}

		// Token: 0x0600016C RID: 364 RVA: 0x000114A3 File Offset: 0x0000F6A3
		public static Microsoft.Xna.Framework.Vector3 ElipseLocalToGlobal(Microsoft.Xna.Framework.Vector3 P1, Microsoft.Xna.Framework.Vector3 P2, Microsoft.Xna.Framework.Vector3 VertexPolygon)
		{
			return Operations.MatrixPerVector3(Operations.GetElipseRotationMatrixLocalToGlobal(P1, P2, 0f), VertexPolygon);
		}

		// Token: 0x0600016D RID: 365 RVA: 0x000114B7 File Offset: 0x0000F6B7
		public static Microsoft.Xna.Framework.Vector3 VectorLocalToGlobal(Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, Microsoft.Xna.Framework.Vector3 Origin, Microsoft.Xna.Framework.Vector3 P)
		{
			return Operations.MatrixPerVector3(Operations.GetMatrixRotoTranslationByReferenceSystem(e1, e2, e3, Origin), P);
		}

		// Token: 0x0600016E RID: 366 RVA: 0x000114C9 File Offset: 0x0000F6C9
		public static Microsoft.Xna.Framework.Vector3 VectorGlobalToLocal(Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, Microsoft.Xna.Framework.Vector3 Origin, Microsoft.Xna.Framework.Vector3 P)
		{
			return Operations.MatrixPerVector3(Matrix.Transpose(Operations.GetMatrixRotoTranslationByReferenceSystem(e1, e2, e3, Origin)), P - Origin);
		}

		// Token: 0x0600016F RID: 367 RVA: 0x000114E8 File Offset: 0x0000F6E8
		public static void FrameVersoriLocal(Microsoft.Xna.Framework.Vector3 P1, Microsoft.Xna.Framework.Vector3 P2, float RotationLocalX, out Microsoft.Xna.Framework.Vector3 e1, out Microsoft.Xna.Framework.Vector3 e2, out Microsoft.Xna.Framework.Vector3 e3)
		{
			Matrix lineRotationMatrixLocalToGlobal = Operations.GetLineRotationMatrixLocalToGlobal(P1, P2, RotationLocalX);
			e1 = new Microsoft.Xna.Framework.Vector3(lineRotationMatrixLocalToGlobal.M11, lineRotationMatrixLocalToGlobal.M21, lineRotationMatrixLocalToGlobal.M31);
			e2 = new Microsoft.Xna.Framework.Vector3(lineRotationMatrixLocalToGlobal.M12, lineRotationMatrixLocalToGlobal.M22, lineRotationMatrixLocalToGlobal.M32);
			e3 = new Microsoft.Xna.Framework.Vector3(lineRotationMatrixLocalToGlobal.M13, lineRotationMatrixLocalToGlobal.M23, lineRotationMatrixLocalToGlobal.M33);
		}

		// Token: 0x06000170 RID: 368 RVA: 0x00011558 File Offset: 0x0000F758
		public static Matrix GetLineRotationMatrixLocalToGlobal(Microsoft.Xna.Framework.Vector3 P1, Microsoft.Xna.Framework.Vector3 P2, float RotationLocalX)
		{
			Matrix matrix = default(Matrix);
			Microsoft.Xna.Framework.Vector3 vector;
			Microsoft.Xna.Framework.Vector3 vector2;
			Microsoft.Xna.Framework.Vector3 vector3;
			if (P2.X == P1.X && P2.Y == P1.Y)
			{
				vector.X = 0f;
				vector.Y = 0f;
				if (P2.Z > P1.Z)
				{
					vector.Z = 1f;
				}
				else
				{
					vector.Z = -1f;
				}
				vector2.X = 0f;
				vector2.Y = 1f;
				vector2.Z = 0f;
				vector3.X = vector.Y * vector2.Z - vector2.Y * vector.Z;
				vector3.Y = vector.Z * vector2.X - vector2.Z * vector.X;
				vector3.Z = vector.X * vector2.Y - vector2.X * vector.Y;
			}
			else
			{
				float num = (P2 - P1).Length();
				vector.X = (P2.X - P1.X) / num;
				vector.Y = (P2.Y - P1.Y) / num;
				vector.Z = (P2.Z - P1.Z) / num;
				float num2 = (float)Math.Pow(Math.Pow((double)vector.X, 2.0) + Math.Pow((double)vector.Y, 2.0), 0.5);
				vector2.X = -vector.Y / num2;
				vector2.Y = vector.X / num2;
				vector2.Z = 0f;
				vector3.X = vector.Y * vector2.Z - vector2.Y * vector.Z;
				vector3.Y = vector.Z * vector2.X - vector2.Z * vector.X;
				vector3.Z = vector.X * vector2.Y - vector2.X * vector.Y;
			}
			matrix.M11 = vector.X;
			matrix.M12 = vector2.X;
			matrix.M13 = vector3.X;
			matrix.M14 = 0f;
			matrix.M21 = vector.Y;
			matrix.M22 = vector2.Y;
			matrix.M23 = vector3.Y;
			matrix.M24 = 0f;
			matrix.M31 = vector.Z;
			matrix.M32 = vector2.Z;
			matrix.M33 = vector3.Z;
			matrix.M34 = 0f;
			matrix.M41 = 0f;
			matrix.M42 = 0f;
			matrix.M43 = 0f;
			matrix.M44 = 1f;
			if (RotationLocalX != 0f)
			{
				RotationLocalX *= 0.017453292f;
				Matrix matrix2 = Matrix.CreateRotationX(RotationLocalX);
				matrix = Matrix.Multiply(matrix, matrix2);
			}
			matrix.M14 = P1.X;
			matrix.M24 = P1.Y;
			matrix.M34 = P1.Z;
			return matrix;
		}

		// Token: 0x06000171 RID: 369 RVA: 0x00011898 File Offset: 0x0000FA98
		public static Matrix GetMatrixRotoTranslationByReferenceSystem(Microsoft.Xna.Framework.Vector3 e1, Microsoft.Xna.Framework.Vector3 e2, Microsoft.Xna.Framework.Vector3 e3, Microsoft.Xna.Framework.Vector3 Origin)
		{
			return new Matrix
			{
				M11 = e1.X,
				M12 = e2.X,
				M13 = e3.X,
				M21 = e1.Y,
				M22 = e2.Y,
				M23 = e3.Y,
				M31 = e1.Z,
				M32 = e2.Z,
				M33 = e3.Z,
				M41 = 0f,
				M42 = 0f,
				M43 = 0f,
				M44 = 1f,
				M14 = Origin.X,
				M24 = Origin.Y,
				M34 = Origin.Z
			};
		}

		// Token: 0x06000172 RID: 370 RVA: 0x000119A0 File Offset: 0x0000FBA0
		private static float[] cubicsolve(float a, float b, float c, float d)
		{
			float[] array = null;
			if (a == 0f)
			{
				return array;
			}
			if (d == 0f)
			{
				return array;
			}
			b /= a;
			c /= a;
			d /= a;
			float num = (3f * c - b * b) / 9f;
			float num2 = -(27f * d) + b * (9f * c - 2f * (b * b));
			num2 /= 54f;
			float num3 = num * num * num + num2 * num2;
			float num4 = b / 3f;
			float num5 = 0.33333334f;
			if (num3 > 0f)
			{
				array = new float[1];
				float num6 = num2 + Operations.sqrt(num3);
				num6 = ((num6 < 0f) ? (-Operations.pow(-num6, num5)) : Operations.pow(num6, num5));
				float num7 = num2 - Operations.sqrt(num3);
				num7 = ((num7 < 0f) ? (-Operations.pow(-num7, num5)) : Operations.pow(num7, num5));
				array[0] = -num4 + num6 + num7;
				return array;
			}
			float num8;
			if (num3 == 0f)
			{
				array = new float[3];
				num8 = ((num2 < 0f) ? (-Operations.pow(-num2, num5)) : Operations.pow(num2, num5));
				array[0] = -num4 + 2f * num8;
				array[1] = -(num8 + num4);
				array[2] = array[1];
				return array;
			}
			num = -num;
			float num9 = num * num * num;
			num9 = Operations.Acos(num2 / Operations.sqrt(num9), 6);
			num8 = 2f * Operations.sqrt(num);
			return new float[]
			{
				-num4 + num8 * Operations.Cos(num9 / 3f, 6),
				-num4 + num8 * Operations.Cos((num9 + 6.2831855f) / 3f, 6),
				-num4 + num8 * Operations.Cos((num9 + 12.566371f) / 3f, 6)
			};
		}

		// Token: 0x06000173 RID: 371 RVA: 0x00011B68 File Offset: 0x0000FD68
		private static float _root3(float x)
		{
			float num = 1f;
			while (x < 1f)
			{
				x *= 8f;
				num *= 0.5f;
			}
			while (x > 8f)
			{
				x *= 0.125f;
				num *= 2f;
			}
			float num2 = 1.5f;
			float num3 = 0.33333334f;
			num2 -= num3 * (num2 - x / (num2 * num2));
			num2 -= num3 * (num2 - x / (num2 * num2));
			num2 -= num3 * (num2 - x / (num2 * num2));
			num2 -= num3 * (num2 - x / (num2 * num2));
			num2 -= num3 * (num2 - x / (num2 * num2));
			num2 -= num3 * (num2 - x / (num2 * num2));
			return num2 * num;
		}

		// Token: 0x06000174 RID: 372 RVA: 0x00011C08 File Offset: 0x0000FE08
		private static float root3(float x)
		{
			if (x > 0f)
			{
				return Operations._root3(x);
			}
			if (x < 0f)
			{
				return -Operations._root3(-x);
			}
			return 0f;
		}

		// Token: 0x06000175 RID: 373 RVA: 0x00011C30 File Offset: 0x0000FE30
		private static int SolveP2(out float[] x, float a, float b)
		{
			x = new float[2];
			float num = 0.25f * a * a - b;
			if (num >= 0f)
			{
				num = Operations.sqrt(num);
				x[0] = 0.5f * a + num;
				x[1] = 0.5f * a - num;
				return 2;
			}
			x[0] = 0.5f * a;
			x[1] = Operations.sqrt(-num);
			return 0;
		}

		// Token: 0x06000176 RID: 374 RVA: 0x00011C94 File Offset: 0x0000FE94
		private static int SolveP3(out float[] x, float a, float b, float c)
		{
			x = new float[3];
			float num = 6.2831855f;
			float num2 = a * a;
			float num3 = (num2 - 3f * b) / 9f;
			float num4 = (a * (2f * num2 - 9f * b) + 27f * c) / 54f;
			float num5 = num4 * num4;
			float num6 = num3 * num3 * num3;
			if (num5 < num6)
			{
				float num7 = num4 / Operations.sqrt(num6);
				if (num7 < -1f)
				{
					num7 = -1f;
				}
				if (num7 > 1f)
				{
					num7 = 1f;
				}
				num7 = Operations.Acos(num7, 6);
				a /= 3f;
				num3 = -2f * Operations.sqrt(num3);
				x[0] = num3 * Operations.Cos(num7 / 3f, 6) - a;
				x[1] = num3 * Operations.Cos((num7 + num) / 3f, 6) - a;
				x[2] = num3 * Operations.Cos((num7 - num) / 3f, 6) - a;
				return 3;
			}
			float num8 = -Operations.root3(Math.Abs(num4) + Operations.sqrt(num5 - num6));
			if (num4 < 0f)
			{
				num8 = -num8;
			}
			float num9 = ((num8 == 0f) ? 0f : (num3 / num8));
			a /= 3f;
			x[0] = num8 + num9 - a;
			x[1] = -0.5f * (num8 + num9) - a;
			x[2] = 0.5f * Operations.sqrt(3f) * (num8 - num9);
			if (Math.Abs(x[2]) < 1E-45f)
			{
				x[2] = x[1];
				return 2;
			}
			return 1;
		}

		// Token: 0x06000177 RID: 375 RVA: 0x00011E24 File Offset: 0x00010024
		public static int GetEigenvalues(Matrix T, out float[] eig)
		{
			eig = null;
			if (Operations.sq(T.M12) + Operations.sq(T.M13) + Operations.sq(T.M23) == 0f)
			{
				eig = new float[3];
				eig[0] = T.M11;
				eig[1] = T.M22;
				eig[2] = T.M33;
				return 3;
			}
			float num = T.M11 + T.M22 + T.M33;
			float num2 = T.M11 * T.M22 + T.M22 * T.M33 + T.M33 * T.M11 - Operations.sq(T.M12) - Operations.sq(T.M13) - Operations.sq(T.M23);
			float num3 = T.Determinant();
			float[] array;
			int num4 = Operations.SolveP3(out array, -num, num2, -num3);
			if (num4 == 1)
			{
				float[] array2 = new float[2];
				array2[0] = array[0];
				eig = array2;
			}
			else if (num4 == 2)
			{
				eig = new float[]
				{
					array[0],
					array[1]
				};
			}
			else if (num4 == 3)
			{
				eig = new float[]
				{
					array[0],
					array[1],
					array[2]
				};
			}
			return num4;
		}

		// Token: 0x06000178 RID: 376 RVA: 0x00011F50 File Offset: 0x00010150
		public static Matrix GetElipseRotationMatrixLocalToGlobal(Microsoft.Xna.Framework.Vector3 P1, Microsoft.Xna.Framework.Vector3 P2, float RotationLocalX)
		{
			Matrix matrix = default(Matrix);
			Microsoft.Xna.Framework.Vector3 vector;
			Microsoft.Xna.Framework.Vector3 vector2;
			Microsoft.Xna.Framework.Vector3 vector3;
			if (P2.X == P1.X && P2.Y == P1.Y)
			{
				vector.X = 0f;
				vector.Y = 0f;
				if (P2.Z > P1.Z)
				{
					vector.Z = 1f;
				}
				else
				{
					vector.Z = -1f;
				}
				vector2.X = 0f;
				vector2.Y = 1f;
				vector2.Z = 0f;
				vector3.X = vector.Y * vector2.Z - vector2.Y * vector.Z;
				vector3.Y = vector.Z * vector2.X - vector2.Z * vector.X;
				vector3.Z = vector.X * vector2.Y - vector2.X * vector.Y;
			}
			else
			{
				float num = (P2 - P1).Length();
				vector.X = (P2.X - P1.X) / num;
				vector.Y = (P2.Y - P1.Y) / num;
				vector.Z = (P2.Z - P1.Z) / num;
				float num2 = (float)Math.Pow(Math.Pow((double)vector.X, 2.0) + Math.Pow((double)vector.Y, 2.0), 0.5);
				vector2.X = -vector.Y / num2;
				vector2.Y = vector.X / num2;
				vector2.Z = 0f;
				vector3.X = vector.Y * vector2.Z - vector2.Y * vector.Z;
				vector3.Y = vector.Z * vector2.X - vector2.Z * vector.X;
				vector3.Z = vector.X * vector2.Y - vector2.X * vector.Y;
			}
			matrix.M11 = vector.X;
			matrix.M12 = vector2.X;
			matrix.M13 = vector3.X;
			matrix.M14 = 0f;
			matrix.M21 = vector.Y;
			matrix.M22 = vector2.Y;
			matrix.M23 = vector3.Y;
			matrix.M24 = 0f;
			matrix.M31 = vector.Z;
			matrix.M32 = vector2.Z;
			matrix.M33 = vector3.Z;
			matrix.M34 = 0f;
			matrix.M41 = 0f;
			matrix.M42 = 0f;
			matrix.M43 = 0f;
			matrix.M44 = 1f;
			matrix.M14 = 0.5f * (P1.X + P2.X);
			matrix.M24 = 0.5f * (P1.Y + P2.Y);
			matrix.M34 = 0.5f * (P1.Z + P2.Z);
			return matrix;
		}

		// Token: 0x06000179 RID: 377 RVA: 0x00012294 File Offset: 0x00010494
		public static void GetAverageVersor(ref Microsoft.Xna.Framework.Vector3 n1, Microsoft.Xna.Framework.Vector3 n2)
		{
			float num = 1f;
			if (n1.X * n2.X + n1.Y * n2.Y + n1.Z * n2.Z < 0f)
			{
				num *= -1f;
			}
			n1 += num * n2;
			n1.Normalize();
		}

		// Token: 0x0600017A RID: 378 RVA: 0x00012300 File Offset: 0x00010500
		public static Microsoft.Xna.Framework.Vector3 GetAverageVersor(Microsoft.Xna.Framework.Vector3 n1, Microsoft.Xna.Framework.Vector3 n2)
		{
			Microsoft.Xna.Framework.Vector3 vector = new Microsoft.Xna.Framework.Vector3(n1.X, n1.Y, n1.Z);
			float num = 1f;
			if (n1.X * n2.X + n1.Y * n2.Y + n1.Z * n2.Z < 0f)
			{
				num *= -1f;
			}
			vector += num * n2;
			vector.Normalize();
			return vector;
		}

		// Token: 0x0600017B RID: 379 RVA: 0x0001237C File Offset: 0x0001057C
		public static Microsoft.Xna.Framework.Vector3 GetVersorByTwoPoints(Microsoft.Xna.Framework.Vector3 p1, Microsoft.Xna.Framework.Vector3 p2)
		{
			Microsoft.Xna.Framework.Vector3 vector = p2 - p1;
			vector.Normalize();
			return vector;
		}

		// Token: 0x0600017C RID: 380 RVA: 0x0001239C File Offset: 0x0001059C
		public static Matrix MatriceRotoTraslazioneDeformazione(float angleX, float angleY, float angleZ, float posX, float posY, float posZ, float scalaX = 1f, float scalaY = 1f, float scalaZ = 1f)
		{
			Matrix matrix = default(Matrix);
			float num = Operations.Cos(angleX * 0.017453292f, 6);
			float num2 = Operations.Cos(angleY * 0.017453292f, 6);
			float num3 = Operations.Cos(angleZ * 0.017453292f, 6);
			float num4 = Operations.Sin(angleX * 0.017453292f, 6);
			float num5 = Operations.Sin(angleY * 0.017453292f, 6);
			float num6 = Operations.Sin(angleZ * 0.017453292f, 6);
			matrix.M11 = scalaX * num2 * num3;
			matrix.M12 = scalaX * num2 * num6;
			matrix.M13 = -(scalaX * num5);
			matrix.M21 = -(scalaY * num * num6) + scalaY * num4 * num5 * num3;
			matrix.M22 = scalaY * num * num3 + scalaY * num4 * num5 * num6;
			matrix.M23 = scalaY * num4 * num2;
			matrix.M31 = scalaZ * num4 * num6 + scalaZ * num * num5 * num3;
			matrix.M32 = -(scalaZ * num4 * num3) + scalaZ * num * num5 * num6;
			matrix.M33 = scalaZ * num * num2;
			matrix.M41 = posX;
			matrix.M42 = posY;
			matrix.M43 = posZ;
			matrix.M44 = 1f;
			return matrix;
		}

		// Token: 0x0600017D RID: 381 RVA: 0x000124D4 File Offset: 0x000106D4
		public static double Interpola(List<double> Valori_x, List<double> Valori_y, double X, bool CheckLimits = true)
		{
			if (Valori_x.Count != Valori_y.Count)
			{
				Logger.Log(string.Concat(new string[]
				{
					"Error 100 in Operations>Interpola: (numero elementi x = ",
					Valori_x.Count.ToString(),
					") __ (numero elementi y=",
					Valori_y.Count.ToString(),
					")"
				}), DebugLevel.CRITICAL);
				return 0.0;
			}
			int count = Valori_x.Count;
			if (CheckLimits)
			{
				if (X <= Valori_x[0])
				{
					return Valori_y[0];
				}
				if (X >= Valori_x[count - 1])
				{
					return Valori_y[count - 1];
				}
			}
			int num = 0;
			double num2 = Valori_x[num];
			double num3 = Valori_x[num + 1] - Valori_x[num];
			while ((X - num2 >= num3) & (num < count - 1))
			{
				num++;
				num2 = Valori_x[num];
				if (num < count - 1)
				{
					num3 = Valori_x[num + 1] - Valori_x[num];
				}
			}
			int num4 = count - 1;
			double num5 = Valori_x[num4];
			num3 = Valori_x[num4] - Valori_x[num4 - 1];
			while ((num5 - X >= num3) & (num4 > 0))
			{
				num4--;
				num5 = Valori_x[num4];
				if (num4 > 0)
				{
					num3 = Valori_x[num4] - Valori_x[num4 - 1];
				}
			}
			num4 = Math.Min(num + 1, num4);
			if (num4 > num)
			{
				double num6 = Valori_y[num4] - Valori_y[num];
				num3 = Valori_x[num4] - Valori_x[num];
				double num7 = num6 / num3;
				return Valori_y[num] + num7 * (X - Valori_x[num]);
			}
			if (num4 == num || Valori_x[num4] == Valori_x[num])
			{
				return Valori_y[num];
			}
			Logger.Log("Error 200 in Operations>Interpola: jj=" + num4.ToString() + "<ii=" + num.ToString(), DebugLevel.CRITICAL);
			return Valori_y[num];
		}

		// Token: 0x0600017E RID: 382 RVA: 0x000126B8 File Offset: 0x000108B8
		public static double Interpola(double[] Valori_x, double[] Valori_y, double X, bool CheckLimits = true)
		{
			if (Valori_x.Length != Valori_y.Length)
			{
				Logger.Log(string.Concat(new string[]
				{
					"Error 100 in Operations>Interpola: (numero elementi x = ",
					Valori_x.Length.ToString(),
					") __ (numero elementi y=",
					Valori_y.Length.ToString(),
					")"
				}), DebugLevel.CRITICAL);
				return 0.0;
			}
			int num = Valori_x.Length;
			if (CheckLimits)
			{
				if (X <= Valori_x[0])
				{
					return Valori_y[0];
				}
				if (X >= Valori_x[num - 1])
				{
					return Valori_y[num - 1];
				}
			}
			int num2 = 0;
			double num3 = Valori_x[num2];
			double num4 = Valori_x[num2 + 1] - Valori_x[num2];
			while ((X - num3 >= num4) & (num2 < num - 1))
			{
				num2++;
				num3 = Valori_x[num2];
				if (num2 < num - 1)
				{
					num4 = Valori_x[num2 + 1] - Valori_x[num2];
				}
			}
			int num5 = num - 1;
			double num6 = Valori_x[num5];
			num4 = Valori_x[num5] - Valori_x[num5 - 1];
			while ((num6 - X >= num4) & (num5 > 0))
			{
				num5--;
				num6 = Valori_x[num5];
				if (num5 > 0)
				{
					num4 = Valori_x[num5] - Valori_x[num5 - 1];
				}
			}
			if (num5 > num2)
			{
				double num7 = Valori_y[num5] - Valori_y[num2];
				num4 = Valori_x[num5] - Valori_x[num2];
				double num8 = num7 / num4;
				return Valori_y[num2] + num8 * (X - Valori_x[num2]);
			}
			if (num5 == num2 || Valori_x[num5] == Valori_x[num2])
			{
				return Valori_y[num2];
			}
			Logger.Log("Error 200 in Operations>Interpola: jj=" + num5.ToString() + "<ii=" + num2.ToString(), DebugLevel.CRITICAL);
			return Valori_y[num2];
		}

		// Token: 0x0600017F RID: 383 RVA: 0x0001281C File Offset: 0x00010A1C
		public static float Interpola(float[] Valori_x, float[] Valori_y, float X)
		{
			if (Valori_x.Length != Valori_y.Length)
			{
				Logger.Log(string.Concat(new string[]
				{
					"Error 100 in Operations>Interpola: (numero elementi x = ",
					Valori_x.Length.ToString(),
					") __ (numero elementi y=",
					Valori_y.Length.ToString(),
					")"
				}), DebugLevel.CRITICAL);
				return 0f;
			}
			int num = Valori_x.Length;
			if (X <= Valori_x[0])
			{
				return Valori_y[0];
			}
			if (X >= Valori_x[num - 1])
			{
				return Valori_y[num - 1];
			}
			int num2 = 0;
			float num3 = Valori_x[num2];
			float num4 = Valori_x[num2 + 1] - Valori_x[num2];
			while ((X - num3 >= num4) & (num2 < num - 1))
			{
				num2++;
				num3 = Valori_x[num2];
				if (num2 < num - 1)
				{
					num4 = Valori_x[num2 + 1] - Valori_x[num2];
				}
			}
			int num5 = num - 1;
			float num6 = Valori_x[num5];
			num4 = Valori_x[num5] - Valori_x[num5 - 1];
			while ((num6 - X >= num4) & (num5 > 0))
			{
				num5--;
				num6 = Valori_x[num5];
				if (num5 > 0)
				{
					num4 = Valori_x[num5] - Valori_x[num5 - 1];
				}
			}
			if (num5 > num2)
			{
				float num7 = Valori_y[num5] - Valori_y[num2];
				num4 = Valori_x[num5] - Valori_x[num2];
				float num8 = num7 / num4;
				return Valori_y[num2] + num8 * (X - Valori_x[num2]);
			}
			if (num5 == num2 || Valori_x[num5] == Valori_x[num2])
			{
				return Valori_y[num2];
			}
			Logger.Log("Error 200 in Operations>Interpola: jj=" + num5.ToString() + "<ii=" + num2.ToString(), DebugLevel.CRITICAL);
			return Valori_y[num2];
		}

		// Token: 0x06000180 RID: 384 RVA: 0x00012978 File Offset: 0x00010B78
		public static float InterpolaLog(float[] Valori_x, float[] Valori_y, float X)
		{
			if (Valori_x.Length != Valori_y.Length)
			{
				Logger.Log(string.Concat(new string[]
				{
					"Error 100 in Operations>Interpola: (numero elementi x = ",
					Valori_x.Length.ToString(),
					") __ (numero elementi y=",
					Valori_y.Length.ToString(),
					")"
				}), DebugLevel.CRITICAL);
				return 0f;
			}
			int num = Valori_x.Length;
			if (X <= Valori_x[0])
			{
				return Valori_y[0];
			}
			if (X >= Valori_x[num - 1])
			{
				return Valori_y[num - 1];
			}
			for (int i = 0; i < Valori_x.Length; i++)
			{
				if (Valori_x[i] == X)
				{
					return Valori_y[i];
				}
			}
			int num2 = 0;
			float num3 = Valori_x[num2];
			float num4 = Valori_x[num2 + 1] - Valori_x[num2];
			while ((X - num3 >= num4) & (num2 < num - 1))
			{
				num2++;
				num3 = Valori_x[num2];
				if (num2 < num - 1)
				{
					num4 = Valori_x[num2 + 1] - Valori_x[num2];
				}
			}
			int num5 = num - 1;
			float num6 = Valori_x[num5];
			num4 = Valori_x[num5] - Valori_x[num5 - 1];
			while ((num6 - X >= num4) & (num5 > 0))
			{
				num5--;
				num6 = Valori_x[num5];
				if (num5 > 0)
				{
					num4 = Valori_x[num5] - Valori_x[num5 - 1];
				}
			}
			if (num5 > num2)
			{
				float num7 = Operations.LogP(Valori_y[num2], Valori_y[num5], Valori_x[num2], Valori_x[num5], X);
				return Operations.pow(10f, num7);
			}
			if (num5 == num2 || Valori_x[num5] == Valori_x[num2])
			{
				return Valori_y[num2];
			}
			Logger.Log("Error 200 in Operations>Interpola: jj=" + num5.ToString() + "<ii=" + num2.ToString(), DebugLevel.CRITICAL);
			return Valori_y[num2];
		}

		// Token: 0x06000181 RID: 385 RVA: 0x00012AEF File Offset: 0x00010CEF
		private static float LogP(float p1, float p2, float Tr1, float Tr2, float Tr)
		{
			return (float)(Math.Log10((double)p1) + Math.Log10((double)p2 / (double)p1) * Math.Log10((double)Tr / (double)Tr1) / Math.Log10((double)Tr2 / (double)Tr1));
		}

		// Token: 0x06000182 RID: 386 RVA: 0x00012B1C File Offset: 0x00010D1C
		public static Microsoft.Xna.Framework.Vector4 GetPlane(Microsoft.Xna.Framework.Vector3 Point1, Microsoft.Xna.Framework.Vector3 Point2, Microsoft.Xna.Framework.Vector3 Point3)
		{
			Microsoft.Xna.Framework.Vector3 vector = Microsoft.Xna.Framework.Vector3.Cross(Point2 - Point1, Point3 - Point1);
			vector.Normalize();
			return new Microsoft.Xna.Framework.Vector4(vector.X, vector.Y, vector.Z, -vector.X * Point1.X - vector.Y * Point1.Y - vector.Z * Point1.Z);
		}

		// Token: 0x06000183 RID: 387 RVA: 0x00012B88 File Offset: 0x00010D88
		public static Microsoft.Xna.Framework.Vector4 GetPlane(Microsoft.Xna.Framework.Vector3 Point, Microsoft.Xna.Framework.Vector3 Normal)
		{
			return new Microsoft.Xna.Framework.Vector4(Normal.X, Normal.Y, Normal.Z, -Normal.X * Point.X - Normal.Y * Point.Y - Normal.Z * Point.Z);
		}

		// Token: 0x06000184 RID: 388 RVA: 0x00012BD8 File Offset: 0x00010DD8
		public static bool IsPointInPlane(Microsoft.Xna.Framework.Vector4 Phi, Microsoft.Xna.Framework.Vector3 Point, float toll = -1f)
		{
			if (toll < 0f)
			{
				toll = DefaultValues.TolerancePlane;
			}
			return Math.Abs(Phi.X * Point.X + Phi.Y * Point.Y + Phi.Z * Point.Z + Phi.W) < toll;
		}

		// Token: 0x06000185 RID: 389 RVA: 0x00012C2C File Offset: 0x00010E2C
		public static bool IsPointInPlane(Microsoft.Xna.Framework.Vector4 Phi, Microsoft.Xna.Framework.Vector3 Point, out float toll, out float err)
		{
			toll = DefaultValues.TolerancePlane;
			err = Math.Abs(Phi.X * Point.X + Phi.Y * Point.Y + Phi.Z * Point.Z + Phi.W);
			return err < toll;
		}

		// Token: 0x06000186 RID: 390 RVA: 0x00012C7D File Offset: 0x00010E7D
		public static int[] OrdinaVettore(int[] vettore)
		{
			return vettore.OrderByDescending((int valore) => valore).ToArray<int>();
		}

		// Token: 0x06000187 RID: 391 RVA: 0x00012CAC File Offset: 0x00010EAC
		public static double Area(double X1, double Y1, double X2, double Y2, double X3, double Y3, double X4, double Y4, bool IsAbsoluteValue = true)
		{
			double num = 0.5 * ((X4 - X2) * (Y1 - Y3) + (X1 - X3) * (Y2 - Y4));
			if (IsAbsoluteValue)
			{
				return Math.Abs(num);
			}
			return num;
		}

		// Token: 0x06000188 RID: 392 RVA: 0x00012CE3 File Offset: 0x00010EE3
		public static float Area_new(Microsoft.Xna.Framework.Vector3[] vertices)
		{
			return Operations.Area(vertices, true);
		}

		// Token: 0x06000189 RID: 393 RVA: 0x00012CEC File Offset: 0x00010EEC
		private static float ComputeArea2D(Microsoft.Xna.Framework.Vector2[] vertices)
		{
			float num = 0f;
			int num2 = vertices.Length;
			for (int i = 0; i < num2; i++)
			{
				Microsoft.Xna.Framework.Vector2 vector = vertices[i];
				Microsoft.Xna.Framework.Vector2 vector2 = vertices[(i + 1) % num2];
				num += vector.X * vector2.Y - vector2.X * vector.Y;
			}
			return Math.Abs(num) * 0.5f;
		}

		// Token: 0x0600018A RID: 394 RVA: 0x00012D50 File Offset: 0x00010F50
		private static Microsoft.Xna.Framework.Vector3 ComputePolygonNormal(IList<Microsoft.Xna.Framework.Vector3> vertices)
		{
			Microsoft.Xna.Framework.Vector3 zero = Microsoft.Xna.Framework.Vector3.Zero;
			int count = vertices.Count;
			for (int i = 0; i < count; i++)
			{
				Microsoft.Xna.Framework.Vector3 vector = vertices[i];
				Microsoft.Xna.Framework.Vector3 vector2 = vertices[(i + 1) % count];
				zero.X += (vector.Y - vector2.Y) * (vector.Z + vector2.Z);
				zero.Y += (vector.Z - vector2.Z) * (vector.X + vector2.X);
				zero.Z += (vector.X - vector2.X) * (vector.Y + vector2.Y);
			}
			return Microsoft.Xna.Framework.Vector3.Normalize(zero);
		}

		// Token: 0x0600018B RID: 395 RVA: 0x00012E10 File Offset: 0x00011010
		private static ValueTuple<Microsoft.Xna.Framework.Vector2[], Microsoft.Xna.Framework.Vector3> ProjectTo2D(Microsoft.Xna.Framework.Vector3[] vertices)
		{
			Microsoft.Xna.Framework.Vector3 vector = Operations.ComputePolygonNormal(vertices);
			Microsoft.Xna.Framework.Vector3 vector2 = Microsoft.Xna.Framework.Vector3.UnitZ;
			if ((double)Math.Abs(Microsoft.Xna.Framework.Vector3.Dot(vector, vector2)) > 0.99)
			{
				vector2 = Microsoft.Xna.Framework.Vector3.UnitY;
			}
			Microsoft.Xna.Framework.Vector3 vector3 = Microsoft.Xna.Framework.Vector3.Normalize(Microsoft.Xna.Framework.Vector3.Cross(vector2, vector));
			Microsoft.Xna.Framework.Vector3 vector4 = Microsoft.Xna.Framework.Vector3.Cross(vector, vector3);
			Microsoft.Xna.Framework.Vector3 vector5 = vertices[0];
			Microsoft.Xna.Framework.Vector2[] array = new Microsoft.Xna.Framework.Vector2[vertices.Length];
			for (int i = 0; i < vertices.Length; i++)
			{
				Microsoft.Xna.Framework.Vector3 vector6 = vertices[i] - vector5;
				array[i] = new Microsoft.Xna.Framework.Vector2(Microsoft.Xna.Framework.Vector3.Dot(vector6, vector3), Microsoft.Xna.Framework.Vector3.Dot(vector6, vector4));
			}
			return new ValueTuple<Microsoft.Xna.Framework.Vector2[], Microsoft.Xna.Framework.Vector3>(array, vector5);
		}

		// Token: 0x0600018C RID: 396 RVA: 0x00012EBC File Offset: 0x000110BC
		public static float Area(Microsoft.Xna.Framework.Vector2[] vect2D, bool IsAbsoluteValue = true)
		{
			float num = 0f;
			int num2 = vect2D.Length;
			for (int i = 0; i < num2; i++)
			{
				if (i == num2 - 1)
				{
					num += vect2D[i].X * vect2D[0].Y - vect2D[0].X * vect2D[i].Y;
				}
				else
				{
					num += vect2D[i].X * vect2D[i + 1].Y - vect2D[i + 1].X * vect2D[i].Y;
				}
			}
			num *= 0.5f;
			if (IsAbsoluteValue)
			{
				return Math.Abs(num);
			}
			return num;
		}

		// Token: 0x0600018D RID: 397 RVA: 0x00012F6C File Offset: 0x0001116C
		public static float Area(Microsoft.Xna.Framework.Vector3[] vect3D, bool IsAbsoluteValue = true)
		{
			Microsoft.Xna.Framework.Vector2[] array = new Microsoft.Xna.Framework.Vector2[vect3D.Length];
			for (int i = 0; i < vect3D.Length; i++)
			{
				Operations.ConvertVector3ToVector2(vect3D[0], vect3D[1], vect3D[2], vect3D[i], out array[i]);
			}
			return Operations.Area(array, IsAbsoluteValue);
		}

		// Token: 0x0600018E RID: 398 RVA: 0x00012FBF File Offset: 0x000111BF
		public static float sqrt(float x)
		{
			return (float)Math.Sqrt((double)x);
		}

		// Token: 0x0600018F RID: 399 RVA: 0x00012FC9 File Offset: 0x000111C9
		public static float sq(float x)
		{
			return x * x;
		}

		// Token: 0x06000190 RID: 400 RVA: 0x00012FC9 File Offset: 0x000111C9
		public static double sq(double x)
		{
			return x * x;
		}

		// Token: 0x06000191 RID: 401 RVA: 0x00012FCE File Offset: 0x000111CE
		public static float pow(float x, float n)
		{
			return (float)Math.Pow((double)x, (double)n);
		}

		// Token: 0x06000192 RID: 402 RVA: 0x00012FDA File Offset: 0x000111DA
		public static float Tand(float x)
		{
			return (float)Math.Tan((double)(x * 0.017453292f));
		}

		// Token: 0x06000193 RID: 403 RVA: 0x00012FEA File Offset: 0x000111EA
		public static float Tan(float x)
		{
			return (float)Math.Tan((double)x);
		}

		// Token: 0x06000194 RID: 404 RVA: 0x00012FF4 File Offset: 0x000111F4
		public static float Atan(float x)
		{
			return (float)Math.Atan((double)x);
		}

		// Token: 0x06000195 RID: 405 RVA: 0x00012FFE File Offset: 0x000111FE
		public static float Atand(float x)
		{
			return (float)Math.Atan((double)x) * 57.295776f;
		}

		// Token: 0x06000196 RID: 406 RVA: 0x0001300E File Offset: 0x0001120E
		public static float sign(float x)
		{
			return (float)Math.Sign(x);
		}

		// Token: 0x06000197 RID: 407 RVA: 0x00013017 File Offset: 0x00011217
		public static int Max(params int[] valori)
		{
			return valori.Max();
		}

		// Token: 0x06000198 RID: 408 RVA: 0x0001301F File Offset: 0x0001121F
		public static int Min(params int[] valori)
		{
			return valori.Min();
		}

		// Token: 0x06000199 RID: 409 RVA: 0x00013028 File Offset: 0x00011228
		public static float Max(float[,] Numbers)
		{
			int length = Numbers.GetLength(0);
			int length2 = Numbers.GetLength(1);
			float num = Numbers[0, 0];
			for (int i = 0; i < length; i++)
			{
				for (int j = 0; j < length2; j++)
				{
					if (num < Numbers[i, j])
					{
						num = Numbers[i, j];
					}
				}
			}
			return num;
		}

		// Token: 0x0600019A RID: 410 RVA: 0x00013084 File Offset: 0x00011284
		public static float Min(float[,] Numbers)
		{
			int length = Numbers.GetLength(0);
			int length2 = Numbers.GetLength(1);
			float num = Numbers[0, 0];
			for (int i = 0; i < length; i++)
			{
				for (int j = 0; j < length2; j++)
				{
					if (num > Numbers[i, j])
					{
						num = Numbers[i, j];
					}
				}
			}
			return num;
		}

		// Token: 0x0600019B RID: 411 RVA: 0x000130DD File Offset: 0x000112DD
		public static double Max(double v1, double v2)
		{
			return Math.Max(v1, v2);
		}

		// Token: 0x0600019C RID: 412 RVA: 0x000130E6 File Offset: 0x000112E6
		public static double Min(double v1, double v2)
		{
			return Math.Min(v1, v2);
		}

		// Token: 0x0600019D RID: 413 RVA: 0x000130EF File Offset: 0x000112EF
		public static int Arrotonda(double v)
		{
			if (Math.Abs(v - Math.Floor(v)) > 0.0)
			{
				return (int)(Math.Floor(v) + 1.0);
			}
			return (int)Math.Floor(v);
		}

		// Token: 0x0600019E RID: 414 RVA: 0x00013124 File Offset: 0x00011324
		public static int AlignNodes(Microsoft.Xna.Framework.Vector3 n, Microsoft.Xna.Framework.Vector3 n1, Microsoft.Xna.Framework.Vector3 n2, float toll = -1f)
		{
			float x = n.X;
			float y = n.Y;
			float z = n.Z;
			if (toll == -1f)
			{
				toll = Operations.ToleranceNode;
			}
			if (x - n1.X < toll && n1.X - x < toll && y - n1.Y < toll && n1.Y - y < toll && z - n1.Z < toll && n1.Z - z < toll)
			{
				return 2;
			}
			if (x - n2.X < toll && n2.X - x < toll && y - n2.Y < toll && n2.Y - y < toll && z - n2.Z < toll && n2.Z - z < toll)
			{
				return 3;
			}
			double num = (double)(n2.X - n1.X);
			double num2 = (double)(n2.Y - n1.Y);
			double num3 = (double)(n2.Z - n1.Z);
			double num4 = (double)(x - n1.X);
			double num5 = (double)(y - n1.Y);
			double num6 = (double)(z - n1.Z);
			double num7 = Math.Sqrt(num * num + num2 * num2 + num3 * num3);
			double num8 = Math.Sqrt(num4 * num4 + num5 * num5 + num6 * num6);
			double num9 = (num * num4 + num2 * num5 + num3 * num6) / (num7 * num8);
			if (num9 > 1.0)
			{
				num9 = 1.0;
			}
			if (num9 < -1.0)
			{
				num9 = -1.0;
			}
			double num10 = Math.Sqrt(1.0 - num9 * num9) * num8;
			if (num10 >= (double)toll || num10 <= (double)(-(double)toll))
			{
				return 0;
			}
			if (num9 > 0.0 && num8 <= num7)
			{
				return 1;
			}
			return -1;
		}

		// Token: 0x0600019F RID: 415 RVA: 0x000132DC File Offset: 0x000114DC
		public static int AlignNodes(Microsoft.Xna.Framework.Vector2 n, Microsoft.Xna.Framework.Vector2 n1, Microsoft.Xna.Framework.Vector2 n2, float toll = -1f)
		{
			float x = n.X;
			float y = n.Y;
			if (toll == -1f)
			{
				toll = Operations.ToleranceNode;
			}
			if (x - n1.X < toll && n1.X - x < toll && y - n1.Y < toll && n1.Y - y < toll)
			{
				return 2;
			}
			if (x - n2.X < toll && n2.X - x < toll && y - n2.Y < toll && n2.Y - y < toll)
			{
				return 3;
			}
			double num = (double)(n2.X - n1.X);
			double num2 = (double)(n2.Y - n1.Y);
			double num3 = (double)(x - n1.X);
			double num4 = (double)(y - n1.Y);
			double num5 = Math.Sqrt(num * num + num2 * num2);
			double num6 = Math.Sqrt(num3 * num3 + num4 * num4);
			double num7 = (num * num3 + num2 * num4) / (num5 * num6);
			if (num7 > 1.0)
			{
				num7 = 1.0;
			}
			if (num7 < -1.0)
			{
				num7 = -1.0;
			}
			double num8 = Math.Sqrt(1.0 - num7 * num7) * num6;
			if (num8 >= (double)toll || num8 <= (double)(-(double)toll))
			{
				return 0;
			}
			if (num7 > 0.0 && num6 <= num5)
			{
				return 1;
			}
			return -1;
		}

		// Token: 0x060001A0 RID: 416 RVA: 0x00013430 File Offset: 0x00011630
		public static bool IntersectSegments(Microsoft.Xna.Framework.Vector3 n1, int n1Key, Microsoft.Xna.Framework.Vector3 n2, int n2Key, Microsoft.Xna.Framework.Vector3 n3, int n3Key, Microsoft.Xna.Framework.Vector3 n4, int n4Key, ref Microsoft.Xna.Framework.Vector3 n, ref int nKey, ref Microsoft.Xna.Framework.Vector3 m, ref int mKey)
		{
			bool flag = false;
			bool flag2 = false;
			if (!flag && Operations.AlignNodes(n3, n1, n2, -1f) == 1)
			{
				if (!flag2)
				{
					n = n3;
					nKey = n3Key;
					flag2 = true;
				}
				else
				{
					m = n3;
					mKey = n3Key;
					flag = true;
				}
			}
			if (!flag && Operations.AlignNodes(n4, n1, n2, -1f) == 1)
			{
				if (!flag2)
				{
					n = n4;
					nKey = n4Key;
					flag2 = true;
				}
				else
				{
					m = n4;
					mKey = n4Key;
					flag = true;
				}
			}
			if (!flag && Operations.AlignNodes(n1, n3, n4, -1f) == 1)
			{
				if (!flag2)
				{
					n = n1;
					nKey = n1Key;
					flag2 = true;
				}
				else
				{
					m = n1;
					mKey = n1Key;
					flag = true;
				}
			}
			if (!flag && Operations.AlignNodes(n2, n3, n4, -1f) == 1)
			{
				if (!flag2)
				{
					n = n2;
					nKey = n2Key;
					flag2 = true;
				}
				else
				{
					m = n2;
					mKey = n2Key;
					flag = true;
				}
			}
			if (!flag2)
			{
				if (Operations.AlignNodes(n1, n3, n4, -1f) <= 0)
				{
					return false;
				}
				if (Operations.AlignNodes(n2, n3, n4, -1f) <= 0)
				{
					return false;
				}
				n = n1;
				nKey = n1Key;
				m = n2;
				mKey = n2Key;
				return true;
			}
			else
			{
				if (flag)
				{
					return true;
				}
				if (Operations.AlignNodes(n1, n3, n4, -1f) > 1)
				{
					m = n1;
					mKey = n1Key;
					return true;
				}
				if (Operations.AlignNodes(n2, n3, n4, -1f) > 1)
				{
					m = n2;
					mKey = n2Key;
					return true;
				}
				return false;
			}
		}

		// Token: 0x060001A1 RID: 417 RVA: 0x000135AC File Offset: 0x000117AC
		public static void CheckDistance(ref float? Distance, float? DistanceCurrent)
		{
			if (DistanceCurrent != null)
			{
				if (Distance == null)
				{
					Distance = DistanceCurrent;
					return;
				}
				float? num = Distance;
				float? num2 = DistanceCurrent;
				if ((num.GetValueOrDefault() > num2.GetValueOrDefault()) & ((num != null) & (num2 != null)))
				{
					Distance = DistanceCurrent;
				}
			}
		}

		// Token: 0x060001A2 RID: 418 RVA: 0x00013604 File Offset: 0x00011804
		public static Microsoft.Xna.Framework.Vector2 GetLowerLeft(Microsoft.Xna.Framework.Vector2 v1, Microsoft.Xna.Framework.Vector2 v2, Microsoft.Xna.Framework.Vector2 v3, Microsoft.Xna.Framework.Vector2 v4)
		{
			float x = v1.X;
			float y = v1.Y;
			float x2 = v2.X;
			float y2 = v2.Y;
			float x3 = v3.X;
			float y3 = v3.Y;
			float x4 = v4.X;
			float y4 = v4.Y;
			float num = y;
			float num2 = x;
			int num3 = 1;
			float num4 = y2;
			float num5 = x2;
			int num6 = 2;
			if (y2 < num)
			{
				num4 = num;
				num5 = num2;
				num6 = num3;
				num = y2;
				num2 = x2;
				num3 = 2;
			}
			if (y3 < num)
			{
				num4 = num;
				num5 = num2;
				num6 = num3;
				num = y3;
				num2 = x3;
				num3 = 3;
			}
			else if (y3 < num4)
			{
				num4 = y3;
				num5 = x3;
				num6 = 3;
			}
			if (y4 < num)
			{
				num5 = num2;
				num6 = num3;
				num2 = x4;
				num3 = 4;
			}
			else if (y4 < num4)
			{
				num5 = x4;
				num6 = 4;
			}
			int num7;
			if (num2 < num5)
			{
				num7 = num3;
			}
			else
			{
				num7 = num6;
			}
			switch (num7)
			{
			case 1:
				return v1;
			case 2:
				return v2;
			case 3:
				return v3;
			case 4:
				return v4;
			default:
				return default(Microsoft.Xna.Framework.Vector2);
			}
		}

		// Token: 0x060001A3 RID: 419 RVA: 0x00013708 File Offset: 0x00011908
		public static Microsoft.Xna.Framework.Vector2 GetLowerRight(Microsoft.Xna.Framework.Vector2 v1, Microsoft.Xna.Framework.Vector2 v2, Microsoft.Xna.Framework.Vector2 v3, Microsoft.Xna.Framework.Vector2 v4)
		{
			float x = v1.X;
			float y = v1.Y;
			float x2 = v2.X;
			float y2 = v2.Y;
			float x3 = v3.X;
			float y3 = v3.Y;
			float x4 = v4.X;
			float y4 = v4.Y;
			float num = y;
			float num2 = x;
			int num3 = 1;
			float num4 = y2;
			float num5 = x2;
			int num6 = 2;
			if (y2 < num)
			{
				num4 = num;
				num5 = num2;
				num6 = num3;
				num = y2;
				num2 = x2;
				num3 = 2;
			}
			if (y3 < num)
			{
				num4 = num;
				num5 = num2;
				num6 = num3;
				num = y3;
				num2 = x3;
				num3 = 3;
			}
			else if (y3 < num4)
			{
				num4 = y3;
				num5 = x3;
				num6 = 3;
			}
			if (y4 < num)
			{
				num5 = num2;
				num6 = num3;
				num2 = x4;
				num3 = 4;
			}
			else if (y4 < num4)
			{
				num5 = x4;
				num6 = 4;
			}
			int num7;
			if (num2 >= num5)
			{
				num7 = num3;
			}
			else
			{
				num7 = num6;
			}
			switch (num7)
			{
			case 1:
				return v1;
			case 2:
				return v2;
			case 3:
				return v3;
			case 4:
				return v4;
			default:
				return default(Microsoft.Xna.Framework.Vector2);
			}
		}

		// Token: 0x060001A4 RID: 420 RVA: 0x0001380C File Offset: 0x00011A0C
		public static Microsoft.Xna.Framework.Vector2 GetHigherLeft(Microsoft.Xna.Framework.Vector2 v1, Microsoft.Xna.Framework.Vector2 v2, Microsoft.Xna.Framework.Vector2 v3, Microsoft.Xna.Framework.Vector2 v4)
		{
			float x = v1.X;
			float y = v1.Y;
			float x2 = v2.X;
			float y2 = v2.Y;
			float x3 = v3.X;
			float y3 = v3.Y;
			float x4 = v4.X;
			float y4 = v4.Y;
			float num = y;
			float num2 = x;
			int num3 = 1;
			float num4 = y2;
			float num5 = x2;
			int num6 = 2;
			if (y2 >= num)
			{
				num4 = num;
				num5 = num2;
				num6 = num3;
				num = y2;
				num2 = x2;
				num3 = 2;
			}
			if (y3 >= num)
			{
				num4 = num;
				num5 = num2;
				num6 = num3;
				num = y3;
				num2 = x3;
				num3 = 3;
			}
			else if (y3 >= num4)
			{
				num4 = y3;
				num5 = x3;
				num6 = 3;
			}
			if (y4 >= num)
			{
				num5 = num2;
				num6 = num3;
				num2 = x4;
				num3 = 4;
			}
			else if (y4 >= num4)
			{
				num5 = x4;
				num6 = 4;
			}
			int num7;
			if (num2 < num5)
			{
				num7 = num3;
			}
			else
			{
				num7 = num6;
			}
			switch (num7)
			{
			case 1:
				return v1;
			case 2:
				return v2;
			case 3:
				return v3;
			case 4:
				return v4;
			default:
				return default(Microsoft.Xna.Framework.Vector2);
			}
		}

		// Token: 0x060001A5 RID: 421 RVA: 0x00013910 File Offset: 0x00011B10
		public static Microsoft.Xna.Framework.Vector2 GetHigherRight(Microsoft.Xna.Framework.Vector2 v1, Microsoft.Xna.Framework.Vector2 v2, Microsoft.Xna.Framework.Vector2 v3, Microsoft.Xna.Framework.Vector2 v4)
		{
			float x = v1.X;
			float y = v1.Y;
			float x2 = v2.X;
			float y2 = v2.Y;
			float x3 = v3.X;
			float y3 = v3.Y;
			float x4 = v4.X;
			float y4 = v4.Y;
			float num = y;
			float num2 = x;
			int num3 = 1;
			float num4 = y2;
			float num5 = x2;
			int num6 = 2;
			if (y2 >= num)
			{
				num4 = num;
				num5 = num2;
				num6 = num3;
				num = y2;
				num2 = x2;
				num3 = 2;
			}
			if (y3 >= num)
			{
				num4 = num;
				num5 = num2;
				num6 = num3;
				num = y3;
				num2 = x3;
				num3 = 3;
			}
			else if (y3 >= num4)
			{
				num4 = y3;
				num5 = x3;
				num6 = 3;
			}
			if (y4 >= num)
			{
				num5 = num2;
				num6 = num3;
				num2 = x4;
				num3 = 4;
			}
			else if (y4 >= num4)
			{
				num5 = x4;
				num6 = 4;
			}
			int num7;
			if (num2 >= num5)
			{
				num7 = num3;
			}
			else
			{
				num7 = num6;
			}
			switch (num7)
			{
			case 1:
				return v1;
			case 2:
				return v2;
			case 3:
				return v3;
			case 4:
				return v4;
			default:
				return default(Microsoft.Xna.Framework.Vector2);
			}
		}

		// Token: 0x060001A6 RID: 422 RVA: 0x00013A14 File Offset: 0x00011C14
		public static void GetIntrinsecCoordinates(out float u, out float v, float x, float y, float x1, float y1, float x2, float y2, float x3, float y3, float x4, float y4, float tol)
		{
			Microsoft.Xna.Framework.Vector3 vector = default(Microsoft.Xna.Framework.Vector3);
			Microsoft.Xna.Framework.Vector3 vector2 = default(Microsoft.Xna.Framework.Vector3);
			Microsoft.Xna.Framework.Vector3 vector3 = default(Microsoft.Xna.Framework.Vector3);
			vector3.X = x;
			vector3.Y = y;
			vector3.Z = 0f;
			vector.X = x1;
			vector.Y = y1;
			vector.Z = 0f;
			vector2.X = x4;
			vector2.Y = y4;
			vector2.Z = 0f;
			if (Operations.AlignNodes(vector3, vector, vector2, -1f) > 0)
			{
				u = -1f;
			}
			else
			{
				vector.X = x2;
				vector.Y = y2;
				vector.Z = 0f;
				vector2.X = x3;
				vector2.Y = y3;
				vector2.Z = 0f;
				if (Operations.AlignNodes(vector3, vector, vector2, -1f) > 0)
				{
					u = 1f;
				}
				else
				{
					Operations.FindU(out u, x, y, x1, y1, x2, y2, x3, y3, x4, y4, tol);
				}
			}
			vector.X = x1;
			vector.Y = y1;
			vector.Z = 0f;
			vector2.X = x2;
			vector2.Y = y2;
			vector2.Z = 0f;
			if (Operations.AlignNodes(vector3, vector, vector2, -1f) > 0)
			{
				v = -1f;
				return;
			}
			vector.X = x4;
			vector.Y = y4;
			vector.Z = 0f;
			vector2.X = x3;
			vector2.Y = y3;
			vector2.Z = 0f;
			if (Operations.AlignNodes(vector3, vector, vector2, -1f) > 0)
			{
				v = 1f;
				return;
			}
			Operations.FindV(out v, x, y, x1, y1, x2, y2, x3, y3, x4, y4, tol);
		}

		// Token: 0x060001A7 RID: 423 RVA: 0x00013BDC File Offset: 0x00011DDC
		public static float DistFromPointToLine(Microsoft.Xna.Framework.Vector3 n, Microsoft.Xna.Framework.Vector3 n1, Microsoft.Xna.Framework.Vector3 n2)
		{
			Microsoft.Xna.Framework.Vector3 vector = Microsoft.Xna.Framework.Vector3.Subtract(n, n1);
			Microsoft.Xna.Framework.Vector3.Dot(vector, Microsoft.Xna.Framework.Vector3.Normalize(n2 - n1));
			return Microsoft.Xna.Framework.Vector3.Cross(vector, Microsoft.Xna.Framework.Vector3.Normalize(n2 - n1)).Length();
		}

		// Token: 0x060001A8 RID: 424 RVA: 0x00013C1C File Offset: 0x00011E1C
		public static void FindU(out float u, float x, float y, float x1, float y1, float x2, float y2, float x3, float y3, float x4, float y4, float tol)
		{
			float num = (x3 + x4) / 2f;
			float num2 = (y3 + y4) / 2f;
			float num3 = (x1 + x2) / 2f;
			float num4 = (y1 + y2) / 2f;
			List<Microsoft.Xna.Framework.Vector2> list = new List<Microsoft.Xna.Framework.Vector2>();
			Microsoft.Xna.Framework.Vector2 vector = new Microsoft.Xna.Framework.Vector2(x, y);
			Microsoft.Xna.Framework.Vector2 vector2 = default(Microsoft.Xna.Framework.Vector2);
			u = 0f;
			float num5 = -1f;
			float num6 = 1f;
			bool flag = false;
			vector2 = new Microsoft.Xna.Framework.Vector2(x1, y1);
			list.Add(vector2);
			vector2 = new Microsoft.Xna.Framework.Vector2(x2, y2);
			list.Add(vector2);
			vector2 = new Microsoft.Xna.Framework.Vector2(x3, y3);
			list.Add(vector2);
			vector2 = new Microsoft.Xna.Framework.Vector2(x4, y4);
			list.Add(vector2);
			if (!Operations.puntoInternoAPoligono(list, vector))
			{
				flag = true;
			}
			int num7 = 0;
			int num8 = 1000;
			while (!flag)
			{
				num7++;
				if (num7 > num8)
				{
					Logger.Log("Error in InterfaceOperations>FindU: Solution not found", DebugLevel.CRITICAL);
					flag = true;
				}
				if (num6 - num5 < tol)
				{
					flag = true;
				}
				else
				{
					list.Clear();
					vector2 = new Microsoft.Xna.Framework.Vector2(x1, y1);
					list.Add(vector2);
					vector2 = new Microsoft.Xna.Framework.Vector2(num3, num4);
					list.Add(vector2);
					vector2 = new Microsoft.Xna.Framework.Vector2(num, num2);
					list.Add(vector2);
					vector2 = new Microsoft.Xna.Framework.Vector2(x4, y4);
					list.Add(vector2);
					if (Operations.puntoInternoAPoligono(list, vector))
					{
						num6 = u;
						u = (num5 + u) / 2f;
					}
					else
					{
						num5 = u;
						u = (num6 + u) / 2f;
					}
					num3 = x1 * (1f - u) / 2f + x2 * (1f + u) / 2f;
					num4 = y1 * (1f - u) / 2f + y2 * (1f + u) / 2f;
					num = x3 * (1f + u) / 2f + x4 * (1f - u) / 2f;
					num2 = y3 * (1f + u) / 2f + y4 * (1f - u) / 2f;
				}
			}
		}

		// Token: 0x060001A9 RID: 425 RVA: 0x00013E38 File Offset: 0x00012038
		public static void FindV(out float v, float x, float y, float x1, float y1, float x2, float y2, float x3, float y3, float x4, float y4, float tol)
		{
			float num = (x3 + x2) / 2f;
			float num2 = (y3 + y2) / 2f;
			float num3 = (x1 + x4) / 2f;
			float num4 = (y1 + y4) / 2f;
			List<Microsoft.Xna.Framework.Vector2> list = new List<Microsoft.Xna.Framework.Vector2>();
			Microsoft.Xna.Framework.Vector2 vector = new Microsoft.Xna.Framework.Vector2(x, y);
			Microsoft.Xna.Framework.Vector2 vector2 = default(Microsoft.Xna.Framework.Vector2);
			v = 0f;
			float num5 = -1f;
			float num6 = 1f;
			bool flag = false;
			vector2 = new Microsoft.Xna.Framework.Vector2(x1, y1);
			list.Add(vector2);
			vector2 = new Microsoft.Xna.Framework.Vector2(x2, y2);
			list.Add(vector2);
			vector2 = new Microsoft.Xna.Framework.Vector2(x3, y3);
			list.Add(vector2);
			vector2 = new Microsoft.Xna.Framework.Vector2(x4, y4);
			list.Add(vector2);
			if (!Operations.puntoInternoAPoligono(list, vector))
			{
				flag = true;
			}
			int num7 = 0;
			int num8 = 1000;
			while (!flag)
			{
				num7++;
				if (num7 > num8)
				{
					Logger.Log("Error in InterfaceOperations>FindV: Solution not found", DebugLevel.CRITICAL);
					flag = true;
				}
				if (num6 - num5 < tol)
				{
					flag = true;
				}
				else
				{
					list.Clear();
					vector2 = new Microsoft.Xna.Framework.Vector2(x1, y1);
					list.Add(vector2);
					vector2 = new Microsoft.Xna.Framework.Vector2(x2, y2);
					list.Add(vector2);
					vector2 = new Microsoft.Xna.Framework.Vector2(num, num2);
					list.Add(vector2);
					vector2 = new Microsoft.Xna.Framework.Vector2(num3, num4);
					list.Add(vector2);
					if (Operations.puntoInternoAPoligono(list, vector))
					{
						num6 = v;
						v = (num5 + v) / 2f;
					}
					else
					{
						num5 = v;
						v = (num6 + v) / 2f;
					}
					num3 = x1 * (1f - v) / 2f + x4 * (1f + v) / 2f;
					num4 = y1 * (1f - v) / 2f + y4 * (1f + v) / 2f;
					num = x2 * (1f - v) / 2f + x3 * (1f + v) / 2f;
					num2 = y2 * (1f - v) / 2f + y3 * (1f + v) / 2f;
				}
			}
		}

		// Token: 0x060001AA RID: 426 RVA: 0x00014054 File Offset: 0x00012254
		public static void GetIntrinsecCoordinates(out float u, out float v, Microsoft.Xna.Framework.Vector3[] VInt, Microsoft.Xna.Framework.Vector3 point, float tol = 0.001f)
		{
			Microsoft.Xna.Framework.Vector2 vector = default(Microsoft.Xna.Framework.Vector2);
			Microsoft.Xna.Framework.Vector2[] array = new Microsoft.Xna.Framework.Vector2[VInt.Length];
			u = (v = 0f);
			if (VInt.Length == 4)
			{
				for (int i = 0; i < VInt.Length; i++)
				{
					Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[3], VInt[i], out array[i]);
				}
				Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[3], point, out vector);
				Operations.GetIntrinsecCoordinates(out u, out v, vector.X, vector.Y, array[0].X, array[0].Y, array[1].X, array[1].Y, array[2].X, array[2].Y, array[3].X, array[3].Y, tol);
			}
			else if (VInt.Length == 3)
			{
				for (int j = 0; j < VInt.Length; j++)
				{
					Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[2], VInt[j], out array[j]);
				}
				Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[2], point, out vector);
				Operations.GetIntrinsecCoordinates(out u, out v, vector.X, vector.Y, array[0].X, array[0].Y, array[1].X, array[1].Y, array[2].X, array[2].Y, array[2].X, array[2].Y, tol);
			}
		}

		// Token: 0x060001AB RID: 427 RVA: 0x00014230 File Offset: 0x00012430
		public static void GetIntrinsecCoordinates_new(out float[] u, out float[] v, Microsoft.Xna.Framework.Vector3[] VInt, Microsoft.Xna.Framework.Vector3[] points, float toll = -1f)
		{
			if (toll == -1f)
			{
				toll = 1E-08f * Operations.ToleranceNode;
			}
			u = new float[points.Length];
			v = new float[points.Length];
			Microsoft.Xna.Framework.Vector3 vector = VInt[0];
			Microsoft.Xna.Framework.Vector3 vector2 = VInt[1];
			Microsoft.Xna.Framework.Vector3 vector3 = VInt[2];
			Microsoft.Xna.Framework.Vector3 vector4 = VInt[3];
			for (int i = 0; i < points.Length; i++)
			{
				Microsoft.Xna.Framework.Vector3 vector5 = points[i];
				float num = 0f;
				float num2 = 0f;
				int num3 = 100;
				for (int j = 0; j < num3; j++)
				{
					float num4 = (num + 1f) * 0.5f;
					float num5 = (num2 + 1f) * 0.5f;
					Microsoft.Xna.Framework.Vector3 vector6 = (1f - num4) * (1f - num5) * vector + num4 * (1f - num5) * vector2 + num4 * num5 * vector3 + (1f - num4) * num5 * vector4;
					Microsoft.Xna.Framework.Vector3 vector7 = vector5 - vector6;
					if (vector7.LengthSquared() < toll * toll)
					{
						break;
					}
					Microsoft.Xna.Framework.Vector3 vector8 = -0.5f * (1f - num5) * vector + 0.5f * (1f - num5) * vector2 + 0.5f * num5 * vector3 - 0.5f * num5 * vector4;
					Microsoft.Xna.Framework.Vector3 vector9 = -0.5f * (1f - num4) * vector - 0.5f * num4 * vector2 + 0.5f * num4 * vector3 + 0.5f * (1f - num4) * vector4;
					float num6 = vector8.LengthSquared() + vector9.LengthSquared();
					if (num6 < 1E-20f)
					{
						break;
					}
					float num7 = Microsoft.Xna.Framework.Vector3.Dot(vector7, vector8) / num6;
					float num8 = Microsoft.Xna.Framework.Vector3.Dot(vector7, vector9) / num6;
					num += num7;
					num2 += num8;
					num = Math.Max(-1f, Math.Min(1f, num));
					num2 = Math.Max(-1f, Math.Min(1f, num2));
				}
				u[i] = num;
				v[i] = num2;
			}
		}

		// Token: 0x060001AC RID: 428 RVA: 0x00014490 File Offset: 0x00012690
		public static void AlignV2ToV1(Microsoft.Xna.Framework.Vector3[] V1, ref Microsoft.Xna.Framework.Vector3[] V2)
		{
			if (V1.Length != 4 || V2.Length != 4)
			{
				throw new ArgumentException("Entrambi gli array devono contenere esattamente 4 vertici.");
			}
			Microsoft.Xna.Framework.Vector3[] array = null;
			float num = float.MaxValue;
			Microsoft.Xna.Framework.Vector3[] V2Local = V2;
			Func<int, Microsoft.Xna.Framework.Vector3> __9__0 = null;
			foreach (int[] enumerable in new int[][]
			{
				new int[] { 0, 1, 2, 3 },
				new int[] { 1, 2, 3, 0 },
				new int[] { 2, 3, 0, 1 },
				new int[] { 3, 0, 1, 2 },
				new int[] { 3, 2, 1, 0 },
				new int[] { 2, 1, 0, 3 },
				new int[] { 1, 0, 3, 2 },
				new int[] { 0, 3, 2, 1 }
			})
			{
				Func<int, Microsoft.Xna.Framework.Vector3> func;
				if ((func = __9__0) == null)
				{
					func = (__9__0 = (int idx) => V2Local[idx]);
				}
				Microsoft.Xna.Framework.Vector3[] array3 = enumerable.Select(func).ToArray<Microsoft.Xna.Framework.Vector3>();
				float num2 = 0f;
				for (int j = 0; j < 4; j++)
				{
					num2 += Microsoft.Xna.Framework.Vector3.DistanceSquared(V1[j], array3[j]);
				}
				if (num2 < num)
				{
					num = num2;
					array = array3;
				}
			}
			if (array != null)
			{
				V2 = array;
			}
		}

		// Token: 0x060001AD RID: 429 RVA: 0x000145F8 File Offset: 0x000127F8
		public static void GetIntrinsecCoordinates(out float[] u, out float[] v, Microsoft.Xna.Framework.Vector3[] VInt, Microsoft.Xna.Framework.Vector3[] points, float toll = -1f)
		{
			u = new float[points.Length];
			v = new float[points.Length];
			Microsoft.Xna.Framework.Vector2[] array = new Microsoft.Xna.Framework.Vector2[4];
			Microsoft.Xna.Framework.Vector2[] array2 = new Microsoft.Xna.Framework.Vector2[4];
			if (toll == -1f)
			{
				toll = 1E-08f * Operations.ToleranceNode;
			}
			bool flag = true;
			for (int i = 0; i < 4; i++)
			{
				if (i < 3)
				{
					flag &= (VInt[i] - VInt[i + 1]).Length() > toll;
				}
				else
				{
					flag &= (VInt[i] - VInt[0]).Length() > toll;
				}
			}
			if (flag)
			{
				for (int j = 0; j < 4; j++)
				{
					Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[3], VInt[j], out array2[j]);
					Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[3], points[j], out array[j]);
				}
				Microsoft.Xna.Framework.Vector2 vector = default(Microsoft.Xna.Framework.Vector2);
				Operations.FindIntersectionBetweenSegments(array2[0], array2[1], array[0], array[3], out vector);
				float num = Microsoft.Xna.Framework.Vector2.Distance(array2[0], vector);
				u[0] = -1f + 2f * num / Microsoft.Xna.Framework.Vector2.Distance(array2[0], array2[1]);
				u[3] = u[0];
				Operations.FindIntersectionBetweenSegments(array2[0], array2[1], array[1], array[2], out vector);
				num = Microsoft.Xna.Framework.Vector2.Distance(array2[0], vector);
				u[1] = -1f + 2f * num / Microsoft.Xna.Framework.Vector2.Distance(array2[0], array2[1]);
				u[2] = u[1];
				Operations.FindIntersectionBetweenSegments(array2[0], array2[3], array[0], array[1], out vector);
				num = Microsoft.Xna.Framework.Vector2.Distance(array2[0], vector);
				v[0] = -1f + 2f * num / Microsoft.Xna.Framework.Vector2.Distance(array2[0], array2[3]);
				v[1] = v[0];
				Operations.FindIntersectionBetweenSegments(array2[0], array2[3], array[2], array[3], out vector);
				num = Microsoft.Xna.Framework.Vector2.Distance(array2[0], vector);
				v[2] = -1f + 2f * num / Microsoft.Xna.Framework.Vector2.Distance(array2[0], array2[3]);
				v[3] = v[2];
			}
			else
			{
				if ((VInt[0] - VInt[3]).Length() < toll)
				{
					for (int k = 0; k < 4; k++)
					{
						Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[2], VInt[k], out array2[k]);
						Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[2], points[k], out array[k]);
					}
				}
				else
				{
					for (int l = 0; l < 4; l++)
					{
						Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[3], VInt[l], out array2[l]);
						Operations.ConvertVector3ToVector2(VInt[0], VInt[1], VInt[3], points[l], out array[l]);
					}
				}
				Microsoft.Xna.Framework.Vector2 vector2 = default(Microsoft.Xna.Framework.Vector2);
				if (Operations.FindIntersectionBetweenSegments(array2[0], array2[1], array[0], array[3], out vector2))
				{
					float num = Microsoft.Xna.Framework.Vector2.Distance(array2[0], vector2);
					u[0] = -1f + 2f * num / Microsoft.Xna.Framework.Vector2.Distance(array2[0], array2[1]);
					u[3] = u[0];
				}
				else
				{
					Logger.Log(string.Concat(new string[]
					{
						"Error 100 in GetIntrinsecCoordinates: unable to find intersection point, p1:{",
						array2[0].ToString(),
						"}; p2:{",
						array2[1].ToString(),
						"}; p3:{",
						array[0].ToString(),
						"}; p4:{",
						array[3].ToString(),
						"}"
					}), DebugLevel.CRITICAL);
				}
				if (Operations.FindIntersectionBetweenSegments(array2[0], array2[1], array[1], array[2], out vector2))
				{
					float num = Microsoft.Xna.Framework.Vector2.Distance(array2[0], vector2);
					u[1] = -1f + 2f * num / Microsoft.Xna.Framework.Vector2.Distance(array2[0], array2[1]);
					u[2] = u[1];
				}
				else
				{
					Logger.Log(string.Concat(new string[]
					{
						"Error 200 in GetIntrinsecCoordinates: unable to find intersection point, p1:{",
						array2[0].ToString(),
						"}; p2:{",
						array2[1].ToString(),
						"}; p3:{",
						array[1].ToString(),
						"}; p4:{",
						array[2].ToString(),
						"}"
					}), DebugLevel.CRITICAL);
				}
				float num2 = (array2[0] - array2[3]).Length();
				if (num2 > toll)
				{
					if (Operations.FindIntersectionBetweenSegments(array2[0], array2[3], array[0], array[1], out vector2))
					{
						float num = Microsoft.Xna.Framework.Vector2.Distance(array2[0], vector2);
						v[0] = -1f + 2f * num / num2;
						v[1] = v[0];
					}
					else
					{
						Logger.Log(string.Concat(new string[]
						{
							"Error 300 in GetIntrinsecCoordinates: unable to find intersection point, p1:{",
							array2[0].ToString(),
							"}; p2:{",
							array2[3].ToString(),
							"}; p3:{",
							array[0].ToString(),
							"}; p4:{",
							array[1].ToString(),
							"}"
						}), DebugLevel.CRITICAL);
					}
					if (Operations.FindIntersectionBetweenSegments(array2[0], array2[3], array[2], array[3], out vector2))
					{
						float num = Microsoft.Xna.Framework.Vector2.Distance(array2[0], vector2);
						v[2] = -1f + 2f * num / num2;
						v[3] = v[2];
					}
					else
					{
						Logger.Log(string.Concat(new string[]
						{
							"Error 400 in GetIntrinsecCoordinates: unable to find intersection point, p1:{",
							array2[0].ToString(),
							"}; p2:{",
							array2[3].ToString(),
							"}; p3:{",
							array[2].ToString(),
							"}; p4:{",
							array[3].ToString(),
							"}"
						}), DebugLevel.CRITICAL);
					}
				}
				else
				{
					num2 = (array2[1] - array2[2]).Length();
					if (num2 > toll)
					{
						if (Operations.FindIntersectionBetweenSegments(array2[1], array2[2], array[0], array[1], out vector2))
						{
							float num = Microsoft.Xna.Framework.Vector2.Distance(array2[1], vector2);
							v[0] = -1f + 2f * num / num2;
							v[1] = v[0];
						}
						else
						{
							Logger.Log(string.Concat(new string[]
							{
								"Error 500 in GetIntrinsecCoordinates: unable to find intersection point, p1:{",
								array2[1].ToString(),
								"}; p2:{",
								array2[2].ToString(),
								"}; p3:{",
								array[0].ToString(),
								"}; p4:{",
								array[1].ToString(),
								"}"
							}), DebugLevel.CRITICAL);
						}
						if (Operations.FindIntersectionBetweenSegments(array2[1], array2[2], array[2], array[3], out vector2))
						{
							float num = Microsoft.Xna.Framework.Vector2.Distance(array2[1], vector2);
							v[2] = -1f + 2f * num / num2;
							v[3] = v[2];
						}
						else
						{
							Logger.Log(string.Concat(new string[]
							{
								"Error 600 in GetIntrinsecCoordinates: unable to find intersection point, p1:{",
								array2[1].ToString(),
								"}; p2:{",
								array2[2].ToString(),
								"}; p3:{",
								array[2].ToString(),
								"}; p4:{",
								array[3].ToString(),
								"}"
							}), DebugLevel.CRITICAL);
						}
					}
					else
					{
						Logger.Log("Error 700 in GetIntrinsecCoordinates(): error in SetSpring() procedure", DebugLevel.CRITICAL);
					}
				}
			}
		}

		// Token: 0x060001AE RID: 430 RVA: 0x00014F64 File Offset: 0x00013164
		public static void GetIntrinsecCoordinates(out float u, out float v, float[] X, float[] Y, Microsoft.Xna.Framework.Vector2 point, float tol = 0.001f)
		{
			Operations.GetIntrinsecCoordinates(out u, out v, point.X, point.Y, X[0], Y[0], X[1], Y[1], X[2], Y[2], X[3], Y[3], tol);
		}

		// Token: 0x060001AF RID: 431 RVA: 0x00014FA0 File Offset: 0x000131A0
		public static bool IntersectionTestForGUI(bool IntersectMode, List<Microsoft.Xna.Framework.Vector2> _finestraSelezione, List<Microsoft.Xna.Framework.Vector2> _verticiOggetto)
		{
			if (_verticiOggetto.Count == 2)
			{
				_verticiOggetto.Add(_verticiOggetto.First<Microsoft.Xna.Framework.Vector2>());
			}
			bool flag;
			if (IntersectMode)
			{
				flag = false;
				if (Operations.IntersectionTest(_finestraSelezione, _verticiOggetto, false) > 1)
				{
					flag = true;
				}
			}
			else
			{
				flag = true;
				int count = _verticiOggetto.Count;
				float x = _finestraSelezione[0].X;
				float x2 = _finestraSelezione[1].X;
				float y = _finestraSelezione[2].Y;
				float y2 = _finestraSelezione[0].Y;
				for (int i = 0; i < count; i++)
				{
					Microsoft.Xna.Framework.Vector2 vector = _verticiOggetto[i];
					flag = flag && (vector.X >= x && vector.X <= x2 && vector.Y >= y) && vector.Y <= y2;
				}
			}
			return flag;
		}

		// Token: 0x060001B0 RID: 432 RVA: 0x00015070 File Offset: 0x00013270
		public static int IntersectionTest(List<Microsoft.Xna.Framework.Vector2> NodeList1, List<Microsoft.Xna.Framework.Vector2> NodeList2, bool IncludeExtremeNodes)
		{
			Microsoft.Xna.Framework.Vector2 vector = default(Microsoft.Xna.Framework.Vector2);
			bool flag = true;
			int i = 0;
			int count = NodeList1.Count;
			int count2 = NodeList2.Count;
			while (flag && i < count)
			{
				int num = 0;
				bool flag2 = false;
				while (num < count2 && !flag2)
				{
					if (Math.Abs(NodeList1[i].X - NodeList2[num].X) < Operations.ToleranceNode && Math.Abs(NodeList1[i].Y - NodeList2[num].Y) < Operations.ToleranceNode)
					{
						flag2 = true;
					}
					num++;
				}
				if (!flag2)
				{
					flag = false;
				}
				i++;
			}
			if (flag)
			{
				return 3;
			}
			flag = true;
			for (i = 0; i < count; i++)
			{
				if (!Operations.puntoInternoAPoligono(NodeList2, NodeList1[i]))
				{
					flag = false;
					break;
				}
			}
			if (flag)
			{
				return 1;
			}
			flag = true;
			for (i = 0; i < count2; i++)
			{
				if (!Operations.puntoInternoAPoligono(NodeList1, NodeList2[i]))
				{
					flag = false;
					break;
				}
			}
			if (flag)
			{
				return 2;
			}
			flag = false;
			i = 0;
			while (!flag && i < count)
			{
				int num = 0;
				while (!flag && num < count2)
				{
					if (Operations.CheckIfTwoLinesAreIntersected(NodeList1[i], NodeList1[(i < count - 1) ? (i + 1) : 0], NodeList2[num], NodeList2[(num < count2 - 1) ? (num + 1) : 0], out vector, IncludeExtremeNodes))
					{
						return 4;
					}
					num++;
				}
				i++;
			}
			return 0;
		}

		// Token: 0x060001B1 RID: 433 RVA: 0x000151D8 File Offset: 0x000133D8
		public static bool CheckIfTwoLinesAreIntersected(Microsoft.Xna.Framework.Vector2 p1, Microsoft.Xna.Framework.Vector2 p2, Microsoft.Xna.Framework.Vector2 r1, Microsoft.Xna.Framework.Vector2 r2, out Microsoft.Xna.Framework.Vector2 IntersectionPoint, bool IncludeExtremeNodes)
		{
			IntersectionPoint = default(Microsoft.Xna.Framework.Vector2);
			float y = p1.Y;
			float y2 = p2.Y;
			float x = p1.X;
			float x2 = p2.X;
			float y3 = r1.Y;
			float y4 = r2.Y;
			float x3 = r1.X;
			float x4 = r2.X;
			float num = (p2.Y - p1.Y) / (p2.X - p1.X);
			float num2 = (r2.Y - r1.Y) / (r2.X - r1.X);
			if (num != num2 && (p2.X != p1.X || r2.X != r1.X))
			{
				IntersectionPoint.Y = ((y2 - y) * y3 * x4 + (y - y2) * y4 * x3 + (y2 * x - y * x2) * y4 + (y * x2 - y2 * x) * y3) / ((y2 - y) * x4 + (y - y2) * x3 + (x - x2) * y4 + (x2 - x) * y3);
				IntersectionPoint.X = (((x2 - x) * y3 - y * x2 + y2 * x) * x4 + ((x - x2) * y4 + y * x2 - y2 * x) * x3) / ((y2 - y) * x4 + (y - y2) * x3 + (x - x2) * y4 + (x2 - x) * y3);
				if (IncludeExtremeNodes)
				{
					if (Operations.AlignNodes(new Microsoft.Xna.Framework.Vector3(IntersectionPoint, 0f), new Microsoft.Xna.Framework.Vector3(p1, 0f), new Microsoft.Xna.Framework.Vector3(p2, 0f), -1f) > 0 && Operations.AlignNodes(new Microsoft.Xna.Framework.Vector3(IntersectionPoint, 0f), new Microsoft.Xna.Framework.Vector3(r1, 0f), new Microsoft.Xna.Framework.Vector3(r2, 0f), -1f) > 0)
					{
						return true;
					}
				}
				else if (Operations.AlignNodes(new Microsoft.Xna.Framework.Vector3(IntersectionPoint, 0f), new Microsoft.Xna.Framework.Vector3(p1, 0f), new Microsoft.Xna.Framework.Vector3(p2, 0f), -1f) == 1 && Operations.AlignNodes(new Microsoft.Xna.Framework.Vector3(IntersectionPoint, 0f), new Microsoft.Xna.Framework.Vector3(r1, 0f), new Microsoft.Xna.Framework.Vector3(r2, 0f), -1f) == 1)
				{
					return true;
				}
			}
			return false;
		}

		// Token: 0x060001B2 RID: 434 RVA: 0x000153F5 File Offset: 0x000135F5
		public static bool puntoInternoAPoligono(List<Microsoft.Xna.Framework.Vector2> NodeList, Microsoft.Xna.Framework.Vector2 Punto)
		{
			return Operations.puntoInternoAPoligono(NodeList.ToArray(), Punto);
		}

		// Token: 0x060001B3 RID: 435 RVA: 0x00015404 File Offset: 0x00013604
		public static bool puntoInternoAPoligono(Microsoft.Xna.Framework.Vector2[] NodeList, Microsoft.Xna.Framework.Vector2 Punto)
		{
			bool flag = false;
			int num = NodeList.Length;
			int num2 = num - 1;
			for (int i = 0; i < num; i++)
			{
				if (Operations.AlignNodes(new Microsoft.Xna.Framework.Vector3(Punto, 0f), new Microsoft.Xna.Framework.Vector3(NodeList[i], 0f), new Microsoft.Xna.Framework.Vector3(NodeList[(i < num - 1) ? (i + 1) : 0], 0f), -1f) > 0)
				{
					return true;
				}
				if (((NodeList[i].Y <= Punto.Y && Punto.Y < NodeList[num2].Y) || (NodeList[num2].Y <= Punto.Y && Punto.Y < NodeList[i].Y)) && Punto.X < (NodeList[num2].X - NodeList[i].X) * (Punto.Y - NodeList[i].Y) / (NodeList[num2].Y - NodeList[i].Y) + NodeList[i].X)
				{
					flag = !flag;
				}
				num2 = i;
			}
			return flag;
		}

		// Token: 0x060001B4 RID: 436 RVA: 0x00015528 File Offset: 0x00013728
		public static bool IsPointInPlane(Microsoft.Xna.Framework.Vector3[] Nodes, Microsoft.Xna.Framework.Vector3 p, float tol = -1f)
		{
			return Operations.IsPointInPlane(Operations.GetPlane(Nodes[0], Nodes[1], Nodes[2]), p, tol);
		}

		// Token: 0x060001B5 RID: 437 RVA: 0x0001554C File Offset: 0x0001374C
		public static bool puntoInternoAPoligono(Microsoft.Xna.Framework.Vector3[] Nodes, Microsoft.Xna.Framework.Vector3 p, float tol = -1f)
		{
			int num = Nodes.Length;
			Microsoft.Xna.Framework.Vector2[] array = new Microsoft.Xna.Framework.Vector2[num];
			if (!Operations.IsPointInPlane(Operations.GetPlane(Nodes[0], Nodes[1], Nodes[2]), p, tol))
			{
				return false;
			}
			Matrix rotationMatrixFrom3Points = Operations.GetRotationMatrixFrom3Points(Nodes[0], Nodes[1], Nodes[2]);
			for (int i = 0; i < num; i++)
			{
				array[i] = Operations.MatrixPerVector3_2d(rotationMatrixFrom3Points, Nodes[i] - Nodes[0]);
			}
			Microsoft.Xna.Framework.Vector2 vector = Operations.MatrixPerVector3_2d(rotationMatrixFrom3Points, p - Nodes[0]);
			return Operations.puntoInternoAPoligono(array, vector);
		}

		// Token: 0x060001B6 RID: 438 RVA: 0x000155F0 File Offset: 0x000137F0
		public static int FindIntersectionBetweenQuadrilaters(out List<Microsoft.Xna.Framework.Vector3> NodeListOut, List<Microsoft.Xna.Framework.Vector3> NodeList1, List<Microsoft.Xna.Framework.Vector3> NodeList2, bool IncludeExtremeNodes)
		{
			NodeListOut = new List<Microsoft.Xna.Framework.Vector3>();
			int num = 0;
			for (int i = 0; i < NodeList1.Count; i++)
			{
				for (int j = 0; j < NodeList1.Count; j++)
				{
					if (i != j && (NodeList1[i] - NodeList1[j]).Length() < Operations.ToleranceNode)
					{
						return num;
					}
				}
			}
			for (int k = 0; k < NodeList2.Count; k++)
			{
				for (int l = 0; l < NodeList2.Count; l++)
				{
					if (k != l && (NodeList2[k] - NodeList2[l]).Length() < Operations.ToleranceNode)
					{
						return num;
					}
				}
			}
			List<Microsoft.Xna.Framework.Vector2> list = new List<Microsoft.Xna.Framework.Vector2>();
			List<Microsoft.Xna.Framework.Vector2> list2 = new List<Microsoft.Xna.Framework.Vector2>();
			Microsoft.Xna.Framework.Vector4 plane = Operations.GetPlane(NodeList1[0], NodeList1[1], NodeList1[2]);
			Microsoft.Xna.Framework.Vector4 plane2 = Operations.GetPlane(NodeList2[0], NodeList2[1], NodeList2[2]);
			if ((Operations.IsPointInPlane(plane, NodeList2[0], -1f) && Operations.IsPointInPlane(plane, NodeList2[1], -1f) && Operations.IsPointInPlane(plane, NodeList2[2], -1f)) || (Operations.IsPointInPlane(plane2, NodeList1[0], -1f) && Operations.IsPointInPlane(plane2, NodeList1[1], -1f) && Operations.IsPointInPlane(plane2, NodeList1[2], -1f)))
			{
				int num2 = Math.Min(NodeList1.Count, NodeList2.Count);
				for (int m = 0; m < num2; m++)
				{
					if (num2 == 4)
					{
						Microsoft.Xna.Framework.Vector2 vector;
						Operations.ConvertVector3ToVector2(NodeList1[0], NodeList1[1], NodeList1[3], NodeList1[m], out vector);
						list.Add(vector);
						Operations.ConvertVector3ToVector2(NodeList1[0], NodeList1[1], NodeList1[3], NodeList2[m], out vector);
						list2.Add(vector);
					}
					else
					{
						Microsoft.Xna.Framework.Vector2 vector;
						Operations.ConvertVector3ToVector2(NodeList1[0], NodeList1[1], NodeList1[2], NodeList1[m], out vector);
						list.Add(vector);
						Operations.ConvertVector3ToVector2(NodeList1[0], NodeList1[1], NodeList1[2], NodeList2[m], out vector);
						list2.Add(vector);
					}
				}
				num = Operations.IntersectionTest(list, list2, IncludeExtremeNodes);
				switch (num)
				{
				case 1:
				case 3:
				{
					for (int n = 0; n < NodeList1.Count; n++)
					{
						Microsoft.Xna.Framework.Vector3 vector2 = NodeList1[n];
						NodeListOut.Add(vector2);
					}
					break;
				}
				case 2:
				{
					for (int num3 = 0; num3 < NodeList2.Count; num3++)
					{
						Microsoft.Xna.Framework.Vector3 vector2 = NodeList2[num3];
						NodeListOut.Add(vector2);
					}
					break;
				}
				case 4:
					Operations.IntersectQuadrilater(out NodeListOut, list, list2, NodeList1[0], NodeList1[1], NodeList1[2], IncludeExtremeNodes);
					if (NodeListOut.Count == 4)
					{
						float num4 = Operations.Area(NodeListOut.ToArray(), true);
						if (float.IsNaN(num4))
						{
							num4 = 0f;
						}
						float num5 = Microsoft.Xna.Framework.Vector3.Distance(NodeListOut[3], NodeListOut[0]);
						float num6 = num5;
						for (int num7 = 0; num7 < 3; num7++)
						{
							float num8 = Microsoft.Xna.Framework.Vector3.Distance(NodeListOut[num7], NodeListOut[num7 + 1]);
							if (num8 > num5)
							{
								num5 = num8;
							}
							if (num8 < num6)
							{
								num6 = num8;
							}
						}
						if (num4 < Operations.ToleranceNode * num5)
						{
							NodeListOut.Clear();
						}
					}
					break;
				}
			}
			return num;
		}

		// Token: 0x060001B7 RID: 439 RVA: 0x00015994 File Offset: 0x00013B94
		public static int FindIntersectionBetweenQuadrilaters(out List<List<Microsoft.Xna.Framework.Vector3>> NodeListOut, List<Microsoft.Xna.Framework.Vector3> NodeList1, List<Microsoft.Xna.Framework.Vector3> NodeList2, bool IncludeExtremeNodes)
		{
			NodeListOut = new List<List<Microsoft.Xna.Framework.Vector3>>();
			int num = 0;
			for (int i = 0; i < NodeList1.Count; i++)
			{
				for (int j = 0; j < NodeList1.Count; j++)
				{
					if (i != j && (NodeList1[i] - NodeList1[j]).Length() < Operations.ToleranceNode)
					{
						return num;
					}
				}
			}
			for (int k = 0; k < NodeList2.Count; k++)
			{
				for (int l = 0; l < NodeList2.Count; l++)
				{
					if (k != l && (NodeList2[k] - NodeList2[l]).Length() < Operations.ToleranceNode)
					{
						return num;
					}
				}
			}
			List<Microsoft.Xna.Framework.Vector2> list = new List<Microsoft.Xna.Framework.Vector2>();
			List<Microsoft.Xna.Framework.Vector2> list2 = new List<Microsoft.Xna.Framework.Vector2>();
			Microsoft.Xna.Framework.Vector4 vector = default(Microsoft.Xna.Framework.Vector4);
			Microsoft.Xna.Framework.Vector4 vector2 = default(Microsoft.Xna.Framework.Vector4);
			vector = Operations.GetPlane(NodeList1[0], NodeList1[1], NodeList1[2]);
			vector2 = Operations.GetPlane(NodeList2[0], NodeList2[1], NodeList2[2]);
			if ((Operations.IsPointInPlane(vector, NodeList2[0], -1f) && Operations.IsPointInPlane(vector, NodeList2[1], -1f) && Operations.IsPointInPlane(vector, NodeList2[2], -1f)) || (Operations.IsPointInPlane(vector2, NodeList1[0], -1f) && Operations.IsPointInPlane(vector2, NodeList1[1], -1f) && Operations.IsPointInPlane(vector2, NodeList1[2], -1f)))
			{
				list.Clear();
				list2.Clear();
				int count = NodeList1.Count;
				for (int m = 0; m < count; m++)
				{
					if (count == 4)
					{
						Microsoft.Xna.Framework.Vector2 vector3 = default(Microsoft.Xna.Framework.Vector2);
						Operations.ConvertVector3ToVector2(NodeList1[0], NodeList1[1], NodeList1[3], NodeList1[m], out vector3);
						list.Add(vector3);
						vector3 = default(Microsoft.Xna.Framework.Vector2);
						Operations.ConvertVector3ToVector2(NodeList1[0], NodeList1[1], NodeList1[3], NodeList2[m], out vector3);
						list2.Add(vector3);
					}
					else
					{
						Microsoft.Xna.Framework.Vector2 vector3 = default(Microsoft.Xna.Framework.Vector2);
						Operations.ConvertVector3ToVector2(NodeList1[0], NodeList1[1], NodeList1[2], NodeList1[m], out vector3);
						list.Add(vector3);
						vector3 = default(Microsoft.Xna.Framework.Vector2);
						Operations.ConvertVector3ToVector2(NodeList1[0], NodeList1[1], NodeList1[2], NodeList2[m], out vector3);
						list2.Add(vector3);
					}
				}
				num = Operations.IntersectionTest(list, list2, IncludeExtremeNodes);
				switch (num)
				{
				case 1:
				case 3:
				{
					List<Microsoft.Xna.Framework.Vector3> list3 = new List<Microsoft.Xna.Framework.Vector3>();
					for (int n = 0; n < NodeList1.Count; n++)
					{
						Microsoft.Xna.Framework.Vector3 vector4 = NodeList1[n];
						list3.Add(vector4);
					}
					NodeListOut.Add(list3);
					break;
				}
				case 2:
				{
					List<Microsoft.Xna.Framework.Vector3> list3 = new List<Microsoft.Xna.Framework.Vector3>();
					for (int num2 = 0; num2 < NodeList2.Count; num2++)
					{
						Microsoft.Xna.Framework.Vector3 vector4 = NodeList2[num2];
						list3.Add(vector4);
					}
					NodeListOut.Add(list3);
					break;
				}
				case 4:
				{
					Operations.IntersectQuadrilater(out NodeListOut, list, list2, NodeList1[0], NodeList1[1], NodeList1[2], IncludeExtremeNodes);
					for (int num3 = 0; num3 < NodeListOut.Count; num3++)
					{
						if (NodeListOut[num3].Count == 4)
						{
							float num4 = Operations.Area(NodeListOut[num3].ToArray(), true);
							if (float.IsNaN(num4))
							{
								num4 = 0f;
							}
							float num5 = Microsoft.Xna.Framework.Vector3.Distance(NodeListOut[num3][3], NodeListOut[num3][0]);
							for (int num6 = 0; num6 < 3; num6++)
							{
								if (Microsoft.Xna.Framework.Vector3.Distance(NodeListOut[num3][num6], NodeListOut[num3][num6 + 1]) > num5)
								{
									num5 = Microsoft.Xna.Framework.Vector3.Distance(NodeListOut[num3][num6], NodeListOut[num3][num6 + 1]);
								}
							}
							if (num4 < Operations.ToleranceNode * num5)
							{
								NodeListOut[num3].Clear();
								NodeListOut.RemoveAt(num3);
							}
						}
					}
					break;
				}
				}
			}
			return num;
		}

		// Token: 0x060001B8 RID: 440 RVA: 0x00008060 File Offset: 0x00006260
		public static int FindIntersectionBetweenPoligons(List<Microsoft.Xna.Framework.Vector3> NodeList1, List<Microsoft.Xna.Framework.Vector3> NodeList2)
		{
			return 0;
		}

		// Token: 0x060001B9 RID: 441 RVA: 0x00015DF8 File Offset: 0x00013FF8
		public static void IntersectQuadrilater(out List<Microsoft.Xna.Framework.Vector3> NodeList, List<Microsoft.Xna.Framework.Vector2> NodeList1_2d, List<Microsoft.Xna.Framework.Vector2> NodeList2_2d, Microsoft.Xna.Framework.Vector3 n1, Microsoft.Xna.Framework.Vector3 n2, Microsoft.Xna.Framework.Vector3 n3, bool IncludeExtremeNodes)
		{
			NodeList = new List<Microsoft.Xna.Framework.Vector3>();
			List<Microsoft.Xna.Framework.Vector2> list = new List<Microsoft.Xna.Framework.Vector2>();
			int num = NodeList1_2d.Count;
			int num2 = 3;
			if (num > 3)
			{
				Microsoft.Xna.Framework.Vector2 vector = Operations.GetLowerLeft(NodeList1_2d[0], NodeList1_2d[1], NodeList1_2d[2], NodeList1_2d[3]);
				Microsoft.Xna.Framework.Vector2 vector2 = Operations.GetLowerRight(NodeList1_2d[0], NodeList1_2d[1], NodeList1_2d[2], NodeList1_2d[3]);
				Microsoft.Xna.Framework.Vector2 vector3 = Operations.GetHigherLeft(NodeList1_2d[0], NodeList1_2d[1], NodeList1_2d[2], NodeList1_2d[3]);
				Microsoft.Xna.Framework.Vector2 vector4 = Operations.GetHigherRight(NodeList1_2d[0], NodeList1_2d[1], NodeList1_2d[2], NodeList1_2d[3]);
				vector.X = (float)Math.Round((double)vector.X, num2);
				vector.Y = (float)Math.Round((double)vector.Y, num2);
				vector2.X = (float)Math.Round((double)vector2.X, num2);
				vector2.Y = (float)Math.Round((double)vector2.Y, num2);
				vector3.X = (float)Math.Round((double)vector3.X, num2);
				vector3.Y = (float)Math.Round((double)vector3.Y, num2);
				vector4.X = (float)Math.Round((double)vector4.X, num2);
				vector4.Y = (float)Math.Round((double)vector4.Y, num2);
				NodeList1_2d.Clear();
				NodeList1_2d.Add(vector);
				NodeList1_2d.Add(vector2);
				NodeList1_2d.Add(vector4);
				NodeList1_2d.Add(vector3);
				vector = Operations.GetLowerLeft(NodeList2_2d[0], NodeList2_2d[1], NodeList2_2d[2], NodeList2_2d[3]);
				vector2 = Operations.GetLowerRight(NodeList2_2d[0], NodeList2_2d[1], NodeList2_2d[2], NodeList2_2d[3]);
				vector3 = Operations.GetHigherLeft(NodeList2_2d[0], NodeList2_2d[1], NodeList2_2d[2], NodeList2_2d[3]);
				vector4 = Operations.GetHigherRight(NodeList2_2d[0], NodeList2_2d[1], NodeList2_2d[2], NodeList2_2d[3]);
				vector.X = (float)Math.Round((double)vector.X, num2);
				vector.Y = (float)Math.Round((double)vector.Y, num2);
				vector2.X = (float)Math.Round((double)vector2.X, num2);
				vector2.Y = (float)Math.Round((double)vector2.Y, num2);
				vector3.X = (float)Math.Round((double)vector3.X, num2);
				vector3.Y = (float)Math.Round((double)vector3.Y, num2);
				vector4.X = (float)Math.Round((double)vector4.X, num2);
				vector4.Y = (float)Math.Round((double)vector4.Y, num2);
				NodeList2_2d.Clear();
				NodeList2_2d.Add(vector);
				NodeList2_2d.Add(vector2);
				NodeList2_2d.Add(vector4);
				NodeList2_2d.Add(vector3);
			}
			List<Microsoft.Xna.Framework.Vector2> list2 = new List<Microsoft.Xna.Framework.Vector2>();
			List<Microsoft.Xna.Framework.Vector2> list3 = new List<Microsoft.Xna.Framework.Vector2>();
			num = NodeList1_2d.Count;
			int count = NodeList2_2d.Count;
			int i;
			int num3;
			for (i = 0; i < num; i = num3 + 1)
			{
				list3.Add(new Microsoft.Xna.Framework.Vector2(NodeList1_2d[i].X, NodeList1_2d[i].Y));
				list3.Add(new Microsoft.Xna.Framework.Vector2(NodeList2_2d[i].X, NodeList2_2d[i].Y));
				num3 = i;
			}
			for (i = 0; i < num; i = num3 + 1)
			{
				for (int i2 = 0; i2 < count; i2++)
				{
					Microsoft.Xna.Framework.Vector2 _interectionPoint;
					if (Operations.CheckIfTwoLinesAreIntersected(NodeList1_2d[i], NodeList1_2d[(i + 1 < num) ? (i + 1) : 0], NodeList2_2d[i2], NodeList2_2d[(i2 + 1 < count) ? (i2 + 1) : 0], out _interectionPoint, false) && list3.Where((Microsoft.Xna.Framework.Vector2 x) => (x - _interectionPoint).Length() < Operations.ToleranceNode).Count<Microsoft.Xna.Framework.Vector2>() == 0)
					{
						list3.Add(_interectionPoint);
					}
				}
				num3 = i;
			}
			IEnumerable<Microsoft.Xna.Framework.Vector2> enumerable = list3.OrderBy((Microsoft.Xna.Framework.Vector2 x) => x.X);
			list2.Clear();
			foreach (Microsoft.Xna.Framework.Vector2 vector5 in enumerable)
			{
				if (list2.Count > 0)
				{
					if (vector5.X > list2.Last<Microsoft.Xna.Framework.Vector2>().X)
					{
						list2.Add(vector5);
					}
				}
				else
				{
					list2.Add(vector5);
				}
			}
			list3.Clear();
			for (i = 0; i < list2.Count - 1; i = num3 + 1)
			{
				list3.Clear();
				Operations.CalcolaTrapezoide(ref list3, NodeList1_2d, NodeList2_2d, list2[i].X, list2[i + 1].X, IncludeExtremeNodes);
				Operations.MergeTrapezoide(ref list, list3, list2[i + 1].X);
				num3 = i;
			}
			for (int j = 0; j < list.Count; j++)
			{
				int k = j + 1;
				while (k < list.Count)
				{
					if (Operations.DistanceBetween(new Microsoft.Xna.Framework.Vector3(list[j], 0f), new Microsoft.Xna.Framework.Vector3(list[k], 0f)) < 1.0)
					{
						list.RemoveAt(k);
					}
					else
					{
						k++;
					}
				}
			}
			for (int j = 0; j < list.Count; j++)
			{
				int k = j + 1;
				while (k < list.Count)
				{
					if (Operations.DistanceBetween(new Microsoft.Xna.Framework.Vector3(list[j], 0f), new Microsoft.Xna.Framework.Vector3(list[k], 0f)) < 1.0)
					{
						list.RemoveAt(k);
					}
					else
					{
						k++;
					}
				}
			}
			if (list.Count > 4)
			{
				List<int> list4 = new List<int>();
				for (int l = 0; l < list.Count; l++)
				{
					for (int m = 0; m < list.Count; m++)
					{
						if (m != l)
						{
							for (int num4 = 0; num4 < list.Count; num4++)
							{
								if (num4 != l && num4 != m && 1 == Operations.AlignNodes(list[num4], list[l], list[m], -1f) && !list4.Contains(num4))
								{
									list4.Add(num4);
								}
							}
						}
					}
				}
				list4.Sort();
				for (int num5 = list4.Count - 1; num5 >= 0; num5--)
				{
					list.RemoveAt(list4[num5]);
				}
			}
			if (list.Count == 4)
			{
				Microsoft.Xna.Framework.Vector2 lowerLeft = Operations.GetLowerLeft(list[0], list[1], list[2], list[3]);
				Microsoft.Xna.Framework.Vector2 lowerRight = Operations.GetLowerRight(list[0], list[1], list[2], list[3]);
				Microsoft.Xna.Framework.Vector2 higherLeft = Operations.GetHigherLeft(list[0], list[1], list[2], list[3]);
				Microsoft.Xna.Framework.Vector2 higherRight = Operations.GetHigherRight(list[0], list[1], list[2], list[3]);
				list.Clear();
				list.Add(lowerLeft);
				list.Add(lowerRight);
				list.Add(higherRight);
				list.Add(higherLeft);
			}
			else
			{
				list.Clear();
			}
			for (i = 0; i < list.Count; i = num3 + 1)
			{
				Microsoft.Xna.Framework.Vector3 vector6 = default(Microsoft.Xna.Framework.Vector3);
				Operations.ConvertVector2ToVector3(n1, n2, n3, list[i], out vector6);
				NodeList.Add(vector6);
				num3 = i;
			}
		}

		// Token: 0x060001BA RID: 442 RVA: 0x00016644 File Offset: 0x00014844
		public static void IntersectQuadrilater(out List<List<Microsoft.Xna.Framework.Vector3>> NodeListOut, List<Microsoft.Xna.Framework.Vector2> NodeList1_2d, List<Microsoft.Xna.Framework.Vector2> NodeList2_2d, Microsoft.Xna.Framework.Vector3 n1, Microsoft.Xna.Framework.Vector3 n2, Microsoft.Xna.Framework.Vector3 n3, bool IncludeExtremeNodes)
		{
			NodeListOut = new List<List<Microsoft.Xna.Framework.Vector3>>();
			List<Microsoft.Xna.Framework.Vector2> list = new List<Microsoft.Xna.Framework.Vector2>();
			Microsoft.Xna.Framework.Vector2 vector = Operations.GetLowerLeft(NodeList1_2d[0], NodeList1_2d[1], NodeList1_2d[2], NodeList1_2d[3]);
			Microsoft.Xna.Framework.Vector2 vector2 = Operations.GetLowerRight(NodeList1_2d[0], NodeList1_2d[1], NodeList1_2d[2], NodeList1_2d[3]);
			Microsoft.Xna.Framework.Vector2 vector3 = Operations.GetHigherLeft(NodeList1_2d[0], NodeList1_2d[1], NodeList1_2d[2], NodeList1_2d[3]);
			Microsoft.Xna.Framework.Vector2 vector4 = Operations.GetHigherRight(NodeList1_2d[0], NodeList1_2d[1], NodeList1_2d[2], NodeList1_2d[3]);
			NodeList1_2d.Clear();
			NodeList1_2d.Add(vector);
			NodeList1_2d.Add(vector2);
			NodeList1_2d.Add(vector4);
			NodeList1_2d.Add(vector3);
			vector = Operations.GetLowerLeft(NodeList2_2d[0], NodeList2_2d[1], NodeList2_2d[2], NodeList2_2d[3]);
			vector2 = Operations.GetLowerRight(NodeList2_2d[0], NodeList2_2d[1], NodeList2_2d[2], NodeList2_2d[3]);
			vector3 = Operations.GetHigherLeft(NodeList2_2d[0], NodeList2_2d[1], NodeList2_2d[2], NodeList2_2d[3]);
			vector4 = Operations.GetHigherRight(NodeList2_2d[0], NodeList2_2d[1], NodeList2_2d[2], NodeList2_2d[3]);
			NodeList2_2d.Clear();
			NodeList2_2d.Add(vector);
			NodeList2_2d.Add(vector2);
			NodeList2_2d.Add(vector4);
			NodeList2_2d.Add(vector3);
			List<Microsoft.Xna.Framework.Vector2> list2 = new List<Microsoft.Xna.Framework.Vector2>();
			List<Microsoft.Xna.Framework.Vector2> list3 = new List<Microsoft.Xna.Framework.Vector2>();
			int count = NodeList1_2d.Count;
			int i;
			int num;
			for (i = 0; i < count; i = num + 1)
			{
				list3.Add(new Microsoft.Xna.Framework.Vector2(NodeList1_2d[i].X, NodeList1_2d[i].Y));
				list3.Add(new Microsoft.Xna.Framework.Vector2(NodeList2_2d[i].X, NodeList2_2d[i].Y));
				num = i;
			}
			for (i = 0; i < 4; i = num + 1)
			{
				for (int i2 = 0; i2 < 4; i2++)
				{
					Microsoft.Xna.Framework.Vector2 _interectionPoint;
					if (Operations.CheckIfTwoLinesAreIntersected(NodeList1_2d[i], NodeList1_2d[(i + 1 < 4) ? (i + 1) : 0], NodeList2_2d[i2], NodeList2_2d[(i2 + 1 < 4) ? (i2 + 1) : 0], out _interectionPoint, false) && list3.Where((Microsoft.Xna.Framework.Vector2 x) => (x - _interectionPoint).Length() < Operations.ToleranceNode).Count<Microsoft.Xna.Framework.Vector2>() == 0)
					{
						list3.Add(_interectionPoint);
					}
				}
				num = i;
			}
			IEnumerable<Microsoft.Xna.Framework.Vector2> enumerable = list3.OrderBy((Microsoft.Xna.Framework.Vector2 x) => x.X);
			list2.Clear();
			foreach (Microsoft.Xna.Framework.Vector2 vector5 in enumerable)
			{
				if (list2.Count > 0)
				{
					if (vector5.X > list2.Last<Microsoft.Xna.Framework.Vector2>().X)
					{
						list2.Add(vector5);
					}
				}
				else
				{
					list2.Add(vector5);
				}
			}
			list3.Clear();
			for (i = 0; i < list2.Count - 1; i = num + 1)
			{
				list3.Clear();
				Operations.CalcolaTrapezoide(ref list3, NodeList1_2d, NodeList2_2d, list2[i].X, list2[i + 1].X, IncludeExtremeNodes);
				Operations.MergeTrapezoide(ref list, list3, list2[i + 1].X);
				num = i;
			}
			for (int j = 0; j < list.Count; j++)
			{
				int k = j + 1;
				while (k < list.Count)
				{
					if (Operations.DistanceBetween(new Microsoft.Xna.Framework.Vector3(list[j], 0f), new Microsoft.Xna.Framework.Vector3(list[k], 0f)) < 1.0)
					{
						list.RemoveAt(k);
					}
					else
					{
						k++;
					}
				}
			}
			if (list.Count > 4)
			{
				List<Microsoft.Xna.Framework.Vector2> list4 = new List<Microsoft.Xna.Framework.Vector2>();
				List<Microsoft.Xna.Framework.Vector2> listaBottom = new List<Microsoft.Xna.Framework.Vector2>();
				for (i = 0; i < list.Count; i += 2)
				{
					list4.Add(list[i]);
				}
				list4.Add(list.Last<Microsoft.Xna.Framework.Vector2>());
				listaBottom.Add(list[0]);
				for (i = 1; i < list.Count; i += 2)
				{
					listaBottom.Add(list[i]);
				}
				int l = 0;
				while (l < list4.Count - 2)
				{
					if (Operations.AlignNodes(list4[l], list4[l + 1], list4[l + 2], -1f) == 0)
					{
						l++;
					}
					else
					{
						list4.RemoveAt(l + 1);
					}
				}
				l = 0;
				while (l < listaBottom.Count - 2)
				{
					if (Operations.AlignNodes(listaBottom[l], listaBottom[l + 1], listaBottom[l + 2], -1f) == 0)
					{
						l++;
					}
					else
					{
						listaBottom.RemoveAt(l + 1);
					}
				}
				Func<Microsoft.Xna.Framework.Vector2, bool> __9__2 = null;
				for (i = 0; i < listaBottom.Count; i = num + 1)
				{
					IEnumerable<Microsoft.Xna.Framework.Vector2> enumerable2 = list4;
					Func<Microsoft.Xna.Framework.Vector2, bool> func;
					if ((func = __9__2) == null)
					{
						func = (__9__2 = (Microsoft.Xna.Framework.Vector2 x) => (x - listaBottom[i]).Length() < Operations.ToleranceNode);
					}
					if (enumerable2.Where(func).Count<Microsoft.Xna.Framework.Vector2>() == 0)
					{
						list4.Add(listaBottom[i]);
					}
					num = i;
				}
				list = null;
				list = list4;
			}
			for (int j = 0; j < list.Count; j++)
			{
				int k = j + 1;
				while (k < list.Count)
				{
					if (Operations.DistanceBetween(new Microsoft.Xna.Framework.Vector3(list[j], 0f), new Microsoft.Xna.Framework.Vector3(list[k], 0f)) < 1.0)
					{
						list.RemoveAt(k);
					}
					else
					{
						k++;
					}
				}
			}
			int num2 = list.Count;
			List<Microsoft.Xna.Framework.Vector2> list5;
			if (num2 > 2)
			{
				try
				{
					SortedList<float, Microsoft.Xna.Framework.Vector2> sortedList = new SortedList<float, Microsoft.Xna.Framework.Vector2>();
					Microsoft.Xna.Framework.Vector2 vector6 = default(Microsoft.Xna.Framework.Vector2);
					for (int m = 0; m < num2; m++)
					{
						vector6 += list[m];
					}
					vector6 /= (float)num2;
					for (int num3 = 0; num3 < num2; num3++)
					{
						float num4 = Operations.ComputeAzimut(vector6, list[num3]);
						if (!sortedList.ContainsKey(num4))
						{
							sortedList.Add(num4, list[num3]);
						}
					}
					list = sortedList.Values.ToList<Microsoft.Xna.Framework.Vector2>();
					if (list.Count > 2)
					{
						try
						{
							int num5 = 0;
							while (num5 < list.Count - 2)
							{
								if (Operations.AlignNodes(list[num5], list[num5 + 1], list[num5 + 2], -1f) == 0)
								{
									num5++;
								}
								else
								{
									list.RemoveAt(num5 + 1);
								}
							}
						}
						catch (Exception)
						{
						}
						num2 = list.Count;
						if (num2 > 2)
						{
							list5 = new List<Microsoft.Xna.Framework.Vector2>();
							do
							{
								try
								{
									if (list.Count >= 4)
									{
										list5.Add(list[0]);
										list5.Add(list[1]);
										list5.Add(list[2]);
										list5.Add(list.Last<Microsoft.Xna.Framework.Vector2>());
									}
									else if (list.Count == 3)
									{
										list5.Add(list[0]);
										list5.Add(list[1]);
										list5.Add(list[2]);
										float[] array = new float[]
										{
											(list[0] - list[1]).Length(),
											(list[1] - list[2]).Length(),
											(list[2] - list[0]).Length()
										};
										switch (Array.IndexOf<float>(array, array.Max()))
										{
										case 0:
											list5.Add((list[0] + list[1]) / 2f);
											break;
										case 1:
											list5.Add((list[1] + list[2]) / 2f);
											break;
										case 2:
											list5.Add((list[2] + list[0]) / 2f);
											break;
										}
									}
								}
								catch
								{
								}
								Microsoft.Xna.Framework.Vector2 lowerLeft = Operations.GetLowerLeft(list5[0], list5[1], list5[2], list5[3]);
								Microsoft.Xna.Framework.Vector2 lowerRight = Operations.GetLowerRight(list5[0], list5[1], list5[2], list5[3]);
								Microsoft.Xna.Framework.Vector2 higherLeft = Operations.GetHigherLeft(list5[0], list5[1], list5[2], list5[3]);
								Microsoft.Xna.Framework.Vector2 higherRight = Operations.GetHigherRight(list5[0], list5[1], list5[2], list5[3]);
								list5.Clear();
								list5.Add(lowerLeft);
								list5.Add(lowerRight);
								list5.Add(higherRight);
								list5.Add(higherLeft);
								List<Microsoft.Xna.Framework.Vector3> list6 = new List<Microsoft.Xna.Framework.Vector3>();
								try
								{
									for (i = 0; i < 4; i = num + 1)
									{
										Microsoft.Xna.Framework.Vector3 vector7;
										Operations.ConvertVector2ToVector3(n1, n2, n3, list5[i], out vector7);
										list6.Add(vector7);
										num = i;
									}
									NodeListOut.Add(list6);
								}
								catch
								{
								}
								try
								{
									if (NodeList2_2d.Count > 0)
									{
										list.RemoveAt(0);
									}
									if (NodeList2_2d.Count > 0)
									{
										list.RemoveAt(0);
									}
								}
								catch
								{
								}
								list5.Clear();
							}
							while (list.Count >= 3);
						}
					}
					goto IL_0A61;
				}
				catch (Exception)
				{
					goto IL_0A61;
				}
			}
			list.Clear();
			IL_0A61:
			list = null;
			list5 = null;
		}

		// Token: 0x060001BB RID: 443 RVA: 0x0001714C File Offset: 0x0001534C
		public static Microsoft.Xna.Framework.Vector3[] IntersectQuadrilaterals(Microsoft.Xna.Framework.Vector3[] quad1, Microsoft.Xna.Framework.Vector3[] quad2)
		{
			ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3>[] array = new ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3>[]
			{
				new ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3>(quad1[0], quad1[1], quad1[2]),
				new ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3>(quad1[0], quad1[2], quad1[3])
			};
			ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3>[] array2 = new ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3>[]
			{
				new ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3>(quad2[0], quad2[1], quad2[2]),
				new ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3>(quad2[0], quad2[2], quad2[3])
			};
			List<Microsoft.Xna.Framework.Vector3> list = new List<Microsoft.Xna.Framework.Vector3>();
			foreach (ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3> valueTuple in array)
			{
				foreach (ValueTuple<Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3, Microsoft.Xna.Framework.Vector3> valueTuple2 in array2)
				{
					List<Microsoft.Xna.Framework.Vector3> list2 = Operations.IntersectTriangles(valueTuple.Item1, valueTuple.Item2, valueTuple.Item3, valueTuple2.Item1, valueTuple2.Item2, valueTuple2.Item3);
					if (list2 != null)
					{
						list.AddRange(list2);
					}
				}
			}
			if (list.Count < 2)
			{
				return null;
			}
			List<Microsoft.Xna.Framework.Vector3> list3 = list.Distinct<Microsoft.Xna.Framework.Vector3>().ToList<Microsoft.Xna.Framework.Vector3>();
			Microsoft.Xna.Framework.Vector3 vector = list3[0];
			Microsoft.Xna.Framework.Vector3 vector2 = list3[1];
			float num = Microsoft.Xna.Framework.Vector3.DistanceSquared(vector, vector2);
			for (int k = 0; k < list3.Count; k++)
			{
				for (int l = k + 1; l < list3.Count; l++)
				{
					float num2 = Microsoft.Xna.Framework.Vector3.DistanceSquared(list3[k], list3[l]);
					if (num2 > num)
					{
						vector = list3[k];
						vector2 = list3[l];
						num = num2;
					}
				}
			}
			return new Microsoft.Xna.Framework.Vector3[] { vector, vector2 };
		}

		// Token: 0x060001BC RID: 444 RVA: 0x00017320 File Offset: 0x00015520
		public static List<Microsoft.Xna.Framework.Vector3> IntersectTriangles(Microsoft.Xna.Framework.Vector3 v0, Microsoft.Xna.Framework.Vector3 v1, Microsoft.Xna.Framework.Vector3 v2, Microsoft.Xna.Framework.Vector3 u0, Microsoft.Xna.Framework.Vector3 u1, Microsoft.Xna.Framework.Vector3 u2)
		{
			Microsoft.Xna.Framework.Vector3 vector = Microsoft.Xna.Framework.Vector3.Normalize(Microsoft.Xna.Framework.Vector3.Cross(v1 - v0, v2 - v0));
			Microsoft.Xna.Framework.Vector3 vector2 = Microsoft.Xna.Framework.Vector3.Normalize(Microsoft.Xna.Framework.Vector3.Cross(u1 - u0, u2 - u0));
			float num = -Microsoft.Xna.Framework.Vector3.Dot(vector, v0);
			float num2 = -Microsoft.Xna.Framework.Vector3.Dot(vector2, u0);
			float num3 = Microsoft.Xna.Framework.Vector3.Dot(vector, u0) + num;
			float num4 = Microsoft.Xna.Framework.Vector3.Dot(vector, u1) + num;
			float num5 = Microsoft.Xna.Framework.Vector3.Dot(vector, u2) + num;
			float num6 = Microsoft.Xna.Framework.Vector3.Dot(vector2, v0) + num2;
			float num7 = Microsoft.Xna.Framework.Vector3.Dot(vector2, v1) + num2;
			float num8 = Microsoft.Xna.Framework.Vector3.Dot(vector2, v2) + num2;
			if ((num3 > 0f && num4 > 0f && num5 > 0f) || (num3 < 0f && num4 < 0f && num5 < 0f))
			{
				return null;
			}
			if ((num6 > 0f && num7 > 0f && num8 > 0f) || (num6 < 0f && num7 < 0f && num8 < 0f))
			{
				return null;
			}
			Microsoft.Xna.Framework.Vector3 vector3 = Microsoft.Xna.Framework.Vector3.Cross(vector, vector2);
			Math.Max(Math.Abs(vector3.X), Math.Max(Math.Abs(vector3.Y), Math.Abs(vector3.Z)));
			Microsoft.Xna.Framework.Vector3 vector4 = Operations.PlaneIntersection(vector, num, vector2, num2);
			ValueTuple<float, float> valueTuple = Operations.ComputeInterval(v0, v1, v2, vector4, vector3);
			ValueTuple<float, float> valueTuple2 = Operations.ComputeInterval(u0, u1, u2, vector4, vector3);
			float num9 = Math.Max(valueTuple.Item1, valueTuple2.Item1);
			float num10 = Math.Min(valueTuple.Item2, valueTuple2.Item2);
			if (num9 > num10)
			{
				return null;
			}
			Microsoft.Xna.Framework.Vector3 vector5 = vector4 + num9 * vector3;
			Microsoft.Xna.Framework.Vector3 vector6 = vector4 + num10 * vector3;
			if (Microsoft.Xna.Framework.Vector3.DistanceSquared(vector5, vector6) < Operations.ToleranceNode)
			{
				return new List<Microsoft.Xna.Framework.Vector3> { vector5 };
			}
			return new List<Microsoft.Xna.Framework.Vector3> { vector5, vector6 };
		}

		// Token: 0x060001BD RID: 445 RVA: 0x0001750C File Offset: 0x0001570C
		private static ValueTuple<float, float> ComputeInterval(Microsoft.Xna.Framework.Vector3 a, Microsoft.Xna.Framework.Vector3 b, Microsoft.Xna.Framework.Vector3 c, Microsoft.Xna.Framework.Vector3 point, Microsoft.Xna.Framework.Vector3 dir)
		{
			float num = Microsoft.Xna.Framework.Vector3.Dot(a - point, dir);
			float num2 = Microsoft.Xna.Framework.Vector3.Dot(b - point, dir);
			float num3 = Microsoft.Xna.Framework.Vector3.Dot(c - point, dir);
			float num4 = Math.Min(num, Math.Min(num2, num3));
			float num5 = Math.Max(num, Math.Max(num2, num3));
			return new ValueTuple<float, float>(num4, num5);
		}

		// Token: 0x060001BE RID: 446 RVA: 0x00017568 File Offset: 0x00015768
		private static Microsoft.Xna.Framework.Vector3 PlaneIntersection(Microsoft.Xna.Framework.Vector3 n1, float d1, Microsoft.Xna.Framework.Vector3 n2, float d2)
		{
			Microsoft.Xna.Framework.Vector3 vector = Microsoft.Xna.Framework.Vector3.Cross(n1, n2);
			float num = vector.LengthSquared();
			Microsoft.Xna.Framework.Vector3 zero = Microsoft.Xna.Framework.Vector3.Zero;
			Microsoft.Xna.Framework.Vector3.Cross(n1, n2);
			Microsoft.Xna.Framework.Vector3 vector2 = Microsoft.Xna.Framework.Vector3.Cross(n1, vector) * d2;
			Microsoft.Xna.Framework.Vector3 vector3 = Microsoft.Xna.Framework.Vector3.Cross(n2, vector) * d1;
			return (vector2 - vector3) / num;
		}

		// Token: 0x060001BF RID: 447 RVA: 0x000175BC File Offset: 0x000157BC
		private static float ComputeAzimut(Microsoft.Xna.Framework.Vector2 p0, Microsoft.Xna.Framework.Vector2 p1)
		{
			float num = p1.X - p0.X;
			float num2 = p1.Y - p0.Y;
			float num3;
			if (num != 0f)
			{
				num3 = Operations.Atand(num2 / num);
				if (num > 0f)
				{
					if (num2 < 0f)
					{
						num3 = 360f + num3;
					}
				}
				else
				{
					num3 = 180f + num3;
				}
			}
			else if (num2 > 0f)
			{
				num3 = 90f;
			}
			else
			{
				num3 = 270f;
			}
			return num3;
		}

		// Token: 0x060001C0 RID: 448 RVA: 0x00017638 File Offset: 0x00015838
		private static void FindChain(ref List<int> chain, int ind_min, int ind_max, List<Microsoft.Xna.Framework.Vector2> NodeList1_2d, bool inf)
		{
			bool flag = false;
			int num = ind_min;
			int num2 = NodeList1_2d.Count - 1;
			while (!flag)
			{
				Microsoft.Xna.Framework.Vector2 vector = new Microsoft.Xna.Framework.Vector2(NodeList1_2d[num].X, NodeList1_2d[num].Y);
				Microsoft.Xna.Framework.Vector2 ptr = new Microsoft.Xna.Framework.Vector2(NodeList1_2d[(num < num2) ? (num + 1) : 0].X, NodeList1_2d[(num < num2) ? (num + 1) : 0].Y);
				Microsoft.Xna.Framework.Vector2 vector2 = new Microsoft.Xna.Framework.Vector2(NodeList1_2d[(num > 0) ? (num - 1) : num2].X, NodeList1_2d[(num > num2) ? (num - 1) : num2].Y);
				if (ptr.Y - vector.Y > vector2.Y - vector.Y)
				{
					if (inf)
					{
						num = ((num < num2) ? (num + 1) : 0);
					}
					else
					{
						num = ((num > 0) ? (num - 1) : num2);
					}
					if (num != ind_max)
					{
						chain.Add(num);
					}
					else
					{
						flag = true;
					}
				}
				else
				{
					if (inf)
					{
						num = ((num < num2) ? (num + 1) : 0);
					}
					else
					{
						num = ((num > 0) ? (num - 1) : num2);
					}
					if (num != ind_max)
					{
						chain.Add(num);
					}
					else
					{
						flag = true;
					}
				}
			}
		}

		// Token: 0x060001C1 RID: 449 RVA: 0x00017754 File Offset: 0x00015954
		private static void CalcolaTrapezoide(ref List<Microsoft.Xna.Framework.Vector2> NodeListTrapezoide, List<Microsoft.Xna.Framework.Vector2> NodeList1_2d, List<Microsoft.Xna.Framework.Vector2> NodeList2_2d, float x_min, float x_max, bool IncludeExtremeNodes)
		{
			List<Microsoft.Xna.Framework.Vector2> list = new List<Microsoft.Xna.Framework.Vector2>();
			List<Microsoft.Xna.Framework.Vector2> list2 = new List<Microsoft.Xna.Framework.Vector2>();
			List<Microsoft.Xna.Framework.Vector2> list3 = new List<Microsoft.Xna.Framework.Vector2>();
			List<Microsoft.Xna.Framework.Vector2> list4 = new List<Microsoft.Xna.Framework.Vector2>();
			int num = NodeList1_2d.Count;
			float num2 = NodeList1_2d[0].Y;
			float num3 = NodeList1_2d[0].Y;
			for (int i = 0; i < num; i++)
			{
				if (num2 > NodeList1_2d[i].Y)
				{
					num2 = NodeList1_2d[i].Y;
				}
				if (num2 > NodeList2_2d[i].Y)
				{
					num2 = NodeList2_2d[i].Y;
				}
				if (num3 < NodeList1_2d[i].Y)
				{
					num3 = NodeList1_2d[i].Y;
				}
				if (num3 < NodeList2_2d[i].Y)
				{
					num3 = NodeList2_2d[i].Y;
				}
			}
			Microsoft.Xna.Framework.Vector2[] array = new Microsoft.Xna.Framework.Vector2[2];
			Microsoft.Xna.Framework.Vector2[] array2 = new Microsoft.Xna.Framework.Vector2[2];
			array[0] = new Microsoft.Xna.Framework.Vector2(x_min, num2);
			array2[0] = new Microsoft.Xna.Framework.Vector2(x_min, num3);
			array[1] = new Microsoft.Xna.Framework.Vector2(x_max, num2);
			array2[1] = new Microsoft.Xna.Framework.Vector2(x_max, num3);
			Microsoft.Xna.Framework.Vector2 intersection;
			Func<Microsoft.Xna.Framework.Vector2, bool> __9__0 = null;
			Func<Microsoft.Xna.Framework.Vector2, bool> __9__1 = null;
			Func<Microsoft.Xna.Framework.Vector2, bool> __9__2 = null;
			Func<Microsoft.Xna.Framework.Vector2, bool> __9__3 = null;
			for (int j = 0; j < 2; j++)
			{
				intersection = default(Microsoft.Xna.Framework.Vector2);
				int k = 0;
				num = NodeList1_2d.Count;
				while (k < num)
				{
					if (Operations.CheckIfTwoLinesAreIntersected(NodeList1_2d[k], NodeList1_2d[(k < num - 1) ? (k + 1) : 0], array[j], array2[j], out intersection, IncludeExtremeNodes))
					{
						if (j == 0)
						{
							IEnumerable<Microsoft.Xna.Framework.Vector2> enumerable = list;
							Func<Microsoft.Xna.Framework.Vector2, bool> func;
							if ((func = __9__0) == null)
							{
								func = (__9__0 = (Microsoft.Xna.Framework.Vector2 x) => (x - intersection).Length() < Operations.ToleranceNode);
							}
							if (!enumerable.Select(func).Contains(true))
							{
								list.Add(intersection);
							}
						}
						else
						{
							IEnumerable<Microsoft.Xna.Framework.Vector2> enumerable2 = list2;
							Func<Microsoft.Xna.Framework.Vector2, bool> func2;
							if ((func2 = __9__1) == null)
							{
								func2 = (__9__1 = (Microsoft.Xna.Framework.Vector2 x) => (x - intersection).Length() < Operations.ToleranceNode);
							}
							if (!enumerable2.Select(func2).Contains(true))
							{
								list2.Add(intersection);
							}
						}
					}
					k++;
				}
				k = 0;
				num = NodeList2_2d.Count;
				while (k < num)
				{
					if (Operations.CheckIfTwoLinesAreIntersected(NodeList2_2d[k], NodeList2_2d[(k < num - 1) ? (k + 1) : 0], array[j], array2[j], out intersection, IncludeExtremeNodes))
					{
						if (j == 0)
						{
							IEnumerable<Microsoft.Xna.Framework.Vector2> enumerable3 = list3;
							Func<Microsoft.Xna.Framework.Vector2, bool> func3;
							if ((func3 = __9__2) == null)
							{
								func3 = (__9__2 = (Microsoft.Xna.Framework.Vector2 x) => (x - intersection).Length() < Operations.ToleranceNode);
							}
							if (!enumerable3.Select(func3).Contains(true))
							{
								list3.Add(intersection);
							}
						}
						else
						{
							IEnumerable<Microsoft.Xna.Framework.Vector2> enumerable4 = list4;
							Func<Microsoft.Xna.Framework.Vector2, bool> func4;
							if ((func4 = __9__3) == null)
							{
								func4 = (__9__3 = (Microsoft.Xna.Framework.Vector2 x) => (x - intersection).Length() < Operations.ToleranceNode);
							}
							if (!enumerable4.Select(func4).Contains(true))
							{
								list4.Add(intersection);
							}
						}
					}
					k++;
				}
			}
			if (list.Count > 0 && list3.Count > 0)
			{
				int num4 = 0;
				if (list.Count == 2 && list[1].Y < list[0].Y)
				{
					num4 = 1;
				}
				int num5 = 0;
				if (list3.Count == 2 && list3[1].Y < list3[0].Y)
				{
					num5 = 1;
				}
				int num6 = 0;
				if (list.Count == 2 && list[1].Y > list[0].Y)
				{
					num6 = 1;
				}
				int num7 = 0;
				if (list3.Count == 2 && list3[1].Y > list3[0].Y)
				{
					num7 = 1;
				}
				if (Math.Min(list[num6].Y, list3[num7].Y) - Math.Max(list[num4].Y, list3[num5].Y) >= 0f || Math.Abs(Math.Min(list[num6].Y, list3[num7].Y) - Math.Max(list[num4].Y, list3[num5].Y)) < Operations.ToleranceNode)
				{
					if (list[num4].Y > list3[num5].Y)
					{
						NodeListTrapezoide.Add(list[num4]);
					}
					else
					{
						NodeListTrapezoide.Add(list3[num5]);
					}
					if (list[num6].Y < list3[num7].Y)
					{
						NodeListTrapezoide.Add(list[num6]);
					}
					else
					{
						NodeListTrapezoide.Add(list3[num7]);
					}
				}
			}
			if (list2.Count > 0 && list4.Count > 0)
			{
				int num4 = 0;
				if (list2.Count == 2 && list2[1].Y < list2[0].Y)
				{
					num4 = 1;
				}
				int num5 = 0;
				if (list4.Count == 2 && list4[1].Y < list4[0].Y)
				{
					num5 = 1;
				}
				int num6 = 0;
				if (list2.Count == 2 && list2[1].Y > list2[0].Y)
				{
					num6 = 1;
				}
				int num7 = 0;
				if (list4.Count == 2 && list4[1].Y > list4[0].Y)
				{
					num7 = 1;
				}
				if (Math.Min(list2[num6].Y, list4[num7].Y) - Math.Max(list2[num4].Y, list4[num5].Y) >= 0f || Math.Abs(Math.Min(list2[num6].Y, list4[num7].Y) - Math.Max(list2[num4].Y, list4[num5].Y)) < Operations.ToleranceNode)
				{
					if (list2[num4].Y > list4[num5].Y)
					{
						NodeListTrapezoide.Add(list2[num4]);
					}
					else
					{
						NodeListTrapezoide.Add(list4[num5]);
					}
					if (list2[num6].Y < list4[num7].Y)
					{
						NodeListTrapezoide.Add(list2[num6]);
						return;
					}
					NodeListTrapezoide.Add(list4[num7]);
				}
			}
		}

		// Token: 0x060001C2 RID: 450 RVA: 0x00017E14 File Offset: 0x00016014
		private static void MergeTrapezoide(ref List<Microsoft.Xna.Framework.Vector2> NodeList, List<Microsoft.Xna.Framework.Vector2> NodeListTrapezoide, float abscissa)
		{
			List<Microsoft.Xna.Framework.Vector2> list = new List<Microsoft.Xna.Framework.Vector2>();
			for (int i = 0; i < NodeList.Count; i++)
			{
				Microsoft.Xna.Framework.Vector2 vector = new Microsoft.Xna.Framework.Vector2(NodeList[i].X, NodeList[i].Y);
				list.Add(vector);
			}
			NodeList.Clear();
			bool flag = true;
			int num = 0;
			int num2 = 0;
			while (num < list.Count || num2 < NodeListTrapezoide.Count)
			{
				if (list.Count > 0)
				{
					if (num < list.Count)
					{
						if (list[num].X < abscissa)
						{
							NodeList.Add(list[num]);
						}
					}
					else
					{
						flag = false;
					}
					num++;
				}
				if (list.Count == 0)
				{
					for (int j = 0; j < NodeListTrapezoide.Count; j++)
					{
						NodeList.Add(NodeListTrapezoide[j]);
						num2 = NodeListTrapezoide.Count;
					}
				}
				while (!flag)
				{
					if (Math.Abs(NodeListTrapezoide[num2].X - abscissa) < Operations.ToleranceNode)
					{
						NodeList.Add(NodeListTrapezoide[num2]);
					}
					num2++;
					if (num2 == NodeListTrapezoide.Count)
					{
						flag = true;
					}
				}
			}
		}

		// Token: 0x060001C3 RID: 451 RVA: 0x00017F40 File Offset: 0x00016140
		public static void ConvertVector2ToVector3(Microsoft.Xna.Framework.Vector3 vector1, Microsoft.Xna.Framework.Vector3 vector2, Microsoft.Xna.Framework.Vector3 vector3, Microsoft.Xna.Framework.Vector2 vector2d, out Microsoft.Xna.Framework.Vector3 vector)
		{
			Microsoft.Xna.Framework.Vector3 vector4 = new Microsoft.Xna.Framework.Vector3(vector2d.X, vector2d.Y, 0f);
			Matrix matrix = Operations.GetRotationMatrixFrom3Points(vector1, vector2, vector3);
			matrix = Matrix.Transpose(matrix);
			vector = Operations.MatrixPerVector3(matrix, vector4) + vector1;
		}

		// Token: 0x060001C4 RID: 452 RVA: 0x00017F8C File Offset: 0x0001618C
		public static void ConvertVector3ToVector2(Microsoft.Xna.Framework.Vector3 p1, Microsoft.Xna.Framework.Vector3 p2, Microsoft.Xna.Framework.Vector3 p3, Microsoft.Xna.Framework.Vector3 p, out Microsoft.Xna.Framework.Vector2 pOut)
		{
			Matrix rotationMatrixFrom3Points = Operations.GetRotationMatrixFrom3Points(p1, p2, p3);
			pOut = Operations.MatrixPerVector3_2d(rotationMatrixFrom3Points, p - p1);
		}

		// Token: 0x060001C5 RID: 453 RVA: 0x00017FB6 File Offset: 0x000161B6
		public static bool IsPointInPlane(Microsoft.Xna.Framework.Vector3 v1, Microsoft.Xna.Framework.Vector3 v2, Microsoft.Xna.Framework.Vector3 v3, Microsoft.Xna.Framework.Vector3 v)
		{
			return Operations.IsPointInPlane(Operations.GetPlane(v1, v2, v3), v, -1f);
		}

		// Token: 0x060001C6 RID: 454 RVA: 0x00017FCC File Offset: 0x000161CC
		public static void GetCoordinateFromIntrinsecSystem(float u, float v, Microsoft.Xna.Framework.Vector3[] vertici, out Microsoft.Xna.Framework.Vector3 point)
		{
			Microsoft.Xna.Framework.Vector2 vector = default(Microsoft.Xna.Framework.Vector2);
			Microsoft.Xna.Framework.Vector2[] array = new Microsoft.Xna.Framework.Vector2[4];
			if ((vertici[0] - vertici[3]).Length() > Operations.ToleranceNode)
			{
				for (int i = 0; i < 4; i++)
				{
					Operations.ConvertVector3ToVector2(vertici[0], vertici[1], vertici[3], vertici[i], out array[i]);
				}
				vector.X = array[0].X * Operations.m1(u, v) + array[1].X * Operations.m2(u, v) + array[2].X * Operations.m3(u, v) + array[3].X * Operations.m4(u, v);
				vector.Y = array[0].Y * Operations.m1(u, v) + array[1].Y * Operations.m2(u, v) + array[2].Y * Operations.m3(u, v) + array[3].Y * Operations.m4(u, v);
				Operations.ConvertVector2ToVector3(vertici[0], vertici[1], vertici[3], vector, out point);
			}
			else
			{
				for (int j = 0; j < 4; j++)
				{
					Operations.ConvertVector3ToVector2(vertici[0], vertici[1], vertici[2], vertici[j], out array[j]);
				}
				vector.X = array[0].X * Operations.m1(u, v) + array[1].X * Operations.m2(u, v) + array[2].X * Operations.m3(u, v) + array[3].X * Operations.m4(u, v);
				vector.Y = array[0].Y * Operations.m1(u, v) + array[1].Y * Operations.m2(u, v) + array[2].Y * Operations.m3(u, v) + array[3].Y * Operations.m4(u, v);
				Operations.ConvertVector2ToVector3(vertici[0], vertici[1], vertici[2], vector, out point);
			}
		}

		// Token: 0x060001C7 RID: 455 RVA: 0x00018224 File Offset: 0x00016424
		public static void GetCoordinateFromIntrinsecSystem(float[] u, float[] v, Microsoft.Xna.Framework.Vector3[] vertici, out Microsoft.Xna.Framework.Vector3[] points)
		{
			points = new Microsoft.Xna.Framework.Vector3[u.Length];
			for (int i = 0; i < u.Length; i++)
			{
				Operations.GetCoordinateFromIntrinsecSystem(u[i], v[i], vertici, out points[i]);
			}
		}

		// Token: 0x060001C8 RID: 456 RVA: 0x00018260 File Offset: 0x00016460
		public static void GetCoordinateFromIntrinsecSystem_new(float u, float v, Microsoft.Xna.Framework.Vector3[] vertici, out Microsoft.Xna.Framework.Vector3 point)
		{
			point = Microsoft.Xna.Framework.Vector3.Zero;
			if (vertici == null || vertici.Length != 4)
			{
				return;
			}
			float num = (u + 1f) / 2f;
			float num2 = (v + 1f) / 2f;
			Microsoft.Xna.Framework.Vector3 vector = vertici[0];
			Microsoft.Xna.Framework.Vector3 vector2 = vertici[1];
			Microsoft.Xna.Framework.Vector3 vector3 = vertici[2];
			Microsoft.Xna.Framework.Vector3 vector4 = vertici[3];
			float num3 = 1E-06f;
			if (Microsoft.Xna.Framework.Vector3.DistanceSquared(vector, vector2) >= num3 && Microsoft.Xna.Framework.Vector3.DistanceSquared(vector2, vector3) >= num3 && Microsoft.Xna.Framework.Vector3.DistanceSquared(vector3, vector4) >= num3 && Microsoft.Xna.Framework.Vector3.DistanceSquared(vector4, vector) >= num3)
			{
				point = (1f - num) * (1f - num2) * vector + num * (1f - num2) * vector2 + num * num2 * vector3 + (1f - num) * num2 * vector4;
				return;
			}
			if (num + num2 > 1f)
			{
				num = 1f - num;
				num2 = 1f - num2;
				point = (1f - num - num2) * vector2 + num * vector3 + num2 * vector4;
				return;
			}
			point = (1f - num - num2) * vector + num * vector2 + num2 * vector4;
		}

		// Token: 0x060001C9 RID: 457 RVA: 0x000183C8 File Offset: 0x000165C8
		public static void GetValueFromIntrinsecSystem(float u, float v, Microsoft.Xna.Framework.Vector3[] Values, out Microsoft.Xna.Framework.Vector3 Value)
		{
			Value = Values[0] * Operations.m1(u, v) + Values[1] * Operations.m2(u, v) + Values[2] * Operations.m3(u, v) + Values[3] * Operations.m4(u, v);
		}

		// Token: 0x060001CA RID: 458 RVA: 0x00018438 File Offset: 0x00016638
		public static void GetCoordinateFromIntrinsecSystem(int I, int NumI, int J, int NumJ, Microsoft.Xna.Framework.Vector3[] vertici, out Microsoft.Xna.Framework.Vector3 point)
		{
			float num = -1f + 2f / (float)NumI * (float)I;
			float num2 = -1f + 2f / (float)NumJ * (float)J;
			Operations.GetCoordinateFromIntrinsecSystem(num, num2, vertici, out point);
		}

		// Token: 0x060001CB RID: 459 RVA: 0x00018474 File Offset: 0x00016674
		public static int ord(Microsoft.Xna.Framework.Vector2 v1, Microsoft.Xna.Framework.Vector2 v2, Microsoft.Xna.Framework.Vector2 v3)
		{
			float num = (v3.X - v1.X) * (v2.Y - v1.Y) - (v3.Y - v1.Y) * (v2.X - v1.X);
			if (num == 0f || float.IsNaN(num))
			{
				return 0;
			}
			return Convert.ToInt32(num / Math.Abs(num));
		}

		// Token: 0x060001CC RID: 460 RVA: 0x000184D8 File Offset: 0x000166D8
		public static Microsoft.Xna.Framework.Vector2 GetVector2FromVector3(Microsoft.Xna.Framework.Vector3 v, ViewDirectionEnum dir = ViewDirectionEnum.XY)
		{
			if (dir == ViewDirectionEnum.XZ)
			{
				return new Microsoft.Xna.Framework.Vector2(v.X, v.Z);
			}
			if (dir == ViewDirectionEnum.YZ)
			{
				return new Microsoft.Xna.Framework.Vector2(v.Y, v.Z);
			}
			return new Microsoft.Xna.Framework.Vector2(v.X, v.Y);
		}

		// Token: 0x060001CD RID: 461 RVA: 0x00018524 File Offset: 0x00016724
		public static bool TestIntersectionBetweenSegments(Microsoft.Xna.Framework.Vector2 v1, Microsoft.Xna.Framework.Vector2 v2, Microsoft.Xna.Framework.Vector2 v3, Microsoft.Xna.Framework.Vector2 v4)
		{
			return Operations.ord(v1, v2, v3) * Operations.ord(v1, v2, v4) <= 0 && Operations.ord(v3, v4, v1) * Operations.ord(v3, v4, v2) <= 0;
		}

		// Token: 0x060001CE RID: 462 RVA: 0x00018554 File Offset: 0x00016754
		public static bool FindIntersectionBetweenSegments(Microsoft.Xna.Framework.Vector2 v1, Microsoft.Xna.Framework.Vector2 v2, Microsoft.Xna.Framework.Vector2 v3, Microsoft.Xna.Framework.Vector2 v4, out Microsoft.Xna.Framework.Vector2 v)
		{
			Microsoft.Xna.Framework.Vector3 vector = new Microsoft.Xna.Framework.Vector3(v1, 0f);
			Microsoft.Xna.Framework.Vector3 vector2 = new Microsoft.Xna.Framework.Vector3(v2, 0f);
			Microsoft.Xna.Framework.Vector3 vector3 = new Microsoft.Xna.Framework.Vector3(v3, 0f);
			Microsoft.Xna.Framework.Vector3 vector4 = new Microsoft.Xna.Framework.Vector3(v4, 0f);
			if ((vector - vector3).Length() < Operations.ToleranceNode || (vector2 - vector3).Length() < Operations.ToleranceNode)
			{
				v = v3;
				return true;
			}
			if ((vector - vector4).Length() < Operations.ToleranceNode || (vector2 - vector4).Length() < Operations.ToleranceNode)
			{
				v = v4;
				return true;
			}
			Microsoft.Xna.Framework.Vector4 plane = Operations.GetPlane(vector3, vector4, new Microsoft.Xna.Framework.Vector3(v3, 1f));
			Ray ray = new Ray(vector, vector2 - vector);
			Microsoft.Xna.Framework.Vector3 vector5;
			bool flag = Operations.FindIntersectionRayAndPlane(plane, ray, out vector5);
			v.X = vector5.X;
			v.Y = vector5.Y;
			return flag;
		}

		// Token: 0x060001CF RID: 463 RVA: 0x0001864B File Offset: 0x0001684B
		public static float m1(float u, float v)
		{
			return (1f - u) * (1f - v) / 4f;
		}

		// Token: 0x060001D0 RID: 464 RVA: 0x00018662 File Offset: 0x00016862
		public static float m2(float u, float v)
		{
			return (1f + u) * (1f - v) / 4f;
		}

		// Token: 0x060001D1 RID: 465 RVA: 0x00018679 File Offset: 0x00016879
		public static float m3(float u, float v)
		{
			return (1f + u) * (1f + v) / 4f;
		}

		// Token: 0x060001D2 RID: 466 RVA: 0x00018690 File Offset: 0x00016890
		public static float m4(float u, float v)
		{
			return (1f - u) * (1f + v) / 4f;
		}

		// Token: 0x060001D3 RID: 467 RVA: 0x000186A8 File Offset: 0x000168A8
		public static bool SamePlane(Microsoft.Xna.Framework.Vector3[] array)
		{
			if (array.Length > 3)
			{
				Microsoft.Xna.Framework.Vector4 plane = Operations.GetPlane(array[0], array[1], array[2]);
				bool flag = true;
				for (int i = 3; i < array.Length; i++)
				{
					flag &= Operations.IsPointInPlane(plane, array[i], -1f);
				}
				return flag;
			}
			return true;
		}

		// Token: 0x060001D4 RID: 468 RVA: 0x00018700 File Offset: 0x00016900
		public static int SolveSecondOrderEquation(double a, double b, double c, out double dlambda1, out double dlambda2)
		{
			dlambda1 = (dlambda2 = 0.0);
			double num = b * b - 4.0 * a * c;
			if (num < 0.0)
			{
				return 0;
			}
			if (a != 0.0)
			{
				dlambda1 = (-b + Math.Sqrt(num)) / (2.0 * a);
				dlambda2 = (-b - Math.Sqrt(num)) / (2.0 * a);
				return 2;
			}
			if (b != 0.0)
			{
				dlambda1 = -c / b;
				return 1;
			}
			return 0;
		}

		// Token: 0x060001D5 RID: 469 RVA: 0x00018790 File Offset: 0x00016990
		public static double Modulo(double[] v)
		{
			double num = 0.0;
			for (int i = 0; i < v.Length; i++)
			{
				num += v[i] * v[i];
			}
			return Math.Sqrt(num);
		}

		// Token: 0x060001D6 RID: 470 RVA: 0x000187C8 File Offset: 0x000169C8
		public static Microsoft.Xna.Framework.Vector3? FindNoramlToEllipse(Microsoft.Xna.Framework.Vector3 p1, Microsoft.Xna.Framework.Vector3 Center, float Rx, float Rz, float X1, float X2)
		{
			Microsoft.Xna.Framework.Vector3? vector = null;
			p1 -= Center;
			double num = (double)(p1.Y * Rz);
			double num2 = (double)(2f * (p1.X * Rx - (Operations.sq(Rz) - Operations.sq(Rx))));
			double num3 = 0.0;
			double num4 = (double)(2f * (p1.X * Rx + (Operations.sq(Rz) - Operations.sq(Rx))));
			double num5 = (double)(-(double)p1.Y * Rz);
			foreach (Complex complex in RealPolynomialRootFinder.FindRoots(new double[] { num, num2, num3, num4, num5 }))
			{
				if (complex.Imaginary == 0.0)
				{
					float num6 = Convert.ToSingle(Operations.sq(complex.Real));
					float num7 = Rx * (1f - num6) / (1f + num6);
					float num8 = Rz * (2f * Convert.ToSingle(complex.Real)) / (1f + num6);
					if (X1 <= num7 && num7 <= X2)
					{
						vector = new Microsoft.Xna.Framework.Vector3?(new Microsoft.Xna.Framework.Vector3(num7, 0f, num8) + Center);
						break;
					}
				}
			}
			return vector;
		}

		// Token: 0x060001D7 RID: 471 RVA: 0x00018928 File Offset: 0x00016B28
		public static int FindIntersectionLineAndEllipse(Microsoft.Xna.Framework.Vector3 p1, Microsoft.Xna.Framework.Vector3 p2, Microsoft.Xna.Framework.Vector3 Center, float Rx, float Rz, out Microsoft.Xna.Framework.Vector3 i1, out Microsoft.Xna.Framework.Vector3 i2)
		{
			p1 -= Center;
			p2 -= Center;
			Microsoft.Xna.Framework.Vector2 vector;
			Microsoft.Xna.Framework.Vector2 vector2;
			int num = Operations.FindIntersectionLineAndEllipse(new Microsoft.Xna.Framework.Vector2(p1.X, p1.Z), new Microsoft.Xna.Framework.Vector2(p2.X, p2.Z), Rx, Rz, out vector, out vector2);
			i1 = new Microsoft.Xna.Framework.Vector3(vector.X, 0f, vector.Y) + Center;
			i2 = new Microsoft.Xna.Framework.Vector3(vector2.X, 0f, vector2.Y) + Center;
			return num;
		}

		// Token: 0x060001D8 RID: 472 RVA: 0x000189BC File Offset: 0x00016BBC
		public static int FindIntersectionLineAndEllipse(Microsoft.Xna.Framework.Vector2 p1, Microsoft.Xna.Framework.Vector2 p2, float Rx, float Ry, out Microsoft.Xna.Framework.Vector2 i1, out Microsoft.Xna.Framework.Vector2 i2)
		{
			int num = 0;
			i1 = default(Microsoft.Xna.Framework.Vector2);
			i2 = default(Microsoft.Xna.Framework.Vector2);
			float num2;
			float num3;
			float num4;
			if (Operations.GetCoefficientLine(p1, p2, out num2, out num3, out num4))
			{
				float num5 = Operations.sq(Rx * num2) + Operations.sq(Ry * num3) - Operations.sq(num4);
				if (num5 >= 0f)
				{
					float num6 = Operations.sq(Rx * num2) + Operations.sq(Ry * num3);
					num5 = Operations.sqrt(num5);
					i1.X = -Rx * (Ry * num3 * num5 + Rx * num2 * num4) / num6;
					i1.Y = Ry * (Rx * num2 * num5 - Ry * num3 * num4) / num6;
					i2.X = Rx * (Ry * num3 * num5 - Rx * num2 * num4) / num6;
					i2.Y = -Ry * (Rx * num2 * num5 + Ry * num3 * num4) / num6;
					num = ((num5 > 0f) ? 2 : 1);
				}
			}
			else
			{
				Logger.Log("Error in Operations>FindIntersectionLineAndEllipse: unable to find solution beacuse p1 is coincident with p2", DebugLevel.WARNING);
			}
			return num;
		}

		// Token: 0x060001D9 RID: 473 RVA: 0x00018AB0 File Offset: 0x00016CB0
		public static bool GetCoefficientLine(Microsoft.Xna.Framework.Vector2 p1, Microsoft.Xna.Framework.Vector2 p2, out float a, out float b, out float c)
		{
			bool flag = false;
			a = (b = (c = 0f));
			if ((p1 - p2).Length() > 0f)
			{
				if (p1.X == p2.X)
				{
					a = 1f;
					b = 0f;
					c = -p1.X;
				}
				else if (p1.Y == p2.Y)
				{
					a = 0f;
					b = 1f;
					c = -p1.Y;
				}
				else
				{
					float num = (p2.Y - p1.Y) / (p2.X - p1.X);
					a = -num;
					b = 1f;
					c = num * p1.X - p1.Y;
				}
				flag = true;
			}
			return flag;
		}

		// Token: 0x060001DA RID: 474 RVA: 0x00018B78 File Offset: 0x00016D78
		public static double GetAbscissaDiscontinuity(IntegrationMethodEnum IntegrationMethod, int i, int NSections, double L)
		{
			double num = 0.0;
			for (int j = 0; j < i; j++)
			{
				num += Operations.GetLength(j, NSections, L, IntegrationMethod);
			}
			return num;
		}

		// Token: 0x060001DB RID: 475 RVA: 0x00018BA8 File Offset: 0x00016DA8
		public static double GetLength(int i, int NSections, double L, IntegrationMethodEnum IntegrationMethod = IntegrationMethodEnum.GaussLobatto)
		{
			if (IntegrationMethod == IntegrationMethodEnum.GaussLobatto)
			{
				return Operations.GetLengthGaussLobatto(i, NSections, L);
			}
			if (IntegrationMethod != IntegrationMethodEnum.NewtonCotes)
			{
				return 0.0;
			}
			return Operations.GetLengthNewtonCotes(NSections, L);
		}

		// Token: 0x060001DC RID: 476 RVA: 0x00018BCD File Offset: 0x00016DCD
		private static double GetLengthNewtonCotes(int NSections, double L)
		{
			return 1.0 / (double)NSections * L;
		}

		// Token: 0x060001DD RID: 477 RVA: 0x00018BE0 File Offset: 0x00016DE0
		private static double GetLengthGaussLobatto(int i, int NSections, double L)
		{
			i++;
			double num = 0.0;
			if (NSections == 2)
			{
				if (i == 1)
				{
					num = 1.0;
				}
				else if (i == 2)
				{
					num = 1.0;
				}
			}
			else if (NSections == 3)
			{
				if (i == 1)
				{
					num = 0.3333333333333333;
				}
				else if (i == 2)
				{
					num = 1.3333333333333333;
				}
				else if (i == 3)
				{
					num = 0.3333333333333333;
				}
			}
			else if (NSections == 4)
			{
				if (i == 1)
				{
					num = 0.166666666;
				}
				else if (i == 2)
				{
					num = 0.833333333;
				}
				else if (i == 3)
				{
					num = 0.833333333;
				}
				else if (i == 4)
				{
					num = 0.166666666;
				}
			}
			else if (NSections == 5)
			{
				if (i == 1)
				{
					num = 0.1;
				}
				else if (i == 2)
				{
					num = 0.544444444;
				}
				else if (i == 3)
				{
					num = 0.711111111;
				}
				else if (i == 4)
				{
					num = 0.544444444;
				}
				else if (i == 5)
				{
					num = 0.1;
				}
			}
			else if (NSections == 6)
			{
				if (i == 1)
				{
					num = 0.06666666;
				}
				else if (i == 2)
				{
					num = 0.37847496;
				}
				else if (i == 3)
				{
					num = 0.55485838;
				}
				else if (i == 4)
				{
					num = 0.55485838;
				}
				else if (i == 5)
				{
					num = 0.37847496;
				}
				else if (i == 6)
				{
					num = 0.06666666;
				}
			}
			else if (NSections == 7)
			{
				if (i == 1)
				{
					num = 0.04761904;
				}
				else if (i == 2)
				{
					num = 0.27682604;
				}
				else if (i == 3)
				{
					num = 0.43174538;
				}
				else if (i == 4)
				{
					num = 0.48761904;
				}
				else if (i == 5)
				{
					num = 0.43174538;
				}
				else if (i == 6)
				{
					num = 0.27682604;
				}
				else if (i == 7)
				{
					num = 0.04761904;
				}
			}
			else if (NSections == 8)
			{
				if (i == 1 || i == 8)
				{
					num = 0.03571428;
				}
				else if (i == 2 || i == 7)
				{
					num = 0.21070422;
				}
				else if (i == 3 || i == 6)
				{
					num = 0.3411227;
				}
				else if (i == 4 || i == 5)
				{
					num = 0.4124588;
				}
			}
			else if (NSections == 9)
			{
				if (i == 1 || i == 9)
				{
					num = 0.0277777778;
				}
				else if (i == 2 || i == 8)
				{
					num = 0.1654953616;
				}
				else if (i == 3 || i == 7)
				{
					num = 0.2745387126;
				}
				else if (i == 4 || i == 6)
				{
					num = 0.346428511;
				}
				else if (i == 5)
				{
					num = 0.3715192744;
				}
			}
			else if (NSections == 10)
			{
				if (i == 1)
				{
					num = 0.02222222222222;
				}
				else if (i == 2)
				{
					num = 0.13330599085107;
				}
				else if (i == 3)
				{
					num = 0.22488934206313;
				}
				else if (i == 4)
				{
					num = 0.29204268367968;
				}
				else if (i == 5)
				{
					num = 0.3275397611839;
				}
				else if (i == 6)
				{
					num = 0.3275397611839;
				}
				else if (i == 7)
				{
					num = 0.29204268367968;
				}
				else if (i == 8)
				{
					num = 0.22488934206313;
				}
				else if (i == 9)
				{
					num = 0.13330599085107;
				}
				else if (i == 10)
				{
					num = 0.02222222222222;
				}
			}
			else if (NSections == 11)
			{
				if (i == 1)
				{
					num = 0.01818181818182;
				}
				else if (i == 2)
				{
					num = 0.109612273267;
				}
				else if (i == 3)
				{
					num = 0.18716988178031;
				}
				else if (i == 4)
				{
					num = 0.24804810426403;
				}
				else if (i == 5)
				{
					num = 0.28687912477901;
				}
				else if (i == 6)
				{
					num = 0.30021759545569;
				}
				else if (i == 7)
				{
					num = 0.28687912477901;
				}
				else if (i == 8)
				{
					num = 0.24804810426403;
				}
				else if (i == 9)
				{
					num = 0.18716988178031;
				}
				else if (i == 10)
				{
					num = 0.109612273267;
				}
				else if (i == 11)
				{
					num = 0.01818181818182;
				}
			}
			else if (NSections == 12)
			{
				if (i == 1)
				{
					num = 0.01515151515152;
				}
				else if (i == 2)
				{
					num = 0.0916845174132;
				}
				else if (i == 3)
				{
					num = 0.15797470556437;
				}
				else if (i == 4)
				{
					num = 0.21250841776102;
				}
				else if (i == 5)
				{
					num = 0.2512756031992;
				}
				else if (i == 6)
				{
					num = 0.2714052409107;
				}
				else if (i == 7)
				{
					num = 0.2714052409107;
				}
				else if (i == 8)
				{
					num = 0.2512756031992;
				}
				else if (i == 9)
				{
					num = 0.21250841776102;
				}
				else if (i == 10)
				{
					num = 0.15797470556437;
				}
				else if (i == 11)
				{
					num = 0.0916845174132;
				}
				else if (i == 12)
				{
					num = 0.01515151515152;
				}
			}
			else if (NSections == 13)
			{
				if (i == 1)
				{
					num = 0.01282051282051;
				}
				else if (i == 2)
				{
					num = 0.07780168674682;
				}
				else if (i == 3)
				{
					num = 0.13498192668961;
				}
				else if (i == 4)
				{
					num = 0.18364686520355;
				}
				else if (i == 5)
				{
					num = 0.22076779356611;
				}
				else if (i == 6)
				{
					num = 0.24401579030668;
				}
				else if (i == 7)
				{
					num = 0.25193084933345;
				}
				else if (i == 8)
				{
					num = 0.24401579030668;
				}
				else if (i == 9)
				{
					num = 0.22076779356611;
				}
				else if (i == 10)
				{
					num = 0.18364686520355;
				}
				else if (i == 11)
				{
					num = 0.13498192668961;
				}
				else if (i == 12)
				{
					num = 0.07780168674682;
				}
				else if (i == 13)
				{
					num = 0.01282051282051;
				}
			}
			else if (NSections == 14)
			{
				if (i == 1)
				{
					num = 0.01098901098901;
				}
				else if (i == 2)
				{
					num = 0.06683728449768;
				}
				else if (i == 3)
				{
					num = 0.11658665589871;
				}
				else if (i == 4)
				{
					num = 0.16002185176295;
				}
				else if (i == 5)
				{
					num = 0.19482614937342;
				}
				else if (i == 6)
				{
					num = 0.21912625300977;
				}
				else if (i == 7)
				{
					num = 0.23161279446846;
				}
				else if (i == 8)
				{
					num = 0.23161279446846;
				}
				else if (i == 9)
				{
					num = 0.21912625300977;
				}
				else if (i == 10)
				{
					num = 0.19482614937342;
				}
				else if (i == 11)
				{
					num = 0.16002185176295;
				}
				else if (i == 12)
				{
					num = 0.11658665589871;
				}
				else if (i == 13)
				{
					num = 0.06683728449768;
				}
				else if (i == 14)
				{
					num = 0.01098901098901;
				}
			}
			else if (NSections == 15)
			{
				if (i == 1)
				{
					num = 0.00952380952381;
				}
				else if (i == 2)
				{
					num = 0.0580298930286;
				}
				else if (i == 3)
				{
					num = 0.10166007032572;
				}
				else if (i == 4)
				{
					num = 0.14051169980243;
				}
				else if (i == 5)
				{
					num = 0.1727896472536;
				}
				else if (i == 6)
				{
					num = 0.19698723596461;
				}
				else if (i == 7)
				{
					num = 0.21197358592682;
				}
				else if (i == 8)
				{
					num = 0.21704811634882;
				}
				else if (i == 9)
				{
					num = 0.21197358592682;
				}
				else if (i == 10)
				{
					num = 0.19698723596461;
				}
				else if (i == 11)
				{
					num = 0.1727896472536;
				}
				else if (i == 12)
				{
					num = 0.14051169980243;
				}
				else if (i == 13)
				{
					num = 0.10166007032572;
				}
				else if (i == 14)
				{
					num = 0.0580298930286;
				}
				else if (i == 15)
				{
					num = 0.00952380952381;
				}
			}
			else if (NSections == 16)
			{
				if (i == 1)
				{
					num = 0.00833333333333;
				}
				else if (i == 2)
				{
					num = 0.05085036100592;
				}
				else if (i == 3)
				{
					num = 0.08939369732593;
				}
				else if (i == 4)
				{
					num = 0.12425538213251;
				}
				else if (i == 5)
				{
					num = 0.15402698080716;
				}
				else if (i == 6)
				{
					num = 0.1774919133917;
				}
				else if (i == 7)
				{
					num = 0.1936900238252;
				}
				else if (i == 8)
				{
					num = 0.20195830817823;
				}
				else if (i == 9)
				{
					num = 0.20195830817823;
				}
				else if (i == 10)
				{
					num = 0.1936900238252;
				}
				else if (i == 11)
				{
					num = 0.1774919133917;
				}
				else if (i == 12)
				{
					num = 0.15402698080716;
				}
				else if (i == 13)
				{
					num = 0.12425538213251;
				}
				else if (i == 14)
				{
					num = 0.08939369732593;
				}
				else if (i == 15)
				{
					num = 0.05085036100592;
				}
				else if (i == 16)
				{
					num = 0.00833333333333;
				}
			}
			else if (NSections == 17)
			{
				if (i == 1)
				{
					num = 0.00735294117647;
				}
				else if (i == 2)
				{
					num = 0.04492194054325;
				}
				else if (i == 3)
				{
					num = 0.07919827050369;
				}
				else if (i == 4)
				{
					num = 0.11059290900703;
				}
				else if (i == 5)
				{
					num = 0.13798774620193;
				}
				else if (i == 6)
				{
					num = 0.16039466199762;
				}
				else if (i == 7)
				{
					num = 0.17700425351566;
				}
				else if (i == 8)
				{
					num = 0.18721633967762;
				}
				else if (i == 9)
				{
					num = 0.19066187475347;
				}
				else if (i == 10)
				{
					num = 0.18721633967762;
				}
				else if (i == 11)
				{
					num = 0.17700425351566;
				}
				else if (i == 12)
				{
					num = 0.16039466199762;
				}
				else if (i == 13)
				{
					num = 0.13798774620193;
				}
				else if (i == 14)
				{
					num = 0.11059290900703;
				}
				else if (i == 15)
				{
					num = 0.07919827050369;
				}
				else if (i == 16)
				{
					num = 0.04492194054325;
				}
				else if (i == 17)
				{
					num = 0.00735294117647;
				}
			}
			else if (NSections == 18)
			{
				if (i == 1)
				{
					num = 0.00653594771242;
				}
				else if (i == 2)
				{
					num = 0.03997062881091;
				}
				else if (i == 3)
				{
					num = 0.07063716688563;
				}
				else if (i == 4)
				{
					num = 0.0990162717175;
				}
				else if (i == 5)
				{
					num = 0.12421053313297;
				}
				else if (i == 6)
				{
					num = 0.1454119615738;
				}
				else if (i == 7)
				{
					num = 0.1619395172376;
				}
				else if (i == 8)
				{
					num = 0.17326210948946;
				}
				else if (i == 9)
				{
					num = 0.1790158634397;
				}
				else if (i == 10)
				{
					num = 0.1790158634397;
				}
				else if (i == 11)
				{
					num = 0.17326210948946;
				}
				else if (i == 12)
				{
					num = 0.1619395172376;
				}
				else if (i == 13)
				{
					num = 0.1454119615738;
				}
				else if (i == 14)
				{
					num = 0.12421053313297;
				}
				else if (i == 15)
				{
					num = 0.0990162717175;
				}
				else if (i == 16)
				{
					num = 0.07063716688563;
				}
				else if (i == 17)
				{
					num = 0.03997062881091;
				}
				else if (i == 18)
				{
					num = 0.00653594771242;
				}
			}
			else if (NSections == 19)
			{
				if (i == 1)
				{
					num = 0.00584795321637;
				}
				else if (i == 2)
				{
					num = 0.03579336518618;
				}
				else if (i == 3)
				{
					num = 0.06338189176263;
				}
				else if (i == 4)
				{
					num = 0.08913175709921;
				}
				else if (i == 5)
				{
					num = 0.11231534147731;
				}
				else if (i == 6)
				{
					num = 0.13226728044875;
				}
				else if (i == 7)
				{
					num = 0.14841394259594;
				}
				else if (i == 8)
				{
					num = 0.16029092404406;
				}
				else if (i == 9)
				{
					num = 0.16755658452714;
				}
				else if (i == 10)
				{
					num = 0.17000191928483;
				}
				else if (i == 11)
				{
					num = 0.16755658452714;
				}
				else if (i == 12)
				{
					num = 0.16029092404406;
				}
				else if (i == 13)
				{
					num = 0.14841394259594;
				}
				else if (i == 14)
				{
					num = 0.13226728044875;
				}
				else if (i == 15)
				{
					num = 0.11231534147731;
				}
				else if (i == 16)
				{
					num = 0.08913175709921;
				}
				else if (i == 17)
				{
					num = 0.06338189176263;
				}
				else if (i == 18)
				{
					num = 0.03579336518618;
				}
				else if (i == 19)
				{
					num = 0.00584795321637;
				}
			}
			else if (NSections >= 20)
			{
				if (i == 1)
				{
					num = 0.00526315789474;
				}
				else if (i == 2)
				{
					num = 0.03223712318849;
				}
				else if (i == 3)
				{
					num = 0.05718180212757;
				}
				else if (i == 4)
				{
					num = 0.08063176399612;
				}
				else if (i == 5)
				{
					num = 0.10199149969945;
				}
				else if (i == 6)
				{
					num = 0.12070922762867;
				}
				else if (i == 7)
				{
					num = 0.13630048235872;
				}
				else if (i == 8)
				{
					num = 0.14836155407092;
				}
				else if (i == 9)
				{
					num = 0.15658010264748;
				}
				else if (i == 10)
				{
					num = 0.16074328638785;
				}
				else if (i == 11)
				{
					num = 0.16074328638785;
				}
				else if (i == 12)
				{
					num = 0.15658010264748;
				}
				else if (i == 13)
				{
					num = 0.14836155407092;
				}
				else if (i == 14)
				{
					num = 0.13630048235872;
				}
				else if (i == 15)
				{
					num = 0.12070922762867;
				}
				else if (i == 16)
				{
					num = 0.10199149969945;
				}
				else if (i == 17)
				{
					num = 0.08063176399612;
				}
				else if (i == 18)
				{
					num = 0.05718180212757;
				}
				else if (i == 19)
				{
					num = 0.03223712318849;
				}
				else if (i == 20)
				{
					num = 0.00526315789474;
				}
			}
			return num * 0.5 * L;
		}

		// Token: 0x060001DE RID: 478 RVA: 0x00019BFA File Offset: 0x00017DFA
		public static double GetAbscissa(int i, int NSections, double L, IntegrationMethodEnum IntegrationMethod = IntegrationMethodEnum.GaussLobatto)
		{
			if (IntegrationMethod == IntegrationMethodEnum.GaussLobatto)
			{
				return Operations.GetAbscissaGaussLobatto(i, NSections, L);
			}
			if (IntegrationMethod != IntegrationMethodEnum.NewtonCotes)
			{
				return 0.0;
			}
			return Operations.GetAbscissaNewtonCotes(i, NSections, L);
		}

		// Token: 0x060001DF RID: 479 RVA: 0x00019C20 File Offset: 0x00017E20
		private static double GetAbscissaNewtonCotes(int i, int NSections, double L)
		{
			return L / (double)NSections * (0.5 + Convert.ToDouble(i));
		}

		// Token: 0x060001E0 RID: 480 RVA: 0x00019C38 File Offset: 0x00017E38
		private static double GetAbscissaGaussLobatto(int i, int NSections, double L)
		{
			double num = 0.0;
			i++;
			if (NSections == 2)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 3)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 4)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.4472136);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, 0.4472136);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 5)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.65465367);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, 0.65465367);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 6)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.76505532);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.28523152);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, 0.28523152);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, 0.76505532);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 7)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.8302239);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.46884879);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, 0.46884879);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, 0.8302239);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 8)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.87174015);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.59170018);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.20929922);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, 0.20929922);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, 0.59170018);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, 0.87174015);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 9)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.8997579954);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.6771862795);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.3631174638);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, 0.3631174638);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, 0.6771862795);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, 0.8997579954);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 10)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.9195339082);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.7387738651);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.4779249498);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.1652789577);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, 0.1652789577);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, 0.4779249498);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, 0.7387738651);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 0.9195339082);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 11)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.9340014304);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.7844834736);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.5652353269);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.2957581356);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, 0.2957581356);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, 0.5652353269);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 0.7844834736);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.9340014304);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 12)
			{
				if ((double)i == num)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.9448992722);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.8192793216);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.632876153);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.3995309409);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.1365529328);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, 0.1365529328);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, 0.3995309409);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 0.632876153);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.8192793216);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.9448992722);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 13)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.9533098466);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.8463475646);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.686188469);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.482909821);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.2492869301);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, 0.2492869301);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 0.482909821);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.686188469);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.8463475646);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 0.9533098466);
				}
				else if (i == 13)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 14)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.9599350452);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.8678010538);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.728868599);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.5506394029);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.3427240133);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, -0.1163318688);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, 0.1163318688);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 0.3427240133);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.5506394029);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.728868599);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 0.8678010538);
				}
				else if (i == 13)
				{
					num = Operations.GaussLobattoRif(L, 0.9599350452);
				}
				else if (i == 14)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 15)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.9652459265);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.8850820442);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.7635196899);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.6062532054);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.4206380547);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, -0.2153539553);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 0.2153539553);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.4206380547);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.6062532054);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 0.7635196899);
				}
				else if (i == 13)
				{
					num = Operations.GaussLobattoRif(L, 0.8850820442);
				}
				else if (i == 14)
				{
					num = Operations.GaussLobattoRif(L, 0.9652459265);
				}
				else if (i == 15)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 16)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.9695680462);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.899200533);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.7920082918);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.6523887028);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.4860594218);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, -0.2998304689);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, -0.1013262735);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 0.1013262735);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.2998304689);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.4860594218);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 0.6523887028);
				}
				else if (i == 13)
				{
					num = Operations.GaussLobattoRif(L, 0.7920082918);
				}
				else if (i == 14)
				{
					num = Operations.GaussLobattoRif(L, 0.899200533);
				}
				else if (i == 15)
				{
					num = Operations.GaussLobattoRif(L, 0.9695680462);
				}
				else if (i == 16)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 17)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.9731321766);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.9108799959);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.8156962512);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.6910289806);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.5413853993);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, -0.3721744335);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, -0.1895119735);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.1895119735);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.3721744335);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 0.5413853993);
				}
				else if (i == 13)
				{
					num = Operations.GaussLobattoRif(L, 0.6910289806);
				}
				else if (i == 14)
				{
					num = Operations.GaussLobattoRif(L, 0.8156962512);
				}
				else if (i == 15)
				{
					num = Operations.GaussLobattoRif(L, 0.9108799959);
				}
				else if (i == 16)
				{
					num = Operations.GaussLobattoRif(L, 0.9731321766);
				}
				else if (i == 17)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 18)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.976105557);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.920649185);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.835593535);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.723679329);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.588504834);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, -0.434415037);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, -0.266362653);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, -0.089749093);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.089749093);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.266362653);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 0.434415037);
				}
				else if (i == 13)
				{
					num = Operations.GaussLobattoRif(L, 0.588504834);
				}
				else if (i == 14)
				{
					num = Operations.GaussLobattoRif(L, 0.723679329);
				}
				else if (i == 15)
				{
					num = Operations.GaussLobattoRif(L, 0.835593535);
				}
				else if (i == 16)
				{
					num = Operations.GaussLobattoRif(L, 0.920649185);
				}
				else if (i == 17)
				{
					num = Operations.GaussLobattoRif(L, 0.976105557);
				}
				else if (i == 18)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections == 19)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.978611766);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.928901528);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.852460578);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.751494203);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.628908137);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, -0.488229286);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, -0.333504848);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, -0.169186023);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, 0.0);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.169186023);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 0.333504848);
				}
				else if (i == 13)
				{
					num = Operations.GaussLobattoRif(L, 0.488229286);
				}
				else if (i == 14)
				{
					num = Operations.GaussLobattoRif(L, 0.628908137);
				}
				else if (i == 15)
				{
					num = Operations.GaussLobattoRif(L, 0.751494203);
				}
				else if (i == 16)
				{
					num = Operations.GaussLobattoRif(L, 0.852460578);
				}
				else if (i == 17)
				{
					num = Operations.GaussLobattoRif(L, 0.928901528);
				}
				else if (i == 18)
				{
					num = Operations.GaussLobattoRif(L, 0.978611766);
				}
				else if (i == 19)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			else if (NSections >= 20)
			{
				if (i == 1)
				{
					num = Operations.GaussLobattoRif(L, -1.0);
				}
				else if (i == 2)
				{
					num = Operations.GaussLobattoRif(L, -0.980743705);
				}
				else if (i == 3)
				{
					num = Operations.GaussLobattoRif(L, -0.935934499);
				}
				else if (i == 4)
				{
					num = Operations.GaussLobattoRif(L, -0.866877978);
				}
				else if (i == 5)
				{
					num = Operations.GaussLobattoRif(L, -0.775368261);
				}
				else if (i == 6)
				{
					num = Operations.GaussLobattoRif(L, -0.663776402);
				}
				else if (i == 7)
				{
					num = Operations.GaussLobattoRif(L, -0.534992864);
				}
				else if (i == 8)
				{
					num = Operations.GaussLobattoRif(L, -0.392353184);
				}
				else if (i == 9)
				{
					num = Operations.GaussLobattoRif(L, -0.239551706);
				}
				else if (i == 10)
				{
					num = Operations.GaussLobattoRif(L, -0.080545937);
				}
				else if (i == 11)
				{
					num = Operations.GaussLobattoRif(L, 0.080545937);
				}
				else if (i == 12)
				{
					num = Operations.GaussLobattoRif(L, 0.239551706);
				}
				else if (i == 13)
				{
					num = Operations.GaussLobattoRif(L, 0.392353184);
				}
				else if (i == 14)
				{
					num = Operations.GaussLobattoRif(L, 0.534992864);
				}
				else if (i == 15)
				{
					num = Operations.GaussLobattoRif(L, 0.663776402);
				}
				else if (i == 16)
				{
					num = Operations.GaussLobattoRif(L, 0.775368261);
				}
				else if (i == 17)
				{
					num = Operations.GaussLobattoRif(L, 0.866877978);
				}
				else if (i == 18)
				{
					num = Operations.GaussLobattoRif(L, 0.935934499);
				}
				else if (i == 19)
				{
					num = Operations.GaussLobattoRif(L, 0.980743705);
				}
				else if (i == 20)
				{
					num = Operations.GaussLobattoRif(L, 1.0);
				}
			}
			return num;
		}

		// Token: 0x060001E1 RID: 481 RVA: 0x0001B1B7 File Offset: 0x000193B7
		private static double GaussLobattoRif(double L, double x_vetti)
		{
			return L / 2.0 * (1.0 + x_vetti);
		}

		// Token: 0x040000FE RID: 254
		public const float MaxValue = 1E+30f;

		// Token: 0x040000FF RID: 255
		public const float MinValue = -1E+30f;

		// Token: 0x04000100 RID: 256
		public static float g = 980.6f;

		// Token: 0x04000101 RID: 257
		public const float deg2rad = 0.017453292f;

		// Token: 0x04000102 RID: 258
		public const float rad2deg = 57.295776f;

		// Token: 0x04000103 RID: 259
		public const float PI = 3.1415927f;
	}
}
