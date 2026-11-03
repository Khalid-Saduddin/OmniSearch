"""Safe and robust query parser for SQLite FTS5 full-text queries."""

from dataclasses import dataclass, field
import re
from typing import List, Set


@dataclass
class ParsedQuery:
    """Encapsulates the parsed user query terms and the sanitized FTS5 MATCH expression."""

    raw_query: str
    fts_query: str
    terms: List[str] = field(default_factory=list)
    phrases: List[str] = field(default_factory=list)
    is_empty: bool = False


class QueryParser:
    """Parses user search queries into safe, syntax-valid SQLite FTS5 MATCH expressions.

    Features:
    - Preserves exact quoted phrases: "quantum computing"
    - Preserves technical identifiers: test_case_1, k-means, v1.2.3, os.path
    - Supports boolean operators: AND, OR, NOT
    - Handles prefix wildcard searches: comput* -> "comput"*
    - Automatically balances or strips malformed / unclosed quotes
    - Neutralizes special FTS5 operators like ':', '^', '*', '(', ')' to prevent syntax crashes
    - Empty or whitespace query returns clean empty representation
    """

    BOOLEAN_OPERATORS: Set[str] = {"AND", "OR", "NOT"}

    @classmethod
    def parse(cls, raw_query: str) -> ParsedQuery:
        """Parse raw user query text into a safe ParsedQuery.

        Args:
            raw_query: Raw user query string.

        Returns:
            ParsedQuery with sanitized FTS5 MATCH expression and extracted terms/phrases.
        """
        if not raw_query or not raw_query.strip():
            return ParsedQuery(
                raw_query=raw_query or "",
                fts_query="",
                terms=[],
                phrases=[],
                is_empty=True,
            )

        cleaned = raw_query.strip()

        # Handle uneven quotes: if odd number of quotes, close the open quote
        if cleaned.count('"') % 2 != 0:
            cleaned = cleaned + '"'

        phrases: List[str] = []
        terms: List[str] = []
        raw_tokens: List[str] = []

        # Regex to extract quoted phrases: "..." and standalone words
        pattern = r'"([^"]*)"|(\S+)'
        for quoted, unquoted in re.findall(pattern, cleaned):
            if quoted:
                phrase = quoted.strip()
                if phrase:
                    # Filter out phrases with zero word/digit characters
                    if re.search(r"[\w]", phrase):
                        phrases.append(phrase)
                        escaped_phrase = phrase.replace('"', '""')
                        raw_tokens.append(f'"{escaped_phrase}"')
            elif unquoted:
                token = unquoted.strip()
                upper = token.upper()
                if upper in cls.BOOLEAN_OPERATORS:
                    raw_tokens.append(upper)
                else:
                    # Check for trailing wildcard prefix search: e.g. comput*
                    if token.endswith("*") and len(token) > 1 and re.match(r"^[\w\-]+$", token[:-1]):
                        prefix = token[:-1]
                        terms.append(prefix)
                        escaped_prefix = prefix.replace('"', '""')
                        raw_tokens.append(f'"{escaped_prefix}"*')
                    else:
                        # Clean token of standalone special characters
                        token_clean = token.replace('"', "")
                        # Ignore tokens that contain absolutely no word/number characters
                        if token_clean and re.search(r"[\w]", token_clean):
                            terms.append(token_clean)
                            escaped_token = token_clean.replace('"', '""')
                            raw_tokens.append(f'"{escaped_token}"')

        # Clean boolean operators:
        # Cannot be at start, cannot be consecutive, cannot be at end
        valid_tokens: List[str] = []
        for tok in raw_tokens:
            if tok in cls.BOOLEAN_OPERATORS:
                if not valid_tokens or valid_tokens[-1] in cls.BOOLEAN_OPERATORS:
                    continue
                valid_tokens.append(tok)
            else:
                valid_tokens.append(tok)

        while valid_tokens and valid_tokens[-1] in cls.BOOLEAN_OPERATORS:
            valid_tokens.pop()

        if not valid_tokens:
            return ParsedQuery(
                raw_query=raw_query,
                fts_query="",
                terms=terms,
                phrases=phrases,
                is_empty=True,
            )

        # Assemble tokens: if two adjacent tokens are operands, join them with implicit AND
        assembled: List[str] = []
        for i, tok in enumerate(valid_tokens):
            if i > 0:
                prev = valid_tokens[i - 1]
                if prev not in cls.BOOLEAN_OPERATORS and tok not in cls.BOOLEAN_OPERATORS:
                    assembled.append("AND")
            assembled.append(tok)

        fts_query = " ".join(assembled)

        return ParsedQuery(
            raw_query=raw_query,
            fts_query=fts_query,
            terms=terms,
            phrases=phrases,
            is_empty=False,
        )
