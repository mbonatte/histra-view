"""Resolve foundation scour regions against a freshly prepared model."""
from __future__ import annotations
import math
import re
from copy import deepcopy


def select_bottom_foundations(model, foundation_material_keys):
    """Group horizontal restraint interfaces by disconnected foundation footprints."""
    c = model.collections
    materials = set(foundation_material_keys)
    entries = []
    for interface in c.interfaces.values():
        sides = [(interface.parent_type_element1, interface.parent_element_key1, interface.parent_type_element2, interface.parent_element_key2),
                 (interface.parent_type_element2, interface.parent_element_key2, interface.parent_type_element1, interface.parent_element_key1)]
        match = next(((rkey,qkey) for rt,rkey,qt,qkey in sides if rt == 'Restraint' and qt == 'Quad'), None)
        if match is None:
            continue
        restraint = c.restraints.get(match[0]); quad = c.quads.get(match[1])
        if restraint is None or quad is None or quad.material_key not in materials:
            continue
        if not restraint.has_reference_system or abs(restraint.reference_e2[2]) < .99999:
            continue
        coords = [c.nodes[k].point for k in quad.node_keys]
        xmin, xmax = min(p.x for p in coords), max(p.x for p in coords)
        points = interface.vint3d
        if len(points) != 4:
            raise ValueError(f'Interface {interface.key} has invalid geometry.')
        y = sum(p.y for p in points) / 4
        ys = [p.y for p in points]
        if not all(math.isfinite(float(v)) for v in (xmin,xmax,y,*ys)):
            raise ValueError('Invalid foundation interface coordinates.')
        entries.append((float(xmin),float(xmax),float(y),min(ys),max(ys),int(interface.key)))
    if not entries:
        raise ValueError('No prepared bottom interfaces were found on the pier foundations.')
    entries.sort()
    groups=[]
    for item in entries:
        if not groups or item[0] > groups[-1]['xmax'] + 1e-4:
            groups.append({'xmin':item[0], 'xmax':item[1], 'entries':[]})
        groups[-1]['xmax']=max(groups[-1]['xmax'],item[1])
        groups[-1]['entries'].append(item)
    for group in groups:
        group['ymin']=min(x[3] for x in group['entries'])
        group['ymax']=max(x[4] for x in group['entries'])
    return groups


def select_ratio(group, ratio, direction='-Y'):
    """Select centroids in a total scour fraction, measured from a Y edge."""
    value=float(ratio)
    if not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('Scour ratio must be between 0 and 1.')
    if direction not in ('-Y', '+Y'):
        raise ValueError('Scour direction must be -Y or +Y.')
    width=group['ymax']-group['ymin']
    if width <= 0:
        raise ValueError('Foundation has zero width.')
    if value == 0:
        return []
    if direction == '-Y':
        return sorted(e[5] for e in group['entries'] if e[2] <= group['ymin'] + value * width + 1e-4)
    return sorted(e[5] for e in group['entries'] if e[2] >= group['ymax'] - value * width - 1e-4)


def selected_scour_extent(group, selected, direction='-Y'):
    """Report the selected patches' farthest edge from the requested start edge."""
    if direction not in ('-Y', '+Y'):
        raise ValueError('Choose the -Y or +Y scour edge.')
    keys = set(selected)
    entries = [entry for entry in group['entries'] if entry[5] in keys]
    width = float(group['ymax'] - group['ymin'])
    if width <= 0:
        raise ValueError('Foundation has zero width.')
    extent = (max(e[4] for e in entries) - group['ymin'] if direction == '-Y'
              else group['ymax'] - min(e[3] for e in entries)) if entries else 0.0
    return {'widthCm': float(extent), 'foundationWidthCm': width,
            'ratio': float(extent / width), 'interfaceCount': len(entries)}


def partition_new_scour_patches(groups, selected, previous, direction):
    """Advance by transverse rows, pairing longitudinal ends toward the centre."""
    new = set(selected) - set(previous)
    batches = []
    for group in groups:
        rows = {}
        for entry in group['entries']:
            if entry[5] in new:
                rows.setdefault(round(float(entry[2]), 6), []).append(entry)
        for y in sorted(rows, reverse=direction == '+Y'):
            row = sorted(rows[y], key=lambda e: (e[0] + e[1], e[5]))
            for index in range((len(row) + 1) // 2):
                pair = {row[index][5], row[-index-1][5]}
                batches.append(sorted(pair))
    return batches


def normalize_workflow(raw):
    if not isinstance(raw, dict):
        raise ValueError('Scour settings must be an object.')
    try:
        pier = 'all' if str(raw['pier']).lower() == 'all' else int(raw['pier'])
        intact = int(raw['intactMaterial'])
        damaged = int(raw['scouredMaterial'])
    except (KeyError, TypeError, ValueError):
        raise ValueError('Choose a pier and both soil material keys.') from None
    if (pier != 'all' and pier < 1) or intact < 1 or damaged < 1:
        raise ValueError('Pier and material keys must be positive integers.')
    skip_audit = raw.get('skipEquilibriumAudit', False)
    if type(skip_audit) is not bool:
        raise ValueError('Equilibrium audit setting must be true or false.')
    modal_each = raw.get('modalEachStage', False)
    if type(modal_each) is not bool:
        raise ValueError('Modal sequence setting must be true or false.')
    minor = raw.get('minorStages', False)
    if type(minor) is not bool:
        raise ValueError('Minor scour stage setting must be true or false.')
    direction = raw.get('direction', '-Y')
    if direction not in ('-Y', '+Y'):
        raise ValueError('Choose the -Y or +Y scour edge.')
    stages = raw.get('stages')
    if not isinstance(stages, list) or not stages:
        raise ValueError('Configure at least one scour stage.')
    normalized=[]
    previous = -1.0
    keys=set()
    for item in stages:
        if not isinstance(item,dict):raise ValueError('Invalid scour stage.')
        try:
            key=int(item['analysisKey']);ratio=float(item['ratio'])
        except (KeyError, TypeError, ValueError):
            raise ValueError('Each scour stage needs an analysis and ratio.') from None
        if key <= 0 or key in keys or not math.isfinite(ratio) or not 0 <= ratio <= 1 or ratio < previous:
            raise ValueError('Scour stages require distinct analyses and nondecreasing total ratios from 0 to 1.')
        keys.add(key);previous=ratio
        normalized.append({'analysisKey':key,'ratio':ratio})
    return {'pier':pier,'intactMaterial':intact,'scouredMaterial':damaged,'direction':direction,'stages':normalized,'skipEquilibriumAudit':skip_audit,'modalEachStage':modal_each,'minorStages':minor}


def insert_minor_scour_stages(model, root, chain, groups, selections, direction):
    """Create explicit load-control analyses for each patch batch."""
    analyses = model.collections.analyses
    result, previous = [], set()
    for analysis in chain:
        key = int(analysis.key)
        if key not in selections:
            result.append(analysis)
            continue
        target = set(selections[key])
        if not previous <= target:
            raise ValueError('Scour selections must remain cumulative.')
        batches = partition_new_scour_patches(groups, target, previous, direction)
        if len(batches) > 1:
            if str(analysis.integration_method) != 'LoadControl' or abs(float(analysis.mult)) > 1e-12:
                raise ValueError(f'{analysis.name} must use LoadControl with zero additional load for minor scour stages.')
            element = root.find(f"Analysis[@Key='{key}']")
            if element is None:
                raise ValueError('Scour analysis is missing from the model.')
            current = set(previous)
            for index, batch in enumerate(batches[:-1], 1):
                current.update(batch)
                minor = deepcopy(analysis)
                minor.key = max(map(int, analyses), default=0) + 1
                base = f'{analysis.name}_minor_{index}'
                names = {str(item.name).casefold() for item in analyses.values()}
                minor.name = base
                suffix = 2
                while minor.name.casefold() in names:
                    minor.name = f'{base}_{suffix}'
                    suffix += 1
                analyses[minor.key] = minor
                xml = deepcopy(element)
                xml.set('Key', str(minor.key)); xml.set('Name', minor.name)
                xml.set('Description', 'Incremental scour re-equilibration')
                root.append(xml)
                selections[int(minor.key)] = sorted(current)
                result.append(minor)
        previous = target
        result.append(analysis)
    for index, analysis in enumerate(result):
        # A virgin modal and Vert each start independently.
        if index == 0 or (index == 1 and str(result[0].name).casefold() == 'modal_-1'):
            analysis.initial_analysis_key = -100
        else:
            analysis.initial_analysis_key = int(result[index - 1].key)
        element = root.find(f"Analysis[@Key='{int(analysis.key)}']")
        if element is None:
            raise ValueError('Analysis missing while building minor scour stages.')
        element.set('InitialAnalysisKey', str(analysis.initial_analysis_key))
    return result


def insert_stage_modals(model, root, sequence):
    """Insert a virgin modal and a modal after each completed static stage."""
    analyses = model.collections.analyses
    by_name = {str(a.name).casefold(): a for a in analyses.values()}
    template = by_name.get('modal_0') or by_name.get('modal_-1')
    if template is None or int(template.analysis_type) != 5:
        raise ValueError('A modal analysis is required to configure the modal sequence.')
    template_xml = root.find(f"Analysis[@Key='{int(template.key)}']")
    if template_xml is None:
        raise ValueError('The modal template is missing from the model.')

    def get_modal(name):
        existing = by_name.get(name.casefold())
        if existing is not None:
            if int(existing.analysis_type) != 5:
                raise ValueError(f'{name} exists but is not a modal analysis.')
            return existing
        key = max((int(k) for k in analyses), default=0) + 1
        modal = deepcopy(template)
        modal.key, modal.name = key, name
        analyses[key] = modal
        element = deepcopy(template_xml)
        element.set('Key', str(key)); element.set('Name', name)
        element.set('Description', f'Modal analysis after {name}')
        root.append(element)
        by_name[name.casefold()] = modal
        return modal

    virgin = get_modal('Modal_-1')
    virgin.initial_analysis_key = -100
    static = [item for item in sequence if int(item.analysis_type) != 5]
    if not static or str(static[0].name).lower() != 'vert':
        raise ValueError('The modal sequence must begin with Vert.')
    result = [virgin, static[0], get_modal('Modal_0')]
    result[2].initial_analysis_key = int(static[0].key)
    previous = result[2]
    for index, stage in enumerate(static[1:], 1):
        stage.initial_analysis_key = int(previous.key)
        modal = get_modal(f'Modal_{index}')
        modal.initial_analysis_key = int(stage.key)
        result.extend((stage, modal))
        previous = modal
    return result


def configure_sequence(model, target, workflow):
    """Make an explicit staged chain on in-memory definitions."""
    analyses = model.collections.analyses
    gravity = [a for a in analyses.values() if str(a.name).lower() == 'vert']
    if len(gravity) != 1:raise ValueError('The scour workflow requires exactly one Vert analysis.')
    stages=[]
    for item in workflow['stages']:
        a=analyses.get(item['analysisKey'])
        if a is None or not str(a.name).lower().startswith('scour') or int(a.analysis_type)==5:
            raise ValueError(f"Analysis {item['analysisKey']} is not a scour stage.")
        stages.append(a)
    numbers = [int(match.group(1)) if (match := re.fullmatch(r'scour[_ ]?(\d+)', str(a.name), re.I)) else -1 for a in stages]
    if numbers != list(range(1, len(stages) + 1)):
        raise ValueError('Configure every scour stage in sequence, starting with scour_1.')
    if int(target.analysis_type) == 5 and str(target.name).lower().replace(' ', '') == 'modal_-1':
        raise ValueError('Modal_-1 is the virgin model; select a modal analysis after scour instead.')
    modal_match = re.fullmatch(r'Modal[_ ]?(\d+)', str(target.name), re.I)
    if int(target.analysis_type) == 5 and modal_match and int(modal_match.group(1)) != len(stages):
        raise ValueError(f"{target.name} requires {modal_match.group(1)} configured scour stages.")
    if int(target.key) in {int(a.key) for a in stages}:
        stages=stages[:next(i for i,a in enumerate(stages) if a.key == target.key)+1]
    elif int(target.analysis_type) != 5:
        raise ValueError('Select a configured scour stage or a modal analysis for this workflow.')
    sequence=[gravity[0],*stages]
    if target.key != sequence[-1].key:
        sequence.append(target)
    if int(gravity[0].initial_analysis_key) >= 0:
        raise ValueError('Vert must start from the undeformed model for this workflow.')
    for previous, current in zip(sequence,sequence[1:]):
        current.initial_analysis_key=int(previous.key)
    return sequence


def pier_foundation_groups(model, wizard):
    """Match restraint footprints to pier locations in the bridge wizard."""
    elements = [e for e in wizard if e.tag in ('Abutment','Pier','Span')]
    piers = [e for e in elements if e.tag == 'Pier']
    if not piers:
        raise ValueError('The model has no wizard piers.')
    materials = {int(e.get('MaterialFoundationKey', '0')) for e in piers}
    if 0 in materials:
        raise ValueError('Cannot identify the pier foundation material.')
    groups = select_bottom_foundations(model, materials)
    cursor = 0.0
    result = []
    for element in elements:
        if element.tag == 'Span':
            cursor += float(element.get('L','0'))
        else:
            width = float(element.get('b2','0'))
            if element.tag == 'Pier':
                centre = cursor + width / 2.0
                matching = [g for g in groups if g['xmin'] - 1e-4 <= centre <= g['xmax'] + 1e-4]
                if len(matching) != 1 or matching[0] in result:
                    raise ValueError('Cannot uniquely match pier foundation interfaces; check the bridge geometry.')
                result.append(matching[0])
            cursor += width
    return result


def apply_scour_stage(session, selected, changed, material_key):
    """Change only newly scoured interfaces, retaining predecessor history."""
    newly_selected = sorted(set(selected) - changed)
    if newly_selected:
        session.change_interface_materials(newly_selected, material_key, preserve_committed_state=True)
    changed.update(newly_selected)
    return len(newly_selected)
