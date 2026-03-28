"""
database.py — SQLite database layer
Handles: users, resume analyses, history
No external ORM needed — pure sqlite3
"""
import sqlite3
import hashlib
import hmac
import os
import json
import secrets
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'ats_data.db')


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_db()
    c = conn.cursor()

    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            email       TEXT UNIQUE NOT NULL,
            password    TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            avatar_color TEXT DEFAULT '#4f6ef7'
        )
    ''')

    # Resume analyses history
    c.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER NOT NULL,
            resume_name     TEXT,
            ats_score       INTEGER,
            score_breakdown TEXT,
            max_breakdown   TEXT,
            improvements    TEXT,
            found_keywords  TEXT,
            missing_keywords TEXT,
            detected_sections TEXT,
            word_count      INTEGER,
            resume_text     TEXT,
            job_description TEXT,
            jd_match        TEXT,
            created_at      TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    ''')

    conn.commit()
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
        color = AVATAR_COLORS[len(email) % len(AVATAR_COLORS)]
        conn.execute(
            'INSERT INTO users (name, email, password, created_at, avatar_color) VALUES (?,?,?,?,?)',
            (name.strip(), email.lower().strip(), hash_password(password),
             datetime.now().isoformat(), color)
        )
        conn.commit()
        return {"success": True}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "Email already registered."}
    finally:
        conn.close()


def get_user_by_email(email: str) -> dict | None:
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE email = ?', (email.lower().strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


# ── Analysis operations ───────────────────────────────────────
def save_analysis(user_id: int, data: dict, resume_name: str = "Resume") -> int:
    conn = get_db()
    cur = conn.execute('''
        INSERT INTO analyses
        (user_id, resume_name, ats_score, score_breakdown, max_breakdown, improvements,
         found_keywords, missing_keywords, detected_sections, word_count,
         resume_text, job_description, jd_match, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
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
    conn.commit()
    aid = cur.lastrowid
    conn.close()
    return aid


def get_user_analyses(user_id: int) -> list:
    conn = get_db()
    rows = conn.execute(
        'SELECT * FROM analyses WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d['score_breakdown']  = json.loads(d['score_breakdown'] or '{}')
        d['improvements']     = json.loads(d['improvements'] or '[]')
        d['found_keywords']   = json.loads(d['found_keywords'] or '[]')
        d['missing_keywords'] = json.loads(d['missing_keywords'] or '[]')
        d['detected_sections']= json.loads(d['detected_sections'] or '[]')
        d['jd_match']         = json.loads(d['jd_match'] or '{}')
        result.append(d)
    return result


def get_analysis_by_id(analysis_id: int, user_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute(
        'SELECT * FROM analyses WHERE id = ? AND user_id = ?',
        (analysis_id, user_id)
    ).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d['score_breakdown']  = json.loads(d['score_breakdown'] or '{}')
    d['max_breakdown']    = json.loads(d.get('max_breakdown') or '{}')
    d['improvements']     = json.loads(d['improvements'] or '[]')
    d['found_keywords']   = json.loads(d['found_keywords'] or '[]')
    d['missing_keywords'] = json.loads(d['missing_keywords'] or '[]')
    d['detected_sections']= json.loads(d['detected_sections'] or '[]')
    d['jd_match']         = json.loads(d['jd_match'] or '{}')
    return d


def delete_analysis(analysis_id: int, user_id: int) -> bool:
    conn = get_db()
    conn.execute('DELETE FROM analyses WHERE id = ? AND user_id = ?', (analysis_id, user_id))
    conn.commit()
    conn.close()
    return True


def get_user_stats(user_id: int) -> dict:
    conn = get_db()
    rows = conn.execute(
        'SELECT ats_score, created_at FROM analyses WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    conn.close()
    if not rows:
        return {"total": 0, "avg_score": 0, "best_score": 0, "latest_score": 0}
    scores = [r['ats_score'] for r in rows]
    return {
        "total":        len(scores),
        "avg_score":    round(sum(scores) / len(scores)),
        "best_score":   max(scores),
        "latest_score": scores[0],
    }

def update_profile(user_id: int, name: str, email: str) -> dict:
    conn = get_db()
    try:
        existing = conn.execute('SELECT id FROM users WHERE email = ? AND id != ?', (email.lower().strip(), user_id)).fetchone()
        if existing:
            return {"success": False, "error": "Email already used by another account."}
        conn.execute('UPDATE users SET name = ?, email = ? WHERE id = ?', (name.strip(), email.lower().strip(), user_id))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def update_password(user_id: int, new_password: str) -> dict:
    conn = get_db()
    try:
        conn.execute('UPDATE users SET password = ? WHERE id = ?', (hash_password(new_password), user_id))
        conn.commit()
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()

def save_reset_token(email: str, token: str, expires_at: str) -> bool:
    conn = get_db()
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS reset_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, token TEXT, expires_at TEXT, used INTEGER DEFAULT 0)')
        conn.execute('DELETE FROM reset_tokens WHERE email = ?', (email.lower(),))
        conn.execute('INSERT INTO reset_tokens (email, token, expires_at) VALUES (?,?,?)', (email.lower(), token, expires_at))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def get_reset_token(token: str):
    conn = get_db()
    try:
        conn.execute('CREATE TABLE IF NOT EXISTS reset_tokens (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT, token TEXT, expires_at TEXT, used INTEGER DEFAULT 0)')
        row = conn.execute('SELECT * FROM reset_tokens WHERE token = ? AND used = 0', (token,)).fetchone()
        return dict(row) if row else None
    except:
        return None
    finally:
        conn.close()

def mark_token_used(token: str):
    conn = get_db()
    try:
        conn.execute('UPDATE reset_tokens SET used = 1 WHERE token = ?', (token,))
        conn.commit()
    except:
        pass
    finally:
        conn.close()
