from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, join_room, leave_room, emit
import mysql.connector
import hashlib
import os
import json
import subprocess
import tempfile
import zipfile
import io
import shutil
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# ─── DB CONFIG ───────────────────────────────────────────────
DB_CONFIG = {
    'host':     os.environ.get('MYSQLHOST',     os.environ.get('MYSQL_HOST',     'localhost')),
    'user':     os.environ.get('MYSQLUSER',     os.environ.get('MYSQL_USER',     'root')),
    'password': os.environ.get('MYSQLPASSWORD', os.environ.get('MYSQL_PASSWORD', 'root')),
    'database': os.environ.get('MYSQLDATABASE', os.environ.get('MYSQL_DATABASE', 'collab_editor')),
    'port':     int(os.environ.get('MYSQLPORT', os.environ.get('MYSQL_PORT', 3306))),
}

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ─── INIT DB ─────────────────────────────────────────────────
def init_db():
    # Railway pe seedha existing DB use karo — naya DB mat banao
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50) UNIQUE NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rooms (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room_code VARCHAR(20) UNIQUE NOT NULL,
            room_name VARCHAR(100) NOT NULL,
            language VARCHAR(30) DEFAULT 'python',
            owner_id INT,
            code_content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS room_members (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room_id INT,
            user_id INT,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE KEY unique_member (room_id, user_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS room_files (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room_id INT NOT NULL,
            filename VARCHAR(200) NOT NULL,
            content LONGTEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id),
            UNIQUE KEY unique_file (room_id, filename)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS room_messages (
            id INT AUTO_INCREMENT PRIMARY KEY,
            room_id INT NOT NULL,
            username VARCHAR(50) NOT NULL,
            message TEXT NOT NULL,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (room_id) REFERENCES rooms(id)
        )
    """)

    conn.commit()
    cursor.close()
    conn.close()
    print("DB initialized successfully")

# ─── HELPERS ─────────────────────────────────────────────────
DEFAULT_FILENAMES = {
    'python': 'main.py', 'javascript': 'main.js', 'java': 'Main.java',
    'cpp': 'main.cpp', 'c': 'main.c', 'html': 'index.html',
    'css': 'styles.css', 'sql': 'query.sql', 'go': 'main.go',
    'rust': 'main.rs', 'typescript': 'main.ts'
}

STARTERS = {
    'python':     '# main.py\nprint("Hello, World!")\n',
    'javascript': '// main.js\nconsole.log("Hello, World!");\n',
    'java':       'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, World!");\n    }\n}\n',
    'cpp':        '#include<iostream>\nusing namespace std;\nint main(){\n    cout<<"Hello, World!"<<endl;\n    return 0;\n}\n',
    'c':          '#include<stdio.h>\nint main(){\n    printf("Hello, World!\\n");\n    return 0;\n}\n',
    'html':       '<!DOCTYPE html>\n<html>\n<head><title>My Page</title></head>\n<body>\n  <h1>Hello, World!</h1>\n</body>\n</html>\n',
    'css':        '/* styles.css */\nbody {\n  margin: 0;\n  font-family: sans-serif;\n  background: #f0f0f0;\n}\n',
    'sql':        '-- query.sql\nSELECT "Hello, World!" AS message;\n',
    'go':         'package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("Hello, World!")\n}\n',
    'rust':       'fn main() {\n    println!("Hello, World!");\n}\n',
}

# ─── ROUTES ──────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        email    = request.form['email'].strip()
        password = request.form['password']
        try:
            conn = get_db(); cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, email, password) VALUES (%s,%s,%s)",
                           (username, email, hash_password(password)))
            conn.commit(); cursor.close(); conn.close()
            return redirect(url_for('login'))
        except mysql.connector.IntegrityError:
            return render_template('register.html', error="Username ya email already exists!")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s",
                       (username, hash_password(password)))
        user = cursor.fetchone(); cursor.close(); conn.close()
        if user:
            session['user_id']  = user['id']
            session['username'] = user['username']
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid credentials!")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.*, (SELECT COUNT(*) FROM room_members rm WHERE rm.room_id=r.id) as member_count
        FROM rooms r WHERE r.owner_id=%s ORDER BY r.updated_at DESC
    """, (session['user_id'],))
    my_rooms = cursor.fetchall()
    cursor.execute("""
        SELECT r.*, u.username as owner_name,
               (SELECT COUNT(*) FROM room_members rm WHERE rm.room_id=r.id) as member_count
        FROM rooms r
        JOIN room_members rm ON r.id=rm.room_id
        JOIN users u ON r.owner_id=u.id
        WHERE rm.user_id=%s AND r.owner_id!=%s
        ORDER BY r.updated_at DESC
    """, (session['user_id'], session['user_id']))
    joined_rooms = cursor.fetchall()
    cursor.close(); conn.close()
    return render_template('dashboard.html', my_rooms=my_rooms, joined_rooms=joined_rooms)

@app.route('/create_room', methods=['POST'])
def create_room():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    room_name    = request.form['room_name'].strip()
    language     = request.form.get('language', 'python')
    room_code    = secrets.token_urlsafe(8)
    default_file = DEFAULT_FILENAMES.get(language, 'main.py')
    starter      = STARTERS.get(language, '# Start coding...\n')

    conn = get_db(); cursor = conn.cursor()
    cursor.execute("INSERT INTO rooms (room_code,room_name,language,owner_id,code_content) VALUES (%s,%s,%s,%s,%s)",
                   (room_code, room_name, language, session['user_id'], starter))
    room_id = cursor.lastrowid
    cursor.execute("INSERT INTO room_members (room_id,user_id) VALUES (%s,%s)", (room_id, session['user_id']))
    cursor.execute("INSERT INTO room_files (room_id,filename,content) VALUES (%s,%s,%s)",
                   (room_id, default_file, starter))
    conn.commit(); cursor.close(); conn.close()
    return redirect(url_for('editor', room_code=room_code))

@app.route('/join_room_page', methods=['POST'])
def join_room_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    room_code = request.form['room_code'].strip()
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM rooms WHERE room_code=%s", (room_code,))
    room = cursor.fetchone()
    if room:
        try:
            cursor.execute("INSERT INTO room_members (room_id,user_id) VALUES (%s,%s)",
                           (room['id'], session['user_id']))
            conn.commit()
        except: pass
        cursor.close(); conn.close()
        return redirect(url_for('editor', room_code=room_code))
    cursor.close(); conn.close()
    return redirect(url_for('dashboard'))

@app.route('/editor/<room_code>')
def editor(room_code):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT r.*, u.username as owner_name
        FROM rooms r JOIN users u ON r.owner_id=u.id
        WHERE r.room_code=%s
    """, (room_code,))
    room = cursor.fetchone()
    if not room:
        cursor.close(); conn.close()
        return redirect(url_for('dashboard'))

    cursor.execute("SELECT * FROM room_files WHERE room_id=%s ORDER BY created_at ASC", (room['id'],))
    files = cursor.fetchall()

    if not files:
        fname = DEFAULT_FILENAMES.get(room['language'], 'main.py')
        cursor.execute("INSERT INTO room_files (room_id,filename,content) VALUES (%s,%s,%s)",
                       (room['id'], fname, room['code_content'] or STARTERS.get(room['language'], '')))
        conn.commit()
        cursor.execute("SELECT * FROM room_files WHERE room_id=%s ORDER BY created_at ASC", (room['id'],))
        files = cursor.fetchall()

    for f in files:
        f['created_at'] = str(f['created_at'])
        f['updated_at'] = str(f['updated_at'])

    cursor.execute("""
        SELECT joined_at FROM room_members
        WHERE room_id = %s AND user_id = %s
    """, (room['id'], session['user_id']))
    membership = cursor.fetchone()
    joined_at = membership['joined_at'] if membership else None

    cursor.execute("""
        SELECT username, message, sent_at
        FROM room_messages
        WHERE room_id = %s
        AND (%s IS NULL OR sent_at >= %s)
        ORDER BY sent_at ASC
        LIMIT 50
    """, (room['id'], joined_at, joined_at))
    chat_history = cursor.fetchall()
    for m in chat_history:
        m['sent_at'] = m['sent_at'].strftime('%H:%M')

    cursor.close(); conn.close()
    return render_template('editor.html', room=room, username=session['username'],
                           files=files, chat_history=chat_history)

# ─── FILE APIs ───────────────────────────────────────────────
@app.route('/api/files/<room_code>/create', methods=['POST'])
def create_file_api(room_code):
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json
    filename = data.get('filename', '').strip()
    if not filename:
        return jsonify({'error': 'filename required'}), 400
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM rooms WHERE room_code=%s", (room_code,))
    room = cursor.fetchone()
    try:
        cursor.execute("INSERT INTO room_files (room_id,filename,content) VALUES (%s,%s,%s)",
                       (room['id'], filename, data.get('content', '')))
        conn.commit()
        fid = cursor.lastrowid
        cursor.execute("SELECT * FROM room_files WHERE id=%s", (fid,))
        new_file = cursor.fetchone()
        new_file['created_at'] = str(new_file['created_at'])
        new_file['updated_at'] = str(new_file['updated_at'])
        cursor.close(); conn.close()
        return jsonify({'file': new_file})
    except mysql.connector.IntegrityError:
        cursor.close(); conn.close()
        return jsonify({'error': 'File already exists'}), 409

@app.route('/api/files/<room_code>/save', methods=['POST'])
def save_file_api(room_code):
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM rooms WHERE room_code=%s", (room_code,))
    room = cursor.fetchone()
    cursor.execute("UPDATE room_files SET content=%s WHERE room_id=%s AND filename=%s",
                   (data['content'], room['id'], data['filename']))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({'status': 'saved', 'time': datetime.now().strftime('%H:%M:%S')})

@app.route('/api/files/<room_code>/delete', methods=['POST'])
def delete_file_api(room_code):
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM rooms WHERE room_code=%s", (room_code,))
    room = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) as cnt FROM room_files WHERE room_id=%s", (room['id'],))
    if cursor.fetchone()['cnt'] <= 1:
        cursor.close(); conn.close()
        return jsonify({'error': 'Cannot delete the only file'}), 400
    cursor.execute("DELETE FROM room_files WHERE room_id=%s AND filename=%s",
                   (room['id'], data['filename']))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({'status': 'deleted'})

@app.route('/api/files/<room_code>/rename', methods=['POST'])
def rename_file_api(room_code):
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    data = request.json
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM rooms WHERE room_code=%s", (room_code,))
    room = cursor.fetchone()
    try:
        cursor.execute("UPDATE room_files SET filename=%s WHERE room_id=%s AND filename=%s",
                       (data['new_name'], room['id'], data['old_name']))
        conn.commit(); cursor.close(); conn.close()
        return jsonify({'status': 'renamed'})
    except:
        cursor.close(); conn.close()
        return jsonify({'error': 'File already exists'}), 409

@app.route('/api/files/<room_code>/download_zip')
def download_zip(room_code):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id,room_name FROM rooms WHERE room_code=%s", (room_code,))
    room = cursor.fetchone()
    cursor.execute("SELECT filename,content FROM room_files WHERE room_id=%s", (room['id'],))
    files = cursor.fetchall()
    cursor.close(); conn.close()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            zf.writestr(f['filename'], f['content'] or '')
    buf.seek(0)
    from flask import send_file
    return send_file(buf, mimetype='application/zip', as_attachment=True,
                     download_name=f"{room['room_name']}.zip")

# ─── TERMINAL ────────────────────────────────────────────────
@app.route('/api/terminal', methods=['POST'])
def terminal_run():
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401

    data      = request.json
    command   = data.get('command', '').strip()
    room_code = data.get('room_code', '')

    if not command:
        return jsonify({'output': '', 'error': 'No command provided.', 'exit_code': 1})

    BLOCKED = ['rm -rf /', 'mkfs', 'dd if=', ':(){:|:&}', 'chmod -R 777 /']
    if any(b in command.lower() for b in BLOCKED):
        return jsonify({'output': '', 'error': 'Command blocked for safety.', 'exit_code': 1})

    env = os.environ.copy()
    env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/root/.cargo/bin:/usr/local/go/bin:' + env.get('PATH', '')

    # Write all room files to a temp directory so terminal commands can access them
    work_dir = tempfile.mkdtemp(prefix='terminal_')
    try:
        if room_code:
            conn = get_db(); cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT id FROM rooms WHERE room_code=%s", (room_code,))
            room = cursor.fetchone()
            if room:
                cursor.execute("SELECT filename, content FROM room_files WHERE room_id=%s", (room['id'],))
                files = cursor.fetchall()
                for f in files:
                    fpath = os.path.join(work_dir, f['filename'])
                    os.makedirs(os.path.dirname(fpath), exist_ok=True)
                    with open(fpath, 'w', encoding='utf-8') as fp:
                        fp.write(f['content'] or '')
            cursor.close(); conn.close()

        proc = subprocess.run(
            command, shell=True,
            capture_output=True, text=True,
            timeout=30, env=env,
            cwd=work_dir
        )
        return jsonify({'output': proc.stdout, 'error': proc.stderr, 'exit_code': proc.returncode})

    except subprocess.TimeoutExpired:
        return jsonify({'output': '', 'error': 'Command timed out (30s limit)', 'exit_code': 1})
    except Exception as e:
        return jsonify({'output': '', 'error': str(e), 'exit_code': 1})
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

# ─── CODE EXECUTION ──────────────────────────────────────────
LANG_CONFIG = {
    'python':     {'file_cmd': ['python', '{file}'],    'ext': '.py'},
    'javascript': {'file_cmd': ['node',   '{file}'],    'ext': '.js'},
    'go':         {'file_cmd': ['go', 'run', '{file}'], 'ext': '.go'},
    'bash':       {'file_cmd': ['bash',   '{file}'],    'ext': '.sh'},
    'php':        {'file_cmd': ['php',    '{file}'],    'ext': '.php'},
    'ruby':       {'file_cmd': ['ruby',   '{file}'],    'ext': '.rb'},
    'java': {
        'ext': '.java',
        'compile': ['javac', '{file}'],
        'run':     ['java', '-cp', '{dir}', 'Main']
    },
    'cpp': {
        'ext': '.cpp',
        'compile': ['g++', '{file}', '-o', '{exe}'],
        'run':     ['{exe}']
    },
    'c': {
        'ext': '.c',
        'compile': ['gcc', '{file}', '-o', '{exe}'],
        'run':     ['{exe}']
    },
    'rust': {
        'ext': '.rs',
        'compile': ['rustc', '{file}', '-o', '{exe}'],
        'run':     ['{exe}']
    },
}

@app.route('/api/run', methods=['POST'])
def run_code():
    if 'user_id' not in session:
        return jsonify({'error': 'unauthorized'}), 401
    data     = request.json
    code     = data.get('code', '')
    language = data.get('language', 'python')
    stdin    = data.get('stdin', '')
    cfg = LANG_CONFIG.get(language)
    if not cfg:
        return jsonify({'output': '', 'error': f'"{language}" supported nahi hai.', 'exit_code': 1})
    tmp_dir = tempfile.mkdtemp()
    try:
        ext      = cfg['ext']
        fname    = 'Main' + ext if language == 'java' else 'code' + ext
        filepath = os.path.join(tmp_dir, fname)
        exe_path = os.path.join(tmp_dir, 'code_out')
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(code)
        if 'compile' in cfg:
            compile_cmd = [
                c.replace('{file}', filepath).replace('{exe}', exe_path).replace('{dir}', tmp_dir)
                for c in cfg['compile']
            ]
            comp = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=20)
            if comp.returncode != 0:
                return jsonify({'output': '', 'error': comp.stderr or comp.stdout or 'Compilation failed',
                                'exit_code': comp.returncode})
            run_cmd = [c.replace('{exe}', exe_path).replace('{dir}', tmp_dir) for c in cfg['run']]
        else:
            run_cmd = [c.replace('{file}', filepath) for c in cfg['file_cmd']]
        proc = subprocess.run(run_cmd, input=stdin, capture_output=True, text=True, timeout=10)
        stdout_val = proc.stdout or ''
        stderr_val = proc.stderr or ''
        exit_code  = proc.returncode
        if exit_code == 0 and stderr_val:
            lower = stderr_val.lower()
            if any(kw in lower for kw in [
                'error', 'traceback', 'exception', 'syntaxerror',
                'nameerror', 'typeerror', 'valueerror', 'indexerror', 'keyerror'
            ]):
                exit_code = 1
        return jsonify({'output': stdout_val, 'error': stderr_val, 'exit_code': exit_code})
    except subprocess.TimeoutExpired:
        return jsonify({'output': '', 'error': 'Execution timed out (10s)', 'exit_code': 1})
    except FileNotFoundError as e:
        return jsonify({'output': '', 'error': f'{language} runtime not found.\n{e}', 'exit_code': 1})
    except Exception as e:
        return jsonify({'output': '', 'error': str(e), 'exit_code': 1})
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

# ─── LANG VERSIONS ───────────────────────────────────────────
@app.route('/api/lang_versions')
def lang_versions():
    checks = {
        'python':     ['python',  '--version'],
        'javascript': ['node',    '--version'],
        'java':       ['java',    '--version'],
        'cpp':        ['g++',     '--version'],
        'c':          ['gcc',     '--version'],
        'go':         ['go',      'version'],
        'rust':       ['rustc',   '--version'],
        'php':        ['php',     '--version'],
        'ruby':       ['ruby',    '--version'],
        'bash':       ['bash',    '--version'],
    }
    versions = {}
    for lang, cmd in checks.items():
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            raw  = (proc.stdout + proc.stderr).strip().splitlines()[0]
            versions[lang] = {'installed': True, 'version': raw, 'runtime': 'local'}
        except FileNotFoundError:
            versions[lang] = {'installed': False, 'version': 'not installed', 'runtime': 'none'}
        except Exception:
            versions[lang] = {'installed': False, 'version': 'error', 'runtime': 'none'}
    return jsonify(versions)

# ─── OLD COMPAT ──────────────────────────────────────────────
@app.route('/save_code', methods=['POST'])
def save_code():
    if 'user_id' not in session:
        return jsonify({'status': 'error'})
    data = request.json
    conn = get_db(); cursor = conn.cursor()
    cursor.execute("UPDATE rooms SET code_content=%s WHERE room_code=%s", (data['code'], data['room_code']))
    conn.commit(); cursor.close(); conn.close()
    return jsonify({'status': 'saved', 'time': datetime.now().strftime('%H:%M:%S')})

@app.route('/delete_room/<room_code>', methods=['POST'])
def delete_room(room_code):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db(); cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id FROM rooms WHERE room_code=%s AND owner_id=%s", (room_code, session['user_id']))
    room = cursor.fetchone()
    if room:
        cursor.execute("DELETE FROM room_files WHERE room_id=%s",   (room['id'],))
        cursor.execute("DELETE FROM room_members WHERE room_id=%s", (room['id'],))
        cursor.execute("DELETE FROM rooms WHERE id=%s",             (room['id'],))
        conn.commit()
    cursor.close(); conn.close()
    return redirect(url_for('dashboard'))

# ─── SOCKETIO EVENTS ─────────────────────────────────────────
active_users = {}

@socketio.on('join')
def on_join(data):
    room = data['room_code']; username = data['username']
    join_room(room)
    if room not in active_users:
        active_users[room] = {}

    # Same user pehle se join hai — purana session remove karo
    old_sid = None
    for sid, uname in list(active_users[room].items()):
        if uname == username and sid != request.sid:
            old_sid = sid
            break
    if old_sid:
        del active_users[room][old_sid]

    active_users[room][request.sid] = username
    emit('user_joined', {'username': username, 'users': list(set(active_users[room].values()))}, room=room)

@socketio.on('code_change')
def on_code_change(data):
    room = data['room_code']
    username = data['username']
    # Same user ke doosre devices ko bhi update bhejo lekin unka onChange fire na ho
    # include_self=False se current tab ko nahi bhejta — baaki sab ko bhejta hai
    emit('code_update', {
        'code': data['code'], 'username': username,
        'filename': data.get('filename', ''), 'cursor': data.get('cursor', {})
    }, room=room, include_self=False)

@socketio.on('file_created')
def on_file_created(data):
    emit('file_added', data, room=data['room_code'], include_self=False)

@socketio.on('file_deleted')
def on_file_deleted(data):
    emit('file_removed', data, room=data['room_code'], include_self=False)

@socketio.on('file_renamed')
def on_file_renamed(data):
    emit('file_rename_update', data, room=data['room_code'], include_self=False)

@socketio.on('cursor_move')
def on_cursor_move(data):
    emit('cursor_update', {'username': data['username'], 'line': data['line'], 'ch': data['ch']},
         room=data['room_code'], include_self=False)

@socketio.on('chat_message')
def on_chat(data):
    now = datetime.now()
    try:
        conn = get_db(); cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id FROM rooms WHERE room_code=%s", (data['room_code'],))
        room = cursor.fetchone()
        if room:
            cursor.execute(
                "INSERT INTO room_messages (room_id, username, message) VALUES (%s,%s,%s)",
                (room['id'], data['username'], data['message'])
            )
            conn.commit()
        cursor.close(); conn.close()
    except Exception as e:
        print(f"Chat save error: {e}")
    emit('new_message', {
        'username': data['username'],
        'message':  data['message'],
        'time':     now.strftime('%H:%M')
    }, room=data['room_code'])

@socketio.on('disconnect')
def on_disconnect():
    for room, users in active_users.items():
        if request.sid in users:
            username = users.pop(request.sid)
            # Agar same user ka koi aur session hai toh user_left mat bhejo
            still_present = username in users.values()
            if not still_present:
                emit('user_left', {
                    'username': username,
                    'users': list(set(users.values()))
                }, room=room)
            break

# ─── STARTUP ─────────────────────────────────────────────────
try:
    init_db()
except Exception as e:
    print(f"DB init error: {e}")

if __name__ == '__main__':
    port  = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') != 'production'
    socketio.run(app, host='0.0.0.0', port=port, debug=debug, allow_unsafe_werkzeug=True)
