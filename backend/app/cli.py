"""
CLI for RAG operations — V2 M1.

Usage::

    python -m app.cli index --pdf-path data/circulars/master.pdf --circular-ref "SEBI/HO/..."
    python -m app.cli search --query "margin collection deadline" --top-k 5
    python -m app.cli stats --circular-ref "SEBI/HO/..."
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure the backend package is importable when run as a module.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s %(message)s",
)
logger = logging.getLogger("cli")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agentic-compliance",
        description="Agentic Compliance — RAG CLI (V2 M1)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # index
    idx = sub.add_parser("index", help="Index a circular PDF into the RAG store")
    idx.add_argument("--pdf-path", required=True, help="Path to circular PDF")
    idx.add_argument("--circular-ref", required=True, help="SEBI circular reference")

    # search
    srch = sub.add_parser("search", help="Semantic search across indexed circulars")
    srch.add_argument("--query", required=True, help="Natural language query")
    srch.add_argument("--top-k", type=int, default=10, help="Max results (default 10)")
    srch.add_argument("--circular-ref", default=None, help="Filter to circular")

    # stats
    st = sub.add_parser("stats", help="Show index statistics")
    st.add_argument("--circular-ref", default=None, help="Filter to circular (omit for all)")

    # list (V2 M2)
    ls = sub.add_parser("list", help="List all indexed circulars")

    # index-all (V2 M2)
    ia = sub.add_parser("index-all", help="Index all PDFs in data/circulars/")
    ia.add_argument("--directory", default="data/circulars", help="Directory to scan for PDFs")

    # delete (V2 M2)
    dl = sub.add_parser("delete", help="Remove a circular from the index")
    dl.add_argument("--circular-ref", required=True, help="SEBI circular reference")

    return parser


def _handle_index(args: argparse.Namespace) -> None:
    """Index a circular PDF."""
    from app.rag.chunker import DocumentChunker
    from app.rag.config import load_rag_config
    from app.rag.embedder import LocalEmbedder
    from app.rag.vector_store import ChromaVectorStore

    config = load_rag_config()

    print(f"Indexing: {args.pdf_path}")
    print(f"Reference: {args.circular_ref}")

    # Chunk
    chunker = DocumentChunker(config)
    chunks = chunker.chunk_pdf(args.pdf_path, args.circular_ref)
    print(f"  Chunks created: {len(chunks)}")

    if not chunks:
        print("  ERROR: No chunks produced.")
        return

    # Embed
    embedder = LocalEmbedder(config)
    texts = [c.text for c in chunks]
    print(f"  Generating embeddings for {len(texts)} chunks...")
    embeddings = embedder._encode_sync(texts)
    print(f"  Embeddings: {len(embeddings)} vectors, dim={embedder.dimension}")

    # Store in Chroma (embeddings)
    store = ChromaVectorStore(config)
    count = store.add_chunks(chunks, embeddings)
    print(f"  Indexed: {count} chunks in Chroma")

    # Store in PostgreSQL (text + metadata)
    _cli_save_chunks_to_pg(chunks)

    print(f"  Total collection size: {store.count()}")
    print("Done.")


async def _handle_search(args: argparse.Namespace) -> None:
    """Semantic search."""
    from app.rag.config import load_rag_config
    from app.rag.retrieval import RetrievalPipeline

    config = load_rag_config()
    pipeline = RetrievalPipeline(config)

    results = await pipeline.search(
        query=args.query,
        top_k=args.top_k,
        circular_ref=args.circular_ref,
    )

    print(f"Query: {args.query}")
    print(f"Results: {len(results)}")
    for i, r in enumerate(results):
        print(f"  [{i+1}] score={r.score:.4f}  section={r.metadata.get('section_path','?')}")
        print(f"       {r.text[:200]}...")


def _handle_stats(args: argparse.Namespace) -> None:
    """Show index statistics."""
    from app.rag.config import load_rag_config
    from app.rag.vector_store import ChromaVectorStore

    config = load_rag_config()
    store = ChromaVectorStore(config)

    print(f"Collection: {config.vector_store.chroma.collection_name}")
    print(f"Total chunks: {store.count()}")

    if args.circular_ref:
        count = store.count_by_circular(args.circular_ref)
        print(f"  {args.circular_ref}: {count} chunks")
    else:
        # Show all circulars (scan by known refs or just total)
        print("  (use --circular-ref for per-circular breakdown)")


def _handle_list(args: argparse.Namespace) -> None:
    """List all indexed circulars."""
    from app.rag.circular_registry import get_registry
    from app.rag.vector_store import ChromaVectorStore
    from app.rag.config import load_rag_config

    config = load_rag_config()
    store = ChromaVectorStore(config)
    registry = get_registry()

    # Merge both sources
    all_refs: set[str] = set()
    all_refs.update(r.circular_ref for r in registry.list_all())
    all_refs.update(store.list_circulars())

    if not all_refs:
        print("No circulars indexed.")
        return

    print(f"{'Circular Ref':<55} {'Chunks':>7}  {'Indexed':>8}  Title")
    print("-" * 110)
    for ref in sorted(all_refs):
        rec = registry.get(ref)
        store_count = store.count_by_circular(ref)
        title = rec.title if rec and rec.title else "-"
        chunk_count = rec.chunk_count if rec else store_count
        indexed = "Yes" if store_count > 0 else "No"
        print(f"{ref:<55} {chunk_count:>7}  {indexed:>8}  {title}")


def _handle_index_all(args: argparse.Namespace) -> None:
    """Index all PDFs in the specified directory."""
    from pathlib import Path
    from app.rag.circular_registry import get_registry, build_record
    from app.rag.chunker import DocumentChunker
    from app.rag.config import load_rag_config
    from app.rag.embedder import LocalEmbedder
    from app.rag.vector_store import ChromaVectorStore

    config = load_rag_config()
    registry = get_registry()
    scan_dir = Path(args.directory)

    entries: list[tuple[str, str]] = []  # (pdf_path, circular_ref)

    # First pass: registry entries whose PDFs exist
    for rec in registry.list_all():
        pdf_path = Path(rec.pdf_path)
        if not pdf_path.exists():
            pdf_path = scan_dir / pdf_path.name
        if pdf_path.exists():
            entries.append((str(pdf_path), rec.circular_ref))
        else:
            print(f"SKIP: {rec.circular_ref} — PDF not found at {pdf_path}")

    # Second pass: scan directory for PDFs not in registry
    if not entries and scan_dir.exists():
        from app.api.routes.rag import _derive_circular_ref
        indexed_refs = {e[1] for e in entries}
        for pdf_path in sorted(scan_dir.glob("*.pdf")):
            ref = _derive_circular_ref(pdf_path)
            if ref not in indexed_refs:
                entries.append((str(pdf_path), ref))

    if not entries:
        print("No PDFs found to index.")
        return

    print(f"Indexing {len(entries)} circular(s)...")
    store = ChromaVectorStore(config)
    embedder = LocalEmbedder(config)
    chunker = DocumentChunker(config)

    for pdf_path, ref in entries:
        print(f"  {ref}")
        try:
            chunks = chunker.chunk_pdf(pdf_path, ref)
            if not chunks:
                print(f"    WARNING: No chunks produced")
                continue

            texts = [c.text for c in chunks]
            embeddings = embedder._encode_sync(texts)
            store.add_chunks(chunks, embeddings)

            # Dual-write to PostgreSQL
            _cli_save_chunks_to_pg(chunks)

            total_chars = sum(c.metadata.char_count for c in chunks)
            record = build_record(
                circular_ref=ref,
                pdf_path=pdf_path,
                chunk_count=len(chunks),
                char_count=total_chars,
            )
            registry.register(record)
            print(f"    OK: {len(chunks)} chunks, {total_chars} chars, "
                  f"hash={record.document_hash[:12]}...")
        except Exception as exc:
            print(f"    ERROR: {exc}")

    print(f"Done. Total collection size: {store.count()}")


def _handle_delete(args: argparse.Namespace) -> None:
    """Remove a circular from the index and registry."""
    from app.rag.circular_registry import get_registry
    from app.rag.vector_store import ChromaVectorStore
    from app.rag.config import load_rag_config

    config = load_rag_config()
    store = ChromaVectorStore(config)
    registry = get_registry()

    ref = args.circular_ref
    store_count = store.count_by_circular(ref)
    reg_record = registry.get(ref)

    if store_count == 0 and reg_record is None:
        print(f"Circular '{ref}' not found.")
        return

    deleted = store.delete_circular(ref) if store_count > 0 else 0
    deregistered = registry.deregister(ref) if reg_record else False

    print(f"Removed '{ref}': {deleted} chunks deleted, "
          f"{'deregistered' if deregistered else 'not in registry'}")


# =============================================================================
# PG helper (V2 M4)
# =============================================================================


def _cli_save_chunks_to_pg(chunks) -> None:
    """Save chunk text and metadata to PostgreSQL.

    Graceful fallback — if PG is unavailable, chunks are still in Chroma.
    """
    try:
        import asyncio
        from app.database import AsyncSessionLocal
        from app.db.repos.rag_chunk_repo import RagChunkRepo

        async def _save():
            async with AsyncSessionLocal() as session:
                repo = RagChunkRepo(session)
                await repo.save_batch(list(chunks))
                await session.commit()

        asyncio.run(_save())
        print(f"    PG: {len(chunks)} chunk(s) saved to rag_chunks")
    except Exception:
        print("    PG: unavailable — chunks stored in Chroma only")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "index":
        _handle_index(args)
    elif args.command == "search":
        asyncio.run(_handle_search(args))
    elif args.command == "stats":
        _handle_stats(args)
    elif args.command == "list":
        _handle_list(args)
    elif args.command == "index-all":
        _handle_index_all(args)
    elif args.command == "delete":
        _handle_delete(args)


if __name__ == "__main__":
    main()
