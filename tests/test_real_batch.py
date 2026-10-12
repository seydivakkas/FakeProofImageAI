import json
from aiforensics.real_validation import batch_real_validation


def test_no_real_data_not_measured(tmp_path):
    p=tmp_path/'absent_case.json'
    p.write_text(json.dumps({'image':'missing.jpg','capture_type':'real_camera'}))
    x=batch_real_validation([p],tmp_path/'out')
    assert x['state']=='NOT_MEASURED'
    assert x['measured_declared_camera_cases']==0
    assert x['results'][0]['result']['state']=='INDETERMINATE'
