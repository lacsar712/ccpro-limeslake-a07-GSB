"""石灰熟化池业务规则。"""

from __future__ import annotations

from sqlalchemy import update

from app.extensions import db
from app.models import Pond, ReleasePass, SlakeBatch, utcnow

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


def hot_neighbor_ponds(pond: Pond) -> list[Pond]:
    """同厂且当前正处于「熟化中」的其他池（热邻池）。"""
    if pond.plant is None:
        return []
    return [
        p
        for p in pond.plant.ponds
        if p.id != pond.id and p.status == Pond.STATUS_SLAKING
    ]


def needs_release_pass(pond: Pond) -> bool:
    """注水池欲进入熟化中时，是否因同厂热邻而须持放行签。"""
    return pond.status == Pond.STATUS_FILLING and bool(hot_neighbor_ponds(pond))


def assert_can_issue_pass(target_pond: Pond, hot_pond: Pond) -> None:
    """签发邻池放行签的前提校验。"""
    if target_pond.id == hot_pond.id:
        raise RuleError("热邻池不能是目标池本身")
    if target_pond.plant_id != hot_pond.plant_id:
        raise RuleError("热邻池必须与目标池同厂")
    if target_pond.status != Pond.STATUS_FILLING:
        raise RuleError("目标池当前不是「注水中」，无需签发放行签")
    if hot_pond.status != Pond.STATUS_SLAKING:
        raise RuleError("热邻池当时须为「熟化中」，不能签发")
    if ReleasePass.open_for(target_pond.id) is not None:
        raise RuleError("该目标池已存在一张未核销放行签")


def prepare_enter_slaking(pond: Pond) -> int | None:
    """
    注水池进入「熟化中」前的放行判定（只读，不核销）。

    - 非注水池 / 同厂无热邻：无须持签，返回 None；
    - 有热邻且持未核销签：返回该签 id（调用方须接着用 claim_pass 原子核销）；
    - 有热邻却无签：抛 RuleError。
    """
    if pond.status != Pond.STATUS_FILLING:
        return None
    if not hot_neighbor_ponds(pond):
        return None
    pas = ReleasePass.open_for(pond.id)
    if pas is None:
        raise RuleError(
            "同厂另有熟化中池（热邻），须先持一张未核销的邻池放行签方可进入熟化中"
        )
    return pas.id


def claim_pass(pass_id: int, at=None) -> bool:
    """
    原子核销：仅当签仍为未核销时写入核销时刻。
    返回是否认领成功（并发下抢输的一方得到 False）。
    """
    result = db.session.execute(
        update(ReleasePass)
        .where(ReleasePass.id == pass_id, ReleasePass.redeemed_at.is_(None))
        .values(redeemed_at=at or utcnow())
    )
    return result.rowcount == 1


def apply_pond_status(pond: Pond, new_status: str) -> int | None:
    """
    校验并执行纯池态变更：含出灰温度规则与邻池放行规则。
    核销时刻的写入先于状态落库，且不提交事务（由调用方提交）。
    返回被核销的放行签 id（可能为 None）。
    """
    if new_status not in Pond.STATUS_CHOICES:
        raise RuleError(f"无效状态：{new_status}")
    if new_status == Pond.STATUS_DRAWN:
        ok, msg = can_mark_pond_drawn(pond)
        if not ok:
            raise RuleError(msg)

    redeemed_id = None
    if pond.status == Pond.STATUS_FILLING and new_status == Pond.STATUS_SLAKING:
        pass_id = prepare_enter_slaking(pond)
        if pass_id is not None:
            if not claim_pass(pass_id):
                raise RuleError("放行签已被同时核销，请刷新平面图后重试")
            redeemed_id = pass_id
    pond.status = new_status
    return redeemed_id
