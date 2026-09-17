"""Publishing dev code must never move stable tags; stable dispatch still works."""
import os
from pathlib import Path
import subprocess
import tempfile
import yaml
root=Path(__file__).resolve().parents[1]
workflow=yaml.safe_load((root/'.github/workflows/docker-publish.yml').read_text())
steps=workflow['jobs']['docker']['steps']
script=next(s['run'] for s in steps if s.get('id')=='target')
cases=[
    ('push','refs/heads/main','main','','0.21.9','dev'),
    ('push','refs/heads/dev','dev','','0.21.9-dev.6','dev'),
    ('push','refs/heads/dev','dev','','0.21.9','dev'),
    ('push','refs/tags/v0.21.9-dev.6','v0.21.9-dev.6','','0.21.9-dev.6','dev'),
    ('push','refs/tags/v0.21.9','v0.21.9','','0.21.9','latest'),
    ('workflow_dispatch','refs/heads/main','main','0.21.9','0.21.9','latest'),
    ('workflow_dispatch','refs/heads/dev','dev','0.21.9','0.21.9','latest'),
    ('workflow_dispatch','refs/heads/main','main','0.21.9-dev.6','0.21.9','dev'),
    # Reusable workflows retain the caller's push event and main ref.
    ('push','refs/heads/main','main','0.21.9','0.21.9','latest'),
    ('push','refs/heads/main','main','0.21.10-dev.1','0.21.10-dev.1','dev'),
]
for event,ref,name,version,app_version,expected in cases:
    with tempfile.NamedTemporaryFile() as out, tempfile.TemporaryDirectory() as tmp:
        app=Path(tmp)/'app';app.mkdir();(app/'main.py').write_text('APP_VERSION = '+repr(app_version))
        env={**os.environ,'GITHUB_EVENT_NAME':event,'GITHUB_REF':ref,'GITHUB_REF_NAME':name,'REQUESTED_VERSION':version,'GITHUB_OUTPUT':out.name}
        result=subprocess.run(['bash','-e','-c',script],env=env,cwd=tmp,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        outputs=dict(line.split('=',1) for line in Path(out.name).read_text().splitlines())
        assert outputs['image']=='21koblenz/haushaltpro:'+expected,(event,ref,outputs)
        assert outputs['dev']==('true' if expected=='dev' else 'false')
        if version:assert outputs['version']==version
        elif ref=='refs/heads/dev':assert outputs['version']==app_version
metadata=next(s['with'] for s in steps if s.get('id')=='meta')
assert metadata['flavor']=='latest=false'
for line in metadata['tags'].splitlines():
    if 'value=latest' in line or 'pattern={{major}}.{{minor}}' in line:
        assert "steps.target.outputs.dev == 'false'" in line,line
    if 'type=raw,value=${{ steps.target.outputs.version }}' in line:
        assert "contains(steps.target.outputs.version, '-dev.')" in line,line
assert "contains(needs.docker.outputs.version, '-dev.')" in workflow['jobs']['dev-release']['if']
stable=yaml.safe_load((root/'.github/workflows/stable-release.yml').read_text())['jobs']
assert stable['publish-image']['needs']=='prepare'
assert set(stable['release']['needs'])=={'prepare','publish-image'}
assert set(stable['cleanup']['needs'])=={'prepare','release'}
print('dev/stable publishing: 10 channel cases, stable tag isolation and gated release order: PASS')
