using System;

namespace EventLoggerAndDebug
{
    public enum DebugLevel
    {
        INFO,
        WARNING,
        CRITICAL
    }

    public static class Logger
    {
        public static void Log(string message, DebugLevel level = DebugLevel.INFO) { }
        public static void Log(params object[] parts) { }
    }
}
