"""Unit tests for runbook similarity scoring."""

import pytest

from dataing_ee.core.runbook.similarity import SimilarityScorer


class TestSimilarityScorer:
    """Test TF-IDF similarity scoring."""

    @pytest.fixture
    def scorer(self) -> SimilarityScorer:
        """Create scorer instance."""
        return SimilarityScorer()

    def test_tokenize_basic(self, scorer: SimilarityScorer) -> None:
        """Test basic tokenization."""
        tokens = scorer._tokenize("Database connection failed")
        assert "database" in tokens
        assert "connection" in tokens
        assert "failed" in tokens

    def test_tokenize_removes_stop_words(self, scorer: SimilarityScorer) -> None:
        """Test that stop words are removed."""
        tokens = scorer._tokenize("The database is not working")
        assert "the" not in tokens
        assert "not" not in tokens
        assert "database" in tokens
        assert "working" in tokens

    def test_tokenize_removes_short_words(self, scorer: SimilarityScorer) -> None:
        """Test that short words are removed."""
        tokens = scorer._tokenize("DB is ok but SQL failed")
        # "db", "is", "ok" are too short (< 3 chars)
        assert "failed" in tokens

    def test_tokenize_lowercase(self, scorer: SimilarityScorer) -> None:
        """Test that tokens are lowercased."""
        tokens = scorer._tokenize("DATABASE CONNECTION Failed")
        assert "database" in tokens
        assert "DATABASE" not in tokens

    def test_tokenize_empty_string(self, scorer: SimilarityScorer) -> None:
        """Test tokenizing empty string."""
        tokens = scorer._tokenize("")
        assert tokens == []

    def test_calculate_idf(self, scorer: SimilarityScorer) -> None:
        """Test IDF calculation."""
        corpus = [
            ["database", "connection", "failed"],
            ["database", "timeout", "error"],
            ["network", "connection", "timeout"],
        ]
        idf = scorer._calculate_idf(corpus)

        # "database" appears in 2/3 docs
        # "connection" appears in 2/3 docs
        # "failed" appears in 1/3 docs
        # "timeout" appears in 2/3 docs
        # "network" appears in 1/3 docs

        # Terms appearing less frequently should have higher IDF
        assert idf["failed"] > idf["database"]
        assert idf["network"] > idf["connection"]

    def test_calculate_tfidf(self, scorer: SimilarityScorer) -> None:
        """Test TF-IDF calculation."""
        terms = ["database", "database", "connection"]
        idf_scores = {"database": 1.5, "connection": 2.0}

        tfidf = scorer._calculate_tfidf(terms, idf_scores)

        # TF for "database" = 2/3, TF for "connection" = 1/3
        # TF-IDF = TF * IDF
        assert "database" in tfidf
        assert "connection" in tfidf
        assert tfidf["database"] > 0
        assert tfidf["connection"] > 0

    def test_cosine_similarity_identical(self, scorer: SimilarityScorer) -> None:
        """Test cosine similarity of identical vectors."""
        vec = {"database": 0.5, "connection": 0.3}
        similarity = scorer._cosine_similarity(vec, vec)
        assert similarity == pytest.approx(1.0, rel=1e-6)

    def test_cosine_similarity_orthogonal(self, scorer: SimilarityScorer) -> None:
        """Test cosine similarity of orthogonal vectors."""
        vec_a = {"database": 1.0}
        vec_b = {"network": 1.0}
        similarity = scorer._cosine_similarity(vec_a, vec_b)
        assert similarity == pytest.approx(0.0, rel=1e-6)

    def test_cosine_similarity_partial_overlap(self, scorer: SimilarityScorer) -> None:
        """Test cosine similarity with partial overlap."""
        vec_a = {"database": 0.5, "connection": 0.5}
        vec_b = {"database": 0.5, "network": 0.5}
        similarity = scorer._cosine_similarity(vec_a, vec_b)
        # Should be > 0 but < 1
        assert 0 < similarity < 1

    def test_cosine_similarity_empty_vectors(self, scorer: SimilarityScorer) -> None:
        """Test cosine similarity with empty vectors."""
        assert scorer._cosine_similarity({}, {"a": 1.0}) == 0.0
        assert scorer._cosine_similarity({"a": 1.0}, {}) == 0.0
        assert scorer._cosine_similarity({}, {}) == 0.0

    def test_find_matched_terms(self, scorer: SimilarityScorer) -> None:
        """Test finding matched terms."""
        query_terms = ["database", "connection", "failed"]
        doc_terms = ["database", "timeout", "error"]
        matched = scorer._find_matched_terms(query_terms, doc_terms)
        assert matched == ["database"]

    def test_build_query_text(self, scorer: SimilarityScorer) -> None:
        """Test building query text from issue."""
        issue = {
            "title": "Database Error",
            "description": "Connection failed",
            "dataset_id": "warehouse.orders",
            "metadata": {"error_message": "Timeout"},
        }
        text = scorer._build_query_text(issue)
        assert "Database Error" in text
        assert "Connection failed" in text
        assert "warehouse.orders" in text
        assert "Timeout" in text

    def test_build_document_text(self, scorer: SimilarityScorer) -> None:
        """Test building document text from runbook."""
        runbook = {
            "title": "Database Runbook",
            "summary": "How to fix database issues",
            "body": "Check connection settings",
            "root_cause": "Configuration error",
            "symptoms": [{"description": "Connection timeout"}],
            "labels": ["database", "production"],
        }
        text = scorer._build_document_text(runbook)
        assert "Database Runbook" in text
        assert "fix database issues" in text
        assert "Connection timeout" in text
        assert "database" in text


class TestSimilarityScorerIntegration:
    """Integration-style tests for similarity scoring."""

    @pytest.fixture
    def scorer(self) -> SimilarityScorer:
        """Create scorer instance."""
        return SimilarityScorer()

    def test_similar_issues_score_higher(self, scorer: SimilarityScorer) -> None:
        """Test that similar content scores higher than dissimilar."""
        # Create a query about database issues
        query_issue = {
            "title": "Database connection timeout",
            "description": "Production database connections are timing out",
        }
        query_text = scorer._build_query_text(query_issue)
        query_terms = scorer._tokenize(query_text)

        # Similar runbook
        similar_runbook = {
            "title": "Database Connection Issues",
            "summary": "Troubleshooting database connection timeouts",
            "body": "Check connection pool settings",
            "symptoms": [{"description": "Connections timing out"}],
        }

        # Dissimilar runbook
        dissimilar_runbook = {
            "title": "API Rate Limiting",
            "summary": "How to handle rate limits",
            "body": "Implement exponential backoff",
            "symptoms": [{"description": "HTTP 429 errors"}],
        }

        # Build corpus for IDF
        similar_text = scorer._build_document_text(similar_runbook)
        dissimilar_text = scorer._build_document_text(dissimilar_runbook)
        similar_terms = scorer._tokenize(similar_text)
        dissimilar_terms = scorer._tokenize(dissimilar_text)

        corpus = [query_terms, similar_terms, dissimilar_terms]
        idf = scorer._calculate_idf(corpus)

        # Calculate TF-IDF vectors
        query_tfidf = scorer._calculate_tfidf(query_terms, idf)
        similar_tfidf = scorer._calculate_tfidf(similar_terms, idf)
        dissimilar_tfidf = scorer._calculate_tfidf(dissimilar_terms, idf)

        # Calculate similarities
        similar_score = scorer._cosine_similarity(query_tfidf, similar_tfidf)
        dissimilar_score = scorer._cosine_similarity(query_tfidf, dissimilar_tfidf)

        # Similar runbook should score higher
        assert similar_score > dissimilar_score
