"""Add fully fixed supports to straight bridge abutment end faces."""
from __future__ import annotations

import math
from lxml import etree


def _vector(value):
    values = tuple(float(part) for part in value.split(';'))
    if len(values) != 3 or not all(math.isfinite(x) for x in values):
        raise ValueError('Invalid geometry vector in model.')
    return values


def _fmt(values):
    return ';'.join(format(value, '.17g') for value in values)


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def _next(root, tag):
    return max((int(e.get('Key')) for e in root.findall(tag)), default=0) + 1


def add_fixed_abutment_ends(data: bytes) -> bytes:
    """Append fully fixed restraints on both outer vertical end faces."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True)
    root = etree.fromstring(data, parser)
    wizard = root.find('WizardData')
    definition = wizard.find('BridgeDefinition') if wizard is not None else None
    abutments = wizard.findall('Abutment') if wizard is not None else []
    bridges = root.findall('Bridge')
    if root.tag != 'HiStrA' or definition is None or len(abutments) != 2 or len(bridges) != 1:
        raise ValueError('Two bridge wizard abutments and one Bridge are required.')
    if any(abs(float(definition.get(k, '0'))) > 1e-9 for k in ('InclinationAngle', 'Slope')):
        raise ValueError('Abutment end restraints currently require a straight, level, unskewed bridge.')
    if any(abs(float(a.get(k, '0'))) > 1e-9 for a in abutments for k in ('b1', 'b3', 'w1', 'w3')):
        raise ValueError('Abutment end restraints currently require vertical, untapered ends.')
    if any(a.get(k, 'false').lower() == 'true' for a in abutments for k in ('ReinforcementLeft', 'ReinforcementRight')):
        raise ValueError('Abutment end restraints do not yet support reinforced abutments.')
    if any(e.get('Name', '').startswith('HiStrAView_EndSupport_') for e in root.findall('GeometryLineRestraint')):
        raise ValueError('Abutment end restraints have already been added to this model.')
    if any(s.get('Exit') != 'NotExecuted' for s in root.findall('Analysis/States/State')):
        raise ValueError('Add restraints to an unexecuted model; saved analysis states would be invalid.')
    kinds = {a.get('AbutmentKind'): a for a in abutments}
    if set(kinds) != {'Sinistra', 'Destra'}:
        raise ValueError('Could not identify the left and right abutments.')
    length = float(bridges[0].get('L', '0'))
    if length <= 0:
        raise ValueError('Bridge length must be positive.')
    nodes = {e.get('Key'): _vector(e.get('Point', '')) for e in root.findall('Node')}
    targets = []
    for side, x in (('Sinistra', 0.0), ('Destra', length)):
        height = float(kinds[side].get('H', '0'))
        if height <= 0:
            raise ValueError('Both abutments need positive heights.')
        count = 0
        for quad in root.findall('Quad'):
            keys = [quad.get(f'NodeKey{i}') for i in range(1, 5)]
            if any(key not in nodes for key in keys):
                raise ValueError('Quad references a missing node.')
            for edge in range(4):
                k1, k2 = keys[edge], keys[(edge + 1) % 4]
                p1, p2 = nodes[k1], nodes[k2]
                if (abs(p1[0]-x) < 1e-4 and abs(p2[0]-x) < 1e-4 and
                    abs(p1[1]-p2[1]) < 1e-4 and abs(p1[2]-p2[2]) > 1e-4 and
                    min(p1[2], p2[2]) >= -height-1e-4):
                    targets.append((side, quad, edge, k1, k2, p1, p2))
                    count += 1
        if not count:
            raise ValueError(f'No vertical end-face mesh edges found for {side} abutment.')
    existing_faces = {(e.get('ComputationalElementKey'), e.get('ComputationalElementEdge'))
                      for e in root.findall('Restraint') if e.get('ComputationalElementType') == 'Quad'}
    if any((quad.get('Key'), str(edge)) in existing_faces for _, quad, edge, *_ in targets):
        raise ValueError('An abutment end face already has a restraint.')
    for side in ('Sinistra', 'Destra'):
        strips = {}
        for target_side, quad, _, _, _, p1, p2 in targets:
            if target_side != side:
                continue
            thickness = float(quad.get('Thickness1', '0'))
            strips.setdefault((p1[1], thickness), []).append(sorted((p1[2], p2[2])))
        height = float(kinds[side].get('H'))
        deck_height = float(bridges[0].get('H', '0'))
        for spans in strips.values():
            spans.sort()
            if abs(spans[0][0] + height) > 1e-3 or spans[-1][1] < deck_height-1e-3 or any(abs(a[1]-b[0]) > 1e-3 for a, b in zip(spans, spans[1:])):
                raise ValueError('The saved end-face mesh does not cover the abutment through the deck level; regenerate it first.')
        widths = sorted((y-width/2, y+width/2) for y, width in strips)
        expected = float(kinds[side].get('w2', '0')) / 2
        if not widths or expected <= 0 or abs(widths[0][0]+expected) > 1e-3 or abs(widths[-1][1]-expected) > 1e-3 or any(abs(a[1]-b[0]) > 1e-3 for a, b in zip(widths, widths[1:])):
            raise ValueError('The saved abutment mesh does not cover its full wizard width; regenerate it first.')
    next_glr, next_r, next_nc = (_next(root, tag) for tag in ('GeometryLineRestraint', 'Restraint', 'NodeC'))
    nodecs = {e.get('NodeKey'): e for e in root.findall('NodeC')}
    bridge_keys = bridges[0].find('GeometryLineRestraintKeys')
    if bridge_keys is None:
        raise ValueError('Bridge has no geometry restraint key list.')
    for side, quad, edge, k1, k2, p1, p2 in targets:
        ref = quad.find('ReferenceSystem')
        if ref is None:
            raise ValueError('Quad has no reference system.')
        e3 = _vector(ref.get('E3', ''))
        if abs(e3[0]) > 1e-5 or abs(e3[2]) > 1e-5 or abs(abs(e3[1])-1) > 1e-5:
            raise ValueError('Abutment Quad thickness axis is not transverse.')
        thickness = [float(quad.get(f'Thickness{i}', '0')) for i in range(1, 5)]
        if min(thickness) <= 0 or max(thickness)-min(thickness) > 1e-4:
            raise ValueError('Abutment end restraint requires constant positive Quad thickness.')
        dz = p2[2]-p1[2]
        e1 = (0.0, 0.0, math.copysign(1.0, dz))
        e2 = _cross(e3, e1)
        ref_attrs = {'E1': _fmt(e1), 'E2': _fmt(e2), 'E3': _fmt(e3), 'Origin': _fmt(p1)}
        nc_keys = []
        for node_key in (k1, k2):
            nc = nodecs.get(node_key)
            if nc is None:
                nc = etree.SubElement(root, 'NodeC', Key=str(next_nc), NodeKey=node_key, MasterElementKey='0', MasterElementType='None', IsIndipendent='true', LayerKey='0', IsPropertyModified='false', Name=str(next_nc))
                aff = etree.SubElement(nc, 'AfferenceMatrices')
                for _ in range(6):
                    mat = etree.SubElement(aff, 'AfferenceMatrix')
                    etree.SubElement(mat, 'Alfa'); etree.SubElement(mat, 'Gdl')
                etree.SubElement(etree.SubElement(nc, 'MasterElements'), 'MasterElement', Key=node_key, Value='Node')
                etree.SubElement(nc, 'SlaveElements')
                etree.SubElement(nc, 'ReferenceSystem', E1='1;0;0', E2='0;1;0', E3='0;0;1', Origin='0;0;0')
                nodecs[node_key] = nc
                next_nc += 1
            slaves = nc.find('SlaveElements')
            if slaves is None:
                raise ValueError('Existing NodeC has no slave list.')
            etree.SubElement(slaves, 'SlaveElement', Key=str(next_r), Value='Restraint')
            nc_keys.append(nc.get('Key'))
        attrs = {'ParentKey':bridges[0].get('Key', '1'), 'ParentType':'Bridge', 'ParentEdge':'0', 'NodeKey1':k1, 'NodeKey2':k2, 'MaterialKey':'0', 'LoadConditionKey':'0', 'Zg':'0', 'B':str(thickness[0]), 'H':'30', 'Alignment':'Center', 'Dy':'0', 'MechanicalType':'Foundation', 'K':'-1|-1|-1|-1|-1|-1', 'MasterElementKey':'0', 'MasterElementType':'None', 'LayerKey':'0', 'IsPropertyModified':'false', 'Key':str(next_glr), 'Name':f'HiStrAView_EndSupport_{side}_{next_glr}'}
        for i, direction in enumerate(('U1','U2','U3','R1','R2','R3')):
            attrs[direction+'mechBehaviourType'] = 'Fixed'
            attrs[(f'K{i+1}' if i < 3 else f'Kr{i-2}')] = '-1'
        glr = etree.SubElement(root, 'GeometryLineRestraint', **attrs)
        etree.SubElement(etree.SubElement(glr, 'RestraintKeys'), 'RestraintKey', Value=str(next_r))
        etree.SubElement(glr, 'ReferenceSystem', **ref_attrs)
        etree.SubElement(bridge_keys, 'GeometryLineRestraintKey', Value=str(next_glr))
        half = thickness[0]/2
        points = [tuple(p[j] + sign*half*e3[j] for j in range(3)) for p, sign in ((p1,-1),(p2,-1),(p2,1),(p1,1))]
        restraint_attrs = {'Key':str(next_r), 'Name':str(next_r), 'ParentKey':str(next_glr), 'ParentTypeElement':'GeometryLineRestraint', 'NodeCKey1':nc_keys[0], 'NodeCKey2':nc_keys[1], 'Type':'Line', 'NodeKey1':k1, 'NodeKey2':k2, 'H':'30', 'MaterialKey':'0', 'LoadConditionKey':'0', 'Zg':'0', 'ComputationalElementKey':quad.get('Key'), 'ComputationalElementType':'Quad', 'ComputationalElementEdge':str(edge), 'G':_fmt(tuple((p1[j]+p2[j])/2 for j in range(3))), 'MasterElementKey':'0', 'MasterElementType':'None', 'LayerKey':'0', 'IsPropertyModified':'false', 'MechanicalType':'Foundation'}
        for key in ('U1','U2','U3','R1','R2','R3'):
            restraint_attrs[key+'mechBehaviourType'] = 'Fixed'
        for key in ('K1','K2','K3','Kr1','Kr2','Kr3'):
            restraint_attrs[key] = '-1'
        restraint_attrs.update({f'Point{i+1}':_fmt(point) for i, point in enumerate(points)})
        restraint = etree.SubElement(root, 'Restraint', **restraint_attrs)
        etree.SubElement(restraint, 'ReferenceSystem', **ref_attrs)
        next_glr += 1; next_r += 1
    return etree.tostring(root, encoding='utf-8', xml_declaration=True)
