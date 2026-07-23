"""SQLite database layer — task widgets, scheduled results, agent logs, sites."""
import json
from datetime import datetime
from pathlib import Path

import aiosqlite

from config import DB_PATH

DB_PATH.parent.mkdir(parents=True, exist_ok=True)


async def get_db():
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            type TEXT DEFAULT 'manual',
            status TEXT DEFAULT 'pending',
            progress INTEGER DEFAULT 0,
            result TEXT,
            agent TEXT,
            created_at TEXT DEFAULT (datetime('now')),
            updated_at TEXT DEFAULT (datetime('now')),
            scheduled_cron TEXT,
            enabled INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS task_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            output TEXT,
            status TEXT,
            duration_ms INTEGER,
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (task_id) REFERENCES tasks(id)
        );

        CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT,
            model TEXT,
            status TEXT DEFAULT 'idle',
            tasks_completed INTEGER DEFAULT 0,
            last_active TEXT,
            config TEXT
        );

        CREATE TABLE IF NOT EXISTS plugins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            type TEXT,
            enabled INTEGER DEFAULT 1,
            config TEXT,
            last_run TEXT,
            result TEXT
        );

        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            domain TEXT,
            template TEXT,
            db_path TEXT,
            status TEXT DEFAULT 'draft',
            published_at TEXT,
            config TEXT
        );

        CREATE TABLE IF NOT EXISTS swarm_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            objective TEXT,
            status TEXT DEFAULT 'running',
            agents_used TEXT,
            started_at TEXT DEFAULT (datetime('now')),
            completed_at TEXT,
            result TEXT
        );

        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            message TEXT,
            level TEXT DEFAULT 'info',
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)

    # Seed default agents
    agents = [
        ("Atlas", "orchestrator", "kimi-for-coding/k2p7", "idle", "Central coordinator — decomposes objectives, dispatches tasks"),
        ("Scout", "researcher", "kimi-for-coding/kimi-k2-thinking", "idle", "Deep research, data gathering, analysis"),
        ("Forge", "builder", "kimi-for-coding/k2p7", "idle", "Writes code, builds systems, deploys"),
        ("Pulse", "monitor", "kimi-for-coding/kimi-for-coding-highspeed", "idle", "Watches schedules, checks health, pushes alerts"),
        ("Echo", "comms", "xai/grok-3-mini", "idle", "Handles email, notifications, external comms"),
    ]
    for name, role, model, status, desc in agents:
        await db.execute(
            "INSERT OR IGNORE INTO agents (name, role, model, status, config) VALUES (?, ?, ?, ?, ?)",
            (name, role, model, status, desc)
        )

    # Seed default scheduled tasks
    tasks = [
        ("Health Check", "scheduled", "pulse", "*/15 * * * *", "Check all systems status"),
        ("Data Sync", "scheduled", "scout", "0 */6 * * *", "Sync contacts, bookings, revenue data"),
        ("Report Generator", "scheduled", "atlas", "0 9 * * *", "Generate daily summary report"),
    ]
    for name, ttype, agent, cron, desc in tasks:
        await db.execute(
            "INSERT OR IGNORE INTO tasks (name, type, agent, scheduled_cron, result) VALUES (?, ?, ?, ?, ?)",
            (name, ttype, agent, cron, desc)
        )

    await db.commit()
    await db.close()


# === CRUD Helpers ===

async def log_activity(source: str, message: str, level: str = "info"):
    db = await get_db()
    await db.execute(
        "INSERT INTO activity_log (source, message, level) VALUES (?, ?, ?)",
        (source, message, level)
    )
    await db.commit()
    await db.close()


async def get_tasks():
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM tasks ORDER BY created_at DESC")
    await db.close()
    return [dict(r) for r in rows]


async def get_agents():
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM agents ORDER BY id")
    await db.close()
    return [dict(r) for r in rows]


async def get_plugins():
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM plugins ORDER BY name")
    await db.close()
    return [dict(r) for r in rows]


async def get_sites():
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM sites ORDER BY created_at DESC")
    await db.close()
    return [dict(r) for r in rows]


async def get_swarm_runs():
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM swarm_runs ORDER BY started_at DESC LIMIT 20")
    await db.close()
    return [dict(r) for r in rows]


async def get_activity(limit: int = 50):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,)
    )
    await db.close()
    return [dict(r) for r in rows]


async def get_task_results(task_id: int):
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM task_results WHERE task_id = ? ORDER BY created_at DESC LIMIT 10",
        (task_id,)
    )
    await db.close()
    return [dict(r) for r in rows]


async def update_task_status(task_id: int, status: str, progress: int = None, result: str = None):
    db = await get_db()
    if progress is not None and result is not None:
        await db.execute(
            "UPDATE tasks SET status=?, progress=?, result=?, updated_at=datetime('now') WHERE id=?",
            (status, progress, result, task_id)
        )
    elif progress is not None:
        await db.execute(
            "UPDATE tasks SET status=?, progress=?, updated_at=datetime('now') WHERE id=?",
            (status, progress, task_id)
        )
    else:
        await db.execute(
            "UPDATE tasks SET status=?, updated_at=datetime('now') WHERE id=?",
            (status, task_id)
        )
    await db.commit()
    await db.close()


async def update_agent_status(agent_id: int, status: str):
    db = await get_db()
    await db.execute(
        "UPDATE agents SET status=?, last_active=datetime('now') WHERE id=?",
        (status, agent_id)
    )
    await db.commit()
    await db.close()


async def add_task_result(task_id: int, output: str, status: str, duration_ms: int = 0):
    db = await get_db()
    await db.execute(
        "INSERT INTO task_results (task_id, output, status, duration_ms) VALUES (?, ?, ?, ?)",
        (task_id, output, status, duration_ms)
    )
    await db.commit()
    await db.close()


async def add_swarm_run(objective: str, agents_used: str = ""):
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO swarm_runs (objective, agents_used) VALUES (?, ?)",
        (objective, agents_used)
    )
    run_id = cursor.lastrowid
    await db.commit()
    await db.close()
    return run_id


async def complete_swarm_run(run_id: int, result: str, status: str = "completed"):
    db = await get_db()
    await db.execute(
        "UPDATE swarm_runs SET status=?, result=?, completed_at=datetime('now') WHERE id=?",
        (status, result, run_id)
    )
    await db.commit()
    await db.close()
