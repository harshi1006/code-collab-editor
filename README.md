# CodeSync — Real-Time Code Collaboration Editor

## Tech Stack
- **Backend**: Flask + Flask-SocketIO (WebSockets)
- **Database**: MySQL
- **Frontend**: HTML, CSS, Bootstrap 5
- **Code Editor**: CodeMirror 5

## Project Structure
```
collab_editor/
├── app.py                  # Main Flask app + SocketIO events
├── requirements.txt
└── templates/
    ├── base.html           # Layout + navbar
    ├── index.html          # Landing page
    ├── login.html          # Login form
    ├── register.html       # Register form
    ├── dashboard.html      # Room management
    └── editor.html         # Live code editor
```

## Features
- User registration & login (password hashing)
- Create/Join rooms via room code
- Real-time code sync (WebSockets)
- Syntax highlighting (10+ languages)
- Live user presence (who's online)
- In-editor chat
- Auto-save every 30 seconds
- Copy room code with one click

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure MySQL
In `app.py`, update DB_CONFIG:
```python
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'YOUR_PASSWORD',   # <-- change this
    'database': 'collab_editor'
}
```

### 3. Run the app
```bash
python app.py
```

### 4. Open browser
```
http://localhost:5000
```

Database tables are created automatically on first run!

## How It Works

```
User A types code
    ↓
CodeMirror 'change' event fires
    ↓
Socket.emit('code_change') sent to server
    ↓
Server broadcasts to all room members
    ↓
User B's CodeMirror updates in real-time
```

## Database Schema

**users** — id, username, email, password (hashed), created_at
**rooms** — id, room_code, room_name, language, owner_id, code_content, timestamps
**room_members** — room_id, user_id (many-to-many join)
