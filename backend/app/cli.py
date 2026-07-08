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

    # Store
    store = ChromaVectorStore(config)
    count = store.add_chunks(chunks, embeddings)
    print(f"  Indexed: {count} chunks in Chroma")
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


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "index":
        _handle_index(args)
    elif args.command == "search":
        asyncio.run(_handle_search(args))
    elif args.command == "stats":
        _handle_stats(args)


if __name__ == "__main__":
    main()
