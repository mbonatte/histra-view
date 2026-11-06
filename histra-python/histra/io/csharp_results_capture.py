"""Capture native static output at save boundaries, without changing mechanics.

Mirrors SolverRuntime/CommonOperations and SpringStateDBclass.SetFromSpring.
Raw Python double state is used; compact viewer arrays are never expanded back
into native records because their precision and constitutive history differ.
"""
from __future__ import annotations

from histra.io.results_reader import ResultsStateError
from histra.solver.restart import capture_committed_spring_state
from histra.springs.elastic import SpringElastic
from histra.springs.hysteretic import SpringHysteretic
from histra.springs.coulomb03 import SpringCoulomb03

_HISTORY_ZERO = ('Fy1 Fy2 Up1 Up2 Uy1 Uy2 Umax1 Umax2 Uu1 Uu2 N LoadIndicator F0 '
                 'CmomMin CmomMax CrotLimNu CrotLimPu CrotYn CrotYp CPhaseUnload_t '
                 'CPhaseUnload_c TangentReload_c TangentReload_t '
                 'CplasticTensionIndicator CplasticCompressionIndicator').split()
_COMPACT = 'ParentKey ParentType SpringPurpose SpringType IdLocal U F Phase Fy1 Fy2 Up1 Up2 N'.split()
_PURPOSE = {'Nothing': 0, 'Transversal1': 1, 'Transversal2': 2, 'Slid': 11, 'SlidOutOfPlan': 21, 'Diagonal': 30}


def native_spring_record(spring, parent_key, parent_type, local_id):
    """Native SetFromSpring leaves E/Ed/Eel NULL, even if Python tracks energy."""
    if isinstance(spring, SpringCoulomb03):
        spring_type = 12
    elif isinstance(spring, SpringHysteretic):
        spring_type = 8
    elif isinstance(spring, SpringElastic):
        spring_type = 1
    else:
        raise ResultsStateError(f'Unsupported native spring export: {type(spring).__name__}')
    try:
        purpose = _PURPOSE[spring.spring_purpose or 'Nothing']
    except KeyError as exc:
        raise ResultsStateError(f'Unknown native spring purpose: {spring.spring_purpose}') from exc
    row = dict.fromkeys(_HISTORY_ZERO, 0.0)
    captured = capture_committed_spring_state(spring)
    if spring_type == 1:
        captured = {key: captured[key] for key in ('U', 'F', 'K_tang', 'Phase')}
    row.update({key: value for key, value in captured.items() if key != 'Ed'})
    row.update(ParentKey=parent_key, ParentType=parent_type, IdLocal=local_id,
               SpringType=spring_type, SpringPurpose=purpose,
               U=float(spring.u), F=float(spring.f), K_tang=float(spring.k_tang),
               ContactArea=float(getattr(spring, '_ccontact_area', spring.area)))
    return row


def _spring_rows(collections):
    rows = []
    for quad in collections.quads.values():
        rows.append(native_spring_record(quad.spring, quad.key, 106, 0))
    for interface in collections.interfaces.values():
        for group in (interface.trasv_1, interface.trasv_2, interface.slid, interface.slid_out_plan):
            for index, spring in enumerate(group or ()):
                rows.append(native_spring_record(spring, interface.key, 102, index))
    return rows


def _element_row(element, size):
    values = list(getattr(element, "status", element).u)
    if len(values) != size:
        raise ResultsStateError(f'Native element {element.key} requires {size} displacements')
    return dict(ParentKey=element.key, **{f'U{i+1}': float(value) for i, value in enumerate(values)})


class CSharpResultsCapture:
    """Opt-in retained native records, separate from lighter viewer snapshots."""
    def __init__(self, model, combination, *, save_all_springs=True):
        self.model = model
        self.combination = int(combination)
        self.save_all_springs = save_all_springs
        self.records = {}
        self.last_springs = None
        self.last_row = None

    def capture(self, step, analysis):
        if int(analysis.analysis_type) == 5:
            raise ResultsStateError('Native capture currently supports static Quad/Interface analyses only')
        from histra.solver.model_manager import ModelManager

        runtime = ModelManager.hysteretic_batch_for(self.model)
        if runtime is not None:
            runtime.sync_all_to_objects()
        for node in self.model.collections.node_c.values():
            if any(node.aff) or any(node.u):
                raise ResultsStateError('Native export requires inactive NodeC DOFs; active NodeC state is not retained')
        springs = _spring_rows(self.model.collections)
        self.last_springs, self.last_row = springs, dict(step)
        interval = max(1, int(getattr(analysis, 'step_save', 1)))
        if int(step['step']) % interval:
            return
        context = dict(AnalysisKey=int(analysis.key), Combination=self.combination, Step=int(step['step']))
        self._elements(context)
        self._reactions(context, step)
        self._points(context, step['u'])
        if self.save_all_springs:
            self._add('SpringStatesTmp', context, ({key: row[key] for key in _COMPACT} for row in springs))

    def _add(self, table, context, rows):
        self.records.setdefault(table, []).extend({**context, **row} for row in rows)

    def _elements(self, context):
        collections = self.model.collections
        self._add('QuadStates', context, ({**_element_row(q, 7), 'K': float(q.status.k)} for q in collections.quads.values()))
        self._add('NodeCStates', context, (_element_row(n, 6) for n in collections.node_c.values()))
        self._add('RestraintStates', context, (_element_row(r, 6) for r in collections.restraints.values()))
        rows = []
        for interface in collections.interfaces.values():
            row = _element_row(interface, 12)
            for prefix, values in (('Force', interface.status.forces), ('BendingMoments', interface.status.bending_moments)):
                row.update({f'{prefix}{axis}': float(value) for axis, value in zip('XYZ', values)})
            rows.append(row)
        self._add('InterfaceStates', context, rows)

    def _reactions(self, context, step):
        row = {f'R{i}': float(step[f'reaction_{axis}']) for i, axis in enumerate('xyz', 1)}
        row.update(Et=0.0, Ei=0.0, Evd=0.0, Eel=float(step['elastic_energy']), Ed=float(step['dissipated_energy']))
        self._add('ReactionSumStates', context, [row])

    def _points(self, context, displacement):
        from histra.solver.output_projection import compute_model_point_displacements

        rows = []
        for point in compute_model_point_displacements(self.model, displacement, step=context['Step']):
            definition = self.model.collections.model_points[point.parent_key]
            row = point.as_runner_dict()
            row.update(ElementType=definition.element_type, Vx=0.0, Vy=0.0, Vz=0.0, Ax=0.0, Ay=0.0, Az=0.0)
            rows.append(row)
        self._add('DisplModelPoints', context, rows)

    def finish(self, analysis_key):
        if self.last_row is None:
            raise ResultsStateError('No initial native state was captured')
        context = dict(AnalysisKey=int(analysis_key), Combination=self.combination, Step=int(self.last_row['step']))
        self._add('SpringStates', context, self.last_springs)
        # C# CommonOperations explicitly writes Combination=1 for these vectors.
        context['Combination'] = 1
        self._add('DynamicVectorsState', context, ({'Dof': i, 'U': float(value), 'V': 0.0} for i, value in enumerate(self.last_row['u'])))
        return self.records
