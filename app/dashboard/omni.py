#!/usr/bin/env python3
"""
Omni-Studio Dashboard — Single-file app.
Everything in one place: database, agents, swarm, scheduler, plugins, web UI, sample library.
Run: python3 omni.py
"""
import os, sys, json, time, asyncio, importlib, importlib.util, sqlite3
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
import shutil
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pydantic import BaseModel
import requests
import httpx

# === Config ===
BASE = Path(__file__).parent
sys.path.insert(0, str(BASE))

try:
    from dotenv import load_dotenv
    load_dotenv(BASE.parent / ".env")
except ImportError:
    pass

KIMI_API_KEY = os.getenv("KIMI_API_KEY", "")
KIMI_BASE_URL = "https://api.kimi.com/coding"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
XAI_API_KEY = os.getenv("XAI_API_KEY", "")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.getenv("GOOGLE_MODEL", "gemini-2.5-flash")

HOST = "127.0.0.1"
PORT = 8500
DB_PATH = BASE / "data" / "dashboard.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# === Disk Cleaner ===
MAX_DISK_GB = 700
CLEAN_PATHS = [
    Path.home() / "Library" / "Caches",
    Path.home() / "Library" / "Logs",
    BASE / "data" / "logs",
    Path("/tmp"),
]
CLEAN_EXTENSIONS = {".log", ".tmp", ".cache", ".bak", ".old"}
CLEAN_MAX_AGE_DAYS = 30

def get_disk_usage_gb(path="/"):
    """Get disk usage in GB for a path."""
    import shutil
    usage = shutil.disk_usage(path)
    return round(usage.used / (1024**3), 2)

def clean_old_files():
    """Remove old temp/cache files. Returns bytes freed."""
    import glob
    from datetime import timedelta
    freed = 0
    cutoff = datetime.now() - timedelta(days=CLEAN_MAX_AGE_DAYS)

    for clean_dir in CLEAN_PATHS:
        if not clean_dir.exists():
            continue
        for pattern in CLEAN_EXTENSIONS:
            for f in glob.glob(str(clean_dir / f"**/*{pattern}"), recursive=True):
                try:
                    p = Path(f)
                    if p.stat().st_mtime < cutoff.timestamp():
                        size = p.stat().st_size
                        p.unlink()
                        freed += size
                except Exception:
                    pass
    return freed

def run_disk_cleaner():
    """Main cleaner: check usage, clean if over limit, return report."""
    usage_gb = get_disk_usage_gb()
    report = {"usage_gb": usage_gb, "limit_gb": MAX_DISK_GB, "cleaned_bytes": 0, "actions": []}

    if usage_gb > MAX_DISK_GB:
        freed = clean_old_files()
        report["cleaned_bytes"] = freed
        report["actions"].append(f"Cleaned old files: {freed / (1024**3):.2f} GB freed")

        # Clean __pycache__ dirs
        for cache in BASE.rglob("__pycache__"):
            try:
                import shutil
                size = sum(f.stat().st_size for f in cache.rglob("*") if f.is_file())
                shutil.rmtree(cache)
                report["cleaned_bytes"] += size
                report["actions"].append(f"Removed {cache.name}: {size / (1024**3):.2f} GB")
            except Exception:
                pass

        # Clean old backups
        backup_dir = BASE / "data" / "backups"
        if backup_dir.exists():
            backups = sorted(backup_dir.glob("*.bak"), key=lambda x: x.stat().st_mtime)
            while len(backups) > 5 and get_disk_usage_gb() > MAX_DISK_GB:
                old = backups.pop(0)
                size = old.stat().st_size
                old.unlink()
                report["cleaned_bytes"] += size
                report["actions"].append(f"Removed old backup: {old.name}")

        report["final_usage_gb"] = get_disk_usage_gb()
    else:
        report["actions"].append(f"Within limit ({usage_gb}/{MAX_DISK_GB} GB)")

    return report

# === Audio Ingestion ===
WATCH_DIR = BASE / "ingest_folder"
PROCESSED_DIR = BASE / "processed_folder"
WATCH_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# === WebBridge (Browser Agent) ===
import httpx

async def web_search(query: str, num_results: int = 5) -> list:
    """Search the web using DuckDuckGo API."""
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get("https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "skip_disambig": 1})
        data = r.json()
        results = []
        for topic in data.get("RelatedTopics", [])[:num_results]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append({"title": topic.get("Text", "")[:100], "url": topic.get("FirstURL", ""), "snippet": topic.get("Text", "")})
        return results

async def web_fetch(url: str, max_chars: int = 5000) -> str:
    """Fetch and extract text content from a URL."""
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        r = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
        text = r.text
        # Simple HTML to text
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]

async def webbridge_task(objective: str) -> dict:
    """Browser agent: research objective on the web."""
    from omni import call_llm, log_activity
    await log_activity("webbridge", f"Researching: {objective[:80]}")

    # Step 1: Generate search queries
    queries = await call_llm("kimi", "kimi-for-coding/kimi-for-coding-highspeed",
        [{"role": "user", "content": f"Generate 3 search queries for: {objective}\nReturn JSON array of strings only."}],
        "Return only a JSON array of search query strings.")
    try:
        queries = json.loads(queries.strip().replace("```json", "").replace("```", ""))
    except Exception:
        queries = [objective]

    # Step 2: Search and fetch
    all_results = []
    for q in queries[:3]:
        results = await web_search(q)
        for r in results[:2]:
            if r.get("url"):
                try:
                    content = await web_fetch(r["url"])
                    r["content"] = content[:2000]
                except Exception:
                    r["content"] = r.get("snippet", "")
                all_results.append(r)

    # Step 3: Synthesize
    context = "\n\n".join([f"[{r['title']}] {r.get('content', '')[:500]}" for r in all_results[:5]])
    synthesis = await call_llm("kimi", "kimi-for-coding/kimi-for-coding-highspeed",
        [{"role": "user", "content": f"Synthesize findings for: {objective}\n\nSources:\n{context}\n\nProvide comprehensive answer."}],
        "You are a research analyst. Synthesize information clearly.")

    await log_activity("webbridge", f"Completed research: {objective[:60]}")
    return {"status": "completed", "objective": objective, "sources": len(all_results), "synthesis": synthesis, "results": all_results[:5]}


# === Autonomous Agent ===
async def autonomous_execute(objective: str, max_steps: int = 5) -> dict:
    """Plan and execute complex goals autonomously."""
    from omni import call_llm, log_activity, get_agents, update_agent
    await log_activity("autonomous", f"Starting: {objective[:80]}")

    # Step 1: Plan
    plan_response = await call_llm("kimi", "kimi-for-coding/kimi-k2-thinking",
        [{"role": "user", "content": f"Create a plan for: {objective}\nMax steps: {max_steps}\nReturn JSON: {{\"steps\": [{{\"action\": \"...\", \"tool\": \"search|code|analyze|execute\", \"input\": \"...\"}}]}}"}],
        "Return only valid JSON with steps array.")
    try:
        plan = json.loads(plan_response.strip().replace("```json", "").replace("```", ""))
        steps = plan.get("steps", [])
    except Exception:
        steps = [{"action": objective, "tool": "execute", "input": objective}]

    # Step 2: Execute each step
    results = []
    for i, step in enumerate(steps[:max_steps]):
        action = step.get("action", "")
        tool = step.get("tool", "execute")
        step_input = step.get("input", action)

        await log_activity("autonomous", f"Step {i+1}/{len(steps)}: {action[:60]}")

        try:
            if tool == "search":
                result = await web_search(step_input)
                result = json.dumps(result)
            elif tool == "code":
                result = await call_llm("kimi", "kimi-for-coding/k2p7",
                    [{"role": "user", "content": step_input}],
                    "You are a code expert. Write clean, working code.")
            elif tool == "analyze":
                result = await call_llm("kimi", "kimi-for-coding/kimi-k2-thinking",
                    [{"role": "user", "content": f"Analyze: {step_input}"}],
                    "You are an analyst. Provide detailed analysis.")
            else:
                result = await call_llm("kimi", "kimi-for-coding/k2p7",
                    [{"role": "user", "content": step_input}],
                    "Complete this task precisely.")

            results.append({"step": i+1, "action": action, "status": "success", "result": str(result)[:1000]})
        except Exception as e:
            results.append({"step": i+1, "action": action, "status": "error", "result": str(e)[:300]})

    # Step 3: Final synthesis
    results_text = "\n".join([f"Step {r['step']}: {r['action'][:50]} → {r['status']}" for r in results])
    summary = await call_llm("kimi", "kimi-for-coding/kimi-k2-thinking",
        [{"role": "user", "content": f"Objective: {objective}\n\nExecution results:\n{results_text}\n\nProvide final summary and outcome."}],
        "You are a project manager. Summarize completion status.")

    await log_activity("autonomous", f"Completed: {objective[:60]}")
    return {"status": "completed", "objective": objective, "steps_executed": len(results), "results": results, "summary": summary}

# === Kimi Daily Pipeline (Agentic Upgrade) ===
import sqlite3 as _sync_sqlite3

VAULT_DIR = BASE / "data" / "vault"
VAULT_DIR.mkdir(parents=True, exist_ok=True)

KIMI_DAILY_DB = BASE / "data" / "kimi_daily.db"

def _init_kimi_daily_db():
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT, transcript TEXT,
            music_ip TEXT, crm_notes TEXT, sops TEXT,
            tools_called TEXT, status TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS vault (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT, title TEXT, content TEXT,
            source_run_id INTEGER, tags TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    conn.close()

_init_kimi_daily_db()

# --- Tool Functions (agents call these) ---

async def tool_create_document(title: str, content: str, category: str = "docs") -> dict:
    """Store document in local vault (replaces Notion)."""
    doc = {
        "title": title,
        "content": content[:5000],
        "category": category,
        "created_at": datetime.now().isoformat()
    }
    doc_file = VAULT_DIR / f"{category}_{int(time.time())}.json"
    doc_file.write_text(json.dumps(doc, indent=2))

    # Also store in DB
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    conn.execute("INSERT INTO vault (category, title, content, tags) VALUES (?,?,?,?)",
                 (category, title, content[:5000], json.dumps([category])))
    conn.commit(); conn.close()

    return {"status": "created", "file": str(doc_file)}

async def tool_send_slack_summary(channel: str, message: str) -> dict:
    """Send summary to Slack webhook."""
    slack_url = os.getenv("SLACK_WEBHOOK_URL", "")
    if not slack_url:
        return {"status": "skipped", "message": "No SLACK_WEBHOOK_URL set"}

    async with httpx.AsyncClient() as client:
        r = await client.post(slack_url, json={"text": message[:3000]})
        return {"status": "sent" if r.status_code == 200 else "error"}

async def tool_vault_store(category: str, title: str, content: str, tags: list = None) -> dict:
    """Store structured output in vault for persistence."""
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    conn.execute("INSERT INTO vault (category, title, content, tags) VALUES (?,?,?,?)",
                 (category, title, content, json.dumps(tags or [])))
    conn.commit(); conn.close()

    # Also save to file
    vault_file = VAULT_DIR / f"{category}_{int(time.time())}.json"
    vault_file.write_text(json.dumps({"category": category, "title": title, "content": content, "tags": tags}, indent=2))
    return {"status": "stored", "file": str(vault_file)}

async def tool_vault_search(query: str, category: str = "") -> list:
    """Search vault for stored content."""
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    conn.row_factory = _sync_sqlite3.Row
    sql = "SELECT * FROM vault WHERE (title LIKE ? OR content LIKE ?)"
    params = [f"%{query}%", f"%{query}%"]
    if category:
        sql += " AND category=?"
        params.append(category)
    rows = conn.execute(sql + " ORDER BY created_at DESC LIMIT 10", params).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# --- WebBridge Context Pull ---

async def webbridge_pull_context(sources: list = None) -> str:
    """Pull context from local vault and external sources."""
    context_parts = []
    sources = sources or ["vault", "crm"]

    for source in sources:
        if source == "vault":
            # Pull recent vault entries
            try:
                conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
                conn.row_factory = _sync_sqlite3.Row
                rows = conn.execute(
                    "SELECT title, content FROM vault ORDER BY created_at DESC LIMIT 5"
                ).fetchall()
                conn.close()
                for row in rows:
                    context_parts.append(f"[Vault] {row['title']}: {row['content'][:200]}")
            except Exception:
                pass

        elif source == "crm":
            crm_url = os.getenv("CRM_API_URL", "")
            if crm_url:
                try:
                    async with httpx.AsyncClient() as client:
                        r = await client.get(crm_url + "/contacts?limit=5")
                        for contact in r.json().get("contacts", [])[:3]:
                            context_parts.append(f"[CRM] {contact.get('name', '')} - {contact.get('company', '')}")
                except Exception:
                    pass

    return "\n".join(context_parts) if context_parts else "No external context available"

# --- Agent Swarm Extraction ---

async def swarm_extract_music_ip(transcript: str) -> dict:
    """Specialized agent: extract music IP from transcript."""
    from omni import call_llm
    result = await call_llm("kimi", "kimi-for-coding/kimi-k2-thinking",
        [{"role": "user", "content": f"Extract music IP from this transcript. Return JSON:\n{{\"artists\": [], \"tracks\": [], \"albums\": [], \"labels\": [], \"rights\": [], \"deals\": []}}\n\nTranscript:\n{transcript[:4000]}"}],
        "You are a music industry analyst. Extract IP details precisely. Return only valid JSON.")
    try:
        return json.loads(result.strip().replace("```json", "").replace("```", ""))
    except Exception:
        return {"raw": result[:1000]}

async def swarm_extract_crm_notes(transcript: str) -> dict:
    """Specialized agent: extract CRM notes from transcript."""
    from omni import call_llm
    result = await call_llm("kimi", "kimi-for-coding/kimi-k2-thinking",
        [{"role": "user", "content": f"Extract CRM data from transcript. Return JSON:\n{{\"contacts\": [], \"companies\": [], \"follow_ups\": [], \"opportunities\": [], \"notes\": []}}\n\nTranscript:\n{transcript[:4000]}"}],
        "You are a CRM specialist. Extract contact and relationship data. Return only valid JSON.")
    try:
        return json.loads(result.strip().replace("```json", "").replace("```", ""))
    except Exception:
        return {"raw": result[:1000]}

async def swarm_extract_sops(transcript: str) -> dict:
    """Specialized agent: extract SOPs from transcript."""
    from omni import call_llm
    result = await call_llm("kimi", "kimi-for-coding/kimi-k2-thinking",
        [{"role": "user", "content": f"Extract Standard Operating Procedures from transcript. Return JSON:\n{{\"procedures\": [{{\"name\": \"...\", \"steps\": [], \"category\": \"...\"}}], \"policies\": [], \"workflows\": []}}\n\nTranscript:\n{transcript[:4000]}"}],
        "You are an operations analyst. Extract SOPs and workflows. Return only valid JSON.")
    try:
        return json.loads(result.strip().replace("```json", "").replace("```", ""))
    except Exception:
        return {"raw": result[:1000]}

# --- Main Pipeline ---

async def kimi_daily_process(transcript: str, auto_tools: bool = True) -> dict:
    """Full agentic pipeline: extract → vault → tools."""
    from omni import log_activity
    start = time.time()
    await log_activity("kimi-daily", "Starting daily extraction pipeline")

    # Step 1: Pull external context
    context = await webbridge_pull_context(["vault", "crm"])
    enriched_transcript = f"External Context:\n{context}\n\nTranscript:\n{transcript}"

    # Step 2: Parallel extraction with specialized agents
    music_ip, crm_notes, sops = await asyncio.gather(
        swarm_extract_music_ip(enriched_transcript),
        swarm_extract_crm_notes(enriched_transcript),
        swarm_extract_sops(enriched_transcript)
    )

    # Step 3: Vault storage (durable memory)
    run_id = int(time.time() * 1000)
    await tool_vault_store("music_ip", f"Extraction {run_id}", json.dumps(music_ip), ["music", "ip"])
    await tool_vault_store("crm", f"CRM Notes {run_id}", json.dumps(crm_notes), ["crm", "contacts"])
    await tool_vault_store("sops", f"SOPs {run_id}", json.dumps(sops), ["sops", "operations"])

    # Step 4: Save to database
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    conn.execute("INSERT INTO extractions (run_date, transcript, music_ip, crm_notes, sops, status) VALUES (?,?,?,?,?,?)",
                 (datetime.now().isoformat(), transcript[:5000], json.dumps(music_ip), json.dumps(crm_notes), json.dumps(sops), "completed"))
    conn.commit(); conn.close()

    # Step 5: Call tools if enabled
    tools_called = []
    if auto_tools:
        # Store extraction summary in local vault
        summary = f"Daily Extraction {datetime.now().strftime('%Y-%m-%d')}\n\nMusic IP: {len(music_ip.get('artists', []))} artists, {len(music_ip.get('tracks', []))} tracks\nCRM: {len(crm_notes.get('contacts', []))} contacts\nSOPs: {len(sops.get('procedures', []))} procedures"

        doc_result = await tool_create_document(f"Daily Extraction {datetime.now().strftime('%Y-%m-%d')}", summary, "extractions")
        tools_called.append({"tool": "vault", "result": doc_result})

        slack_result = await tool_send_slack_summary("daily-extractions", summary)
        tools_called.append({"tool": "slack", "result": slack_result})

    elapsed = round(time.time() - start, 2)
    await log_activity("kimi-daily", f"Pipeline completed in {elapsed}s")

    return {
        "status": "completed",
        "run_id": run_id,
        "elapsed_seconds": elapsed,
        "music_ip": music_ip,
        "crm_notes": crm_notes,
        "sops": sops,
        "tools_called": tools_called,
        "vault_stored": True
    }

class AudioMetadata(BaseModel):
    filename: str
    format: str
    duration_seconds: float
    channels: int
    sample_rate: int
    archive_path: str

class AudioIngestionHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return

        filepath = event.src_path
        filename = os.path.basename(filepath)
        _, ext = os.path.splitext(filepath)
        ext = ext.lower()

        if ext not in ['.wav', '.mp3']:
            return

        time.sleep(1.5)

        try:
            if ext == '.wav':
                from mutagen.wave import WAVE
                audio = WAVE(filepath)
            else:
                from mutagen.mp3 import MP3
                audio = MP3(filepath)

            archive_path = str(PROCESSED_DIR / filename)

            payload = {
                "filename": filename,
                "format": ext.replace(".", ""),
                "duration_seconds": round(audio.info.length, 2),
"channels": audio.info.channels,
                "sample_rate": audio.info.sample_rate,
                "archive_path": archive_path
            }
            
            response = requests.post(f"http://127.0.0.1:{PORT}/ingest", json=payload, timeout=10)
            response.raise_for_status()

            shutil.move(filepath, archive_path)
            print(f"Processed and archived: {filename}")

        except Exception as e:
            print(f"Failed to process {filepath}: {str(e)}")

ingest_observer = Observer()

# === Database ===
import aiosqlite

async def get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, type TEXT DEFAULT 'manual', status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0, result TEXT, agent TEXT,
            created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')),
            scheduled_cron TEXT, enabled INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS task_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER, output TEXT, status TEXT, duration_ms INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );
        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, role TEXT, model TEXT, status TEXT DEFAULT 'idle',
            tasks_completed INTEGER DEFAULT 0, last_active TEXT, config TEXT
        );
        CREATE TABLE IF NOT EXISTS plugins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE, type TEXT, enabled INTEGER DEFAULT 1,
            config TEXT, last_run TEXT, result TEXT
        );
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, domain TEXT, template TEXT, db_path TEXT,
            status TEXT DEFAULT 'draft', published_at TEXT, config TEXT
        );
        CREATE TABLE IF NOT EXISTS swarm_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            objective TEXT, status TEXT DEFAULT 'running', agents_used TEXT,
            started_at TEXT DEFAULT (datetime('now')), completed_at TEXT, result TEXT
        );
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT, message TEXT, level TEXT DEFAULT 'info',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    agents = [
        ("Atlas", "orchestrator", "kimi-for-coding/k2p7", "idle", "Central coordinator"),
        ("Scout", "researcher", "kimi-for-coding/kimi-k2-thinking", "idle", "Deep research & analysis"),
        ("Forge", "builder", "kimi-for-coding/k2p7", "idle", "Writes code, builds systems"),
        ("Pulse", "monitor", "kimi-for-coding/kimi-for-coding-highspeed", "idle", "Schedules & health checks"),
        ("Echo", "comms", "xai/grok-3-mini", "paused", "Email, notifications, comms"),
        ("Harmony", "studio", "kimi-for-coding/kimi-for-coding-highspeed", "idle", "Audio analysis, metadata, mixing"),
    ]
    for name, role, model, status, desc in agents:
        await db.execute("INSERT OR IGNORE INTO agents (name,role,model,status,config) VALUES (?,?,?,?,?)",
                         (name, role, model, status, desc))
    tasks = [
        ("Health Check", "scheduled", "pulse", "*/15 * * * *"),
        ("Data Sync", "scheduled", "scout", "0 */6 * * *"),
        ("Daily Report", "scheduled", "atlas", "0 9 * * *"),
        ("Disk Cleaner", "scheduled", "pulse", "0 3 * * *"),
        ("Kimi Daily", "scheduled", "atlas", "0 0 * * *"),
    ]
    for name, ttype, agent, cron in tasks:
        await db.execute("INSERT OR IGNORE INTO tasks (name,type,agent,scheduled_cron) VALUES (?,?,?,?)",
                         (name, ttype, agent, cron))
    plugins = [
        ("Financial Data", "financial"), ("Economic Calendar", "economic"),
        ("Music Industry", "industry"), ("Weather", "utility"),
    ]
    for name, ptype in plugins:
        await db.execute("INSERT OR IGNORE INTO plugins (name,type) VALUES (?,?)", (name, ptype))
    await db.commit()
    await db.close()

async def log_activity(source, message, level="info"):
    db = await get_db()
    await db.execute("INSERT INTO activity_log (source,message,level) VALUES (?,?,?)", (source, message, level))
    await db.commit(); await db.close()

async def get_tasks():
    db = await get_db(); rows = await db.execute_fetchall("SELECT * FROM tasks ORDER BY created_at DESC"); await db.close()
    return [dict(r) for r in rows]

async def get_agents():
    db = await get_db(); rows = await db.execute_fetchall("SELECT * FROM agents ORDER BY id"); await db.close()
    return [dict(r) for r in rows]

async def get_plugins():
    db = await get_db(); rows = await db.execute_fetchall("SELECT * FROM plugins ORDER BY name"); await db.close()
    return [dict(r) for r in rows]

async def get_activity(limit=50):
    db = await get_db(); rows = await db.execute_fetchall("SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)); await db.close()
    return [dict(r) for r in rows]

async def get_swarm_runs():
    db = await get_db(); rows = await db.execute_fetchall("SELECT * FROM swarm_runs ORDER BY started_at DESC LIMIT 20"); await db.close()
    return [dict(r) for r in rows]

async def update_task(task_id, status=None, progress=None, result=None):
    db = await get_db()
    sets, vals = ["updated_at=datetime('now')"], []
    if status: sets.append("status=?"); vals.append(status)
    if progress is not None: sets.append("progress=?"); vals.append(progress)
    if result: sets.append("result=?"); vals.append(result[:2000])
    vals.append(task_id)
    await db.execute(f"UPDATE tasks SET {','.join(sets)} WHERE id=?", vals)
    await db.commit(); await db.close()

async def update_agent(agent_id, status):
    db = await get_db()
    await db.execute("UPDATE agents SET status=?, last_active=datetime('now') WHERE id=?", (status, agent_id))
    await db.commit(); await db.close()

# === LLM Client ===
import httpx
from llm_router import call_llm, parse_model, get_health as get_llm_health

# === Scheduler ===
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
scheduler = AsyncIOScheduler()

async def run_scheduled_task(task_id, name, agent="atlas"):
    start = time.time()
    await update_task(task_id, status="running", progress=0)
    await log_activity("scheduler", f"Running: {name}")

    # Handle Disk Cleaner task directly without LLM
    if name == "Disk Cleaner":
        try:
            report = run_disk_cleaner()
            elapsed = int((time.time() - start) * 1000)
            result = json.dumps(report, indent=2)
            await update_task(task_id, status="completed", progress=100, result=result[:2000])
            db = await get_db()
            await db.execute("INSERT INTO task_results (task_id,output,status,duration_ms) VALUES (?,?,?,?)",
                             (task_id, result[:2000], "success", elapsed))
            await db.commit(); await db.close()
            await log_activity("scheduler", f"Disk Cleaner: {report['usage_gb']}GB used, freed {report['cleaned_bytes']/(1024**3):.2f}GB")
        except Exception as e:
            await update_task(task_id, status="failed", result=str(e)[:2000])
            await log_activity("scheduler", f"Failed: {name}: {e}", "error")
        return

    # Handle Kimi Daily pipeline
    if name == "Kimi Daily":
        try:
            # Use a sample/demo transcript or fetch from a source
            demo_transcript = "Meeting notes: Discussed new artist signing with Universal Music. Follow up with Sarah at Sony regarding licensing deal. Update SOP for sample clearance process."
            report = await kimi_daily_process(demo_transcript, auto_tools=True)
            elapsed = int((time.time() - start) * 1000)
            result = json.dumps(report, indent=2)
            await update_task(task_id, status="completed", progress=100, result=result[:2000])
            db = await get_db()
            await db.execute("INSERT INTO task_results (task_id,output,status,duration_ms) VALUES (?,?,?,?)",
                             (task_id, result[:2000], "success", elapsed))
            await db.commit(); await db.close()

            # Send notification
            await _send_notification("Kimi Daily Complete", f"Extraction completed in {report['elapsed_seconds']}s")
            await log_activity("scheduler", f"Kimi Daily: {report['elapsed_seconds']}s, vault stored")
        except Exception as e:
            await update_task(task_id, status="failed", result=str(e)[:2000])
            await log_activity("scheduler", f"Failed: {name}: {e}", "error")
        return

    db = await get_db()
    row = await db.execute_fetchall("SELECT model FROM agents WHERE LOWER(name)=LOWER(?)", (agent,))
    await db.close()
    model_str = row[0]["model"] if row else "kimi-for-coding/kimi-for-coding-highspeed"
    prov, model_id = parse_model(model_str)
    try:
        result = await call_llm(prov, model_id,
            [{"role": "user", "content": f"Scheduled task: {name}\nTime: {datetime.now().isoformat()}\nProvide brief status report."}],
            "You are a system monitor. Report concisely with health status (green/yellow/red).")
        elapsed = int((time.time() - start) * 1000)
        await update_task(task_id, status="completed", progress=100, result=result[:2000])
        db = await get_db()
        await db.execute("INSERT INTO task_results (task_id,output,status,duration_ms) VALUES (?,?,?,?)",
                         (task_id, result[:2000], "success", elapsed))
        await db.commit(); await db.close()
        await log_activity("scheduler", f"Completed: {name} ({elapsed}ms)")
    except Exception as e:
        await update_task(task_id, status="failed", result=str(e)[:2000])
        await log_activity("scheduler", f"Failed: {name}: {e}", "error")

async def sync_schedules():
    for job in scheduler.get_jobs():
        if job.id.startswith("task_"): scheduler.remove_job(job.id)
    for t in await get_tasks():
        if t["type"] == "scheduled" and t["enabled"] and t["scheduled_cron"]:
            parts = t["scheduled_cron"].split()
            if len(parts) == 5:
                cron = {"minute": parts[0], "hour": parts[1], "day": parts[2], "month": parts[3], "day_of_week": parts[4]}
                scheduler.add_job(run_scheduled_task, CronTrigger(**cron),
                    args=[t["id"], t["name"], t.get("agent", "atlas")], id=f"task_{t['id']}", replace_existing=True)

# === Swarm ===
async def swarm_run(objective, max_agents=3):
    run_id = int(time.time() * 1000)
    db = await get_db()
    await db.execute("INSERT INTO swarm_runs (objective,agents_used) VALUES (?,?)", (objective, ""))
    await db.commit(); await db.close()
    await log_activity("swarm", f"Started: {objective[:80]}")

    agents = await get_agents()
    idle = [a for a in agents if a["status"] == "idle"][:max_agents]
    if not idle:
        return {"status": "failed", "reason": "No idle agents"}

    agent_names = ", ".join([f"{a['name']}({a['role']})" for a in idle])
    prov, model_id = parse_model(idle[0]["model"])
    plan_text = await call_llm(prov, model_id,
        [{"role": "user", "content": f"Decompose into subtasks.\nObjective: {objective}\nAgents: {agent_names}\nReturn JSON array: [{{\"task\":\"...\",\"agent\":\"name\",\"priority\":1-5}}]\nONLY JSON."}],
        "Return only valid JSON array.")

    try:
        plan_text = plan_text.strip()
        if "```" in plan_text:
            plan_text = plan_text.split("```")[1]
            if plan_text.startswith("json"): plan_text = plan_text[4:]
        tasks = json.loads(plan_text)
    except Exception: tasks = [{"task": objective, "agent": idle[0]["name"], "priority": 1}]

    agent_map = {a["name"]: a for a in idle}
    results = []
    sem = asyncio.Semaphore(3)

    async def exec_subtask(subtask):
        async with sem:
            a = agent_map.get(subtask.get("agent", idle[0]["name"]), idle[0])
            p, m = parse_model(a["model"])
            await update_agent(a["id"], "working")
            start = time.time()
            try:
                result = await call_llm(p, m,
                    [{"role": "user", "content": subtask["task"]}],
                    f"You are {a['name']}, a {a['role']}. Complete precisely.")
                elapsed = int((time.time() - start) * 1000)
                await update_agent(a["id"], "idle")
                db = await get_db()
                await db.execute("UPDATE agents SET tasks_completed=tasks_completed+1 WHERE id=?", (a["id"],))
                await db.commit(); await db.close()
                return {"agent": a["name"], "task": subtask["task"], "result": result[:500], "duration_ms": elapsed, "status": "success"}
            except Exception as e:
                await update_agent(a["id"], "idle")
                return {"agent": a["name"], "task": subtask["task"], "result": str(e)[:300], "status": "error"}

    results = await asyncio.gather(*[exec_subtask(t) for t in tasks])
    results_text = "\n".join([f"[{r['agent']}] {r['result']}" for r in results if r["status"] == "success"])
    complete_result = f"{len([r for r in results if r['status']=='success'])}/{len(tasks)} subtasks done.\n{results_text}"

    db = await get_db()
    await db.execute("UPDATE swarm_runs SET status='completed', result=?, completed_at=datetime('now') WHERE id=?",
                     (complete_result[:2000], run_id))
    await db.commit(); await db.close()
    await log_activity("swarm", f"Completed: {objective[:80]}")
    return {"status": "completed", "run_id": run_id, "tasks": tasks, "results": results, "synthesis": complete_result}

# === FastAPI App ===
from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

@asynccontextmanager
async def lifespan(app):
    await init_db(); scheduler.start(); await sync_schedules()
    _contacts_module.init_contacts_db()

    # Start audio ingestion watcher
    ingest_handler = AudioIngestionHandler()
    ingest_observer.schedule(ingest_handler, str(WATCH_DIR), recursive=False)
    ingest_observer.start()

    # Start DAW export watcher
    try:
        from daw_watcher import daw_watcher as _daw_watcher
        await _daw_watcher.start()
    except Exception as e:
        print(f"DAW watcher failed to start: {e}")

    await log_activity("system", "Dashboard started")
    yield
    ingest_observer.stop()
    ingest_observer.join()
    try:
        from daw_watcher import daw_watcher as _daw_watcher
        _daw_watcher.stop()
    except Exception: pass
    scheduler.shutdown()

app = FastAPI(title="Omni-Studio", version="1.0.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")

# (Volt SPA mount registered LAST — see bottom of file)

templates = Jinja2Templates(directory=str(BASE / "templates"))

@app.get("/api/tasks")
async def api_tasks(): return await get_tasks()

@app.post("/api/tasks")
async def api_create_task(name: str = Form(...), type: str = Form("manual"), agent: str = Form("atlas"), cron: str = Form("")):
    db = await get_db()
    await db.execute("INSERT INTO tasks (name,type,agent,scheduled_cron) VALUES (?,?,?,?)", (name, type, agent, cron))
    await db.commit(); await db.close()
    if cron: await sync_schedules()
    await log_activity("tasks", f"Created: {name}")
    return RedirectResponse("/", status_code=303)

@app.post("/api/tasks/{task_id}/run")
async def api_run_task(task_id: int):
    tasks = await get_tasks()
    t = next((x for x in tasks if x["id"] == task_id), None)
    if not t: raise HTTPException(404)
    asyncio.create_task(run_scheduled_task(task_id, t["name"], t.get("agent", "atlas")))
    return {"status": "started"}

@app.post("/api/tasks/{task_id}/toggle")
async def api_toggle_task(task_id: int):
    db = await get_db(); await db.execute("UPDATE tasks SET enabled=NOT enabled WHERE id=?", (task_id,))
    await db.commit(); await db.close(); return {"status": "toggled"}

@app.post("/api/agents/{agent_id}/toggle")
async def api_toggle_agent(agent_id: int):
    db = await get_db()
    row = await db.execute_fetchall("SELECT status FROM agents WHERE id=?", (agent_id,))
    if not row:
        await db.close()
        raise HTTPException(404)
    new_status = "paused" if row[0]["status"] != "paused" else "idle"
    await db.execute("UPDATE agents SET status=? WHERE id=?", (new_status, agent_id))
    await db.commit(); await db.close()
    await log_activity("agents", f"Agent {agent_id} set to {new_status}")
    return {"status": new_status}

@app.get("/api/agents")
async def api_agents(): return await get_agents()

@app.get("/api/activity")
async def api_activity(): return await get_activity(50)

@app.get("/api/plugins")
async def api_plugins(): return await get_plugins()
@app.get("/api/swarm/runs")
async def api_swarm_runs(): return await get_swarm_runs()

@app.post("/api/swarm/run")
async def api_swarm_run(objective: str = Form(...)):
    return await swarm_run(objective)

@app.post("/api/chat")
async def api_chat(message: str = Form(...), provider: str = Form("kimi")):
    prov, model = parse_model(provider + "/k2p7") if "/" not in provider else parse_model(provider)
    return {"response": await call_llm(prov, model, [{"role": "user", "content": message}])}

@app.post("/api/plugins/{name}/run")
async def api_run_plugin(name: str):
    builtin = {
        "Financial Data": {"fn": lambda: {"status": "ok", "sp500": "5,800", "trend": "bullish"}},
        "Economic Calendar": {"fn": lambda: {"events": [{"date": "2026-07-22", "event": "FOMC", "impact": "high"}]}},
        "Music Industry": {"fn": lambda: {"streaming_growth": "+10.2%", "vinyl_growth": "+15.7%"}},
        "Weather": {"fn": lambda: {"city": "Nashville", "temp": "88°F"}},
    }
    if name in builtin:
        result = builtin[name]["fn"]()
        db = await get_db()
        await db.execute("UPDATE plugins SET last_run=datetime('now'), result=? WHERE name=?", (json.dumps(result), name))
        await db.commit(); await db.close()
        return {"status": "success", "data": result}
    return {"status": "error", "error": f"Plugin '{name}' not found"}

@app.get("/api/sites")
async def api_sites(): return []
@app.post("/api/sites")
async def api_create_site(name: str = Form(...), template: str = Form("default")):
    site_dir = BASE / "sites" / name.lower().replace(" ", "-")
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "index.html").write_text(f"<html><head><title>{name}</title></head><body><h1>{name}</h1><p>Powered by Omni-Studio</p></body></html>")
    db = await get_db()
    await db.execute("INSERT INTO sites (name,template,config) VALUES (?,?,?)", (name, template, json.dumps({"dir": str(site_dir)})))
    await db.commit(); await db.close()
    return RedirectResponse("/", status_code=303)

@app.get("/api/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat(), "agents": len(await get_agents()), "tasks": len(await get_tasks())}

@app.post("/ingest")
async def ingest_audio(data: AudioMetadata):
    await log_activity("ingest", f"Received: {data.filename}")
    return {"status": "success", "stored_at": data.archive_path}

@app.post("/api/studio/analyze")
async def api_studio_analyze(filepath: str = Form(...)):
    """Analyze audio file metadata using Harmony agent."""
    import os
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in ['.wav', '.mp3']:
        raise HTTPException(400, "Unsupported format")

    try:
        if ext == '.wav':
            from mutagen.wave import WAVE
            audio = WAVE(filepath)
        elif ext == '.mp3':
            from mutagen.mp3 import MP3
            audio = MP3(filepath)

        metadata = {
            "filename": os.path.basename(filepath),
            "format": ext.replace(".", ""),
            "duration_seconds": round(audio.info.length, 2),
            "channels": audio.info.channels,
            "sample_rate": audio.info.sample_rate
        }

        await log_activity("studio", f"Analyzed: {metadata['filename']}")
        return {"status": "success", "metadata": metadata}
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")

@app.get("/api/cleaner/status")
async def api_cleaner_status():
    """Check current disk usage."""
    usage_gb = get_disk_usage_gb()
    return {"usage_gb": usage_gb, "limit_gb": MAX_DISK_GB, "percent": round(usage_gb / MAX_DISK_GB * 100, 1)}

@app.post("/api/cleaner/run")
async def api_run_cleaner():
    """Manually run disk cleaner."""
    report = run_disk_cleaner()
    await log_activity("cleaner", f"Manual run: {report['usage_gb']}GB used")
    return report


# === Contacts CRM ===
import contacts as _contacts_module
from contacts import (
    init_contacts_db, list_contacts as _list_contacts, get_contact as _get_contact,
    create_contact as _create_contact, update_contact as _update_contact,
    delete_contact as _delete_contact, import_csv as _import_csv
)

CONTACTS_DB = _contacts_module.DB_PATH

@app.get("/api/contacts")
async def api_list_contacts(status: str = "", search: str = "", limit: int = 100, offset: int = 0):
    return _list_contacts(status, search, limit, offset)

@app.get("/api/contacts/stats")
async def api_contact_stats():
    """Get contact stats by status and source."""
    conn = _contacts_module._get_conn()
    by_status = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM contacts GROUP BY status").fetchall()}
    by_source = {r[0]: r[1] for r in conn.execute("SELECT source, COUNT(*) FROM contacts GROUP BY source").fetchall()}
    total = conn.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
    conn.close()
    return {"total": total, "by_status": by_status, "by_source": by_source}

@app.get("/api/contacts/{contact_id}")
async def api_get_contact(contact_id: int):
    c = _get_contact(contact_id)
    if not c: raise HTTPException(404)
    return c

@app.post("/api/contacts")
async def api_create_contact(name: str = Form(...), email: str = Form(""), phone: str = Form(""),
                             company: str = Form(""), role: str = Form(""), source: str = Form(""),
                             status: str = Form("lead"), notes: str = Form("")):
    cid = _create_contact({"name": name, "email": email, "phone": phone, "company": company,
                           "role": role, "source": source, "status": status, "notes": notes})
    await log_activity("contacts", f"Created contact: {name}")
    return {"status": "created", "id": cid}

@app.put("/api/contacts/{contact_id}")
async def api_update_contact(contact_id: int, data: dict):
    _update_contact(contact_id, data)
    return {"status": "updated"}

@app.delete("/api/contacts/{contact_id}")
async def api_delete_contact(contact_id: int):
    _delete_contact(contact_id)
    return {"status": "deleted"}

# === Vault (kimi_daily.db) ===
@app.get("/api/vault/all")
async def api_vault_all(category: str = "", limit: int = 50):
    """Get all vault entries, optionally filtered by category."""
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    conn.row_factory = _sync_sqlite3.Row
    if category:
        rows = conn.execute("SELECT * FROM vault WHERE category=? ORDER BY created_at DESC LIMIT ?", (category, limit)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM vault ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/vault/stats")
async def api_vault_stats():
    """Get vault stats by category."""
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    by_cat = {r[0]: r[1] for r in conn.execute("SELECT category, COUNT(*) FROM vault GROUP BY category").fetchall()}
    total = conn.execute("SELECT COUNT(*) FROM vault").fetchone()[0]
    extractions = conn.execute("SELECT COUNT(*) FROM extractions").fetchone()[0]
    conn.close()
    return {"total_entries": total, "total_extractions": extractions, "by_category": by_cat}

# === Sample Library ===
import sample_library
from sample_library import (
    init_sample_db, search_samples, get_sample_stats, get_sample,
    upsert_sample, bulk_upsert_samples, update_sample_tags, update_sample_notes,
    start_scan, complete_scan, get_scan_history, get_unanalyzed_samples,
    get_all_keys, get_all_directories
)

# Sample tables created at import time in sample_library.py


@app.get("/api/samples")
async def api_samples(q: str = "", key: str = "", tempo_min: float = 0, tempo_max: float = 999,
                       sample_type: str = "", directory: str = "", limit: int = 100, offset: int = 0):
    return await search_samples(q, key, tempo_min, tempo_max, sample_type, directory, limit, offset)


@app.get("/api/samples/stats")
async def api_sample_stats():
    return await get_sample_stats()


@app.get("/api/samples/keys")
async def api_sample_keys():
    return await get_all_keys()


@app.get("/api/samples/directories")
async def api_sample_dirs():
    return await get_all_directories()


@app.get("/api/samples/unanalyzed")
async def api_unanalyzed(limit: int = 50):
    return await get_unanalyzed_samples(limit)


@app.get("/api/samples/scan-history")
async def api_scan_history():
    return await get_scan_history()


@app.get("/api/samples/{sample_id}")
async def api_sample_detail(sample_id: int):
    s = await get_sample(sample_id)
    if not s: raise HTTPException(404)
    return s

@app.get("/api/samples/{sample_id}/stream")
async def api_stream_sample(sample_id: int):
    """Stream audio file for preview."""
    from starlette.responses import FileResponse
    s = await get_sample(sample_id)
    if not s: raise HTTPException(404)
    filepath = s.get("path") if isinstance(s, dict) else getattr(s, "path", None)
    if not filepath or not os.path.isfile(filepath):
        raise HTTPException(404, "Audio file not found on disk")
    import mimetypes
    mime = mimetypes.guess_type(filepath)[0] or "audio/wav"
    return FileResponse(filepath, media_type=mime, filename=os.path.basename(filepath))

@app.post("/api/samples/{sample_id}/tags")
async def api_update_tags(sample_id: int, tags: str = Form(...)):
    tag_list = [t.strip() for t in tags.split(",") if t.strip()]
    await update_sample_tags(sample_id, tag_list)
    return {"status": "updated"}


@app.post("/api/samples/{sample_id}/notes")
async def api_update_notes(sample_id: int, notes: str = Form(...)):
    await update_sample_notes(sample_id, notes)
    return {"status": "updated"}


@app.post("/api/samples/scan")
async def api_start_scan():
    import sample_scanner
    scan_id = await start_scan()
    asyncio.create_task(_run_sample_scan(scan_id))
    return {"status": "started", "scan_id": scan_id}


async def _run_sample_scan(scan_id: int):
    import time as _time
    import sample_scanner
    start = _time.time()
    try:
        files = await asyncio.to_thread(sample_scanner.scan_all_audio)
        count = await asyncio.to_thread(bulk_upsert_samples_sync, files)
        elapsed = _time.time() - start
        await complete_scan(scan_id, count, 0, elapsed)
        await log_activity("scanner", f"Scan complete: {count} files in {elapsed:.1f}s")
    except Exception as e:
        await log_activity("scanner", f"Scan failed: {e}", "error")


def bulk_upsert_samples_sync(files: list[dict]) -> int:
    """Synchronous bulk upsert for use with asyncio.to_thread."""
    import sqlite3 as _sqlite3
    import sample_library
    db_path_str = str(sample_library.DB_PATH)
    conn = sqlite3.connect(db_path_str)
    count = 0
    for meta in files:
        try:
            conn.execute("""
                INSERT INTO samples (path, filename, directory, extension, size_bytes, size_mb,
                    modified_at, file_hash, sample_type, key, mode, key_full, tempo, duration, analyzed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    size_bytes=excluded.size_bytes, size_mb=excluded.size_mb,
                    modified_at=excluded.modified_at, file_hash=excluded.file_hash,
                    sample_type=excluded.sample_type, key=excluded.key, mode=excluded.mode,
                    key_full=excluded.key_full, tempo=excluded.tempo, duration=excluded.duration,
                    analyzed=excluded.analyzed, updated_at=datetime('now')
            """, (
                meta.get("path"), meta.get("filename"), meta.get("directory"),
                meta.get("extension"), meta.get("size_bytes", 0), meta.get("size_mb", 0.0),
                meta.get("modified_at"), meta.get("file_hash"), meta.get("sample_type", "unknown"),
                meta.get("key", ""), meta.get("mode", ""), meta.get("key_full", "Unknown"),
                meta.get("tempo", 0.0), meta.get("duration", 0.0), meta.get("analyzed", 0)
            ))
            count += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return count


@app.post("/api/samples/analyze")
async def api_analyze_samples():
    import sample_scanner
    import sample_library
    from sample_library import get_unanalyzed_samples as _get_unanalyzed
    import time as _time

    async def _run():
        start = _time.time()
        unanalyzed = await _get_unanalyzed(limit=100)
        analyzed = 0
        for s in unanalyzed:
            try:
                result = await asyncio.to_thread(sample_scanner.detect_key_and_tempo, s["path"])
                dur = await asyncio.to_thread(sample_scanner.get_audio_duration, s["path"])
                import sqlite3 as _sqlite3
                conn = _sqlite3.connect(str(sample_library.DB_PATH))
                conn.execute(
                    "UPDATE samples SET key=?, mode=?, key_full=?, tempo=?, duration=?, analyzed=1 WHERE id=?",
                    (result["key"], result["mode"], result["key_full"], result["tempo"], dur, s["id"]))
                conn.commit()
                conn.close()
                analyzed += 1
            except Exception:
                pass
        elapsed = _time.time() - start
        await log_activity("scanner", f"Analyzed {analyzed} samples in {elapsed:.1f}s")

    asyncio.create_task(_run())
    return {"status": "started"}


@app.post("/api/samples/export")
async def api_export_sample(sample_id: int = Form(...)):
    """Export a sample to Google Drive."""
    s = await get_sample(sample_id)
    if not s: raise HTTPException(404)
    from google_drive import upload_to_drive
    try:
        result = await upload_to_drive(s["path"], "OMNI Samples")
        db = await get_db()
        await db.execute(
            "UPDATE samples SET drive_id=?, drive_url=?, synced_at=datetime('now') WHERE id=?",
            (result.get("id"), result.get("url", ""), sample_id))
        await db.commit(); await db.close()
        return {"status": "uploaded", "drive_url": result.get("url", "")}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# === Kimi Bridge ===
from bridge import kimi_to_omni, omni_to_kimi, get_kimi_tasks, complete_kimi_task

@app.post("/api/bridge/kimi")
async def api_bridge_kimi(task_type: str = Form(...), payload: str = Form("{}")):
    """Kimi app sends tasks to Omni-Studio."""
    data = json.loads(payload)
    return await kimi_to_omni(task_type, data)

@app.post("/api/bridge/omni")
async def api_bridge_omni(prompt: str = Form(...), callback_url: str = Form("")):
    """Omni-Studio sends work to Kimi app."""
    return await omni_to_kimi(prompt, callback_url or None)

@app.get("/api/bridge/tasks")
async def api_bridge_tasks():
    """Get pending Kimi tasks."""
    return await get_kimi_tasks()

@app.post("/api/bridge/complete")
async def api_bridge_complete(task_id: str = Form(...), result: str = Form(...)):
    """Mark Kimi task as completed."""
    return await complete_kimi_task(task_id, result)

# === Kimi Daily Pipeline API ===
@app.post("/api/kimi-daily/run")
async def api_run_kimi_daily(transcript: str = Form(""), auto_tools: bool = Form(True)):
    """Manually trigger the daily extraction pipeline."""
    if not transcript:
        transcript = "Demo meeting: Signed deal with Warner for new album distribution. CRM note - contact Mike at ABC Records. SOP update needed for royalty calculation workflow."
    return await kimi_daily_process(transcript, auto_tools)

@app.get("/api/kimi-daily/history")
async def api_kimi_daily_history(limit: int = 10):
    """Get recent extraction history."""
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    conn.row_factory = _sync_sqlite3.Row
    rows = conn.execute("SELECT * FROM extractions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/vault/search")
async def api_vault_search(q: str, category: str = ""):
    """Search vault for stored extractions."""
    return await tool_vault_search(q, category)

@app.get("/api/vault/recent")
async def api_vault_recent(limit: int = 20):
    """Get recent vault entries."""
    conn = _sync_sqlite3.connect(str(KIMI_DAILY_DB))
    conn.row_factory = _sync_sqlite3.Row
    rows = conn.execute("SELECT * FROM vault ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# === Notifications ===
async def _send_notification(title: str, message: str):
    """Send notification to configured channels."""
    # Slack
    await tool_send_slack_summary("general", f"*{title}*\n{message}")

    # Log to activity
    await log_activity("notification", f"{title}: {message}")

@app.get("/api/notifications")
async def api_notifications():
    """Get recent notifications from activity log."""
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM activity_log WHERE source='notification' ORDER BY created_at DESC LIMIT 20")
    await db.close()
    return [dict(r) for r in rows]

# === Omi Webhook ===

class OmiPayload(BaseModel):
    session_id: str
    transcript: str
    timestamp: float

@app.post("/webhook/omi")
async def receive_omi_transcript(payload: OmiPayload):
    """Receive ambient transcript from Omi device."""
    from omni_kimi_bridge import receive_omi_transcript as _receive
    return await _receive(payload)

@app.post("/process/kimi-daily")
async def process_kimi_daily():
    """Process today's Omi transcripts through Kimi 128k."""
    from omni_kimi_bridge import process_daily_batch
    return await process_daily_batch()


# === DAW Export Feed ===
@app.get("/api/daw/status")
async def api_daw_status():
    """Get DAW watcher state."""
    try:
        from daw_watcher import daw_watcher as _daw
        return _daw.get_state()
    except Exception:
        return {"processed_files": [], "uploads": [], "last_scan": None}

@app.get("/api/daw/exports")
async def api_daw_exports():
    """Get recent DAW exports."""
    state = await api_daw_status()
    return state.get("uploads", [])[-20:]

@app.post("/api/daw/scan")
async def api_daw_scan():
    """Scan existing DAW export files."""
    try:
        from daw_watcher import daw_watcher as _daw
        existing = await _daw.scan_existing()
        return {"status": "ok", "count": len(existing), "files": existing}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# === Audio Apps Integration ===
import subprocess
import signal

AUDIO_APPS = {
    "stabledaw": {
        "name": "StableDAW",
        "description": "AI Audio DAW with text-to-audio, inpainting, and LoRA training",
        "app_id": "stabledaw.pinokio.git",
        "port": 5173,
        "icon": "fa-solid fa-wave-square"
    },
    "stable-audio-3": {
        "name": "Stable Audio 3",
        "description": "Text-to-audio generation for music and sound effects",
        "app_id": "stable-audio-3-small.pinokio.git",
        "icon": "fa-solid fa-music"
    },
    "tascar": {
        "name": "TASCAR",
        "description": "Spatial audio rendering in Ambisonics and VBAP",
        "app_id": "tascar",
        "icon": "fa-solid fa-headphones"
    }
}

def get_audio_app_status(app_id: str) -> dict:
    """Check if an audio app is running via pterm status."""
    app = AUDIO_APPS.get(app_id)
    if not app:
        return {"status": "error", "error": "App not found"}

    is_running = False
    try:
        result = subprocess.run(
            ["pterm", "status", app["app_id"]],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            is_running = info.get("running", False)
    except Exception:
        pass

    return {
        "id": app_id,
        "name": app["name"],
        "description": app["description"],
        "status": "running" if is_running else "stopped",
        "port": app.get("port"),
        "icon": app["icon"]
    }

@app.get("/api/audio-apps")
async def api_audio_apps():
    """Get status of all audio apps."""
    return [get_audio_app_status(app_id) for app_id in AUDIO_APPS]

@app.get("/api/audio-apps/{app_id}")
async def api_audio_app_status(app_id: str):
    """Get status of a specific audio app."""
    return get_audio_app_status(app_id)

@app.post("/api/audio-apps/{app_id}/launch")
async def api_audio_app_launch(app_id: str):
    """Launch an audio app via pterm."""
    app = AUDIO_APPS.get(app_id)
    if not app:
        return {"status": "error", "error": "App not found"}

    try:
        subprocess.Popen(
            ["pterm", "run", app["app_id"]],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return {"status": "ok", "message": f"Launching {app['name']}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/audio-apps/{app_id}/stop")
async def api_audio_app_stop(app_id: str):
    """Stop an audio app."""
    app = AUDIO_APPS.get(app_id)
    if not app:
        return {"status": "error", "error": "App not found"}

    try:
        subprocess.run(
            ["pterm", "stop", app["app_id"]],
            capture_output=True, timeout=5
        )
        return {"status": "ok", "message": f"Stopping {app['name']}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# === Volt Records Agents ===
AGENTS_DIR = BASE.parent / "omni-source" / "agents"

VOLT_AGENTS = {
    "studio_agent": {
        "name": "Studio Agent",
        "description": "Lead processor - watches for new inbound leads, extracts facts, computes deals, writes pitches",
        "script": "studio_agent.py",
        "icon": "fa-solid fa-microphone",
        "color": "amber"
    },
    "inbound_agent": {
        "name": "Inbound Agent",
        "description": "Handles incoming email replies from artists, auto-responds to inquiries",
        "script": "inbound_agent.py",
        "icon": "fa-solid fa-inbox",
        "color": "emerald"
    },
    "contact_enricher": {
        "name": "Contact Enricher",
        "description": "Enriches pitch files with artist contact info (Instagram, X, email)",
        "script": "contact_enricher.py",
        "icon": "fa-solid fa-address-book",
        "color": "blue"
    },
    "send_queue": {
        "name": "Send Queue",
        "description": "Drafts Instagram DMs and emails for enriched pitches, queues for approval",
        "script": "send_queue.py",
        "icon": "fa-solid fa-paper-plane",
        "color": "violet"
    },
    "approved_sender": {
        "name": "Approved Sender",
        "description": "Sends approved emails via Gmail SMTP, watches Send_Queue/Approved/",
        "script": "approved_sender.py",
        "icon": "fa-solid fa-check-circle",
        "color": "green"
    },
    "ghost_followup": {
        "name": "Ghost Follow-Up",
        "description": "Follows up with artists who haven't replied to pitches after 48 hours",
        "script": "ghost_followup.py",
        "icon": "fa-solid fa-ghost",
        "color": "orange"
    },
    "instagram_coldlist": {
        "name": "Instagram Cold Outreach",
        "description": "Cold DMs to Instagram followers, drafts personalized messages",
        "script": "instagram_coldlist.py",
        "icon": "fa-brands fa-instagram",
        "color": "pink"
    },
    "music_library_aggregator": {
        "name": "Music Library Aggregator",
        "description": "A&R lead discovery via LinkedIn for APM/UPM sub-libraries",
        "script": "music_library_aggregator.py",
        "icon": "fa-solid fa-music",
        "color": "cyan"
    }
}

def get_agent_status(agent_id: str) -> dict:
    """Get status and metrics for a Volt agent."""
    agent = VOLT_AGENTS.get(agent_id)
    if not agent:
        return {"status": "error", "error": "Agent not found"}

    script_path = AGENTS_DIR / agent["script"]
    is_installed = script_path.exists()

    # Check if agent is currently running
    try:
        result = subprocess.run(
            ["pgrep", "-f", agent["script"]],
            capture_output=True,
            text=True
        )
        is_running = result.returncode == 0
    except Exception:
        is_running = False

    # Get recent logs
    log_file = BASE.parent / "logs" / f"{agent_id.replace('_agent', '')}.log"
    recent_logs = []
    if log_file.exists():
        try:
            with open(log_file, 'r') as f:
                lines = f.readlines()
                recent_logs = [l.strip() for l in lines[-5:] if l.strip()]
        except Exception:
            pass

    # Get metrics based on agent type
    metrics = {}
    if agent_id == "studio_agent":
        # Count incoming leads
        leads_dir = BASE.parent / "Incoming_Leads"
        if leads_dir.exists():
            metrics["pending_leads"] = len(list(leads_dir.glob("*.txt")))
        # Count closed deals
        closed_dir = BASE.parent / "Closed_Deals"
        if closed_dir.exists():
            metrics["closed_deals"] = len(list(closed_dir.glob("*.txt")))
    elif agent_id == "send_queue":
        # Count queued messages
        queue_dir = BASE.parent / "Send_Queue"
        if queue_dir.exists():
            metrics["queued"] = len(list(queue_dir.glob("*.md")))
    elif agent_id == "approved_sender":
        # Count sent messages
        sent_dir = BASE.parent / "Send_Queue" / "Sent"
        if sent_dir.exists():
            metrics["sent"] = len(list(sent_dir.glob("*.md")))
    elif agent_id == "ghost_followup":
        # Count pending follow-ups
        pitch_dir = BASE.parent / "Outbound_Pitches"
        if pitch_dir.exists():
            metrics["pending_followups"] = len(list(pitch_dir.glob("*_pitch.txt")))

    return {
        "id": agent_id,
        "name": agent["name"],
        "description": agent["description"],
        "icon": agent["icon"],
        "color": agent["color"],
        "installed": is_installed,
        "running": is_running,
        "metrics": metrics,
        "recent_logs": recent_logs,
        "script": agent["script"]
    }

@app.get("/api/volt-agents")
async def api_volt_agents():
    """Get status of all Volt Records agents."""
    return [get_agent_status(agent_id) for agent_id in VOLT_AGENTS]

@app.get("/api/volt-agents/{agent_id}")
async def api_volt_agent_status(agent_id: str):
    """Get status of a specific Volt agent."""
    return get_agent_status(agent_id)

@app.post("/api/volt-agents/{agent_id}/run")
async def api_volt_agent_run(agent_id: str):
    """Run a Volt agent once."""
    agent = VOLT_AGENTS.get(agent_id)
    if not agent:
        return {"status": "error", "error": "Agent not found"}

    script_path = AGENTS_DIR / agent["script"]
    if not script_path.exists():
        return {"status": "error", "error": "Agent script not found"}

    try:
        # Run the agent script
        process = subprocess.Popen(
            ["python3", str(script_path)],
            cwd=str(AGENTS_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return {"status": "ok", "message": f"Running {agent['name']}", "pid": process.pid}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.post("/api/volt-agents/{agent_id}/stop")
async def api_volt_agent_stop(agent_id: str):
    """Stop a running Volt agent."""
    agent = VOLT_AGENTS.get(agent_id)
    if not agent:
        return {"status": "error", "error": "Agent not found"}

    try:
        subprocess.run(
            ["pkill", "-f", agent["script"]],
            capture_output=True
        )
        return {"status": "ok", "message": f"Stopping {agent['name']}"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/api/volt-agents/{agent_id}/logs")
async def api_volt_agent_logs(agent_id: str, lines: int = 50):
    """Get recent logs for a Volt agent."""
    agent = VOLT_AGENTS.get(agent_id)
    if not agent:
        return {"status": "error", "error": "Agent not found"}

    log_file = BASE.parent / "logs" / f"{agent_id.replace('_agent', '')}.log"
    if not log_file.exists():
        return {"logs": []}

    try:
        with open(log_file, 'r') as f:
            all_lines = f.readlines()
            return {"logs": [l.strip() for l in all_lines[-lines:] if l.strip()]}
    except Exception:
        return {"logs": []}

@app.get("/api/pipeline/stats")
async def api_pipeline_stats():
    """Get overall pipeline statistics."""
    stats = {
        "incoming_leads": 0,
        "outbound_pitches": 0,
        "send_queue": 0,
        "sent": 0,
        "closed_deals": 0,
        "skipped": 0
    }

    dirs = {
        "incoming_leads": BASE.parent / "Incoming_Leads",
        "outbound_pitches": BASE.parent / "Outbound_Pitches",
        "send_queue": BASE.parent / "Send_Queue",
        "closed_deals": BASE.parent / "Closed_Deals",
        "skipped": BASE.parent / "Skipped_Leads"
    }

    for key, dir_path in dirs.items():
        if dir_path.exists():
            if key == "send_queue":
                # Count .md files in Send_Queue root (not subdirs)
                stats[key] = len(list(dir_path.glob("*.md")))
                # Count sent in Sent subdirectory
                sent_dir = dir_path / "Sent"
                if sent_dir.exists():
                    stats["sent"] = len(list(sent_dir.glob("*.md")))
            else:
                stats[key] = len(list(dir_path.glob("*.txt")))

    return stats

# === System Health ===
@app.get("/api/system/health")
async def api_system_health():
    """Full system health: disk, agents, tasks, services."""
    usage_gb = get_disk_usage_gb()
    agents = await get_agents()
    tasks = await get_tasks()
    activity = await get_activity(5)

    idle_agents = len([a for a in agents if a["status"] == "idle"])
    working_agents = len([a for a in agents if a["status"] == "working"])
    paused_agents = len([a for a in agents if a["status"] == "paused"])
    pending_tasks = len([t for t in tasks if t["status"] == "pending"])
    completed_tasks = len([t for t in tasks if t["status"] == "completed"])

    # Check databases
    dbs = {}
    for name, path in [("dashboard", DB_PATH), ("contacts", CONTACTS_DB), ("samples", BASE/"data"/"samples.db"), ("kimi_daily", KIMI_DAILY_DB)]:
        if path.exists():
            dbs[name] = {"exists": True, "size_mb": round(path.stat().st_size / (1024*1024), 2)}
        else:
            dbs[name] = {"exists": False, "size_mb": 0}

    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "disk": {"usage_gb": usage_gb, "limit_gb": MAX_DISK_GB, "percent": round(usage_gb / MAX_DISK_GB * 100, 1)},
        "agents": {"total": len(agents), "idle": idle_agents, "working": working_agents, "paused": paused_agents},
        "tasks": {"total": len(tasks), "pending": pending_tasks, "completed": completed_tasks},
        "databases": dbs,
        "recent_activity": activity[:3],
        "llm_providers": get_llm_health(),
    }

@app.get("/api/system/llm-health")
async def api_llm_health():
    """Circuit breaker status for all LLM providers."""
    return get_llm_health()

# === Lead Pipeline & Outreach ===
CRM_DB = BASE.parent / "data" / "studio_crm.db"

def _crm_conn():
    import sqlite3 as _s3
    conn = _s3.connect(str(CRM_DB))
    conn.row_factory = _s3.Row
    return conn

def _init_crm():
    """Ensure CRM tables exist."""
    if CRM_DB.exists():
        return
    import migrate_music_library_schema
    migrate_music_library_schema.migrate()

@app.get("/api/leads")
async def api_leads(status: str = "", source: str = "", limit: int = 200):
    """Get all leads, optionally filtered."""
    conn = _crm_conn()
    conditions, params = [], []
    if status:
        conditions.append("status=?"); params.append(status)
    if source:
        conditions.append("source=?"); params.append(source)
    where = " AND ".join(conditions) if conditions else "1=1"
    rows = conn.execute(f"SELECT * FROM leads WHERE {where} ORDER BY created_at DESC LIMIT ?", params + [limit]).fetchall()
    total = conn.execute(f"SELECT COUNT(*) FROM leads WHERE {where}", params).fetchone()[0]
    conn.close()
    return {"leads": [dict(r) for r in rows], "total": total}

@app.get("/api/leads/stats")
async def api_lead_stats():
    """Lead pipeline stats."""
    conn = _crm_conn()
    by_status = {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM leads GROUP BY status").fetchall()}
    by_source = {r[0]: r[1] for r in conn.execute("SELECT source, COUNT(*) FROM leads GROUP BY source").fetchall()}
    total = conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    conn.close()
    return {"total": total, "by_status": by_status, "by_source": by_source}

@app.post("/api/leads")
async def api_create_lead(name: str = Form(...), email: str = Form(""), company: str = Form(""),
                          city: str = Form(""), status: str = Form("SCRAPED"), source: str = Form("manual")):
    conn = _crm_conn()
    conn.execute("INSERT INTO leads (name,email,company,city,status,source) VALUES (?,?,?,?,?,?)",
                 (name, email, company, city, status, source))
    conn.commit(); conn.close()
    await log_activity("leads", f"Created lead: {name}")
    return {"status": "created"}

@app.put("/api/leads/{lead_id}")
async def api_update_lead(lead_id: int, data: dict):
    conn = _crm_conn()
    allowed = {"name", "email", "company", "city", "status", "notes", "phone", "role", "sub_library", "gate_code"}
    fields, vals = [], []
    for k, v in data.items():
        if k in allowed:
            fields.append(f"{k}=?"); vals.append(v)
    if fields:
        vals.append(lead_id)
        conn.execute(f"UPDATE leads SET {','.join(fields)}, last_updated=CURRENT_TIMESTAMP WHERE id=?", vals)
        conn.commit()
    conn.close()
    return {"status": "updated"}

@app.delete("/api/leads/{lead_id}")
async def api_delete_lead(lead_id: int):
    conn = _crm_conn()
    conn.execute("DELETE FROM leads WHERE id=?", (lead_id,))
    conn.commit(); conn.close()
    return {"status": "deleted"}

@app.post("/api/leads/scan-library")
async def api_scan_music_library():
    """Run the music library aggregator (LinkedIn A&R discovery)."""
    asyncio.create_task(_run_music_library_scan())
    return {"status": "started"}

async def _run_music_library_scan():
    try:
        sys.path.insert(0, str(BASE.parent / "agents"))
        from music_library_aggregator import ensure_db, dork_linkedin, extract_targets, save_targets, CORE_LIBRARIES
        import httpx as _httpx
        ensure_db()
        total = 0
        async with _httpx.AsyncClient() as client:
            for lib in CORE_LIBRARIES:
                try:
                    raw = await dork_linkedin(client, lib)
                    if raw:
                        targets = extract_targets(raw, lib)
                        inserted = save_targets(targets)
                        total += inserted
                    await asyncio.sleep(1)
                except Exception: pass
        await log_activity("leads", f"Library scan complete: {total} new targets")
    except Exception as e:
        await log_activity("leads", f"Library scan failed: {e}", "error")

@app.post("/api/leads/audit-payments")
async def api_audit_payments():
    """Run the missed payments auditor."""
    asyncio.create_task(_run_payment_audit())
    return {"status": "started"}

async def _run_payment_audit():
    try:
        sys.path.insert(0, str(BASE.parent / "scripts"))
        from audit_missed_funds import audit_missed_payments
        await asyncio.to_thread(audit_missed_payments)
        await log_activity("leads", "Payment audit complete")
    except Exception as e:
        await log_activity("leads", f"Payment audit failed: {e}", "error")

@app.get("/api/leads/media-contacts")
async def api_media_contacts():
    conn = _crm_conn()
    rows = conn.execute("SELECT * FROM media_contacts ORDER BY outlet").fetchall()
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/leads/payments")
async def api_payments():
    conn = _crm_conn()
    try:
        rows = conn.execute("SELECT * FROM payments ORDER BY detected_at DESC LIMIT 50").fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(r) for r in rows]

@app.get("/api/leads/sessions")
async def api_sessions():
    conn = _crm_conn()
    try:
        rows = conn.execute("SELECT * FROM sessions ORDER BY session_date DESC LIMIT 50").fetchall()
    except Exception:
        rows = []
    conn.close()
    return [dict(r) for r in rows]

# === Music Knowledge API ===
import sqlite3 as _sql3

@app.get("/api/music-knowledge/billboard")
async def api_music_billboard(decade: str = "", genre: str = ""):
    """Get billboard chart archetypes for hit record patterns"""
    db = await get_db()
    query = "SELECT * FROM music_knowledge_billboard WHERE 1=1"
    params = []
    if decade:
        query += " AND decade=?"
        params.append(decade)
    if genre:
        query += " AND genre LIKE ?"
        params.append(f"%{genre}%")
    query += " ORDER BY decade, genre"
    rows = await db.execute_fetchall(query, params)
    await db.close()
    return [dict(r) for r in rows]

@app.get("/api/music-knowledge/frequency")
async def api_music_frequency(genre: str = ""):
    """Get frequency band profiles for mixing/mastering hit records"""
    db = await get_db()
    query = "SELECT * FROM music_knowledge_frequency WHERE 1=1"
    params = []
    if genre:
        query += " AND genre=?"
        params.append(genre)
    query += " ORDER BY genre, freq_low"
    rows = await db.execute_fetchall(query, params)
    await db.close()
    return [dict(r) for r in rows]

@app.get("/api/music-knowledge/harmonic")
async def api_music_harmonic(pattern: str = ""):
    """Get harmonic progression patterns used in hit records"""
    db = await get_db()
    query = "SELECT * FROM music_knowledge_harmonic WHERE 1=1"
    params = []
    if pattern:
        query += " AND pattern_name LIKE ?"
        params.append(f"%{pattern}%")
    query += " ORDER BY pattern_name"
    rows = await db.execute_fetchall(query, params)
    await db.close()
    return [dict(r) for r in rows]

@app.get("/api/music-knowledge/resonance")
async def api_music_resonance(concept: str = ""):
    """Get vibration/resonance concepts (Solfeggio, Schumann, A432, etc.)"""
    db = await get_db()
    query = "SELECT * FROM music_knowledge_resonance WHERE 1=1"
    params = []
    if concept:
        query += " AND concept LIKE ?"
        params.append(f"%{concept}%")
    query += " ORDER BY concept"
    rows = await db.execute_fetchall(query, params)
    await db.close()
    return [dict(r) for r in rows]

@app.get("/api/music-knowledge/search")
async def api_music_knowledge_search(q: str = "", limit: int = 20):
    """Full-text search across all music knowledge tables"""
    db = await get_db()
    results = {}
    
    tables = [
        ("billboard", "music_knowledge_billboard", "decade || ' ' || genre || ' ' || production_traits"),
        ("frequency", "music_knowledge_frequency", "genre || ' ' || band || ' ' || description"),
        ("harmonic", "music_knowledge_harmonic", "pattern_name || ' ' || chords || ' ' || emotional_impact"),
        ("resonance", "music_knowledge_resonance", "concept || ' ' || description"),
    ]
    
    for name, table, search_cols in tables:
        query = f"SELECT * FROM {table} WHERE {search_cols} LIKE ? LIMIT ?"
        rows = await db.execute_fetchall(query, (f"%{q}%", limit))
        results[name] = [dict(r) for r in rows]
    
    await db.close()
    return results

# --- Volt Dashboard SPA (must be registered LAST) ---
from starlette.exceptions import HTTPException as StarletteHTTPException

VOLT_DIST = BASE.parent / "volt-dashboard" / "dist"

class SPAStaticFiles(StaticFiles):
    """Serve index.html for unknown non-API paths (client-side routing)."""
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise

if VOLT_DIST.exists():
    app.mount("/", SPAStaticFiles(directory=str(VOLT_DIST), html=True), name="volt")
else:
    import logging as _log
    _log.getLogger("omni").warning("volt-dashboard/dist not found — run volt-dashboard/build.sh first")

# === Main ===
if __name__ == "__main__":
    import uvicorn
    print(f"\n⚡ Omni-Studio Dashboard — http://{HOST}:{PORT}\n")
    uvicorn.run("omni:app", host=HOST, port=PORT, reload=False)
