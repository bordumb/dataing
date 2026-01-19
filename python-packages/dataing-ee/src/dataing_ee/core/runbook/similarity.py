"""Similarity scoring for runbook suggestions."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from dataing.adapters.db.app_db import AppDatabase

logger = logging.getLogger(__name__)


@dataclass
class ScoredRunbook:
    """A runbook with similarity score."""

    runbook_id: UUID
    title: str
    summary: str | None
    score: float
    matched_terms: list[str]


class SimilarityScorer:
    """TF-IDF based similarity scoring for runbook matching."""

    # Common stop words to exclude
    STOP_WORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "will",
        "with",
        "this",
        "they",
        "have",
        "had",
        "not",
        "but",
        "what",
        "all",
        "when",
        "we",
        "can",
        "there",
        "been",
        "if",
        "more",
        "no",
        "out",
        "so",
        "up",
        "other",
    }

    def __init__(self, min_term_length: int = 3) -> None:
        """Initialize scorer.

        Args:
            min_term_length: Minimum length for terms to consider
        """
        self.min_term_length = min_term_length

    async def find_similar_runbooks(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        issue_id: UUID,
        limit: int = 5,
        min_score: float = 0.1,
    ) -> list[ScoredRunbook]:
        """Find runbooks similar to an issue.

        Args:
            db: Database connection
            tenant_id: Tenant ID
            issue_id: Issue ID to find similar runbooks for
            limit: Maximum number of results
            min_score: Minimum similarity score (0.0 to 1.0)

        Returns:
            List of ScoredRunbook sorted by score descending
        """
        # Get issue data
        issue = await db.fetch_one(
            """
            SELECT title, description, dataset_id, metadata
            FROM issues
            WHERE id = $1 AND tenant_id = $2
            """,
            issue_id,
            tenant_id,
        )

        if not issue:
            return []

        # Build query text from issue
        query_text = self._build_query_text(issue)
        query_terms = self._tokenize(query_text)

        if not query_terms:
            return []

        # Get all runbooks for tenant
        runbooks = await db.fetch_all(
            """
            SELECT id, title, summary, body, symptoms, root_cause, labels
            FROM runbooks
            WHERE tenant_id = $1 AND is_published = true
            """,
            tenant_id,
        )

        if not runbooks:
            return []

        # Build document corpus for IDF calculation
        corpus = []
        for runbook in runbooks:
            doc_text = self._build_document_text(runbook)
            doc_terms = self._tokenize(doc_text)
            corpus.append(doc_terms)

        # Calculate IDF scores
        idf_scores = self._calculate_idf(corpus)

        # Score each runbook
        scored: list[ScoredRunbook] = []
        query_tfidf = self._calculate_tfidf(query_terms, idf_scores)

        for i, runbook in enumerate(runbooks):
            doc_tfidf = self._calculate_tfidf(corpus[i], idf_scores)
            score = self._cosine_similarity(query_tfidf, doc_tfidf)

            if score >= min_score:
                matched_terms = self._find_matched_terms(query_terms, corpus[i])
                scored.append(
                    ScoredRunbook(
                        runbook_id=runbook["id"],
                        title=runbook["title"],
                        summary=runbook.get("summary"),
                        score=score,
                        matched_terms=matched_terms[:10],
                    )
                )

        # Sort by score and limit
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:limit]

    async def score_runbook_for_issue(
        self,
        db: AppDatabase,
        tenant_id: UUID,
        issue_id: UUID,
        runbook_id: UUID,
    ) -> float:
        """Calculate similarity score between a specific runbook and issue.

        Args:
            db: Database connection
            tenant_id: Tenant ID
            issue_id: Issue ID
            runbook_id: Runbook ID

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Get issue
        issue = await db.fetch_one(
            """
            SELECT title, description, dataset_id, metadata
            FROM issues
            WHERE id = $1 AND tenant_id = $2
            """,
            issue_id,
            tenant_id,
        )

        if not issue:
            return 0.0

        # Get runbook
        runbook = await db.fetch_one(
            """
            SELECT title, summary, body, symptoms, root_cause, labels
            FROM runbooks
            WHERE id = $1 AND tenant_id = $2
            """,
            runbook_id,
            tenant_id,
        )

        if not runbook:
            return 0.0

        # Tokenize
        query_text = self._build_query_text(issue)
        query_terms = self._tokenize(query_text)

        doc_text = self._build_document_text(runbook)
        doc_terms = self._tokenize(doc_text)

        if not query_terms or not doc_terms:
            return 0.0

        # Simple Jaccard similarity for single comparison
        query_set = set(query_terms)
        doc_set = set(doc_terms)
        intersection = query_set & doc_set
        union = query_set | doc_set

        if not union:
            return 0.0

        return len(intersection) / len(union)

    def _build_query_text(self, issue: dict[str, Any]) -> str:
        """Build search text from issue data."""
        parts = []

        if issue.get("title"):
            parts.append(issue["title"])

        if issue.get("description"):
            parts.append(issue["description"])

        if issue.get("dataset_id"):
            parts.append(issue["dataset_id"])

        metadata = issue.get("metadata") or {}
        if metadata.get("error_message"):
            parts.append(metadata["error_message"])

        return " ".join(parts)

    def _build_document_text(self, runbook: dict[str, Any]) -> str:
        """Build search text from runbook data."""
        parts = []

        if runbook.get("title"):
            parts.append(runbook["title"])

        if runbook.get("summary"):
            parts.append(runbook["summary"])

        if runbook.get("body"):
            parts.append(runbook["body"])

        if runbook.get("root_cause"):
            parts.append(runbook["root_cause"])

        # Extract symptoms descriptions
        symptoms = runbook.get("symptoms") or []
        for symptom in symptoms:
            if isinstance(symptom, dict) and symptom.get("description"):
                parts.append(symptom["description"])

        # Add labels
        labels = runbook.get("labels") or []
        parts.extend(labels)

        return " ".join(parts)

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text into terms."""
        if not text:
            return []

        # Lowercase and extract words
        words = re.findall(r"\b[a-z][a-z0-9_]*\b", text.lower())

        # Filter
        terms = [w for w in words if len(w) >= self.min_term_length and w not in self.STOP_WORDS]

        return terms

    def _calculate_idf(self, corpus: list[list[str]]) -> dict[str, float]:
        """Calculate IDF scores for terms in corpus."""
        doc_count = len(corpus)
        if doc_count == 0:
            return {}

        # Count documents containing each term
        doc_freq: Counter[str] = Counter()
        for doc_terms in corpus:
            unique_terms = set(doc_terms)
            doc_freq.update(unique_terms)

        # Calculate IDF: log(N / df)
        idf: dict[str, float] = {}
        for term, df in doc_freq.items():
            idf[term] = math.log(doc_count / df) + 1.0

        return idf

    def _calculate_tfidf(
        self,
        terms: list[str],
        idf_scores: dict[str, float],
    ) -> dict[str, float]:
        """Calculate TF-IDF vector for terms."""
        tf = Counter(terms)
        total = len(terms)

        if total == 0:
            return {}

        tfidf: dict[str, float] = {}
        for term, count in tf.items():
            tf_score = count / total
            idf_score = idf_scores.get(term, 1.0)
            tfidf[term] = tf_score * idf_score

        return tfidf

    def _cosine_similarity(
        self,
        vec_a: dict[str, float],
        vec_b: dict[str, float],
    ) -> float:
        """Calculate cosine similarity between two TF-IDF vectors."""
        if not vec_a or not vec_b:
            return 0.0

        # Dot product
        dot_product = sum(
            vec_a.get(term, 0.0) * vec_b.get(term, 0.0) for term in set(vec_a) | set(vec_b)
        )

        # Magnitudes
        mag_a = math.sqrt(sum(v * v for v in vec_a.values()))
        mag_b = math.sqrt(sum(v * v for v in vec_b.values()))

        if mag_a == 0 or mag_b == 0:
            return 0.0

        return dot_product / (mag_a * mag_b)

    def _find_matched_terms(
        self,
        query_terms: list[str],
        doc_terms: list[str],
    ) -> list[str]:
        """Find terms that match between query and document."""
        query_set = set(query_terms)
        doc_set = set(doc_terms)
        return list(query_set & doc_set)
