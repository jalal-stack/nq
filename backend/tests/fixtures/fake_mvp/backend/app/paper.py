import ccxt


class PaperExecutor:
    def execute(self, proposal):
        return {"filled": True}


def _unused_live_path(exchange: "ccxt.Exchange", symbol: str, qty: float):
    return exchange.create_order(symbol, "market", "buy", qty)
