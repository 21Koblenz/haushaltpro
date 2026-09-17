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
    ('push','refs/heads/main','main','','dev'),
    ('push','refs/heads/dev','dev','','dev'),
    ('push','refs/tags/v0.21.9-dev.4','v0.21.9-dev.4','','dev'),
    ('push','refs/tags/v0.21.8','v0.21.8','','latest'),
    ('workflow_dispatch','refs/heads/main','main','0.21.8','latest'),
    ('workflow_dispatch','refs/heads/dev','dev','0.21.8','latest'),
    ('workflow_dispatch','refs/heads/main','main','0.21.9-dev.4','dev'),
]
for event,ref,name,version,expected in cases:
    with tempfile.NamedTemporaryFile() as out:
        env={**os.environ,'GITHUB_EVENT_NAME':event,'GITHUB_REF':ref,'GITHUB_REF_NAME':name,'REQUESTED_VERSION':version,'GITHUB_OUTPUT':out.name}
        result=subprocess.run(['bash','-e','-c',script],env=env,cwd=root,capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        outputs=dict(line.split('=',1) for line in Path(out.name).read_text().splitlines())
        assert outputs['image']=='21koblenz/haushaltpro:'+expected,(event,ref,outputs)
        assert outputs['dev']==('true' if expected=='dev' else 'false')
metadata=next(s['with'] for s in steps if s.get('id')=='meta')
assert metadata['flavor']=='latest=false'
for line in metadata['tags'].splitlines():
    if 'value=latest' in line or 'pattern={{major}}.{{minor}}' in line:
        assert "steps.target.outputs.dev == 'false'" in line,line
print('dev/stable publishing: 7 channel cases + stable tag isolation: PASS')
