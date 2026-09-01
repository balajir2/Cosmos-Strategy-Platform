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
        is_template BOOLEAN NOT NULL DEFAULT false,
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
        reviewer_role TEXT,
        sequence_order INTEGER NOT NULL DEFAULT 0
    );
    """)

    # Migrations for pre-existing tables (CREATE TABLE IF NOT EXISTS above is a
    # no-op against them) — bring them to the authoring shape idempotently.
    cursor.execute("ALTER TABLE processes ADD COLUMN IF NOT EXISTS is_template BOOLEAN NOT NULL DEFAULT false;")
    cursor.execute("UPDATE processes SET is_template = true WHERE id = (SELECT min(id) FROM processes);")

    cursor.execute("ALTER TABLE questions ADD COLUMN IF NOT EXISTS sequence_order INTEGER;")
    cursor.execute("UPDATE questions SET sequence_order = id WHERE sequence_order IS NULL;")
    cursor.execute("ALTER TABLE questions ALTER COLUMN sequence_order SET NOT NULL;")
    cursor.execute("ALTER TABLE questions ALTER COLUMN sequence_order SET DEFAULT 0;")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guidance (
        id BIGSERIAL PRIMARY KEY,
        question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        type TEXT NOT NULL,
        content TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id BIGSERIAL PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        full_name TEXT NOT NULL,
        is_active BOOLEAN NOT NULL DEFAULT true,
        is_admin BOOLEAN NOT NULL DEFAULT false,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id BIGSERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        description TEXT,
        industry_context TEXT,
        status TEXT NOT NULL DEFAULT 'Draft'
            CHECK (status IN ('Draft', 'Active', 'Completed', 'Archived')),
        process_id BIGINT NOT NULL REFERENCES processes(id),
        created_by BIGINT NOT NULL REFERENCES users(id),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_members (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('Consultant', 'ClientUser')),
        org_title TEXT,
        assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(project_id, user_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS responses (
        id BIGSERIAL PRIMARY KEY,
        question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        submitted_text TEXT,
        self_evaluation_notes TEXT,
        self_evaluation_status TEXT
            CHECK (self_evaluation_status IS NULL OR self_evaluation_status IN ('Needs Work', 'Satisfactory', 'Strong')),
        status TEXT NOT NULL DEFAULT 'Draft'
            CHECK (status IN ('Draft', 'Submitted', 'Self-Evaluated', 'Reviewed')),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE(question_id, project_id)
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_artifacts (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        artifact_type TEXT NOT NULL
            CHECK (artifact_type IN ('document', 'audio')),
        source_format TEXT NOT NULL
            CHECK (source_format IN ('pdf', 'docx', 'pptx', 'txt', 'audio')),
        purpose TEXT NOT NULL DEFAULT 'reference'
            CHECK (purpose IN ('reference', 'case_study_external', 'case_study_internal', 'case_study_resolution')),
        status TEXT NOT NULL DEFAULT 'Uploaded'
            CHECK (status IN ('Uploaded', 'Processing', 'Indexed', 'Failed', 'Transcript Needed')),
        transcript_text TEXT,
        uploaded_by BIGINT NOT NULL REFERENCES users(id),
        uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS project_kb_chunks (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        artifact_id BIGINT NOT NULL REFERENCES project_artifacts(id) ON DELETE CASCADE,
        chunk_text TEXT NOT NULL,
        embedding VECTOR(384) NOT NULL
    );
    """)

    cursor.execute("""
    CREATE INDEX IF NOT EXISTS project_kb_chunks_embedding_idx
    ON project_kb_chunks USING hnsw (embedding vector_cosine_ops);
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

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS platform_settings (
        id INTEGER PRIMARY KEY DEFAULT 1,
        active_llm_provider TEXT NOT NULL DEFAULT 'anthropic'
            CHECK (active_llm_provider IN ('anthropic', 'openai', 'gemini')),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT platform_settings_singleton CHECK (id = 1)
    );
    """)

    cursor.execute("""
    INSERT INTO platform_settings (id, active_llm_provider)
    VALUES (1, 'anthropic')
    ON CONFLICT (id) DO NOTHING;
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_sessions (
        id BIGSERIAL PRIMARY KEY,
        case_id TEXT,
        project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE,
        current_level_index INTEGER NOT NULL DEFAULT 0,
        phase TEXT NOT NULL DEFAULT 'asking'
            CHECK (phase IN ('asking', 'awaiting_answer', 'benchmarking', 'awaiting_self_rating', 'complete')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT chat_sessions_exactly_one_of_case_or_project CHECK (
            (case_id IS NOT NULL AND project_id IS NULL) OR (case_id IS NULL AND project_id IS NOT NULL)
        )
    );
    """)

    # Migration for a chat_sessions table that already exists from before this
    # column/constraint existed (case_id was NOT NULL, no project_id column) -
    # the CREATE TABLE IF NOT EXISTS above is a no-op against an existing
    # table, so bring it up to the dual-mode shape explicitly and idempotently.
    cursor.execute("ALTER TABLE chat_sessions ALTER COLUMN case_id DROP NOT NULL;")
    cursor.execute("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS project_id BIGINT REFERENCES projects(id) ON DELETE CASCADE;")
    cursor.execute(
        """
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'chat_sessions' AND constraint_name = 'chat_sessions_exactly_one_of_case_or_project';
        """
    )
    if cursor.fetchone() is None:
        cursor.execute(
            """
            ALTER TABLE chat_sessions
            ADD CONSTRAINT chat_sessions_exactly_one_of_case_or_project CHECK (
                (case_id IS NOT NULL AND project_id IS NULL) OR (case_id IS NULL AND project_id IS NOT NULL)
            );
            """
        )

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        id BIGSERIAL PRIMARY KEY,
        session_id BIGINT NOT NULL REFERENCES chat_sessions(id) ON DELETE CASCADE,
        role TEXT NOT NULL CHECK (role IN ('assistant', 'user')),
        content TEXT NOT NULL,
        message_type TEXT NOT NULL DEFAULT 'chat'
            CHECK (message_type IN ('question', 'benchmark', 'self_rating_prompt', 'chat', 'level_transition')),
        level_index INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    );
    """)

    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM processes;")
    if cursor.fetchone()[0] == 0:
        seed_database(cursor)
        conn.commit()

    # Re-point any project still sharing the template onto its own clone.
    from framework_db import migrate_existing_projects  # local import to avoid a circular import
    cloned = migrate_existing_projects()
    if cloned:
        print(f"Cloned the template framework for {cloned} existing project(s).")

    cursor.close()
    conn.close()


def seed_database(cursor):
    print("Seeding initial Cosmos Brand Compass framework data...")

    cursor.execute(
        """
        INSERT INTO processes (name, description, is_template) VALUES (%s, %s, true) RETURNING id;
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

    stage_question_seq = {}
    for stage_id, level, text, search_query, owner, reviewer in questions:
        seq = stage_question_seq.get(stage_id, 0) + 1
        stage_question_seq[stage_id] = seq
        cursor.execute(
            """
            INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role, sequence_order)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id;
            """,
            (stage_id, level, text, search_query, owner, reviewer, seq),
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
