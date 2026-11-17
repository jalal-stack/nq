-- Initial schema
CREATE TABLE IF NOT EXISTS proposals (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(32) NOT NULL,
    side VARCHAR(4) NOT NULL CHECK (side IN ('BUY', 'SELL')),
    entry_price DOUBLE PRECISION NOT NULL,
    stop_loss NUMERIC(18, 8),
    created_at TIMESTAMP DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_orders (
    id SERIAL PRIMARY KEY,
    proposal_id INTEGER REFERENCES proposals(id),
    status VARCHAR(16) CHECK (status IN ('open', 'filled', 'cancelled')),
    quantity NUMERIC(18, 8),
    filled_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id SERIAL PRIMARY KEY,
    equity REAL NOT NULL,
    ts TIMESTAMP WITH TIME ZONE NOT NULL
);
