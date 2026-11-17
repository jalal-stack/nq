from pydantic import BaseModel


class ProposalIn(BaseModel):
    symbol: str
    side: str
    entry_price: float
    stop_loss: float
