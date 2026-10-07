"""Pinned embedder + reranker wrappers for regulation retrieval (Track C, T3.2).

Both models are small enough for an air-gapped on-prem deploy (T7.2). Weights are
loaded from a local cache dir; once cached, loading is forced offline
(``local_files_only``) so no hub call happens at query time.

Model gates that touch these weights are marked ``@pytest.mark.network`` and run
locally before push; the review chat re-runs only the offline gates.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CACHE_DIR = Path(os.environ.get("COBOL_MODEL_CACHE", ROOT / ".model_cache"))

# Pinned per the work order. Revisions are the exact commit shas resolved from the
# downloaded snapshot (recorded in the relevance-report header) so a re-download is
# byte-identical — the determinism requirement (Gate C) extends to model weights.
EMBEDDER_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDER_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_REVISION = "c5ee24cb16019beea0893ab7796b1df96625c6b8"

# bge-small-en-v1.5 is trained with an asymmetric query instruction for
# retrieval; passages are embedded raw. Applying it lifts query-side recall.
BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _is_cached(model: str, cache_dir: Path) -> bool:
    """True if the model snapshot already lives under the local cache."""
    slug = "models--" + model.replace("/", "--")
    return (cache_dir / slug).exists()


class DenseEmbedder:
    """``BAAI/bge-small-en-v1.5`` bi-encoder, L2-normalised outputs."""

    def __init__(
        self,
        model: str = EMBEDDER_MODEL,
        revision: str = EMBEDDER_REVISION,
        cache_dir: Path = CACHE_DIR,
        device: str = "cpu",
    ) -> None:
        self.model = model
        self.revision = revision
        self.cache_dir = Path(cache_dir)
        self.device = device
        self._st = None

    def _ensure(self):
        if self._st is None:
            from sentence_transformers import SentenceTransformer

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._st = SentenceTransformer(
                self.model,
                revision=self.revision,
                cache_folder=str(self.cache_dir),
                device=self.device,
                local_files_only=_is_cached(self.model, self.cache_dir),
            )
        return self._st

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        st = self._ensure()
        vecs = st.encode(
            list(texts),
            batch_size=64,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return [v.tolist() for v in vecs]

    def encode_passages(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(texts)

    def encode_query(self, query: str) -> list[float]:
        return self._encode([BGE_QUERY_INSTRUCTION + query])[0]


class Reranker:
    """``cross-encoder/ms-marco-MiniLM-L-6-v2`` cross-encoder."""

    def __init__(
        self,
        model: str = RERANKER_MODEL,
        revision: str = RERANKER_REVISION,
        cache_dir: Path = CACHE_DIR,
        device: str = "cpu",
    ) -> None:
        self.model = model
        self.revision = revision
        self.cache_dir = Path(cache_dir)
        self.device = device
        self._ce = None

    def _ensure(self):
        if self._ce is None:
            from sentence_transformers import CrossEncoder

            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._ce = CrossEncoder(
                self.model,
                revision=self.revision,
                cache_folder=str(self.cache_dir),
                device=self.device,
                local_files_only=_is_cached(self.model, self.cache_dir),
            )
        return self._ce

    def score(self, query: str, texts: Sequence[str]) -> list[float]:
        if not texts:
            return []
        ce = self._ensure()
        scores = ce.predict([(query, t) for t in texts], show_progress_bar=False)
        return [float(s) for s in scores]
