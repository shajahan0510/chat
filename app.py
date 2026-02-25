import streamlit as st
import sqlite3
import bcrypt
from datetime import datetime
import time

# --- Database Configuration ---
DB_NAME = "messaging_app.db"

def init_db():
    """Initialize the database tables."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Users Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Message Requests Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS message_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            status TEXT DEFAULT 'pending',
            FOREIGN KEY(sender_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        )
    ''')
    
    # Messages Table
    c.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            receiver_id INTEGER,
            message_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(sender_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        )
    ''')
    
    conn.commit()
    conn.close()

# --- Authentication Functions ---

def hash_password(password):
    """Hash a password for storing."""
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password, hashed_password):
    """Verify a stored password against one provided by user"""
    pwd_bytes = plain_password.encode('utf-8')
    hash_bytes = hashed_password.encode('utf-8')
    return bcrypt.checkpw(pwd_bytes, hash_bytes)

def register_user(username, password):
    """Register a new user."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        hashed_pw = hash_password(password)
        c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", 
                  (username, hashed_pw))
        conn.commit()
        return True, "Registration successful! Please login."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        conn.close()

def login_user(username, password):
    """Login a user."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, password_hash FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    
    if result:
        user_id, stored_hash = result
        if verify_password(password, stored_hash):
            return True, user_id
    return False, None

# --- Messaging Functions ---

def get_user_id(username):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def send_request(sender_id, receiver_username):
    receiver_id = get_user_id(receiver_username)
    if not receiver_id:
        return False, "User not found."
    if sender_id == receiver_id:
        return False, "You cannot send a request to yourself."
    
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Check if request already exists or they are already connected
    c.execute('''
        SELECT status FROM message_requests 
        WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
    ''', (sender_id, receiver_id, receiver_id, sender_id))
    existing = c.fetchone()
    
    if existing:
        if existing[0] == 'accepted':
            return False, "You are already connected with this user."
        return False, "A pending request already exists or was declined."
    
    c.execute("INSERT INTO message_requests (sender_id, receiver_id, status) VALUES (?, ?, 'pending')",
              (sender_id, receiver_id))
    conn.commit()
    conn.close()
    return True, "Request sent!"

def get_pending_requests(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT u.username, mr.id 
        FROM message_requests mr
        JOIN users u ON mr.sender_id = u.id
        WHERE mr.receiver_id = ? AND mr.status = 'pending'
    ''', (user_id,))
    requests = c.fetchall()
    conn.close()
    return requests

def get_sent_requests(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT u.username, mr.status 
        FROM message_requests mr
        JOIN users u ON mr.receiver_id = u.id
        WHERE mr.sender_id = ?
    ''', (user_id,))
    requests = c.fetchall()
    conn.close()
    return requests

def accept_request(request_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Ensure the request belongs to the current user
    c.execute("UPDATE message_requests SET status='accepted' WHERE id=? AND receiver_id=?", 
              (request_id, user_id))
    conn.commit()
    conn.close()

def decline_request(request_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("UPDATE message_requests SET status='declined' WHERE id=? AND receiver_id=?", 
              (request_id, user_id))
    conn.commit()
    conn.close()

def get_accepted_chats(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Find chats where user is sender or receiver and status is accepted
    c.execute('''
        SELECT u.id, u.username 
        FROM message_requests mr
        JOIN users u ON (u.id = mr.sender_id OR u.id = mr.receiver_id)
        WHERE (mr.sender_id = ? OR mr.receiver_id = ?) 
        AND mr.status = 'accepted'
        AND u.id != ?
    ''', (user_id, user_id, user_id))
    chats = c.fetchall()
    conn.close()
    return chats

def get_last_message(user_id, partner_id):
    """Get the last message between two users."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT sender_id, message_text, timestamp 
        FROM messages 
        WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
        ORDER BY timestamp DESC
        LIMIT 1
    ''', (user_id, partner_id, partner_id, user_id))
    result = c.fetchone()
    conn.close()
    return result

def get_unread_count(user_id, partner_id):
    """Count unread messages from partner (simplified - all messages are unread for demo)."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT COUNT(*) 
        FROM messages 
        WHERE sender_id = ? AND receiver_id = ?
    ''', (partner_id, user_id))
    count = c.fetchone()[0]
    conn.close()
    return count

def send_message(sender_id, receiver_id, text):
    if not text.strip():
        return
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO messages (sender_id, receiver_id, message_text, timestamp)
        VALUES (?, ?, ?, ?)
    ''', (sender_id, receiver_id, text, datetime.now()))
    conn.commit()
    conn.close()

def get_messages(user_id, partner_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Security check: Ensure users have an accepted request
    c.execute('''
        SELECT id FROM message_requests 
        WHERE ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?))
        AND status='accepted'
    ''', (user_id, partner_id, partner_id, user_id))
    
    if not c.fetchone():
        conn.close()
        return [] # No permission

    c.execute('''
        SELECT sender_id, message_text, timestamp 
        FROM messages 
        WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)
        ORDER BY timestamp ASC
    ''', (user_id, partner_id, partner_id, user_id))
    
    messages = c.fetchall()
    conn.close()
    return messages

# --- Enhanced UI Components ---

def css_style():
    st.markdown("""
    <style>
    /* Main App Styling */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    /* Hide Streamlit default elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Chat Container */
    .chat-container {
        height: 450px;
        overflow-y: auto;
        border: none;
        border-radius: 20px;
        padding: 20px;
        background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%);
        display: flex;
        flex-direction: column;
        box-shadow: inset 0 2px 10px rgba(0,0,0,0.05);
    }
    
    /* Message Bubbles */
    .message-bubble {
        padding: 12px 18px;
        border-radius: 20px;
        margin-bottom: 12px;
        max-width: 75%;
        word-wrap: break-word;
        font-size: 15px;
        line-height: 1.4;
        animation: fadeIn 0.3s ease;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    .sender {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        align-self: flex-end;
        text-align: right;
        border-bottom-right-radius: 6px;
        box-shadow: 0 3px 10px rgba(102, 126, 234, 0.3);
    }
    
    .receiver {
        background: #ffffff;
        color: #333;
        align-self: flex-start;
        text-align: left;
        border: 1px solid #e8e8e8;
        border-bottom-left-radius: 6px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    
    .meta {
        font-size: 0.7em;
        color: rgba(255,255,255,0.8);
        display: block;
        margin-top: 4px;
    }
    
    .receiver .meta {
        color: #999;
    }
    
    /* ========== IMPROVED CHAT LIST DESIGN ========== */
    
    /* Chat List Container */
    .chat-list-container {
        background: white;
        border-radius: 20px;
        padding: 0;
        box-shadow: 0 10px 40px rgba(0,0,0,0.15);
        overflow: hidden;
    }
    
    /* Chat List Header */
    .chat-list-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 25px 30px;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    .chat-list-header h2 {
        margin: 0;
        font-size: 24px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    
    .chat-count {
        background: rgba(255,255,255,0.2);
        padding: 5px 12px;
        border-radius: 20px;
        font-size: 14px;
    }
    
    /* Individual Chat Item */
    .chat-item {
        display: flex;
        align-items: center;
        padding: 18px 25px;
        border-bottom: 1px solid #f0f0f0;
        cursor: pointer;
        transition: all 0.2s ease;
        position: relative;
        overflow: hidden;
    }
    
    .chat-item:hover {
        background: linear-gradient(90deg, #f8f9ff 0%, #fff 100%);
        transform: translateX(5px);
    }
    
    .chat-item:last-child {
        border-bottom: none;
    }
    
    /* Avatar */
    .chat-avatar {
        width: 55px;
        height: 55px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 22px;
        font-weight: 600;
        color: white;
        margin-right: 18px;
        flex-shrink: 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        position: relative;
    }
    
    .avatar-online::after {
        content: '';
        position: absolute;
        bottom: 2px;
        right: 2px;
        width: 14px;
        height: 14px;
        background: #25d366;
        border: 3px solid white;
        border-radius: 50%;
    }
    
    /* Chat Info Section */
    .chat-info {
        flex: 1;
        min-width: 0;
    }
    
    .chat-name {
        font-size: 17px;
        font-weight: 600;
        color: #222;
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .verified-badge {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-size: 10px;
        padding: 2px 6px;
        border-radius: 10px;
    }
    
    .chat-preview {
        font-size: 14px;
        color: #888;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 250px;
    }
    
    .chat-preview-you {
        color: #667eea;
        font-weight: 500;
    }
    
    /* Chat Meta Section */
    .chat-meta {
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 6px;
        margin-left: 15px;
    }
    
    .chat-time {
        font-size: 12px;
        color: #aaa;
        font-weight: 500;
    }
    
    .unread-badge {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-size: 12px;
        font-weight: 600;
        padding: 4px 10px;
        border-radius: 15px;
        min-width: 24px;
        text-align: center;
        box-shadow: 0 3px 10px rgba(102, 126, 234, 0.4);
    }
    
    /* Empty State */
    .empty-state {
        text-align: center;
        padding: 60px 30px;
        color: #888;
    }
    
    .empty-icon {
        font-size: 80px;
        margin-bottom: 20px;
        opacity: 0.5;
    }
    
    .empty-title {
        font-size: 20px;
        font-weight: 600;
        color: #555;
        margin-bottom: 10px;
    }
    
    .empty-description {
        font-size: 15px;
        line-height: 1.6;
    }
    
    /* Inbox Card Styling */
    .inbox-card {
        background: white;
        border-radius: 16px;
        padding: 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        display: flex;
        align-items: center;
        justify-content: space-between;
        transition: all 0.2s ease;
        border-left: 4px solid #667eea;
    }
    
    .inbox-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.12);
    }
    
    .request-avatar {
        width: 50px;
        height: 50px;
        border-radius: 50%;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 20px;
        color: white;
        font-weight: 600;
        margin-right: 15px;
    }
    
    .request-info {
        flex: 1;
    }
    
    .request-name {
        font-weight: 600;
        font-size: 16px;
        color: #333;
    }
    
    .request-subtitle {
        font-size: 13px;
        color: #888;
        margin-top: 3px;
    }
    
    /* Action Buttons */
    .action-buttons {
        display: flex;
        gap: 10px;
    }
    
    .btn-accept {
        background: linear-gradient(135deg, #25d366 0%, #128c7e 100%);
        color: white;
        border: none;
        padding: 10px 20px;
        border-radius: 25px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 4px 12px rgba(37, 211, 102, 0.3);
    }
    
    .btn-accept:hover {
        transform: scale(1.05);
        box-shadow: 0 6px 18px rgba(37, 211, 102, 0.4);
    }
    
    .btn-decline {
        background: #f5f5f5;
        color: #666;
        border: none;
        padding: 10px 20px;
        border-radius: 25px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
    }
    
    .btn-decline:hover {
        background: #eee;
        color: #333;
    }
    
    /* Search User Card */
    .user-search-card {
        background: white;
        border-radius: 16px;
        padding: 18px 20px;
        margin-bottom: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        display: flex;
        align-items: center;
        justify-content: space-between;
        transition: all 0.2s ease;
    }
    
    .user-search-card:hover {
        transform: translateX(5px);
        box-shadow: 0 6px 20px rgba(0,0,0,0.12);
    }
    
    /* Status Badge */
    .status-badge {
        padding: 5px 12px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        text-transform: uppercase;
    }
    
    .status-pending {
        background: #fff3cd;
        color: #856404;
    }
    
    .status-accepted {
        background: #d4edda;
        color: #155724;
    }
    
    .status-declined {
        background: #f8d7da;
        color: #721c24;
    }
    
    /* Sent Request Card */
    .sent-request-card {
        background: white;
        border-radius: 12px;
        padding: 15px 20px;
        margin-bottom: 10px;
        box-shadow: 0 3px 10px rgba(0,0,0,0.06);
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    
    /* Input Styling */
    .stTextInput > div > div > input {
        border-radius: 15px !important;
        border: 2px solid #e0e0e0 !important;
        padding: 12px 18px !important;
        font-size: 15px !important;
        transition: all 0.2s ease !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
    }
    
    /* Button Styling */
    .stButton > button {
        border-radius: 15px !important;
        padding: 12px 25px !important;
        font-weight: 600 !important;
        transition: all 0.2s ease !important;
    }
    
    .primary-btn > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        border: none !important;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
    }
    
    .primary-btn > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4) !important;
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%) !important;
    }
    
    section[data-testid="stSidebar"] > div > div {
        padding-top: 2rem;
    }
    
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
        color: white !important;
    }
    
    section[data-testid="stSidebar"] .stRadio > label {
        color: white !important;
    }
    
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h1,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2,
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

def show_login():
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h1 style="font-size: 3rem; margin-bottom: 0.5rem;">🔐</h1>
        <h1 style="font-size: 2rem; color: white;">Welcome Back</h1>
        <p style="color: rgba(255,255,255,0.8);">Sign in to continue to your messages</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Username", placeholder="Enter your username")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        
        st.markdown("<div class='primary-btn'>", unsafe_allow_html=True)
        if st.button("Login", use_container_width=True):
            success, result = login_user(username, password)
            if success:
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.session_state['user_id'] = result
                st.rerun()
            else:
                st.error("Invalid username or password")
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div style='text-align: center; margin-top: 1rem;'>", unsafe_allow_html=True)
        if st.button("Don't have an account? Register"):
            st.session_state['page'] = 'Register'
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

def show_register():
    st.markdown("""
    <div style="text-align: center; padding: 2rem;">
        <h1 style="font-size: 3rem; margin-bottom: 0.5rem;">📝</h1>
        <h1 style="font-size: 2rem; color: white;">Create Account</h1>
        <p style="color: rgba(255,255,255,0.8);">Join and start connecting with others</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        username = st.text_input("Choose a Username", placeholder="Pick a unique username")
        password = st.text_input("Choose a Password", type="password", placeholder="Create a strong password")
        
        st.markdown("<div class='primary-btn'>", unsafe_allow_html=True)
        if st.button("Create Account", use_container_width=True):
            if username and password:
                success, msg = register_user(username, password)
                if success:
                    st.success(msg)
                    st.session_state['page'] = 'Login'
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.warning("Please fill all fields")
        st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<div style='text-align: center; margin-top: 1rem;'>", unsafe_allow_html=True)
        if st.button("Already have an account? Login"):
            st.session_state['page'] = 'Login'
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

def show_inbox():
    st.markdown("""
    <div class="chat-list-header" style="border-radius: 20px 20px 0 0; margin-bottom: 0;">
        <h2>📥 Message Requests</h2>
        <span class="chat-count">Inbox</span>
    </div>
    """, unsafe_allow_html=True)
    
    requests = get_pending_requests(st.session_state['user_id'])
    
    st.markdown("<div class='chat-list-container'>", unsafe_allow_html=True)
    
    if not requests:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">📭</div>
            <div class="empty-title">No New Requests</div>
            <div class="empty-description">When someone wants to chat with you,<br>their request will appear here.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for sender_name, req_id in requests:
            initial = sender_name[0].upper() if sender_name else "?"
            st.markdown(f'''
            <div class="inbox-card">
                <div style="display: flex; align-items: center;">
                    <div class="request-avatar">{initial}</div>
                    <div class="request-info">
                        <div class="request-name">{sender_name}</div>
                        <div class="request-subtitle">wants to start a conversation</div>
                    </div>
                </div>
            </div>
            ''', unsafe_allow_html=True)
            
            col1, col2, col3 = st.columns([3, 1, 1])
            with col2:
                if st.button("✓ Accept", key=f"acc_{req_id}"):
                    accept_request(req_id, st.session_state['user_id'])
                    st.success(f"Accepted request from {sender_name}")
                    st.rerun()
            with col3:
                if st.button("✗ Decline", key=f"dec_{req_id}"):
                    decline_request(req_id, st.session_state['user_id'])
                    st.warning(f"Declined request from {sender_name}")
                    st.rerun()
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div style='margin-top: 2rem;'>", unsafe_allow_html=True)
    st.markdown("""
    <div class="chat-list-header" style="border-radius: 20px 20px 0 0;">
        <h2>📤 Sent Requests</h2>
        <span class="chat-count">Outbox</span>
    </div>
    """, unsafe_allow_html=True)
    
    sent = get_sent_requests(st.session_state['user_id'])
    st.markdown("<div class='chat-list-container'>", unsafe_allow_html=True)
    
    if sent:
        for name, status in sent:
            initial = name[0].upper() if name else "?"
            status_class = f"status-{status}"
            st.markdown(f'''
            <div class="sent-request-card">
                <div style="display: flex; align-items: center;">
                    <div class="request-avatar" style="width: 40px; height: 40px; font-size: 16px;">{initial}</div>
                    <div style="margin-left: 12px;">
                        <div style="font-weight: 600; color: #333;">{name}</div>
                    </div>
                </div>
                <span class="status-badge {status_class}">{status}</span>
            </div>
            ''', unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-state" style="padding: 30px;">
            <div class="empty-title">No Sent Requests</div>
            <div class="empty-description">Search for users to start new conversations!</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

def show_new_request():
    st.markdown("""
    <div class="chat-list-header" style="border-radius: 20px 20px 0 0; margin-bottom: 0;">
        <h2>🔍 Find Users</h2>
        <span class="chat-count">Search</span>
    </div>
    """, unsafe_allow_html=True)
    
    if 'search_results' not in st.session_state:
        st.session_state['search_results'] = []

    col1, col2 = st.columns([4, 1])
    with col1:
        search = st.text_input("Search username", placeholder="Type to search...")
    with col2:
        st.markdown("<div style='padding-top: 1.6rem;'>", unsafe_allow_html=True)
        if st.button("🔍 Search"):
            if search:
                conn = sqlite3.connect(DB_NAME)
                c = conn.cursor()
                c.execute("SELECT username FROM users WHERE username LIKE ? AND username != ?", 
                          (f"%{search}%", st.session_state['username']))
                st.session_state['search_results'] = c.fetchall()
                conn.close()
            else:
                st.session_state['search_results'] = []
        st.markdown("</div>", unsafe_allow_html=True)
    
    results = st.session_state['search_results']
    
    st.markdown("<div class='chat-list-container'>", unsafe_allow_html=True)
    
    if results:
        for user_tuple in results:
            found_user = user_tuple[0]
            initial = found_user[0].upper() if found_user else "?"
            
            st.markdown(f'''
            <div class="user-search-card">
                <div style="display: flex; align-items: center;">
                    <div class="chat-avatar" style="width: 45px; height: 45px; font-size: 18px;">
                        {initial}
                    </div>
                    <div style="margin-left: 15px;">
                        <div style="font-weight: 600; font-size: 16px; color: #333;">{found_user}</div>
                        <div style="font-size: 13px; color: #888;">Tap to send request</div>
                    </div>
                </div>
            </div>
            ''', unsafe_allow_html=True)
            
            if st.button("Send Request", key=f"add_{found_user}", use_container_width=True):
                success, msg = send_request(st.session_state['user_id'], found_user)
                if success:
                    st.success(f"Request sent to {found_user}!")
                    st.session_state['search_results'].remove(user_tuple)
                    st.rerun()
                else:
                    st.error(msg)
    elif search and not results:
        st.markdown("""
        <div class="empty-state" style="padding: 40px;">
            <div class="empty-icon">🔍</div>
            <div class="empty-title">No Users Found</div>
            <div class="empty-description">Try searching with a different username</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="empty-state" style="padding: 40px;">
            <div class="empty-icon">👥</div>
            <div class="empty-title">Find New Friends</div>
            <div class="empty-description">Search by username to find and connect with others</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

def show_chat_list():
    st.markdown("""
    <div class="chat-list-header">
        <h2>💬 Messages</h2>
    </div>
    """, unsafe_allow_html=True)
    
    chats = get_accepted_chats(st.session_state['user_id'])
    
    st.markdown("<div class='chat-list-container'>", unsafe_allow_html=True)
    
    if not chats:
        st.markdown("""
        <div class="empty-state">
            <div class="empty-icon">💬</div>
            <div class="empty-title">No Conversations Yet</div>
            <div class="empty-description">
                Start by searching for users and sending chat requests.<br>
                Your active conversations will appear here.
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for partner_id, partner_name in chats:
            # Get last message
            last_msg = get_last_message(st.session_state['user_id'], partner_id)
            unread = get_unread_count(st.session_state['user_id'], partner_id)
            
            initial = partner_name[0].upper() if partner_name else "?"
            
            # Generate random gradient colors for avatar
            import hashlib
            hash_val = int(hashlib.md5(partner_name.encode()).hexdigest(), 16)
            colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe', '#43e97b', '#38f9d7', '#fa709a', '#fee140']
            color1 = colors[hash_val % len(colors)]
            color2 = colors[(hash_val + 1) % len(colors)]
            
            # Format last message preview
            if last_msg:
                sender_id, msg_text, timestamp = last_msg
                preview = msg_text[:35] + "..." if len(msg_text) > 35 else msg_text
                if sender_id == st.session_state['user_id']:
                    preview = f"You: {preview}"
                
                # Format time
                try:
                    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
                except:
                    dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
                
                now = datetime.now()
                if dt.date() == now.date():
                    time_str = dt.strftime("%I:%M %p")
                elif (now - dt).days == 1:
                    time_str = "Yesterday"
                elif (now - dt).days < 7:
                    time_str = dt.strftime("%A")[:3]
                else:
                    time_str = dt.strftime("%m/%d")
            else:
                preview = "Start a conversation..."
                time_str = ""
            
            st.markdown(f'''
            <div class="chat-item" onclick="document.getElementById('chat_btn_{partner_id}').click()">
                <div class="chat-avatar avatar-online" style="background: linear-gradient(135deg, {color1} 0%, {color2} 100%);">
                    {initial}
                </div>
                <div class="chat-info">
                    <div class="chat-name">
                        {partner_name}
                    </div>
                    <div class="chat-preview">{preview}</div>
                </div>
                <div class="chat-meta">
                    <div class="chat-time">{time_str}</div>
                    {f'<div class="unread-badge">{unread}</div>' if unread > 0 else ''}
                </div>
            </div>
            ''', unsafe_allow_html=True)
            
            # Hidden button that gets triggered by clicking the chat item
            st.markdown(f"<div style='display:none;'>", unsafe_allow_html=True)
            if st.button("Open", key=f"chat_{partner_id}", id=f"chat_btn_{partner_id}"):
                st.session_state['current_chat_partner'] = partner_id
                st.session_state['current_chat_partner_name'] = partner_name
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

def show_chat_window():
    partner_id = st.session_state.get('current_chat_partner')
    partner_name = st.session_state.get('current_chat_partner_name')
    user_id = st.session_state['user_id']
    
    if not partner_id:
        st.warning("Select a chat to start messaging.")
        return

    # Header
    import hashlib
    hash_val = int(hashlib.md5(partner_name.encode()).hexdigest(), 16)
    colors = ['#667eea', '#764ba2', '#f093fb', '#f5576c', '#4facfe', '#00f2fe', '#43e97b', '#38f9d7', '#fa709a', '#fee140']
    color1 = colors[hash_val % len(colors)]
    color2 = colors[(hash_val + 1) % len(colors)]
    initial = partner_name[0].upper() if partner_name else "?"
    
    st.markdown(f'''
    <div style="display: flex; align-items: center; padding: 15px 20px; background: white; border-radius: 20px; margin-bottom: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
        <div class="chat-avatar" style="background: linear-gradient(135deg, {color1} 0%, {color2} 100%); width: 45px; height: 45px; font-size: 18px; margin-right: 15px;">
            {initial}
        </div>
        <div>
            <div style="font-weight: 600; font-size: 18px; color: #333;">{partner_name}</div>
            <div style="font-size: 13px; color: #25d366;">● Online</div>
        </div>
    </div>
    ''', unsafe_allow_html=True)
    
    if st.button("⬅️ Back to Chats"):
        del st.session_state['current_chat_partner']
        del st.session_state['current_chat_partner_name']
        st.rerun()

    # Messages
    messages = get_messages(user_id, partner_id)
    
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    
    if not messages:
        st.markdown("""
        <div style="text-align: center; padding: 60px 20px; color: #888;">
            <div style="font-size: 50px; margin-bottom: 15px;">👋</div>
            <div style="font-size: 18px; font-weight: 600; color: #555;">Say Hello!</div>
            <div style="font-size: 14px; margin-top: 5px;">Start your conversation</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        for sender_id, text, timestamp in messages:
            try:
                dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S.%f")
            except:
                dt = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            time_str = dt.strftime("%I:%M %p")
            
            if sender_id == user_id:
                st.markdown(f'''
                    <div class="message-bubble sender">
                        <span>{text}</span>
                        <span class="meta">{time_str} ✓✓</span>
                    </div>
                ''', unsafe_allow_html=True)
            else:
                st.markdown(f'''
                    <div class="message-bubble receiver">
                        <span>{text}</span>
                        <span class="meta">{time_str}</span>
                    </div>
                ''', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

    # Input
    st.markdown("<div style='margin-top: 15px;'>", unsafe_allow_html=True)
    col1, col2 = st.columns([5, 1])
    
    with col1:
        new_msg = st.text_input("Type a message...", key="msg_input", placeholder="Type your message...")
    
    with col2:
        st.markdown("<div style='padding-top: 1.6rem;'>", unsafe_allow_html=True)
        if st.button("📤", use_container_width=True):
            if new_msg:
                send_message(user_id, partner_id, new_msg)
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

# --- Main Application Logic ---

def main():
    init_db()
    css_style()
    
    # Session State Initialization
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['page'] = 'Login'
    
    # Sidebar Navigation
    if st.session_state['logged_in']:
        # Sidebar header with user info
        st.sidebar.markdown(f"""
        <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 20px; margin-bottom: 20px;">
            <div style="width: 70px; height: 70px; background: rgba(255,255,255,0.2); border-radius: 50%; margin: 0 auto 15px; display: flex; align-items: center; justify-content: center; font-size: 30px;">
                {st.session_state['username'][0].upper()}
            </div>
            <div style="color: white; font-size: 18px; font-weight: 600;">{st.session_state['username']}</div>
            <div style="color: rgba(255,255,255,0.7); font-size: 13px; margin-top: 5px;">● Online</div>
        </div>
        """, unsafe_allow_html=True)
        
        menu = ["Chat List", "Inbox", "New Chat", "Logout"]
        choice = st.sidebar.radio("", menu, label_visibility="collapsed")
        
        if choice == "Logout":
            st.session_state.clear()
            st.rerun()
        elif choice == "Inbox":
            show_inbox()
        elif choice == "New Chat":
            show_new_request()
        elif choice == "Chat List":
            if 'current_chat_partner' in st.session_state:
                show_chat_window()
            else:
                show_chat_list()
    else:
        # Not Logged In Flow
        if st.session_state.get('page') == 'Register':
            show_register()
        else:
            show_login()

if __name__ == "__main__":
    main()

