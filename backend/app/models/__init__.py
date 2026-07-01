"""FVpn SQLAlchemy Models"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer,
    String, Text, JSON, func, BigInteger
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def gen_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id:               Mapped[int]             = mapped_column(Integer, primary_key=True, index=True)
    uuid:             Mapped[str]             = mapped_column(String(36), default=gen_uuid, unique=True)
    username:         Mapped[str]             = mapped_column(String(64), unique=True, index=True)
    email:            Mapped[Optional[str]]   = mapped_column(String(255), nullable=True)
    hashed_password:  Mapped[str]             = mapped_column(String(255))
    is_admin:         Mapped[bool]            = mapped_column(Boolean, default=False)
    is_active:        Mapped[bool]            = mapped_column(Boolean, default=True)
    traffic_limit_gb: Mapped[float]           = mapped_column(Float, default=0.0)
    traffic_used_gb:  Mapped[float]           = mapped_column(Float, default=0.0)
    expire_at:        Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at:       Mapped[datetime]        = mapped_column(DateTime, default=func.now())

    subscriptions: Mapped[list["Subscription"]] = relationship("Subscription", back_populates="user")

    @property
    def is_expired(self) -> bool:
        if self.expire_at is None:
            return False
        return datetime.utcnow() > self.expire_at

    @property
    def traffic_remaining_gb(self) -> Optional[float]:
        """None for unlimited (traffic_limit_gb==0) — float('inf') is not valid JSON."""
        if self.traffic_limit_gb == 0:
            return None
        return max(0.0, self.traffic_limit_gb - self.traffic_used_gb)


class Node(Base):
    __tablename__ = "nodes"

    id:          Mapped[int]             = mapped_column(Integer, primary_key=True)
    name:        Mapped[str]             = mapped_column(String(128))
    host:        Mapped[str]             = mapped_column(String(255))
    ssh_port:    Mapped[int]             = mapped_column(Integer, default=22)
    ssh_user:    Mapped[str]             = mapped_column(String(64), default="root")
    ssh_key:     Mapped[Optional[str]]   = mapped_column(Text, nullable=True)
    group:       Mapped[Optional[str]]   = mapped_column(String(64), nullable=True)
    status:      Mapped[str]             = mapped_column(String(32), default="unknown")
    latency_ms:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    traffic_in:  Mapped[int]             = mapped_column(BigInteger, default=0)
    traffic_out: Mapped[int]             = mapped_column(BigInteger, default=0)
    is_active:   Mapped[bool]            = mapped_column(Boolean, default=True)
    last_check:  Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at:  Mapped[datetime]        = mapped_column(DateTime, default=func.now())
    meta:        Mapped[Optional[dict]]  = mapped_column(JSON, nullable=True)

    protocols: Mapped[list["Protocol"]] = relationship("Protocol", back_populates="node")


class Protocol(Base):
    __tablename__ = "protocols"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True)
    node_id:    Mapped[int]  = mapped_column(ForeignKey("nodes.id", ondelete="CASCADE"))
    name:       Mapped[str]  = mapped_column(String(64))
    port:       Mapped[int]  = mapped_column(Integer)
    is_active:  Mapped[bool] = mapped_column(Boolean, default=True)
    config:     Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    node: Mapped["Node"] = relationship("Node", back_populates="protocols")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id:         Mapped[int]  = mapped_column(Integer, primary_key=True)
    user_id:    Mapped[int]  = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token:      Mapped[str]  = mapped_column(String(64), unique=True, default=lambda: uuid.uuid4().hex)
    format:     Mapped[str]  = mapped_column(String(32))
    last_fetch: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="subscriptions")


class EventLog(Base):
    __tablename__ = "event_logs"

    id:         Mapped[int]          = mapped_column(Integer, primary_key=True)
    level:      Mapped[str]          = mapped_column(String(16))
    source:     Mapped[str]          = mapped_column(String(64))
    message:    Mapped[str]          = mapped_column(Text)
    meta:       Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime]     = mapped_column(DateTime, default=func.now())
