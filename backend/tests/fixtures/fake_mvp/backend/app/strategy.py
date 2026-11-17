import pandas as pd


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n).mean()


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    d = s.diff()
    return 100 - 100 / (1 + d.clip(lower=0).rolling(n).mean() / (-d.clip(upper=0)).rolling(n).mean())


def generate_signal(df):
    return "buy" if ema(df.close, 20).iloc[-1] > ema(df.close, 50).iloc[-1] else None
