---
name: whatsapp-reader
description: Read WhatsApp messages directly from the macOS local database (ChatStorage.sqlite). No bridge, no API keys, no second phone number required.
version: 1.0.0
author: Vulti
license: MIT
triggers:
  - "connect whatsapp"
  - "read whatsapp"
  - "whatsapp messages"
  - "check whatsapp"
  - "whatsapp inbox"
  - "what's on whatsapp"
metadata:
  vulti:
    tags: [whatsapp, messaging, chat, inbox, contacts, local, sqlite, macos]
    related_skills: [telephony]
    category: productivity
---

# WhatsApp Reader — Read Local Messages (macOS)

This skill reads WhatsApp messages directly from the macOS WhatsApp desktop app's local SQLite database. No API keys, no bridge process, no second phone number. If WhatsApp is installed on the Mac, you can read messages.

## How it works

WhatsApp for Mac stores its message database at:
```
~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite
```

This is a standard Core Data SQLite database with these key tables:
- `ZWACHATSESSION` — chat threads (contacts and groups)
- `ZWAMESSAGE` — individual messages
- `ZWAMEDIAITEM` — media attachments (images, voice, video)
- `ZWAGROUPINFO` — group metadata
- `ZWAGROUPMEMBER` — group members

The helper script `scripts/whatsapp_reader.py` queries this database read-only. It never writes to it.

## Prerequisites

- **WhatsApp for Mac** must be installed and logged in (App Store version)
- **Full Disk Access** must be granted to the terminal or app running Vulti (System Settings > Privacy & Security > Full Disk Access)
- macOS only — this reads the native macOS WhatsApp database

## What you can do

### List recent chats
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" chats --limit 20
```
Shows recent conversations sorted by last message date, with contact name, unread count, and last message preview.

### Read messages from a chat
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" messages --contact "John" --limit 50
```
Reads messages from a specific contact or group. Matches by partial name (case-insensitive).

### Search messages
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" search --query "meeting tomorrow" --limit 20
```
Full-text search across all messages.

### Get unread messages
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" unread
```
Shows all chats with unread messages and their content.

### Contact info
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" contact --name "John"
```
Shows contact details including phone number (JID) and message count.

## Important notes

- **Read-only** — this skill never modifies the WhatsApp database
- **No sending** — this skill cannot send messages (use the WhatsApp gateway platform for that)
- **Privacy** — treat message content as sensitive. Do not store message content in agent memory unless the user explicitly asks
- **Timestamps** — WhatsApp uses Core Data timestamps (seconds since 2001-01-01). The script converts these automatically
- **Database locking** — the script opens the database in read-only mode (`?mode=ro`) to avoid conflicts with the running WhatsApp app

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "database is locked" | WhatsApp may be writing. Wait a moment and retry |
| "no such file" | WhatsApp for Mac is not installed, or using the Electron version (need App Store version) |
| "permission denied" | Grant Full Disk Access to your terminal app in System Settings |
| No messages found | Check that WhatsApp is logged in and synced on this Mac |

## Workflows

### A — "What's new on WhatsApp?"
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" unread
```
Then summarize the unread messages for the user.

### B — "What did [person] say?"
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" messages --contact "[person]" --limit 20
```
Read and summarize recent messages from that contact.

### C — "Search WhatsApp for [topic]"
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" search --query "[topic]" --limit 30
```
Search across all chats and present relevant results.

### D — "Give me a WhatsApp digest"
```bash
python3 "$SKILL_DIR/scripts/whatsapp_reader.py" chats --limit 30
```
Then for each chat with unread messages, fetch and summarize the content.
