---
name: histra-hrx-builder
description: >-
  Create, inspect, and configure HiStrA bridge .hrx structural models (parametric
  geometry, Advanced mode masonry constitutive laws, analyses, stages, and load
  functions) using the self-describing CLI (hrx_cli.py) or MCP server (mcp_server.py)
  without reading internal solver or builder source code.
---

# HiStrA `.hrx` Model Builder & Editor Skill

Use this skill whenever you need to generate a new HiStrA `.hrx` masonry arch bridge model, inspect an existing `.hrx` file's materials and analyses, or modify material constitutive laws (Advanced mode masonry), analyses, stages, or load functions.

You do **not** need to read the internal codebase (`histra_builder/` or `histra-python/`) to build or configure `.hrx` files. Use either the **CLI** (`hrx_cli.py`) or the **MCP server** (`mcp_server.py`) located in `/home/mauricio/coding/histra-bridge/histra-view/model-view/`.

---

## 1. Quick-Start CLI Commands (`hrx_cli.py`)

Run all commands from `/home/mauricio/coding/histra-bridge/histra-view/model-view/`:

```bash
# 1. Inspect available templates, geometry defaults, and Advanced mode masonry law enums
.venv/bin/python hrx_cli.py catalog
.venv/bin/python hrx_cli.py catalog --section masonry-schema

# 2. Export a starter JSON bridge specification
.venv/bin/python hrx_cli.py init-spec -o bridge_spec.json

# 3. Generate a new .hrx bridge from a JSON spec or inline dot-path overrides
.venv/bin/python hrx_cli.py create -o bridge.hrx \
  --set nl=150 \
  --set spans.0.L=800 \
  --set spans.0.f=350 \
  --set piers.0.H=250

# 4. Inspect all materials, analyses, and loads in an .hrx file
.venv/bin/python hrx_cli.py inspect bridge.hrx
.venv/bin/python hrx_cli.py inspect bridge.hrx --section materials

# 5. Configure an Advanced-mode masonry material in an .hrx file
.venv/bin/python hrx_cli.py edit-material bridge.hrx -o bridge.hrx \
  --key 18 \
  --orthotropic-rocking false \
  --set Ehor=320 \
  --set TensileCurveType=Exponential \
  --set FtmHor=0.025 \
  --set Gt=0.002 \
  --set CompressiveCurveType=Parabolic \
  --set FmHor=0.45 \
  --set Gc=0.05 \
  --set ConstitutiveLawMasonryShear=ElastoPlasticFractureEnergyFixed \
  --set CriterioSnervamento=Cacovic \
  --set fvk0d=0.015 \
  --sliding-law LinearSoftening \
  --set CohesionSlidingHor=0.02 \
  --set FrictionRatioSlidingHor=0.5 \
  --set Gs=0.01

# 6. Add, duplicate, delete, or edit an analysis or nested stage
.venv/bin/python hrx_cli.py edit-analysis bridge.hrx -o bridge.hrx \
  --name "Vert" \
  --set MaxIterations=50 \
  --set ConvergenceTolerance=0.0005 \
  --set AdapticConvergenceCriteria=Work
```

---

## 2. Units Convention (Base C# / HRX Units)

All raw `.hrx` material and geometry attributes use the native HiStrA C# base unit system:
- **Length**: `cm`
- **Force**: `kN`
- **Stress / Modulus** ($E$, $G$, $f_m$, $f_t$, $\tau_0$, $c$): `kN/cm²` ($1\text{ MPa} = 0.1\text{ kN/cm}^2$, so $3000\text{ MPa} = 300\text{ kN/cm}^2$)
- **Fracture energy** ($G_t$, $G_c$, $G_s$): `kN/cm` ($1\text{ N/mm} = 0.01\text{ kN/cm}$)
- **Specific weight** (`w`): `kN/cm³` ($1\text{ kN/m}^3 = 10^{-6}\text{ kN/cm}^3$, so $18\text{ kN/m}^3 = 1.8\times 10^{-5}\text{ kN/cm}^3$)

---

## 3. Advanced Mode Masonry Constitutive Laws Reference

When configuring a masonry material (`edit-material` or `hrx_edit_material`), all materials use **Advanced mode** (`SimpleMode=false`) organized into four sections (`hrx_cli.py catalog --section masonry-schema`):

### General
- `Name`, `Description`: Material name and description (`string`)
- `w`: Specific weight $W$ (`kN/cm³`)
- `Ehor`, `Gd`, `FmHor`, `FtmHor`, `fvk0d`, `CohesionSlidingHor`, `FrictionRatioSlidingHor`, `FrictionRatioShear`

### Rocking (Flexural / Normal Behaviour)
- `ortpf`: Orthotropic rocking (`true` / `false`, or `--orthotropic-rocking`).
- `Ehor`, `Ever`: Young's modulus $E$ (`kN/cm²`).
- `TensileCurveType` (and `TensileCurveTypeVertical` when `ortpf=true`):
  - `Elastic`: Only `Ehor`/`Ever` used.
  - `LinearHardening`: Uses `FtmHor` ($f_t$), `RatioEtTraction` ($\kappa_t$), `IsDuctTraz` (`true`/`false`), `DuctTrazRockingHor` ($\mu_{ut}$ when `IsDuctTraz=true`), `UnloadTractionRockingHor`.
  - `LinearSoftening` or `Exponential`: Uses `FtmHor` ($f_t$), `Gt` ($G_t$), `UnloadTractionRockingHor`.
- `CompressiveCurveType` (and `CompressiveCurveTypeVertical` when `ortpf=true`):
  - `Elastic`: Only `Ehor`/`Ever` used.
  - `LinearHardening`: Uses `FmHor` ($f_m$), `RatioEtCompression` ($\kappa_c$), `IsDuctCompr` (`true`/`false`), `DuctComprRockingHor` ($\mu_{uc}$ when `IsDuctCompr=true`), `UnloadCompressionRockingHor`, `RotationLimitRockingHor` ($\Phi_u$).
  - `LinearSoftening` or `Parabolic`: Uses `FmHor` ($f_m$), `Gc` ($G_c$), `UnloadCompressionRockingHor`, `RotationLimitRockingHor` ($\Phi_u$).
- `UnloadTractionRockingHor`, `UnloadCompressionRockingHor`:
  - `Initial` ($\beta = 0$), `Origin` ($\beta = 1$), or `Nothing` (Mixed $0 < \beta < 1$, which activates `BetaUnloadTractionRockingHor` / `BetaUnloadCompressionRockingHor`).

### Shear (In-Plane Diagonal / Bed-Joint Shear)
- `Gd`: Shear modulus $G$ (`kN/cm²`), `AlfaShearUser`.
- `ConstitutiveLawMasonryShear`:
  - `Elastic`, `ElastoPlastic`, `ElastoPlasticDuctilityFixed`, `ElastoPlasticAndSoftening`, `ElastoPlasticFractureEnergyFixed`, `ElastoPlasticEnergySigmaInterpolation`.
- `CriterioSnervamento` (yielding domain):
  - `Coulomb`: `fvk0d` ($\tau_0$), `FrictionRatioShear` ($\mu$), `ShearReloadStiffnessRatio`, `ShearMaxTensileRatio`.
  - `Cacovic`: `fvk0d` ($\tau_0$), `Bcacovic` ($b$).
  - `Linear`: `fvk0d` ($\tau_0$).
- Cyclic shear parameters: `HasKinCiclShear`, `AkinCiclShear`, `CiclShear`, `AlfaCiclShear`, `GammaCiclShear`, `UnloadShear`, `BetaUnloadShear`.

### Sliding (Joint Sliding)
- `ortsc`: Orthotropic sliding (`true` / `false`, or `--orthotropic-sliding`).
- `CheckContactArea`: Update cohesive contact area (`true` / `false`).
- Use `--sliding-law` (or `sliding_law` in MCP):
  - `Elastic`: Sets `scorrhor=false`, `SlidingFractureEnergy=false`.
  - `ElastoPlastic`: Sets `scorrhor=true`, `SlidingFractureEnergy=false`. Uses `SlidingYieldingDomainHor`, `CohesionSlidingHor` ($c$), `FrictionRatioSlidingHor` ($\mu$), `SlidingMaxTensileRatioHor`, `SlidingPlasticStiffnessRatioHor`.
  - `LinearSoftening`: Sets `scorrhor=true`, `SlidingFractureEnergy=true`. Uses the `ElastoPlastic` fields plus `Gs` ($G_s$).

---

## 4. MCP Server (`mcp_server.py`)

If connected via MCP (`python3 /home/mauricio/coding/histra-bridge/histra-view/model-view/mcp_server.py`), the following tools are available directly:
- `hrx_catalog`: Returns geometry defaults, templates, and the Advanced mode masonry schema.
- `hrx_create_bridge`: Builds a new `.hrx` file from `output_path`, optional `spec`, and `overrides`.
- `hrx_inspect`: Inspects materials, analyses, and loads in an `.hrx` file.
- `hrx_edit_material`: Adds, duplicates, deletes, or updates an Advanced mode masonry material in an `.hrx` file.
- `hrx_edit_analysis`: Adds, duplicates, deletes, or updates an analysis in an `.hrx` file.
