# Solver strategy benchmark methodology

Benchmark at least one gravity/seating stage, force-controlled pushover,
displacement-controlled pushover, P-Delta EachStep, P-Delta EachIteration,
coarse mesh, fine mesh, and near-collapse stage. Evaluate every supported
method/integrator/criterion combination that is constructible for that scenario.

A candidate qualifies only when strict equilibrium passes, the reference range
is covered, a traceable accepted reference path is supplied, and signed/path-
aware response metrics pass the same peak/RMSE/area/stiffness/peak-displacement
limits used by the Article gate. Compare runtime, nonlinear
iterations, tangent factorizations, and peak memory only among qualifying
candidates. Save the exact command, HRX hash, environment, repetitions, warm-up
policy, raw observations, aggregate statistics, and selected recommendation.

Do not publish “always”, “guarantees”, or fixed speedup language from a single
model. The public advisor contains stable codes and model-qualified reasons; it
does not modify HRX settings.

The canonical runner accepts a JSON matrix and writes a versioned raw report:

```json
{
  "scenario": "coarse live-load pushover",
  "hrx": "my_model/Article_Models_Benchmark/Bridge_3.1_Coarse.hrx",
  "target": "Second",
  "max_steps": 5,
  "repetitions": 5,
  "cache_state": "process-warm; fresh model and runtime per observation",
  "baseline_id": "force-bisection",
  "reference_evidence": {
    "accepted": true,
    "source": "release-evidence/article-models/<accepted-path>.json",
    "source_sha256": "<sha256>"
  },
  "reference_results": "my_model/benchmark.Results",
  "reference_curve": {
    "displacement_mm": [0.0, 0.1, 0.2],
    "load_kn": [0.0, 10.0, 20.0]
  },
  "candidates": [
    {"id": "authored"},
    {
      "id": "force-bisection",
      "adaptive_convergence_criteria": "ForceMoment",
      "method": "StandardBisectionLineSearch",
      "csharp_line_search_compatibility": false,
      "analysis_overrides": {
        "Vert": {"adaptive_convergence_criteria": "ForceMoment", "method": "StandardBisectionLineSearch"},
        "First": {"adaptive_convergence_criteria": "ForceMoment", "method": "StandardBisectionLineSearch"}
      }
    }
  ]
}
```

```console
python -m histra.tools.strategy_benchmark matrix.json \
  --output release-evidence/strategy/coarse-live-load.json
```

When `reference_results` is supplied, the runner extracts the C# response at
the target analysis' configured master point and direction, subtracting the
predecessor terminal reaction/displacement for staged live loading. It does not
compare an integrator-private displacement scalar or a matching solver step.

The report preserves every observation and includes medians for committed steps,
iterations, linear solves, factorizations, preparation/runtime, and peak
resident memory where the OS exposes it. A candidate qualifies only when every
repeat is complete, safe, covers the reference range, and passes response
metrics; a median never hides one bad run. The fastest qualifying candidate is
selected from those medians.

The baseline must itself be a safe, accepted response. The runner requires the
external reference path and an `accepted` evidence record containing a source
and SHA-256 before it can select a recommendation. An authored C# strategy that
fails the independent equilibrium audit belongs in the matrix as compatibility
evidence, but it must not be used as the correctness baseline. Signed path
order, repeated displacements, and unloading/reloading branches are retained;
the runner never sorts absolute displacement/load values for qualification.
ArcLength matrices may additionally vary `csharp_line_search_compatibility`,
`arc_length_procedure`, `dr2`, predictor caps, adaptive-radius behavior, and
bounded cutback settings. These values are recorded with each candidate; they
must not be changed implicitly by the public advisor.

The current stored matrices predate the required external-reference schema and
are diagnostic only; they must be regenerated before a recommendation can be
released. The current P-Delta gravity matrix executes the complete five-increment range.
All measured `EachStep` and `EachIteration` Standard line-search variants
preserve the Bisection baseline response and pass strict equilibrium. The
authored Modified Regula-Falsi `EachStep` configuration is also safe and was
fastest in the recorded single run. This qualifies the gravity scenario only;
it does not replace a P-Delta live-load or near-collapse gate.
