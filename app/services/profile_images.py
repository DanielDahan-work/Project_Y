"""Validate image bytes and store private avatars using the EC2 IAM role."""
from io import BytesIO
import warnings
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app, g
from PIL import Image, ImageOps, UnidentifiedImageError


class InvalidProfileImage(ValueError):
    pass


class ProfileStorageError(RuntimeError):
    pass


def storage_enabled():
    return bool(current_app.config["PROFILE_IMAGES_BUCKET"])


def s3_client():
    if not storage_enabled():
        raise ProfileStorageError("Profile image storage is unavailable.")
    if "profile_s3" not in g:
        g.profile_s3 = boto3.client(
            "s3", region_name=current_app.config["PROFILE_IMAGES_REGION"],
            config=Config(signature_version="s3v4", connect_timeout=5, read_timeout=10,
                          retries={"max_attempts": 1}),
        )
    return g.profile_s3


def normalize_image(file):
    """Decode rather than trusting the filename, then re-encode without metadata."""
    maximum = current_app.config["PROFILE_IMAGE_MAX_BYTES"]
    data = file.stream.read(maximum + 1)
    if len(data) > maximum:
        raise InvalidProfileImage("Choose an image smaller than 2 MB.")
    if not data:
        raise InvalidProfileImage("Choose a JPEG or PNG image.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                image_format = image.format
                if image_format not in {"JPEG", "PNG"}:
                    raise InvalidProfileImage("Only JPEG and PNG images are supported.")
                if image.width * image.height > 16_000_000:
                    raise InvalidProfileImage("Choose an image with at most 16 million pixels.")
                if getattr(image, "n_frames", 1) != 1:
                    raise InvalidProfileImage("Choose a still image, rather than an animation.")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                normalized = ImageOps.exif_transpose(image)
                normalized.thumbnail((512, 512), Image.Resampling.LANCZOS)
                mode = "RGBA" if image_format == "PNG" else "RGB"
                clean = Image.new(mode, normalized.size)
                clean.paste(normalized.convert(mode))
                output = BytesIO()
                clean.save(output, format=image_format, **({"quality": 85} if image_format == "JPEG" else {}))
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        if isinstance(error, InvalidProfileImage):
            raise
        raise InvalidProfileImage("The image could not be read. Choose a valid JPEG or PNG.") from error
    return output.getvalue(), "jpg" if image_format == "JPEG" else "png"


def upload_image(user_id, data, extension):
    key = f"avatars/{user_id}/{uuid4().hex}.{extension}"
    try:
        s3_client().put_object(
            Bucket=current_app.config["PROFILE_IMAGES_BUCKET"], Key=key,
            Body=data, ContentType="image/jpeg" if extension == "jpg" else "image/png",
            ServerSideEncryption="AES256", CacheControl="private, max-age=300",
        )
    except (BotoCoreError, ClientError) as error:
        raise ProfileStorageError("The image could not be uploaded. Please try again.") from error
    return key


def delete_image(user_id, key):
    if not key or not key.startswith(f"avatars/{user_id}/"):
        return
    try:
        s3_client().delete_object(Bucket=current_app.config["PROFILE_IMAGES_BUCKET"], Key=key)
    except (BotoCoreError, ClientError) as error:
        raise ProfileStorageError("The previous image could not be removed.") from error


def image_url(user):
    key = user.profile_image_key
    if not storage_enabled() or not key or not key.startswith(f"avatars/{user.id}/"):
        return None
    try:
        return s3_client().generate_presigned_url(
            "get_object", Params={"Bucket": current_app.config["PROFILE_IMAGES_BUCKET"], "Key": key},
            ExpiresIn=current_app.config["PROFILE_IMAGE_URL_SECONDS"],
        )
    except (BotoCoreError, ClientError, ProfileStorageError):
        current_app.logger.warning("Could not generate a profile image URL.")
        return None
