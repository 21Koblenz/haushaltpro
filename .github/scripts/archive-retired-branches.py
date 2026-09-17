"""Archive only the reviewed branch heads, with atomic, lease-protected removal."""
import json
from pathlib import Path
import re
import subprocess
import sys


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def archive_branch(branch, expected, tag):
    if branch in {'main', 'dev', 'HEAD'} or not re.fullmatch(r'[0-9a-f]{40}', expected):
        raise ValueError('Invalid cleanup branch or commit')
    git('check-ref-format', 'refs/heads/' + branch)
    git('check-ref-format', 'refs/tags/' + tag)
    if not tag.startswith('archive/'):
        raise ValueError('Cleanup tags must be in the archive namespace')
    refs = dict(line.split()[::-1] for line in git('ls-remote', 'origin', 'refs/heads/' + branch, 'refs/tags/' + tag).splitlines())
    current, archived = refs.get('refs/heads/' + branch), refs.get('refs/tags/' + tag)
    if current is None:
        if archived != expected:
            raise RuntimeError('Missing branch without the expected archive: ' + branch)
        print('Already archived:', branch)
        return
    if current != expected or (archived is not None and archived != expected):
        raise RuntimeError('Branch or archive changed; refusing cleanup: ' + branch)
    git('push', '--atomic', '--force-with-lease=refs/heads/' + branch + ':' + expected,
        'origin', expected + ':refs/tags/' + tag, ':refs/heads/' + branch)
    print('Archived and removed:', branch, '->', tag)


def main():
    plan = json.loads(Path(sys.argv[1]).read_text())
    release = sys.argv[2]
    if git('rev-parse', 'HEAD') != release:
        raise RuntimeError('Cleanup must run on the released commit')
    for entry in plan['branches']:
        branch = entry['name']
        opened = subprocess.check_output(['gh', 'pr', 'list', '--state', 'open', '--head', branch,
                                         '--json', 'number', '--jq', 'length'], text=True).strip()
        if opened != '0':
            print('Keeping branch with an open pull request:', branch)
            continue
        archive_branch(branch, entry['sha'], 'archive/' + plan['release'] + '/' + branch)


if __name__ == '__main__':
    main()
