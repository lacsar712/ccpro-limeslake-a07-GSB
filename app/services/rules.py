"""石灰熟化池业务规则。"""

from __future__ import annotations

from app.extensions import db
from app.models import NeighborClearance, Pond, SlakeBatch, utcnow

MIN_PEAK_TEMP_FOR_DRAWN = 60.0


class RuleError(ValueError):
    """业务规则校验失败。"""


def latest_batch_for_pond(pond: Pond) -> SlakeBatch | None:
    if not pond.batches:
        return None
    return max(pond.batches, key=lambda b: b.started_at)


def can_mark_pond_drawn(pond: Pond) -> tuple[bool, str]:
    """
    熟化池转为「已出灰」(drawn) 的前提：
    最近一条熟化批次的峰值温度已记录，且 >= 60℃。
    """
    latest = latest_batch_for_pond(pond)
    if latest is None:
        return False, "该池尚无熟化批次，不能标记为已出灰"
    if latest.peak_temp_c is None:
        return False, "最近批次尚未记录峰值温度，不能标记为已出灰"
    if latest.peak_temp_c < MIN_PEAK_TEMP_FOR_DRAWN:
        return (
            False,
            f"最近批次峰值温度 {latest.peak_temp_c}℃ 低于 {MIN_PEAK_TEMP_FOR_DRAWN:.0f}℃，不能标记为已出灰",
        )
    return True, ""


def hot_neighbors_for(pond: Pond) -> list[Pond]:
    """同厂处于熟化中的其他池（热邻）。"""
    if pond is None or pond.id is None or pond.plant_id is None:
        return []
    return (
        Pond.query.filter(
            Pond.plant_id == pond.plant_id,
            Pond.id != pond.id,
            Pond.status == Pond.STATUS_SLAKING,
        )
        .order_by(Pond.code)
        .all()
    )


def open_clearance_for_pond(pond_id: int) -> NeighborClearance | None:
    """目标池当前未核销的放行签（至多一张，由唯一索引兜底）。"""
    return (
        NeighborClearance.query.filter(
            NeighborClearance.target_pond_id == pond_id,
            NeighborClearance.consumed_at.is_(None),
        )
        .order_by(NeighborClearance.issued_at.desc())
        .first()
    )


def _consume_clearance_for_slaking(pond: Pond) -> None:
    """注水中 -> 熟化中：同厂有热邻时须持未核销放行签，并在同事务核销。"""
    if not hot_neighbors_for(pond):
        return
    ticket = open_clearance_for_pond(pond.id)
    if ticket is None:
        raise RuleError("同厂已有熟化中池，须先取得未核销的邻池放行签才能进入熟化中")
    ticket.consumed_at = utcnow()


def apply_pond_status(pond: Pond, new_status: str) -> None:
    """
    校验并应用池态变更（调用方负责 commit）：
    - 出灰规则照旧：最近批次峰值已记且 >= 60℃；
    - 注水中 -> 熟化中：同厂有热邻时须持未核销放行签，随状态变更一并核销。
    """
    if new_status not in Pond.STATUS_CHOICES:
        raise RuleError(f"无效状态：{new_status}")
    if new_status == Pond.STATUS_DRAWN:
        ok, msg = can_mark_pond_drawn(pond)
        if not ok:
            raise RuleError(msg)
    if pond.status == Pond.STATUS_FILLING and new_status == Pond.STATUS_SLAKING:
        _consume_clearance_for_slaking(pond)
    pond.status = new_status


def register_batch(pond: Pond, batch: SlakeBatch) -> None:
    """
    登记熟化批次（调用方负责 commit）：
    池当前为注水中时，登记批次即进入熟化中；同厂有热邻时须持未核销放行签，
    核销、批次入库、池态变更在同一事务完成。
    """
    if pond.status == Pond.STATUS_FILLING:
        _consume_clearance_for_slaking(pond)
        pond.status = Pond.STATUS_SLAKING
    db.session.add(batch)


def build_clearance(target: Pond, neighbor: Pond, issuer) -> NeighborClearance:
    """
    签发前校验并构造放行签（不落库）。
    并发双签由唯一索引 uq_neighbor_clearance_open_target 兜底，
    调用方需捕获 IntegrityError 并回滚。
    """
    if target is None or neighbor is None:
        raise RuleError("目标池或热邻池不存在")
    if neighbor.id == target.id:
        raise RuleError("热邻池不能是目标池本身")
    if neighbor.plant_id != target.plant_id:
        raise RuleError("热邻池须与目标池同厂")
    if neighbor.status != Pond.STATUS_SLAKING:
        raise RuleError("热邻池当前须为熟化中")
    if open_clearance_for_pond(target.id) is not None:
        raise RuleError("该目标池已存在未核销放行签")
    return NeighborClearance(
        target_pond_id=target.id,
        neighbor_pond_id=neighbor.id,
        issued_by_id=issuer.id,
        issued_at=utcnow(),
    )
