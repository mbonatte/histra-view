# HiStrA Python Solver Package

Core implementation package for the HiStrA Python nonlinear and modal solver.

## Overview

This directory contains the Python package modules:
- `elements/`: Quad and Interface structural element implementations and state containers.
- `io/`: HRX model file loader and C# SQLite Results database reader.
- `model/`: Structural data model (Nodes, Quads, Interfaces, Springs, Restraints, Materials, Loads).
- `preprocessing/`: Automatic model preparation, contact detection, interface generation, and spring assignment.
- `solver/`: Nonlinear static integrators (LoadControl, ArcLength, ArcLengthLinear), Newton algorithms, line searches, P-Delta assembly, modal solver, and compiled hysteretic batch kernels.
- `springs/`: Hysteretic, Coulomb, and elastic spring constitutive laws.
- `tools/`: Benchmark drivers, verification harnesses, and distribution manifest utilities.
- `types/`: Common types, enums, and data containers.

## Documentation

Comprehensive documentation, usage guides, feature matrices, and benchmark reports are located in the top-level [`docs/`](../docs/) directory.
