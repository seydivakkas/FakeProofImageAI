"""P7-S02 controlled failure-policy checks; never a real-camera specificity test."""
from __future__ import annotations
import argparse,copy,json
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from aiforensics.sensor_fingerprint import analyze_fingerprint_manifest,FingerprintError
from aiforensics.sensor_fingerprint_synthetic import write_synthetic_fingerprint_fixture,sensor_pattern,synthetic_raw_stacks


def run(seed:int=5151):
    outcomes={}
    with TemporaryDirectory(prefix='p7s02_negative_') as td:
        root=Path(td)
        _,_=write_synthetic_fingerprint_fixture(root,seed=seed)
        baseline=json.loads((root/'p7_s02_fixture.json').read_text())
        def safe_case(label,mutate):
            data=copy.deepcopy(baseline)
            try:
                mutate(data)
                r=analyze_fingerprint_manifest(data,base_dir=root)
                outcomes[label]={'state':r['state'],'query_states':[q['state'] for q in r['queries']]}
            except (FingerprintError,ValueError,KeyError,OSError) as ex:
                outcomes[label]={'state':'REJECTED_INPUT','reason':str(ex)}
        safe_case('unverified_capture_provenance',lambda m:m.update(provenance='unverified'))
        safe_case('jpeg_input',lambda m:m.update(input_domain='jpeg_encoded'))
        safe_case('nonuniform_flat_unverified',lambda m:m.update(uniform_flat_field=False))
        safe_case('temperature_mismatch',lambda m:m.update(matched_temperature=False))
        safe_case('no_alignment',lambda m:m.update(spatial_alignment_verified=False))
        safe_case('reference_frame_leakage',lambda m:m['queries'][0].update(npz='reference.npz'))
        with np.load(root/'same_sensor.npz') as z:
            dark=z['dark'].copy();flat=z['flat'].copy()
        flat[:]=16383
        np.savez_compressed(root/'clipped.npz',dark=dark,flat=flat)
        safe_case('saturation',lambda m:m['queries'][0].update(npz='clipped.npz'))
        d,f=synthetic_raw_stacks(sensor_pattern(seed,(40,40)),seed=seed+20)
        np.savez_compressed(root/'wrong_grid.npz',dark=d,flat=f)
        safe_case('unaligned_grid_shape',lambda m:m['queries'][0].update(npz='wrong_grid.npz'))
    return {'module':'P7_S02_FAILURE_MODE_CONTROLS','seed':seed,'outcomes':outcomes,
            'note':'controlled demonstrations only; NOT empirical real-camera false-match statistics'}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('outputs/p7_s02_negative_controls.json'))
    p.add_argument('--seed',type=int,default=5151)
    a=p.parse_args();v=run(a.seed);a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(v,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(v['outcomes'],ensure_ascii=False))
