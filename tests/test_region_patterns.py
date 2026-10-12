import numpy as np
import cv2
import pytest
from aiforensics.region_patterns import PlaneRegion,validated_mask,analyze_regions


def patterned_image():
    im=np.zeros((360,640,3),dtype=np.uint8)
    for y in (100,145,190,235):
        for x in (110,190,270,350,430):
            cv2.rectangle(im,(x,y),(x+46,y+32),(220,220,220),3)
            cv2.line(im,(x+9,y+6),(x+35,y+22),(170,170,170),2)
    return im


def test_independent_floor_facade_annotation_regions():
    im=patterned_image()
    roof=PlaneRegion('upper',((80,70),(530,70),(530,179),(80,179)),'facade','human_verified')
    ground=PlaneRegion('lower',((80,180),(530,180),(530,300),(80,300)),'floor','human_verified')
    result=analyze_regions(im,[roof,ground])
    assert [r['plane_label'] for r in result['regions']]==['facade','floor']
    assert result['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert sum(r['rectangular_candidates'] for r in result['regions'])>2
    assert all(r['physical_spacing_evidence']=='NOT_MEASURED' for r in result['regions'])


def test_claimed_label_without_verification_is_unknown():
    im=patterned_image()
    x=PlaneRegion('guessed',((50,50),(570,50),(570,315),(50,315)),'facade','unverified_candidate')
    r=analyze_regions(im,[x])['regions'][0]
    assert r['plane_label']=='unknown'
    assert r['label_state']=='UNVERIFIED'


def test_mask_rejects_bad_polygon():
    with pytest.raises(ValueError,match='Self-crossing|too small'):
        validated_mask((360,640),PlaneRegion('x',((40,40),(540,330),(40,330),(540,40)),'floor'))
    with pytest.raises(ValueError,match='bounds'):
        validated_mask((360,640),PlaneRegion('x',((0,0),(800,0),(800,40),(0,40)),'facade'))


def test_empty_image_has_no_pattern_corroboration():
    x=np.full((250,400,3),127,dtype=np.uint8)
    r=analyze_regions(x,[PlaneRegion('f',((5,5),(390,5),(390,240),(5,240)),'floor','human_verified')])
    assert not r['regions'][0]['appearance_repeat_groups']
    assert not r['regions'][0]['line_intersection_candidates']
