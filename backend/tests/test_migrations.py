"""Exercise clean installs and legacy paper-ledger upgrades on isolated SQLite files."""

from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _alembic(database_url: str, revision: str) -> subprocess.CompletedProcess[str]:
    environment = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "backend/alembic.ini", "upgrade", revision],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_legacy_paper_records_upgrade_to_multi_market_schema(tmp_path):
    database_path = tmp_path / "legacy-upgrade.db"
    database_url = f"sqlite:///{database_path.as_posix()}"

    initial = _alembic(database_url, "51c892a239bf")
    assert initial.returncode == 0, f"Legacy schema creation failed: {initial.stderr}"

    now = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            ("user-1", "migration@example.test", "test-hash", now),
        )
        connection.execute(
            "INSERT INTO virtual_portfolios (id, user_id, starting_cash, cash, created_at) VALUES (?, ?, ?, ?, ?)",
            ("portfolio-1", "user-1", 100000, 9975.32, now),
        )
        connection.execute(
            "INSERT INTO virtual_positions (id, portfolio_id, symbol, quantity, average_entry) VALUES (?, ?, ?, ?, ?)",
            ("position-1", "portfolio-1", "NIFTYBEES", 2, 10.5),
        )
        connection.execute(
            """INSERT INTO simulated_orders (
                id, portfolio_id, idempotency_key, request_fingerprint, symbol, side, quantity,
                quote_price, fill_price, fees, slippage, realized_pnl, status, mode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("order-1", "portfolio-1", "legacy-order", "a" * 64, "NIFTYBEES", "buy", 2,
             12.3, 12.34, 0.02, 0.04, 0, "filled", "simulation", now),
        )

    upgraded = _alembic(database_url, "head")
    assert upgraded.returncode == 0, f"Legacy data upgrade failed: {upgraded.stderr}"

    with sqlite3.connect(database_path) as connection:
        position = connection.execute(
            "SELECT market_type, quote_currency, average_entry_inr FROM virtual_positions WHERE id = ?",
            ("position-1",),
        ).fetchone()
        order = connection.execute(
            "SELECT market_type, quote_currency, value_inr, source_provider, price_basis FROM simulated_orders WHERE id = ?",
            ("order-1",),
        ).fetchone()
        watchlist_exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'market_watchlist'"
        ).fetchone()
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()

    assert position == ("EQUITY", "INR", 10.5)
    assert order == ("EQUITY", "INR", 24.68, "synthetic-demo", "synthetic demo value")
    assert watchlist_exists == ("market_watchlist",)
    assert revision == ("c03abc12cf5e",)
