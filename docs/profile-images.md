# User profiles

Signed-in users open **My profile** by clicking their name in the navigation bar.
They can change their username, upload or replace a JPEG/PNG avatar, or remove it.
The username is also their next login name; the account ID, email, password and
verification status do not change. Names remain case-insensitive for login and
uniqueness. Profile changes require the existing session CSRF token.

## Storage

- `PROFILE_IMAGES_BUCKET`: private S3 bucket; empty disables image changes.
- `PROFILE_IMAGES_REGION`: bucket region, default `us-east-1`.
- Jenkins supplies `project-y-profile-images-daniel-081809265825` in `us-east-1`.
- AWS credentials come from the existing EC2 instance role. No access key is
  embedded in the image or repository. The role needs `s3:PutObject`,
  `s3:GetObject` and `s3:DeleteObject` on this bucket's `avatars/*` objects.
- Only a generated key such as `avatars/<account-id>/<uuid>.png` is stored in
  `users.profile_image_key`. Bucket public access remains blocked; image URLs
  use signed GET requests lasting 15 minutes (or until role credentials expire).
- Inputs are limited to 2 MiB and 16 million pixels. The server decodes and
  re-encodes still JPEG/PNG images, strips metadata and resizes to at most
  512 by 512 pixels. Browser filenames and declared MIME types are not trusted.
- Replacements save the new S3 object and database reference before deleting
  the previous object. Database failure triggers cleanup of the new object.
  If cleanup fails, a warning is logged and an unused object can remain in S3.
- Signed-in HTML responses are marked `private, no-store`.

## Deployment and recovery

Jenkins runs both migrations before stopping the old application container:

```bash
flask --app run migrate-email-verification
flask --app run migrate-profile-images
```

The profile migration adds a nullable column and an index enforcing unique
`lower(username)` values. It is repeatable and preserves existing accounts and
image references. If existing usernames differ only by letter case, it stops
with an explicit error; resolve those duplicate accounts before deployment.
A migration failure leaves the old container running. Existing users without
an image see the default profile icon. Old application code ignores the added
column, so an application rollback does not require dropping user data.

NAS build archives contain the application Docker image, not S3 avatar objects.
Database backups retain image keys, not the image bytes. The bucket currently
has versioning disabled, so deleting or replacing an avatar does not retain a
recoverable previous S3 version.

## Validation

```bash
python -m unittest discover -s tests -v
```

S3 operations in the tests are mocked. Set `TEST_POSTGRES_URI` to a disposable
local PostgreSQL database to additionally test the migrations, account
preservation, repeated runs, and case-insensitive uniqueness. Integration tests
create and remove their own random schema; never point them at production.
