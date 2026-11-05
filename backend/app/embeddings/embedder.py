"""Production local embedder implementation using Google EmbeddingGemma 2."""

import logging
from typing import List, Optional

from app.embeddings.base import BaseEmbedder
from app.embeddings.configuration import EmbeddingConfig
from app.embeddings.exceptions import (
    DimensionMismatchError,
    InferenceError,
)
from app.embeddings.model_manager import EmbeddingModelManager
from app.embeddings.prompts import format_document_prompt, format_query_prompt

logger = logging.getLogger(__name__)


class EmbeddingGemmaEmbedder(BaseEmbedder):
    """Local embedding generator using EmbeddingGemma 2 and PyTorch/Transformers."""

    def __init__(
        self,
        config: Optional[EmbeddingConfig] = None,
        model_manager: Optional[EmbeddingModelManager] = None,
    ) -> None:
        self.config = config or EmbeddingConfig()
        self.config.validate_dimension()
        self.manager = model_manager or EmbeddingModelManager.get_instance()

    @property
    def dimension(self) -> int:
        return self.config.dimension

    @property
    def model_id(self) -> str:
        return self.config.model_id

    @property
    def is_loaded(self) -> bool:
        return self.manager.is_loaded

    def unload(self) -> None:
        self.manager.unload()

    def embed_query(self, query: str) -> List[float]:
        """Generate a normalized embedding vector for a user search query."""
        formatted_prompt = format_query_prompt(query)
        embeddings = self._generate_embeddings([formatted_prompt])
        return embeddings[0]

    def embed_documents(
        self,
        documents: List[str],
        titles: Optional[List[Optional[str]]] = None,
    ) -> List[List[float]]:
        """Generate normalized embedding vectors for a batch of document chunks."""
        if not documents:
            return []

        formatted_prompts: List[str] = []
        for i, text in enumerate(documents):
            title = titles[i] if titles and i < len(titles) else None
            formatted_prompts.append(format_document_prompt(text, title))

        return self._generate_embeddings(formatted_prompts)

    def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Batch-process formatted text prompts through the model and mean pool."""
        if not texts:
            return []

        try:
            import torch
        except ImportError as e:
            raise InferenceError(f"PyTorch is required for embedding inference: {e}") from e

        tokenizer, model = self.manager.get_model_and_tokenizer(self.config)
        device = torch.device(self.config.device)
        batch_size = self.config.batch_size
        results: List[List[float]] = []

        try:
            for start_idx in range(0, len(texts), batch_size):
                batch_texts = texts[start_idx : start_idx + batch_size]

                encoded = tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=self.config.max_sequence_length,
                    return_tensors="pt",
                )
                encoded = {k: v.to(device) for k, v in encoded.items()}

                with torch.no_grad():
                    outputs = model(**encoded)
                    # Last hidden state: (batch_size, seq_len, hidden_dim)
                    last_hidden = outputs.last_hidden_state
                    attention_mask = encoded["attention_mask"].unsqueeze(-1)  # (batch_size, seq_len, 1)

                    # Attention-weighted mean pooling
                    sum_embeddings = torch.sum(last_hidden * attention_mask, dim=1)
                    sum_mask = torch.clamp(attention_mask.sum(dim=1), min=1e-9)
                    pooled = sum_embeddings / sum_mask

                    # Matryoshka dimension truncation if configured dimension < native dimension
                    if self.config.dimension < pooled.shape[-1]:
                        pooled = pooled[:, : self.config.dimension]
                    elif self.config.dimension > pooled.shape[-1]:
                        raise DimensionMismatchError(
                            f"Model output dimension ({pooled.shape[-1]}) is smaller than "
                            f"configured target dimension ({self.config.dimension})."
                        )

                    # L2 Normalization
                    normalized = torch.nn.functional.normalize(pooled, p=2, dim=1)
                    batch_results = normalized.cpu().tolist()
                    results.extend(batch_results)

            return results
        except Exception as e:
            if isinstance(e, DimensionMismatchError):
                raise
            raise InferenceError(f"Inference computation failed: {e}") from e

