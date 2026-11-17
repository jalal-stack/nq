import enum

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Side(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"


class Proposal(Base):
    __tablename__ = "proposals"
    id = Column(Integer, primary_key=True)
    symbol = Column(String(32), nullable=False)
    side = Column(Enum(Side), nullable=False)
    entry_price = Column(Float, nullable=False)
    stop_loss = Column(Numeric(18, 8))
    created_at = Column(DateTime)


class PaperOrder(Base):
    __tablename__ = "paper_orders"
    id = Column(Integer, primary_key=True)
    proposal_id = Column(Integer, ForeignKey("proposals.id"))
    status = Column(Enum("open", "filled", "cancelled", name="order_status"))
    quantity = Column(Numeric(18, 8))
    filled_at = Column(DateTime(timezone=True))
