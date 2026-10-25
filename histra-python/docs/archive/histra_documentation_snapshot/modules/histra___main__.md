# `histra.__main__`

**Source:** `histra/__main__.py`  
**Size:** 78 lines  
**Layer:** Package entry points and command-line inspection tooling.

## Purpose

Implements `python -m histra`: loads an HRX model, assembles the initial stiffness matrix, extracts stored displacements, prints statistics, and optionally writes JSON.

### Source docstring

HiStrA-Python: structural analysis solver CLI.

Usage:
    python -m histra model.hrx [--output results.json]

## Dependencies

**Internal:** `histra.io.hr_loader`, `histra.solver.assembler`  
**Python/third-party:** `json`, `numpy`, `sys`, `time`  

## API and implementation units

### Module functions

| Function | Description |
|---|---|
| `def main()` | Main. |

## Known issues affecting this module

- **ISSUE-26 — CLI summary assumes nonzero model size and nonempty arrays** (Low). See [ISSUES.md](../ISSUES.md#issue-26).

## Related documentation

- [Architecture](../ARCHITECTURE.md)
- [Solver flow](../SOLVER_FLOW.md)
- [Module index](../MODULE_INDEX.md)
- [Issues report](../ISSUES.md)
