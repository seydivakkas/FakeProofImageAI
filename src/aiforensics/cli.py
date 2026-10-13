"""Command line: analyze a photo; generate example; run controlled benchmark."""
from __future__ import annotations
import argparse
import hashlib
import json
import platform
from pathlib import Path
import numpy as np
import cv2
import scipy
from . import __version__
from .imaging import load_bgr, write_image, detect_segments, overlay_measurements
from .synthetic import render_corridor, noisy_vp_case
from .vp import fit_vp, find_vps, VPConfig
from .calibration import (CalibrationError, calibrate_three_orthogonal_vps, calibrate_from_g01_groups)
from .synthetic_camera import camera_ground_truth, labeled_segments_from_vps
from .cross_ratio import analyze_repeated_landmarks, ProjectiveEvidenceError
from .real_validation import run_real_manifest, RealValidationError, batch_real_validation
from .auto_patterns import analyze_auto_pattern_file, PatternConfig
from .homography import analyze_g04_manifest, HomographyError
from .region_patterns import run_region_manifest
from .g04_pair import run_photo_pair
from .shadow_geometry import ShadowConfig, ShadowEvidenceError, run_shadow_manifest, fit_projected_light
from .shadow_synthetic import synthetic_shadow_scene
from .shadow_multilight import MultiLightConfig, run_multilight_manifest
from .shadow_multi_synthetic import synthetic_multilight_scene
from .shadow_3d import Shadow3DConfig, Shadow3DError, run_shadow3d_manifest
from .shadow_3d_synthetic import synthetic_shadow3d_scene
from .solar_geometry import SolarConfig, SolarGeometryError, run_solar_manifest
from .solar_synthetic import synthetic_solar_scene
from .penumbra import PenumbraConfig, PenumbraError, run_penumbra_manifest
from .penumbra_synthetic import synthetic_penumbra_fixture
from .penumbra_sampling import run_sample_transects
from .mirror_geometry import MirrorGeometryError, run_mirror_manifest
from .mirror_synthetic import synthetic_mirror_scene
from .refraction_geometry import RefractionGeometryError, run_refraction_manifest
from .refraction_synthetic import synthetic_refraction_scene
from .refraction_index import run_index_manifest
from .mirror_chain import MirrorChainError, run_multi_mirror_manifest
from .mirror_chain_synthetic import synthetic_two_mirror_scene, render_chain_xz_diagram
from .lens_distortion import LensGeometryError, LensConfig, run_lens_manifest
from .lens_synthetic import synthetic_lens_scene
from .defocus import DefocusError, run_defocus_manifest
from .defocus_synthetic import synthetic_defocus_fixture, render_defocus_comparison
from .optical_consistency import OpticalConsistencyError, OpticalConfig, run_optical_manifest, camera_fovs
from .optical_synthetic import synthetic_optical_fixture, render_optical_overlay
from .vignetting import VignettingError, VignettingConfig, run_vignetting_manifest, sample_linear_regions
from .vignetting_synthetic import synthetic_vignetting_fixture, render_vignetting_demo, render_vignetting_radial_profile
from .depth_contact import DepthContactConfig, DepthContactError, run_depth_contact_manifest
from .depth_contact_synthetic import synthetic_depth_contact_fixture, render_depth_contact_overlay
from .depth_occlusion import OcclusionConfig, OcclusionGeometryError, run_occlusion_manifest
from .depth_occlusion_synthetic import synthetic_occlusion_fixture, render_occlusion_overlay
from .static_equilibrium import EquilibriumConfig, StaticEquilibriumError, run_static_manifest
from .static_equilibrium_synthetic import synthetic_equilibrium_fixture
from .material_physics import MaterialPhysicsError, MaterialConfig, run_material_manifest, audit_brdf_matrix, hemisphere_quadrature
from .material_synthetic import synthetic_material_fixture, draw_material_demo
from .microfacet_physics import (MicrofacetConfig, MicrofacetError, run_microfacet_manifest, audit_ggx_energy)
from .microfacet_synthetic import synthetic_microfacet_fixture, render_microfacet_report
from .combined_material import (CombinedMaterialError, CombinedMaterialConfig, run_combined_manifest, audit_combined_energy)
from .combined_material_synthetic import synthetic_combined_fixture, render_combined_report
from .sensor_noise import (SensorNoiseError, SensorNoiseConfig, SensorParameters,
                           run_sensor_manifest, summarize_temporal_raw_stack)
from .sensor_synthetic import synthetic_sensor_fixture, render_sensor_demo
from .sensor_fingerprint import FingerprintError, run_fingerprint_manifest
from .sensor_fingerprint_synthetic import write_synthetic_fingerprint_fixture, render_fingerprint_summary
from .evidence_contract import run_evidence_manifest, MODULES, EvidenceContractError
from .evidence_fusion import run_fusion_manifest


def _write_report(out: Path, data: dict):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def analyze(image_path: Path, out: Path, method: str, config: VPConfig) -> dict:
    img = load_bgr(image_path)
    segments = detect_segments(img, method=method)
    fits = find_vps(segments, img.shape[:2], max_models=3, config=config)
    out.mkdir(parents=True, exist_ok=True)
    overlay_path = out / "g01_overlay.png"
    write_image(overlay_path, overlay_measurements(img, segments, fits))
    report = {
        "project": "AI Image Forensics — Physics First",
        "version": __version__,
        "module": "G01_FINITE_VANISHING_POINTS",
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "image_dimensions_hw": list(img.shape[:2]),
        "detector": method,
        "detected_segments": int(len(segments)),
        "vp_models": [m.to_dict() for m in fits],
        "g02": {"state": "INDETERMINATE",
                "reason": "Unlabeled G01 VP families cannot be assumed mutually orthogonal. "
                          "Use calibrate-segments with externally established orthogonal families."},
        "state": "MEASURED" if fits else "INDETERMINATE",
        "decision": "NO_AI_ORIGIN_CONCLUSION",
        "assumptions": ["straight 3D features", "approximately pinhole camera", "finite VP", 
                        "each VP family represents a separate 3D direction"],
        "limitations": ["different legitimate directions produce different vanishing points",
                        "lens distortion, panorama stitching and curved surfaces may change measurements",
                        "sequential RANSAC returns descriptive structure; not a physical consistency verdict",
                        "bootstrap standard deviation is exploratory, not calibrated 95% uncertainty",
                        "no verified AI-origin assessment or false-positive calibration"],
        "runtime_versions": {"python": platform.python_version(), "numpy": np.__version__,
                             "opencv": cv2.__version__, "scipy": scipy.__version__},
        "overlay": overlay_path.name,
    }
    _write_report(out/"g01_report.json", report)
    return report


def demo(out: Path, config: VPConfig):
    out.mkdir(parents=True,exist_ok=True)
    image, truth = render_corridor()
    corridor_path = out/"synthetic_corridor.png"
    write_image(corridor_path,image)
    report = analyze(corridor_path,out/"corridor_analysis","lsd",config)
    segments,mask,gt = noisy_vp_case()
    fit = fit_vp(segments, (720,1280), config)
    synthetic_line_image = np.full((720,1280,3), (35,42,48),dtype=np.uint8)
    for s, is_real_direction in zip(segments, mask):
        a,b=tuple(np.round(s[:2]).astype(int)),tuple(np.round(s[2:]).astype(int))
        cv2.line(synthetic_line_image,a,b,(200,160,120) if is_real_direction else (85,85,85),2,cv2.LINE_AA)
    write_image(out/"synthetic_noisy_lines.png",synthetic_line_image)
    write_image(out/"synthetic_noisy_lines_fitted.png",
                overlay_measurements(synthetic_line_image,segments,[fit] if fit else []))
    summary={"synthetic_corridor_vp_ground_truth_xy":list(truth),
             "corridor_primary_fitted_vp_xy":report["vp_models"][0]["vp_xy_px"] if report["vp_models"] else None,
             "controlled_lines_ground_truth_xy":gt.tolist(),
             "controlled_lines_fit":fit.to_dict() if fit else None,
             "controlled_lines_inlier_ground_truth_count":int(mask.sum())}
    _write_report(out/"demo_ground_truth.json",summary)
    # Independent labeled-family integration fixture with known camera K/R.
    truth_K, truth_R, truth_vps = camera_ground_truth()
    labeled = labeled_segments_from_vps(truth_vps)
    g02 = calibrate_from_g01_groups(labeled, (720, 1280), config)
    camera_demo = {
        "ground_truth_K": truth_K.tolist(), "ground_truth_R": truth_R.tolist(),
        "ground_truth_vps_xy": truth_vps.tolist(), "result": g02,
        "scenario": "controlled 3 orthogonal projected directions; labeled 2D lines",
    }
    if g02['state'] == 'MEASURED':
        estimated_K = np.array(g02['g02_calibration']['K'])
        camera_demo['focal_absolute_error_px'] = abs(float(estimated_K[0,0] - truth_K[0,0]))
        camera_demo['principal_error_px'] = float(np.linalg.norm(estimated_K[:2,2]-truth_K[:2,2]))
    _write_report(out/"g02_labeled_camera_demo.json",camera_demo)
    # A visual audit trail for synthetic group labels (off-canvas VPs in JSON).
    canvas = np.full((720, 1280, 3), (28, 36, 43), dtype=np.uint8)
    palette = [(80, 210, 255), (80, 220, 130), (255, 165, 85)]
    for group_idx, (group, color) in enumerate(zip(labeled, palette)):
        for seg in group:
            p1, p2 = tuple(np.round(seg[:2]).astype(int)), tuple(np.round(seg[2:]).astype(int))
            cv2.line(canvas, p1, p2, color, 1, cv2.LINE_AA)
        cv2.putText(canvas, f"3D axis group {group_idx+1}: {len(group)} lines",
                    (20, 35 + 35*group_idx), cv2.FONT_HERSHEY_SIMPLEX, .8, color, 2, cv2.LINE_AA)
    cv2.putText(canvas, "SYNTHETIC LABELED LINE FIXTURE - NOT REAL IMAGE EVIDENCE",
                (20, 685), cv2.FONT_HERSHEY_SIMPLEX, .67, (235, 235, 235), 2, cv2.LINE_AA)
    write_image(out/"g02_labeled_orthogonal_line_fixture.png", canvas)
    summary['g02_labeled_camera_state'] = g02['state']
    return summary


def benchmark(out: Path, n: int, config: VPConfig):
    """Ground-truth regression benchmark, not a real-image accuracy experiment."""
    errors=[]
    failures=0
    for seed in range(n):
        seg,mask,gt = noisy_vp_case(endpoint_sigma_px=0.75,seed=seed,
                                   outlier_count=20)
        fit=fit_vp(seg,(720,1280),config)
        if fit is None:
            failures+=1
        else:
            errors.append(float(np.linalg.norm(np.asarray(fit.xy)-gt)))
    result={"scenario":"controlled finite VP + 0.75px Gaussian endpoint noise + 20 outlier segments",
            "trials":n,"successful_fits":len(errors),"failed_fits":failures,
            "vp_error_median_px_successes":float(np.median(errors)) if errors else None,
            "vp_error_p90_px_successes":float(np.percentile(errors,90)) if errors else None,
            "vp_error_max_px_successes":float(np.max(errors)) if errors else None,
            "not_measured":["real photo FPR", "AI image classification", "real camera calibration"]}
    _write_report(out/"synthetic_benchmark.json",result)
    return result



def benchmark_g02(out: Path, n: int, config: VPConfig) -> dict:
    """Known-truth G01-labeled-lines-to-G02 benchmark (NOT field validation)."""
    K, _, vps = camera_ground_truth()
    errors = []
    failures = []
    for seed in range(n):
        groups = labeled_segments_from_vps(vps, count_per_group=45,
                                           endpoint_noise=.35, seed=seed)
        result = calibrate_from_g01_groups(groups, (720, 1280), config)
        if result['state'] != 'MEASURED':
            failures.append({'seed':seed, 'reason':result.get('reason','unknown')})
            continue
        Kest = np.asarray(result['g02_calibration']['K'])
        errors.append([abs(float(Kest[0,0]-K[0,0])),
                       float(np.linalg.norm(Kest[:2,2]-K[:2,2]))])
    e = np.asarray(errors)
    response = {
        'scenario': 'known synthetic orthogonal VP geometry -> noisy labeled 2D line segments -> G01 -> G02',
        'endpoint_noise_sigma_px': .35,
        'segments_per_direction': 45,
        'image_dimensions_hw': [720,1280],
        'camera_focal_ground_truth_px': float(K[0,0]),
        'trials': n, 'successful_calibrations': len(errors),
        'indeterminate_calibrations': len(failures), 'failures': failures,
        'focal_absolute_error_median_px_successes': float(np.median(e[:,0])) if len(e) else None,
        'focal_absolute_error_p90_px_successes': float(np.percentile(e[:,0], 90)) if len(e) else None,
        'principal_point_error_median_px_successes': float(np.median(e[:,1])) if len(e) else None,
        'principal_point_error_p90_px_successes': float(np.percentile(e[:,1],90)) if len(e) else None,
        'limitations': ['fixed one camera model and synthetic labeled 2D line family generator',
                        'labels certify orthogonality by construction, not recovered from image',
                        'not measured: real photos, lens distortions, false alarms, AI detection'],
        'decision': 'NO_AI_ORIGIN_CONCLUSION',
    }
    _write_report(out/'g02_benchmark.json', response)
    return response


def run_calibration_from_points(vps_xy: list[list[float]], shape: tuple[int, int], out: Path) -> dict:
    try:
        cal = calibrate_three_orthogonal_vps(np.array(vps_xy), shape)
        result = cal.to_dict()
    except CalibrationError as e:
        result = {'state': 'INDETERMINATE', 'reason': str(e), 'decision': 'NO_AI_ORIGIN_CONCLUSION'}
    result['module'] = 'G02_K_R_FROM_THREE_ORTHOGONAL_VPS'
    result['input_vps_xy'] = vps_xy
    _write_report(out/'g02_calibration.json',result)
    return result


def run_calibration_from_segments(input_path: Path, out: Path, config: VPConfig) -> dict:
    data = json.loads(input_path.read_text(encoding='utf-8'))
    if 'orthogonal_groups' not in data or 'image_shape_hw' not in data:
        raise ValueError('JSON requires image_shape_hw and orthogonal_groups')
    groups = [np.asarray(s, dtype=float) for s in data['orthogonal_groups']]
    shape = tuple(data['image_shape_hw'])
    result = calibrate_from_g01_groups(groups, shape, config)
    result['input_file'] = str(input_path)
    _write_report(out/'g01_g02_report.json',result)
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description="Physics-first image measurements G01–G04 / P2-S01–S05 / P3-R01/R02/R03 / P4-O01/O02/O03/O04 / P5-D01/D02/D03 / P6-M01 (NOT an AI detector)")
    subs=parser.add_subparsers(dest="command",required=True)
    p=subs.add_parser("analyze",help="Detect line families in a local image")
    p.add_argument("image",type=Path)
    p.add_argument("--out",type=Path,default=Path("outputs/analyze"))
    p.add_argument("--method",choices=["lsd","hough"],default="lsd")
    p=subs.add_parser("demo",help="Generate synthetic corridor and VP test")
    p.add_argument("--out",type=Path,default=Path("outputs/demo"))
    p=subs.add_parser("benchmark",help="Known-truth mathematical stress test")
    p.add_argument("--out",type=Path,default=Path("outputs/benchmark"))
    p.add_argument("--trials",type=int,default=100)
    p=subs.add_parser("calibrate", help="G02 from three finite externally-orthogonal vanishing points")
    p.add_argument("--vp", action="append", required=True, metavar="X,Y", help="repeat exactly 3 times")
    p.add_argument("--width", type=int, required=True)
    p.add_argument("--height", type=int, required=True)
    p.add_argument("--out", type=Path, default=Path("outputs/g02_calibration"))
    p=subs.add_parser("calibrate-segments", help="G01-to-G02 from JSON with 3 labeled orthogonal line families")
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--out", type=Path, default=Path("outputs/g01_g02"))
    p=subs.add_parser("benchmark-g02", help="Controlled G01->G02 ground-truth regression")
    p.add_argument("--trials", type=int, default=30)
    p.add_argument("--out", type=Path, default=Path("outputs/g02_benchmark"))
    p=subs.add_parser("validate-g02-real",help="Real-camera reference-K + disjoint Manhattan line-family holdout")
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--out",type=Path,default=Path("outputs/g02_real_validation"))
    p=subs.add_parser("analyze-g03",help="Evaluate pre-labelled equally spaced collinear landmarks")
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--out",type=Path,default=Path("outputs/g03"))
    p.add_argument("--image",type=Path,help="optional source photograph for point overlays")
    p=subs.add_parser("auto-g03",help="Find exploratory repeated intersection candidates directly from photo")
    p.add_argument("image", type=Path)
    p.add_argument("--out",type=Path,default=Path("outputs/g03_auto"))
    p.add_argument("--min-marks",type=int,default=5)
    p.add_argument("--min-support",type=float,default=80.)
    p=subs.add_parser("validate-g04",help="Planar world-image homography with independent holdout points")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--image",type=Path)
    p.add_argument("--out",type=Path,default=Path("outputs/g04"))
    p=subs.add_parser("validate-g02-batch",help="Aggregate independent real-camera validation manifests")
    p.add_argument("--inputs",type=Path,nargs='+',required=True)
    p.add_argument("--out",type=Path,default=Path("outputs/g02_batch"))
    p=subs.add_parser("analyze-g03-regions",help="Analyze independently annotated floor/facade regions")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("outputs/g03_regions"))
    p=subs.add_parser("validate-g04-pair",help="Photo pair planar correspondence holdout (no plane proof)")
    p.add_argument("--image-a",type=Path,required=True)
    p.add_argument("--image-b",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("outputs/g04_pair"))
    p=subs.add_parser("analyze-shadows",help="P2-S01 robust projected light-ray convergence (annotated object-shadow pairs)")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--image",type=Path,help="optional image of exactly the specified dimensions")
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s01"))
    p.add_argument("--angle-threshold",type=float,default=2.5)
    p=subs.add_parser("demo-shadows",help="Generate a physically valid projected 3D shadow fixture")
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s01_demo"))
    p=subs.add_parser("analyze-multilight",help="P2-S02 annotate-based multi-family shadow-ray consensus")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--image",type=Path)
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s02"))
    p.add_argument("--angle-threshold",type=float,default=2.0)
    p.add_argument("--max-models",type=int,default=3)
    p=subs.add_parser("demo-multilight",help="Generate and analyze two known 3D light sources")
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s02_demo"))
    p=subs.add_parser("analyze-light-3d",help="P2-S03 calibrated receiver-plane intersection + 3D light fitting")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--image",type=Path,help="optional same-size image overlay")
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s03"))
    p.add_argument("--point-tolerance",type=float,default=.22,help="3D point-ray tolerance in scene world units")
    p.add_argument("--s02-report",type=Path,help="optional S02 projected-family assignment JSON")
    p=subs.add_parser("demo-light-3d",help="Create known-truth 3D point-source/directional shadow fixtures")
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s03_demo"))
    p=subs.add_parser("analyze-solar",help="P2-S04 compare calibrated ENU solar-shadow direction and optional NOAA ephemeris")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--image",type=Path)
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s04_analysis"))
    p.add_argument("--angle-tolerance",type=float,default=2.)
    p=subs.add_parser("demo-solar",help="P2-S04 controlled known-truth directional Sun fixture")
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s04_demo"))
    p=subs.add_parser("analyze-penumbra",help="P2-S05 fit photometrically linear annotated penumbra edge profiles")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s05_analysis"))
    p.add_argument("--bootstrap",type=int,default=0,help="conditional parametric Monte Carlo replicates (0..250)")
    p=subs.add_parser("sample-penumbra",help="P2-S05 sample supplied transects from verified linear .npy irradiance")
    p.add_argument("--npy",type=Path,required=True)
    p.add_argument("--transects",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s05_sampled_profiles.json"))
    p=subs.add_parser("demo-penumbra",help="P2-S05 controlled uniform extended-source knife-edge fixture")
    p.add_argument("--out",type=Path,default=Path("outputs/p2_s05_demo"))
    p=subs.add_parser("analyze-mirror",help="P3-R01 annotated 3D points and calibrated planar-mirror consistency")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--image",type=Path,help="optional supplied image of exact declared dimensions")
    p.add_argument("--out",type=Path,default=Path("outputs/p3_r01_analysis"))
    p.add_argument("--tolerance-px",type=float,default=3.0)
    p=subs.add_parser("demo-mirror",help="P3-R01 deterministic virtual-point planar-mirror fixture")
    p.add_argument("--out",type=Path,default=Path("outputs/p3_r01_demo"))
    p=subs.add_parser("analyze-refraction",help="P3-R02 calibrated single-plane refraction / parallel glass slab consistency")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--image",type=Path,help="optional synthetic or annotated image")
    p.add_argument("--out",type=Path,default=Path("outputs/p3_r02_analysis"))
    p.add_argument("--tolerance-px",type=float,default=3.)
    p=subs.add_parser("estimate-refraction-index",help="P3-R02 infer single-interface index with explicit train vs holdout IDs")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--out",type=Path,default=Path("outputs/p3_r02_index"))
    p.add_argument("--tolerance-px",type=float,default=3.)
    p=subs.add_parser("demo-refraction",help="P3-R02 deterministic Snell water/slab fixture")
    p.add_argument("--out",type=Path,default=Path("outputs/p3_r02_demo"))
    p.add_argument("--model",choices=["single_interface","parallel_slab"],default="single_interface")
    p=subs.add_parser("analyze-mirror-chain",help="P3-R03 ordered finite mirrors, virtual images and traced 3D ray paths")
    p.add_argument("--input",type=Path,required=True)
    p.add_argument("--image",type=Path,help="optional image of exactly declared dimensions")
    p.add_argument("--out",type=Path,default=Path("outputs/p3_r03_analysis"))
    p.add_argument("--tolerance-px",type=float,default=3.)
    p=subs.add_parser("demo-mirror-chain",help="P3-R03 controlled two-mirror fixture")
    p.add_argument("--out",type=Path,default=Path("outputs/p3_r03_demo"))
    p=subs.add_parser("analyze-lens",help="P4-O01 known-K Brown-Conrady calibration and disjoint optical holdouts")
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o01_analysis'))
    p.add_argument('--image',type=Path)
    p.add_argument('--order',type=int,choices=(4,5),default=5)
    p.add_argument('--holdout-threshold',type=float,default=2.0)
    p=subs.add_parser("demo-lens",help="P4-O01 controlled synthetic curved-line and lens calibration example")
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o01_demo'))
    p.add_argument('--seed',type=int,default=41)
    p=subs.add_parser("analyze-defocus",help="P4-O02 conditional thin-lens defocus CoC comparison with measured PSF")
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o02_analysis'))
    p.add_argument('--tolerance-sigma',type=float,default=3.)
    p.add_argument('--mc-samples',type=int,default=512)
    p=subs.add_parser("demo-defocus",help="P4-O02 deterministic synthetic focus/depth/CoC fixture")
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o02_demo'))
    p.add_argument('--fit-focus',action='store_true',help='estimate focus only from train group')
    p.add_argument('--seed',type=int,default=1402)
    p=subs.add_parser('analyze-optics',help='P4-O03 conditional focal/FoV/perspective cross-checks with independent 3D holdouts')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o03_analysis'))
    p.add_argument('--tolerance-px',type=float,default=2.5)
    p=subs.add_parser('demo-optics',help='P4-O03 controlled 3D camera perspective and sensor metadata fixture')
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o03_demo'))
    p.add_argument('--fit-focal',action='store_true')
    p.add_argument('--seed',type=int,default=1503)
    p=subs.add_parser('analyze-vignetting', help='P4-O04 linear flat-field, cos4 and radial illumination model with independent holdouts')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o04_analysis'))
    p.add_argument('--sigma-threshold',type=float,default=3.5)
    p=subs.add_parser('demo-vignetting',help='P4-O04 known-truth linear flat field and radial calibration')
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o04_demo'))
    p.add_argument('--fit-center',action='store_true',help='fit shifted radial shading center from train group only')
    p.add_argument('--seed',type=int,default=1801)
    p=subs.add_parser('sample-vignetting',help='P4-O04 nonoverlapping ROI sampling from a dark-corrected linear .npy field')
    p.add_argument('--npy',type=Path,required=True)
    p.add_argument('--regions',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p4_o04_roi_manifest.json'))
    p=subs.add_parser('analyze-depth-contact',help='P5-D01 calibrated support-plane, upright-height and independent metric anchor checks')
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--out',type=Path,default=Path('outputs/p5_d01'))
    p.add_argument('--image',type=Path,help='optional photograph with declared width/height for evidence overlay')
    p.add_argument('--pixel-tolerance',type=float,default=3.0)
    p.add_argument('--contact-tolerance',type=float,default=0.03)
    p=subs.add_parser('demo-depth-contact',help='P5-D01 controlled 3D support, floating-anchor, top-height fixture')
    p.add_argument('--out',type=Path,default=Path('outputs/p5_d01_demo'))
    p.add_argument('--seed',type=int,default=2026)
    p=subs.add_parser('analyze-occlusion',help='P5-D02 conditional multi-plane visibility and independent 3D anchor tests')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p5_d02_analysis'))
    p.add_argument('--image',type=Path,help='optional image for evidence overlay; check dimensions')
    p.add_argument('--pixel-tolerance',type=float,default=3.0)
    p.add_argument('--min-depth-gap',type=float,default=0.04)
    p=subs.add_parser('demo-occlusion',help='P5-D02 controlled multi-plane and annotated occlusion fixture')
    p.add_argument('--out',type=Path,default=Path('outputs/p5_d02_demo'))
    p.add_argument('--seed',type=int,default=2502)
    p=subs.add_parser('analyze-static',help='P5-D03 static equilibrium under independently known metric rigid-body mechanics')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p5_d03_analysis'))
    p.add_argument('--cone-sides',type=int,choices=(8,12,16,20,24,32),default=16)
    p=subs.add_parser('demo-static',help='P5-D03 controlled gravity, point contact, friction and tipping examples')
    p.add_argument('--out',type=Path,default=Path('outputs/p5_d03_demo'))
    p.add_argument('--seed',type=int,default=2503)
    p=subs.add_parser('analyze-material',help='P6-M01 Lambertian energy, known-light albedo and independent linear-radiance holdouts')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m01_analysis'))
    p.add_argument('--consistent-sigma',type=float,default=2.5)
    p.add_argument('--inconsistent-sigma',type=float,default=4.5)
    p=subs.add_parser('audit-brdf',help='P6-M01 explicit sampled BRDF reciprocity and numerical energy audit')
    p.add_argument('--input',type=Path,required=True,help='JSON: brdf_values_matrix plus directions/solid_angle_weights')
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m01_brdf_audit.json'))
    p=subs.add_parser('demo-material',help='P6-M01 controlled spectral RGB Lambertian material experiment')
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m01_demo'))
    p.add_argument('--seed',type=int,default=2601)
    p.add_argument('--known-albedo',action='store_true',help='Use independent material albedo instead of fit from train')
    p=subs.add_parser('analyze-microfacet',help='P6-M02 GGX Cook-Torrance calibrated specular radiance holdout consistency')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m02_analysis'))
    p.add_argument('--consistent-sigma',type=float,default=2.5)
    p.add_argument('--inconsistent-sigma',type=float,default=4.5)
    p=subs.add_parser('demo-microfacet',help='P6-M02 controlled known-truth GGX specular surface measurements')
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m02_demo'))
    p.add_argument('--seed',type=int,default=2702)
    p.add_argument('--known-roughness',action='store_true')
    p=subs.add_parser('audit-microfacet-energy',help='P6-M02 numerical directional-hemispherical energy audit for specular GGX')
    p.add_argument('--roughness',type=float,default=.45)
    p.add_argument('--f0',type=float,nargs=3,default=[.04,.04,.04],metavar=('R','G','B'))
    p.add_argument('--n-mu',type=int,default=40)
    p.add_argument('--n-phi',type=int,default=96)
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m02_energy_audit.json'))
    p=subs.add_parser('analyze-combined-material',help='P6-M03 energy-bounded diffuse+GGX material holdout analysis')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m03_analysis'))
    p=subs.add_parser('demo-combined-material',help='P6-M03 synthetic disjoint-surface material example')
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m03_demo'))
    p.add_argument('--seed',type=int,default=2803)
    p.add_argument('--known-material',action='store_true')
    p.add_argument('--proxy',action='store_true',help='Use a separately declared phenomenological diffuse proxy')
    p=subs.add_parser('audit-combined-energy',help='P6-M03 sampled directional BRDF energy audit')
    p.add_argument('--input',type=Path,required=True,help='JSON material parameter object')
    p.add_argument('--out',type=Path,default=Path('outputs/p6_m03_energy_audit.json'))
    p.add_argument('--n-mu',type=int,default=40)
    p.add_argument('--n-phi',type=int,default=96)
    p=subs.add_parser('analyze-sensor-noise',help='P7-S01 conditional RAW Poisson/Gaussian moment holdout test')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p7_s01_analysis'))
    p.add_argument('--consistent-sigma',type=float,default=2.5)
    p.add_argument('--inconsistent-sigma',type=float,default=5.0)
    p=subs.add_parser('demo-sensor-noise',help='P7-S01 controlled synthetic dark/flat sensor photon-transfer experiment')
    p.add_argument('--out',type=Path,default=Path('outputs/p7_s01_demo'))
    p.add_argument('--seed',type=int,default=3101)
    p.add_argument('--fit-parameters',action='store_true',help='Estimate gain/read/dark from training groups only')
    p=subs.add_parser('summarize-raw-stack',help='P7-S01 temporal fixed-pixel RAW .npy stack to moments only; no origin verdict')
    p.add_argument('--npy',type=Path,required=True,help='NumPy array [frames,height,width] of integer RAW ADU codes')
    p.add_argument('--adc-max',type=int,default=16383)
    p.add_argument('--roi',type=int,nargs=4,metavar=('X0','Y0','X1','Y1'))
    p.add_argument('--out',type=Path,default=Path('outputs/p7_s01_temporal_stats.json'))
    p=subs.add_parser('analyze-evidence',help='P8-E01 conditional scalar physical evidence, uncertainty and null testing')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    subs.add_parser('list-evidence-modules',help='P8-E01 registered P1–P7 physical evidence modules')
    p=subs.add_parser('analyze-fusion',help='P8-E02 dependency groups and conservative familywise inference')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    p=subs.add_parser('analyze-sensor-fingerprint',help='P7-S02 RAW PRNU/DSNU reference and independent query correlation')
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,default=Path('outputs/p7_s02_analysis'))
    p=subs.add_parser('demo-sensor-fingerprint',help='P7-S02 independent synthetic same/wrong camera patterns')
    p.add_argument('--out',type=Path,default=Path('outputs/p7_s02_demo'))
    p.add_argument('--seed',type=int,default=4202)
    args=parser.parse_args(argv)
    config=VPConfig()
    if args.command=='analyze-evidence':
        try:
            result=run_evidence_manifest(args.input, args.out)
        except (EvidenceContractError, ValueError, OSError) as exc:
            parser.error(str(exc))
        print(json.dumps({'summary_counts':result['summary_counts'],'output':str(args.out/'p8_e01_evidence_report.json'),'decision':result['decision']},ensure_ascii=False))
        return
    if args.command=='analyze-fusion':
        try:
            report=run_fusion_manifest(args.input,args.out)
        except (EvidenceContractError,ValueError,TypeError,OSError) as exc:
            parser.error(str(exc))
        print(json.dumps({'overall_state':report['overall_state'],
                          'components':report['component_count'],
                          'report':str(args.out/'p8_e02_fusion_report.json'),
                          'decision':report['decision']},ensure_ascii=False))
        return
    if args.command=='list-evidence-modules':
        print(json.dumps(MODULES,ensure_ascii=False,indent=2))
        return
    if args.command=='analyze-sensor-fingerprint':
        try:report=run_fingerprint_manifest(args.input,args.out)
        except (FingerprintError,ValueError,KeyError,OSError,TypeError) as exc:parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'report':str(args.out/'p7_s02_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-sensor-fingerprint':
        try:
            manifest,truth=write_synthetic_fingerprint_fixture(args.out,seed=args.seed)
            report=run_fingerprint_manifest(manifest,args.out,controlled_synthetic_evaluation=True)
            report['controlled_synthetic_ground_truth']=truth
            _write_report(args.out/'p7_s02_report.json',report)
            render_fingerprint_summary(manifest,report,args.out/'p7_s02_maps.png')
        except (FingerprintError,ValueError,KeyError,OSError,TypeError) as exc:parser.error(str(exc))
        print(json.dumps({'counts':report['counts'],'out':str(args.out)},ensure_ascii=False))
        return
    if args.command=='summarize-raw-stack':
        try:
            raw=np.load(args.npy,allow_pickle=False)
            sensor=SensorParameters(adc_max_adu=args.adc_max)
            result=summarize_temporal_raw_stack(raw,sensor,
                tuple(args.roi) if args.roi is not None else None)
            result['origin_verdict']='NOT_EVALUATED'
            result['input_sha256']=hashlib.sha256(args.npy.read_bytes()).hexdigest()
            _write_report(args.out,result)
        except (SensorNoiseError,ValueError,TypeError,OSError) as exc:
            parser.error(str(exc))
        print(json.dumps({'moments_file':str(args.out),'n_samples':result['n_samples'],
                          'origin_verdict':'NOT_EVALUATED'},ensure_ascii=False))
        return
    if args.command=='analyze-sensor-noise':
        try:
            report=run_sensor_manifest(args.input,args.out,SensorNoiseConfig(
                consistent_sigma=args.consistent_sigma,inconsistent_sigma=args.inconsistent_sigma))
        except (SensorNoiseError,OSError,ValueError,KeyError,TypeError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'report':str(args.out/'p7_s01_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-sensor-noise':
        try:
            manifest,truth=synthetic_sensor_fixture(seed=args.seed,
                mode='fit_train_parameters' if args.fit_parameters else 'known_parameters')
            args.out.mkdir(parents=True,exist_ok=True)
            inp=args.out/'p7_s01_fixture.json'
            _write_report(inp,manifest)
            report=run_sensor_manifest(inp,args.out)
            report['controlled_synthetic_ground_truth']=truth
            _write_report(args.out/'p7_s01_report.json',report)
            render_sensor_demo(manifest,report,args.out/'p7_s01_photon_transfer.png')
        except (SensorNoiseError,OSError,ValueError,KeyError,TypeError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'parameters':report['parameters'],'out':str(args.out)},ensure_ascii=False))
        return
    if args.command=='analyze-combined-material':
        try:report=run_combined_manifest(args.input,args.out,CombinedMaterialConfig())
        except (CombinedMaterialError,OSError,ValueError,KeyError,TypeError) as exc:parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'report':str(args.out/'p6_m03_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-combined-material':
        data,truth=synthetic_combined_fixture(seed=args.seed,
            mode='known_material' if args.known_material else 'fit_diffuse_albedo',
            policy='bounded_diffuse_proxy' if args.proxy else 'assumed_negligible')
        args.out.mkdir(parents=True,exist_ok=True)
        _write_report(args.out/'p6_m03_fixture.json',data)
        report=run_combined_manifest(args.out/'p6_m03_fixture.json',args.out)
        report['controlled_synthetic_ground_truth']=truth
        _write_report(args.out/'p6_m03_report.json',report)
        try:render_combined_report(args.out/'p6_m03_holdout.png',report)
        except ImportError:pass
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'out':str(args.out)},ensure_ascii=False))
        return
    if args.command=='audit-combined-energy':
        try:
            data=json.loads(args.input.read_text(encoding='utf-8'))
            material=data['materials']['paint01'] if 'materials' in data and 'paint01' in data['materials'] else data
            result=audit_combined_energy(material,n_mu=args.n_mu,n_phi=args.n_phi)
            _write_report(args.out,result)
        except (CombinedMaterialError,OSError,ValueError,KeyError,TypeError) as exc:parser.error(str(exc))
        print(json.dumps({'state':result['state'],'out':str(args.out)},ensure_ascii=False))
        return
    if args.command=='analyze-microfacet':
        try:
            report=run_microfacet_manifest(args.input,args.out,MicrofacetConfig(
                consistent_sigma=args.consistent_sigma,inconsistent_sigma=args.inconsistent_sigma))
        except (MicrofacetError,OSError,ValueError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'report':str(args.out/'p6_m02_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-microfacet':
        fixture,truth=synthetic_microfacet_fixture(seed=args.seed,
            mode='known_roughness' if args.known_roughness else 'fit_roughness')
        args.out.mkdir(parents=True,exist_ok=True)
        fixture_path=args.out/'p6_m02_fixture.json'
        _write_report(fixture_path,fixture)
        report=run_microfacet_manifest(fixture_path,args.out)
        report['controlled_synthetic_ground_truth']=truth
        _write_report(args.out/'p6_m02_report.json',report)
        try:
            render_microfacet_report(args.out/'p6_m02_holdout.png',report)
        except ImportError:
            report['plot_note']='matplotlib not installed; JSON remains available'
            _write_report(args.out/'p6_m02_report.json',report)
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'roughness':report['fitted_or_known_roughness'],
                          'output':str(args.out)},ensure_ascii=False))
        return
    if args.command=='audit-microfacet-energy':
        try:
            report=audit_ggx_energy(args.roughness,args.f0,n_mu=args.n_mu,n_phi=args.n_phi)
            _write_report(args.out,report)
        except (MicrofacetError,ValueError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'output':str(args.out)},ensure_ascii=False))
        return
    if args.command=='audit-brdf':
        try:
            data=json.loads(args.input.read_text(encoding='utf-8'))
            if data.get('use_builtin_quadrature',False):
                dirs,weights=hemisphere_quadrature(int(data.get('n_mu',6)),int(data.get('n_phi',12)))
            else:
                dirs,weights=data['directions'],data['solid_angle_weights']
            if data.get('brdf_model')=='lambertian':
                rho=float(data['diffuse_albedo'])
                if not np.isfinite(rho) or rho<0 or rho>1:
                    raise MaterialPhysicsError('diffuse_albedo must be [0,1]')
                values=np.full((len(dirs),len(dirs)),rho/np.pi)
            else:
                values=data['brdf_values_matrix']
            result=audit_brdf_matrix(values,dirs,weights)
            args.out.parent.mkdir(parents=True,exist_ok=True)
            _write_report(args.out,result)
        except (MaterialPhysicsError,ValueError,OSError,KeyError,TypeError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':result['state'],'max_energy':result['max_hemispherical_reflectance'],
                          'out':str(args.out)},ensure_ascii=False))
        return
    if args.command=='analyze-material':
        try:
            report=run_material_manifest(args.input,args.out,MaterialConfig(
                consistent_sigma=args.consistent_sigma,inconsistent_sigma=args.inconsistent_sigma))
        except (MaterialPhysicsError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'report':str(args.out/'p6_m01_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-material':
        data,truth=synthetic_material_fixture(seed=args.seed,mode='known_albedo' if args.known_albedo else 'fit_albedo')
        args.out.mkdir(parents=True,exist_ok=True)
        path=args.out/'p6_m01_fixture.json'
        _write_report(path,data)
        report=run_material_manifest(path,args.out)
        report['controlled_synthetic_ground_truth']=truth
        _write_report(args.out/'p6_m01_report.json',report)
        try:
            draw_material_demo(args.out/'p6_m01_radiance_holdout.png',data,report)
        except ImportError:
            report['optional_plot_note']='matplotlib not installed; JSON report remains available'
            _write_report(args.out/'p6_m01_report.json',report)
        got={r['id']:r['state'] for r in report['observations']}
        missed=sum((v=='INCONSISTENT_UNDER_ASSUMPTIONS' and got[k]!=v) for k,v in truth['expected_holdout_states'].items())
        false_alarms=sum((v=='CONSISTENT' and got[k]=='INCONSISTENT_UNDER_ASSUMPTIONS') for k,v in truth['expected_holdout_states'].items())
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'fitted_albedo_rgb':report['fitted_or_known_albedo_rgb'],
                          'synthetic_missed_corruption':missed,'synthetic_false_alarms':false_alarms,
                          'output':str(args.out)},ensure_ascii=False))
        return
    if args.command=='analyze-static':
        try:
            report=run_static_manifest(args.input,args.out,EquilibriumConfig(cone_sides=args.cone_sides))
        except (StaticEquilibriumError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'report':str(args.out/'p5_d03_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-static':
        data,truth=synthetic_equilibrium_fixture(seed=args.seed)
        args.out.mkdir(parents=True,exist_ok=True)
        path=args.out/'p5_d03_fixture.json'
        _write_report(path,data)
        report=run_static_manifest(path,args.out)
        report['controlled_ground_truth']=truth
        _write_report(args.out/'p5_d03_report.json',report)
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'ground_truth_exact_match':{r['id']:r['state'] for r in report['objects']}==truth,
                          'output':str(args.out)},ensure_ascii=False))
        return
    if args.command=='analyze-occlusion':
        try:
            report=run_occlusion_manifest(args.input,args.out,
                         OcclusionConfig(pixel_tolerance=args.pixel_tolerance,
                                         min_depth_gap_world=args.min_depth_gap))
            if args.image is not None:
                supplied=load_bgr(args.image)
                manifest=json.loads(args.input.read_text(encoding='utf-8'))
                if list(supplied.shape[:2])!=manifest['image_shape_hw']:
                    raise OcclusionGeometryError('image size differs from manifest')
                # Overlay calculated ray-intersections on the specified image.
                canvas=render_occlusion_overlay(manifest,report)
                mask=np.any(canvas!=[28,34,40],axis=2)
                supplied[mask]=canvas[mask]
                write_image(args.out/'p5_d02_overlay.png',supplied)
                report['image_sha256']=hashlib.sha256(args.image.read_bytes()).hexdigest()
                report['overlay']='p5_d02_overlay.png'
                _write_report(args.out/'p5_d02_report.json',report)
        except (OcclusionGeometryError,DepthContactError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'report':str(args.out/'p5_d02_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-occlusion':
        manifest,truth=synthetic_occlusion_fixture(seed=args.seed)
        args.out.mkdir(parents=True,exist_ok=True)
        inp=args.out/'p5_d02_fixture.json'
        _write_report(inp,manifest)
        report=run_occlusion_manifest(inp,args.out)
        report['synthetic_ground_truth']=truth
        write_image(args.out/'p5_d02_overlay.png',render_occlusion_overlay(manifest,report))
        _write_report(args.out/'p5_d02_report.json',report)
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'output':str(args.out)},ensure_ascii=False))
        return
    if args.command=='analyze-depth-contact':
        try:
            report=run_depth_contact_manifest(args.input,args.out,DepthContactConfig(pixel_tolerance=args.pixel_tolerance,contact_tolerance_world=args.contact_tolerance))
            if args.image is not None:
                supplied=load_bgr(args.image)
                manifest=json.loads(args.input.read_text(encoding='utf-8'))
                if list(supplied.shape[:2])!=manifest['image_shape_hw']:
                    raise DepthContactError('supplied image dimensions differ from manifest')
                write_image(args.out/'p5_d01_overlay.png',render_depth_contact_overlay(manifest,report,background=supplied))
                report['image_sha256']=hashlib.sha256(args.image.read_bytes()).hexdigest()
                report['overlay']='p5_d01_overlay.png'
                _write_report(args.out/'p5_d01_report.json',report)
        except (DepthContactError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],'report':str(args.out/'p5_d01_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-depth-contact':
        data,truth=synthetic_depth_contact_fixture(seed=args.seed)
        args.out.mkdir(parents=True,exist_ok=True)
        fixture=args.out/'p5_d01_fixture.json'
        _write_report(fixture,data)
        report=run_depth_contact_manifest(fixture,args.out)
        report['synthetic_ground_truth']=truth
        write_image(args.out/'p5_d01_overlay.png',render_depth_contact_overlay(data,report))
        _write_report(args.out/'p5_d01_report.json',report)
        print(json.dumps({'state':report['state'],'counts':report['counts'],'output':str(args.out)},ensure_ascii=False))
        return
    if args.command=='sample-vignetting':
        try:
            result=sample_linear_regions(args.npy,args.regions,args.out)
        except (VignettingError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'sample_count':len(result['samples']),'manifest':str(args.out)}))
        return
    if args.command=='analyze-vignetting':
        try:
            report=run_vignetting_manifest(args.input,args.out,VignettingConfig(sigma_threshold=args.sigma_threshold))
        except (VignettingError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'inconsistent_count':report.get('inconsistent_count'),
                          'report':str(args.out/'p4_o04_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-vignetting':
        mode='fit_radial_and_center' if args.fit_center else 'fit_radial'
        data,truth=synthetic_vignetting_fixture(seed=args.seed,mode=mode)
        args.out.mkdir(parents=True,exist_ok=True)
        fixture=args.out/'p4_o04_fixture.json'
        _write_report(fixture,data)
        report=run_vignetting_manifest(fixture,args.out)
        report['synthetic_ground_truth']=truth
        write_image(args.out/'p4_o04_flatfield_comparison.png',render_vignetting_demo(data,report))
        write_image(args.out/'p4_o04_radial_profile.png',render_vignetting_radial_profile(report))
        report['synthetic_visualization']='p4_o04_flatfield_comparison.png'
        _write_report(args.out/'p4_o04_report.json',report)
        print(json.dumps({'state':report['state'],'inconsistent_count':report.get('inconsistent_count'),
                          'calibration_mode':mode,'out':str(args.out)},ensure_ascii=False))
        return
    if args.command=='analyze-optics':
        try:
            report=run_optical_manifest(args.input,args.out,OpticalConfig(tolerance_px=args.tolerance_px))
        except (OpticalConsistencyError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report.get('counts'),
            'report':str(args.out/'p4_o03_report.json')},ensure_ascii=False))
        return
    if args.command=='demo-optics':
        data,truth=synthetic_optical_fixture(seed=args.seed,fit_focal=args.fit_focal)
        args.out.mkdir(parents=True,exist_ok=True)
        fixture=args.out/'p4_o03_fixture.json'
        _write_report(fixture,data)
        report=run_optical_manifest(fixture,args.out)
        report['synthetic_ground_truth']=truth
        write_image(args.out/'p4_o03_holdout_overlay.png',render_optical_overlay(data,report))
        report['synthetic_holdout_overlay']='p4_o03_holdout_overlay.png'
        _write_report(args.out/'p4_o03_report.json',report)
        print(json.dumps({'state':report['state'],'counts':report['counts'],
            'camera_fovs':report['camera_fovs'], 'out':str(args.out)},ensure_ascii=False))
        return
    if args.command=="analyze-defocus":
        try:
            report=run_defocus_manifest(args.input,args.out,
                tolerance_sigma=args.tolerance_sigma,mc_samples=args.mc_samples)
        except (DefocusError,ValueError,OSError,KeyError) as exc: parser.error(str(exc))
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'report':str(args.out/'p4_o02_report.json')},ensure_ascii=False))
        return
    if args.command=="demo-defocus":
        data,truth=synthetic_defocus_fixture(seed=args.seed,fit_focus=args.fit_focus)
        args.out.mkdir(parents=True,exist_ok=True)
        fixture=args.out/'p4_o02_fixture.json'
        _write_report(fixture,data)
        report=run_defocus_manifest(fixture,args.out)
        from .defocus import ThinLens
        k=data['optics']
        lens=ThinLens(k['focal_mm'],k['f_number'],k['pixel_pitch_um'],truth['focus_distance_mm'])
        write_image(args.out/'p4_o02_depth_comparison.png',render_defocus_comparison(lens))
        report['synthetic_ground_truth']=truth
        _write_report(args.out/'p4_o02_report.json',report)
        print(json.dumps({'state':report['state'],'counts':report['counts'],
                          'focus_distance_mm':report['lens']['focus_distance_mm'],
                          'out':str(args.out)},ensure_ascii=False))
        return
    if args.command=="analyze-lens":
        try:
            if args.holdout_threshold<=0: raise LensGeometryError('positive holdout threshold required')
            result=run_lens_manifest(args.input,args.out,args.image,
                LensConfig(order=args.order,holdout_threshold_px=args.holdout_threshold))
        except (LensGeometryError,ValueError,OSError,KeyError) as exc: parser.error(str(exc))
        print(json.dumps({'state':result['state'],'holdout_rmse_px':result.get('holdout_rmse_px'),
                          'report':str(args.out/'p4_o01_report.json')},ensure_ascii=False))
        return
    if args.command=="demo-lens":
        fixture,frame,truth=synthetic_lens_scene(seed=args.seed)
        args.out.mkdir(parents=True,exist_ok=True)
        json_path=args.out/'p4_o01_fixture.json'
        _write_report(json_path,fixture)
        image_path=args.out/'p4_o01_fixture.png'
        write_image(image_path,frame)
        result=run_lens_manifest(json_path,args.out,image_path)
        result['synthetic_ground_truth']=truth
        _write_report(args.out/'p4_o01_report.json',result)
        print(json.dumps({'state':result['state'],'holdout_rmse_px':result.get('holdout_rmse_px'),
                          'true_coefficients':truth['coefficients'],
                          'fitted_coefficients':result.get('coefficients'),'output':str(args.out)},ensure_ascii=False))
        return
    if args.command=="analyze-mirror-chain":
        try:
            report=run_multi_mirror_manifest(args.input,args.out,args.image,args.tolerance_px)
        except (MirrorChainError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'consistent':report['consistent_count'],
                          'inconsistent':report['inconsistent_count'],
                          'indeterminate':report['indeterminate_count'],
                          'report':str(args.out/'p3_r03_report.json')},ensure_ascii=False))
    elif args.command=="demo-mirror-chain":
        data,image,truth=synthetic_two_mirror_scene(n=20,noise_px=.35,corrupt=3,seed=43)
        args.out.mkdir(parents=True,exist_ok=True)
        fixture=args.out/'p3_r03_fixture.json';frame=args.out/'p3_r03_fixture.png'
        _write_report(fixture,data);write_image(frame,image)
        write_image(args.out/'p3_r03_physical_path_xz.png',render_chain_xz_diagram(data))
        report=run_multi_mirror_manifest(fixture,args.out,frame,tolerance_px=3.)
        report['controlled_synthetic_ground_truth']=truth
        _write_report(args.out/'p3_r03_report.json',report)
        print(json.dumps({'state':report['state'],'known_good':truth['known_good'],
                          'measured_good':report['consistent_count'],
                          'known_corrupted':truth['known_corrupt'],
                          'measured_corrupted':report['inconsistent_count'],
                          'out':str(args.out)},ensure_ascii=False))
    elif args.command=="analyze-refraction":
        try:
            report=run_refraction_manifest(args.input,args.out,args.image,args.tolerance_px)
        except (RefractionGeometryError,MirrorGeometryError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'consistent':report['consistent_count'],
                          'inconsistent':report['inconsistent_count'],
                          'indeterminate':report['indeterminate_count'],
                          'report':str(args.out/'p3_r02_report.json')},ensure_ascii=False))
    elif args.command=="estimate-refraction-index":
        try:
            report=run_index_manifest(args.input,args.out,args.tolerance_px)
        except (RefractionGeometryError,MirrorGeometryError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],'estimated_n_layer':report['estimated_n_layer'],
                          'train_count':report['train_count'],
                          'holdout_count':report['holdout_count'],
                          'report':str(args.out/'p3_r02_index_report.json')},ensure_ascii=False))
    elif args.command=="demo-refraction":
        data,image,truth=synthetic_refraction_scene(model=args.model,n=18,noise_px=.23,corrupt=3,seed=33)
        args.out.mkdir(parents=True,exist_ok=True)
        fixture=args.out/'p3_r02_fixture.json';frame=args.out/'p3_r02_fixture.png'
        _write_report(fixture,data);write_image(frame,image)
        report=run_refraction_manifest(fixture,args.out,frame,tolerance_px=3.)
        report['controlled_synthetic_ground_truth']=truth
        _write_report(args.out/'p3_r02_report.json',report)
        print(json.dumps({'state':report['state'],'known_good':truth['known_good'],
                          'measured_good':report['consistent_count'],
                          'known_corrupted':truth['known_corrupted'],
                          'measured_corrupted':report['inconsistent_count'],
                          'out':str(args.out)},ensure_ascii=False))
    elif args.command=="analyze-mirror":
        try:
            report=run_mirror_manifest(args.input,args.out,args.image,args.tolerance_px)
        except (MirrorGeometryError,ValueError,OSError,KeyError) as e:
            parser.error(str(e))
        print(json.dumps({'state':report['state'],'consistent':report['consistent_count'],
                          'inconsistent':report['inconsistent_count'],
                          'indeterminate':report['indeterminate_count'],
                          'report':str(args.out/'p3_r01_report.json')},ensure_ascii=False))
    elif args.command=="demo-mirror":
        data,image,truth=synthetic_mirror_scene(n=16,noise_px=.3,corrupt=2,seed=29)
        args.out.mkdir(parents=True,exist_ok=True)
        fixture=args.out/'p3_r01_fixture.json';frame=args.out/'p3_r01_fixture.png'
        _write_report(fixture,data);write_image(frame,image)
        report=run_mirror_manifest(fixture,args.out,frame,tolerance_px=3.)
        report['controlled_synthetic_ground_truth']=truth
        _write_report(args.out/'p3_r01_report.json',report)
        print(json.dumps({'state':report['state'],'known_good':truth['known_good'],
                          'measured_good':report['consistent_count'],
                          'known_corrupted':truth['known_corrupted'],
                          'measured_corrupted':report['inconsistent_count'],
                          'out':str(args.out)},ensure_ascii=False))
    elif args.command=="sample-penumbra":
        try:
            report=run_sample_transects(args.npy,args.transects,args.out)
        except (PenumbraError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'count':len(report['edges']),'output':str(args.out)},ensure_ascii=False))
    elif args.command=="analyze-penumbra":
        try:
            report=run_penumbra_manifest(args.input,args.out,
                                         PenumbraConfig(bootstrap_samples=args.bootstrap))
        except (PenumbraError,ValueError,OSError,KeyError) as exc:
            parser.error(str(exc))
        print(json.dumps({'state':report['state'],
                          'angular_diameter_median_deg':report['angular_diameter_median_deg'],
                          'measured_edges':report['profiles_measured'],
                          'output':str(args.out/'p2_s05_report.json')},ensure_ascii=False))
    elif args.command=="demo-penumbra":
        data,truth=synthetic_penumbra_fixture(seed=18,noise_sigma=.006)
        args.out.mkdir(parents=True,exist_ok=True)
        file=args.out/'p2_s05_fixture.json';_write_report(file,data)
        report=run_penumbra_manifest(file,args.out)
        report['synthetic_ground_truth']=truth
        _write_report(args.out/'p2_s05_report.json',report)
        print(json.dumps({'state':report['state'],
                          'truth_angular_diameter_deg':truth['source_angular_diameter_deg'],
                          'estimated_angular_diameter_deg':report['angular_diameter_median_deg'],
                          'output':str(args.out)},ensure_ascii=False))
    elif args.command=="analyze-solar":
        try:
            report=run_solar_manifest(args.input,args.out,args.image,SolarConfig(
                direction_tolerance_deg=args.angle_tolerance))
        except (SolarGeometryError,ValueError,OSError,KeyError) as e:parser.error(str(e))
        print(json.dumps({"state":report["state"],"azimuth_deg":report["measured_sun_azimuth_deg"],
                         "elevation_deg":report["measured_sun_elevation_deg"],
                         "ephemeris":report["ephemeris_comparison"]["state"],
                         "output":str(args.out/"p2_s04_report.json")},ensure_ascii=False))
    elif args.command=="demo-solar":
        d,img,truth=synthetic_solar_scene(n=20,noise_px=.15,wrong_pairs=3)
        args.out.mkdir(parents=True,exist_ok=True)
        _write_report(args.out/"p2_s04_fixture.json",d)
        image=args.out/"p2_s04_fixture.png";write_image(image,img)
        report=run_solar_manifest(args.out/"p2_s04_fixture.json",args.out,image)
        report["known_synthetic_truth"]=truth
        _write_report(args.out/"p2_s04_report.json",report)
        print(json.dumps({"state":report["state"],"estimated_azimuth_deg":report["measured_sun_azimuth_deg"],
                          "estimated_elevation_deg":report["measured_sun_elevation_deg"],
                          "output":str(args.out)},ensure_ascii=False))
    elif args.command=="analyze-light-3d":
        try:
            report=run_shadow3d_manifest(args.input,args.out,args.image,
                Shadow3DConfig(point_tolerance_world=args.point_tolerance),args.s02_report)
        except (Shadow3DError,ValueError,OSError,KeyError) as e:parser.error(str(e))
        print(json.dumps({'state':report['state'],'groups':report['group_count'],
                          'models':[x['model_class'] for x in report['model_groups']],
                          'output':str(args.out/'p2_s03_report.json')},ensure_ascii=False))
    elif args.command=="demo-light-3d":
        args.out.mkdir(parents=True,exist_ok=True)
        data,frame,truth=synthetic_shadow3d_scene(n=16,noise_px=.2,bad_pairs=2)
        manifest=args.out/'p2_s03_fixture.json'
        _write_report(manifest,data)
        image=args.out/'p2_s03_fixture.png'
        write_image(image,frame)
        report=run_shadow3d_manifest(manifest,args.out,image)
        report['known_synthetic_truth']=truth
        _write_report(args.out/'p2_s03_report.json',report)
        print(json.dumps({'state':report['state'],'known_truth':truth,
                          'output':str(args.out)},ensure_ascii=False))
    elif args.command=="analyze-multilight":
        try:
            report=run_multilight_manifest(args.input,args.out,args.image,
                MultiLightConfig(angle_threshold_deg=args.angle_threshold,max_models=args.max_models))
        except (ShadowEvidenceError, ValueError, OSError, KeyError) as e:
            parser.error(str(e))
        print(json.dumps({'state':report['state'],'model_count':len(report['models']),
                          'unassigned_count':len(report['unassigned_ids']),
                          'output':str(args.out/'p2_s02_report.json')},ensure_ascii=False))
    elif args.command=="demo-multilight":
        args.out.mkdir(parents=True,exist_ok=True)
        data,frame,truth=synthetic_multilight_scene()
        manifest=args.out/'p2_s02_fixture.json'
        _write_report(manifest,data)
        image=args.out/'p2_s02_fixture.png'
        write_image(image,frame)
        report=run_multilight_manifest(manifest,args.out,image)
        report['known_synthetic_truth']=truth
        _write_report(args.out/'p2_s02_report.json',report)
        print(json.dumps({'state':report['state'],
                          'estimated_projected_families':len(report['models']),
                          'known_fixture_sources':len(truth['groups']),
                          'output':str(args.out)},ensure_ascii=False))
    if args.command=="analyze-shadows":
        try:
            report=run_shadow_manifest(args.input,args.out,args.image,
                                       ShadowConfig(angle_threshold_deg=args.angle_threshold))
        except (ShadowEvidenceError,ValueError,OSError,KeyError) as e:parser.error(str(e))
        print(json.dumps({'state':report['state'],'model':report.get('model_class'),
                          'inlier_count':report.get('inlier_count'),
                          'output':str(args.out/'p2_s01_report.json')},ensure_ascii=False))
    elif args.command=="demo-shadows":
        args.out.mkdir(parents=True,exist_ok=True)
        data,frame,truth=synthetic_shadow_scene()
        manifest=args.out/'p2_s01_synthetic_manifest.json'
        _write_report(manifest,data)
        image=args.out/'p2_s01_synthetic_scene.png'
        write_image(image,frame)
        report=run_shadow_manifest(manifest,args.out,image)
        report['controlled_true_projected_light_xy_px']=truth
        report['controlled_point_error_px']=(float(np.linalg.norm(
            np.asarray(report['projected_convergence_xy_px'])-np.asarray(truth)))
            if report.get('projected_convergence_xy_px') is not None else None)
        _write_report(args.out/'p2_s01_report.json',report)
        print(json.dumps({'state':report['state'],'inliers':report.get('inlier_count'),
                          'known_truth_error_px':report['controlled_point_error_px'],
                          'output':str(args.out)},ensure_ascii=False))
    elif args.command=="analyze-g03-regions":
        try: result=run_region_manifest(args.input,args.out)
        except (ValueError,OSError,KeyError) as e: parser.error(str(e))
        print(json.dumps({"state":result["state"],"regions":result["region_count"],"output":str(args.out)},ensure_ascii=False))
    elif args.command=="validate-g04-pair":
        try: result=run_photo_pair(args.image_a,args.image_b,args.out)
        except (ValueError,OSError) as e: parser.error(str(e))
        print(json.dumps({"state":result["status"],"holdout":result.get("calibration_report",{}).get("holdout_reprojection_rmse_px"),"output":str(args.out)},ensure_ascii=False))
    elif args.command=="auto-g03":
        try: result=analyze_auto_pattern_file(args.image,args.out,PatternConfig(
            min_marks=args.min_marks,min_support_length_px=args.min_support))
        except (ValueError,FileNotFoundError) as e: parser.error(str(e))
        print(json.dumps({'state':result['status'],'candidate_count':result['candidate_count'],
                          'output':str(args.out/'g03_auto_report.json')},ensure_ascii=False))
    elif args.command=="validate-g04":
        try: result=analyze_g04_manifest(args.input,args.out,args.image)
        except (ValueError,KeyError,OSError) as e: parser.error(str(e))
        print(json.dumps({'state':result['state'], 'holdout_rmse_px':result.get('holdout_reprojection_rmse_px'),
                          'output':str(args.out/'g04_homography_report.json')},ensure_ascii=False))
    elif args.command=="validate-g02-batch":
        r=batch_real_validation(args.inputs,args.out)
        print(json.dumps({'state':r['state'],'measured':r['measured_declared_camera_cases'],
                          'output':str(args.out/'g02_batch_real_validation.json')},ensure_ascii=False))
    elif args.command=="analyze":
        result=analyze(args.image,args.out,args.method,config)
        print(json.dumps({"state":result["state"],"detected_segments":result["detected_segments"],
                          "vp_models":len(result["vp_models"]),"output":str(args.out)},ensure_ascii=False))
    elif args.command=="demo":
        result=demo(args.out,config)
        print(json.dumps({"corridor_vp":result["corridor_primary_fitted_vp_xy"],
                          "ground_truth":result["synthetic_corridor_vp_ground_truth_xy"],
                          "output":str(args.out)},ensure_ascii=False))
    elif args.command=="calibrate":
        if len(args.vp) != 3: parser.error("--vp must be supplied exactly three times")
        try:
            coords = [list(map(float, item.split(','))) for item in args.vp]
        except ValueError: parser.error("--vp must be in X,Y numeric format")
        if any(len(v) != 2 for v in coords): parser.error("--vp must contain exactly X,Y")
        result=run_calibration_from_points(coords,(args.height,args.width),args.out)
        print(json.dumps({'state':result['state'], 'reason':result.get('reason'),
                          'output':str(args.out/'g02_calibration.json')},ensure_ascii=False))
    elif args.command=="calibrate-segments":
        try:
            result=run_calibration_from_segments(args.input,args.out,config)
        except (ValueError, KeyError, json.JSONDecodeError) as e: parser.error(str(e))
        print(json.dumps({'state':result['state'], 'reason':result.get('reason'),
                          'output':str(args.out/'g01_g02_report.json')},ensure_ascii=False))
    elif args.command=="validate-g02-real":
        try:
            result=run_real_manifest(args.input,args.out)
        except (RealValidationError,ValueError) as e: parser.error(str(e))
        print(json.dumps({'state':result['state'],'reason':result.get('reason'),
                          'output':str(args.out/'g02_real_independent_validation.json')},ensure_ascii=False))
    elif args.command=="analyze-g03":
        try:
            data=json.loads(args.input.read_text(encoding="utf-8"))
            result=analyze_repeated_landmarks(data['points_xy'],data.get('lattice_indices'),
                data.get('training_indices'),data.get('pixel_sigma',.5),
                data.get('bootstrap_samples',400),data.get('seed',2026))
        except (ValueError,KeyError,ProjectiveEvidenceError) as e: parser.error(str(e))
        if args.image is not None:
            img=load_bgr(args.image)
            pts=np.asarray(data['points_xy'],dtype=float)
            if np.any(pts[:,0]<0) or np.any(pts[:,0]>=img.shape[1]) or np.any(pts[:,1]<0) or np.any(pts[:,1]>=img.shape[0]):
                parser.error('annotated points must lie inside image bounds')
            result['image_sha256']=hashlib.sha256(args.image.read_bytes()).hexdigest()
            result['image_dimensions_hw']=list(img.shape[:2])
            for i,(x,y) in enumerate(pts):
                loc=(int(round(x)),int(round(y)))
                cv2.circle(img,loc,5,(25,220,255),-1,cv2.LINE_AA)
                cv2.putText(img,f'P{i}',(loc[0]+8,loc[1]-8),cv2.FONT_HERSHEY_SIMPLEX,.48,(20,250,255),1,cv2.LINE_AA)
            write_image(args.out/'g03_landmarks_overlay.png',img)
            result['overlay_file']='g03_landmarks_overlay.png'
        _write_report(args.out/'g03_projective_report.json',result)
        print(json.dumps({'state':result['state'],'cross_ratio_error':result['cross_ratio_abs_error'],
                          'holdout':result['holdout'],'output':str(args.out/'g03_projective_report.json')},ensure_ascii=False))
    elif args.command=="benchmark-g02":
        if args.trials < 1: parser.error("--trials must be at least 1")
        print(json.dumps(benchmark_g02(args.out,args.trials,config),indent=2,ensure_ascii=False))
    elif args.command=="benchmark":
        if args.trials < 1: parser.error("--trials must be at least 1")
        print(json.dumps(benchmark(args.out,args.trials,config),indent=2,ensure_ascii=False))

if __name__=="__main__":
    main()
