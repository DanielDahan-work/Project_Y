# Project Y build archives

The pipeline saves the image actually built and deployed, plus a readable build
record and SHA-256 checksums. Each build has its own directory under
`/data/share/project-y-builds/<job>/build-<number>-<commit>` on the NAS.
Windows users open `\\10.50.2.10\nas\project-y-builds` using their existing SMB access.

If a build fails before creating an image, the archive contains its build record
only. If deployment fails after building an image, that image is still archived.
The record describes the pipeline result before archiving; a backup failure makes
the Jenkins job fail too, even if deployment already completed.
An unavailable agent or a failed initial checkout may prevent archiving altogether.

Uploads use a private temporary directory. Files become readable after remote
checksum verification, followed by a directory rename. Existing completed archives
are not overwritten. Failed temporary uploads remain for investigation.

## One-time NAS setup

Run as ubuntu on PX-NAS-01:

```sh
sudo install -d -o ubuntu -g ubuntu -m 755 /data/share/project-y-builds
ls -ld /data/share /data/share/project-y-builds
```

This creates only the application archive directory. Do not change permissions on
the private Jenkins configuration backups or key vault. Existing Samba rules and
parent-directory permissions must allow the intended SMB users to read this path.
These commands do not enable guest access or change share-wide write permissions.

## Jenkins prerequisites

The agent needs Python 3, Docker, OpenSSH client tools, and the Jenkins SSH Agent
plugin. The ubuntu account on the NAS must accept the backup SSH public key.
The existing `restrict` authorized_keys option permits commands and SFTP uploads.

Add two Jenkins credentials in the job's credential scope:

* `project-y-nas-backup`: SSH Username with private key, username `ubuntu`.
  Enter the backup private key and its passphrase in Jenkins credentials only.
  Never commit this key or paste it into a chat.
* `project-y-nas-known-hosts`: Secret file containing the pinned NAS known_hosts
  entry. Verify the NAS ED25519 fingerprint is
  `SHA256:QL3wtSYPifHMnUkhCaX2w6Ik4uEkQTouVCC7ynu9r6k` before saving it.
  Host checking is mandatory; the script does not accept unknown hosts automatically.

Do this before enabling the updated Jenkinsfile. Run a build and check for
`NAS_BUILD_BACKUP_VERIFIED` in its console. Open the folder over SMB and inspect
README.txt and build.json. Verify SHA256SUMS on the NAS. Finally test loading the
saved image on a suitable Docker host; loading alone does not start a container.

## Restore and storage

```sh
sha256sum -c SHA256SUMS
docker image load --input image.tar.gz
```

Recreate the container using the restored tag and the normal runtime settings.
The archive does not contain PostgreSQL data, runtime credentials, or Jenkins
configuration. Application images contain the application's source code.

No automatic deletion is configured. Monitor NAS free space and Jenkins local
space: unique Docker tags accumulate locally as well as archives on the NAS.
Local tests use mocked Docker and SSH; a real Jenkins/NAS build is required to
validate credentials, networking, plugin availability, permissions and restore.
