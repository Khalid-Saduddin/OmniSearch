"""Exception hierarchy for the embedding subsystem."""


class EmbeddingError(Exception):
    """Base exception for all embedding-related errors."""


class ModelNotFoundError(EmbeddingError):
    """Raised when the specified model or its local weights cannot be found."""


class ModelLoadError(EmbeddingError):
    """Raised when loading model weights or tokenizer into memory fails."""


class InferenceError(EmbeddingError):
    """Raised when an error occurs during embedding forward pass or tensor computation."""


class DimensionMismatchError(EmbeddingError):
    """Raised when generated embedding dimensions do not match the expected configuration."""

