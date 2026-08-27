# Import regular expressions for detecting Markdown headings
# and technical error codes.
import re

# Import dataclass for structured retrieval results.
from dataclasses import dataclass

# Import TF-IDF and cosine similarity.
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Import our validated data repository.
from app.data_repository import get_repository


# Match Markdown headings such as:
# # Authentication
# ## Token Expiration
MARKDOWN_HEADING_PATTERN = re.compile(
    r"^(#{1,6})\s+(.+?)\s*$"
)

# Match uppercase technical codes containing underscores,
# such as AUTH_TOKEN_EXPIRED.
ERROR_CODE_PATTERN = re.compile(
    r"\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b"
)


@dataclass(frozen=True)
class KnowledgeChunk:
    """
    One searchable section of a knowledge-base document.
    """

    chunk_id: str
    document_name: str
    document_path: str
    document_title: str
    heading: str
    content: str
    search_text: str
    error_codes: tuple[str, ...]


@dataclass(frozen=True)
class RetrievalResult:
    """
    One ranked knowledge-base retrieval result.
    """

    chunk_id: str
    document_name: str
    document_path: str
    document_title: str
    heading: str
    content: str
    similarity_score: float
    matched_error_codes: tuple[str, ...]

    @property
    def exact_error_code_match(self) -> bool:
        """
        Return True when an exact error code was matched.
        """

        return bool(self.matched_error_codes)

    @property
    def rank_score(self) -> float:
        """
        Boost exact error-code matches above text-only matches.
        """

        exact_match_bonus = (
            1.0
            if self.exact_error_code_match
            else 0.0
        )

        return self.similarity_score + exact_match_bonus


def extract_error_codes(text: str) -> tuple[str, ...]:
    """
    Extract unique uppercase error codes from text.
    """

    normalized_text = text.upper()

    error_codes = set(
        ERROR_CODE_PATTERN.findall(normalized_text)
    )

    return tuple(sorted(error_codes))


def create_knowledge_chunk(
    document: dict[str, str],
    heading: str,
    content: str,
    chunk_number: int,
) -> KnowledgeChunk:
    """
    Create one searchable chunk from a Markdown section.
    """

    search_text = "\n".join(
        [
            document["title"],
            heading,
            content,
        ]
    )

    return KnowledgeChunk(
        chunk_id=(
            f"{document['document_path']}"
            f"#chunk-{chunk_number:03d}"
        ),
        document_name=document["document_name"],
        document_path=document["document_path"],
        document_title=document["title"],
        heading=heading,
        content=content,
        search_text=search_text,
        error_codes=extract_error_codes(search_text),
    )


def split_markdown_document(
    document: dict[str, str],
) -> list[KnowledgeChunk]:
    """
    Split one Markdown document using its headings.
    """

    chunks: list[KnowledgeChunk] = []

    current_heading = document["title"]
    current_content_lines: list[str] = []
    chunk_number = 1

    for line in document["content"].splitlines():
        heading_match = MARKDOWN_HEADING_PATTERN.match(line)

        if heading_match:
            current_content = "\n".join(
                current_content_lines
            ).strip()

            if current_content:
                chunks.append(
                    create_knowledge_chunk(
                        document=document,
                        heading=current_heading,
                        content=current_content,
                        chunk_number=chunk_number,
                    )
                )

                chunk_number += 1

            current_heading = heading_match.group(2).strip()
            current_content_lines = []

        else:
            current_content_lines.append(line)

    final_content = "\n".join(
        current_content_lines
    ).strip()

    if final_content:
        chunks.append(
            create_knowledge_chunk(
                document=document,
                heading=current_heading,
                content=final_content,
                chunk_number=chunk_number,
            )
        )

    if not chunks:
        chunks.append(
            create_knowledge_chunk(
                document=document,
                heading=document["title"],
                content=document["content"],
                chunk_number=1,
            )
        )

    return chunks


class KnowledgeBaseRetriever:
    """
    Retrieve relevant KB sections using exact codes and TF-IDF.
    """

    def __init__(self) -> None:
        repository = get_repository()

        all_chunks: list[KnowledgeChunk] = []

        for document in repository.knowledge_base_documents:
            document_chunks = split_markdown_document(
                document
            )

            all_chunks.extend(document_chunks)

        if not all_chunks:
            raise ValueError(
                "No searchable knowledge-base chunks were created."
            )

        self.chunks = tuple(all_chunks)

        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
        )

        self.chunk_matrix = self.vectorizer.fit_transform(
            chunk.search_text
            for chunk in self.chunks
        )

    def retrieve(
        self,
        subject: str,
        body: str,
        top_k: int = 3,
    ) -> list[RetrievalResult]:
        """
        Return the most relevant knowledge-base documents.
        """

        if top_k < 1:
            raise ValueError(
                "top_k must be at least 1."
            )

        query_text = f"{subject}\n{body}".strip()

        if not query_text:
            raise ValueError(
                "The retrieval query cannot be empty."
            )

        query_vector = self.vectorizer.transform(
            [query_text]
        )

        similarity_scores = cosine_similarity(
            query_vector,
            self.chunk_matrix,
        ).flatten()

        query_error_codes = set(
            extract_error_codes(query_text)
        )

        candidates: list[RetrievalResult] = []

        for chunk, similarity_score in zip(
            self.chunks,
            similarity_scores,
        ):
            matched_error_codes = tuple(
                sorted(
                    query_error_codes.intersection(
                        chunk.error_codes
                    )
                )
            )

            candidates.append(
                RetrievalResult(
                    chunk_id=chunk.chunk_id,
                    document_name=chunk.document_name,
                    document_path=chunk.document_path,
                    document_title=chunk.document_title,
                    heading=chunk.heading,
                    content=chunk.content,
                    similarity_score=float(similarity_score),
                    matched_error_codes=matched_error_codes,
                )
            )

        candidates.sort(
            key=lambda result: (
                -result.rank_score,
                result.document_path,
                result.chunk_id,
            )
        )

        results: list[RetrievalResult] = []
        seen_documents: set[str] = set()

        for candidate in candidates:
            if candidate.document_path in seen_documents:
                continue

            results.append(candidate)
            seen_documents.add(candidate.document_path)

            if len(results) == top_k:
                break

        return results


def has_confident_match(
    results: list[RetrievalResult],
    minimum_similarity: float = 0.15,
) -> bool:
    """
    Decide whether retrieval found enough evidence for a KB match.
    """

    return any(
        result.exact_error_code_match
        or result.similarity_score >= minimum_similarity
        for result in results
    )
    
    