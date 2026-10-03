from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.blueprints.auth import admin_required
from app.extensions import db
from app.models import Pond, ReleasePass, utcnow
from app.services.rules import RuleError, assert_can_issue_pass

bp = Blueprint("passes", __name__, url_prefix="/passes")


def _issue_form_ponds():
    """签发表单的候选池：注水池可作目标，熟化中池可作热邻。"""
    ponds = (
        Pond.query.join(Pond.plant)
        .order_by(Pond.plant_id, Pond.code)
        .all()
    )
    targets = [p for p in ponds if p.status == Pond.STATUS_FILLING]
    hot_options = [p for p in ponds if p.status == Pond.STATUS_SLAKING]
    return targets, hot_options


@bp.route("/")
@login_required
def index():
    open_passes = (
        ReleasePass.query.filter_by(redeemed_at=None)
        .order_by(ReleasePass.issued_at.desc())
        .all()
    )
    redeemed_passes = (
        ReleasePass.query.filter(ReleasePass.redeemed_at.isnot(None))
        .order_by(ReleasePass.redeemed_at.desc())
        .limit(10)
        .all()
    )
    targets, hot_options = _issue_form_ponds()
    return render_template(
        "passes/index.html",
        open_passes=open_passes,
        redeemed_passes=redeemed_passes,
        targets=targets,
        hot_options=hot_options,
        preset_target_id=request.args.get("target_id", type=int),
        preset_hot_id=request.args.get("hot_pond_id", type=int),
        is_admin=current_user.role == "admin",
    )


@bp.route("/issue", methods=["POST"])
@admin_required
def issue():
    target_id = request.form.get("target_pond_id", type=int)
    hot_id = request.form.get("hot_pond_id", type=int)
    target = db.session.get(Pond, target_id) if target_id else None
    hot = db.session.get(Pond, hot_id) if hot_id else None
    if target is None or hot is None:
        flash("请选择目标池与热邻池", "error")
        return redirect(url_for("passes.index"))

    try:
        assert_can_issue_pass(target, hot)
        pas = ReleasePass(
            target_pond_id=target.id,
            hot_pond_id=hot.id,
            issued_by=current_user.id,
        )
        db.session.add(pas)
        # 先 flush 让部分唯一索引在并发下立刻兜底，而不是拖到提交。
        db.session.flush()
        db.session.commit()
        flash(
            f"已签发：{target.code} 凭热邻 {hot.code} 放行（{target.plant.name}）",
            "ok",
        )
    except RuleError as exc:
        db.session.rollback()
        flash(str(exc), "error")
    except IntegrityError:
        # 两名管理员同时给同一目标池开未核销签：只有一张能落库。
        db.session.rollback()
        flash("该目标池已有一张未核销放行签（可能与其他管理员同时签发），仅保留一张", "error")

    return redirect(
        url_for(
            "passes.index",
            target_id=target.id,
            hot_pond_id=hot.id,
        )
    )


@bp.route("/<int:pass_id>/redeem", methods=["POST"])
@admin_required
def redeem(pass_id: int):
    pas = ReleasePass.query.get_or_404(pass_id)
    if pas.redeemed_at is not None:
        flash("该放行签已核销", "error")
    else:
        pas.redeemed_at = utcnow()
        db.session.commit()
        flash(f"放行签 #{pas.id} 已核销", "ok")
    return redirect(url_for("passes.index"))
