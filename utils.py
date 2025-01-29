import logging
import re
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse
from config import Config

logger = logging.getLogger(__name__)


def clean_url(url: str) -> Optional[str]:
    """Clean and validate URL"""
    if not url:
        return None

    if not url.startswith(("http://", "https://")):
        url = "http://" + url

    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"
    except:
        return None


def init_db():
    """Initialize database with required tables"""
    conn = sqlite3.connect("submissions.db")
    c = conn.cursor()
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            url TEXT NOT NULL,
            stage INTEGER NOT NULL,
            score INTEGER NOT NULL,
            status TEXT NOT NULL,
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            details TEXT
        )
    """
    )
    conn.commit()
    conn.close()


def check_submission_status(
    url: str, user_id: str, stage: int
) -> Dict[str, Any]:
    """Check if URL was previously submitted successfully"""
    conn = sqlite3.connect("submissions.db")
    c = conn.cursor()

    c.execute(
        """
        SELECT status, score FROM submissions 
        WHERE url = ? AND user_id = ? AND stage = ?
        ORDER BY submitted_at DESC LIMIT 1
    """,
        (url, user_id, stage),
    )

    result = c.fetchone()
    conn.close()

    if result:
        return {
            "previously_submitted": True,
            "status": result[0],
            "score": result[1],
        }
    return {"previously_submitted": False}


def save_submission(
    user_id: str,
    url: str,
    stage: int,
    score: int,
    status: str,
    details: Dict[str, Any],
):
    """Save submission details to database"""
    conn = sqlite3.connect("submissions.db")
    c = conn.cursor()

    c.execute(
        """
        INSERT INTO submissions (user_id, url, stage, score, status, details)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (user_id, url, stage, score, status, str(details)),
    )

    conn.commit()
    conn.close()


def handle_promotion(stage, client, user_id):
    """Handle user promotion to next stage"""
    try:
        # for channel in Config.STAGE_CHANNELS[stage]["current"]:
        #     client.conversations_kick(channel=channel, user=user_id, token=Config.SLACK_USER_TOKEN)

        for channel in Config.STAGE_CHANNELS[stage]["next"]:
            client.conversations_invite(channel=channel, users=user_id)

        client.users_profile_set(
            user=user_id,
            profile={"status_emoji": Config.STAGE_STATUS_EMOJIS[stage + 1]},
            token=Config.SLACK_USER_TOKEN
        )
    except Exception as e:
        logger.error(f"Promotion error: {str(e)}")
        raise
