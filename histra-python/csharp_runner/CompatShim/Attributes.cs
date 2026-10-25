using System;

namespace SirioSoft
{
    [AttributeUsage(AttributeTargets.All, AllowMultiple = true)]
    public class SerializeAttribute : Attribute
    {
        public SerializeAttribute(params object[] args) { }
    }
}

namespace UtilityLibrary.Tipi
{
    [AttributeUsage(AttributeTargets.All, AllowMultiple = true)]
    public class SavedToDbAttribute : Attribute
    {
        public SavedToDbAttribute(params object[] args) { }
    }
}
