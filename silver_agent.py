#!/usr/bin/env python3
"""
SilverAgent - Stripped Down CPU-Optimized Version with Rich UI
No GPU required. Uses minimal resources.

Simple 4-step flow:
1. Read Gmail
2. Generate reply with qwen2.5:1.5b (no streaming, simple prompt)
3. Save to SQLite + Obsidian
4. Notify Discord
"""

import os
import re
import json
import time
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

# Rich Terminal UI
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.columns import Columns
from rich.align import Align
from rich.text import Text
from rich import box
from rich.live import Live
from rich.spinner import Spinner

import ollama
import requests
from email.mime.text import MIMEText

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
import base64

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config:
    """Simple configuration."""
    # Ollama - HARDCODED for CPU efficiency
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL = "qwen2.5:1.5b"  # HARDCODED - small, fast, CPU-friendly

    # Gmail
    GMAIL_CREDENTIALS_PATH = os.getenv("GMAIL_CREDENTIALS_PATH", "credentials.json")
    GMAIL_TOKEN_PATH = os.getenv("GMAIL_TOKEN_PATH", "token.json")

    # Discord
    DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "https://discord.com/api/webhooks/1487862809629950152/G3n-kuQ7Bdmz1HERxykrtvzqUMKR0VBkRMQsD4hBGdmVwN_3NkkDk8kfxSMghOFrf1mD")

    # Paths
    OBSIDIAN_VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", "golden_database.md"))
    SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", "silver_agent.db"))

    # Agent settings
    AGENT_CYCLE_INTERVAL = int(os.getenv("AGENT_CYCLE_INTERVAL", "60"))  # seconds


# ============================================================================
# SQLITE DATABASE
# ============================================================================

class SQLiteStore:
    """Simple SQLite storage for email interactions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Create table if not exists."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS email_interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender TEXT NOT NULL,
                subject TEXT NOT NULL,
                email_body TEXT,
                reply TEXT,
                received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def save_interaction(self, sender: str, subject: str, email_body: str, reply: str) -> bool:
        """Save email and reply to database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO email_interactions (sender, subject, email_body, reply, processed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (sender, subject, email_body, reply, datetime.now()))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            return False

    def get_stats(self) -> Dict:
        """Get simple stats."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM email_interactions")
            total = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM email_interactions WHERE date(processed_at) = date('now')")
            today = cursor.fetchone()[0]
            conn.close()
            return {"total": total, "today": today}
        except:
            return {"total": 0, "today": 0}


# ============================================================================
# EMAIL CLEANER
# ============================================================================

class EmailCleaner:
    """Minimal text cleaning - no heavy processing."""

    @staticmethod
    def clean(body: str, max_chars: int = 1500) -> str:
        """Strip HTML and truncate."""
        if not body:
            return ""
        # Remove HTML
        text = re.sub(r'<[^>]+>', ' ', body)
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text)
        # Truncate
        if len(text) > max_chars:
            text = text[:max_chars] + "..."
        return text.strip()


# ============================================================================
# OLLAMA CLIENT - CPU OPTIMIZED
# ============================================================================

class OllamaClient:
    """Minimal Ollama client - stream=False for CPU efficiency."""

    def __init__(self):
        self.client = ollama.Client(host=Config.OLLAMA_HOST)
        self.model = Config.OLLAMA_MODEL

    def generate_reply(self, sender: str, subject: str, body: str) -> str:
        """Generate a simple polite reply. No chain-of-thought."""
        system_prompt = "You are a polite email assistant. Write brief, professional replies."

        user_prompt = f"""Write a short, polite reply to this email:

From: {sender}
Subject: {subject}
Body: {body[:1000]}

Reply:"""

        try:
            response = self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                options={"temperature": 0.5},  # Lower temp for faster, more consistent output
                stream=False  # CRITICAL: saves CPU cycles
            )
            return response['message']['content'].strip()
        except Exception as e:
            return "Thank you for your email. I will review and respond shortly."


# ============================================================================
# GMAIL CLIENT
# ============================================================================

class GmailClient:
    """Simple Gmail client."""

    def __init__(self):
        self.service = None

    def authenticate(self) -> bool:
        """Authenticate with Gmail."""
        try:
            SCOPES = ['https://www.googleapis.com/auth/gmail.modify']

            creds = None
            if os.path.exists(Config.GMAIL_TOKEN_PATH):
                creds = Credentials.from_authorized_user_file(Config.GMAIL_TOKEN_PATH, SCOPES)

            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    if not os.path.exists(Config.GMAIL_CREDENTIALS_PATH):
                        return False
                    flow = InstalledAppFlow.from_client_secrets_file(
                        Config.GMAIL_CREDENTIALS_PATH, SCOPES)
                    creds = flow.run_local_server(port=0)

                with open(Config.GMAIL_TOKEN_PATH, 'w') as token:
                    token.write(creds.to_json())

            self.service = build('gmail', 'v1', credentials=creds)
            return True
        except Exception as e:
            return False

    def fetch_unread(self, after_timestamp: Optional[datetime] = None) -> Tuple[List[Dict], int]:
        """Fetch unread emails received after the given timestamp.

        Args:
            after_timestamp: Only return emails received after this time

        Returns:
            Tuple of (filtered_emails, skipped_count)
        """
        emails = []
        skipped_count = 0

        if not self.service:
            if not self.authenticate():
                return emails, skipped_count

        try:
            query = "is:unread"
            if after_timestamp:
                timestamp_sec = int(after_timestamp.timestamp())
                query += f" after:{timestamp_sec}"

            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=10
            ).execute()

            messages = results.get('messages', [])

            for msg in messages:
                detail = self.service.users().messages().get(
                    userId='me', id=msg['id']
                ).execute()

                headers = detail['payload'].get('headers', [])
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                sender = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')

                # Skip old emails (received before agent started)
                internal_date_ms = int(detail.get('internalDate', 0))
                msg_time = datetime.fromtimestamp(internal_date_ms / 1000)
                if after_timestamp and msg_time < after_timestamp:
                    skipped_count += 1
                    continue

                # Extract body
                body = ""
                payload = detail['payload']
                if 'parts' in payload:
                    for part in payload['parts']:
                        if part['mimeType'] == 'text/plain':
                            data = part['body'].get('data', '')
                            if data:
                                body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
                                break
                elif 'body' in payload:
                    data = payload['body'].get('data', '')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')

                # Capture threadId for reply threading
                thread_id = detail.get('threadId', msg['id'])

                emails.append({
                    'message_id': msg['id'],
                    'thread_id': thread_id,
                    'sender': sender,
                    'subject': subject,
                    'body': EmailCleaner.clean(body),
                    'received_at': msg_time
                })

        except Exception as e:
            pass

        return emails, skipped_count

    def mark_as_read(self, message_id: str):
        """Mark email as read (remove UNREAD label)."""
        try:
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
        except Exception as e:
            pass

    def send_reply(self, to_email: str, subject: str, original_message_id: str,
                   thread_id: str, reply_text: str) -> bool:
        """Send a reply email via Gmail API.

        Args:
            to_email: Recipient email address (original sender)
            subject: Original subject (will be prefixed with 'Re: ')
            original_message_id: Message-ID of original email for threading
            thread_id: Thread ID for keeping conversation thread intact
            reply_text: The reply body text

        Returns:
            True if sent successfully, False otherwise
        """
        try:
            # Extract clean email address from sender string
            # Handle formats like: "Name <email@example.com>" or "email@example.com"
            email_match = re.search(r'<([^>]+)>', to_email)
            if email_match:
                clean_to = email_match.group(1)
            else:
                clean_to = to_email.strip()

            # Create MIME message
            message = MIMEText(reply_text, 'plain', 'utf-8')
            message['to'] = clean_to

            # Add 'Re: ' prefix if not already present
            if not subject.lower().startswith('re:'):
                message['subject'] = f"Re: {subject}"
            else:
                message['subject'] = subject

            # Threading headers - critical for keeping email in same thread
            message['In-Reply-To'] = original_message_id

            # Build References header (append to existing or create new)
            # Use the Message-ID from original email
            message['References'] = original_message_id

            # Encode to base64url
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')

            # Send via Gmail API
            sent_message = self.service.users().messages().send(
                userId='me',
                body={
                    'raw': raw_message,
                    'threadId': thread_id
                }
            ).execute()

            return True
        except Exception as e:
            print(f"[GMAIL SEND ERROR] {e}")
            return False


# ============================================================================
# OBSIDIAN STORAGE
# ============================================================================

class ObsidianStore:
    """Append interactions to Obsidian vault file."""

    @staticmethod
    def append(sender: str, subject: str, email_body: str, reply: str) -> bool:
        """Append interaction to markdown file."""
        try:
            vault_path = Config.OBSIDIAN_VAULT_PATH
            vault_path.parent.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            content = f"""
## Email Processed - {timestamp}

**From:** {sender}
**Subject:** {subject}

### Original Email:
{email_body[:500]}{'...' if len(email_body) > 500 else ''}

### Generated Reply:
{reply}

---
"""
            with open(vault_path, 'a', encoding='utf-8') as f:
                f.write(content)

            return True
        except Exception as e:
            return False


# ============================================================================
# DISCORD NOTIFIER
# ============================================================================

class DiscordNotifier:
    """Send simple notifications to Discord."""

    @staticmethod
    def notify(sender: str, subject: str) -> bool:
        """Send notification to Discord webhook."""
        if not Config.DISCORD_WEBHOOK_URL:
            return False

        try:
            payload = {
                "content": f"New Email Processed",
                "embeds": [{
                    "title": f"From: {sender}",
                    "description": f"**Subject:** {subject}",
                    "color": 3447003,
                    "timestamp": datetime.now().isoformat()
                }]
            }

            response = requests.post(
                Config.DISCORD_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            return response.status_code == 204
        except Exception as e:
            return False


# ============================================================================
# MAIN AGENT - WITH RICH UI
# ============================================================================

class SilverAgent:
    """
    Stripped-down agent with 4-step flow and Rich UI:
    1. Read Gmail
    2. Generate Reply (simple, no skills)
    3. Save to SQLite + Obsidian
    4. Discord notification
    """

    def __init__(self):
        self.console = Console()
        self.gmail = GmailClient()
        self.llm = OllamaClient()
        self.db = SQLiteStore(Config.SQLITE_DB_PATH)
        self.cycle_results: List[Dict] = []
        # CAPTURE START TIME: Only process emails received after this timestamp
        self.start_time = datetime.utcnow()
        self.console.print(f"[dim]Agent started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]")
        self.console.print(f"[dim]Will only process emails received after this time.[/dim]")

    def _create_header(self) -> Panel:
        """Create beautiful header panel."""
        header_text = """
[cyan]╭────────────────────────────────────────────────────────────╮[/cyan]
[cyan]│[/cyan]  [bold white]🤖 SILVER AGENT v2.0[/bold white]                                    [cyan]│[/cyan]
[cyan]│[/cyan]  [dim]CPU Edition - Optimized for Low-Resource Systems[/dim]       [cyan]│[/cyan]
[cyan]╰────────────────────────────────────────────────────────────╯[/cyan]

[bold]Model:[/bold] [green]{model}[/green]
[bold]Database:[/bold] [blue]{db}[/blue]
[bold]Obsidian:[/bold] [magenta]{vault}[/magenta]
[bold]Cycle Interval:[/bold] [yellow]{interval}s[/yellow]
        """.strip().format(
            model=Config.OLLAMA_MODEL,
            db=Config.SQLITE_DB_PATH,
            vault=Config.OBSIDIAN_VAULT_PATH,
            interval=Config.AGENT_CYCLE_INTERVAL
        )
        return Panel(
            Align.center(header_text),
            border_style="cyan",
            box=box.DOUBLE,
            title="[bold cyan]Email AI Assistant[/bold cyan]",
            title_align="center"
        )

    def _step_panel(self, step_num: int, step_name: str, color: str) -> Panel:
        """Create a step panel."""
        return Panel(
            f"[bold {color}]{step_name}[/bold {color}]",
            border_style=color,
            width=30,
            box=box.ROUNDED
        )

    def _status_message(self, text: str, status: str) -> Text:
        """Create a status message."""
        if status == "success":
            return Text(f"✓ {text}", style="bold green")
        elif status == "failed":
            return Text(f"✗ {text}", style="bold red")
        elif status == "info":
            return Text(f"ℹ {text}", style="cyan")
        elif status == "processing":
            return Text(f"⚡ {text}", style="magenta")
        else:
            return Text(text)

    def process_email(self, email: Dict, email_num: int, total: int) -> bool:
        """Process a single email through the 5-step flow with Rich UI."""
        sender = email['sender']
        subject = email['subject']
        body = email['body']
        message_id = email['message_id']
        thread_id = email.get('thread_id', message_id)  # Fallback to message_id if no thread_id
        sender_short = sender[:40] + "..." if len(sender) > 40 else sender
        subject_short = subject[:50] + "..." if len(subject) > 50 else subject

        # Email Header Panel
        self.console.print()
        self.console.print(Panel(
            f"[bold cyan]From:[/bold cyan] {sender_short}\n"
            f"[bold cyan]Subject:[/bold cyan] {subject_short}",
            title=f"[bold]Email {email_num}/{total}[/bold]",
            border_style="blue",
            box=box.ROUNDED
        ))

        # Step 1: Gmail Reading (Blue/Cyan)
        self.console.print(self._step_panel(1, "📧 STEP 1: Reading Gmail", "cyan"))
        self.console.print(f"  [dim]Message ID:[/dim] {message_id[:20]}...")
        self.console.print(f"  [dim]Thread ID:[/dim] {thread_id[:20]}...")

        # Step 2: AI Generation (Magenta/Purple with spinner)
        self.console.print(self._step_panel(2, "🤖 STEP 2: AI Generation", "magenta"))
        with self.console.status("[magenta]Generating reply with qwen2.5:1.5b...", spinner="dots"):
            reply = self.llm.generate_reply(sender, subject, body)
        reply_preview = reply[:80].replace('\n', ' ')
        self.console.print(f"  [green]Reply:[/green] {reply_preview}...")

        # Step 2.5: SEND EMAIL (Critical!)
        self.console.print(self._step_panel(2.5, "📨 STEP 2.5: Sending Email", "bright_blue"))
        send_success = self.gmail.send_reply(
            to_email=sender,
            subject=subject,
            original_message_id=message_id,
            thread_id=thread_id,
            reply_text=reply
        )
        if send_success:
            self.console.print("  [bold green]✓ Gmail:[/bold green] SENT")
        else:
            self.console.print("  [bold red]✗ Gmail:[/bold red] FAILED")

        # Step 3: Database/Obsidian (Green for success, Red for failed)
        self.console.print(self._step_panel(3, "💾 STEP 3: Save Data", "green"))

        db_success = self.db.save_interaction(sender, subject, body, reply)
        if db_success:
            self.console.print("  [bold green]✓ SQLite:[/bold green] Saved successfully")
        else:
            self.console.print("  [bold red]✗ SQLite:[/bold red] Failed to save")

        obsidian_success = ObsidianStore.append(sender, subject, body, reply)
        if obsidian_success:
            self.console.print(f"  [bold green]✓ Obsidian:[/bold green] {Config.OBSIDIAN_VAULT_PATH}")
        else:
            self.console.print("  [bold red]✗ Obsidian:[/bold red] Failed to save")

        # Step 4: Discord (Yellow/Gold)
        self.console.print(self._step_panel(4, "📤 STEP 4: Discord Notify", "yellow"))
        discord_success = DiscordNotifier.notify(sender, subject)
        if discord_success:
            self.console.print("  [bold yellow]✓ Discord:[/bold yellow] Notification sent")
        else:
            self.console.print("  [dim]Discord: Skipped (no webhook)[/dim]")

        # Mark as read (only if email was sent successfully)
        if send_success:
            self.gmail.mark_as_read(message_id)

        # Store result for cycle summary table
        status = "[green]✓ Sent[/green]" if send_success else "[red]✗ Failed[/red]"
        self.cycle_results.append({
            "sender": sender_short,
            "subject": subject_short,
            "status": status
        })

        return send_success

    def _create_summary_table(self) -> Table:
        """Create cycle summary table."""
        table = Table(
            title="[bold cyan]Cycle Summary[/bold cyan]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold cyan"
        )
        table.add_column("Sender", style="blue", width=40)
        table.add_column("Subject", style="white", width=40)
        table.add_column("Status", style="green", width=15)

        for result in self.cycle_results:
            table.add_row(
                result["sender"],
                result["subject"],
                result["status"]
            )

        return table

    def run_cycle(self) -> int:
        """Run one processing cycle with Rich UI. Returns count of processed emails."""
        self.cycle_results = []
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # Cycle Header
        self.console.rule(f"[bold cyan]🔄 Cycle Start: {timestamp}[/bold cyan]", style="cyan")
        self.console.print(f"[dim]Model:[/dim] [magenta]{Config.OLLAMA_MODEL}[/magenta] [dim](CPU optimized)[/dim]")
        self.console.print()

        # Step 1: Read Gmail (only emails received after agent started)
        self.console.print(Panel(
            "[bold blue]📧 STEP 1: Reading Gmail[/bold blue]",
            border_style="blue",
            box=box.ROUNDED
        ))
        self.console.print(f"[dim]  Filtering for emails after: {self.start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]")

        emails, skipped_count = self.gmail.fetch_unread(after_timestamp=self.start_time)

        if skipped_count > 0:
            self.console.print(f"[dim]  Skipped {skipped_count} old unread email(s)[/dim]")

        if not emails:
            self.console.print("[dim]  No new emails found.[/dim]")
            self.console.rule(style="dim")
            return 0

        self.console.print(f"  [bold cyan]Found {len(emails)} new email(s)[/bold cyan]")

        # Process each email
        processed = 0
        for idx, email in enumerate(emails, 1):
            success = self.process_email(email, idx, len(emails))
            if success:
                processed += 1

        # Cycle Summary
        self.console.print()
        self.console.rule("[bold green]Cycle Complete[/bold green]", style="green")

        # Show summary table
        if self.cycle_results:
            self.console.print(self._create_summary_table())

        # Show stats
        stats = self.db.get_stats()
        stats_text = (
            f"[bold]Processed:[/bold] {processed} | "
            f"[bold]Database:[/bold] {stats['total']} total, {stats['today']} today"
        )
        self.console.print(Panel(stats_text, border_style="dim", box=box.SIMPLE))
        self.console.print()

        return processed

    def run_forever(self):
        """Run continuous loop with Rich UI."""
        # Print beautiful header
        self.console.print(self._create_header())
        self.console.print()

        # Test Ollama connection
        try:
            client = ollama.Client(host=Config.OLLAMA_HOST)
            client.list()
            self.console.print("[bold green]✓[/bold green] Connected to Ollama at [cyan]" + Config.OLLAMA_HOST + "[/cyan]")
        except Exception as e:
            self.console.print("[bold red]✗[/bold red] Cannot connect to Ollama: " + str(e))
            self.console.print("[yellow]⚠[/yellow] Make sure Ollama is running and [bold]" + Config.OLLAMA_MODEL + "[/bold] is pulled")
            return 1

        self.console.print()
        cycle = 0

        while True:
            cycle += 1
            try:
                self.run_cycle()
            except Exception as e:
                self.console.print(f"[bold red]Cycle Error:[/bold red] {e}")

            # Sleep message
            self.console.print(f"[dim]⏳ Sleeping for {Config.AGENT_CYCLE_INTERVAL}s...[/dim]")
            time.sleep(Config.AGENT_CYCLE_INTERVAL)
            self.console.print()


# ============================================================================
# ENTRY POINT
# ============================================================================

def main():
    """Main entry point."""
    agent = SilverAgent()
    return agent.run_forever()


if __name__ == "__main__":
    exit(main())
