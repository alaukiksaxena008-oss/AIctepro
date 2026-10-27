# AICTE Student Data Ingestion & APAAR Verification Gateway

A high-integrity data ingestion and verification portal designed for AICTE and Indian technical institutions. It solves data corruption, tenant spoofing, and fraud by implementing **session-bound tenant isolation**, a **decoupled staging buffer**, a **multi-tier verification pipeline**, and an **immutable audit trail**.

---

## 🌟 Key Features

1. **Step 1: Session-Bound Authentication (No Spoofing)**
   - Institute administrators log in using AICTE-issued credentials.
   - The session permanently binds the authenticated `institute_id` (e.g., `PCT01` for Pune College of Technology) and the open academic year (`2026-27`).
   - Colleges never type their own ID in upload files, completely preventing cross-tenant spoofing.

2. **Step 2: Decoupled Staging Ingestion**
   - Uploaded sheets (CSV / TSV) are stored in an isolated staging area (`staging_batches` and `staging_rows`).
   - Nothing touches the canonical `students` master table until it passes verification.

3. **Step 3: Multi-Tier Verification Checks (In Order)**
   - **Format Check (No Table)**: Regex validation enforcing 12-digit numeric APAAR IDs (rejects invalid lengths like `12345`).
   - **Registry Check (`apaar_registry`)**: Queries the national identity registry. Rejects unregistered IDs and flags name discrepancies.
   - **Redundancy Check (`staging_rows` & `students`)**:
     - Detects in-file duplicates.
     - Rejects duplicate enrolments at the same college for the academic year.
     - Flags active enrolments at another college (dual-enrolment detection).
   - **Intake & Anomaly Checks (`institutes`)**:
     - Ensures total enrolment does not exceed approved sanctioned intake caps.
     - Flags large statistical year-over-year jumps (>50% YoY increase) for AICTE review.

4. **Step 4: Real-time Staging Report & Partial Commits**
   - Instant visual feedback: `ACCEPTED`, `REJECTED`, or `FLAGGED` with exact diagnostic reasons.
   - **Fault-Tolerant Partial Commit**: One bad row does not block valid ones. Colleges can commit clean rows immediately and re-upload only the corrected rows.

5. **Step 5: Official Master Database & Immutable Audit Log**
   - Valid rows move to the `students` master table with `UNIQUE(apaar_id, academic_year)`.
   - Every transaction is recorded in `audit_logs` for regulatory accountability.

6. **Step 6: Dual-Role Dashboards & SQL Explorer**
   - **College View**: Intake fill percentage gauge, staging report, committed student roster.
   - **AICTE Apex View**: Nationwide institutional fill rates, cross-college dual enrolment review queue, regulatory audit trail.
   - **Built-in SQL Query Explorer**: Direct read-only database query tool right from the browser.

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+

### 2. Run with One Command
```bash
chmod +x start.sh run.py
./start.sh
```

Or run manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 run.py
```

### 3. Open the Web Application
Open your browser and navigate to:
👉 **[http://127.0.0.1:8000](http://127.0.0.1:8000)**

---

## 🔑 Demo Accounts

Use the **One-Click Demo Login** buttons on the login screen, or type:

| Role | Username | Password | Organization |
| :--- | :--- | :--- | :--- |
| **College Admin** | `pct_admin` | `pct123` | Pune College of Technology (`PCT01`) |
| **College Admin** | `coep_admin` | `coep123` | College of Engineering Pune (`COEP02`) |
| **AICTE Central** | `aicte_officer` | `aicte123` | AICTE Apex Regulatory Body |

---

## 🗄️ Database Architecture

- `institutes` (`institute_id` PK): Institute intake caps, previous year numbers, and metadata.
- `users` (`user_id` PK): Issued admin credentials bound to `institute_id` and role.
- `apaar_registry` (`apaar_id` PK): National central identity registry master.
- `staging_batches` (`batch_id` PK): Tracks upload sessions and status.
- `staging_rows` (`row_id` PK): Raw rows undergoing verification with outcome and reason tags.
- `students` (`student_id` PK, `UNIQUE(apaar_id, academic_year)`): Official canonical enrolment master.
- `audit_logs` (`log_id` PK): Tamper-evident regulatory audit trail.
