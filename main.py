import os
import re
import uuid
import sqlite3
from typing import List, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pydantic import BaseModel
from db import get_connection, init_db

app = FastAPI(title="AICTE Student Data Ingestion & APAAR Verification Engine")

init_db()

class LoginRequest(BaseModel):
    username: str
    password: str

class QueryRequest(BaseModel):
    query: str

class CommitRequest(BaseModel):
    batch_id: str
    institute_id: str
    actor: str = "pct_admin@edu.in"

@app.post("/api/login")
def login(req: LoginRequest):
    conn = get_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE username = ? AND password = ?", 
        (req.username.strip(), req.password.strip())
    ).fetchone()

    if not user:
        conn.close()
        raise HTTPException(status_code=401, detail="Invalid username or password issued by AICTE.")

    user_dict = dict(user)
    institute_name = None
    approved_intake = None
    
    if user_dict["institute_id"]:
        inst = conn.execute(
            "SELECT * FROM institutes WHERE institute_id = ?", 
            (user_dict["institute_id"],)
        ).fetchone()
        if inst:
            institute_name = inst["name"]
            approved_intake = inst["approved_intake"]

    # Active academic year window
    academic_year = "2026-27"
    token = f"TOKEN-{uuid.uuid4().hex[:12]}"

    # Audit login
    conn.execute("""
    INSERT INTO audit_logs (institute_id, action, actor, details)
    VALUES (?, 'USER_LOGIN', ?, ?)
    """, (
        user_dict["institute_id"] or 'AICTE',
        user_dict["username"],
        f"Authenticated user '{user_dict['username']}' with role '{user_dict['role']}'. Active window: {academic_year}."
    ))
    conn.commit()
    conn.close()

    return {
        "token": token,
        "username": user_dict["username"],
        "full_name": user_dict["full_name"],
        "role": user_dict["role"],
        "institute_id": user_dict["institute_id"],
        "institute_name": institute_name,
        "approved_intake": approved_intake,
        "academic_year": academic_year
    }

@app.get("/api/institutes")
def list_institutes():
    conn = get_connection()
    institutes = conn.execute("SELECT * FROM institutes").fetchall()
    conn.close()
    return [dict(ix) for ix in institutes]

@app.get("/api/dashboard/{institute_id}")
def get_institute_dashboard(institute_id: str):
    conn = get_connection()
    inst = conn.execute("SELECT * FROM institutes WHERE institute_id = ?", (institute_id,)).fetchone()
    if not inst:
        conn.close()
        raise HTTPException(status_code=404, detail="Institute not found")

    inst_dict = dict(inst)
    
    confirmed_count = conn.execute(
        "SELECT COUNT(*) as count FROM students WHERE institute_id = ?", 
        (institute_id,)
    ).fetchone()["count"]

    batches = conn.execute(
        "SELECT * FROM staging_batches WHERE institute_id = ? ORDER BY created_at DESC LIMIT 10",
        (institute_id,)
    ).fetchall()

    students = conn.execute(
        "SELECT * FROM students WHERE institute_id = ? ORDER BY enrolled_at DESC LIMIT 50",
        (institute_id,)
    ).fetchall()

    conn.close()
    return {
        "institute": inst_dict,
        "confirmed_count": confirmed_count,
        "fill_percentage": round((confirmed_count / inst_dict["approved_intake"]) * 100, 1) if inst_dict["approved_intake"] else 0,
        "batches": [dict(b) for b in batches],
        "students": [dict(s) for s in students]
    }

@app.get("/api/download/sample-excel")
def download_sample_excel():
    if not os.path.exists("pune_college_students.xlsx"):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        "pune_college_students.xlsx", 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 
        filename="pune_college_students.xlsx"
    )

@app.get("/api/download/sample-csv")
def download_sample_csv():
    if not os.path.exists("pune_college_students.csv"):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        "pune_college_students.csv", 
        media_type="text/csv", 
        filename="pune_college_students.csv"
    )

@app.get("/api/download/test-clean-csv")
def download_test_clean_csv():
    if not os.path.exists("test_students_to_commit.csv"):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        "test_students_to_commit.csv", 
        media_type="text/csv", 
        filename="test_students_to_commit.csv"
    )

@app.get("/api/batches/{batch_id}")
def get_batch_details(batch_id: str):
    conn = get_connection()
    batch = conn.execute("SELECT * FROM staging_batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if not batch:
        conn.close()
        raise HTTPException(status_code=404, detail="Batch not found")
    
    rows = conn.execute(
        "SELECT * FROM staging_rows WHERE batch_id = ? ORDER BY row_num ASC", 
        (batch_id,)
    ).fetchall()
    conn.close()
    return {
        "batch": dict(batch),
        "rows": [dict(r) for r in rows]
    }

@app.post("/api/upload")
async def upload_student_data(
    institute_id: str = Form(...),
    academic_year: str = Form("2026-27"),
    uploaded_by: str = Form("admin@college.edu"),
    file_content: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
):
    conn = get_connection()
    inst = conn.execute("SELECT * FROM institutes WHERE institute_id = ?", (institute_id,)).fetchone()
    if not inst:
        conn.close()
        raise HTTPException(status_code=400, detail="Unknown institute")

    raw_text = ""
    if file:
        filename = (file.filename or "").lower()
        content_bytes = await file.read()
        if filename.endswith(".xlsx"):
            import io
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(content_bytes), data_only=True)
            ws = wb.active
            rows_list = []
            for row in ws.iter_rows(values_only=True):
                if any(row):
                    # take first 4 columns: apaar_id, name, course, seat_category
                    row_vals = [str(c).strip() if c is not None else "" for c in row[:4]]
                    rows_list.append(",".join(row_vals))
            raw_text = "\n".join(rows_list)
        else:
            raw_text = content_bytes.decode("utf-8", errors="replace")
    elif file_content:
        raw_text = file_content
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="No student data provided")

    lines = [line.strip() for line in raw_text.strip().splitlines() if line.strip()]
    if not lines:
        conn.close()
        raise HTTPException(status_code=400, detail="Empty data submitted")

    header_line = lines[0].lower()
    has_header = "apaar" in header_line or "name" in header_line or "course" in header_line
    data_lines = lines[1:] if has_header else lines

    batch_id = f"BATCH-{uuid.uuid4().hex[:8].upper()}"

    conn.execute("""
    INSERT INTO staging_batches (batch_id, institute_id, academic_year, uploaded_by, status, total_rows)
    VALUES (?, ?, ?, ?, 'PROCESSED', ?)
    """, (batch_id, institute_id, academic_year, uploaded_by, len(data_lines)))

    seen_apaar_in_batch = set()
    accepted_count = 0
    rejected_count = 0
    flagged_count = 0

    current_confirmed = conn.execute(
        "SELECT COUNT(*) as count FROM students WHERE institute_id = ? AND academic_year = ?",
        (institute_id, academic_year)
    ).fetchone()["count"]

    approved_intake = inst["approved_intake"]
    prev_year_intake = inst["prev_year_intake"]

    staging_records = []

    for idx, line in enumerate(data_lines, start=1):
        parts = [p.strip() for p in re.split(r'[\t,]', line)]
        if len(parts) < 2:
            continue
        
        raw_apaar = parts[0] if len(parts) > 0 else ""
        raw_name = parts[1] if len(parts) > 1 else ""
        raw_course = parts[2] if len(parts) > 2 else "B.Tech"
        raw_category = parts[3] if len(parts) > 3 else "General"

        status = "ACCEPTED"
        reject_reason = None
        flag_reason = None

        # Check 1: Format Check (12 numeric digits)
        if not re.match(r'^\d{12}$', raw_apaar):
            status = "REJECTED"
            reject_reason = f"Invalid APAAR ID format (got '{raw_apaar}', must be exactly 12 digits)"

        # Check 2: Central APAAR Registry Lookup
        if status == "ACCEPTED":
            registry_match = conn.execute(
                "SELECT * FROM apaar_registry WHERE apaar_id = ?", 
                (raw_apaar,)
            ).fetchone()

            if not registry_match:
                status = "REJECTED"
                reject_reason = "Not found in APAAR registry"
            else:
                reg_name = registry_match["full_name"]
                if raw_name.lower().strip() != reg_name.lower().strip():
                    status = "FLAGGED"
                    flag_reason = f"Name discrepancy (Registry: '{reg_name}', Uploaded: '{raw_name}')"

        # Check 3: Redundancy / Duplication Checks
        if status in ("ACCEPTED", "FLAGGED"):
            if raw_apaar in seen_apaar_in_batch:
                status = "REJECTED"
                reject_reason = "Duplicate entry within uploaded batch file"
                flag_reason = None
            else:
                seen_apaar_in_batch.add(raw_apaar)

        if status in ("ACCEPTED", "FLAGGED"):
            existing_here = conn.execute(
                "SELECT * FROM students WHERE apaar_id = ? AND academic_year = ? AND institute_id = ?",
                (raw_apaar, academic_year, institute_id)
            ).fetchone()
            if existing_here:
                status = "REJECTED"
                reject_reason = f"Already officially enrolled at this institute for {academic_year}"
                flag_reason = None

        if status in ("ACCEPTED", "FLAGGED"):
            existing_other = conn.execute("""
                SELECT s.*, i.name as inst_name 
                FROM students s 
                JOIN institutes i ON s.institute_id = i.institute_id 
                WHERE s.apaar_id = ? AND s.academic_year = ? AND s.institute_id != ?
            """, (raw_apaar, academic_year, institute_id)).fetchone()

            if existing_other:
                status = "FLAGGED"
                reason_detail = f"Potential dual-enrolment: Active at {existing_other['inst_name']} ({existing_other['institute_id']})"
                flag_reason = f"{flag_reason}; {reason_detail}" if flag_reason else reason_detail

        # Check 4: Capacity & Anomaly Checks
        if status == "ACCEPTED":
            tentative_total = current_confirmed + accepted_count + 1
            if tentative_total > approved_intake:
                status = "FLAGGED"
                flag_reason = f"Exceeds approved institute intake quota ({approved_intake} seats)"
            elif prev_year_intake > 0 and (tentative_total / prev_year_intake) > 1.5:
                status = "FLAGGED"
                flag_reason = f"Year-over-Year statistical intake spike (>50% YoY jump from {prev_year_intake})"

        if status == "ACCEPTED":
            accepted_count += 1
        elif status == "REJECTED":
            rejected_count += 1
        elif status == "FLAGGED":
            flagged_count += 1

        staging_records.append((
            batch_id, idx, raw_apaar, raw_name, raw_course, raw_category,
            status, reject_reason, flag_reason
        ))

    conn.executemany("""
    INSERT INTO staging_rows (
        batch_id, row_num, raw_apaar_id, raw_name, course, seat_category,
        validation_status, rejection_reason, flag_reason
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, staging_records)

    conn.execute("""
    UPDATE staging_batches 
    SET accepted_rows = ?, rejected_rows = ?, flagged_rows = ?
    WHERE batch_id = ?
    """, (accepted_count, rejected_count, flagged_count, batch_id))

    conn.execute("""
    INSERT INTO audit_logs (institute_id, action, actor, details)
    VALUES (?, 'BATCH_UPLOAD', ?, ?)
    """, (institute_id, uploaded_by, f"Uploaded {len(staging_records)} rows in batch {batch_id}. Accepted: {accepted_count}, Rejected: {rejected_count}, Flagged: {flagged_count}"))

    conn.commit()
    conn.close()

    return {
        "batch_id": batch_id,
        "total": len(staging_records),
        "accepted": accepted_count,
        "rejected": rejected_count,
        "flagged": flagged_count,
        "message": "File parsed and validated in staging."
    }

@app.post("/api/commit")
def commit_batch(req: CommitRequest):
    conn = get_connection()
    batch = conn.execute("SELECT * FROM staging_batches WHERE batch_id = ?", (req.batch_id,)).fetchone()
    if not batch:
        conn.close()
        raise HTTPException(status_code=404, detail="Batch not found")

    if batch["status"] == "COMMITTED":
        conn.close()
        return {"message": "Batch already committed", "committed_count": 0}

    accepted_rows = conn.execute("""
    SELECT * FROM staging_rows 
    WHERE batch_id = ? AND validation_status = 'ACCEPTED' AND is_committed = 0
    """, (req.batch_id,)).fetchall()

    committed_count = 0
    for r in accepted_rows:
        try:
            conn.execute("""
            INSERT INTO students (apaar_id, institute_id, name, course, seat_category, academic_year, batch_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                r["raw_apaar_id"], req.institute_id, r["raw_name"],
                r["course"], r["seat_category"], batch["academic_year"], req.batch_id
            ))
            conn.execute("UPDATE staging_rows SET is_committed = 1 WHERE row_id = ?", (r["row_id"],))
            committed_count += 1
        except sqlite3.IntegrityError:
            conn.execute("""
            UPDATE staging_rows 
            SET validation_status = 'REJECTED', rejection_reason = 'Integrity constraint violation during commit'
            WHERE row_id = ?
            """, (r["row_id"],))

    conn.execute("UPDATE staging_batches SET status = 'COMMITTED' WHERE batch_id = ?", (req.batch_id,))

    conn.execute("""
    INSERT INTO audit_logs (institute_id, action, actor, details)
    VALUES (?, 'BATCH_COMMITTED', ?, ?)
    """, (req.institute_id, req.actor, f"Committed {committed_count} accepted rows from batch {req.batch_id} into canonical students table."))

    conn.commit()
    conn.close()

    return {
        "batch_id": req.batch_id,
        "status": "COMMITTED",
        "committed_count": committed_count,
        "message": f"Successfully moved {committed_count} verified students to official database."
    }

@app.get("/api/aicte-overview")
def aicte_overview():
    conn = get_connection()
    institutes = conn.execute("SELECT * FROM institutes").fetchall()
    
    inst_summaries = []
    for inst in institutes:
        c_count = conn.execute("SELECT COUNT(*) as c FROM students WHERE institute_id = ?", (inst["institute_id"],)).fetchone()["c"]
        inst_summaries.append({
            "institute_id": inst["institute_id"],
            "name": inst["name"],
            "approved_intake": inst["approved_intake"],
            "prev_year_intake": inst["prev_year_intake"],
            "enrolled_count": c_count,
            "fill_percentage": round((c_count / inst["approved_intake"]) * 100, 1) if inst["approved_intake"] else 0
        })

    flagged = conn.execute("""
        SELECT sr.*, sb.institute_id, sb.academic_year, i.name as inst_name
        FROM staging_rows sr
        JOIN staging_batches sb ON sr.batch_id = sb.batch_id
        JOIN institutes i ON sb.institute_id = i.institute_id
        WHERE sr.validation_status = 'FLAGGED'
        ORDER BY sr.row_id DESC LIMIT 30
    """).fetchall()

    logs = conn.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 20").fetchall()

    conn.close()
    return {
        "institutes": inst_summaries,
        "flagged_issues": [dict(f) for f in flagged],
        "audit_logs": [dict(l) for l in logs]
    }

@app.post("/api/query")
def run_custom_query(req: QueryRequest):
    cleaned = req.query.strip()
    if not cleaned.lower().startswith("select") and not cleaned.lower().startswith("pragma"):
        raise HTTPException(status_code=400, detail="Only SELECT and PRAGMA read queries are allowed in this explorer.")
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(cleaned)
        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return {"columns": columns, "rows": rows, "count": len(rows)}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/", response_class=HTMLResponse)
def serve_frontend():
    with open("frontend.html", "r", encoding="utf-8") as f:
        return f.read()
