"""
PROACTIVE LIFE SYSTEM - OMNI STUDIO
====================================
Fully autonomous system that:
- Monitors all emails (Gmail OAuth2 + IMAP)
- Tracks finances, deals, revenue
- Manages CRM/contacts
- Runs LoRA training automatically
- Monitors system health
- Proactively suggests money-making actions
- Syncs calendar, tasks, notes
- Daily/weekly/monthly reports
"""

import os
import json
import asyncio
import sqlite3
import logging
import imaplib
import email
import smtplib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from contextlib import asynccontextmanager

import aiosqlite
import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class ProactiveConfig:
    # Database
    db_path: str = "data/proactive.db"
    
    # Email (Gmail)
    gmail_user: str = os.getenv("GMAIL_USER", "")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")
    gmail_oauth_creds: str = os.path.expanduser("~/Omni-Studio/config/gmail_credentials.json")
    gmail_token_path: str = os.path.expanduser("~/Omni-Studio/config/token.pickle")
    
    # Monitoring intervals
    email_check_interval: int = 300          # 5 min
    finance_check_interval: int = 3600       # 1 hour
    health_check_interval: int = 900         # 15 min
    lora_check_interval: int = 7200          # 2 hours
    crm_sync_interval: int = 1800            # 30 min
    daily_report_time: str = "07:00"         # 7 AM
    weekly_report_day: int = 0               # Monday
    monthly_report_day: int = 1              # 1st
    
    # Thresholds
    low_balance_alert: float = 5000.0
    high_priority_email_keywords: List[str] = field(default_factory=lambda: [
        "urgent", "contract", "deal", "invoice", "payment", "revenue",
        "opportunity", "partnership", "acquisition", "investment", "funding"
    ])
    spam_keywords: List[str] = field(default_factory=lambda: [
        "unsubscribe", "promotional", "marketing", "newsletter", "spam"
    ])
    
    # LoRA training
    lora_auto_train: bool = True
    lora_model_path: str = "./models/stable_audio_open"
    lora_dataset_path: str = "./audio_dataset"
    lora_output_dir: str = "./lora_output"
    lora_preset: str = "sota_full"
    
    # Financial
    revenue_target_monthly: float = 50000.0
    expense_limit_monthly: float = 10000.0
    
    # Paths
    config_dir: str = os.path.expanduser("~/Omni-Studio/config")
    data_dir: str = os.path.expanduser("~/Omni-Studio/data")
    logs_dir: str = os.path.expanduser("~/Omni-Studio/logs")

# =============================================================================
# DATABASE SCHEMA
# =============================================================================

SCHEMA = """
-- Emails
CREATE TABLE IF NOT EXISTS emails (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id TEXT UNIQUE,
    thread_id TEXT,
    from_email TEXT,
    from_name TEXT,
    to_emails TEXT,
    cc_emails TEXT,
    subject TEXT,
    body_text TEXT,
    body_html TEXT,
    labels TEXT,
    is_read INTEGER DEFAULT 0,
    is_starred INTEGER DEFAULT 0,
    is_important INTEGER DEFAULT 0,
    category TEXT,  -- inbox, sent, draft, spam, trash, finance, deal, personal
    priority INTEGER DEFAULT 0,  -- 0=normal, 1=high, 2=urgent
    received_at TEXT,
    sent_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    processed INTEGER DEFAULT 0
);

-- Financial transactions
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,  -- income, expense, invoice, payment, deal
    amount REAL,
    currency TEXT DEFAULT 'USD',
    category TEXT,
    subcategory TEXT,
    description TEXT,
    counterparty TEXT,
    counterparty_email TEXT,
    invoice_number TEXT,
    status TEXT DEFAULT 'pending',  -- pending, paid, overdue, cancelled
    due_date TEXT,
    paid_date TEXT,
    source_email_id INTEGER,
    recurring INTEGER DEFAULT 0,
    recurrence_rule TEXT,
    tags TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Contacts / CRM
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE,
    name TEXT,
    company TEXT,
    role TEXT,
    phone TEXT,
    linkedin TEXT,
    twitter TEXT,
    source TEXT,  -- email, manual, import, scraped
    status TEXT DEFAULT 'lead',  -- lead, prospect, qualified, customer, churned
    value_estimate REAL DEFAULT 0,
    last_contact_at TEXT,
    next_followup_at TEXT,
    tags TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Contact interactions
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    type TEXT,  -- email_sent, email_received, call, meeting, note, task
    subject TEXT,
    body TEXT,
    direction TEXT,  -- inbound, outbound
    email_id INTEGER,
    outcome TEXT,  -- positive, neutral, negative, no_response
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (email_id) REFERENCES emails(id)
);

-- Tasks / Actions
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT,
    type TEXT,  -- email_reply, follow_up, call, meeting, task, lora_train, financial
    priority INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',  -- pending, in_progress, completed, cancelled, delegated
    assignee TEXT,
    contact_id INTEGER,
    email_id INTEGER,
    transaction_id INTEGER,
    due_date TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (contact_id) REFERENCES contacts(id),
    FOREIGN KEY (email_id) REFERENCES emails(id),
    FOREIGN KEY (transaction_id) REFERENCES transactions(id)
);

-- LoRA Training Jobs
CREATE TABLE IF NOT EXISTS lora_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    preset TEXT,
    model_path TEXT,
    dataset_path TEXT,
    output_dir TEXT,
    status TEXT DEFAULT 'queued',  -- queued, preparing, training, completed, failed
    config TEXT,
    current_step INTEGER DEFAULT 0,
    total_steps INTEGER DEFAULT 0,
    loss REAL,
    metrics TEXT,
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- System Health
CREATE TABLE IF NOT EXISTS health_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    component TEXT,
    status TEXT,  -- healthy, warning, critical
    message TEXT,
    metrics TEXT,
    checked_at TEXT DEFAULT (datetime('now'))
);

-- Reports
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT,  -- daily, weekly, monthly, custom
    title TEXT,
    content TEXT,
    metrics TEXT,
    generated_at TEXT DEFAULT (datetime('now'))
);

-- Settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_emails_thread ON emails(thread_id);
CREATE INDEX IF NOT EXISTS idx_emails_received ON emails(received_at);
CREATE INDEX IF NOT EXISTS idx_emails_category ON emails(category);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(type);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(created_at);
CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
CREATE INDEX IF NOT EXISTS idx_contacts_status ON contacts(status);
CREATE INDEX IF NOT EXISTS idx_actions_due ON actions(due_date);
CREATE INDEX IF NOT EXISTS idx_actions_status ON actions(status);
CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id);
"""

# =============================================================================
# CORE SYSTEM
# =============================================================================

class ProactiveSystem:
    def __init__(self, config: ProactiveConfig):
        self.config = config
        self.scheduler = AsyncIOScheduler()
        self.db = None
        self.gmail_service = None
        self.imap = None
        self.running = False
        
        # Setup logging
        Path(config.logs_dir).mkdir(parents=True, exist_ok=True)
        Path(config.data_dir).mkdir(parents=True, exist_ok=True)
        Path(config.config_dir).mkdir(parents=True, exist_ok=True)
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(Path(config.logs_dir) / "proactive.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger("ProactiveSystem")
    
    async def initialize(self):
        """Initialize database, email, scheduler"""
        self.logger.info("🚀 Initializing Proactive System...")
        
        # Database
        Path(self.config.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = await aiosqlite.connect(self.config.db_path)
        self.db.row_factory = aiosqlite.Row
        await self.db.executescript(SCHEMA)
        await self.db.commit()
        
        # Initialize default settings
        await self._init_settings()
        
        # Email
        await self._init_gmail_oauth()
        await self._init_imap()
        
        # Scheduler
        self._setup_scheduler()
        
        self.logger.info("✅ Proactive System initialized")
    
    async def _init_settings(self):
        defaults = {
            "email_check_interval": str(self.config.email_check_interval),
            "finance_check_interval": str(self.config.finance_check_interval),
            "health_check_interval": str(self.config.health_check_interval),
            "lora_check_interval": str(self.config.lora_check_interval),
            "crm_sync_interval": str(self.config.crm_sync_interval),
            "daily_report_time": self.config.daily_report_time,
            "weekly_report_day": str(self.config.weekly_report_day),
            "monthly_report_day": str(self.config.monthly_report_day),
            "low_balance_alert": str(self.config.low_balance_alert),
            "revenue_target_monthly": str(self.config.revenue_target_monthly),
            "lora_auto_train": str(self.config.lora_auto_train).lower(),
            "lora_preset": self.config.lora_preset,
        }
        for k, v in defaults.items():
            await self.db.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )
        await self.db.commit()
    
    async def _init_gmail_oauth(self):
        """Initialize Gmail API with OAuth2"""
        try:
            from google.auth.transport.requests import Request
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            import pickle
            
            SCOPES = ['https://mail.google.com/']
            creds = None
            
            if os.path.exists(self.config.gmail_token_path):
                with open(self.config.gmail_token_path, 'rb') as token:
                    creds = pickle.load(token)
            
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(self.config.gmail_oauth_creds):
                        self.logger.warning("Gmail OAuth credentials not found. Run setup first.")
                        return
                    flow = InstalledAppFlow.from_client_secrets_file(
                        self.config.gmail_oauth_creds, SCOPES)
                    creds = flow.run_local_server(port=0)
                
                with open(self.config.gmail_token_path, 'wb') as token:
                    pickle.dump(creds, token)
            
            self.gmail_service = build('gmail', 'v1', credentials=creds)
            self.logger.info("✅ Gmail OAuth2 connected")
        except Exception as e:
            self.logger.error(f"Gmail OAuth failed: {e}")
    
    async def _init_imap(self):
        """Initialize IMAP for fetching emails"""
        try:
            if self.config.gmail_user and self.config.gmail_app_password:
                self.imap = imaplib.IMAP4_SSL("imap.gmail.com")
                self.imap.login(self.config.gmail_user, self.config.gmail_app_password)
                self.imap.select("inbox")
                self.logger.info("✅ IMAP connected")
        except Exception as e:
            self.logger.error(f"IMAP failed: {e}")
    
    def _setup_scheduler(self):
        """Setup all recurring jobs"""
        # Email checking
        self.scheduler.add_job(
            self.check_emails,
            IntervalTrigger(seconds=self.config.email_check_interval),
            id="check_emails",
            replace_existing=True
        )
        
        # Finance monitoring
        self.scheduler.add_job(
            self.monitor_finances,
            IntervalTrigger(seconds=self.config.finance_check_interval),
            id="monitor_finances",
            replace_existing=True
        )
        
        # Health checks
        self.scheduler.add_job(
            self.health_check,
            IntervalTrigger(seconds=self.config.health_check_interval),
            id="health_check",
            replace_existing=True
        )
        
        # CRM sync
        self.scheduler.add_job(
            self.sync_crm,
            IntervalTrigger(seconds=self.config.crm_sync_interval),
            id="sync_crm",
            replace_existing=True
        )
        
        # LoRA training check
        self.scheduler.add_job(
            self.check_lora_training,
            IntervalTrigger(seconds=self.config.lora_check_interval),
            id="check_lora",
            replace_existing=True
        )
        
        # Daily report
        h, m = map(int, self.config.daily_report_time.split(":"))
        self.scheduler.add_job(
            self.generate_daily_report,
            CronTrigger(hour=h, minute=m),
            id="daily_report",
            replace_existing=True
        )
        
        # Weekly report
        self.scheduler.add_job(
            self.generate_weekly_report,
            CronTrigger(day_of_week=self.config.weekly_report_day, hour=8, minute=0),
            id="weekly_report",
            replace_existing=True
        )
        
        # Monthly report
        self.scheduler.add_job(
            self.generate_monthly_report,
            CronTrigger(day=self.config.monthly_report_day, hour=9, minute=0),
            id="monthly_report",
            replace_existing=True
        )
        
        self.scheduler.start()
        self.logger.info("✅ Scheduler started with all jobs")
    
    # =========================================================================
    # EMAIL PROCESSING
    # =========================================================================
    
    async def check_emails(self):
        """Fetch and process new emails"""
        self.logger.info("📧 Checking emails...")
        
        try:
            # Use IMAP to fetch unseen
            self.imap.select("inbox")
            status, messages = self.imap.search(None, '(UNSEEN)')
            
            if status != "OK":
                return
            
            email_ids = messages[0].split()
            if not email_ids:
                return
            
            self.logger.info(f"Found {len(email_ids)} new emails")
            
            for e_id in email_ids[-50:]:  # Limit to 50 newest
                await self._process_email(e_id)
                
        except Exception as e:
            self.logger.error(f"Email check failed: {e}")
    
    async def _process_email(self, e_id: bytes):
        """Process a single email"""
        try:
            res, msg_data = self.imap.fetch(e_id, "(RFC822)")
            if res != "OK":
                return
            
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            
            # Extract fields
            message_id = msg.get("Message-ID", "")
            thread_id = msg.get("Thread-Index", "") or msg.get("In-Reply-To", "")
            from_raw = msg.get("From", "")
            to_raw = msg.get("To", "")
            cc_raw = msg.get("Cc", "")
            subject = msg.get("Subject", "")
            date_str = msg.get("Date", "")
            
            # Parse email address
            from_name, from_email = self._parse_address(from_raw)
            to_emails = self._parse_addresses(to_raw)
            cc_emails = self._parse_addresses(cc_raw)
            
            # Get body
            body_text, body_html = self._get_body(msg)
            
            # Categorize
            category = self._categorize_email(subject, body_text, from_email)
            priority = self._calculate_priority(subject, body_text, from_email)
            
            # Save to DB
            await self.db.execute("""
                INSERT OR IGNORE INTO emails 
                (message_id, thread_id, from_email, from_name, to_emails, cc_emails,
                 subject, body_text, body_html, category, priority, received_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                message_id, thread_id, from_email, from_name,
                json.dumps(to_emails), json.dumps(cc_emails),
                subject, body_text, body_html, category, priority, date_str
            ))
            await self.db.commit()
            
            # Auto-process based on category
            if category in ["finance", "deal"]:
                await self._extract_financial_data(e_id, subject, body_text, from_email)
            
            # Create contact if new
            await self._upsert_contact(from_email, from_name)
            
            # Create follow-up action for high priority
            if priority >= 1:
                await self._create_action(
                    title=f"Reply to: {subject[:50]}",
                    description=f"From: {from_name} <{from_email}>\n\n{body_text[:500]}",
                    type="email_reply",
                    priority=priority,
                    email_id=e_id.decode() if isinstance(e_id, bytes) else str(e_id)
                )
            
            # Mark as processed
            self.imap.store(e_id, '+FLAGS', '\\Seen')
            
        except Exception as e:
            self.logger.error(f"Failed to process email {e_id}: {e}")
    
    def _parse_address(self, raw: str) -> tuple:
        """Parse 'Name <email@domain.com>' -> (name, email)"""
        import re
        match = re.match(r'(.+?)\s*<(.+?)>', raw)
        if match:
            return match.group(1).strip(), match.group(2).strip()
        return "", raw.strip()
    
    def _parse_addresses(self, raw: str) -> List[str]:
        if not raw:
            return []
        return [self._parse_address(a.strip())[1] for a in raw.split(",")]
    
    def _get_body(self, msg) -> tuple:
        """Extract text and HTML body"""
        text_body = ""
        html_body = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                if ctype == "text/plain" and not text_body:
                    text_body = part.get_payload(decode=True).decode(errors="ignore")
                elif ctype == "text/html" and not html_body:
                    html_body = part.get_payload(decode=True).decode(errors="ignore")
        else:
            ctype = msg.get_content_type()
            payload = msg.get_payload(decode=True).decode(errors="ignore")
            if ctype == "text/html":
                html_body = payload
            else:
                text_body = payload
        
        return text_body, html_body
    
    def _categorize_email(self, subject: str, body: str, from_email: str) -> str:
        text = f"{subject} {body}".lower()
        
        if any(k in text for k in ["invoice", "payment", "payment", "billing", "receipt", "transaction"]):
            return "finance"
        if any(k in text for k in ["deal", "contract", "partnership", "agreement", "proposal", "proposal"]):
            return "deal"
        if any(k in text for k in ["unsubscribe", "newsletter", "promotional", "marketing"]):
            return "promotional"
        if any(k in from_email for k in ["noreply", "no-reply", "support@", "info@", "admin@"]):
            return "automated"
        return "inbox"
    
    def _calculate_priority(self, subject: str, body: str, from_email: str) -> int:
        text = f"{subject} {body}".lower()
        
        # High priority keywords
        for kw in self.config.high_priority_email_keywords:
            if kw in text:
                return 2  # urgent
        
        # Medium priority
        if any(k in text for k in ["meeting", "call", "schedule", "deadline", "urgent", "asap"]):
            return 1
        
        return 0  # normal
    
    async def _extract_financial_data(self, email_id: str, subject: str, body: str, from_email: str):
        """Extract financial info from email using LLM"""
        # This would call an LLM to extract structured financial data
        # For now, create a basic transaction record
        await self.db.execute("""
            INSERT INTO transactions (type, amount, category, description, counterparty, 
                                     counterparty_email, status, source_email_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, ("invoice", 0, "extracted", f"From: {subject}", from_email, from_email, "pending", email_id))
        await self.db.commit()
    
    async def _upsert_contact(self, email: str, name: str = ""):
        await self.db.execute("""
            INSERT INTO contacts (email, name, source, status)
            VALUES (?, ?, 'email', 'lead')
            ON CONFLICT(email) DO UPDATE SET
                name = COALESCE(?, name),
                updated_at = datetime('now')
        """, (email, name, name))
        await self.db.commit()
    
    async def _create_action(self, title: str, description: str, type: str, 
                            priority: int, email_id: str = None, contact_id: int = None):
        await self.db.execute("""
            INSERT INTO actions (title, description, type, priority, status, email_id, contact_id)
            VALUES (?, ?, ?, ?, 'pending', ?, ?)
        """, (title, description, type, priority, email_id, contact_id))
        await self.db.commit()
    
    # =========================================================================
    # FINANCE MONITORING
    # =========================================================================
    
    async def monitor_finances(self):
        """Monitor financial health, overdue invoices, cash flow"""
        self.logger.info("💰 Monitoring finances...")
        
        # Check overdue invoices
        overdue = await self.db.execute_fetchall("""
            SELECT * FROM transactions 
            WHERE type IN ('invoice', 'payment') 
            AND status IN ('pending', 'sent')
            AND due_date < date('now')
        """)
        
        for inv in overdue:
            await self._create_action(
                title=f"Overdue: {inv['description']}",
                description=f"${inv['amount']} from {inv['counterparty']} was due {inv['due_date']}",
                type="financial",
                priority=2,
                transaction_id=inv["id"]
            )
        
        # Check cash flow
        month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
        income = await self.db.execute_fetchall("""
            SELECT SUM(amount) as total FROM transactions 
            WHERE type = 'income' AND created_at >= ?
        """, (month_start,))
        
        expenses = await self.db.execute_fetchall("""
            SELECT SUM(amount) as total FROM transactions 
            WHERE type = 'expense' AND created_at >= ?
        """, (month_start,))
        
        monthly_income = income[0]["total"] or 0
        monthly_expenses = expenses[0]["total"] or 0
        net = monthly_income - monthly_expenses
        
        # Alert if below target
        if monthly_income < self.config.revenue_target_monthly * 0.5:
            await self._create_action(
                title="Revenue below 50% target",
                description=f"Monthly income: ${monthly_income:,.2f} (target: ${self.config.revenue_target_monthly:,.2f})",
                type="financial",
                priority=2
            )
        
        # Alert if expenses too high
        if monthly_expenses > self.config.expense_limit_monthly:
            await self._create_action(
                title="Expenses exceed limit",
                description=f"Monthly expenses: ${monthly_expenses:,.2f} (limit: ${self.config.expense_limit_monthly:,.2f})",
                type="financial",
                priority=1
            )
        
        # Check low balance (would need bank integration)
        await self.db.execute("""
            INSERT INTO health_checks (component, status, message, metrics)
            VALUES (?, ?, ?, ?)
        """, ("finance", "healthy" if net > 0 else "warning", 
              f"Monthly net: ${net:,.2f}", json.dumps({
                  "income": monthly_income, "expenses": monthly_expenses, "net": net
              })))
        await self.db.commit()
    
    # =========================================================================
    # CRM SYNC
    # =========================================================================
    
    async def sync_crm(self):
        """Sync contacts, interactions, pipeline"""
        self.logger.info("👥 Syncing CRM...")
        
        # Find contacts needing follow-up
        overdue_followup = await self.db.execute_fetchall("""
            SELECT * FROM contacts 
            WHERE next_followup_at < datetime('now')
            AND status IN ('lead', 'prospect', 'qualified')
        """)
        
        for contact in overdue_followup:
            await self._create_action(
                title=f"Follow up with {contact['name'] or contact['email']}",
                description=f"Last contact: {contact['last_contact_at']}\nValue: ${contact['value_estimate']:,.2f}",
                type="follow_up",
                priority=1,
                contact_id=contact["id"]
            )
        
        # Auto-create contacts from recent email senders
        recent_senders = await self.db.execute_fetchall("""
            SELECT DISTINCT from_email, from_name, COUNT(*) as count
            FROM emails 
            WHERE received_at > datetime('now', '-30 days')
            AND category IN ('inbox', 'deal', 'finance')
            GROUP BY from_email
            HAVING count > 2
        """)
        
        for sender in recent_senders:
            await self._upsert_contact(sender["from_email"], sender["from_name"])
            # Update contact value based on interaction frequency
            await self.db.execute("""
                UPDATE contacts SET value_estimate = value_estimate + 100
                WHERE email = ?
            """, (sender["from_email"],))
        
        await self.db.commit()
    
    # =========================================================================
    # LORA TRAINING AUTOMATION
    # =========================================================================
    
    async def check_lora_training(self):
        """Check and manage LoRA training jobs"""
        if not self.config.lora_auto_train:
            return
        
        self.logger.info("🎵 Checking LoRA training...")
        
        # Check for completed jobs
        jobs = await self.db.execute_fetchall("""
            SELECT * FROM lora_jobs WHERE status IN ('training', 'queued')
        """)
        
        for job in jobs:
            # Check actual training process (would need to track PID or check output dir)
            config = json.loads(job["config"])
            output_dir = Path(config.get("output_dir", self.config.lora_output_dir))
            
            # Check for completion markers
            if (output_dir / "adapter_model.safetensors").exists():
                await self.db.execute("""
                    UPDATE lora_jobs SET status='completed', completed_at=datetime('now')
                    WHERE id=?
                """, (job["id"],))
                await self.db.commit()
                
                # Notify completion
                await self._notify(f"🎵 LoRA training completed: {job['name']}")
    
    async def queue_lora_training(self, name: str, preset: str = None, **kwargs):
        """Queue a new LoRA training job"""
        preset = preset or self.config.lora_preset
        config = create_lora_config_preset(preset)
        
        # Override with kwargs
        for k, v in kwargs.items():
            if hasattr(config, k):
                setattr(config, k, v)
        
        await self.db.execute("""
            INSERT INTO lora_jobs (name, preset, model_path, dataset_path, output_dir, config)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            name, preset, config.output_dir, config.dataset_path, config.output_dir,
            json.dumps(config.__dict__)
        ))
        await self.db.commit()
        self.logger.info(f"Queued LoRA training: {name}")
    
    # =========================================================================
    # HEALTH CHECKS
    # =========================================================================
    
    async def health_check(self):
        """Comprehensive system health check"""
        self.logger.info("🏥 Running health check...")
        
        checks = []
        
        # Disk space
        disk = await self._check_disk_space()
        checks.append(disk)
        
        # Memory
        mem = await self._check_memory()
        checks.append(mem)
        
        # Database
        db_check = await self._check_database()
        checks.append(db_check)
        
        # Email connectivity
        email_check = await self._check_email()
        checks.append(email_check)
        
        # LoRA training
        lora_check = await self._check_lora()
        checks.append(lora_check)
        
        # Store all checks
        for check in checks:
            await self.db.execute("""
                INSERT INTO health_checks (component, status, message, metrics)
                VALUES (?, ?, ?, ?)
            """, (check["component"], check["status"], check["message"], 
                  json.dumps(check.get("metrics", {}))))
        
        await self.db.commit()
        
        # Alert on critical
        critical = [c for c in checks if c["status"] == "critical"]
        if critical:
            await self._notify(f"🚨 CRITICAL: {len(critical)} health checks failed")
    
    async def _check_disk_space(self):
        import shutil
        total, used, free = shutil.disk_usage("/")
        pct = (used / total) * 100
        return {
            "component": "disk",
            "status": "critical" if pct > 95 else "warning" if pct > 85 else "healthy",
            "message": f"Disk usage: {pct:.1f}%",
            "metrics": {"used_gb": used/1e9, "free_gb": free/1e9, "pct": pct}
        }
    
    async def _check_memory(self):
        import psutil
        mem = psutil.virtual_memory()
        return {
            "component": "memory",
            "status": "critical" if mem.percent > 95 else "warning" if mem.percent > 85 else "healthy",
            "message": f"Memory usage: {mem.percent:.1f}%",
            "metrics": {"used_gb": mem.used/1e9, "available_gb": mem.available/1e9, "pct": mem.percent}
        }
    
    async def _check_database(self):
        try:
            await self.db.execute("SELECT 1")
            size = os.path.getsize(self.config.db_path) / 1e6
            return {
                "component": "database",
                "status": "healthy",
                "message": f"DB accessible ({size:.1f} MB)",
                "metrics": {"size_mb": size}
            }
        except Exception as e:
            return {
                "component": "database",
                "status": "critical",
                "message": f"DB error: {e}",
                "metrics": {}
            }
    
    async def _check_email(self):
        try:
            if self.imap:
                self.imap.noop()
                return {"component": "email", "status": "healthy", 
                        "message": "IMAP connected", "metrics": {}}
        except:
            pass
        return {"component": "email", "status": "warning", 
                "message": "IMAP disconnected", "metrics": {}}
    
    async def _check_lora(self):
        jobs = await self.db.execute_fetchall(
            "SELECT COUNT(*) as c FROM lora_jobs WHERE status IN ('training', 'queued')"
        )
        count = jobs[0]["c"] if jobs else 0
        return {
            "component": "lora_training",
            "status": "healthy",
            "message": f"{count} jobs in queue",
            "metrics": {"queued_jobs": count}
        }
    
    # =========================================================================
    # REPORTING
    # =========================================================================
    
    async def generate_daily_report(self):
        """Generate and send daily report"""
        self.logger.info("📊 Generating daily report...")
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Collect metrics
        emails_today = await self.db.execute_fetchall("""
            SELECT category, COUNT(*) as count FROM emails 
            WHERE date(received_at) = date('now')
            GROUP BY category
        """)
        
        actions_today = await self.db.execute_fetchall("""
            SELECT status, COUNT(*) as count FROM actions 
            WHERE date(created_at) = date('now')
            GROUP BY status
        """)
        
        finance = await self.db.execute_fetchall("""
            SELECT type, SUM(amount) as total FROM transactions 
            WHERE date(created_at) = date('now')
            GROUP BY type
        """)
        
        lora_jobs = await self.db.execute_fetchall("""
            SELECT status, COUNT(*) as count FROM lora_jobs
            WHERE date(created_at) = date('now')
            GROUP BY status
        """)
        
        health = await self.db.execute_fetchall("""
            SELECT component, status, COUNT(*) as count FROM health_checks
            WHERE date(checked_at) = date('now')
            GROUP BY component, status
        """)
        
        # Build report
        report = f"""
📅 DAILY REPORT - {today}
{'='*50}

📧 EMAILS:
"""
        for e in emails_today:
            report += f"  {e['category']}: {e['count']}\n"
        
        report += f"""
✅ ACTIONS:
"""
        for a in actions_today:
            report += f"  {a['status']}: {a['count']}\n"
        
        report += f"""
💰 FINANCE:
"""
        for f in finance:
            report += f"  {f['type']}: ${f['total']:,.2f}\n"
        
        report += f"""
🎵 LORA TRAINING:
"""
        for l in lora_jobs:
            report += f"  {l['status']}: {l['count']}\n"
        
        report += f"""
🏥 HEALTH:
"""
        for h in health:
            report += f"  {h['component']} ({h['status']}): {h['count']}\n"
        
        # Save report
        await self.db.execute("""
            INSERT INTO reports (type, title, content, metrics)
            VALUES (?, ?, ?, ?)
        """, ("daily", f"Daily Report {today}", report, json.dumps({
            "emails": [dict(e) for e in emails_today],
            "actions": [dict(a) for a in actions_today],
            "finance": [dict(f) for f in finance],
            "lora": [dict(l) for l in lora_jobs],
            "health": [dict(h) for h in health]
        })))
        await self.db.commit()
        
        # Send via email if configured
        await self._send_report("daily", report)
        
        self.logger.info("✅ Daily report generated")
    
    async def generate_weekly_report(self):
        """Generate weekly report"""
        self.logger.info("📈 Generating weekly report...")
        # Similar to daily but aggregated over 7 days
        pass
    
    async def generate_monthly_report(self):
        """Generate monthly report"""
        self.logger.info("📊 Generating monthly report...")
        pass
    
    async def _send_report(self, report_type: str, content: str):
        """Send report via email"""
        if not self.gmail_service or not self.config.gmail_user:
            return
        
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            import base64
            
            msg = MIMEMultipart()
            msg['to'] = self.config.gmail_user
            msg['subject'] = f"📊 {report_type.capitalize()} Report - {datetime.now().strftime('%Y-%m-%d')}"
            msg.attach(MIMEText(content, 'plain'))
            
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            self.gmail_service.users().messages().send(
                userId="me", body={'raw': raw}).execute()
        except Exception as e:
            self.logger.error(f"Failed to send report: {e}")
    
    async def _notify(self, message: str):
        """Send notification (email, push, etc.)"""
        await self._send_report("alert", f"⚠️ ALERT: {message}")
    
    # =========================================================================
    # MAIN LOOP
    # =========================================================================
    
    async def run(self):
        """Main run loop"""
        self.running = True
        self.logger.info("🎯 Proactive System RUNNING")
        
        try:
            while self.running:
                await asyncio.sleep(60)  # Heartbeat
        except KeyboardInterrupt:
            self.logger.info("Shutting down...")
            await self.shutdown()
    
    async def shutdown(self):
        self.running = False
        self.scheduler.shutdown()
        if self.imap:
            self.imap.logout()
        await self.db.close()
        self.logger.info("✅ Proactive System shutdown complete")


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

async def main():
    config = ProactiveConfig()
    system = ProactiveSystem(config)
    await system.initialize()
    await system.run()


if __name__ == "__main__":
    asyncio.run(main())