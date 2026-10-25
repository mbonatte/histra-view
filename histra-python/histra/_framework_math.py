"""Transcendental arithmetic for source-sensitive C# fibre integration.

The Windows .NET Framework runtime used by HiStrA 2026.1.1 has its own CRT
power and arctangent implementations. LLVM may replace pow(x, 0.5) with sqrt(x), which changes
cancellation-sensitive roots. Register the CRT symbol at import, so cached
Numba code resolves a fresh process-local address instead of caching a pointer.
Other platforms retain their standard arithmetic; bitwise agreement with
the Windows runtime is not guaranteed there.
"""
import ctypes
import sys
import math
from numba import njit, types
from llvmlite import binding
_runtime = None
if sys.platform == "win32":
    # Current Framework servicing uses its private UCRT; older installations
    # use the VC120 CRT. They differ in cancellation-sensitive power results.
    for library in ("ucrtbase_clr0400.dll", "msvcr120_clr0400.dll"):
        try:
            _runtime = ctypes.CDLL(library, winmode=0x800)
            break
        except OSError:
            pass
POWER_BACKEND = "dotnet-framework-crt" if _runtime is not None else "platform-math"

if _runtime is not None:
    _native_pow = _runtime.pow
    _native_pow.argtypes = [ctypes.c_double, ctypes.c_double]
    _native_pow.restype = ctypes.c_double
    binding.add_symbol("histra_clr_framework_pow", ctypes.cast(_native_pow, ctypes.c_void_p).value)
    _compiled_pow = types.ExternalFunction("histra_clr_framework_pow", types.float64(types.float64, types.float64))
    _native_atan = _runtime.atan
    _native_atan.argtypes = [ctypes.c_double]
    _native_atan.restype = ctypes.c_double
    binding.add_symbol("histra_clr_framework_atan", ctypes.cast(_native_atan, ctypes.c_void_p).value)
    _compiled_atan = types.ExternalFunction("histra_clr_framework_atan", types.float64(types.float64))
    @njit(cache=True)
    def csharp_atan(value):
        return _compiled_atan(value)
    @njit(cache=True)
    def csharp_pow(value, exponent):
        return _compiled_pow(value, exponent)
else:
    @njit(cache=True)
    def csharp_pow(value, exponent):
        return math.pow(value, exponent)

if _runtime is None:
    @njit(cache=True)
    def csharp_atan(value):
        return math.atan(value)
