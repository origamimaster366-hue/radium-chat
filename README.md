# ⚡ Radium Chat

A real-time group chat app built with Python (Flask + SocketIO).

## Features
- User registration & login (hashed passwords)
- Real-time group messaging via WebSockets
- Typing indicators
- Online user count
- Message history (last 60 messages)
- Slick dark UI

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the server
python app.py
```

Then open **http://127.0.0.1:5000** in your browser.

## Deploy (free)

**Render.com:**
1. Push this folder to GitHub
2. Create a new "Web Service" on Render
3. Build command: `pip install -r requirements.txt`
4. Start command: `python app.py`
5. Done — your chat is live!

## Stack
- **Backend:** Flask, Flask-SocketIO, SQLAlchemy, Bcrypt
- **Database:** SQLite (swap to PostgreSQL for production)
- **Frontend:** Vanilla HTML/CSS/JS + Socket.IO client
