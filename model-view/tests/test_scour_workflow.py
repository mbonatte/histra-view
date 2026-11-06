import unittest
from scour_workflow import select_ratio, selected_scour_extent, normalize_workflow, configure_sequence
from types import SimpleNamespace

class ScourSelectionTests(unittest.TestCase):
    def test_centroid_selection_is_total_from_chosen_edge(self):
        group={'ymin':0,'ymax':100,'entries':[(0,1,y,y-5,y+5,k) for k,y in enumerate((5,15,25,35,45,55,65,75,85,95),1)]}
        self.assertEqual(select_ratio(group,.2),[1,2])
        self.assertEqual(select_ratio(group,.4),[1,2,3,4])
        self.assertEqual(select_ratio(group,.2,'+Y'),[9,10])
        self.assertEqual(select_ratio(group,0),[])
        self.assertEqual(select_ratio(group,1),list(range(1,11)))
    def test_invalid_inputs(self):
        group={'ymin':0,'ymax':100,'entries':[]}
        for value in (-.1,1.1,float('nan')):
            with self.assertRaises(ValueError):select_ratio(group,value)
        with self.assertRaises(ValueError):select_ratio(group,.2,'-X')

    def test_selected_extent_uses_patch_edges_in_both_directions(self):
        group={'ymin':0,'ymax':100,'entries':[(0,1,y,y-5,y+5,k) for k,y in enumerate((5,15,25,35,45,55,65,75,85,95),1)]}
        for direction in ('-Y', '+Y'):
            selected = select_ratio(group, .26, direction)
            result = selected_scour_extent(group, selected, direction)
            self.assertAlmostEqual(result['ratio'], .3)
            self.assertEqual(result['widthCm'], 30)
            self.assertEqual(result['interfaceCount'], 3)
            self.assertEqual(selected_scour_extent(group, [], direction)['ratio'], 0)

    def test_sequence_includes_every_configured_scour_stage(self):
        def a(k,name,kind,previous):return SimpleNamespace(key=k,name=name,analysis_type=kind,initial_analysis_key=previous)
        analyses={1:a(1,'Vert',2,-100),23:a(23,'scour_1',2,1),24:a(24,'scour_2',2,23),26:a(26,'scour_3',2,24),28:a(28,'scour_4',2,24),40:a(40,'Modal_4',5,28)}
        model=SimpleNamespace(collections=SimpleNamespace(analyses=analyses))
        cfg=normalize_workflow({'pier':1,'intactMaterial':146,'scouredMaterial':147,'direction':'-Y','stages':[{'analysisKey':k,'ratio':r} for k,r in ((23,.1),(24,.2),(26,.3),(28,.4))]})
        chain=configure_sequence(model,analyses[40],cfg)
        self.assertEqual([a.key for a in chain],[1,23,24,26,28,40])
        self.assertEqual(analyses[28].initial_analysis_key,26)
        self.assertEqual(analyses[40].initial_analysis_key,28)
        cfg['stages'].pop(1)
        with self.assertRaisesRegex(ValueError,'every scour stage'):
            configure_sequence(model,analyses[40],cfg)

    def test_ratios_must_be_nondecreasing(self):
        raw={'pier':1,'intactMaterial':146,'scouredMaterial':147,'stages':[{'analysisKey':23,'ratio':.4},{'analysisKey':24,'ratio':.2}]}
        with self.assertRaisesRegex(ValueError,'nondecreasing'):
            normalize_workflow(raw)

    def test_prepared_foundation_interfaces_accept_soil_mutation(self):
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from lxml import etree
        from builder_api import build, defaults
        from histra import load_solver_model, AnalysisSession
        from histra.preprocessing import prepare_model
        payload=defaults();payload['nl']=200
        with TemporaryDirectory() as directory:
            path=Path(directory)/'bridge.hrx'
            path.write_bytes(build({'mode':'create','payload':payload}))
            model=load_solver_model(path)
            prepare_model(model, force=True, use_cache=False)
            wizard=etree.fromstring(path.read_bytes()).find('WizardData')
        from scour_workflow import pier_foundation_groups
        groups=pier_foundation_groups(model, wizard)
        self.assertEqual(len(groups), 1)
        all_keys=[item[5] for item in groups[0]['entries']]
        selected=select_ratio(groups[0], .4)
        self.assertTrue(selected)
        self.assertLess(len(selected), len(all_keys))
        session=AnalysisSession(model)
        session.change_interface_materials(all_keys,146,preserve_committed_state=False)
        session.change_interface_materials(selected,147,preserve_committed_state=True)
        for key in selected:
            self.assertEqual(model.collections.interfaces[key].material_key,147)
        for key in set(all_keys)-set(selected):
            self.assertEqual(model.collections.interfaces[key].material_key,146)

    def test_stages_mutate_only_new_interfaces_and_preserve_state(self):
        from scour_workflow import apply_scour_stage
        class Session:
            def __init__(self):self.calls=[]
            def change_interface_materials(self, keys, material, **kwargs):self.calls.append((keys,material,kwargs))
        session=Session();changed=set()
        self.assertEqual(apply_scour_stage(session,[1,2],changed,147),2)
        self.assertEqual(apply_scour_stage(session,[1,2,3],changed,147),1)
        self.assertEqual(session.calls,[([1,2],147,{'preserve_committed_state':True}),([3],147,{'preserve_committed_state':True})])

    def test_runner_sequences_mutations_and_all_scour_stages(self):
        import time
        from tempfile import TemporaryDirectory
        from pathlib import Path
        from copy import deepcopy
        from unittest.mock import patch
        from lxml import etree
        from builder_api import build, defaults
        import solver_api
        from histra.solver.outcomes import AnalysisOutcome
        payload=defaults();payload['nl']=200
        root=etree.fromstring(build({'mode':'create','payload':payload}))
        modal=deepcopy(next(a for a in root.findall('Analysis') if a.get('Name')=='Modal_1'))
        modal.set('Key','40');modal.set('Name','Modal_4');root.append(modal)
        events=[]
        class Session:
            def __init__(self, model, **kwargs):
                self.model=model
                self.kwargs=kwargs
                self.assert_options()
            def assert_options(self):
                assert self.kwargs['preserve_predecessor_load'] is True
                assert self.kwargs['equilibrium_policy']=='error'
            def resolve_analysis(self, key):return self.model.collections.analyses[int(key)]
            def change_interface_materials(self, keys, material, **kwargs):
                events.append(('material',material,list(keys),kwargs['preserve_committed_state']))
            def run(self, definition, **kwargs):
                events.append(('run',definition.name))
                is_modal=int(definition.analysis_type)==5
                return SimpleNamespace(completed=True, outcome=AnalysisOutcome.COMPLETED,
                    committed_steps=[] if is_modal else [{'load_factor':1.0 if definition.name=='Vert' else 0.0}],
                    modal_result=SimpleNamespace(modes=[1]) if is_modal else None,
                    runtime_seconds=0,code=0,message='')
        workflow={'pier':1,'intactMaterial':146,'scouredMaterial':147,'direction':'-Y',
                  'stages':[{'analysisKey':k,'ratio':r} for k,r in ((23,.2),(24,.4),(26,.6),(28,.8))]}
        def write_bundle(_model,_executions,filepath,**_kwargs):
            path=Path(filepath);path.write_bytes(b'test');return path
        with TemporaryDirectory() as directory, patch.object(solver_api,'RUNS_DIR',Path(directory)), \
             patch('histra.AnalysisSession',Session), \
             patch('histra.io.results_writer.ResultsWriter.export_bundle',side_effect=write_bundle):
            job=solver_api.start_job(etree.tostring(root),'chain.hrx',40,scour_workflow=workflow)
            deadline=time.monotonic()+30
            while (status:=solver_api.job_status(job['jobId']))['status']=='running' and time.monotonic()<deadline:
                time.sleep(.05)
            self.assertEqual(status['status'],'completed',status.get('error'))
        self.assertEqual([e[1] for e in events if e[0]=='run'],['Vert','scour_1','scour_2','scour_3','scour_4','Modal_4'])
        mutations=[e for e in events if e[0]=='material']
        self.assertEqual((mutations[0][1],mutations[0][3]),(146,False))
        self.assertTrue(all(e[1]==147 and e[3] for e in mutations[1:]))
        scoured=[k for e in mutations[1:] for k in e[2]]
        self.assertEqual(len(scoured),len(set(scoured)))

    def test_equilibrium_audit_override_is_explicit_and_per_workflow(self):
        raw={'pier':1,'intactMaterial':146,'scouredMaterial':147,'stages':[{'analysisKey':23,'ratio':.2}]}
        self.assertFalse(normalize_workflow(raw)['skipEquilibriumAudit'])
        self.assertTrue(normalize_workflow({**raw,'skipEquilibriumAudit':True})['skipEquilibriumAudit'])
        with self.assertRaisesRegex(ValueError,'audit setting'):
            normalize_workflow({**raw,'skipEquilibriumAudit':'true'})
