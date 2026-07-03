"""
Hash chain utility.

Provides a verifiable hash chain for locking FSM snapshots and ensuring
audit trail integrity throughout the compliance pipeline.

M0 delivers the interface (data structures + function signatures).
Full implementation is in M3.

Design:
  - SHA-256 for all hashing
  - Linked list: each HashLink stores (index, timestamp, data_hash, previous_hash, link_hash)
  - Genesis link has previous_hash = 64 zero-characters
  - verify_chain checks every link and detects: tampered data, broken links, reordered links
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.models.scoreboard import HashChain, HashLink

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENESIS_PREVIOUS_HASH: str = "0" * 64  # 64 zeros — genesis link's "previous" anchor


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------


def _serialize(data: Any) -> bytes:
    """Serialize any JSON-serializable data to canonical UTF-8 bytes.

    Uses sorted keys for deterministic output — critical for hash consistency.
    """
    return json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------


def compute_hash(data: bytes | dict[str, Any] | str) -> str:
    """Compute the SHA-256 hash of the input.

    Accepts raw bytes, a dict (serialized with sorted keys), or a hex string.
    Returns a 64-character lowercase hex digest.

    Args:
        data: Bytes to hash, a dict to serialize-and-hash, or a pre-existing hex string.

    Returns:
        64-character SHA-256 hex digest.

    Raises:
        TypeError: If data is not bytes, dict, or str.
    """
    if isinstance(data, dict):
        data = _serialize(data)
    elif isinstance(data, str):
        data = data.encode("utf-8")
    elif not isinstance(data, bytes):
        raise TypeError(f"compute_hash expects bytes, dict, or str; got {type(data).__name__}")

    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Link creation
# ---------------------------------------------------------------------------


def link(previous_link: HashLink | None, data: dict[str, Any]) -> HashLink:
    """Create the next link in the hash chain.

    If previous_link is None, creates the genesis link (index 0) with
    previous_hash set to 64 zeros.

    Args:
        previous_link: The preceding HashLink, or None for genesis.
        data: The data payload to seal into this link.

    Returns:
        A new HashLink chained to the previous one.

    Raises:
        TypeError: If data cannot be serialized.
    """
    index = 0 if previous_link is None else previous_link.index + 1
    prev_hash = GENESIS_PREVIOUS_HASH if previous_link is None else previous_link.link_hash
    data_hash = compute_hash(data)

    # Link hash = hash(index || data_hash || previous_hash)
    link_payload = f"{index}{data_hash}{prev_hash}".encode("utf-8")
    link_hash = compute_hash(link_payload)

    return HashLink(
        index=index,
        data_hash=data_hash,
        previous_hash=prev_hash,
        link_hash=link_hash,
    )


# ---------------------------------------------------------------------------
# Chain verification
# ---------------------------------------------------------------------------


def verify_chain(chain: HashChain | list[HashLink]) -> bool:
    """Verify the integrity of a hash chain.

    Checks that:
      1. The first link's previous_hash is the genesis anchor (64 zeros).
      2. Each subsequent link's previous_hash matches the preceding link's link_hash.
      3. Each link's link_hash correctly recomputes from its fields.
      4. Indices are sequential (0, 1, 2, …).

    Args:
        chain: A HashChain object or a list of HashLinks.

    Returns:
        True if the chain is intact, False if tampering is detected.

    Note:
        An empty chain is considered valid (vacuously true).
    """
    links: list[HashLink]
    if isinstance(chain, HashChain):
        links = chain.chain
    else:
        links = chain

    if not links:
        return True  # Empty chain is valid

    # Verify first link is genesis or follows genesis correctly
    if links[0].index != 0:
        return False

    if links[0].previous_hash != GENESIS_PREVIOUS_HASH:
        return False

    # Verify each link
    for i, link in enumerate(links):
        # Index must be sequential
        if link.index != i:
            return False

        # Recompute link_hash from its components
        expected_preimage = f"{link.index}{link.data_hash}{link.previous_hash}".encode("utf-8")
        expected_link_hash = compute_hash(expected_preimage)

        if link.link_hash != expected_link_hash:
            return False

        # For non-genesis links: previous_hash must match the prior link's link_hash
        if i > 0:
            if link.previous_hash != links[i - 1].link_hash:
                return False

    return True


# ---------------------------------------------------------------------------
# Chain construction helper
# ---------------------------------------------------------------------------


def build_chain(data_items: list[dict[str, Any]]) -> HashChain:
    """Build a complete HashChain from a list of data payloads.

    Each payload becomes one HashLink, chained in order.

    Args:
        data_items: Ordered list of data payloads to seal into the chain.

    Returns:
        A HashChain with one link per data item. Empty list → empty chain.
    """
    links: list[HashLink] = []
    previous: HashLink | None = None

    for item in data_items:
        new_link = link(previous, item)
        links.append(new_link)
        previous = new_link

    root_hash = links[0].link_hash if links else GENESIS_PREVIOUS_HASH

    return HashChain(root_hash=root_hash, chain=links)
