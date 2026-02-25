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

# --- UI Components ---

def css_style():
    st.markdown("""
    <style>
    .chat-container {
        height: 400px;
        overflow-y: auto;
        border: 1px solid #e6e6e6;
        border-radius: 10px;
        padding: 10px;
        background-color: #f9f9f9;
        display: flex;
        flex-direction: column;
    }
    .message-bubble {
        padding: 8px 15px;
        border-radius: 15px;
        margin-bottom: 10px;
        max-width: 70%;
        word-wrap: break-word;
    }
    .sender {
        background-color: #dcf8c6;
        align-self: flex-end;
        text-align: right;
    }
    .receiver {
        background-color: #ffffff;
        align-self: flex-start;
        text-align: left;
        border: 1px solid #ddd;
    }
    .meta {
        font-size: 0.7em;
        color: #999;
        display: block;
        margin-top: 2px;
    }
    </style>
    """, unsafe_allow_html=True)

def show_login():
    st.title("🔐 Login")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Login"):
            success, result = login_user(username, password)
            if success:
                st.session_state['logged_in'] = True
                st.session_state['username'] = username
                st.session_state['user_id'] = result
                st.rerun()
            else:
                st.error("Invalid username or password")
    
    with col2:
        if st.button("Go to Register"):
            st.session_state['page'] = 'Register'
            st.rerun()

def show_register():
    st.title("📝 Register")
    username = st.text_input("Choose a Username")
    password = st.text_input("Choose a Password", type="password")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Create Account"):
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
                
    with col2:
        if st.button("Back to Login"):
            st.session_state['page'] = 'Login'
            st.rerun()

def show_inbox():
    st.subheader("📥 Pending Requests")
    requests = get_pending_requests(st.session_state['user_id'])
    
    if not requests:
        st.info("No new requests.")
    else:
        for sender_name, req_id in requests:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"**{sender_name}** wants to chat.")
            with col2:
                if st.button("Accept", key=f"acc_{req_id}"):
                    accept_request(req_id, st.session_state['user_id'])
                    st.success(f"Accepted request from {sender_name}")
                    st.rerun()
            with col3:
                if st.button("Decline", key=f"dec_{req_id}"):
                    decline_request(req_id, st.session_state['user_id'])
                    st.warning(f"Declined request from {sender_name}")
                    st.rerun()
    
    st.divider()
    st.subheader("📤 Sent Requests")
    sent = get_sent_requests(st.session_state['user_id'])
    if sent:
        for name, status in sent:
            st.write(f"To: **{name}** - Status: _{status}_")
    else:
        st.write("No sent requests yet.")

def show_new_request():
    st.subheader("🔍 Find User")
    search = st.text_input("Enter username to search")
    if st.button("Search"):
        # Simple search logic
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE username LIKE ? AND username != ?", 
                  (f"%{search}%", st.session_state['username']))
        users = c.fetchall()
        conn.close()
        
        if users:
            for u in users:
                col1, col2 = st.columns([3, 1])
                col1.write(u[0])
                if col2.button("Add", key=f"add_{u[0]}"):
                    success, msg = send_request(st.session_state['user_id'], u[0])
                    if success:
                        st.success(msg)
                    else:
                        st.error(msg)
        else:
            st.warning("User not found.")

def show_chat_list():
    st.subheader("💬 Chats")
    chats = get_accepted_chats(st.session_state['user_id'])
    
    if not chats:
        st.info("No active chats. Send a request to start chatting!")
        return

    for partner_id, partner_name in chats:
        if st.button(f"Chat with {partner_name}", key=f"chat_{partner_id}"):
            st.session_state['current_chat_partner'] = partner_id
            st.session_state['current_chat_partner_name'] = partner_name
            st.rerun()

def show_chat_window():
    partner_id = st.session_state.get('current_chat_partner')
    partner_name = st.session_state.get('current_chat_partner_name')
    user_id = st.session_state['user_id']
    
    if not partner_id:
        st.warning("Select a chat to start messaging.")
        return

    st.markdown(f"### Chat with {partner_name}")
    if st.button("⬅️ Back to Chat List"):
        del st.session_state['current_chat_partner']
        del st.session_state['current_chat_partner_name']
        st.rerun()

    # Message Container
    messages = get_messages(user_id, partner_id)
    
    st.markdown('<div class="chat-container">', unsafe_allow_html=True)
    for sender_id, text, timestamp in messages:
        if sender_id == user_id:
            st.markdown(f'''
                <div class="message-bubble sender">
                    <span>{text}</span>
                    <span class="meta">{timestamp}</span>
                </div>
            ''', unsafe_allow_html=True)
        else:
            st.markdown(f'''
                <div class="message-bubble receiver">
                    <span>{text}</span>
                    <span class="meta">{timestamp}</span>
                </div>
            ''', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Input Area
    new_msg = st.text_input("Type a message...", key="msg_input")
    col1, col2 = st.columns([4, 1])
    
    with col1:
        if st.button("Send", use_container_width=True):
            if new_msg:
                send_message(user_id, partner_id, new_msg)
                st.rerun() # Refresh to show new message

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
        st.sidebar.title(f"👤 {st.session_state['username']}")
        menu = ["Inbox", "New Chat", "Chat List", "Logout"]
        choice = st.sidebar.radio("Navigation", menu)
        
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