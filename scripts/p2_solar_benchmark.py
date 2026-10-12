"""P2-S04 reproducible controlled-noise physical-geometry stress benchmark."""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import numpy as np
from aiforensics.solar_synthetic import synthetic_solar_scene
from aiforensics.solar_geometry import analyze_solar_geometry, sun_direction_from_angles


def benchmark(trials:int=80):
    if trials<1:raise ValueError('trials >= 1 required')
    errors=[];az_errors=[];el_errors=[];fail=[];inliers=[]
    for seed in range(trials):
        # Fixed Sun and camera, variable shapes, surface slopes, Gaussian pixel noise,
        # independently corrupted object-shadow pairings. Controlled fixture ONLY.
        a=120.0+float(seed%9)*2.0;e=38.0+float(seed%7)*2.0
        try:
            d,_,truth=synthetic_solar_scene(n=24,seed=1000+seed,
                azimuth_deg=a,elevation_deg=e,noise_px=.20,wrong_pairs=3,
                slope_x=(seed%5-2)*.025,slope_y=(seed%3-1)*.022)
            r=analyze_solar_geometry(d)
            if r['state']!='MEASURED':
                fail.append({'seed':seed,'reason':r['reason']});continue
            fitted=np.array(r['direction_fit']['direction_enu'])
            actual=sun_direction_from_angles(a,e)
            errors.append(float(np.rad2deg(np.arccos(np.clip(np.dot(fitted,actual),-1,1)))))
            az_errors.append(float(abs((r['measured_sun_azimuth_deg']-a+180)%360-180)))
            el_errors.append(float(abs(r['measured_sun_elevation_deg']-e)))
            inliers.append(r['direction_fit']['inlier_count'])
        except (ValueError,RuntimeError) as exc:
            fail.append({'seed':seed,'reason':str(exc)})
    return {'module':'P2_S04','scenario':'controlled ENU 3D pinhole camera, tilted planar receiver, fixed Sun per trial, 0.20px noise and 3 wrong matches/24',
            'trials':trials,'successful_trials':len(errors),'failures':fail,
            'angular_error_median_deg_successes':float(np.median(errors)) if errors else None,
            'angular_error_p90_deg_successes':float(np.percentile(errors,90)) if errors else None,
            'azimuth_absolute_error_median_deg_successes':float(np.median(az_errors)) if errors else None,
            'elevation_absolute_error_median_deg_successes':float(np.median(el_errors)) if errors else None,
            'inlier_count_median':float(np.median(inliers)) if inliers else None,
            'not_measured':['real photo solar-direction accuracy','ephemeris error versus reference SPA','photo manipulation or AI detection','real-world false positives'],
            'decision':'NO_AI_ORIGIN_CONCLUSION'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--trials',type=int,default=80)
    parser.add_argument('--out',type=Path,default=Path('outputs/p2_s04_benchmark.json'))
    args=parser.parse_args();res=benchmark(args.trials)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(res,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in res.items() if k!='failures'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
