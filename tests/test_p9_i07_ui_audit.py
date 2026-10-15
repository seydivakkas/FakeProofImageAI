"""P9-I07 audit/regression: review linkage and screen usability, synthetic only."""
import hashlib
from types import SimpleNamespace

from PIL import Image
from aiforensics.annotation_model import AnnotationDocument
from aiforensics.review_workspace import annotation_layers
from aiforensics.review_ui import initial_image_index


def _fixture(tmp_path):
    root = tmp_path / "project"
    for part in ("images", "manifests", "annotations"):
        (root / part).mkdir(parents=True)
    image = root / "images" / "source.png"
    Image.new("RGB", (160, 90), (10, 20, 30)).save(image)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    project = SimpleNamespace(
        root=root,
        data={"images": [{"name": "source.png", "file": "source.png", "sha256": digest}]},
    )
    return project, digest


def test_editor_saved_manifest_visible_to_review(tmp_path):
    project, digest = _fixture(tmp_path)
    document = AnnotationDocument(160, 90, digest)
    document.add("line", [(3, 4), (83, 40)], family="X")
    document.save(project.root / "manifests" / f"annotations_{digest}.json")
    layers = annotation_layers(project, digest)
    assert len(layers) == 1
    assert layers[0]["count"] == 1
    assert layers[0]["kind"] == "user_annotation_unverified"


def test_legacy_annotations_folder_remains_supported(tmp_path):
    project, digest = _fixture(tmp_path)
    document = AnnotationDocument(160, 90, digest)
    document.add("point", [(7, 9)])
    document.save(project.root / "annotations" / "legacy.json")
    assert len(annotation_layers(project, digest)) == 1


def test_foreign_image_annotation_not_visible(tmp_path):
    project, digest = _fixture(tmp_path)
    document = AnnotationDocument(160, 90, "0" * 64)
    document.save(project.root / "manifests" / f"annotations_{digest}.json")
    assert annotation_layers(project, digest) == []


def test_wrong_resolution_annotation_not_visible(tmp_path):
    project, digest = _fixture(tmp_path)
    document = AnnotationDocument(170, 91, digest)
    document.save(project.root / "manifests" / f"annotations_{digest}.json")
    assert annotation_layers(project, digest) == []


def test_symlink_annotation_ignored(tmp_path):
    project, digest = _fixture(tmp_path)
    source = tmp_path / "external.json"
    doc = AnnotationDocument(160, 90, digest)
    doc.save(source)
    link = project.root / "manifests" / f"annotations_{digest}.json"
    try:
        link.symlink_to(source)
    except (OSError, NotImplementedError):
        return
    assert annotation_layers(project, digest) == []


def test_selected_image_index_respects_sha_and_no_fallback():
    images = [{"sha256": "a" * 64}, {"sha256": "b" * 64}]
    assert initial_image_index(images, "b" * 64) == 1
    assert initial_image_index(images, "c" * 64) is None
    assert initial_image_index(images, None) == 0
    assert initial_image_index([], None) is None


def test_scroll_keyboard_wiring_is_present():
    import inspect
    from aiforensics.desktop_app import DesktopApp
    text = inspect.getsource(DesktopApp)
    assert "page_canvas" in text
    assert "<Control-Key-n>" in text
    assert 'initial_image_sha=self.selected_asset_sha' in text
    assert "<F5>" in text
