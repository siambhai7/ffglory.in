from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import os
import sqlite3
from datetime import datetime
from functools import wraps
import urllib.parse
import json
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'glorybot-super-secret-key-2025')

# ===== REGION MAPPING =====
REGION_MAP = {
    'bangladesh': 'bd', 'pakistan': 'pk', 'india': 'ind',
    'middle east': 'me', 'brazil': 'br', 'singapore': 'sg',
    'bd': 'bd', 'pk': 'pk', 'ind': 'ind', 'in': 'ind',
    'me': 'me', 'br': 'br', 'sg': 'sg',
}

REGION_DISPLAY = {
    'bd': '🇧🇩 Bangladesh', 'pk': '🇵🇰 Pakistan', 'ind': '🇮🇳 India',
    'me': '🇸🇦 Middle East', 'br': '🇧🇷 Brazil', 'sg': '🇸🇬 Singapore',
}

def normalize_region(region):
    if not region: return region
    key = region.strip().lower()
    return REGION_MAP.get(key, region.strip().lower())

def get_region_display(region_code):
    if not region_code: return '—'
    key = region_code.strip().lower()
    return REGION_DISPLAY.get(key, region_code)

# ===== DATABASE SETUP =====
# Support both Render (/tmp) and Termux (local directory) environments
# Termux doesn't have /tmp writable, so we detect and use the app directory instead
def _resolve_db_path():
    env_path = os.environ.get('DATABASE_PATH')
    if env_path:
        return env_path
    # Try /tmp first (works on Render/cloud)
    try:
        os.makedirs('/tmp', exist_ok=True)
        test_file = os.path.join('/tmp', '.glorybot_test')
        with open(test_file, 'w') as f:
            f.write('test')
        os.remove(test_file)
        return os.path.join('/tmp', 'glorybot.db')
    except (OSError, PermissionError):
        pass
    # Fallback: use the directory where app.py lives (works on Termux)
    app_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(app_dir, 'glorybot.db')

DB_PATH = _resolve_db_path()

# ===== CONFIG.JSON FILE SETUP =====
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

# QR photo path inside the project
QR_PHOTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images')
os.makedirs(QR_PHOTO_DIR, exist_ok=True)

def _load_config():
    """Load settings from config.json file."""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def _save_config(config_data):
    """Save settings to config.json file."""
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config_data, f, indent=2, ensure_ascii=False)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_setting(key, default=''):
    """Get setting from config.json first, then fall back to DB, then default."""
    # Priority 1: config.json file
    config = _load_config()
    if key in config and config[key]:
        return str(config[key])
    # Priority 2: SQLite DB
    conn = get_db()
    try:
        row = conn.execute('SELECT value FROM settings WHERE key = ?', (key,)).fetchone()
        if row and row['value']:
            return row['value']
    finally:
        conn.close()
    return default

def set_setting(key, value):
    """Save setting to both SQLite DB and config.json file."""
    # Save to SQLite
    conn = get_db()
    try:
        conn.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
        conn.commit()
    finally:
        conn.close()
    # Save to config.json
    config = _load_config()
    config[key] = value
    _save_config(config)

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        banned INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        last_login TEXT
    )''')

    # Add banned column if missing
    try:
        cols = [row[1] for row in cursor.execute('PRAGMA table_info(users)').fetchall()]
        if 'banned' not in cols:
            cursor.execute('ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0')
    except Exception:
        pass

    # Remove credits column if exists
    try:
        cols = [row[1] for row in cursor.execute('PRAGMA table_info(users)').fetchall()]
        if 'credits' in cols:
            cursor.execute('''CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                banned INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_login TEXT
            )''')
            cursor.execute('''INSERT INTO users_new (id, username, email, password_hash, created_at, last_login)
                SELECT id, username, email, password_hash, created_at, last_login FROM users''')
            cursor.execute('DROP TABLE users')
            cursor.execute('ALTER TABLE users_new RENAME TO users')
    except Exception:
        pass

    cursor.execute('''CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        clan_id TEXT NOT NULL,
        region TEXT NOT NULL,
        glory_earned INTEGER DEFAULT 0,
        status TEXT DEFAULT 'active',
        started_at TEXT NOT NULL,
        completed_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        clan_id TEXT NOT NULL,
        region TEXT NOT NULL,
        clan_name TEXT DEFAULT '',
        transaction_id TEXT NOT NULL,
        amount INTEGER DEFAULT 650,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')

    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )''')

    # Default settings
    defaults = [
        ('payment_video_url', 'https://youtu.be/PKbari5YGMs?si=wZ-UGtyZa5NYHo2c'),
        ('price', '650'),
        ('guild_api_url', 'https://guild-info-oa3v.onrender.com/info2'),
        ('admin_password', 'admin2025'),
        ('till_id', '995865874'),
        ('qr_image_url', ''),
        ('allowed_regions', 'me,ind,bd,pk,br,sg'),
        ('guild_info_enabled', 'on'),
    ]
    for key, val in defaults:
        cursor.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, val))

    conn.commit()
    conn.close()

init_db()

# ===== AUTH HELPERS =====
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please login to access this page.', 'warning')
            return redirect(url_for('login'))
        # Check if user is banned
        conn = get_db()
        user = conn.execute('SELECT banned FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        conn.close()
        if user and user['banned']:
            return redirect(url_for('banned_page'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('Admin login required.', 'error')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user():
    if 'user_id' in session:
        conn = get_db()
        try:
            user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
            return user
        finally:
            conn.close()
    return None

# ===== ROUTES =====

@app.route('/')
def index():
    user = get_current_user()
    return render_template('index.html', title='GloryBot', user=user)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Please fill in all fields.', 'error')
            return render_template('login.html', title='Login')
        conn = get_db()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            if user['banned']:
                conn.close()
                session['user_id'] = user['id']
                session['username'] = user['username']
                return redirect(url_for('banned_page'))
            session['user_id'] = user['id']
            session['username'] = user['username']
            conn.execute('UPDATE users SET last_login = ? WHERE id = ?', (datetime.now().isoformat(), user['id']))
            conn.commit()
            conn.close()
            flash(f'Welcome back, {user["username"]}!', 'success')
            return redirect(url_for('client'))
        else:
            conn.close()
            flash('Invalid username or password.', 'error')
            return render_template('login.html', title='Login')
    return render_template('login.html', title='Login')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not username or not email or not password or not confirm_password:
            flash('Please fill in all fields.', 'error')
            return render_template('register.html', title='Register')
        if len(username) < 3:
            flash('Username must be at least 3 characters.', 'error')
            return render_template('register.html', title='Register')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'error')
            return render_template('register.html', title='Register')
        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html', title='Register')
        conn = get_db()
        existing = conn.execute('SELECT id FROM users WHERE username = ?', (username,)).fetchone()
        if existing:
            conn.close()
            flash('Username already taken.', 'error')
            return render_template('register.html', title='Register')
        existing = conn.execute('SELECT id FROM users WHERE email = ?', (email,)).fetchone()
        if existing:
            conn.close()
            flash('Email already registered.', 'error')
            return render_template('register.html', title='Register')
        password_hash = generate_password_hash(password)
        conn.execute('INSERT INTO users (username, email, password_hash, created_at) VALUES (?, ?, ?, ?)',
                     (username, email, password_hash, datetime.now().isoformat()))
        conn.commit()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        session['user_id'] = user['id']
        session['username'] = user['username']
        flash(f'Account created! Welcome, {username}!', 'success')
        return redirect(url_for('client'))
    return render_template('register.html', title='Register')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/banned')
def banned_page():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    if not user:
        session.clear()
        return redirect(url_for('login'))
    if not user['banned']:
        return redirect(url_for('client'))
    return render_template('banned.html', title='Account Banned', user=user)

@app.route('/client')
@login_required
def client():
    user = get_current_user()
    conn = get_db()
    orders = conn.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 5', (user['id'],)).fetchall()
    conn.close()
    # Get allowed regions from settings
    allowed_regions_str = get_setting('allowed_regions', 'me,ind,bd,pk,br,sg')
    allowed_regions_list = [r.strip() for r in allowed_regions_str.split(',') if r.strip()] if allowed_regions_str else []
    guild_info_enabled = get_setting('guild_info_enabled', 'on')
    return render_template('client.html', title='Dashboard', user=user, orders=[dict(o) for o in orders],
                          region_display=get_region_display, all_regions=REGION_DISPLAY,
                          allowed_regions=allowed_regions_list,
                          guild_info_enabled=guild_info_enabled)

@app.route('/result')
@login_required
def result():
    user = get_current_user()
    payment_video_url = get_setting('payment_video_url', 'https://youtu.be/PKbari5YGMs?si=wZ-UGtyZa5NYHo2c')
    price = get_setting('price', '650')
    return render_template('result.html', title='Clan Info', user=user, region_display=get_region_display, payment_video_url=payment_video_url, price=price)

@app.route('/payment')
@login_required
def payment():
    user = get_current_user()
    clan_id = request.args.get('clan_id', '')
    region = request.args.get('region', '')
    clan_name = request.args.get('clan_name', '')
    region_display_name = get_region_display(region)
    price = get_setting('price', '650')
    till_id = get_setting('till_id', '995865874')
    qr_image_url = get_setting('qr_image_url', '')
    return render_template('payment.html', title='Payment', user=user,
                          clan_id=clan_id, region=region, clan_name=clan_name,
                          region_display_name=region_display_name, price=price,
                          till_id=till_id, qr_image_url=qr_image_url)

@app.route('/submit-order', methods=['POST'])
@login_required
def submit_order():
    user = get_current_user()
    transaction_id = request.form.get('transaction_id', '').strip()
    clan_id = request.form.get('clan_id', '').strip()
    region = request.form.get('region', '').strip()
    clan_name = request.form.get('clan_name', '').strip()
    if not transaction_id:
        flash('Please enter your Transaction ID.', 'error')
        return redirect(url_for('payment', clan_id=clan_id, region=region, clan_name=clan_name))
    if len(transaction_id) < 3:
        flash('Transaction ID must be at least 3 characters.', 'error')
        return redirect(url_for('payment', clan_id=clan_id, region=region, clan_name=clan_name))
    region = normalize_region(region)
    price = int(get_setting('price', '650'))
    conn = get_db()
    conn.execute('INSERT INTO orders (user_id, clan_id, region, clan_name, transaction_id, amount, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                 (user['id'], clan_id, region, clan_name, transaction_id, price, 'pending', datetime.now().isoformat()))
    conn.commit()
    order = conn.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT 1', (user['id'],)).fetchone()
    conn.close()
    session['last_order_id'] = order['id']
    flash('Order submitted successfully!', 'success')
    return redirect(url_for('thankyou'))

@app.route('/thankyou')
@login_required
def thankyou():
    user = get_current_user()
    order_id = session.get('last_order_id')
    order = None
    if order_id:
        conn = get_db()
        order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
        conn.close()
    return render_template('thankyou.html', title='Thank You', user=user, order=order, region_display=get_region_display)

@app.route('/order-status')
@login_required
def order_status():
    user = get_current_user()
    conn = get_db()
    orders = conn.execute('SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC', (user['id'],)).fetchall()
    conn.close()
    return render_template('order_status.html', title='Order Status', user=user, orders=orders, region_display=get_region_display)

# ===== ADMIN PANEL =====

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        admin_password = get_setting('admin_password', 'admin2025')
        if password == admin_password:
            session['admin_logged_in'] = True
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin password.', 'error')
    return render_template('admin_login.html', title='Admin Login')

@app.route('/admin/forcelogin')
def admin_forcelogin():
    """Force login to admin panel without password."""
    session['admin_logged_in'] = True
    flash('Admin force login successful!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Admin logged out.', 'info')
    return redirect(url_for('admin_login'))

@app.route('/admin')
@admin_required
def admin_dashboard():
    conn = get_db()
    stats = {
        'total_users': conn.execute('SELECT COUNT(*) as c FROM users').fetchone()['c'],
        'banned_users': conn.execute('SELECT COUNT(*) as c FROM users WHERE banned = 1').fetchone()['c'],
        'total_orders': conn.execute('SELECT COUNT(*) as c FROM orders').fetchone()['c'],
        'pending_orders': conn.execute("SELECT COUNT(*) as c FROM orders WHERE status='pending'").fetchone()['c'],
        'confirmed_orders': conn.execute("SELECT COUNT(*) as c FROM orders WHERE status='confirmed'").fetchone()['c'],
        'cancelled_orders': conn.execute("SELECT COUNT(*) as c FROM orders WHERE status='cancelled'").fetchone()['c'],
    }
    orders = conn.execute('''SELECT o.*, u.username FROM orders o JOIN users u ON o.user_id = u.id ORDER BY o.created_at DESC''').fetchall()
    users = conn.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    settings = {}
    for row in conn.execute('SELECT key, value FROM settings').fetchall():
        settings[row['key']] = row['value']
    conn.close()
    # Parse allowed regions
    allowed_regions_str = settings.get('allowed_regions', 'me,ind,bd,pk,br,sg')
    allowed_regions_list = [r.strip() for r in allowed_regions_str.split(',') if r.strip()] if allowed_regions_str else []

    return render_template('admin_dashboard.html', title='Admin Panel', stats=stats,
                          orders=orders, users=[dict(u) for u in users],
                          settings=settings, region_display=get_region_display,
                          all_regions=REGION_DISPLAY, allowed_regions=allowed_regions_list)

@app.route('/admin/order/<int:order_id>/<action>')
@admin_required
def admin_order_action(order_id, action):
    if action not in ('confirmed', 'cancelled'):
        flash('Invalid action.', 'error')
        return redirect(url_for('admin_dashboard'))
    conn = get_db()
    order = conn.execute('SELECT * FROM orders WHERE id = ?', (order_id,)).fetchone()
    if not order:
        conn.close()
        flash('Order not found.', 'error')
        return redirect(url_for('admin_dashboard'))
    conn.execute('UPDATE orders SET status = ?, updated_at = ? WHERE id = ?', (action, datetime.now().isoformat(), order_id))
    conn.commit()
    conn.close()
    flash(f'Order #{order_id} has been {action}!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/ban/<int:user_id>')
@admin_required
def admin_ban_user(user_id):
    conn = get_db()
    conn.execute('UPDATE users SET banned = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash(f'User #{user_id} has been banned.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/unban/<int:user_id>')
@admin_required
def admin_unban_user(user_id):
    conn = get_db()
    conn.execute('UPDATE users SET banned = 0 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    flash(f'User #{user_id} has been unbanned.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/settings', methods=['POST'])
@admin_required
def admin_update_settings():
    price = request.form.get('price', '').strip()
    admin_password = request.form.get('admin_password', '').strip()
    payment_video_url = request.form.get('payment_video_url', '').strip()
    guild_api_url = request.form.get('guild_api_url', '').strip()
    till_id = request.form.get('till_id', '').strip()
    qr_image_url = request.form.get('qr_image_url', '').strip()
    allowed_regions = request.form.getlist('allowed_regions')
    guild_info_enabled = request.form.get('guild_info_enabled', 'off')

    # Handle QR photo file upload
    qr_file = request.files.get('qr_photo_file')
    if qr_file and qr_file.filename:
        # Save uploaded QR photo to static/images/
        import secrets
        ext = os.path.splitext(qr_file.filename)[1].lower()
        if ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp'):
            filename = f'qr_uploaded_{secrets.token_hex(4)}{ext}'
            save_path = os.path.join(QR_PHOTO_DIR, filename)
            qr_file.save(save_path)
            qr_image_url = f'/static/images/{filename}'

    if price:
        set_setting('price', price)
    if admin_password and len(admin_password) >= 6:
        set_setting('admin_password', admin_password)
    if payment_video_url:
        set_setting('payment_video_url', payment_video_url)
    if guild_api_url:
        set_setting('guild_api_url', guild_api_url)
    if till_id:
        set_setting('till_id', till_id)
    set_setting('qr_image_url', qr_image_url)
    set_setting('allowed_regions', ','.join(allowed_regions) if allowed_regions else '')
    set_setting('guild_info_enabled', guild_info_enabled)

    flash('Settings updated successfully! (config.json synced)', 'success')
    return redirect(url_for('admin_dashboard'))

# ===== API ROUTES =====

@app.route('/api/clan-info', methods=['POST'])
@login_required
def clan_info():
    user = get_current_user()
    data = request.get_json()
    clan_id = data.get('clan_id', '').strip()
    region = data.get('region', '').strip()
    if not clan_id or not region:
        return jsonify({'success': False, 'message': 'Clan ID and Region are required'}), 400
    region_code = normalize_region(region)

    # Check if guild info check is enabled
    guild_info_enabled = get_setting('guild_info_enabled', 'on')
    if guild_info_enabled != 'on':
        # Skip API call, return minimal data to proceed to payment directly
        return jsonify({'success': True, 'data': {
            'status': 'success',
            'clan_id': clan_id,
            'clan_name': '',
            'region': region_code,
            'level': '—',
            'xp': 0,
            'welcome_message': '',
            'guild_info_skipped': True
        }})

    try:
        guild_api_url = get_setting('guild_api_url', 'https://guild-info-oa3v.onrender.com/info2')
        encoded_clan_id = urllib.parse.quote(str(clan_id), safe='')
        api_url = f'{guild_api_url}?clan_id={encoded_clan_id}&region={region_code}'
        try:
            resp = requests.get(api_url, headers={'User-Agent': 'GloryBot/1.0'}, timeout=30, allow_redirects=True)
            api_data = resp.json()
        except requests.exceptions.SSError:
            # Retry without SSL verification for Vercel/Render edge cases
            resp = requests.get(api_url, headers={'User-Agent': 'GloryBot/1.0'}, timeout=30, allow_redirects=True, verify=False)
            api_data = resp.json()
        except requests.exceptions.JSONDecodeError:
            return jsonify({'success': False, 'message': 'API returned invalid response. Please check the API URL.'}), 500

        if api_data.get('status') == 'success':
            conn = get_db()
            conn.execute('INSERT INTO sessions (user_id, clan_id, region, glory_earned, status, started_at) VALUES (?, ?, ?, ?, ?, ?)',
                         (user['id'], str(api_data.get('clan_id', clan_id)), region_code, api_data.get('xp', 0), 'active', datetime.now().isoformat()))
            conn.commit()
            conn.close()
            api_data['region'] = region_code
        return jsonify({'success': True, 'data': api_data})
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'message': 'Connection error — API server is unreachable. Please try again later.'}), 500
    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'message': 'API request timed out. Please try again.'}), 500
    except requests.exceptions.HTTPError as e:
        return jsonify({'success': False, 'message': f'API returned error: {e.response.status_code}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'}), 500

@app.route('/api/sessions', methods=['GET'])
@login_required
def get_sessions():
    user = get_current_user()
    conn = get_db()
    sessions = conn.execute('SELECT * FROM sessions WHERE user_id = ? ORDER BY started_at DESC', (user['id'],)).fetchall()
    conn.close()
    return jsonify({'success': True, 'sessions': [dict(s) for s in sessions]})

@app.route('/api/stats', methods=['GET'])
@login_required
def get_stats():
    user = get_current_user()
    conn = get_db()
    active_bots = conn.execute("SELECT COUNT(*) as count FROM sessions WHERE user_id = ? AND status = 'active'", (user['id'],)).fetchone()['count']
    total_glory = conn.execute('SELECT COALESCE(SUM(glory_earned), 0) as total FROM sessions WHERE user_id = ?', (user['id'],)).fetchone()['total']
    sessions_count = conn.execute('SELECT COUNT(*) as count FROM sessions WHERE user_id = ?', (user['id'],)).fetchone()['count']
    conn.close()
    return jsonify({'success': True, 'stats': {'total_glory': total_glory, 'active_bots': active_bots, 'sessions_run': sessions_count}})

@app.context_processor
def inject_user():
    return dict(current_user=get_current_user(), region_display=get_region_display)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('index.html', title='404 - Not Found'), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({'success': False, 'message': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5555))
    app.run(host='0.0.0.0', port=port, debug=False)
