"""
Tests for M3 — Hash Chain Utility.

Verifies the verifiable hash chain that ensures audit trail integrity
for locked FSMs and scoreboard entries.

Covers:
  - SHA-256 hashing (bytes, dict, str, determinism)
  - Link creation (genesis, chaining)
  - Chain verification (valid, empty, single)
  - Tamper detection (modified data, broken links, reordering)
  - Chain construction helper (build_chain)
  - JSON serialization roundtrip
  - Large chain handling (1000+ links)
  - Edge cases: wrong genesis previous_hash
"""

from __future__ import annotations

import json

from app.models.scoreboard import HashChain, HashLink
from app.utils.hash_chain import build_chain, compute_hash, link, verify_chain


# ====================================================================
# Hash computation
# ====================================================================


class TestComputeHash:
    """Tests for compute_hash — SHA-256 hashing."""

    def test_bytes(self):
        digest = compute_hash(b"hello world")
        assert len(digest) == 64
        assert all(c in "0123456789abcdef" for c in digest)

    def test_dict(self):
        data = {"broker_id": "B-12345", "status": "compliant"}
        digest = compute_hash(data)
        assert len(digest) == 64

    def test_deterministic(self):
        """Same input must always produce the same hash."""
        data = {"a": 1, "b": 2}
        h1 = compute_hash(data)
        h2 = compute_hash(data)
        assert h1 == h2

    def test_dict_key_order_independent(self):
        """Dicts with different insertion order but same content should match."""
        d1 = {"a": 1, "b": 2}
        d2 = {"b": 2, "a": 1}
        assert compute_hash(d1) == compute_hash(d2)

    def test_invalid_type_raises(self):
        import pytest
        with pytest.raises(TypeError, match="expects bytes, dict, or str"):
            compute_hash(12345)  # type: ignore[arg-type]


# ====================================================================
# Link creation
# ====================================================================


class TestLink:
    """Tests for link — HashLink creation and chaining."""

    def test_genesis(self):
        """Creating a link with previous_link=None produces a genesis link."""
        data = {"fsm_id": "FSM-001", "approved": True}
        genesis = link(None, data)
        assert genesis.index == 0
        assert genesis.previous_hash == "0" * 64
        assert len(genesis.link_hash) == 64
        assert len(genesis.data_hash) == 64

    def test_chain(self):
        """Creating multiple links in sequence produces a valid chain."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        l3 = link(l2, {"step": 3})

        assert g.index == 0
        assert l2.index == 1
        assert l3.index == 2
        assert l2.previous_hash == g.link_hash
        assert l3.previous_hash == l2.link_hash


# ====================================================================
# Chain verification
# ====================================================================


class TestVerifyChain:
    """Tests for verify_chain — integrity validation."""

    def test_valid_chain(self):
        """A properly constructed chain must verify as valid."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        l3 = link(l2, {"step": 3})
        chain = [g, l2, l3]
        assert verify_chain(chain) is True

    def test_empty_chain(self):
        """An empty chain is vacuously valid."""
        assert verify_chain([]) is True

    def test_single_link(self):
        """A single-link chain should verify."""
        g = link(None, {"step": 1})
        assert verify_chain([g]) is True

    def test_tampered_data(self):
        """Tampering with a link's data_hash must be detected."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})

        tampered = HashLink(
            index=l2.index,
            data_hash="f" * 64,  # changed!
            previous_hash=l2.previous_hash,
            link_hash=l2.link_hash,
        )
        assert verify_chain([g, tampered]) is False

    def test_broken_link(self):
        """A link whose previous_hash doesn't match must be detected."""
        g = link(None, {"step": 1})
        l2_broken = HashLink(
            index=1,
            data_hash="a" * 64,
            previous_hash="0" * 64,  # should be g.link_hash, not genesis
            link_hash="b" * 64,       # will mismatch when recomputed
        )
        assert verify_chain([g, l2_broken]) is False

    def test_reordered(self):
        """Reordered links must be detected via index check."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        # Swap order
        assert verify_chain([l2, g]) is False

    def test_accepts_hash_chain_object(self):
        """verify_chain should accept a HashChain object."""
        g = link(None, {"step": 1})
        l2 = link(g, {"step": 2})
        chain_obj = HashChain(root_hash=g.link_hash, chain=[g, l2])
        assert verify_chain(chain_obj) is True

    def test_wrong_genesis_previous(self):
        """First link must have previous_hash = 64 zeros."""
        bad_genesis = HashLink(
            index=0,
            data_hash="a" * 64,
            previous_hash="b" * 64,  # not genesis anchor
            link_hash="c" * 64,
        )
        assert verify_chain([bad_genesis]) is False

    def test_1000_plus_links(self):
        """Chain with 1000+ links must verify correctly and detect tampering."""
        # Build a large chain
        data_items = [{"index": i, "payload": f"data_{i}"} for i in range(1001)]
        chain = build_chain(data_items)

        assert chain.length == 1001
        assert verify_chain(chain) is True

        # Verify ordering preserved
        for i, link in enumerate(chain.chain):
            assert link.index == i

        # Tamper detection still works on large chains
        middle_link = chain.chain[500]
        tampered = HashLink(
            index=middle_link.index,
            data_hash="f" * 64,
            previous_hash=middle_link.previous_hash,
            link_hash=middle_link.link_hash,
        )
        chain.chain[500] = tampered
        assert verify_chain(chain) is False


# ====================================================================
# Chain construction
# ====================================================================


class TestBuildChain:
    """Tests for build_chain — bulk chain construction."""

    def test_build(self):
        """build_chain helper should produce a valid chain."""
        data_items = [{"broker": "B-1"}, {"broker": "B-2"}, {"broker": "B-3"}]
        chain = build_chain(data_items)
        assert chain.length == 3
        assert verify_chain(chain) is True

    def test_empty(self):
        """build_chain with no data should produce an empty chain."""
        chain = build_chain([])
        assert chain.length == 0
        assert verify_chain(chain) is True


# ====================================================================
# JSON serialization roundtrip
# ====================================================================


class TestJsonRoundtrip:
    """Tests for HashChain JSON serialization and deserialization."""

    def test_roundtrip(self):
        """HashChain → model_dump_json → model_validate_json → verify_chain == True."""
        data_items = [
            {"broker_id": "B-12345", "fsm_ref": "FSM-001", "approved": True},
            {"broker_id": "B-12345", "fsm_ref": "FSM-002", "approved": True},
            {"broker_id": "B-67890", "fsm_ref": "FSM-003", "approved": False},
        ]
        original = build_chain(data_items)
        assert verify_chain(original) is True

        # Serialize
        json_str = original.model_dump_json(indent=2)
        assert isinstance(json_str, str)
        assert len(json_str) > 0

        # Deserialize
        rehydrated = HashChain.model_validate_json(json_str)
        assert rehydrated.length == original.length
        assert rehydrated.root_hash == original.root_hash
        assert verify_chain(rehydrated) is True

        # Verify individual links survived roundtrip
        for i, (orig_link, rehyd_link) in enumerate(zip(original.chain, rehydrated.chain)):
            assert rehyd_link.index == orig_link.index
            assert rehyd_link.data_hash == orig_link.data_hash
            assert rehyd_link.previous_hash == orig_link.previous_hash
            assert rehyd_link.link_hash == orig_link.link_hash

    def test_roundtrip_empty_chain(self):
        """Empty chain should survive serialization roundtrip."""
        original = build_chain([])
        json_str = original.model_dump_json()
        rehydrated = HashChain.model_validate_json(json_str)
        assert rehydrated.length == 0
        assert verify_chain(rehydrated) is True
