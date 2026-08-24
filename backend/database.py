import os
from dotenv import load_dotenv
import psycopg2
from pgvector.psycopg2 import register_vector

load_dotenv()


def _require_database_url():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not set. Copy .env.example to .env at the repo root "
            "and set it to your Neon Postgres connection string."
        )
    return database_url


def get_db_connection():
    database_url = _require_database_url()
    conn = psycopg2.connect(database_url)
    register_vector(conn)
    return conn


def init_db():
    # First, create a basic connection to create the extension
    database_url = _require_database_url()
    conn = psycopg2.connect(database_url)
    cursor = conn.cursor()

    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    conn.commit()
    cursor.close()
    conn.close()

    # Now create the main connection with vector registered
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processes (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stages (
        id BIGSERIAL PRIMARY KEY,
        process_id BIGINT NOT NULL REFERENCES processes(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        sequence_order INTEGER NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id BIGSERIAL PRIMARY KEY,
        stage_id BIGINT NOT NULL REFERENCES stages(id) ON DELETE CASCADE,
        level TEXT NOT NULL,
        text TEXT NOT NULL,
        search_query TEXT,
        owner_role TEXT NOT NULL,
        reviewer_role TEXT
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guidance (
        id BIGSERIAL PRIMARY KEY,
        question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        content TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS framework_kb_chunks (
        id BIGSERIAL PRIMARY KEY,
        source_file TEXT NOT NULL,
        phase TEXT NOT NULL,
        slide_number INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding VECTOR(384) NOT NULL,
        UNIQUE (source_file, slide_number)
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS framework_kb_chunks_embedding_idx
    ON framework_kb_chunks USING hnsw (embedding vector_cosine_ops);
    """)

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM processes;")
    if cursor.fetchone()[0] == 0:
        seed_database(cursor)
        conn.commit()

    cursor.close()
    conn.close()


def seed_database(cursor):
    print("Seeding initial Cosmos Brand Compass framework data...")

    cursor.execute(
        """
        INSERT INTO processes (name, description) VALUES (%s, %s) RETURNING id;
        """,
        (
            "Aditya Birla Brand Compass V2",
            "The master strategic framework shaping brand positioning, customer alignment, active botanical claims, and visual portfolio architecture.",
        ),
    )
    process_id = cursor.fetchone()[0]

    stages = [
        ("Aim & SWOT", 1),
        ("Opportunity Expansion", 2),
        ("Consumer & Value Flows", 3),
        ("Insight Spiral", 4),
        ("Competitive Positioning", 5),
        ("Visual Architecture & Goals", 6),
    ]

    stage_ids = {}
    for name, seq in stages:
        cursor.execute(
            "INSERT INTO stages (process_id, name, sequence_order) VALUES (%s, %s, %s) RETURNING id;",
            (process_id, name, seq),
        )
        stage_ids[name] = cursor.fetchone()[0]

    questions = [
        (
            stage_ids["Aim & SWOT"],
            "Level 7: Business Model",
            "What core brand attributes does our organization command, and in which specific market context does each attribute transition from a strength to a vulnerability?",
            "core attributes strengths weaknesses brand context",
            "Brand Manager",
            "CMO",
        ),
        (
            stage_ids["Opportunity Expansion"],
            "Level 6: Market Opportunities",
            "Which adjacent category opportunities lie closest to our core capabilities, and what is the strategic justification for expansion vs. specialization?",
            "adjacent category opportunities capabilities expansion matrix",
            "Brand Manager",
            "CMO",
        ),
        (
            stage_ids["Consumer & Value Flows"],
            "Level 5: Value Distribution",
            "Among all target segments, who contributes the highest marginal share to our growth, and what specific service gaps make them vulnerable to competition?",
            "value flows customer share category growth under served",
            "CMO",
            "CEO",
        ),
        (
            stage_ids["Insight Spiral"],
            "Level 4: Insight Spiral",
            "What is the single biggest anxiety the consumer has when using our product, and how does this anxiety ladder up to a cultural or societal tension?",
            "insight spiral cultural tension anxiety experience brand relationship",
            "CMO",
            "CEO",
        ),
        (
            stage_ids["Competitive Positioning"],
            "Level 3: Brand Positioning",
            "How does our positioning reduce customer transaction risk, and how do we measure our BrandFaith Xtent and Xtensity to justify a premium price?",
            "brand faith xtent xtensity premium pricing positioning risk",
            "CMO",
            "CEO",
        ),
        (
            stage_ids["Visual Architecture & Goals"],
            "Level 2: Visual Architecture",
            "How should our visual brand architecture balance master-brand authority with individual need-state visual indicators (e.g. following the Godrej portfolio model)?",
            "visual architecture master brand need states portfolio layout",
            "Brand Manager",
            "CMO",
        ),
        (
            stage_ids["Visual Architecture & Goals"],
            "Level 1: Brand Vision",
            "What is the greater purpose our brand serves in society, and what measurable metrics (beyond financial results) track our strategic progress?",
            "brand purpose society vision goals metrics kpis",
            "CEO",
            "CEO",
        ),
    ]

    for stage_id, level, text, search_query, owner, reviewer in questions:
        cursor.execute(
            """
            INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (stage_id, level, text, search_query, owner, reviewer),
        )
        question_id = cursor.fetchone()[0]

        cursor.execute(
            """
            INSERT INTO guidance (question_id, type, content)
            VALUES (%s, 'Framework', %s);
            """,
            (
                question_id,
                f"Guidance module for {level}. Apply the appropriate Cosmos models. Address systemic value exchanges.",
            ),
        )


if __name__ == "__main__":
    init_db()
    print("Database initialisation completed successfully.")
