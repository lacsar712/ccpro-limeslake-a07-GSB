from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="worker")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class Plant(db.Model):
    __tablename__ = "plants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    location = db.Column(db.String(200), nullable=False, default="")
    notes = db.Column(db.Text, nullable=False, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow)

    ponds = db.relationship("Pond", back_populates="plant", cascade="all, delete-orphan")


class Pond(db.Model):
    __tablename__ = "ponds"
    __table_args__ = (
        db.UniqueConstraint("plant_id", "code", name="uq_pond_code_per_plant"),
    )

    STATUS_FILLING = "filling"
    STATUS_SLAKING = "slaking"
    STATUS_DRAWN = "drawn"
    STATUS_CHOICES = (STATUS_FILLING, STATUS_SLAKING, STATUS_DRAWN)

    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False)
    code = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_FILLING)
    capacity_m3 = db.Column(db.Float, nullable=False, default=0.0)
    notes = db.Column(db.Text, nullable=False, default="")
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    plant = db.relationship("Plant", back_populates="ponds")
    batches = db.relationship(
        "SlakeBatch",
        back_populates="pond",
        cascade="all, delete-orphan",
    )


class SlakeBatch(db.Model):
    __tablename__ = "slake_batches"

    id = db.Column(db.Integer, primary_key=True)
    pond_id = db.Column(db.Integer, db.ForeignKey("ponds.id"), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    target_temp_c = db.Column(db.Float, nullable=False, default=80.0)
    peak_temp_c = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=False, default="")

    pond = db.relationship("Pond", back_populates="batches")


class NeighborClearance(db.Model):
    """邻池放行签：同厂已有熟化中池时，注水中池转入熟化中的通行凭证。

    未核销签对同一目标池至多一张，由部分唯一索引在数据库层兜底（并发双签只落一张）。
    """

    __tablename__ = "neighbor_clearances"
    __table_args__ = (
        db.Index(
            "uq_neighbor_clearance_open_target",
            "target_pond_id",
            unique=True,
            postgresql_where=db.text("consumed_at IS NULL"),
            sqlite_where=db.text("consumed_at IS NULL"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    target_pond_id = db.Column(db.Integer, db.ForeignKey("ponds.id"), nullable=False)
    neighbor_pond_id = db.Column(db.Integer, db.ForeignKey("ponds.id"), nullable=False)
    issued_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    issued_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    target_pond = db.relationship("Pond", foreign_keys=[target_pond_id])
    neighbor_pond = db.relationship("Pond", foreign_keys=[neighbor_pond_id])
    issuer = db.relationship("User", foreign_keys=[issued_by_id])
