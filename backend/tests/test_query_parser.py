"""Tests for safe FTS5 query parser and snippet formatting."""

import sqlite3
import pytest
from app.search.query_parser import ParsedQuery, QueryParser
from app.search.snippets import SnippetFormatter


def test_empty_and_whitespace_query() -> None:
    """Verify empty or whitespace-only queries return is_empty=True."""
    assert QueryParser.parse("").is_empty
    assert QueryParser.parse("   ").is_empty
    assert QueryParser.parse("\t\n").is_empty


def test_single_and_multi_word_query() -> None:
    """Verify single and multi-term queries assemble with implicit conjunction."""
    p1 = QueryParser.parse("quantum")
    assert not p1.is_empty
    assert p1.fts_query == '"quantum"'
    assert p1.terms == ["quantum"]

    p2 = QueryParser.parse("quantum computing")
    assert not p2.is_empty
    assert p2.fts_query == '"quantum" AND "computing"'
    assert p2.terms == ["quantum", "computing"]


def test_exact_phrase_preservation() -> None:
    """Verify quoted exact phrases are preserved without splitting."""
    p = QueryParser.parse('"quantum computing algorithms"')
    assert not p.is_empty
    assert p.fts_query == '"quantum computing algorithms"'
    assert p.phrases == ["quantum computing algorithms"]
    assert p.terms == []


def test_mixed_phrase_and_terms() -> None:
    """Verify mixed exact phrases and terms assemble correctly."""
    p = QueryParser.parse('"neural networks" backpropagation pytorch')
    assert not p.is_empty
    assert p.fts_query == '"neural networks" AND "backpropagation" AND "pytorch"'
    assert p.phrases == ["neural networks"]
    assert p.terms == ["backpropagation", "pytorch"]


def test_technical_identifiers_and_paths() -> None:
    """Verify technical identifiers, snake_case, CamelCase, dots, and paths are preserved."""
    test_cases = [
        ("test_case_1", '"test_case_1"'),
        ("k-means", '"k-means"'),
        ("v1.2.3", '"v1.2.3"'),
        ("os.path.join", '"os.path.join"'),
        ("C:\\Windows\\System32", '"C:\\Windows\\System32"'),
    ]
    for raw, expected in test_cases:
        p = QueryParser.parse(raw)
        assert not p.is_empty
        assert p.fts_query == expected


def test_unclosed_quotes_resilience() -> None:
    """Verify queries with odd / unclosed quotes are safely balanced without crashing."""
    p1 = QueryParser.parse('unclosed "quote')
    assert not p1.is_empty
    assert "quote" in p1.fts_query
    # Must be valid in SQLite
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(c);")
    res = conn.execute("SELECT * FROM t WHERE t MATCH ?", (p1.fts_query,)).fetchall()
    assert res == []


def test_boolean_operators_preservation() -> None:
    """Verify AND, OR, NOT operators are preserved when placed between terms."""
    p_and = QueryParser.parse("quantum AND computing")
    assert p_and.fts_query == '"quantum" AND "computing"'

    p_or = QueryParser.parse("quantum OR classical")
    assert p_or.fts_query == '"quantum" OR "classical"'

    p_not = QueryParser.parse("python NOT java")
    assert p_not.fts_query == '"python" NOT "java"'


def test_stray_boolean_operators_cleaned() -> None:
    """Verify boolean operators at boundaries or repeated are safely stripped."""
    assert QueryParser.parse("AND").is_empty
    assert QueryParser.parse("AND OR NOT").is_empty
    p = QueryParser.parse("AND quantum OR NOT")
    assert p.fts_query == '"quantum"'


def test_prefix_wildcard_search() -> None:
    """Verify trailing asterisk wildcard on alphanumeric prefix creates prefix search."""
    p = QueryParser.parse("comput*")
    assert p.fts_query == '"comput"*'
    assert p.terms == ["comput"]


def test_special_characters_neutralization() -> None:
    """Verify special FTS5 characters like :, ^, *, (, ) do not cause SQLite syntax errors."""
    special_queries = [
        "test: syntax",
        "*",
        "^carat",
        "(parentheses)",
        "[brackets] {braces}",
        "foo ~ bar + baz",
    ]
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE VIRTUAL TABLE t USING fts5(c);")
    for sq in special_queries:
        parsed = QueryParser.parse(sq)
        if not parsed.is_empty:
            # Must execute without SQLite OperationalError
            cur = conn.cursor()
            cur.execute("SELECT * FROM t WHERE t MATCH ?", (parsed.fts_query,))
            assert cur.fetchall() == []
            cur.close()


def test_snippet_formatter_standard_markers() -> None:
    """Verify SnippetFormatter translates FTS markers to <mark> and extracts highlights."""
    raw = "Here is [[[HL]]]quantum[[[/HL]]] computing with [[[HL]]]qubits[[[/HL]]]."
    formatted, highlights = SnippetFormatter.format(raw)
    assert formatted == "Here is <mark>quantum</mark> computing with <mark>qubits</mark>."
    assert highlights == ["quantum", "qubits"]


def test_snippet_formatter_xss_protection() -> None:
    """Verify HTML special characters in documents are escaped to prevent XSS."""
    raw = "Code: <script>alert(1)</script> and [[[HL]]]search[[[/HL]]]."
    formatted, highlights = SnippetFormatter.format(raw)
    assert "<script>" not in formatted
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in formatted
    assert "<mark>search</mark>" in formatted
    assert highlights == ["search"]


def test_snippet_formatter_fallback_content() -> None:
    """Verify fallback snippet generation locates query terms in raw content."""
    content = "A long document starting here. Later on we discuss artificial intelligence networks and deep architectures."
    formatted, highlights = SnippetFormatter.format(
        raw_snippet="",
        fallback_content=content,
        terms=["intelligence"],
    )
    assert "<mark>intelligence</mark>" in formatted
    assert highlights == ["intelligence"]
