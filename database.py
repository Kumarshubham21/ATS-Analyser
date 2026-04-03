"""
database.py — PostgreSQL (Supabase) database layer
Migrated from SQLite. All function signatures unchanged — app.py needs zero edits.
"""
import psycopg2
import psycopg2.extras
import hashlib
import hmac
import os
import json
import secrets
from datetime import datetime
# ── Connection ────────────────────────────────────────────────
# Paste your Supabase connection string in .env as:
# DATABASE_URL=postgresql://postgres:<password>@<host>:5432/postgres

def get_db():
    conn = psycopg2.connect(
        os.environ.get('DATABASE_URL'),
        cursor_factory=psycopg2.extras.RealDictCursor   # makes rows behave like dicts
    )
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    c = conn.cursor()

    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id           SERIAL PRIMARY KEY,
            name         TEXT NOT NULL,
            email        TEXT UNIQUE NOT NULL,
            password     TEXT NOT NULL,
            created_at   TEXT NOT NULL,
            avatar_color TEXT DEFAULT '#4f6ef7'
        )
    ''')

    # Resume analyses history
    c.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id                INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id           INTEGER NOT NULL REFERENCES users(id),
            resume_name       TEXT,
            ats_score         INTEGER,
            score_breakdown   TEXT,
            max_breakdown     TEXT,
            improvements      TEXT,
            found_keywords    TEXT,
            missing_keywords  TEXT,
            detected_sections TEXT,
            word_count        INTEGER,
            resume_text       TEXT,
            job_description   TEXT,
            jd_match          TEXT,
            created_at        TEXT NOT NULL
        )
    ''')

    # Password reset tokens
    c.execute('''
        CREATE TABLE IF NOT EXISTS reset_tokens (
            id         SERIAL PRIMARY KEY,
            email      TEXT,
            token      TEXT,
            expires_at TEXT,
            used       INTEGER DEFAULT 0
        )
    ''')

    conn.commit()
    c.close()
    conn.close()


# ── Password hashing ──────────────────────────────────────────
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000)
    return f"{salt}:{h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, h_hex = stored.split(':', 1)
        h = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000)
        return hmac.compare_digest(h.hex(), h_hex)
    except Exception:
        return False


# ── User operations ───────────────────────────────────────────
AVATAR_COLORS = ['#4f6ef7','#7c3aed','#059669','#dc2626','#d97706','#0891b2','#be185d']

def create_user(name: str, email: str, password: str) -> dict:
    conn = get_db()
    try:
        c = conn.cursor()
        color = AVATAR_COLORS[len(email) % len(AVATAR_COLORS)]
        c.execute(
            'INSERT INTO users (name, email, password, created_at, avatar_color) VALUES (%s,%s,%s,%s,%s)',
            (name.strip(), email.lower().strip(), hash_password(password),
             datetime.now().isoformat(), color)
        )
        conn.commit()
        return {"success": True}
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return {"success": False, "error": "Email already registered."}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE email = %s', (email.lower().strip(),))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE id = %s', (user_id,))
        row = c.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ── Analysis operations ───────────────────────────────────────
def save_analysis(user_id: int, data: dict, resume_name: str = "Resume") -> int:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('''
            INSERT INTO analyses
            (user_id, resume_name, ats_score, score_breakdown, max_breakdown, improvements,
             found_keywords, missing_keywords, detected_sections, word_count,
             resume_text, job_description, jd_match, created_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
        ''', (
            user_id,
            resume_name,
            data.get('ats_score', 0),
            json.dumps(data.get('score_breakdown', {})),
            json.dumps(data.get('max_breakdown', {})),
            json.dumps(data.get('improvements', [])),
            json.dumps(data.get('found_keywords', [])),
            json.dumps(data.get('missing_keywords', [])),
            json.dumps(data.get('detected_sections', [])),
            data.get('word_count', 0),
            data.get('resume_text', '')[:8000],
            data.get('job_description', '')[:4000],
            json.dumps(data.get('jd_match', {})),
            datetime.now().isoformat()
        ))
        aid = c.fetchone()['id']
        conn.commit()
        return aid
    finally:
        conn.close()


def _parse_analysis(d: dict) -> dict:
    """Parse JSON string fields back into Python objects."""
    d['score_breakdown']   = json.loads(d.get('score_breakdown') or '{}')
    d['max_breakdown']     = json.loads(d.get('max_breakdown') or '{}')
    d['improvements']      = json.loads(d.get('improvements') or '[]')
    d['found_keywords']    = json.loads(d.get('found_keywords') or '[]')
    d['missing_keywords']  = json.loads(d.get('missing_keywords') or '[]')
    d['detected_sections'] = json.loads(d.get('detected_sections') or '[]')
    d['jd_match']          = json.loads(d.get('jd_match') or '{}')
    return d


def get_user_analyses(user_id: int) -> list:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            'SELECT * FROM analyses WHERE user_id = %s ORDER BY created_at DESC',
            (user_id,)
        )
        return [_parse_analysis(dict(r)) for r in c.fetchall()]
    finally:
        conn.close()


def get_analysis_by_id(analysis_id: int, user_id: int) -> dict | None:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            'SELECT * FROM analyses WHERE id = %s AND user_id = %s',
            (analysis_id, user_id)
        )
        row = c.fetchone()
        return _parse_analysis(dict(row)) if row else None
    finally:
        conn.close()


def delete_analysis(analysis_id: int, user_id: int) -> bool:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('DELETE FROM analyses WHERE id = %s AND user_id = %s', (analysis_id, user_id))
        conn.commit()
        return True
    finally:
        conn.close()


def get_user_stats(user_id: int) -> dict:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute(
            'SELECT ats_score FROM analyses WHERE user_id = %s ORDER BY created_at DESC',
            (user_id,)
        )
        rows = c.fetchall()
        if not rows:
            return {"total": 0, "avg_score": 0, "best_score": 0, "latest_score": 0}
        scores = [r['ats_score'] for r in rows]
        return {
            "total":        len(scores),
            "avg_score":    round(sum(scores) / len(scores)),
            "best_score":   max(scores),
            "latest_score": scores[0],
        }
    finally:
        conn.close()


def update_profile(user_id: int, name: str, email: str) -> dict:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT id FROM users WHERE email = %s AND id != %s', (email.lower().strip(), user_id))
        if c.fetchone():
            return {"success": False, "error": "Email already used by another account."}
        c.execute('UPDATE users SET name = %s, email = %s WHERE id = %s',
                  (name.strip(), email.lower().strip(), user_id))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def update_password(user_id: int, new_password: str) -> dict:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE users SET password = %s WHERE id = %s',
                  (hash_password(new_password), user_id))
        conn.commit()
        return {"success": True}
    except Exception as e:
        conn.rollback()
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


# ── Password reset tokens ─────────────────────────────────────
def save_reset_token(email: str, token: str, expires_at: str) -> bool:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('DELETE FROM reset_tokens WHERE email = %s', (email.lower(),))
        c.execute(
            'INSERT INTO reset_tokens (email, token, expires_at) VALUES (%s,%s,%s)',
            (email.lower(), token, expires_at)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def get_reset_token(token: str) -> dict | None:
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('SELECT * FROM reset_tokens WHERE token = %s AND used = 0', (token,))
        row = c.fetchone()
        return dict(row) if row else None
    except Exception:
        return None
    finally:
        conn.close()


def mark_token_used(token: str):
    conn = get_db()
    try:
        c = conn.cursor()
        c.execute('UPDATE reset_tokens SET used = 1 WHERE token = %s', (token,))
        conn.commit()
    except Exception:
        conn.rollback()
    finally:
        conn.close()
