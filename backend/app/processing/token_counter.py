"""Token counting abstraction and deterministic approximation for document chunking."""

from abc import ABC, abstractmethod
import re

# Regex matching words, numbers, punctuation symbols, and non-whitespace sequences
_TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)


class BaseTokenCounter(ABC):
    """Abstract interface for token counters.

    Allows seamless transition from heuristic/approximate counting in Phase 3
    to exact model-specific tokenizers (e.g. Google EmbeddingGemma 2) in Phase 5.
    """

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Calculate the estimated or exact number of tokens in text.

        Args:
            text: Input string to evaluate.

        Returns:
            Non-negative integer token count.
        """
        raise NotImplementedError


class ApproximateTokenCounter(BaseTokenCounter):
    """Deterministic token estimator for text chunking before embedding model integration.

    Design Note:
        Modern BPE / SentencePiece tokenizers (such as those in Gemma and EmbeddingGemma)
        typically produce ~1.25 to 1.35 tokens per English word, or ~3.8 to 4 characters
        per token for natural language. Punctuation, camelCase code identifiers, and numbers
        split into multiple subwords. This counter splits tokens deterministically and applies
        subword expansion heuristics to closely approximate modern LLM token bounds.
    """

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0

        # Match lexical words, numbers, and punctuation marks
        tokens = _TOKEN_PATTERN.findall(text)
        if not tokens:
            return 0

        total_tokens = 0
        for token in tokens:
            length = len(token)
            if length <= 4:
                total_tokens += 1
            elif length <= 8:
                total_tokens += 2
            elif length <= 12:
                total_tokens += 3
            else:
                # Long identifier or compound word (1 token per ~4 chars)
                total_tokens += (length + 3) // 4

        return max(1, total_tokens)


_default_counter = ApproximateTokenCounter()


def get_default_token_counter() -> BaseTokenCounter:
    """Return the global default token counter instance."""
    return _default_counter
