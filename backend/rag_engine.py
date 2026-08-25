import os
import json
import contextlib
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer

from database import get_db_connection
from llm_providers import get_provider_adapter
from llm_providers.base import parse_evaluation_json
import settings as platform_settings

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RagEngine:
    def __init__(self):
        print("Initializing RAG Engine...")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.load_or_build_index()

    def vector_db_size(self):
        """Returns the number of indexed chunks in the Framework Knowledge Base."""
        with contextlib.closing(get_db_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM framework_kb_chunks;")
                return cursor.fetchone()[0]

    def load_or_build_index(self):
        """Builds the Framework Knowledge Base if it's empty."""
        size = self.vector_db_size()
        if size > 0:
            print(f"Framework Knowledge Base already indexed ({size} chunks).")
        else:
            print("Framework Knowledge Base is empty. Ingesting PDF files...")
            self.ingest_pdfs()

    def ingest_pdfs(self):
        """Reads Phase 1 and Phase 2 PDFs, extracts slides, embeds them, and inserts into framework_kb_chunks."""
        pdf_files = [
            ("ABG.Madura.Brand Compass.Phase1.V2.pdf", "Phase 1"),
            ("ABG.Brand Compass.Phase2.V1.pdf", "Phase 2"),
        ]

        records = []

        for filename, phase_name in pdf_files:
            file_path = os.path.join(BASE_DIR, "archives", filename)
            if not os.path.exists(file_path):
                print(f"Warning: PDF file not found at: {file_path}. Skipping.")
                continue

            print(f"Parsing {filename} ({phase_name})...")
            try:
                reader = PdfReader(file_path)
                total_pages = len(reader.pages)
                print(f"Found {total_pages} pages in {filename}.")

                for i, page in enumerate(reader.pages):
                    text = page.extract_text()
                    if text and len(text.strip()) > 20:
                        records.append(
                            {
                                "source_file": filename,
                                "phase": phase_name,
                                "slide_number": i + 1,
                                "text": text.strip(),
                            }
                        )
            except Exception as e:
                print(f"Error parsing {filename}: {e}")

        if not records:
            print("No text could be extracted from PDFs. Creating synthetic database for fallback.")
            self.create_synthetic_fallback()
            return

        print(f"Computing embeddings for {len(records)} slides...")
        texts = [r["text"] for r in records]
        embeddings = self.embedding_model.encode(texts)

        self._insert_chunks(records, embeddings)
        print(f"Inserted {len(records)} chunks into framework_kb_chunks.")

    def create_synthetic_fallback(self):
        """Fallback synthetic DB if PDFs are absent or failed to load."""
        records = [
            {
                "source_file": "synthetic",
                "phase": "Phase 1",
                "slide_number": 295,
                "text": "Insight Matrix 360Sight. Known What, Known Why = Not an Insight. Unknown What, Known Why = Fair insight for innovation. Known What, Unknown Why = Good insight. Unknown What, Unknown Why = Great insight.",
            },
            {
                "source_file": "synthetic",
                "phase": "Phase 1",
                "slide_number": 304,
                "text": "Insight Spiral: Connecting customer behaviour to societal culture. Traces from 1. Culture & Society (emergent culture), 2. Life & People (need states), 3. Experience & Consumers, 4. Behavior & Users, 5. Brand Relationship, 6. Business & Shoppers, 7. Business Model.",
            },
            {
                "source_file": "synthetic",
                "phase": "Phase 2",
                "slide_number": 60,
                "text": "Competitive Environment: BrandFaith Xtent & Xtensity. Focuses on how brand positioning reduces consumer risk, builds trust, and helps command price premia.",
            },
        ]
        print("Generating embeddings for synthetic fallback records...")
        texts = [r["text"] for r in records]
        embeddings = self.embedding_model.encode(texts)
        self._insert_chunks(records, embeddings)

    def _insert_chunks(self, records, embeddings):
        with contextlib.closing(get_db_connection()) as conn:
            with conn.cursor() as cursor:
                for record, emb in zip(records, embeddings):
                    cursor.execute(
                        """
                        INSERT INTO framework_kb_chunks (source_file, phase, slide_number, text, embedding)
                        VALUES (%s, %s, %s, %s, %s);
                        """,
                        (record["source_file"], record["phase"], record["slide_number"], record["text"], emb),
                    )
            conn.commit()

    def search(self, query: str, top_k: int = 3):
        """pgvector cosine-distance search against the Framework Knowledge Base."""
        query_vector = self.embedding_model.encode(query)

        with contextlib.closing(get_db_connection()) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, source_file, phase, slide_number, text, 1 - (embedding <=> %s) AS score
                    FROM framework_kb_chunks
                    ORDER BY embedding <=> %s
                    LIMIT %s;
                    """,
                    (query_vector, query_vector, top_k),
                )
                rows = cursor.fetchall()

        hits = []
        for row_id, source_file, phase, slide_number, text, score in rows:
            hits.append(
                {
                    "id": row_id,
                    "source_file": source_file,
                    "phase": phase,
                    "slide_number": slide_number,
                    "text": text,
                    "score": float(score),
                }
            )
        return hits

    def generate_evaluation(self, question: str, user_answer: str, context_hits: list):
        """Generates RAG-assisted critique of the user's answer using the active LLM provider."""
        context_str = "\n\n".join(
            [
                f"Source: {hit['source_file']} (Slide {hit['slide_number']})\nContext: {hit['text']}"
                for hit in context_hits
            ]
        )

        system_prompt = (
            "You are Cosmos AI, a premier management consulting assistant. Your job is to evaluate "
            "the user's answers to strategic business questions using the Cosmos methodology. "
            "You judge answers on a strict, restlessness-arousing scale:\n"
            "\U0001F534 Level 1: Superficial / Fact-based (obvious quotes, research facts, universal truths with no actionable connect).\n"
            "\U0001F7E1 Level 2: Good / Needs-based (identifies standard customer conflicts, needs, and safety vs performance trade-offs).\n"
            "\U0001F7E2 Level 3: Deep / Insight-driven (explores existential customer anxieties, hidden economic transactions, binary risks, and societal shifts).\n\n"
            "Provide your evaluation in a JSON structure containing:\n"
            "1. 'rating': '\U0001F534 Level 1', '\U0001F7E1 Level 2', or '\U0001F7E2 Level 3'\n"
            "2. 'critique': A detailed, RESTLESSNESS-AROUSING explanation of why the answer received this rating.\n"
            "3. 'recommendations': Actionable guidance on how to push the thinking deeper to achieve Level 3 depth."
        )

        user_prompt = (
            f"Here is the context retrieved from the Cosmos frameworks:\n"
            f"{context_str}\n\n"
            f"Question asked: {question}\n\n"
            f"User's submitted answer: {user_answer}\n\n"
            f"Please critique this answer against the framework. Return ONLY a valid JSON object matching the schema:\n"
            f"{{\n"
            f'  "rating": "\U0001F534 Level 1" | "\U0001F7E1 Level 2" | "\U0001F7E2 Level 3",\n'
            f'  "critique": "your detailed critique text here",\n'
            f'  "recommendations": "your recommendations text here"\n'
            f"}}"
        )

        try:
            provider_name = platform_settings.get_active_provider()
            provider = get_provider_adapter(provider_name)
            response_text = provider.complete(system_prompt, user_prompt)
            return parse_evaluation_json(response_text)
        except Exception as e:
            print(f"Error generating evaluation via '{provider_name if 'provider_name' in locals() else 'unknown'}' provider: {e}")
            return self.fallback_local_critique(question, user_answer)

    def fallback_local_critique(self, question: str, user_answer: str):
        """Local fallback evaluation engine using simple heuristics for offline testing."""
        answer_length = len(user_answer.strip())

        if answer_length < 40:
            rating = "\U0001F534 Level 1"
            critique = "Your response is extremely brief and lists superficial facts or generic statements. It fails to expose any tension, business trade-offs, or underlying customer anxiety."
            recommendations = "Push past the obvious. Describe specific customer anxieties (e.g. fear of aging roots, social embarrassment) and explain what trade-offs they make."
        elif any(
            term in user_answer.lower()
            for term in ["anxiety", "tension", "transaction", "exposure", "existential", "binary"]
        ):
            rating = "\U0001F7E2 Level 3"
            critique = "Excellent strategic depth. You identified the core human tension and the trade-offs driving customer brand relationships, addressing the underlying existential anxiety."
            recommendations = "Perfect. Now translate this insight into specific visual packaging requirements or product active botanical claims."
        else:
            rating = "\U0001F7E1 Level 2"
            critique = "This is a good, needs-based explanation. You successfully capture the conflict between natural safety and efficacy, but your answer stops at the surface functional level."
            recommendations = "Dig deeper into the emotional and social consequences. Why do they buy henna? What is the hidden transaction? How does root-showing affect their professional relevance?"

        return {"rating": rating, "critique": critique, "recommendations": recommendations}
