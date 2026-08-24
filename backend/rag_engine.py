import os
import json
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
import boto3
from botocore.exceptions import BotoCoreError, ClientError

from database import get_db_connection

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RagEngine:
    def __init__(self):
        print("Initializing RAG Engine...")
        self.embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        self.bedrock_client = None
        self.init_aws()
        self.load_or_build_index()

    def init_aws(self):
        """Initialize AWS Bedrock client if credentials exist."""
        try:
            self.bedrock_client = boto3.client(
                service_name="bedrock-runtime",
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            )
            print("AWS Bedrock Runtime client initialized successfully.")
        except Exception as e:
            print(f"Warning: Failed to initialize AWS Bedrock Client: {e}")
            print("Fallback: Using mock/local LLM responses for development.")
            self.bedrock_client = None

    def vector_db_size(self):
        """Returns the number of indexed chunks in the Framework Knowledge Base."""
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM framework_kb_chunks;")
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count

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
        conn = get_db_connection()
        cursor = conn.cursor()
        for record, emb in zip(records, embeddings):
            cursor.execute(
                """
                INSERT INTO framework_kb_chunks (source_file, phase, slide_number, text, embedding)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (record["source_file"], record["phase"], record["slide_number"], record["text"], emb),
            )
        conn.commit()
        cursor.close()
        conn.close()

    def search(self, query: str, top_k: int = 3):
        """pgvector cosine-distance search against the Framework Knowledge Base."""
        query_vector = self.embedding_model.encode(query)

        conn = get_db_connection()
        cursor = conn.cursor()
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
        cursor.close()
        conn.close()

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
        """Generates RAG-assisted critique of the user's answer using AWS Bedrock Claude 3.5 Sonnet."""
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

        if not self.bedrock_client:
            print("No Bedrock Client active. Running fallback local heuristics evaluation.")
            return self.fallback_local_critique(question, user_answer)

        try:
            body = json.dumps(
                {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "temperature": 0.2,
                }
            )

            response = self.bedrock_client.invoke_model(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                contentType="application/json",
                accept="application/json",
                body=body,
            )

            response_body = json.loads(response.get("body").read())
            response_text = response_body["content"][0]["text"]

            try:
                if "```json" in response_text:
                    response_text = response_text.split("```json")[1].split("```")[0]
                elif "```" in response_text:
                    response_text = response_text.split("```")[1].split("```")[0]

                return json.loads(response_text.strip())
            except Exception as parse_err:
                print(f"Error parsing Claude's JSON response: {parse_err}. Raw response: {response_text}")
                return {
                    "rating": "\U0001F7E1 Level 2",
                    "critique": f"Raw response from AWS Bedrock: {response_text}",
                    "recommendations": "Ensure response formatting is strictly structured as JSON next time.",
                }

        except Exception as aws_err:
            print(f"Error invoking AWS Bedrock: {aws_err}")
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
