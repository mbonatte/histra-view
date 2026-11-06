"""Bridge authoring and HRX material/analysis editor backed by local histra_builder."""
import base64
import binascii
import math
import tempfile
from pathlib import Path

MAX_SOURCE = 32 * 1024 * 1024


def defaults():
    from histra_builder.ui import default_payload, export_hrx
    payload = default_payload()
    raw = export_hrx(payload)
    encoded = base64.b64encode(raw).decode('ascii')
    return {
        **payload,
        'inspection': inspect_source(encoded),
    }


def catalog():
    """Native material and analysis templates available to the editor."""
    from histra_builder.generator.materials import DEFAULT_TEMPLATES
    from histra_builder.generator.native_analysis import ANALYSIS_ORDER
    return {
        'materials': [
            {'key': str(template.get('Key', '')), 'name': template.get('Name', ''),
             'type': template.get('TypeOf', '')}
            for template in DEFAULT_TEMPLATES
        ],
        'analyses': list(ANALYSIS_ORDER),
    }


def _source(encoded):
    if not isinstance(encoded, str) or len(encoded) > (MAX_SOURCE + 2) // 3 * 4:
        raise ValueError('Choose an HRX file of at most 32 MiB.')
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('Invalid HRX upload.') from exc
    if not data or len(data) > MAX_SOURCE:
        raise ValueError('Choose an HRX file of at most 32 MiB.')
    return data


def _document(data):
    from lxml import etree
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    root = etree.fromstring(data, parser)
    if root.tag != 'HiStrA':
        raise ValueError('This file is not a HiStrA model.')
    return root


def _wizard(root):
    return root.find('WizardData')


def _wizard_elements(root, tag):
    wizard = _wizard(root)
    return list(wizard.findall(tag)) if wizard is not None else []


def _collections(root):
    wizard = _wizard(root)
    layers = []
    if wizard is not None:
        elevations = wizard.find('Elevations')
        if elevations is not None:
            layers = [elevations.find(f'Layer{index}') for index in (1, 2, 3)]
            layers = [layer for layer in layers if layer is not None]
    return {
        'material': [e for e in root.findall('Template')
                     if e.get('TypeOf', '').endswith('Material')],
        'analysis': list(root.findall('Analysis')),
        'load_function': list(root.findall('LoadFunction')),
        'load_function_item': list(root.findall('LoadFunctionItem')),
        'load_combination': list(root.findall('LoadCombination')),
        'load_combination_item': list(root.findall('LoadCombinationItem')),
        'load_condition': list(root.findall('LoadCondition')),
        # C# wizard geometry.  These are the exact groups shown by the
        # Geometry tabs in the native HiStrA bridge wizard.
        'wizard_definition': [wizard.find('BridgeDefinition')] if wizard is not None and wizard.find('BridgeDefinition') is not None else [],
        'wizard_corsia': (wizard.find('BridgeDefinition').findall('Corsie/Corsia')
                          if wizard is not None and wizard.find('BridgeDefinition') is not None else []),
        'wizard_abutment': _wizard_elements(root, 'Abutment'),
        'wizard_span': _wizard_elements(root, 'Span'),
        'wizard_pier': _wizard_elements(root, 'Pier'),
        'wizard_elevation': [wizard.find('Elevations')] if wizard is not None and wizard.find('Elevations') is not None else [],
        'wizard_layer': layers,
        'wizard_trunk': (wizard.find('BridgeDefinition').findall('Trunks/Trunk')
                         if wizard is not None and wizard.find('BridgeDefinition') is not None else []),
        # Native load authoring objects.  A vehicle/line-load Template owns its
        # LoadTemplateItem rows as child nodes; the generic editor exposes each
        # row through the settings-section selector.
        'vehicle_load': [e for e in root.findall('Template')
                         if e.get('PurposeType') == 'VehicleLoad'],
        'line_load': [e for e in root.findall('Template')
                      if e.get('PurposeType') == 'LineLoad'],
        'schema': [e for e in root.findall('Template')
                   if e.get('PurposeType') == 'Schema'],
        # Model configuration (Model informations / Advanced options).
        'model_property': list(root.find('ModelProperty')) if root.find('ModelProperty') is not None else [],
        'advanced_options': [root.find('AdvancedOptionsDefault')] if root.find('AdvancedOptionsDefault') is not None else [],
        # The root carries model-wide flags such as
        # DisableGeoLinksOnLoadingLateralEarthPressure.
        'model_settings': [root],
    }


def _editable_nodes(element, kind):
    # States are execution records. They are preserved, not authoring inputs.
    nodes = []
    if kind == 'model_settings':
        return [([], element)]
    def visit(node, path):
        if not isinstance(node.tag, str) or (kind == 'analysis' and node.tag == 'States'):
            return
        nodes.append((path, node))
        for index, child in enumerate(node):
            visit(child, path + [index])
    visit(element, [])
    return nodes


def _record(element, kind):
    records = []
    for path, node in _editable_nodes(element, kind):
        # Keys identify model objects and child rows; changing one could break
        # references, so they stay read-only at every level.
        protected = ('Key', 'key', 'TypeOf')
        attrs = {k: v for k, v in node.attrib.items() if k not in protected}
        if kind == 'wizard_pier' and not path:
            attrs.setdefault('HiStrAShoulderHeight', '0')
        if kind == 'wizard_span' and not path:
            attrs.setdefault('HiStrAArchLayers', '1')
        if attrs:
            records.append({'path': path, 'tag': node.tag, 'attributes': attrs})
    name = element.get('Name')
    if not name:
        if element.tag == 'BridgeDefinition':
            name = 'Bridge definition'
        elif element.tag == 'Abutment':
            name = 'Left abutment' if element.get('AbutmentKind') == 'Sinistra' else 'Right abutment'
        elif element.tag == 'Span':
            name = 'Span'
        elif element.tag == 'Pier':
            name = 'Pier'
        elif element.tag in ('Layer1', 'Layer2', 'Layer3'):
            name = f'Backfill {element.tag[-1]}'
        elif element.tag in ('GeneralInfo', 'BuildingInfo', 'Soil', 'VitaUtile'):
            name = {
                'GeneralInfo': 'General info',
                'BuildingInfo': 'Building info',
                'Soil': 'Soil',
                'VitaUtile': 'Service life',
            }[element.tag]
        elif element.tag == 'AdvancedOptionsDefault':
            name = 'Advanced options'
        else:
            name = kind.replace('_', ' ').title()
    return {'name': name,
            'key': element.get('Key', element.get('key', element.get('Id', ''))),
            'attributes': records[0]['attributes'] if records and not records[0]['path'] else {},
            'nodes': records}


def inspect_source(encoded):
    root = _document(_source(encoded))
    collections = _collections(root)
    records = {
        kind: ([] if kind == 'model_settings' else [_record(e, kind) for e in entries])
        for kind, entries in collections.items()
    }
    if 'model_settings' in collections:
        attributes = {k: v for k, v in root.attrib.items() if k != 'version'}
        records['model_settings'] = [{
            'name': 'Model settings',
            'key': '',
            'attributes': attributes,
            'nodes': [{'path': [], 'tag': root.tag, 'attributes': attributes}],
        }]
    # Keep legacy names for clients using the original material-only API.
    return {'materials': records['material'], 'analyses': records['analysis'], 'collections': records}


def _integer_key(element):
    try:
        return int(element.get('Key', ''))
    except (TypeError, ValueError):
        return None


def _next_key(elements):
    keys = [key for key in (_integer_key(element) for element in elements) if key is not None]
    return str(max(keys, default=0) + 1)


def _unique_name(elements, preferred):
    names = {element.get('Name', '') for element in elements}
    if preferred not in names:
        return preferred
    index = 2
    while f'{preferred} ({index})' in names:
        index += 1
    return f'{preferred} ({index})'


def _model_point_keys(root):
    keys = []
    for element in root.findall('ModelPoint'):
        try:
            keys.append(int(element.get('Key', '')))
        except (TypeError, ValueError):
            continue
    return keys


def _analysis_keys(root):
    keys = set()
    for element in root.findall('Analysis'):
        key = _integer_key(element)
        if key is not None:
            keys.add(str(key))
    return keys


def _analysis_references(root, key, own=None):
    references = []
    watched = {
        'InitialAnalysisKey', 'PushModal_ModalAnalysisKey', 'MassSourceAnalysisKey',
        'AnalysisKey',
    }
    for element in root.iter():
        if element is own or not isinstance(element.tag, str):
            continue
        for attribute, value in element.attrib.items():
            if attribute in watched and value == key:
                references.append(f'{element.tag}.{attribute}')
    return references


def _material_references(root, key, own=None):
    references = []
    for element in root.iter():
        if element is own or not isinstance(element.tag, str):
            continue
        for attribute, value in element.attrib.items():
            if value == key and 'Material' in attribute:
                references.append(f'{element.tag}.{attribute}')
    return references


def _analysis_fragment(root, request):
    from histra_builder.generator.native_analysis import (
        ANALYSIS_OVERRIDES,
        analysis_specs,
        build_analysis,
    )
    from lxml import etree
    analyses = root.findall('Analysis')
    duplicate = request.get('duplicate')
    if duplicate is not None:
        if type(duplicate) is not int or duplicate < 0 or duplicate >= len(analyses):
            raise ValueError('Unknown analysis to duplicate.')
        base = analyses[duplicate]
        attributes = dict(base.attrib)
        preferred = f'{base.get("Name", "Analysis")} copy'
    else:
        template = request.get('template')
        if template not in ANALYSIS_OVERRIDES:
            raise ValueError('Unknown analysis template.')
        points = _model_point_keys(root)
        spec = next(
            item for item in analysis_specs(True, model_point_keys=points)
            if item['name'] == template
        )
        attributes = dict(spec['attributes'])
        preferred = str(attributes.get('Name', template))
    keys = _analysis_keys(root)
    attributes['Key'] = _next_key(analyses)
    attributes['Name'] = _unique_name(analyses, preferred)
    points = _model_point_keys(root)
    if points and attributes.get('MasterPoint') not in {str(key) for key in points}:
        attributes['MasterPoint'] = str(points[0])
    initial = attributes.get('InitialAnalysisKey')
    if initial not in keys and initial not in ('-100', attributes['Key']):
        attributes['InitialAnalysisKey'] = min(keys, key=int) if keys else '-100'
    modal = attributes.get('PushModal_ModalAnalysisKey')
    if modal not in keys and modal != '0':
        modal_key = next(
            (element.get('Key') for element in analyses
             if element.get('AnalysisType') == '5'), None)
        attributes['PushModal_ModalAnalysisKey'] = modal_key or (
            attributes['Key'] if attributes.get('AnalysisType') == '5' else '0')
    spec = {'name': attributes.get('Name', 'Analysis'), 'attributes': attributes}
    element = build_analysis(spec, model_point_keys=points)
    return etree.tostring(element).decode('utf-8')


def _material_fragment(root, request):
    from histra_builder.generator.materials import DEFAULT_TEMPLATES
    from lxml import etree
    materials = [e for e in root.findall('Template')
                 if e.get('TypeOf', '').endswith('Material')]
    duplicate = request.get('duplicate')
    if duplicate is not None:
        if type(duplicate) is not int or duplicate < 0 or duplicate >= len(materials):
            raise ValueError('Unknown material to duplicate.')
        base = materials[duplicate]
        attributes = dict(base.attrib)
        preferred = f'{base.get("Name", "Material")} copy'
    else:
        template = str(request.get('template', ''))
        match = next((item for item in DEFAULT_TEMPLATES if str(item.get('Key')) == template), None)
        if match is None:
            raise ValueError('Unknown material template.')
        attributes = {str(k): str(v) for k, v in match.items()}
        preferred = str(attributes.get('Name', 'Material'))
    attributes['Key'] = _next_key(materials)
    attributes['Name'] = _unique_name(materials, preferred)
    return etree.tostring(etree.Element('Template', attrib=attributes)).decode('utf-8')


def _edit_operations(root, request, collections):
    """Turn add/delete requests into deterministic compile patches."""
    from histra_builder.models import PatchOperation
    operations = request.get('operations', [])
    if not isinstance(operations, list) or len(operations) > 100:
        raise ValueError('Too many edit operations.')
    patches = []
    for operation in operations:
        if not isinstance(operation, dict):
            raise ValueError('Invalid edit operation.')
        kind = operation.get('op')
        if kind in ('add_analysis', 'duplicate_analysis'):
            xml = _analysis_fragment(root, operation)
            patches.append(PatchOperation(op='append_xml', xpath='/HiStrA', xml=xml))
            # Keep the in-memory tree in sync for later operations and key checks.
            from lxml import etree
            root.append(etree.fromstring(xml.encode('utf-8')))
            collections['analysis'] = root.findall('Analysis')
        elif kind in ('add_material', 'duplicate_material'):
            xml = _material_fragment(root, operation)
            patches.append(PatchOperation(op='append_xml', xpath='/HiStrA', xml=xml))
            from lxml import etree
            root.append(etree.fromstring(xml.encode('utf-8')))
            collections['material'] = [
                element for element in root.findall('Template')
                if element.get('TypeOf', '').endswith('Material')
            ]
        elif kind in ('delete_analysis', 'delete_material'):
            collection = 'analysis' if kind == 'delete_analysis' else 'material'
            index = operation.get('index')
            objects = collections[collection]
            if type(index) is not int or index < 0 or index >= len(objects):
                raise ValueError('Unknown model object.')
            element = objects[index]
            key = element.get('Key', '')
            own = element
            references = (_analysis_references(root, key, own)
                          if collection == 'analysis' else _material_references(root, key, own))
            if references:
                raise ValueError(
                    f'Cannot delete this {collection}; it is referenced by '
                    f'{", ".join(sorted(set(references))[:5])}.'
                )
            if key:
                xpath = f"/HiStrA/{element.tag}[@Key={key!r}]"
            else:
                xpath = element.getroottree().getpath(element)
            patches.append(PatchOperation(op='delete', xpath=xpath))
            root.remove(element)
            if collection == 'analysis':
                collections['analysis'] = root.findall('Analysis')
            else:
                collections['material'] = [
                    item for item in root.findall('Template')
                    if item.get('TypeOf', '').endswith('Material')
                ]
        else:
            raise ValueError('Unknown edit operation.')
    return patches


def _change_patches(collections, changes):
    from histra_builder.models import PatchOperation
    if not isinstance(changes, list) or len(changes) > 1000:
        raise ValueError('Too many changes.')
    patches = []
    for change in changes:
        if not isinstance(change, dict):
            raise ValueError('Invalid change.')
        # The old material-only request format remains supported.
        kind = change.get('collection', 'material')
        index = change.get('index', change.get('material'))
        if kind not in collections or type(index) is not int:
            raise ValueError('Invalid model object.')
        objects = collections[kind]
        if index < 0 or index >= len(objects):
            raise ValueError('Unknown model object.')
        path = change.get('node', [])
        if not isinstance(path, list) or any(type(i) is not int or i < 0 for i in path):
            raise ValueError('Invalid settings path.')
        editable = {tuple(p): e for p, e in _editable_nodes(objects[index], kind)}
        element = editable.get(tuple(path))
        if element is None:
            raise ValueError('Unknown or protected settings.')
        attribute, value = change.get('attribute'), change.get('value')
        protected = ('Key', 'key', 'TypeOf')
        extension = not path and ((kind == 'wizard_pier' and attribute == 'HiStrAShoulderHeight') or (kind == 'wizard_span' and attribute == 'HiStrAArchLayers'))
        if attribute in protected or (attribute not in element.attrib and not extension) or not isinstance(value, str) or len(value) > 10000:
            raise ValueError('Invalid attribute or value.')
        if value != element.get(attribute):
            patches.append(PatchOperation(op='set_attribute', xpath=element.getroottree().getpath(element), attribute=attribute, value=value))
            element.set(attribute, value)
    return patches


def _apply_patches(data, request):
    from histra_builder.compiler import compile_job
    from histra_builder.importer import job_from_hrx
    from histra_builder.templates import TemplateRegistry
    steps = request.get('steps', [])
    if not isinstance(steps, list) or len(steps) > 100:
        raise ValueError('Too many edit steps.')
    batches = [
        *(step for step in steps if isinstance(step, dict)),
        {'changes': request.get('changes', []), 'operations': request.get('operations', [])},
    ]
    if not any(batch.get('changes') or batch.get('operations') for batch in batches):
        return data
    root = _document(data)
    collections = _collections(root)
    patches = []
    for batch in batches:
        patches.extend(_change_patches(collections, batch.get('changes', [])))
        patches.extend(_edit_operations(root, batch, collections))
    if not patches:
        return data
    with tempfile.TemporaryDirectory(prefix='histra-view-builder-') as directory:
        registry = TemplateRegistry(Path(directory))
        job = job_from_hrx(data, job_id='view', template_id='source', registry=registry, validate_xml=False)
        job.model.patches = patches
        return compile_job(job, registry).hrx_bytes


def build(request):
    from histra_builder.ui import export_hrx
    if request.get('mode') == 'create':
        payload = request.get('payload')
        if not isinstance(payload, dict):
            raise ValueError('A bridge definition is required.')
        spans, strips = payload.get('spans', []), payload.get('strips', [])
        if not 1 <= len(spans) <= 12 or not 1 <= len(strips) <= 20:
            raise ValueError('Use 1–12 spans and 1–20 strips.')
        nl = float(payload.get('nl', 0))
        if not 5 <= nl <= 100000 or sum(float(s.get('L', 0)) for s in spans) / nl > 500:
            raise ValueError('Mesh size must be at least 5 and the total span length / mesh size at most 500.')
        data = export_hrx(payload)
        return _apply_patches(data, request)
    if request.get('mode') != 'edit':
        raise ValueError('Choose a build mode.')
    data = _source(request.get('source'))
    return _apply_patches(data, request)


def _regenerated_geometry(data, *, legacy_backfill=False, previous_backfill=False):
    from histra_builder.generator.csharp_import import spec_from_wizard_data
    from histra_builder.generator.csharp_mesher import CSharpMesher
    from histra_builder.generator.csharp_writer import serialize_csharp_mesh_to_hrx
    root = _document(data)
    wizard = root.find('WizardData')
    if wizard is None:
        raise ValueError('This model has no bridge wizard geometry to rebuild.')
    spec = spec_from_wizard_data(wizard)
    spec.material_templates = [dict(item.attrib) for item in root.findall('Template')
                               if item.get('TypeOf', '').endswith('Material') and item.get('Key')]
    try:
        return serialize_csharp_mesh_to_hrx(CSharpMesher(spec, legacy_backfill=legacy_backfill,
                                                        previous_backfill=previous_backfill).mesh())
    except NotImplementedError as exc:
        raise ValueError(f'Geometry regeneration is unavailable: {exc}') from exc


def preview(request):
    """Generate a geometry-only preview when an existing wizard is edited."""
    data = build(request)
    if request.get('mode') == 'edit' and request.get('rebuild_geometry'):
        return _regenerate_with_end_restraints(data)
    return data


def _has_fixed_end_restraints(root):
    supports = [e for e in root.findall('GeometryLineRestraint')
                if e.get('Name', '').startswith('HiStrAView_EndSupport_')]
    if not supports:
        return False
    sides = {e.get('Name', '').split('_')[2] for e in supports}
    restraints = {e.get('Key'): e for e in root.findall('Restraint')}
    if sides != {'Sinistra', 'Destra'}:
        raise ValueError('Cannot regenerate incomplete abutment end restraints.')
    for support in supports:
        refs = support.findall('RestraintKeys/RestraintKey')
        restraint = restraints.get(refs[0].get('Value')) if len(refs) == 1 else None
        if (support.get('K') != '-1|-1|-1|-1|-1|-1' or restraint is None or
                restraint.get('ParentKey') != support.get('Key') or
                any(restraint.get(key) != '-1' for key in ('K1', 'K2', 'K3', 'Kr1', 'Kr2', 'Kr3'))):
            raise ValueError('Cannot regenerate modified abutment end restraints.')
    return True


def _regenerate_with_end_restraints(data, *, legacy_backfill=False, previous_backfill=False):
    from abutment_restraints import add_fixed_abutment_ends
    from lateral_soil import strip_soil_supports, recreate_soil_supports
    from lxml import etree
    original = _document(data)
    settings, targets = strip_soil_supports(original)
    stripped = etree.tostring(original, encoding='utf-8', xml_declaration=True)
    has_ends = _has_fixed_end_restraints(original)
    generated = _regenerated_geometry(data, legacy_backfill=legacy_backfill, previous_backfill=previous_backfill)
    if has_ends:
        generated = add_fixed_abutment_ends(generated)
    return recreate_soil_supports(generated, settings, stripped, targets)


_GENERATED_GEOMETRY_TAGS = {'Node', 'NodeC', 'Quad', 'Restraint', 'GeometryLineRestraint', 'Bridge', 'ModelPoint'}
_SAFE_MODEL_TAGS = _GENERATED_GEOMETRY_TAGS | {
    'WizardData', 'Template', 'Layer', 'Analysis', 'LoadCondition',
    'LoadCombination', 'LoadCombinationItem', 'LoadFunction', 'LoadFunctionItem',
    'AdvancedOptionsDefault', 'ModelProperty',
}


def _element_signature(element):
    return (element.tag, tuple(sorted(element.attrib.items())),
            tuple(_element_signature(child) for child in element if isinstance(child.tag, str)))


def _geometry_signatures(root, tag):
    return [_element_signature(item) for item in root.findall(tag)]


def _geometry_matches(left, right, tag):
    """Match generator output while allowing rounding in derived Quad geometry.

    Older meshes calculated these fields before node coordinates were rounded
    to four decimal places. Node coordinates, connectivity, material,
    thickness, flags, and all other data still have to match exactly.
    """
    if tag != 'Quad':
        return _geometry_signatures(left, tag) == _geometry_signatures(right, tag)
    first, second = left.findall(tag), right.findall(tag)
    if len(first) != len(second):
        return False
    tolerances = {**{f'Length{i}': 0.0001 for i in range(1, 5)},
                  **{f'Diago{i}': 0.0001 for i in range(1, 3)},
                  **{f'Cos{i}': 0.000002 for i in range(1, 5)},
                  **{f'Sin{i}': 0.000002 for i in range(1, 5)}, 'G': 0.0002}
    def attributes_match(a, b, limits):
        if set(a.attrib) != set(b.attrib) or len(a) != len(b):
            return False
        for key, value in a.attrib.items():
            other = b.get(key)
            if value == other:
                continue
            if key not in limits:
                return False
            try:
                values = [float(item) for item in value.split(';')]
                alternatives = [float(item) for item in other.split(';')]
            except (ValueError, TypeError, AttributeError):
                return False
            if (len(values) != len(alternatives) or not values or
                    any(not math.isfinite(x) or not math.isfinite(y) or abs(x-y) > limits[key]
                        for x, y in zip(values, alternatives))):
                return False
        return True
    for a, b in zip(first, second):
        if not attributes_match(a, b, tolerances):
            return False
        for x, y in zip(a, b):
            if x.tag == y.tag == 'ReferenceSystem' and not len(x) and not len(y):
                if not attributes_match(x, y, {'Origin': 0.0001, 'E1': 0.000002,
                                                'E2': 0.000002, 'E3': 0.000002}):
                    return False
            elif _element_signature(x) != _element_signature(y):
                return False
    return True


def needs_backfill_regeneration(data):
    """Recognize unchanged meshes produced by the previous backfill algorithm."""
    try:
        root = _document(data)
        wizard = root.find('WizardData')
        definition = wizard.find('BridgeDefinition') if wizard is not None else None
        section = wizard.find('Elevations/Elevations/Elevation') if wizard is not None else None
        if definition is None or section is None:
            return False
        nl = float(definition.get('Nl', '0'))
        h1, h2, h3 = (float(section.get(key, '0')) for key in ('H1', 'H2', 'H3'))
        crosses = any(float(span.get('f', '0')) + float(span.get('Tt', '0')) > h1 + 1e-6
                      for span in wizard.findall('Span'))
        if not crosses and not (nl > 0 and max(h2, h3) > nl):
            return False
        from lateral_soil import strip_soil_supports
        from lxml import etree
        strip_soil_supports(root)
        data = etree.tostring(root, encoding='utf-8', xml_declaration=True)
        current = _document(_regenerate_with_end_restraints(data))
        if all(_geometry_matches(root, current, tag)
               for tag in _GENERATED_GEOMETRY_TAGS):
            return False
        for profile in ({'previous_backfill': True}, {'legacy_backfill': True}):
            old = _document(_regenerate_with_end_restraints(data, **profile))
            if all(_geometry_matches(root, old, tag)
                   for tag in _GENERATED_GEOMETRY_TAGS):
                return True
        return False
    except (ValueError, TypeError, KeyError, NotImplementedError):
        return False


def _regenerate_export(original, edited, *, replace_existing=False):
    """Replace only geometry verified as belonging to the current generator."""
    from copy import deepcopy
    from lxml import etree
    old_root = _document(original)
    edited_root = _document(edited)
    from lateral_soil import strip_soil_supports
    comparison_root = _document(original)
    soil_settings, _ = strip_soil_supports(comparison_root)
    has_ends = _has_fixed_end_restraints(old_root)
    unsupported = sorted({element.tag for element in old_root if element.tag not in _SAFE_MODEL_TAGS})
    if unsupported:
        raise ValueError('Cannot safely regenerate this model: unsupported objects ' + ', '.join(unsupported))
    for element in old_root:
        if element.tag in _GENERATED_GEOMETRY_TAGS or element.tag == 'WizardData':
            continue
        for node in element.iter():
            for key, value in node.attrib.items():
                if (key.startswith(('NodeKey', 'QuadKey', 'RestraintKey')) or
                        key in {'ElementKey', 'IdElement', 'ComputationalElementKey', 'ParentElementKey'}):
                    if value not in {'', '0', '-1'}:
                        raise ValueError(f'Cannot safely transfer {node.tag}.{key} to the regenerated mesh.')
    for analysis in old_root.findall('Analysis'):
        for state in analysis.findall('States/State'):
            if state.get('Exit') != 'NotExecuted':
                raise ValueError('Cannot regenerate a model with executed analysis states; use an unexecuted model.')
    if replace_existing:
        for quad in old_root.findall('Quad'):
            if any(quad.get(key, 'false').lower() == 'true' for key in ('IsGeometryCustomized', 'IsPropertyModified')):
                raise ValueError('Cannot replace a mesh with customized Quad geometry or properties.')
            if any(quad.get(key, '0') not in {'', '0', '-1'} for key in ('LoadTemplateAreaKey', 'LoadTemplateLineKey', 'LoadTemplatePointKey')):
                raise ValueError('Cannot transfer loads assigned directly to Quads.')
        baseline = old_root
    else:
        comparison_bytes = etree.tostring(comparison_root, encoding='utf-8', xml_declaration=True)
        baseline = _document(_regenerate_with_end_restraints(comparison_bytes))
        differences = [tag for tag in _GENERATED_GEOMETRY_TAGS
                       if not _geometry_matches(comparison_root, baseline, tag)]
        if differences:
            legacy = None
            for profile in ({'previous_backfill': True}, {'legacy_backfill': True}):
                candidate = _document(_regenerate_with_end_restraints(comparison_bytes, **profile))
                if all(_geometry_matches(comparison_root, candidate, tag)
                       for tag in _GENERATED_GEOMETRY_TAGS):
                    legacy = candidate
                    break
            if legacy is None:
                raise ValueError(f'Cannot safely regenerate this model: its {differences[0]} objects differ from the generated wizard mesh.')
            baseline = legacy
    updated = _document(_regenerate_with_end_restraints(edited) if has_ends or soil_settings else _regenerated_geometry(edited))
    def point_roles(root):
        return [(point.get('Key'), point.get('Description', '').split('Point in (')[0])
                for point in root.findall('ModelPoint')]
    if point_roles(baseline) != point_roles(updated):
        raise ValueError('Cannot safely transfer monitoring points to the regenerated mesh.')
    for element in list(edited_root):
        if element.tag in _GENERATED_GEOMETRY_TAGS:
            edited_root.remove(element)
    for element in updated:
        if element.tag in _GENERATED_GEOMETRY_TAGS:
            edited_root.append(deepcopy(element))
    return etree.tostring(edited_root, xml_declaration=True, encoding='utf-8', pretty_print=True)


def export(request):
    """Regenerate verified wizard geometry before exporting edits."""
    if request.get('mode') == 'edit':
        batches = [*(request.get('steps') or []), request]
        geometry_changed = request.get('rebuild_geometry') or any(
            isinstance(batch, dict) and any(
                isinstance(change, dict) and str(change.get('collection', '')).startswith('wizard_')
                for change in (batch.get('changes') or [])
            ) for batch in batches
        )
        if geometry_changed:
            return _regenerate_export(_source(request.get('source')), build(request), replace_existing=request.get('replace_existing_mesh') is True)
    return build(request)


def apply_edits(request):
    """Apply edits and return the new source plus its re-inspected collections."""
    data = build(request)
    encoded = base64.b64encode(data).decode('ascii')
    return {'source': encoded, 'inspection': inspect_source(encoded)}


def add_abutment_end_restraints(request):
    from abutment_restraints import add_fixed_abutment_ends
    from hrx_model import parse_hrx
    if request.get('mode') != 'edit':
        raise ValueError('Open an existing HRX model first.')
    batches = [*(request.get('steps') or []), request]
    if any(str(change.get('collection', '')).startswith('wizard_')
           for batch in batches if isinstance(batch, dict)
           for change in batch.get('changes', []) if isinstance(change, dict)):
        raise ValueError('Regenerate and reopen the model before adding end restraints.')
    data = add_fixed_abutment_ends(build(request))
    encoded = base64.b64encode(data).decode('ascii')
    return {'source': encoded, 'inspection': inspect_source(encoded),
            'model': parse_hrx(data, 'Abutment restraints preview.hrx')}
