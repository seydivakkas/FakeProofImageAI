"""Known-truth 3D two/three-light projected-shadow fixtures for P2-S02."""
from __future__ import annotations

import numpy as np
import cv2
from .shadow_synthetic import synthetic_shadow_scene


def synthetic_multilight_scene(per_light: int = 10, *, seed: int = 32,
                               noise_px: float = .25, bad_pairs: int = 3,
                               light_sources: list | None = None,
                               shape=(720, 1280)):
    """Independent point-light 3D fixtures, with known disjoint membership.

    Wrong matches are moved cross-track by design, NOT modelled as physical shadows.
    """
    if per_light < 5 or bad_pairs < 0:
        raise ValueError('at least five per source, nonnegative bad_pairs')
    if light_sources is None:
        light_sources = [[-2.2, 3., 7.5], [4.5, 2.5, 6.2]]
    if not (1 <= len(light_sources) <= 3):
        raise ValueError('1–3 sources supported in controlled fixture')
    rng = np.random.default_rng(seed + 300)
    all_pairs = []
    truth = {}
    groups = {}
    frame = np.full((*shape, 3), (28, 37, 48), dtype=np.uint8)
    palette = [(45, 188, 85), (200, 154, 40), (172, 85, 195)]
    for k, src in enumerate(light_sources):
        data, _, pos = synthetic_shadow_scene(n=per_light, seed=seed + k * 11,
                           noise_px=noise_px, shape=shape, light_source_world=src)
        label = f'fixture_{k+1:02d}'
        truth[label] = pos
        groups[label] = []
        for old in data['correspondences']:
            item = dict(old)
            item['id'] = f'{label}_{old["id"]}'
            all_pairs.append(item)
            groups[label].append(item['id'])
            a, b = [tuple(np.rint(item[name]).astype(int)) for name in ('object_xy', 'shadow_xy')]
            cv2.line(frame, a, b, palette[k], 1, cv2.LINE_AA)
            cv2.circle(frame, a, 4, (245, 235, 180), -1)
            cv2.circle(frame, b, 4, palette[k], -1)
    for i in range(bad_pairs):
        a = np.array([rng.uniform(180, 1000), rng.uniform(190, 370)])
        b = a + np.array([rng.choice([-1., 1.]) * rng.uniform(75, 140), rng.uniform(70, 180)])
        if not (0 < b[0] < shape[1] and 0 < b[1] < shape[0]):
            raise ValueError('wrong-match fixture left canvas')
        all_pairs.append({'id': f'wrong_{i:02d}', 'object_xy': a.tolist(), 'shadow_xy': b.tolist()})
        cv2.line(frame, tuple(np.rint(a).astype(int)), tuple(np.rint(b).astype(int)), (58, 65, 230), 2)
    rng.shuffle(all_pairs)
    return {'image_shape_hw': list(shape), 'correspondences': all_pairs}, frame, {'points_px': truth, 'groups': groups}
