"""Bridge authoring and HRX material/analysis editor backed by local histra_builder."""
import base64
import binascii
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


def _collections(root):
    return {
        'material': [e for e in root.findall('Template')
                     if e.get('TypeOf', '').endswith('Material')],
        'analysis': list(root.findall('Analysis')),
        'load_function': list(root.findall('LoadFunction')),
        'load_function_item': list(root.findall('LoadFunctionItem')),
        'load_combination': list(root.findall('LoadCombination')),
        'load_combination_item': list(root.findall('LoadCombinationItem')),
        'load_condition': list(root.findall('LoadCondition')),
    }


def _editable_nodes(element, kind):
    # States are execution records. They are preserved, not authoring inputs.
    nodes = []
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
        # Root keys identify model objects; changing one could break references.
        protected = ('Key', 'key', 'TypeOf') if not path else ('TypeOf',)
        attrs = {k: v for k, v in node.attrib.items() if k not in protected}
        if attrs:
            records.append({'path': path, 'tag': node.tag, 'attributes': attrs})
    return {'name': element.get('Name', kind.title()), 'key': element.get('Key', element.get('key', '')),
            'attributes': records[0]['attributes'] if records and not records[0]['path'] else {},
            'nodes': records}


def inspect_source(encoded):
    root = _document(_source(encoded))
    collections = _collections(root)
    records = {kind: [_record(e, kind) for e in entries] for kind, entries in collections.items()}
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
        protected = ('Key', 'key', 'TypeOf') if not path else ('TypeOf',)
        if attribute in protected or attribute not in element.attrib or not isinstance(value, str) or len(value) > 10000:
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


def apply_edits(request):
    """Apply edits and return the new source plus its re-inspected collections."""
    data = build(request)
    encoded = base64.b64encode(data).decode('ascii')
    return {'source': encoded, 'inspection': inspect_source(encoded)}
