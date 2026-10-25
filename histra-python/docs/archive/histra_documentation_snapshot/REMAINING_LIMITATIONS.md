# Remaining Limitations

1. Vert analysis 1 still diverges from the C# committed displacement path after its roundoff-exact first step; steps 2–5 exceed the 1e-4 relative target.
2. The C# SQLite schema does not store ArcLength multipliers per committed public step, so Live Load multiplier error cannot be independently measured.
3. Analysis 22 ends on the configured maximum-displacement condition and therefore has compact public spring rows but no complete final restart state for further chaining.
4. The supplied C# line-load source and the binary/database behavior appear different; Python follows measured SQLite behavior and documents the deviation.
5. Intermediate restart remains non-lossless because `SpringStatesTmp` omits constitutive history.
6. P-Delta is not implemented and raises explicitly when requested.
7. Load families other than the validated self-weight and supplied Quad line-load path remain incomplete and must not silently become zero.
8. Modal and dynamic analyses remain outside the validated solver path.
9. Python reads C# results but does not yet write a complete C#-compatible `.Results` database.
10. Raw-HRX preprocessing currently supports four-node masonry Quads, exact full-edge contacts, and fixed line restraints; partial polygon contacts, slave/partition models, and other computational element families remain unsupported.
11. Generated computational data is currently held in memory and is not written back to an HRX file, so a new process repeats preprocessing for an unlocked model.
12. The complete 87-step ArcLength benchmark remains opt-in even though the optimized standalone run is substantially faster, because it is still a long numerical acceptance test relative to the unit suite.
