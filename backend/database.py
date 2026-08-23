import os
import sqlite3
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "cosmos_platform.db")

def get_db_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Enable foreign keys
    cursor.execute("PRAGMA foreign_keys = ON;")
    
    # 1. Processes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS processes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    # 2. Stages Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS stages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        process_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        sequence_order INTEGER NOT NULL,
        FOREIGN KEY (process_id) REFERENCES processes (id) ON DELETE CASCADE
    );
    """)
    
    # 3. Questions Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        stage_id INTEGER NOT NULL,
        level TEXT NOT NULL,
        text TEXT NOT NULL,
        search_query TEXT,
        owner_role TEXT NOT NULL,
        reviewer_role TEXT,
        FOREIGN KEY (stage_id) REFERENCES stages (id) ON DELETE CASCADE
    );
    """)
    
    # 4. Guidance Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS guidance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        type TEXT NOT NULL, -- 'Framework', 'Case Study', 'Tool'
        content TEXT NOT NULL,
        FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
    );
    """)
    
    # 5. Responses Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question_id INTEGER NOT NULL,
        client_case_id TEXT NOT NULL, -- e.g. 'blazar_project_2026'
        submitted_text TEXT,
        status TEXT DEFAULT 'Draft', -- 'Draft', 'Locked', 'Reviewed'
        rating TEXT,
        critique TEXT,
        recommendations TEXT,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
        UNIQUE(question_id, client_case_id)
    );
    """)
    
    conn.commit()
    
    # Seed initial data if database is empty
    cursor.execute("SELECT COUNT(*) FROM processes;")
    if cursor.fetchone()[0] == 0:
        seed_database(cursor)
        conn.commit()
        
    conn.close()

def seed_database(cursor):
    print("Seeding initial Cosmos Brand Compass framework data...")
    
    # Seed 1: Madura Brand Compass V2 Process
    cursor.execute("""
    INSERT INTO processes (name, description) VALUES (
        'Aditya Birla Brand Compass V2',
        'The master strategic framework shaping brand positioning, customer alignment, active botanical claims, and visual portfolio architecture.'
    );
    """)
    process_id = cursor.lastrowid
    
    # Seed 2: Stages
    stages = [
        ("Aim & SWOT", 1),
        ("Opportunity Expansion", 2),
        ("Consumer & Value Flows", 3),
        ("Insight Spiral", 4),
        ("Competitive Positioning", 5),
        ("Visual Architecture & Goals", 6)
    ]
    
    stage_ids = {}
    for name, seq in stages:
        cursor.execute("INSERT INTO stages (process_id, name, sequence_order) VALUES (?, ?, ?);", (process_id, name, seq))
        stage_ids[name] = cursor.lastrowid
        
    # Seed 3: Questions with ownership, levels, and search queries mapped
    questions = [
        # Stage 1: Aim & SWOT
        (stage_ids["Aim & SWOT"], "Level 7: Business Model", 
         "What core brand attributes does our organization command, and in which specific market context does each attribute transition from a strength to a vulnerability?",
         "core attributes strengths weaknesses brand context", "Brand Manager", "CMO"),
         
        # Stage 2: Opportunity Expansion
        (stage_ids["Opportunity Expansion"], "Level 6: Market Opportunities",
         "Which adjacent category opportunities lie closest to our core capabilities, and what is the strategic justification for expansion vs. specialization?",
         "adjacent category opportunities capabilities expansion matrix", "Brand Manager", "CMO"),
         
        # Stage 3: Consumer & Value Flows
        (stage_ids["Consumer & Value Flows"], "Level 5: Value Distribution",
         "Among all target segments, who contributes the highest marginal share to our growth, and what specific service gaps make them vulnerable to competition?",
         "value flows customer share category growth under served", "CMO", "CEO"),
         
        # Stage 4: Insight Spiral
        (stage_ids["Insight Spiral"], "Level 4: Insight Spiral",
         "What is the single biggest anxiety the consumer has when using our product, and how does this anxiety ladder up to a cultural or societal tension?",
         "insight spiral cultural tension anxiety experience brand relationship", "CMO", "CEO"),
         
        # Stage 5: Competitive Positioning
        (stage_ids["Competitive Positioning"], "Level 3: Brand Positioning",
         "How does our positioning reduce customer transaction risk, and how do we measure our BrandFaith Xtent and Xtensity to justify a premium price?",
         "brand faith xtent xtensity premium pricing positioning risk", "CMO", "CEO"),
         
        # Stage 6: Visual Architecture & Goals
        (stage_ids["Visual Architecture & Goals"], "Level 2: Visual Architecture",
         "How should our visual brand architecture balance master-brand authority with individual need-state visual indicators (e.g. following the Godrej portfolio model)?",
         "visual architecture master brand need states portfolio layout", "Brand Manager", "CMO"),
        
        (stage_ids["Visual Architecture & Goals"], "Level 1: Brand Vision",
         "What is the greater purpose our brand serves in society, and what measurable metrics (beyond financial results) track our strategic progress?",
         "brand purpose society vision goals metrics kpis", "CEO", "CEO")
    ]
    
    for stage_id, level, text, search_query, owner, reviewer in questions:
        cursor.execute("""
        INSERT INTO questions (stage_id, level, text, search_query, owner_role, reviewer_role)
        VALUES (?, ?, ?, ?, ?, ?);
        """, (stage_id, level, text, search_query, owner, reviewer))
        question_id = cursor.lastrowid
        
        # Add basic Guidance for each question
        cursor.execute("""
        INSERT INTO guidance (question_id, type, content)
        VALUES (?, 'Framework', ?);
        """, (question_id, f"Guidance module for {level}. Apply the appropriate Cosmos models. Address systemic value exchanges."))

if __name__ == "__main__":
    init_db()
    print("Database initialisation completed successfully.")
