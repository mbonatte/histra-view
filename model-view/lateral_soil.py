"""Preserve the viewer's complete, linear foundation-side soil supports."""
from copy import deepcopy
import math
import tempfile
from pathlib import Path
from lxml import etree


def _vec(value):
    values = tuple(float(x) for x in value.split(';'))
    if len(values) != 3 or not all(math.isfinite(x) for x in values):
        raise ValueError('Invalid soil support geometry.')
    return values


def _area(points):
    import numpy as np
    p = np.asarray(points, dtype=float)
    return float((np.linalg.norm(np.cross(p[1]-p[0], p[2]-p[0])) + np.linalg.norm(np.cross(p[2]-p[0], p[3]-p[0]))) / 2)


def strip_soil_supports(root):
    """Remove recognized soil objects from a copy, returning their settings.

    Reject edits to the generated support mechanics rather than discard them.
    """
    supports = [g for g in root.findall('GeometryLineRestraint') if g.get('Name', '').startswith(('X soil face ', 'Y soil face '))]
    if not supports:
        return {}, {}
    restraints = {r.get('Key'): r for r in root.findall('Restraint')}
    nodes = {n.get('Key'): n for n in root.findall('Node')}
    settings, targets, node_keys = {}, {}, set()
    bridge_refs = root.find('Bridge/GeometryLineRestraintKeys')
    if bridge_refs is None:
        raise ValueError('Cannot regenerate soil supports: bridge references are missing.')
    for g in supports:
        axis = g.get('Name')[0]
        refs = g.findall('RestraintKeys/RestraintKey')
        r = restraints.get(refs[0].get('Value')) if len(refs) == 1 else None
        if (r is None or r.get('ParentKey') != g.get('Key') or r.get('MaterialKey') != '0' or r.get('ComputationalElementType') != 'Quad'
                or any(e.get('LoadConditionKey', '0') != '0' or e.get('MasterElementKey', '0') != '0'
                       or e.get('LayerKey', '0') != '0' or e.get('IsPropertyModified', 'false').lower() != 'false'
                       for e in (r, g))):
            raise ValueError('Cannot regenerate modified soil supports.')
        if any(float(r.get(k, 'nan')) != 0 for k in ('K1','K3','Kr1','Kr2','Kr3')):
            raise ValueError('Cannot regenerate soil supports with additional stiffness directions.')
        ref = r.find('ReferenceSystem')
        expected = (1., 0., 0.) if axis == 'X' else (0., 1., 0.)
        e3 = (0., -1., 0.) if axis == 'X' else (1., 0., 0.)
        if ref is None or _vec(ref.get('E2', '')) != expected or _vec(ref.get('E1', '')) != (0., 0., -1.) or _vec(ref.get('E3', '')) != e3:
            raise ValueError('Cannot regenerate soil supports with modified directions.')
        area = _area([_vec(r.get(f'Point{i}', '')) for i in range(1, 5)])
        k = float(r.get('K2', 'nan'))
        if not math.isfinite(k) or k <= 0 or area <= 0 or not math.isclose(float(g.get('K2', 'nan')), k, rel_tol=1e-10):
            raise ValueError('Cannot regenerate modified soil stiffness.')
        try:
            glr_values = [float(v) for v in g.get('K', '').split('|')]
        except ValueError:
            glr_values = []
        if len(glr_values) != 6 or any(not math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10) for a, b in zip(glr_values, (0, k, 0, 0, 0, 0))):
            raise ValueError('Cannot regenerate modified soil stiffness.')
        if any(g.get(f'NodeKey{i}') != r.get(f'NodeKey{i}') for i in (1, 2)):
            raise ValueError('Cannot regenerate modified soil support nodes.')
        modulus = k / area
        if axis in settings and not math.isclose(settings[axis], modulus, rel_tol=1e-9):
            raise ValueError('Cannot regenerate nonuniform soil stiffness.')
        settings[axis] = modulus
        target = (int(r.get('ComputationalElementKey')), int(r.get('ComputationalElementEdge')))
        if target in targets.setdefault(axis, set()):
            raise ValueError('Cannot regenerate duplicate soil supports.')
        targets[axis].add(target)
        for key in (r.get('NodeKey1'), r.get('NodeKey2')):
            if key not in nodes or key in node_keys:
                raise ValueError('Cannot regenerate modified soil support nodes.')
            node_keys.add(key)
        matching = [x for x in bridge_refs if x.get('Value') == g.get('Key')]
        if len(matching) != 1:
            raise ValueError('Cannot regenerate soil supports with modified bridge references.')
        bridge_refs.remove(matching[0]);root.remove(r);root.remove(g)
    used_nodes = {element.get(attr) for element in root.iter() if element.tag != 'Node'
                  for attr in ('NodeKey1','NodeKey2','NodeKey3','NodeKey4')}
    if node_keys & used_nodes:
        raise ValueError('Cannot regenerate soil nodes used by other objects.')
    for key in node_keys:
        root.remove(nodes[key])
    return settings, targets


def _exposed_faces(data, settings):
    import numpy as np
    from histra import load_solver_model
    from histra.preprocessing import prepare_model
    from histra.preprocessing.contact_geometry import _quad_face_vertices
    with tempfile.TemporaryDirectory(prefix='histra-soil-prep-') as directory:
        path = Path(directory) / 'bridge.hrx'
        path.write_bytes(data)
        model = load_solver_model(path)
        prepare_model(model, force=True, use_cache=False)
    root = etree.fromstring(data)
    wizard = root.find('WizardData')
    materials = {int(p.get('MaterialFoundationKey', '0')) for p in wizard.findall('Pier')} if wizard is not None else set()
    if not materials or 0 in materials:
        raise ValueError('Cannot identify the pier foundation material for soil restraints.')
    result = {axis: [] for axis in settings}
    for q in model.collections.quads.values():
        if q.material_key not in materials:
            continue
        for axis, face_ids, component in (('X', range(4), 0), ('Y', (4, 5), 1)):
            if axis not in result:
                continue
            for face in face_ids:
                vertices = np.asarray(_quad_face_vertices(model, q, face), dtype=float)
                normal = np.cross(vertices[1]-vertices[0], vertices[2]-vertices[0])
                norm = np.linalg.norm(normal)
                if norm and abs(normal[component]/norm) > .999999 and not q.interface_keys[face]:
                    result[axis].append((q.key, face, vertices))
    if any(not faces for faces in result.values()):
        raise ValueError('Cannot find all requested foundation-side soil faces.')
    return result


def recreate_soil_supports(data, settings, original_data=None, original_targets=None):
    import numpy as np
    if not settings:
        return data
    if original_data is not None:
        old_faces = _exposed_faces(original_data, settings)
        for axis, faces in old_faces.items():
            if {(q, face) for q, face, _ in faces} != original_targets[axis]:
                raise ValueError('Cannot regenerate partial or modified foundation soil restraints.')
    faces = _exposed_faces(data, settings)
    root = etree.fromstring(data)
    bridge = root.find('Bridge')
    if bridge is None:
        raise ValueError('Cannot regenerate soil restraints without a bridge.')
    bridge_refs = bridge.find('GeometryLineRestraintKeys')
    if bridge_refs is None:
        bridge_refs = etree.SubElement(bridge, 'GeometryLineRestraintKeys')
    template = root.find('Restraint')
    if template is None:
        raise ValueError('Cannot regenerate soil restraints without a foundation restraint template.')
    rkey = max(int(e.get('Key')) for e in root.findall('Restraint')) + 1
    nkey = max(int(e.get('Key')) for e in root.findall('Node')) + 1
    gkey = max(int(e.get('Key')) for e in root.findall('GeometryLineRestraint')) + 1
    fmt = lambda v: ';'.join(str(float(x)) for x in v)
    for axis in ('Y', 'X'):
        for qkey, face, v in faces.get(axis, []):
            r = deepcopy(template)
            p1, p2 = (v[0]+v[3])/2, (v[1]+v[2])/2
            for key, p in ((nkey,p1),(nkey+1,p2)):
                etree.SubElement(root,'Node',Key=str(key),Name=str(key),Point=fmt(p))
            k2 = float(settings[axis] * _area(v))
            e2, e3 = ('1;0;0','0;-1;0') if axis == 'X' else ('0;1;0','1;0;0')
            refattrs = dict(E1='0;0;-1', E2=e2, E3=e3, Origin=fmt(p1))
            r.attrib.update(dict(ParentKey=str(gkey),Key=str(rkey),Name=str(rkey),NodeKey1=str(nkey),NodeKey2=str(nkey+1),NodeCKey1='0',NodeCKey2='0',ComputationalElementKey=str(qkey),ComputationalElementType='Quad',ComputationalElementEdge=str(face),MaterialKey='0',G=fmt(v.mean(axis=0))))
            for key, value in zip(('K1','K2','K3','Kr1','Kr2','Kr3'), (0,k2,0,0,0,0)):
                r.set(key,str(value))
            for d in ('U1','U3','R1','R2','R3'): r.set(d+'mechBehaviourType','Free')
            r.set('U2mechBehaviourType','Fixed')
            for i, p in enumerate(v,1): r.set(f'Point{i}',fmt(p))
            r.find('ReferenceSystem').attrib.update(refattrs)
            glr=etree.SubElement(root,'GeometryLineRestraint',Key=str(gkey),Name=f'{axis} soil face {qkey}',ParentKey=bridge.get('Key'),ParentType='Bridge',ParentEdge='0',NodeKey1=str(nkey),NodeKey2=str(nkey+1),MaterialKey='0',LoadConditionKey='0',Zg='0',B=str(float(np.linalg.norm(v[3]-v[0]))),H='30',Alignment='Center',Dy='0',MechanicalType='Foundation',K=f'0|{k2}|0|0|0|0',MasterElementKey='0',MasterElementType='None',LayerKey='0',IsPropertyModified='false',K1='0',K2=str(k2),K3='0',Kr1='0',Kr2='0',Kr3='0',U1mechBehaviourType='Free',U2mechBehaviourType='Fixed',U3mechBehaviourType='Free',R1mechBehaviourType='Free',R2mechBehaviourType='Free',R3mechBehaviourType='Free')
            etree.SubElement(etree.SubElement(glr,'RestraintKeys'),'RestraintKey',Value=str(rkey))
            etree.SubElement(glr,'ReferenceSystem',**refattrs)
            etree.SubElement(bridge_refs,'GeometryLineRestraintKey',Value=str(gkey))
            root.append(r);rkey+=1;nkey+=2;gkey+=1
    return etree.tostring(root,encoding='utf-8',xml_declaration=True)
