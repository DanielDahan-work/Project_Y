# Email verification with Brevo

## Jenkins credentials and deployment

Store these in Jenkins System / Global credentials as **Secret text**:

- `project-y-brevo-api-key`: the Brevo API key (not an SMTP key).
- `project-y-secret-key`: a stable random value, at least 32 characters.

The verified sender is `noreply@project-x.ink`. Jenkins injects the keys into
the runtime container, alongside `EMAIL_SENDER`, `PUBLIC_BASE_URL` and secure
session cookies. They are not Docker build arguments and do not enter the image
archived on the NAS. Administrators with Docker access can read runtime secrets.

The first deployment with the new signing key signs out existing browser sessions;
users can sign in again. Keep this key stable: rotating it invalidates sessions and
outstanding email verification links. Store it with your private recovery secrets,
not in the shared website-build archive.

Before stopping the existing site, Jenkins runs:

```sh
flask --app run migrate-email-verification
```

This PostgreSQL migration adds three columns to `users` in a transaction and uses
an advisory lock. Existing accounts get `email_verification_required=false` and
`email_verified=false`: their access remains available without falsely claiming
verified emails. New accounts require verification. Rerunning the migration leaves
existing flags intact. A failed migration stops deployment while the old container
remains running. Old application code can still use the table with the added columns;
do not drop columns on rollback. Back up the database before the first deployment.

## API request

The server sends `POST https://api.brevo.com/v3/smtp/email` using HTTPS, an `api-key`
header and JSON containing `sender`, `to`, `subject`, `htmlContent` and `textContent`.
It expects HTTP 201 (provider acceptance, not proof of inbox delivery). The 10-second
timeout bounds request latency. Redirects are refused to avoid forwarding credentials.
Errors log only status information; keys, recipients and links are not logged.

Documentation: https://developers.brevo.com/reference/send-transac-email

The signed token contains the user ID and current email and expires after one hour.
The configured public base URL prevents request Host headers from changing the link.
Opening a link displays a confirmation form; POST with a session CSRF token verifies
the email. This avoids verification by automatic link scanners. Login and registration
forms also have CSRF protection. Unverified new accounts cannot sign in or restore a
Flask-Login session. Existing public pages remain public.

After successful signup the account is saved even if Brevo fails. The user can retry
at `/resend-verification` with their email and password. An atomic database update
limits attempts to one per account per minute, including unsuccessful deliveries.
Verified accounts are not sent additional messages. Resending does not revoke older
unexpired links. Username and email duplicate checks ignore case; the original
case-sensitive PostgreSQL unique constraints remain (concurrent differently cased
signups would require a separate unique-index migration to eliminate that race).

This per-account cooldown is not a global anti-abuse or signup quota mechanism.
For wider public usage, add registration throttling/CAPTCHA before relying on a
limited provider allowance. No marketing subscriptions are created.

## Validation and acceptance

```sh
python -m unittest discover -s tests -v
```

The default tests use SQLite and mocked Brevo HTTPS calls: they do not spend mail
quota or use real credentials. Set `TEST_POSTGRES_URI` to a disposable PostgreSQL
database to run the migration integration test in a temporary schema. The test
creates and drops only its randomly named `email_test_...` schema. Without this
variable the integration test is skipped, including in the default Jenkins run.

Validation for this change: 23 tests passed, including the migration integration
test on an isolated PostgreSQL 17.10 instance. It checked unchanged legacy data,
legacy login, new-user database defaults and rerunning the migration after a user
was verified. No production database was accessed. Then check a controlled real
signup with an email address you own:

1. Jenkins completes schema migration and starts the new container.
2. A new account receives mail and cannot log in until confirmation.
3. Opening the link alone leaves the account pending; pressing Confirm activates it.
4. `Gal`, `gal` and `GAL` can log in with the account's password.
5. Existing accounts can still log in; NAS build archival remains successful.

Check Brevo transactional logs and the spam folder if the provider accepted a message
but it has not arrived. Mail delivery and a live PostgreSQL migration are not proven
by the mocked local tests.
