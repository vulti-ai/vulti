#!/usr/bin/env python3
"""WhatsApp local database reader for macOS.

Reads messages directly from the WhatsApp for Mac ChatStorage.sqlite database.
Read-only — never modifies the database.

Usage:
    python3 whatsapp_reader.py chats [--limit N]
    python3 whatsapp_reader.py messages --contact NAME [--limit N] [--since YYYY-MM-DD]
    python3 whatsapp_reader.py search --query TEXT [--limit N]
    python3 whatsapp_reader.py unread
    python3 whatsapp_reader.py contact --name NAME
"""

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Core Data epoch: 2001-01-01 00:00:00 UTC
CORE_DATA_EPOCH = 978307200

DB_PATH = os.path.expanduser(
    "~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite"
)


def get_db():
    """Open the WhatsApp database in read-only mode."""
    if not os.path.exists(DB_PATH):
        print(json.dumps({"error": "WhatsApp database not found. Is WhatsApp for Mac installed?"}))
        sys.exit(1)

    try:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        print(json.dumps({"error": f"Cannot open database: {e}. Check Full Disk Access permissions."}))
        sys.exit(1)


def ts_to_iso(core_data_ts):
    """Convert Core Data timestamp to ISO 8601 string."""
    if core_data_ts is None:
        return None
    try:
        unix_ts = core_data_ts + CORE_DATA_EPOCH
        return datetime.fromtimestamp(unix_ts, tz=timezone.utc).isoformat()
    except (OSError, ValueError, OverflowError):
        return None


def jid_to_phone(jid):
    """Extract phone number from WhatsApp JID (e.g. '61432390205@s.whatsapp.net' -> '+61432390205')."""
    if not jid:
        return None
    num = jid.split("@")[0]
    if num.isdigit():
        return f"+{num}"
    return jid


def cmd_chats(args):
    """List recent chats."""
    db = get_db()
    cur = db.execute("""
        SELECT
            cs.Z_PK,
            cs.ZPARTNERNAME,
            cs.ZCONTACTJID,
            cs.ZUNREADCOUNT,
            cs.ZLASTMESSAGETEXT,
            cs.ZLASTMESSAGEDATE,
            cs.ZSESSIONTYPE
        FROM ZWACHATSESSION cs
        WHERE cs.ZREMOVED = 0
          AND cs.ZCONTACTJID IS NOT NULL
          AND cs.ZCONTACTJID != '0@status'
          AND cs.ZLASTMESSAGEDATE IS NOT NULL
        ORDER BY cs.ZLASTMESSAGEDATE DESC
        LIMIT ?
    """, (args.limit,))

    chats = []
    for row in cur:
        chats.append({
            "id": row["Z_PK"],
            "name": row["ZPARTNERNAME"] or jid_to_phone(row["ZCONTACTJID"]),
            "jid": row["ZCONTACTJID"],
            "unread": row["ZUNREADCOUNT"] or 0,
            "last_message": row["ZLASTMESSAGETEXT"],
            "last_message_at": ts_to_iso(row["ZLASTMESSAGEDATE"]),
            "type": "group" if row["ZSESSIONTYPE"] == 1 else "dm",
        })
    db.close()
    print(json.dumps({"chats": chats, "count": len(chats)}, ensure_ascii=False, indent=2))


def cmd_messages(args):
    """Read messages from a specific contact or group."""
    db = get_db()

    # Find the chat session by partial name match
    cur = db.execute("""
        SELECT Z_PK, ZPARTNERNAME, ZCONTACTJID
        FROM ZWACHATSESSION
        WHERE ZREMOVED = 0
          AND (ZPARTNERNAME LIKE ? OR ZCONTACTJID LIKE ?)
        ORDER BY ZLASTMESSAGEDATE DESC
        LIMIT 1
    """, (f"%{args.contact}%", f"%{args.contact}%"))

    session = cur.fetchone()
    if not session:
        print(json.dumps({"error": f"No chat found matching '{args.contact}'"}))
        db.close()
        return

    query = """
        SELECT
            m.ZTEXT,
            m.ZISFROMME,
            m.ZMESSAGEDATE,
            m.ZMESSAGETYPE,
            m.ZPUSHNAME,
            m.ZFROMJID,
            m.ZTOJID
        FROM ZWAMESSAGE m
        WHERE m.ZCHATSESSION = ?
    """
    params = [session["Z_PK"]]

    if args.since:
        try:
            since_dt = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            since_core = since_dt.timestamp() - CORE_DATA_EPOCH
            query += " AND m.ZMESSAGEDATE >= ?"
            params.append(since_core)
        except ValueError:
            pass

    query += " ORDER BY m.ZMESSAGEDATE DESC LIMIT ?"
    params.append(args.limit)

    cur = db.execute(query, params)

    messages = []
    for row in cur:
        msg = {
            "text": row["ZTEXT"],
            "from_me": bool(row["ZISFROMME"]),
            "timestamp": ts_to_iso(row["ZMESSAGEDATE"]),
            "type": _message_type(row["ZMESSAGETYPE"]),
        }
        if row["ZPUSHNAME"]:
            msg["sender"] = row["ZPUSHNAME"]
        messages.append(msg)

    # Reverse so oldest first
    messages.reverse()

    db.close()
    print(json.dumps({
        "chat": session["ZPARTNERNAME"] or jid_to_phone(session["ZCONTACTJID"]),
        "jid": session["ZCONTACTJID"],
        "messages": messages,
        "count": len(messages),
    }, ensure_ascii=False, indent=2))


def cmd_search(args):
    """Search messages across all chats."""
    db = get_db()
    cur = db.execute("""
        SELECT
            m.ZTEXT,
            m.ZISFROMME,
            m.ZMESSAGEDATE,
            m.ZPUSHNAME,
            cs.ZPARTNERNAME,
            cs.ZCONTACTJID
        FROM ZWAMESSAGE m
        JOIN ZWACHATSESSION cs ON m.ZCHATSESSION = cs.Z_PK
        WHERE m.ZTEXT LIKE ?
          AND cs.ZREMOVED = 0
        ORDER BY m.ZMESSAGEDATE DESC
        LIMIT ?
    """, (f"%{args.query}%", args.limit))

    results = []
    for row in cur:
        results.append({
            "text": row["ZTEXT"],
            "from_me": bool(row["ZISFROMME"]),
            "timestamp": ts_to_iso(row["ZMESSAGEDATE"]),
            "chat": row["ZPARTNERNAME"] or jid_to_phone(row["ZCONTACTJID"]),
            "sender": row["ZPUSHNAME"] if not row["ZISFROMME"] else "me",
        })

    db.close()
    print(json.dumps({
        "query": args.query,
        "results": results,
        "count": len(results),
    }, ensure_ascii=False, indent=2))


def cmd_unread(args):
    """Show all chats with unread messages."""
    db = get_db()
    cur = db.execute("""
        SELECT
            cs.Z_PK,
            cs.ZPARTNERNAME,
            cs.ZCONTACTJID,
            cs.ZUNREADCOUNT,
            cs.ZLASTMESSAGETEXT,
            cs.ZLASTMESSAGEDATE
        FROM ZWACHATSESSION cs
        WHERE cs.ZREMOVED = 0
          AND cs.ZUNREADCOUNT > 0
          AND cs.ZCONTACTJID != '0@status'
        ORDER BY cs.ZLASTMESSAGEDATE DESC
    """)

    chats = []
    for row in cur:
        # Fetch the unread messages
        msg_cur = db.execute("""
            SELECT ZTEXT, ZISFROMME, ZMESSAGEDATE, ZPUSHNAME
            FROM ZWAMESSAGE
            WHERE ZCHATSESSION = ?
            ORDER BY ZMESSAGEDATE DESC
            LIMIT ?
        """, (row["Z_PK"], row["ZUNREADCOUNT"]))

        messages = []
        for m in msg_cur:
            messages.append({
                "text": m["ZTEXT"],
                "from_me": bool(m["ZISFROMME"]),
                "timestamp": ts_to_iso(m["ZMESSAGEDATE"]),
                "sender": m["ZPUSHNAME"],
            })
        messages.reverse()

        chats.append({
            "name": row["ZPARTNERNAME"] or jid_to_phone(row["ZCONTACTJID"]),
            "jid": row["ZCONTACTJID"],
            "unread": row["ZUNREADCOUNT"],
            "messages": messages,
        })

    db.close()
    print(json.dumps({
        "unread_chats": chats,
        "total_unread": sum(c["unread"] for c in chats),
    }, ensure_ascii=False, indent=2))


def cmd_contact(args):
    """Show contact details."""
    db = get_db()
    cur = db.execute("""
        SELECT
            cs.Z_PK,
            cs.ZPARTNERNAME,
            cs.ZCONTACTJID,
            cs.ZUNREADCOUNT,
            cs.ZMESSAGECOUNTER,
            cs.ZLASTMESSAGEDATE,
            cs.ZSESSIONTYPE
        FROM ZWACHATSESSION cs
        WHERE cs.ZREMOVED = 0
          AND (cs.ZPARTNERNAME LIKE ? OR cs.ZCONTACTJID LIKE ?)
        ORDER BY cs.ZLASTMESSAGEDATE DESC
        LIMIT 5
    """, (f"%{args.name}%", f"%{args.name}%"))

    contacts = []
    for row in cur:
        contacts.append({
            "name": row["ZPARTNERNAME"],
            "phone": jid_to_phone(row["ZCONTACTJID"]),
            "jid": row["ZCONTACTJID"],
            "total_messages": row["ZMESSAGECOUNTER"] or 0,
            "unread": row["ZUNREADCOUNT"] or 0,
            "last_message_at": ts_to_iso(row["ZLASTMESSAGEDATE"]),
            "type": "group" if row["ZSESSIONTYPE"] == 1 else "dm",
        })

    db.close()
    print(json.dumps({"contacts": contacts, "count": len(contacts)}, ensure_ascii=False, indent=2))


def _message_type(type_int):
    """Map WhatsApp message type integer to human-readable string."""
    types = {
        0: "text",
        1: "image",
        2: "video",
        3: "voice",
        4: "contact",
        5: "location",
        6: "system",
        7: "link",
        8: "document",
        10: "missed_call",
        11: "gif",
        14: "deleted",
        15: "sticker",
    }
    return types.get(type_int, f"type_{type_int}")


def main():
    parser = argparse.ArgumentParser(description="WhatsApp local database reader")
    sub = parser.add_subparsers(dest="command")

    # chats
    p = sub.add_parser("chats", help="List recent chats")
    p.add_argument("--limit", type=int, default=20)

    # messages
    p = sub.add_parser("messages", help="Read messages from a contact")
    p.add_argument("--contact", required=True, help="Contact name (partial match)")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--since", help="Only messages since date (YYYY-MM-DD)")

    # search
    p = sub.add_parser("search", help="Search messages across all chats")
    p.add_argument("--query", required=True, help="Search text")
    p.add_argument("--limit", type=int, default=20)

    # unread
    sub.add_parser("unread", help="Show unread messages")

    # contact
    p = sub.add_parser("contact", help="Show contact details")
    p.add_argument("--name", required=True, help="Contact name (partial match)")

    args = parser.parse_args()

    if args.command == "chats":
        cmd_chats(args)
    elif args.command == "messages":
        cmd_messages(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "unread":
        cmd_unread(args)
    elif args.command == "contact":
        cmd_contact(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
