"""Lightweight performance guardrails (mocked DB, no network)."""

import time
from unittest.mock import MagicMock

from app.services.pitch_reels.service import PitchReelService


def test_upsert_reel_mocked_completes_quickly():
    select_chain = MagicMock()
    select_chain.select.return_value = select_chain
    select_chain.eq.return_value = select_chain
    select_chain.limit.return_value = select_chain
    select_chain.execute.return_value = MagicMock(data=[])

    insert_chain = MagicMock()
    insert_tail = MagicMock()
    insert_chain.insert.return_value = insert_tail
    insert_tail.execute.return_value = MagicMock()

    n = {"c": 0}

    def table_side_effect(name):
        n["c"] += 1
        return select_chain if n["c"] == 1 else insert_chain

    db = MagicMock()
    db.table.side_effect = table_side_effect
    svc = PitchReelService(db)

    t0 = time.perf_counter()
    for _ in range(50):
        n["c"] = 0
        db.table.side_effect = table_side_effect
        svc.upsert_reel_for_published_idea(
            "550e8400-e29b-41d4-a716-446655440000",
            "owner",
            "T",
            "D",
        )
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"50 upserts took {elapsed:.3f}s"
