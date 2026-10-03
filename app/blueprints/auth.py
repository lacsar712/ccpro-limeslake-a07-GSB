from functools import wraps

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


def admin_required(view):
    """仅管理员可访问；需叠在 login_required 之内使用。"""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            flash("仅管理员可执行此操作", "error")
            return redirect(url_for("board.floor_plan"))
        return view(*args, **kwargs)

    return wrapper


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            next_url = request.args.get("next") or url_for("board.floor_plan")
            return redirect(next_url)
        flash("用户名或密码错误", "error")
    return render_template("auth/login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
