from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from datetime import datetime
import os

app = Flask(__name__)

# Fixed secret key so sessions survive restarts
app.secret_key = os.environ.get('SECRET_KEY', 'radium-dev-secret-change-in-prod')

# PostgreSQL in production (Neon), fallback to SQLite locally
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///radium.db')
# Neon gives postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
}

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='gevent')
typing_users = set()
online_users = set()  # track online users by username

# ──────────────────────────────────────────
#  Models
# ──────────────────────────────────────────

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='author', lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

# ──────────────────────────────────────────
#  Routes
# ──────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('chat'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and bcrypt.check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('chat'))
        error = 'Invalid username or password.'
    return render_template('auth.html', mode='login', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm', '')

        if len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif len(username) > 30:
            error = 'Username must be at most 30 characters.'
        elif len(password) < 4:
            error = 'Password must be at least 4 characters.'
        elif password != confirm:
            error = 'Passwords do not match.'
        elif User.query.filter_by(username=username).first():
            error = 'Username already taken.'
        else:
            hashed = bcrypt.generate_password_hash(password).decode('utf-8')
            user = User(username=username, password_hash=hashed)
            db.session.add(user)
            db.session.commit()
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect(url_for('chat'))
    return render_template('auth.html', mode='register', error=error)

@app.route('/chat')
def chat():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    # Load last 60 messages
    messages = (Message.query
                .order_by(Message.timestamp.asc())
                .limit(60).all())
    history = [
        {
            'username': m.author.username,
            'content': m.content,
            'timestamp': m.timestamp.strftime('%H:%M'),
            'self': m.user_id == session['user_id']
        }
        for m in messages
    ]
    return render_template('chat.html',
                           username=session['username'],
                           history=history)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/api/online')
def online_count():
    return jsonify({'count': len(online_users)})

# ──────────────────────────────────────────
#  Socket.IO events
# ──────────────────────────────────────────

@socketio.on('connect')
def on_connect():
    if 'user_id' not in session:
        return False
    join_room('global')
    online_users.add(session['username'])
    emit('system', {'msg': f"{session['username']} joined the chat ⚡"}, to='global')
    emit('online_count', {'count': len(online_users)}, to='global')

@socketio.on('disconnect')
def on_disconnect():
    if 'username' in session:
        online_users.discard(session['username'])
        typing_users.discard(session['username'])
        emit('typing_update', list(typing_users), to='global')
        emit('online_count', {'count': len(online_users)}, to='global')
        emit('system', {'msg': f"{session['username']} left the chat"}, to='global')

@socketio.on('typing')
def on_typing(data):
    if 'username' in session:
        typing_users.add(session['username'])
        emit('typing_update', list(typing_users), to='global')

@socketio.on('stopped_typing')
def on_stopped_typing(data):
    if 'username' in session:
        typing_users.discard(session['username'])
        emit('typing_update', list(typing_users), to='global')

@socketio.on('send_message')
def handle_message(data):
    if 'user_id' not in session:
        return
    content = data.get('content', '').strip()
    if not content or len(content) > 1000:
        return
    msg = Message(content=content, user_id=session['user_id'])
    db.session.add(msg)
    db.session.commit()
    emit('new_message', {
        'username': session['username'],
        'content': content,
        'timestamp': msg.timestamp.strftime('%H:%M'),
        'user_id': session['user_id']
    }, to='global')

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🟢  Radium Chat running → http://127.0.0.1:{port}")
    socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
