from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.models import Pond, SlakeBatch
from app.services.rules import (
    RuleError,
    claim_pass,
    prepare_enter_slaking,
)

bp = Blueprint("batches", __name__, url_prefix="/batches")


@bp.route("/")
@login_required
def list_batches():
    batches = (
        SlakeBatch.query.join(Pond)
        .order_by(SlakeBatch.started_at.desc())
        .all()
    )
    return render_template("batches/list.html", batches=batches)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create_batch():
    ponds = Pond.query.order_by(Pond.code).all()
    if request.method == "POST":
        pond_id = int(request.form["pond_id"])
        started_raw = request.form.get("started_at") or ""
        target = float(request.form.get("target_temp_c") or 80)
        peak_raw = (request.form.get("peak_temp_c") or "").strip()
        notes = (request.form.get("notes") or "").strip()
        started_at = (
            datetime.fromisoformat(started_raw)
            if started_raw
            else datetime.utcnow()
        )
        peak = float(peak_raw) if peak_raw else None
        pond = db.session.get(Pond, pond_id)
        if pond is None:
            flash("熟化池不存在", "error")
            return redirect(url_for("batches.create_batch"))

        batch = SlakeBatch(
            pond_id=pond_id,
            started_at=started_at,
            target_temp_c=target,
            peak_temp_c=peak,
            notes=notes,
        )

        try:
            # 注水池登记批次即进入熟化中：同厂有热邻须持未核销放行签。
            # 必须先在本事务原子核销该签，批次才允许入库并翻转池态（同生共死）。
            redeemed_id = None
            if pond.status == Pond.STATUS_FILLING:
                pass_id = prepare_enter_slaking(pond)
                if pass_id is not None:
                    if not claim_pass(pass_id):
                        raise RuleError("放行签已被同时核销，请刷新平面图后重试")
                    redeemed_id = pass_id
                pond.status = Pond.STATUS_SLAKING

            db.session.add(batch)
            db.session.commit()
            if redeemed_id is not None:
                flash(
                    f"熟化批次已登记，放行签 #{redeemed_id} 已核销，{pond.code} 进入熟化中",
                    "ok",
                )
            elif pond.status == Pond.STATUS_SLAKING:
                flash(f"熟化批次已登记，{pond.code} 进入熟化中", "ok")
            else:
                flash("熟化批次已登记", "ok")
            return redirect(
                url_for(
                    "board.floor_plan",
                    plant_id=pond.plant_id,
                    pond=pond_id,
                )
            )
        except RuleError as exc:
            db.session.rollback()
            flash(str(exc), "error")
            return redirect(
                url_for(
                    "board.floor_plan",
                    plant_id=pond.plant_id,
                    pond=pond_id,
                )
            )
    return render_template("batches/form.html", ponds=ponds, batch=None)


@bp.route("/<int:batch_id>/edit", methods=["GET", "POST"])
@login_required
def edit_batch(batch_id: int):
    batch = SlakeBatch.query.get_or_404(batch_id)
    ponds = Pond.query.order_by(Pond.code).all()
    if request.method == "POST":
        batch.pond_id = int(request.form["pond_id"])
        started_raw = request.form.get("started_at") or ""
        if started_raw:
            batch.started_at = datetime.fromisoformat(started_raw)
        batch.target_temp_c = float(request.form.get("target_temp_c") or 80)
        peak_raw = (request.form.get("peak_temp_c") or "").strip()
        batch.peak_temp_c = float(peak_raw) if peak_raw else None
        batch.notes = (request.form.get("notes") or "").strip()
        db.session.commit()
        flash("熟化批次已更新", "ok")
        return redirect(
            url_for(
                "board.floor_plan",
                plant_id=batch.pond.plant_id,
                pond=batch.pond_id,
            )
        )
    return render_template("batches/form.html", ponds=ponds, batch=batch)
