"""Publish a Docker image and readable build record to the NAS using SSH agent auth."""

import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def make_bundle(directory, env):
    # Explicit fields only: never dump the environment or container credentials.
    record = {
        'job': env['JOB_NAME'],
        'build_number': env['BUILD_NUMBER'],
        'commit': env.get('GIT_COMMIT', ''),
        'build_result_before_backup': env['BUILD_RESULT'],
        'build_url': env.get('BUILD_URL', ''),
        'saved_at_utc': datetime.now(timezone.utc).isoformat(),
        'image': None,
        'image_id': None,
        'image_archive': None,
    }
    if env.get('IMAGE_BUILT') == 'true':
        image = env['BUILD_IMAGE']
        record['image_id'] = subprocess.check_output(
            ['docker', 'image', 'inspect', '--format', '{{.Id}}', image], text=True
        ).strip()
        archive = directory / 'image.tar.gz'
        with subprocess.Popen(['docker', 'image', 'save', image], stdout=subprocess.PIPE) as process:
            try:
                with gzip.open(archive, 'wb') as target:
                    shutil.copyfileobj(process.stdout, target)
            except BaseException:
                process.kill()
                raise
            finally:
                process.stdout.close()
            if process.wait() != 0:
                raise RuntimeError('Docker export failed; incomplete backup will not be published.')
        record.update(image=image, image_archive=archive.name)

    (directory / 'build.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    restore = (
        'Restore the saved image with: docker image load --input image.tar.gz\n'
        'Recreate the application container with its configured ports, network and runtime credentials.\n'
        'This archive does not include database contents or runtime credentials.\n'
        if record['image'] else
        'This build did not produce a Docker image. This folder contains its build record only.\n'
    )
    (directory / 'README.txt').write_text(
        f"Project Y build {record['build_number']}\n"
        f"Job: {record['job']}\nCommit: {record['commit']}\n"
        f"Build result before backup: {record['build_result_before_backup']}\n"
        'Verify downloaded files with: sha256sum -c SHA256SUMS\n\n' + restore,
        encoding='utf-8',
    )
    files = sorted(directory.iterdir())
    (directory / 'SHA256SUMS').write_text(
        ''.join(f'{sha256(path)}  {path.name}\n' for path in files), encoding='utf-8'
    )
    return record


def destination_paths(env):
    root = env['NAS_BACKUP_ROOT']
    path = PurePosixPath(root)
    if not path.is_absolute() or len(path.parts) < 3 or '..' in path.parts:
        raise ValueError('NAS_BACKUP_ROOT must be an absolute directory below /data or another share.')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', env['NAS_HOST']):
        raise ValueError('Invalid NAS host')
    if not re.fullmatch(r'[A-Za-z0-9_-]+', env['NAS_USER']):
        raise ValueError('Invalid NAS user')
    number = env['BUILD_NUMBER']
    commit = env.get('GIT_COMMIT', '')
    if not number.isdigit() or (commit and not re.fullmatch(r'[0-9a-fA-F]{40,64}', commit)):
        raise ValueError('Invalid build number or commit')
    job = env['JOB_NAME']
    slug = re.sub(r'[^A-Za-z0-9_-]+', '-', job).strip('-')[:64] or 'job'
    job_directory = path / f'{slug}-{hashlib.sha256(job.encode()).hexdigest()[:8]}'
    build_name = f'build-{number}-{commit[:12] or "no-commit"}'
    return job_directory, build_name


def publish(directory, env):
    job_directory, build_name = destination_paths(env)
    remote = f"{env['NAS_USER']}@{env['NAS_HOST']}"
    options = ['-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
               '-o', f"UserKnownHostsFile={env['NAS_KNOWN_HOSTS']}", '-o', 'ConnectTimeout=15']
    q = shlex.quote
    root = str(PurePosixPath(env['NAS_BACKUP_ROOT']))
    job = str(job_directory)
    destination = str(job_directory / build_name)
    command = (
        f'test -d {q(root)} && test -w {q(root)} && '
        f'mkdir -p -- {q(job)} && chmod 755 -- {q(job)} && '
        f'test ! -e {q(destination)} && '
        f'mktemp -d {q(job + "/.upload-" + build_name + "-XXXXXX")}'
    )
    stage = subprocess.check_output(['ssh', *options, remote, command], text=True).strip()
    stage_path = PurePosixPath(stage)
    if stage_path.parent != job_directory or not stage_path.name.startswith(f'.upload-{build_name}-'):
        raise RuntimeError('NAS returned an unexpected staging path')
    # Staging remains private until checksums pass. Failed uploads stay hidden
    # for investigation; an existing completed backup is never replaced.
    subprocess.run(['scp', *options, '-p', *map(str, sorted(directory.iterdir())),
                    f'{remote}:{stage}/'], check=True)
    command = (
        f'cd {q(stage)} && sha256sum -c SHA256SUMS && '
        f'test ! -e {q(destination)} && chmod 644 -- ./* && chmod 755 . && '
        f'mv -T -- {q(stage)} {q(destination)}'
    )
    subprocess.run(['ssh', *options, remote, command], check=True)
    print(f'NAS_BUILD_BACKUP_VERIFIED: {destination}')


def main():
    env = os.environ
    destination_paths(env)
    with tempfile.TemporaryDirectory(prefix='project-y-build-backup-') as temporary:
        directory = Path(temporary)
        make_bundle(directory, env)
        publish(directory, env)


if __name__ == '__main__':
    main()
