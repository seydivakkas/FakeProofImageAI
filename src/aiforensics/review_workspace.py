"""P9-I04 auditable offline evidence/image review and explicit user bindings.

Links are user assertions, never independently authenticated evidence. A model
output alone does not establish that it belongs to an imported photograph.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .annotation_model import AnnotationDocument, AnnotationError

SCHEMA = 'fakeproof.review.v1'
MAX_JSON = 20 * 1024 * 1024
MAX_LINKS = 5000
RUN_PATTERN = re.compile(r'^[A-Za-z0-9_-]{1,96}$')


class ReviewError(ValueError):
    pass


def _asset_digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _within(root, child):
    root = Path(root).resolve()
    child = Path(child).resolve()
    try:
        child.relative_to(root)
    except ValueError as exc:
        raise ReviewError('Dosya çalışma alanının dışında') from exc
    return child


def _safe_json(path):
    path = Path(path)
    if path.stat().st_size > MAX_JSON:
        raise ReviewError('Rapor dosyası boyut sınırını aşıyor')
    def no_constants(value):
        raise ReviewError('Geçersiz sayı sabiti: ' + value)
    return json.loads(path.read_text(encoding='utf-8'), parse_constant=no_constants)


def _image_match(project, image_sha):
    if not isinstance(image_sha, str) or not re.fullmatch(r'[0-9a-f]{64}', image_sha):
        raise ReviewError('Geçersiz görüntü SHA-256')
    matches = [entry for entry in project.data['images'] if entry['sha256'] == image_sha]
    if len(matches) != 1:
        raise ReviewError('Görüntü proje envanterinde tekil değil')
    entry = matches[0]
    path = _within(project.root / 'images', project.root / 'images' / entry['file'])
    if not path.is_file() or _asset_digest(path) != image_sha:
        raise ReviewError('Görüntü dosyasının SHA-256 değeri değişmiş')
    return path, entry


def list_images(project):
    return [{'name': e['name'], 'sha256': e['sha256'], 'file': e['file'],
             'camera_origin_verified': False} for e in project.data['images']]


def annotation_layers(project, image_sha):
    path, _ = _image_match(project, image_sha)
    output = []
    annotation_root = project.root / 'annotations'
    if not annotation_root.exists():
        return output
    for candidate in sorted(annotation_root.glob('*.json'))[:5000]:
        if candidate.is_symlink() or candidate.stat().st_size > 16*1024*1024:
            continue
        try:
            doc = AnnotationDocument.load(candidate, image_sha256=image_sha)
        except (OSError, ValueError, AnnotationError):
            continue
        output.append({'id': candidate.name, 'path': candidate,
                       'count': len(doc.marks), 'marks': doc.marks,
                       'kind': 'user_annotation_unverified'})
    return output


def report_catalog(project):
    """Only reports in recorded run folders, no fabricated links or verdicts."""
    output = []
    for run in project.data['runs']:
        run_id = run.get('run_id', '')
        if not RUN_PATTERN.fullmatch(run_id):
            continue
        folder = _within(project.root / 'runs', project.root / 'runs' / run_id)
        if not folder.is_dir():
            continue
        for name in ('p8_e03_explainable_report.json', 'p8_e02_fusion_report.json',
                     'p8_e01_evidence_report.json'):
            file = folder / name
            if file.is_symlink() or not file.is_file():
                continue
            try:
                body = _safe_json(file)
                if not isinstance(body, dict) or body.get('decision') != 'NO_AI_ORIGIN_CONCLUSION':
                    continue
                expected = {'p8_e03_explainable_report.json': 'p8.e03.v1',
                            'p8_e02_fusion_report.json': 'p8.e02.v1',
                            'p8_e01_evidence_report.json': 'p8.e01.v1'}[name]
                if body.get('schema_version') != expected:
                    continue
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            output.append({'id': run_id + '/' + name,
                           'path': file, 'run_id': run_id,
                           'schema_version': expected,
                           'sha256': _asset_digest(file),
                           'record_count': len(body.get('findings', body.get('records', []))),
                           'overall_state': body.get('summary', {}).get('overall_state',
                                                      body.get('overall_state', 'NOT_EVALUATED'))})
    return output


def read_report(project, report_id):
    match = next((r for r in report_catalog(project) if r['id'] == report_id), None)
    if match is None:
        raise ReviewError('Rapor bulunamadı veya şema geçerli değil')
    if _asset_digest(match['path']) != match['sha256']:
        raise ReviewError('Rapor içeriği değişmiş')
    return _safe_json(match['path'])


def dependency_graph(report):
    """Returns only declared shared lineage edges or E02 explicit dependencies."""
    if report.get('schema_version') != 'p8.e03.v1':
        raise ReviewError('E03 raporu gerekli')
    groups = report.get('dependency_groups')
    findings = report.get('findings')
    if not isinstance(groups, list) or not isinstance(findings, list):
        raise ReviewError('Rapor bağımlılık alanları eksik')
    ids = [x.get('record_id') for x in findings]
    if not all(isinstance(x, str) for x in ids) or len(ids) != len(set(ids)):
        raise ReviewError('Tekil olmayan kanıt kayıtları')
    edges = []
    for group in groups:
        members = group.get('members')
        if not isinstance(members, list) or any(m not in ids for m in members):
            raise ReviewError('Bağımlılık üyesi kayıt dışı')
        for link in group.get('explicit_edges', []):
            if link.get('left') not in members or link.get('right') not in members:
                raise ReviewError('Bağımlılık kenarı kayıt dışı')
            edges.append({'from': link['left'], 'to': link['right'],
                          'reason': str(link.get('reason', '')),
                          'kind': 'explicit_declared'})
        for item in group.get('shared_evidence', {}).get('shared_references', []):
            uses = item.get('members', [])
            if not isinstance(uses, list) or any(m not in members for m in uses):
                raise ReviewError('Ortak kaynak üyesi kayıt dışı')
            # star structure prevents fabricated pairwise hypothesis independence.
            for other in uses[1:]:
                edges.append({'from': uses[0], 'to': other,
                              'reason': str(item.get('field', '')) + '=' + str(item.get('identifier', '')),
                              'kind': 'shared_lineage'})
    return {'nodes': [{'id': f['record_id'], 'module': f.get('module_id', ''),
                       'group': f.get('dependency', {}).get('component_id'),
                       'state': f.get('single_test', {}).get('state')}
                      for f in findings], 'edges': edges,
            'note': 'Grup üyeliği bağımsızlık kanıtı değildir.'}


def _binding_path(project):
    return project.root / 'review_links.json'


def read_bindings(project):
    path = _binding_path(project)
    if not path.exists():
        return []
    body = _safe_json(path)
    if not isinstance(body, dict) or body.get('schema_version') != SCHEMA or not isinstance(body.get('links'), list):
        raise ReviewError('İnceleme bağlantı sözleşmesi geçersiz')
    if len(body['links']) > MAX_LINKS:
        raise ReviewError('Çok fazla bağlantı')
    return body['links']


def bind_finding_to_image(project, report_id, record_id, image_sha):
    """Explicit user association; preserves unverified provenance."""
    _image_match(project, image_sha)
    report = read_report(project, report_id)
    findings = report.get('findings', [])
    if report.get('schema_version') != 'p8.e03.v1' or not isinstance(findings, list):
        raise ReviewError('E03 açıklanabilir kanıt raporu gerekli')
    if not isinstance(record_id, str) or record_id not in {f.get('record_id') for f in findings}:
        raise ReviewError('Kanıt kaydı raporda bulunmuyor')
    links = read_bindings(project)
    item = {'report_id': report_id, 'record_id': record_id,
            'image_sha256': image_sha, 'link_type': 'user_asserted_not_verified'}
    if item not in links:
        if len(links) >= MAX_LINKS:
            raise ReviewError('Bağlantı üst sınırına ulaşıldı')
        links.append(item)
    target = _binding_path(project)
    fd, tmp = tempfile.mkstemp(prefix='.links-', dir=project.root, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'schema_version': SCHEMA, 'links': links,
                       'decision': 'NO_AI_ORIGIN_CONCLUSION'}, stream,
                      ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return item


def linked_images(project, report_id, record_id):
    matches = [x for x in read_bindings(project) if x.get('report_id') == report_id
               and x.get('record_id') == record_id]
    result = []
    for link in matches:
        try:
            _, entry = _image_match(project, link['image_sha256'])
            report = read_report(project, report_id)
            if not any(f.get('record_id') == record_id for f in report.get('findings', [])):
                continue
        except (ReviewError, OSError, KeyError):
            continue
        result.append({'image': entry['name'], 'sha256': entry['sha256'],
                       'provenance': 'user_asserted_not_verified'})
    return result


def register_overlay(project, image_sha, png_path):
    """Copy externally selected PNG with verified geometry; user-asserted association."""
    _image_match(project, image_sha)
    source = Path(png_path).expanduser().resolve(strict=True)
    if source.suffix.lower() != '.png' or not source.is_file() or source.stat().st_size > 40 * 1024 * 1024:
        raise ReviewError('PNG katmanı boyut/tür koşullarını sağlamıyor')
    try:
        from PIL import Image
    except ImportError as exc:
        raise ReviewError('PNG katmanları için Pillow yüklenmeli') from exc
    image_path, _ = _image_match(project, image_sha)
    with Image.open(image_path) as base, Image.open(source) as overlay:
        if overlay.size != base.size:
            raise ReviewError('Katman piksel boyutu özgün görüntüyle eşleşmiyor')
        overlay.verify()
    digest = _asset_digest(source)
    overlay_dir = project.root / 'review_overlays'
    overlay_dir.mkdir(exist_ok=True)
    target = overlay_dir / (digest + '.png')
    if not target.exists():
        import shutil
        shutil.copyfile(source, target)
    if _asset_digest(target) != digest:
        raise ReviewError('Katman SHA-256 eşleşmedi')
    path = project.root / 'review_overlays.json'
    if path.exists():
        items = _safe_json(path)
        if not isinstance(items, dict) or items.get('schema_version') != SCHEMA or not isinstance(items.get('overlays'), list):
            raise ReviewError('Katman envanteri geçersiz')
        entries = items['overlays']
    else:
        entries = []
    item = {'image_sha256': image_sha, 'file_sha256': digest,
            'file': digest + '.png', 'source_label': source.name,
            'verification': 'user_asserted_unverified'}
    if item not in entries:
        if len(entries) >= MAX_LINKS:
            raise ReviewError('Katman sayısı sınırı')
        entries.append(item)
    fd, tmp = tempfile.mkstemp(prefix='.overlays-', suffix='.tmp', dir=project.root)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump({'schema_version': SCHEMA, 'overlays': entries}, stream,
                      indent=2, ensure_ascii=False, allow_nan=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return item


def image_overlays(project, image_sha):
    _image_match(project, image_sha)
    path = project.root / 'review_overlays.json'
    if not path.exists():
        return []
    body = _safe_json(path)
    if not isinstance(body, dict) or body.get('schema_version') != SCHEMA or not isinstance(body.get('overlays'), list):
        raise ReviewError('Katman envanteri geçersiz')
    if len(body['overlays']) > MAX_LINKS:
        raise ReviewError('Katman envanteri çok büyük')
    output = []
    for item in body['overlays']:
        if not isinstance(item, dict) or item.get('image_sha256') != image_sha:
            continue
        digest = item.get('file_sha256', '')
        if not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            continue
        if item.get('file') != digest+'.png':
            continue
        target = _within(project.root / 'review_overlays', project.root / 'review_overlays' / item['file'])
        if target.is_file() and _asset_digest(target) == digest:
            output.append({'name': item.get('source_label', ''), 'path': target,
                           'digest': digest, 'verified_source': False})
    return output
