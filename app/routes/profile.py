from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import db
from app.models.user import User
from app.routes.auth import protect_auth_forms
from app.services.profile_images import (
    InvalidProfileImage, ProfileStorageError, delete_image, image_url,
    normalize_image, storage_enabled, upload_image,
)


profile_bp = Blueprint("profile", __name__)
profile_bp.before_request(protect_auth_forms)


@profile_bp.after_app_request
def prevent_profile_caching(response):
    if current_user.is_authenticated:
        response.headers["Cache-Control"] = "private, no-store"
    return response


@profile_bp.app_context_processor
def avatar_context():
    return {"profile_image_url": image_url(current_user) if current_user.is_authenticated else None}


def profile_page(error=None, status=200):
    return render_template("profile.html", storage_enabled=storage_enabled(), error=error), status


@profile_bp.errorhandler(413)
def image_too_large(error):
    return profile_page("Choose an image smaller than 2 MB.", 413)


def cleanup_image(user_id, key):
    try:
        delete_image(user_id, key)
    except ProfileStorageError:
        current_app.logger.warning("Profile image cleanup failed; an unused object remains in S3.")
        flash("An unused image could not be removed from storage.", "warning")


@profile_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "GET":
        return profile_page()
    if not storage_enabled():
        return profile_page("Profile image uploads are temporarily unavailable.", 503)
    file = request.files.get("image")
    if file is None or not file.filename:
        return profile_page("Choose a JPEG or PNG image to upload.", 400)
    try:
        data, extension = normalize_image(file)
        new_key = upload_image(current_user.id, data, extension)
    except InvalidProfileImage as error:
        return profile_page(str(error), 400)
    except ProfileStorageError as error:
        return profile_page(str(error), 503)

    user_id = current_user.id
    try:
        # Serialize replacements and refresh ORM values after a concurrent upload.
        user = db.session.execute(
            select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
        ).scalar_one()
        old_key = user.profile_image_key
        user.profile_image_key = new_key
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        cleanup_image(user_id, new_key)
        return profile_page("Your profile could not be saved. Please try again.", 503)
    cleanup_image(user_id, old_key)
    flash("Your profile image was updated.", "success")
    return redirect(url_for("profile.profile"))


@profile_bp.route("/profile/remove-image", methods=["POST"])
@login_required
def remove_image():
    if not storage_enabled():
        return profile_page("Profile image storage is temporarily unavailable.", 503)
    user_id = current_user.id
    try:
        user = db.session.execute(
            select(User).where(User.id == user_id).with_for_update().execution_options(populate_existing=True)
        ).scalar_one()
        old_key = user.profile_image_key
        user.profile_image_key = None
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return profile_page("Your profile could not be saved. Please try again.", 503)
    cleanup_image(user_id, old_key)
    flash("Your profile image was removed.", "success")
    return redirect(url_for("profile.profile"))


@profile_bp.route("/profile/username", methods=["POST"])
@login_required
def update_username():
    username = request.form.get("username", "").strip()
    if not username or len(username) > 80 or not username.isprintable():
        return profile_page("Enter a username between 1 and 80 characters.", 400)
    duplicate = User.query.filter(
        func.lower(User.username) == username.lower(), User.id != current_user.id
    ).first()
    if duplicate:
        return profile_page("That username is already taken. Choose another name.", 400)
    try:
        current_user.username = username
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return profile_page("That username is already taken. Choose another name.", 400)
    except SQLAlchemyError:
        db.session.rollback()
        return profile_page("Your username could not be saved. Please try again.", 503)
    flash("Your username was updated. Use this name the next time you sign in.", "success")
    return redirect(url_for("profile.profile"))
