from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.blueprints.auth import admin_required
from app.extensions import db
from app.models import NeighborClearance, Plant, Pond, utcnow
from app.services.rules import RuleError, build_clearance

bp = Blueprint("clearances", __name__, url_prefix="/clearances")


def _form_pond_id(name: str) -> int | None:
    raw = (request.form.get(name) or "").strip()
    return int(raw) if raw.isdigit() else None


@bp.route("/")
@login_required
def list_clearances():
    open_tickets = (
        NeighborClearance.query.filter(NeighborClearance.consumed_at.is_(None))
        .order_by(NeighborClearance.issued_at.desc())
        .all()
    )
    recent_consumed = (
        NeighborClearance.query.filter(NeighborClearance.consumed_at.isnot(None))
        .order_by(NeighborClearance.consumed_at.desc())
        .limit(10)
        .all()
    )
    targets = (
        Pond.query.join(Plant)
        .filter(Pond.status == Pond.STATUS_FILLING)
        .order_by(Plant.name, Pond.code)
        .all()
    )
    neighbors = (
        Pond.query.join(Plant)
        .filter(Pond.status == Pond.STATUS_SLAKING)
        .order_by(Plant.name, Pond.code)
        .all()
    )
    return render_template(
        "clearances/list.html",
        open_tickets=open_tickets,
        recent_consumed=recent_consumed,
        targets=targets,
        neighbors=neighbors,
    )


@bp.route("/issue", methods=["POST"])
@login_required
@admin_required
def issue_clearance():
    target_id = _form_pond_id("target_pond_id")
    neighbor_id = _form_pond_id("neighbor_pond_id")
    target = db.session.get(Pond, target_id) if target_id else None
    neighbor = db.session.get(Pond, neighbor_id) if neighbor_id else None
    try:
        ticket = build_clearance(target, neighbor, current_user)
    except RuleError as exc:
        flash(str(exc), "error")
        return redirect(url_for("clearances.list_clearances"))

    db.session.add(ticket)
    try:
        db.session.commit()
    except IntegrityError:
        # 并发双签：唯一索引只放行一张，被挡的这张整体回滚
        db.session.rollback()
        flash("该目标池已存在未核销放行签，本次签发被挡下", "error")
        return redirect(url_for("clearances.list_clearances"))

    flash(f"已签发 {ticket.target_pond.code} 的邻池放行签", "ok")
    return redirect(url_for("clearances.list_clearances"))


@bp.route("/<int:clearance_id>/consume", methods=["POST"])
@login_required
@admin_required
def consume_clearance(clearance_id: int):
    ticket = NeighborClearance.query.get_or_404(clearance_id)
    if ticket.consumed_at is not None:
        flash("该放行签已核销", "error")
    else:
        ticket.consumed_at = utcnow()
        db.session.commit()
        flash(f"{ticket.target_pond.code} 的放行签已核销", "ok")
    return redirect(url_for("clearances.list_clearances"))
