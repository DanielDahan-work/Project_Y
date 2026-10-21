import io
import unittest
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError, NoCredentialsError
from PIL import Image
from sqlalchemy.exc import SQLAlchemyError

from app import create_app, db
from app.models.user import User


def picture(format="PNG", size=(800, 400)):
    output = io.BytesIO()
    Image.new("RGB", size, "navy").save(output, format=format)
    return output.getvalue()


class ProfileImageTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            "TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SECRET_KEY": "profile-test-secret-" * 3, "SESSION_COOKIE_SECURE": False,
            "PROFILE_IMAGES_BUCKET": "test-private-bucket", "PROFILE_IMAGES_REGION": "us-east-1",
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.user = User(username="Daniel", email="daniel@example.com", email_verified=True)
        self.user.set_password("password")
        self.other = User(username="Other", email="other@example.com", email_verified=True,
                          profile_image_key="avatars/2/other.png")
        self.other.set_password("password")
        db.session.add_all([self.user, self.other])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = str(self.user.id)
            session["_fresh"] = True
            session["auth_csrf"] = "test-csrf"
        self.s3 = MagicMock()
        self.s3.generate_presigned_url.return_value = "https://example.com/private-image?signature=test"
        self.client_patch = patch("app.services.profile_images.boto3.client", return_value=self.s3)
        self.client_patch.start()

    def tearDown(self):
        self.client_patch.stop()
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def upload(self, data=None, filename="photo.png", **extra):
        form = {"csrf_token": "test-csrf", "image": (io.BytesIO(picture() if data is None else data), filename)}
        form.update(extra)
        return self.client.post("/profile", data=form, content_type="multipart/form-data")

    def test_upload_uses_logged_in_owner_private_encryption_and_normalized_bytes(self):
        response = self.upload(user_id=str(self.other.id), profile_image_key=self.other.profile_image_key)
        self.assertEqual(response.status_code, 302)
        key = self.user.profile_image_key
        self.assertTrue(key.startswith(f"avatars/{self.user.id}/"))
        self.assertEqual(self.other.profile_image_key, "avatars/2/other.png")
        request = self.s3.put_object.call_args.kwargs
        self.assertEqual(request["Bucket"], "test-private-bucket")
        self.assertEqual(request["Key"], key)
        self.assertEqual(request["ContentType"], "image/png")
        self.assertEqual(request["ServerSideEncryption"], "AES256")
        self.assertNotIn("ACL", request)
        with Image.open(io.BytesIO(request["Body"])) as image:
            self.assertEqual(image.size, (512, 256))
        self.s3.delete_object.assert_not_called()
        page = self.client.get("/profile")
        self.assertIn(b"private-image?signature=test", page.data)
        self.assertIn(b"navbar-avatar", page.data)
        self.assertEqual(page.headers["Cache-Control"], "private, no-store")
        self.assertEqual(self.s3.generate_presigned_url.call_args.kwargs["ExpiresIn"], 900)

    def test_jpeg_content_is_detected_without_trusting_filename(self):
        self.assertEqual(self.upload(picture("JPEG"), "misleading.png").status_code, 302)
        self.assertTrue(self.user.profile_image_key.endswith(".jpg"))
        self.assertEqual(self.s3.put_object.call_args.kwargs["ContentType"], "image/jpeg")

    def test_metadata_is_removed(self):
        from PIL.PngImagePlugin import PngInfo
        output = io.BytesIO()
        info = PngInfo()
        info.add_text("Private note", "location metadata")
        Image.new("RGB", (10, 10), "navy").save(output, "PNG", pnginfo=info)
        self.assertEqual(self.upload(output.getvalue()).status_code, 302)
        with Image.open(io.BytesIO(self.s3.put_object.call_args.kwargs["Body"])) as image:
            self.assertNotIn("Private note", image.info)

    def test_invalid_empty_unsupported_truncated_and_oversized_images_never_reach_s3(self):
        for data in (b"<svg></svg>", b"", picture("GIF"), picture()[:30], b"x" * (2 * 1024 * 1024 + 1)):
            with self.subTest(length=len(data)):
                self.assertEqual(self.upload(data).status_code, 400)
        self.s3.put_object.assert_not_called()
        self.assertIsNone(self.user.profile_image_key)

    def test_large_request_returns_helpful_413(self):
        response = self.upload(b"x" * (3 * 1024 * 1024 + 1))
        self.assertEqual(response.status_code, 413)
        self.assertIn(b"smaller than 2 MB", response.data)
        self.s3.put_object.assert_not_called()

    def test_excessive_pixel_count_is_rejected(self):
        self.assertEqual(self.upload(picture(size=(4100, 4000))).status_code, 400)
        self.s3.put_object.assert_not_called()

    def test_csrf_missing_or_wrong_blocks_upload_and_removal(self):
        for path in ("/profile", "/profile/remove-image", "/profile/username"):
            for token in ("", "wrong", "שלום"):
                self.assertEqual(self.client.post(path, data={"csrf_token": token}).status_code, 400)
        self.s3.put_object.assert_not_called()
        self.s3.delete_object.assert_not_called()

    def test_anonymous_and_unverified_accounts_cannot_upload(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get("/profile").status_code, 302)
        with anonymous.session_transaction() as session:
            session["auth_csrf"] = "test-csrf"
        self.assertEqual(anonymous.post("/profile", data={"csrf_token": "test-csrf"}).status_code, 302)
        self.user.email_verified = False
        db.session.commit()
        self.assertEqual(self.upload().status_code, 302)
        self.s3.put_object.assert_not_called()

    def test_replacement_deletes_old_image_only_after_database_commit(self):
        self.user.profile_image_key = f"avatars/{self.user.id}/old.png"
        db.session.commit()
        old_key = self.user.profile_image_key
        def check_committed(**kwargs):
            self.assertEqual(kwargs["Key"], old_key)
            self.assertNotEqual(db.session.get(User, self.user.id).profile_image_key, old_key)
        self.s3.delete_object.side_effect = check_committed
        self.assertEqual(self.upload().status_code, 302)
        self.s3.delete_object.assert_called_once()

    def test_upload_failure_preserves_old_image(self):
        self.user.profile_image_key = f"avatars/{self.user.id}/old.png"
        db.session.commit()
        self.s3.put_object.side_effect = NoCredentialsError()
        self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(self.user.profile_image_key, f"avatars/{self.user.id}/old.png")
        self.s3.delete_object.assert_not_called()

    def test_database_failure_cleans_new_upload_and_preserves_old_image(self):
        self.user.profile_image_key = f"avatars/{self.user.id}/old.png"
        db.session.commit()
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("unavailable")):
            self.assertEqual(self.upload().status_code, 503)
        self.assertEqual(self.user.profile_image_key, f"avatars/{self.user.id}/old.png")
        self.assertEqual(self.s3.delete_object.call_args.kwargs["Key"], self.s3.put_object.call_args.kwargs["Key"])

    def test_cleanup_failure_keeps_new_profile_and_shows_warning(self):
        self.user.profile_image_key = f"avatars/{self.user.id}/old.png"
        db.session.commit()
        self.s3.delete_object.side_effect = ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")
        self.assertEqual(self.upload().status_code, 302)
        self.assertNotEqual(self.user.profile_image_key, f"avatars/{self.user.id}/old.png")
        self.assertIn(b"unused image", self.client.get("/profile").data)

    def test_remove_image_resets_avatar_and_cannot_delete_another_users_image(self):
        self.user.profile_image_key = f"avatars/{self.user.id}/old.png"
        db.session.commit()
        self.assertEqual(self.client.post("/profile/remove-image", data={"csrf_token": "test-csrf"}).status_code, 302)
        self.assertIsNone(self.user.profile_image_key)
        self.assertEqual(self.s3.delete_object.call_args.kwargs["Key"], f"avatars/{self.user.id}/old.png")
        self.user.profile_image_key = self.other.profile_image_key
        db.session.commit()
        self.s3.delete_object.reset_mock()
        page = self.client.get("/profile")
        self.assertNotIn(b"private-image", page.data)
        self.client.post("/profile/remove-image", data={"csrf_token": "test-csrf"})
        self.s3.delete_object.assert_not_called()

    def test_disabled_storage_keeps_profile_page_available(self):
        self.app.config["PROFILE_IMAGES_BUCKET"] = ""
        self.assertEqual(self.client.get("/profile").status_code, 200)
        self.assertEqual(self.upload().status_code, 503)
        self.s3.put_object.assert_not_called()

    def test_signing_failure_falls_back_to_default_avatar(self):
        self.user.profile_image_key = f"avatars/{self.user.id}/old.png"
        db.session.commit()
        self.s3.generate_presigned_url.side_effect = NoCredentialsError()
        page = self.client.get("/profile")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"Default profile image", page.data)

    def test_profile_migration_rejects_non_postgres(self):
        result = self.app.test_cli_runner().invoke(args=["migrate-profile-images"])
        self.assertEqual(result.exit_code, 1)
        self.assertIn("requires PostgreSQL", result.output)

    def test_username_change_updates_navigation_and_login_but_not_account_ownership(self):
        original_id = self.user.id
        original_email = self.user.email
        response = self.client.post("/profile/username", data={
            "csrf_token": "test-csrf", "username": "  DanielNew  ", "user_id": str(self.other.id)
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.user.id, original_id)
        self.assertEqual(self.user.email, original_email)
        self.assertEqual(self.user.username, "DanielNew")
        self.assertEqual(self.other.username, "Other")
        self.assertIn(b"DanielNew", self.client.get("/profile").data)
        self.client.get("/logout")
        for name, status in (("Daniel", 401), ("DANIELNEW", 302)):
            self.assertEqual(self.client.post("/login", data={
                "csrf_token": "test-csrf", "username": name, "password": "password"
            }).status_code, status)

    def test_username_conflict_validation_and_case_only_change(self):
        for name in ("OTHER", "other", "", "   ", "x" * 81, "hello\nworld"):
            self.assertEqual(self.client.post("/profile/username", data={
                "csrf_token": "test-csrf", "username": name
            }).status_code, 400)
            self.assertEqual(self.user.username, "Daniel")
        self.assertEqual(self.client.post("/profile/username", data={
            "csrf_token": "test-csrf", "username": "DANIEL"
        }).status_code, 302)
        self.assertEqual(self.user.username, "DANIEL")

    def test_username_can_be_changed_when_image_storage_is_disabled(self):
        self.app.config["PROFILE_IMAGES_BUCKET"] = ""
        self.assertEqual(self.client.post("/profile/username", data={
            "csrf_token": "test-csrf", "username": "DanielNew"
        }).status_code, 302)

    def test_username_database_failure_preserves_old_name(self):
        with patch.object(db.session, "commit", side_effect=SQLAlchemyError("unavailable")):
            self.assertEqual(self.client.post("/profile/username", data={
                "csrf_token": "test-csrf", "username": "DanielNew"
            }).status_code, 503)
        self.assertEqual(self.user.username, "Daniel")
