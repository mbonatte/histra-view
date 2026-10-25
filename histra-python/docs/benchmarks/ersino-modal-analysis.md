# Ersino modal-analysis parity benchmark

## Inputs

- Model: `Ersino.hrx`
- C# result database: `Ersino.Results`
- Modal analysis: key `30`, name `Modal_-1`
- Active degrees of freedom: `14,252`
- Requested modes: `10`
- Stored C# mode-shape rows: `142,520`

## C# algorithm reproduced

The Python implementation follows the active C# execution path rather than
substituting a generic eigensolver:

1. restore or initialise the model state;
2. assemble the tangent stiffness matrix with `alfa = 1`;
3. integrate the Quad consistent mass matrix with the C# 6×6×6 rule;
4. run `Matrix.SubSpaceIteration2`, including its deterministic .NET
   `Random(0)` initial subspace and eigenvalue-change convergence test;
5. mass-normalise the modes;
6. calculate participation factors, effective masses, mass percentages,
   directional maxima and complete DOF mode shapes.

The requested HRX mass type is `Lumped`, but the active C# Quad routine ignores
that switch and integrates the consistent matrix. Python deliberately reports
both the requested and effective types and reproduces the effective C# matrix.

## Numerical comparison

| Mode | C# frequency [Hz] | Python frequency [Hz] | Relative error |
|---:|---:|---:|---:|
| 1 | 3.8184457214 | 3.8184457448 | 6.14e-09 |
| 2 | 4.7701457266 | 4.7701457666 | 8.40e-09 |
| 3 | 5.0543547533 | 5.0543547868 | 6.63e-09 |
| 4 | 6.0342187771 | 6.0342188601 | 1.38e-08 |
| 5 | 6.6696856866 | 6.6696857786 | 1.38e-08 |
| 6 | 6.8503087343 | 6.8503087855 | 7.47e-09 |
| 7 | 6.9993484729 | 6.9993485643 | 1.31e-08 |
| 8 | 8.6566424669 | 8.6566425457 | 9.11e-09 |
| 9 | 9.2394155830 | 9.2394157155 | 1.43e-08 |
| 10 | 10.2326334901 | 10.2326336046 | 1.12e-08 |

Maximum absolute relative frequency error: `1.4342e-08`.

Directional total mass in X:

- C#: `51.67654681724974`
- Python: `51.67654580028968`
- Relative error: `-1.9679e-08`

The minimum diagonal mass-weighted correlation between matching C# and Python
mode shapes is `0.9999999861`; all ten correlations are effectively one.

## Test commands

```console
HISTRA_MODAL_HRX=/path/Ersino.hrx \
HISTRA_MODAL_RESULTS=/path/Ersino.Results \
python -m pytest -q histra/tests/test_modal_analysis.py
```

```console
python -m histra.tools.validate_modal_results \
  Ersino.hrx Ersino.Results --analysis-key 30 \
  --output modal-validation.json
```

## Interpretation

The upper modes retain larger eigen-residuals because the original C# stopping
rule checks the normalized change in eigenvalues, not the eigen-residual. This
is intentional compatibility behaviour. Python exposes each residual so that a
future high-accuracy eigensolver mode can be added without confusing it with
strict C# parity.

## Raw-HRX preprocessing parity

A second Ersino file was supplied in its original unlocked, geometry-only form.
Running modal analysis on that file originally regenerated a substantially
stiffer interface system and produced a first frequency of `3.99807945 Hz`,
whereas the C#-prepared HRX and `Ersino.Results` contain `3.81844572 Hz`.

The decisive mismatch was in C#'s directional in-plane sliding law selection:

- `MasonryMaterial.SlidingOrthotropyType` is a read-only property that always
  returns `true`;
- therefore Quad faces 4 and 5 use the direction-3 sliding law;
- the direction-3 in-plane modulus is `Gd`;
- the horizontal and vertical in-plane modulus is
  `2*Gd/(1-AlfaShear)`, equal to `20*Gd` for Ersino's `AlfaShear=0.9`.

Python had interpreted the serialized `ortsc="false"` attribute as disabling
that selection and consequently assigned the 20-times-stiffer horizontal or
vertical law to 1,752 broad-face interfaces. The implementation now reproduces
`Interface.SetSpring` and `ConstitutiveLawCoulomb.PropOrthotropyParameter`,
including the direction-3 law.

A second, smaller mismatch occurred at the C# single-precision subdivision
boundary. Two nominal 160 mm contacts were evaluated by Python as approximately
159.99996 mm, producing four rows instead of six and omitting 16 transverse
springs. The row/column calculation now applies the C# float boundary and
contact tolerance.

After correction, modal analysis generated directly from the raw HRX gives:

| Mode | C# result [Hz] | Raw HRX after Python preprocessing [Hz] | Relative error |
|---:|---:|---:|---:|
| 1 | 3.8184457214 | 3.8184467000 | 2.56e-07 |
| 2 | 4.7701457266 | 4.7701447647 | -2.02e-07 |
| 3 | 5.0543547533 | 5.0543583203 | 7.06e-07 |
| 4 | 6.0342187771 | 6.0342223762 | 5.96e-07 |
| 5 | 6.6696856866 | 6.6696956670 | 1.50e-06 |
| 6 | 6.8503087343 | 6.8503151129 | 9.31e-07 |
| 7 | 6.9993484729 | 6.9993547071 | 8.91e-07 |
| 8 | 8.6566424669 | 8.6566543620 | 1.37e-06 |
| 9 | 9.2394155830 | 9.2394244396 | 9.59e-07 |
| 10 | 10.2326334901 | 10.2326645915 | 3.04e-06 |

The maximum absolute frequency difference is `3.11e-05 Hz`; the maximum
relative difference is `3.04e-06`. This is close preprocessing parity, although
not bit-for-bit identity with the C#-serialized computational model.
