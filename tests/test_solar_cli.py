"""External CLI smoke tests for P2-S04, including report I/O contract."""
import json
import os
import subprocess
import sys
from pathlib import Path


def test_demo_and_analyze_cli(tmp_path):
    env=os.environ.copy()
    source=Path(__file__).resolve().parents[1]/'src'
    env['PYTHONPATH']=str(source)+os.pathsep+env.get('PYTHONPATH','')
    demo=tmp_path/'demo'
    proc=subprocess.run([sys.executable,'-m','aiforensics','demo-solar','--out',str(demo)],
                        env=env,capture_output=True,text=True,timeout=35)
    assert proc.returncode==0,proc.stderr
    r=json.loads((demo/'p2_s04_report.json').read_text())
    assert r['state']=='MEASURED'
    assert r['known_synthetic_truth']['corrupted']==3
    out=tmp_path/'analysis'
    proc=subprocess.run([sys.executable,'-m','aiforensics','analyze-solar',
                         '--input',str(demo/'p2_s04_fixture.json'),
                         '--image',str(demo/'p2_s04_fixture.png'),
                         '--out',str(out)],env=env,capture_output=True,text=True,timeout=35)
    assert proc.returncode==0,proc.stderr
    rr=json.loads((out/'p2_s04_report.json').read_text())
    assert rr['state']=='MEASURED'
    assert rr['decision']=='NO_AI_ORIGIN_CONCLUSION'
    assert (out/'p2_s04_overlay.png').exists()


def test_malformed_manifest_does_not_silently_succeed(tmp_path):
    env=os.environ.copy()
    source=Path(__file__).resolve().parents[1]/'src'
    env['PYTHONPATH']=str(source)+os.pathsep+env.get('PYTHONPATH','')
    bad=tmp_path/'bad.json';bad.write_text('{}')
    p=subprocess.run([sys.executable,'-m','aiforensics','analyze-solar',
                      '--input',str(bad),'--out',str(tmp_path/'badout')],
                      env=env,capture_output=True,text=True,timeout=35)
    assert p.returncode!=0
    assert 'world_frame' in p.stderr
    assert not (tmp_path/'badout/p2_s04_report.json').exists()
