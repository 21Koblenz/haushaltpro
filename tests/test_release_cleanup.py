"""Use real local Git repositories to check archiving and guarded branch removal."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cleanup', root / '.github/scripts/archive-retired-branches.py')
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


with tempfile.TemporaryDirectory() as tmp:
    remote = Path(tmp) / 'remote.git'
    work = Path(tmp) / 'work'
    subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
    subprocess.run(['git', 'init', '-q', '-b', 'main', str(work)], check=True)
    previous = Path.cwd()
    os.chdir(work)
    try:
        git = cleanup.git
        git('config', 'user.name', 'Release test')
        git('config', 'user.email', 'release@example.test')
        (work / 'sample').write_text('original\n')
        git('add', 'sample'); git('commit', '-qm', 'initial')
        original = git('rev-parse', 'HEAD')
        git('remote', 'add', 'origin', str(remote))
        git('push', '-q', 'origin', 'main', 'HEAD:refs/heads/fix/retired', 'HEAD:refs/heads/fix/new-work', 'HEAD:refs/heads/fix/conflict')
        cleanup.archive_branch('fix/retired', original, 'archive/test/fix/retired')
        assert not git('ls-remote', 'origin', 'refs/heads/fix/retired')
        assert git('ls-remote', 'origin', 'refs/tags/archive/test/fix/retired').split()[0] == original
        cleanup.archive_branch('fix/retired', original, 'archive/test/fix/retired')
        (work / 'sample').write_text('new work\n')
        git('commit', '-qam', 'unrelated new work')
        newer = git('rev-parse', 'HEAD')
        git('push', '-q', 'origin', 'HEAD:refs/heads/fix/new-work', 'HEAD:refs/tags/archive/test/fix/conflict')
        for branch, tag in [('main', 'archive/test/main'), ('dev', 'archive/test/dev'),
                            ('fix/new-work', 'archive/test/fix/new-work'), ('fix/conflict', 'archive/test/fix/conflict')]:
            try:
                cleanup.archive_branch(branch, original, tag)
            except (ValueError, RuntimeError):
                pass
            else:
                raise AssertionError('Cleanup should refuse ' + branch)
        assert git('ls-remote', 'origin', 'refs/heads/fix/new-work').split()[0] == newer
        assert git('ls-remote', 'origin', 'refs/heads/fix/conflict').split()[0] == original
        assert git('ls-remote', 'origin', 'refs/heads/main').split()[0] == original
    finally:
        os.chdir(previous)
print('Release cleanup: archive preservation, repeatability, protected branches and changed-head refusal: PASS')
