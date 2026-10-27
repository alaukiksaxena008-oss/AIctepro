import sqlite3
import os

DB_PATH = "aicte_portal.db"

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Institutes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS institutes (
        institute_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        approved_intake INTEGER NOT NULL,
        prev_year_intake INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # 2. Portal Users (Authentication & Session Binding)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL, -- 'COLLEGE_ADMIN' or 'AICTE_OFFICER'
        institute_id TEXT,  -- Bound tenant for college admins (NULL for AICTE officers)
        full_name TEXT NOT NULL,
        FOREIGN KEY (institute_id) REFERENCES institutes(institute_id)
    );
    """)

    # 3. APAAR Central Registry Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS apaar_registry (
        apaar_id TEXT PRIMARY KEY,
        full_name TEXT NOT NULL,
        gender TEXT,
        dob TEXT,
        is_active INTEGER DEFAULT 1
    );
    """)

    # 4. Staging Batches Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS staging_batches (
        batch_id TEXT PRIMARY KEY,
        institute_id TEXT NOT NULL,
        academic_year TEXT NOT NULL,
        uploaded_by TEXT NOT NULL,
        status TEXT DEFAULT 'PROCESSED', -- PROCESSED, COMMITTED, DISCARDED
        total_rows INTEGER DEFAULT 0,
        accepted_rows INTEGER DEFAULT 0,
        rejected_rows INTEGER DEFAULT 0,
        flagged_rows INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (institute_id) REFERENCES institutes(institute_id)
    );
    """)

    # 5. Staging Rows Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS staging_rows (
        row_id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        row_num INTEGER NOT NULL,
        raw_apaar_id TEXT,
        raw_name TEXT,
        course TEXT,
        seat_category TEXT,
        validation_status TEXT DEFAULT 'PENDING', -- ACCEPTED, REJECTED, FLAGGED
        rejection_reason TEXT,
        flag_reason TEXT,
        is_committed INTEGER DEFAULT 0,
        FOREIGN KEY (batch_id) REFERENCES staging_batches(batch_id)
    );
    """)

    # 6. Canonical Students Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        apaar_id TEXT NOT NULL,
        institute_id TEXT NOT NULL,
        name TEXT NOT NULL,
        course TEXT NOT NULL,
        seat_category TEXT NOT NULL,
        academic_year TEXT NOT NULL,
        batch_id TEXT NOT NULL,
        enrolled_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(apaar_id, academic_year),
        FOREIGN KEY (institute_id) REFERENCES institutes(institute_id)
    );
    """)

    # 7. Regulatory Audit Log Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        log_id INTEGER PRIMARY KEY AUTOINCREMENT,
        institute_id TEXT,
        action TEXT NOT NULL,
        actor TEXT NOT NULL,
        details TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Seed Initial Data if institutes empty
    cursor.execute("SELECT count(*) as count FROM institutes")
    if cursor.fetchone()["count"] == 0:
        cursor.executemany("""
        INSERT INTO institutes (institute_id, name, approved_intake, prev_year_intake)
        VALUES (?, ?, ?, ?);
        """, [
            ('PCT01', 'Pune College of Technology', 60, 40),
            ('COEP02', 'College of Engineering Pune', 120, 110),
            ('VIT03', 'Vishwakarma Institute of Technology', 90, 85)
        ])

    # Seed Users if empty
    cursor.execute("SELECT count(*) as count FROM users")
    if cursor.fetchone()["count"] == 0:
        cursor.executemany("""
        INSERT INTO users (username, password, role, institute_id, full_name)
        VALUES (?, ?, ?, ?, ?);
        """, [
            ('pct_admin', 'pct123', 'COLLEGE_ADMIN', 'PCT01', 'Prof. S. Joshi (PCT Dean)'),
            ('coep_admin', 'coep123', 'COLLEGE_ADMIN', 'COEP02', 'Dr. V. Kulkarni (COEP Registrar)'),
            ('aicte_officer', 'aicte123', 'AICTE_OFFICER', None, 'Shri R. Singhania (AICTE Deputy Director)')
        ])

    # Seed Registry if empty
    cursor.execute("SELECT count(*) as count FROM apaar_registry")
    if cursor.fetchone()["count"] == 0:
        cursor.executemany("""
        INSERT INTO apaar_registry (apaar_id, full_name, gender, dob)
        VALUES (?, ?, ?, ?);
        """, [
            ('482910563721', 'Aarav Sharma', 'M', '2005-04-12'),
            ('771203948856', 'Rohan Das', 'M', '2004-11-23'),
            ('998877665544', 'Ananya Iyer', 'F', '2005-08-30'),
            ('112233445566', 'Kavita Pillai', 'F', '2005-01-15'),
            ('334455667788', 'Vikram Malhotra', 'M', '2004-06-20'),
            ('556677889900', 'Sameer Verma', 'M', '2005-09-09'),
            ('667788990011', 'Aditya Patil', 'M', '2005-03-14'),
            ('889900112233', 'Sneha Kulkarni', 'F', '2005-07-21'),
            ('223344556677', 'Rahul Deshmukh', 'M', '2004-12-05'),
            ('445566778899', 'Priya Nair', 'F', '2005-05-18'),
            ('778899001122', 'Tanvi Joshi', 'F', '2005-10-09')
        ])

        # Seed existing active student in COEP02 (to demonstrate dual enrolment detection)
        cursor.execute("""
        INSERT INTO students (apaar_id, institute_id, name, course, seat_category, academic_year, batch_id)
        VALUES ('334455667788', 'COEP02', 'Vikram Malhotra', 'B.Tech', 'General', '2026-27', 'BATCH-INIT-001');
        """)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database checked and initialized.")
