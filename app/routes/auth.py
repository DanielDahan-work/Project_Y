from flask import Blueprint, render_template, request, redirect, url_for

from app import db
from app.models.user import User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        # Login will be connected to PostgreSQL next
        
        return redirect(url_for("home.home"))
    
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
       username = request.form["username"]
       email = request.form["email"]
       password = request.form["password"]
       
       existing_user = User.query.filter_by(username=username).first()

       if existing_user:
            return "Username already exists", 400

       user = User(
            username=username,
            email=email
        )

       user.set_password(password)

       db.session.add(user)
       db.session.commit()

       return redirect(url_for("auth.login"))

    return render_template("register.html")

