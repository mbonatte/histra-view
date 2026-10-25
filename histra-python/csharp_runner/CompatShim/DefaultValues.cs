using System;

namespace UtilityLibrary
{
    public static class DefaultValues
    {
        public static float ToleranceNode = 1f;
        public static float TolerancePlane = 1f;
        public static float MesherAngularToll = 0.0001f;
        public static double TollZeroForce = 0.0001;

        public static bool RunAsParallel(int count) => false;
    }
}
