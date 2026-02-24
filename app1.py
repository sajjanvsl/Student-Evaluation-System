import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import hashlib
import random
import string
import os
import base64
import time
import re
import numpy as np

# Try to import sklearn, but provide fallback if not available
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    # Define dummy classes/functions if needed
    class TfidfVectorizer:
        def fit_transform(self, texts):
            return np.zeros((len(texts), 1))
    def cosine_similarity(a, b):
        return np.zeros((a.shape[0], b.shape[0]))

st.set_page_config(page_title="Student Evaluation System", page_icon="📚", layout="wide", initial_sidebar_state="expanded")

# ---------- Session State ----------
if 'current_student' not in st.session_state:
    st.session_state.current_student = None
if 'current_teacher' not in st.session_state:
    st.session_state.current_teacher = None
if 'user_role' not in st.session_state:
    st.session_state.user_role = None
if 'reset_email' not in st.session_state:
    st.session_state.reset_email = None
if 'temp_password' not in st.session_state:
    st.session_state.temp_password = None
if 'view_file' not in st.session_state:
    st.session_state.view_file = None
if 'submission_review' not in st.session_state:
    st.session_state.submission_review = None
if 'page' not in st.session_state:
    st.session_state.page = "Welcome"

# ---------- Database Helper (prevents locks) ----------
def get_db_connection():
    """Return a database connection with busy timeout and thread safety."""
    conn = sqlite3.connect('student_evaluation.db', timeout=10, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 5000")  # 5 seconds
    return conn

# ---------- Database Initialisation ----------
def init_database():
    """Create tables if they don't exist, add missing columns if needed."""
    conn = get_db_connection()
    c = conn.cursor()

    # Submissions table with AI columns
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='submissions'")
    table_exists = c.fetchone()
    if table_exists:
        c.execute("PRAGMA table_info(submissions)")
        columns = [column[1] for column in c.fetchall()]
        if 'auto_graded' not in columns:
            c.execute('ALTER TABLE submissions ADD COLUMN auto_graded INTEGER DEFAULT 0')
        if 'file_name' not in columns:
            c.execute('ALTER TABLE submissions ADD COLUMN file_name TEXT')
        if 'file_type' not in columns:
            c.execute('ALTER TABLE submissions ADD COLUMN file_type TEXT')
        if 'file_size' not in columns:
            c.execute('ALTER TABLE submissions ADD COLUMN file_size INTEGER')
        if 'ai_confidence' not in columns:
            c.execute('ALTER TABLE submissions ADD COLUMN ai_confidence DECIMAL(3,2) DEFAULT 0')
        if 'ai_feedback' not in columns:
            c.execute('ALTER TABLE submissions ADD COLUMN ai_feedback TEXT')
        if 'plagiarism_score' not in columns:
            c.execute('ALTER TABLE submissions ADD COLUMN plagiarism_score DECIMAL(3,2) DEFAULT 0')
    else:
        c.execute('''
            CREATE TABLE submissions (
                submission_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                submission_type TEXT NOT NULL,
                subject TEXT,
                title TEXT,
                description TEXT,
                date DATE NOT NULL,
                status TEXT DEFAULT 'Submitted',
                teacher_feedback TEXT,
                grade TEXT,
                points_earned INTEGER DEFAULT 0,
                max_points INTEGER DEFAULT 50,
                file_path TEXT,
                file_name TEXT,
                file_type TEXT,
                file_size INTEGER,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                graded_at TIMESTAMP,
                graded_by INTEGER,
                auto_graded INTEGER DEFAULT 0,
                ai_confidence DECIMAL(3,2) DEFAULT 0,
                ai_feedback TEXT,
                plagiarism_score DECIMAL(3,2) DEFAULT 0
            )
        ''')

    # Students table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='students'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE students (
                student_id INTEGER PRIMARY KEY AUTOINCREMENT,
                reg_no TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                class TEXT NOT NULL,
                email TEXT UNIQUE,
                phone TEXT,
                password TEXT,
                total_points INTEGER DEFAULT 0,
                current_streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active DATE
            )
        ''')
    else:
        c.execute("PRAGMA table_info(students)")
        columns = [column[1] for column in c.fetchall()]
        if 'password' not in columns:
            c.execute('ALTER TABLE students ADD COLUMN password TEXT')
        if 'email' not in columns:
            c.execute('ALTER TABLE students ADD COLUMN email TEXT')

    # Teachers table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='teachers'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE teachers (
                teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT,
                department TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    else:
        c.execute("PRAGMA table_info(teachers)")
        columns = [column[1] for column in c.fetchall()]
        if 'password' not in columns:
            c.execute('ALTER TABLE teachers ADD COLUMN password TEXT')

    # Subjects table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='subjects'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE subjects (
                subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_code TEXT UNIQUE NOT NULL,
                subject_name TEXT NOT NULL,
                class TEXT NOT NULL,
                teacher_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    # Student subjects junction
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='student_subjects'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE student_subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                subject_id INTEGER,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'Active',
                UNIQUE(student_id, subject_id)
            )
        ''')

    # Activities table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='activities'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE activities (
                activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                activity_type TEXT NOT NULL,
                topic TEXT,
                date DATE NOT NULL,
                duration_minutes INTEGER,
                points_earned INTEGER DEFAULT 0,
                status TEXT DEFAULT 'Completed',
                remarks TEXT,
                file_path TEXT,
                file_name TEXT
            )
        ''')

    # Daily activity table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_activity'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE daily_activity (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                activity_date DATE NOT NULL,
                submission_count INTEGER DEFAULT 0,
                activity_count INTEGER DEFAULT 0,
                total_points_earned INTEGER DEFAULT 0,
                study_hours DECIMAL(3,1) DEFAULT 0,
                attendance_status TEXT DEFAULT 'Present',
                remarks TEXT,
                UNIQUE(student_id, activity_date)
            )
        ''')

    # Rewards table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='rewards'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE rewards (
                reward_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                reward_type TEXT NOT NULL,
                points_cost INTEGER,
                reward_date DATE NOT NULL,
                description TEXT,
                status TEXT DEFAULT 'Available',
                claimed_at TIMESTAMP
            )
        ''')

    # Point transactions table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='point_transactions'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE point_transactions (
                transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER,
                transaction_type TEXT NOT NULL,
                points INTEGER NOT NULL,
                description TEXT,
                reference_id INTEGER,
                transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

    # Password reset table
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='password_reset'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE password_reset (
                reset_id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                reset_code TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                used BOOLEAN DEFAULT 0
            )
        ''')

    # Sample reference answers table for AI validation
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reference_answers'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE reference_answers (
                answer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                answer_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER
            )
        ''')

    # Indexes
    try:
        c.execute('CREATE INDEX IF NOT EXISTS idx_submissions_date ON submissions(date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_activities_student ON activities(student_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_student_subjects ON student_subjects(student_id, subject_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_reference_answers ON reference_answers(subject, topic)')
    except:
        pass

    conn.commit()
    conn.close()

# ---------- Test User Creation ----------
def ensure_test_users():
    """Create test users only if they don't exist - preserves existing registrations."""
    conn = get_db_connection()
    c = conn.cursor()
    
    # Check if test student exists
    c.execute("SELECT student_id FROM students WHERE email = ?", ("test@student.com",))
    if not c.fetchone():
        password_hash = hash_password("test123")
        c.execute('''
            INSERT INTO students (reg_no, name, class, email, phone, password, last_active)
            VALUES (?, ?, ?, ?, ?, ?, DATE("now"))
        ''', ("TEST001", "Test Student", "BCA VI", "test@student.com", "1234567890", password_hash))
        print("✅ Test student created.")
    
    # Check if test teacher exists
    c.execute("SELECT teacher_id FROM teachers WHERE email = ?", ("test@teacher.com",))
    if not c.fetchone():
        teacher_hash = hash_password("test123")
        c.execute('''
            INSERT INTO teachers (teacher_code, name, email, password, department)
            VALUES (?, ?, ?, ?, ?)
        ''', ("T001", "Test Teacher", "test@teacher.com", teacher_hash, "Computer Science"))
        print("✅ Test teacher created.")

    # Add some sample reference answers
    c.execute("SELECT COUNT(*) FROM reference_answers")
    if c.fetchone()[0] == 0:
        sample_answers = [
            ("Database Management", "SQL Basics", "SQL is a standard language for storing, manipulating and retrieving data in databases. Key commands include SELECT, INSERT, UPDATE, DELETE."),
            ("Database Management", "Normalization", "Normalization is the process of organizing data to reduce redundancy. Normal forms include 1NF, 2NF, 3NF, and BCNF."),
            ("Web Technologies", "HTML", "HTML (HyperText Markup Language) is the standard markup language for creating web pages and web applications."),
            ("Python Programming", "Variables", "Variables are containers for storing data values. Python has no command for declaring a variable."),
        ]
        for subject, topic, answer in sample_answers:
            c.execute('''
                INSERT INTO reference_answers (subject, topic, answer_text)
                VALUES (?, ?, ?)
            ''', (subject, topic, answer))
        print("✅ Sample reference answers added.")

    conn.commit()
    conn.close()

# ---------- Helper Functions ----------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def generate_temp_password(length=8):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))

def cleanup_old_data():
    """Delete submissions and activities older than 6 months - preserves user accounts."""
    conn = get_db_connection()
    c = conn.cursor()
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    try:
        c.execute('DELETE FROM submissions WHERE date < ?', (six_months_ago,))
        c.execute('DELETE FROM activities WHERE date < ?', (six_months_ago,))
        c.execute('DELETE FROM daily_activity WHERE activity_date < ?', (six_months_ago,))
        c.execute('DELETE FROM password_reset WHERE created_at < ?', (six_months_ago,))
        conn.commit()
        print(f"✅ Cleaned up data older than 6 months.")
    except Exception as e:
        print(f"Cleanup error: {e}")
    finally:
        conn.close()

# ---------- AI Validation Functions ----------
def validate_submission_with_ai(submission_text, subject, topic=None):
    """
    Validate student submission using AI techniques.
    Falls back to basic analysis if scikit-learn is not available.
    """
    if not submission_text or len(submission_text.strip()) < 10:
        return {
            'confidence': 0.3,
            'feedback': "Submission is too short. Please provide more detailed content.",
            'plagiarism_score': 0.0,
            'quality_score': 0.3,
            'word_count': len(submission_text.split()),
            'keyword_score': 0.0
        }
    
    # Basic metrics
    word_count = len(submission_text.split())
    sentence_count = len(re.findall(r'[.!?]+', submission_text))
    
    # Get reference answers for this subject/topic
    conn = get_db_connection()
    c = conn.cursor()
    if topic:
        c.execute('''
            SELECT answer_text FROM reference_answers 
            WHERE subject = ? AND topic = ?
        ''', (subject, topic))
    else:
        c.execute('''
            SELECT answer_text FROM reference_answers 
            WHERE subject = ?
        ''', (subject,))
    references = [row[0] for row in c.fetchall()]
    conn.close()
    
    # Calculate similarity with reference answers
    similarity_scores = []
    if references and SKLEARN_AVAILABLE:
        try:
            vectorizer = TfidfVectorizer(stop_words='english')
            all_texts = [submission_text] + references
            tfidf_matrix = vectorizer.fit_transform(all_texts)
            similarity_matrix = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:])
            similarity_scores = similarity_matrix.flatten().tolist()
        except:
            similarity_scores = []
    elif references and not SKLEARN_AVAILABLE:
        # Basic word overlap similarity (fallback)
        submission_words = set(submission_text.lower().split())
        for ref in references:
            ref_words = set(ref.lower().split())
            if len(submission_words) > 0 and len(ref_words) > 0:
                overlap = len(submission_words.intersection(ref_words))
                total = len(submission_words.union(ref_words))
                similarity_scores.append(overlap / total if total > 0 else 0)
            else:
                similarity_scores.append(0)
    
    # Calculate plagiarism score (max similarity)
    plagiarism_score = max(similarity_scores) if similarity_scores else 0.0
    
    # Extract keywords (simple version)
    common_keywords = {
        'Database Management': ['sql', 'query', 'table', 'database', 'normalization', 'index', 'data', 'server'],
        'Web Technologies': ['html', 'css', 'javascript', 'web', 'browser', 'server', 'client', 'http'],
        'Python Programming': ['python', 'variable', 'function', 'class', 'loop', 'list', 'dict', 'import'],
        'General': ['example', 'explain', 'define', 'describe', 'compare', 'analyze', 'discuss']
    }
    
    # Get relevant keywords for this subject
    keywords = common_keywords.get(subject, common_keywords['General'])
    
    # Calculate keyword relevance
    submission_lower = submission_text.lower()
    keyword_matches = sum(1 for keyword in keywords if keyword in submission_lower)
    keyword_score = keyword_matches / len(keywords) if keywords else 0.5
    
    # Quality score based on multiple factors
    length_score = min(word_count / 100, 1.0)  # Max score at 100 words
    structure_score = min(sentence_count / 5, 1.0)  # Max score at 5 sentences
    
    # Combined quality score
    quality_score = (length_score * 0.3 + structure_score * 0.2 + keyword_score * 0.5)
    
    # Confidence score (0-1)
    confidence = quality_score * 0.7 + (1 - plagiarism_score) * 0.3
    
    # Generate AI feedback
    feedback_parts = []
    
    if word_count < 50:
        feedback_parts.append("• Your submission could be more detailed. Aim for at least 50-100 words.")
    elif word_count > 200:
        feedback_parts.append("• Good length! Your submission is comprehensive.")
    
    if plagiarism_score > 0.7:
        feedback_parts.append("⚠️ High similarity with reference materials detected. Please use your own words.")
    elif plagiarism_score > 0.4:
        feedback_parts.append("• Moderate similarity with reference materials. Try to paraphrase more.")
    else:
        feedback_parts.append("✓ Good originality in your response.")
    
    if keyword_score < 0.3:
        feedback_parts.append("• Missing key terminology. Try to include more subject-specific terms.")
    elif keyword_score > 0.7:
        feedback_parts.append("✓ Excellent use of subject terminology!")
    
    if structure_score < 0.5:
        feedback_parts.append("• Consider organizing your response into clearer sentences/paragraphs.")
    
    if not SKLEARN_AVAILABLE:
        feedback_parts.append("• Note: Advanced AI features limited (scikit-learn not installed).")
    
    feedback = "\n".join(feedback_parts)
    
    return {
        'confidence': round(confidence, 2),
        'feedback': feedback,
        'plagiarism_score': round(plagiarism_score, 2),
        'quality_score': round(quality_score, 2),
        'word_count': word_count,
        'keyword_score': round(keyword_score, 2)
    }

def add_reference_answer(subject, topic, answer_text, teacher_id):
    """Add a reference answer for AI validation."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO reference_answers (subject, topic, answer_text, created_by)
            VALUES (?, ?, ?, ?)
        ''', (subject, topic, answer_text, teacher_id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error adding reference answer: {str(e)}")
        return False
    finally:
        conn.close()

# ---------- Student Functions ----------
def add_student_with_password(reg_no, name, class_name, email, password, phone=None):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        reg_no = reg_no.strip()
        email = email.strip().lower()
        password_hash = hash_password(password)
        
        # Check duplicates (case-insensitive)
        c.execute("SELECT reg_no, email FROM students WHERE reg_no = ? COLLATE NOCASE OR email = ?", (reg_no, email))
        existing = c.fetchone()
        if existing:
            st.error("Registration number or email already exists!")
            return False

        c.execute('''
            INSERT INTO students (reg_no, name, class, email, phone, password, last_active)
            VALUES (?, ?, ?, ?, ?, ?, DATE("now"))
        ''', (reg_no, name, class_name, email, phone, password_hash))
        conn.commit()
        return True
    except sqlite3.IntegrityError as e:
        st.error(f"Registration failed: {str(e)}")
        return False
    finally:
        conn.close()

def edit_student_registration(student_id, name, class_name, email, phone):
    """Update student registration details (excluding password and reg_no)."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        email = email.strip().lower()
        # Check if email is already used by another student
        c.execute("SELECT student_id FROM students WHERE email = ? AND student_id != ?", (email, student_id))
        if c.fetchone():
            st.error("Email already exists for another student!")
            return False

        c.execute('''
            UPDATE students 
            SET name = ?, class = ?, email = ?, phone = ?
            WHERE student_id = ?
        ''', (name, class_name, email, phone, student_id))
        conn.commit()
        
        # Update the session with new values
        c.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
        updated_student = c.fetchone()
        st.session_state.current_student = updated_student
        
        return True
    except Exception as e:
        st.error(f"Error updating registration: {str(e)}")
        return False
    finally:
        conn.close()

def faculty_edit_student(student_id, reg_no, name, class_name, email, phone, password=None):
    """Faculty can edit all student details including registration number and password."""
    conn = get_db_connection()
    c = conn.cursor()
    try:
        reg_no = reg_no.strip()
        email = email.strip().lower()
        
        # Check if reg_no is already used by another student (case-insensitive)
        c.execute("SELECT student_id FROM students WHERE reg_no = ? COLLATE NOCASE AND student_id != ?", (reg_no, student_id))
        if c.fetchone():
            st.error("Registration number already exists for another student!")
            return False
        
        # Check if email is already used by another student
        c.execute("SELECT student_id FROM students WHERE email = ? AND student_id != ?", (email, student_id))
        if c.fetchone():
            st.error("Email already exists for another student!")
            return False
        
        if password:
            password_hash = hash_password(password)
            c.execute('''
                UPDATE students 
                SET reg_no = ?, name = ?, class = ?, email = ?, phone = ?, password = ?
                WHERE student_id = ?
            ''', (reg_no, name, class_name, email, phone, password_hash, student_id))
        else:
            c.execute('''
                UPDATE students 
                SET reg_no = ?, name = ?, class = ?, email = ?, phone = ?
                WHERE student_id = ?
            ''', (reg_no, name, class_name, email, phone, student_id))
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error updating student: {str(e)}")
        return False
    finally:
        conn.close()

def authenticate_student(login_id, password, use_regno=False):
    conn = get_db_connection()
    c = conn.cursor()
    # Get column names
    c.execute("PRAGMA table_info(students)")
    columns = [col[1] for col in c.fetchall()]
    
    if use_regno:
        c.execute("SELECT * FROM students WHERE reg_no = ?", (login_id.strip(),))
    else:
        c.execute("SELECT * FROM students WHERE email = ?", (login_id.strip().lower(),))
    student = c.fetchone()
    conn.close()
    
    if student:
        # Create dictionary mapping column name to value
        student_dict = dict(zip(columns, student))
        stored_hash = student_dict['password']
        if stored_hash == hash_password(password):
            return student  # return tuple for backward compatibility
    return None

def update_student_profile(student_id, name, email, phone, password=None):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if password:
            pwd_hash = hash_password(password)
            c.execute('''
                UPDATE students SET name = ?, email = ?, phone = ?, password = ?
                WHERE student_id = ?
            ''', (name, email, phone, pwd_hash, student_id))
        else:
            c.execute('''
                UPDATE students SET name = ?, email = ?, phone = ?
                WHERE student_id = ?
            ''', (name, email, phone, student_id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error updating profile: {str(e)}")
        return False
    finally:
        conn.close()

def get_student(reg_no):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE reg_no = ?", (reg_no.strip(),))
    student = c.fetchone()
    conn.close()
    return student

def get_student_by_id(student_id):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
    student = c.fetchone()
    conn.close()
    return student

# ---------- Teacher Functions ----------
def register_teacher_with_password(teacher_code, name, email, password, department):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        pwd_hash = hash_password(password)
        email = email.strip().lower()
        teacher_code = teacher_code.strip()
        c.execute('''
            INSERT INTO teachers (teacher_code, name, email, password, department)
            VALUES (?, ?, ?, ?, ?)
        ''', (teacher_code, name, email, pwd_hash, department))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def authenticate_teacher(email, password):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(teachers)")
    columns = [col[1] for col in c.fetchall()]
    c.execute("SELECT * FROM teachers WHERE email = ?", (email.strip().lower(),))
    teacher = c.fetchone()
    conn.close()
    if teacher:
        teacher_dict = dict(zip(columns, teacher))
        stored_hash = teacher_dict['password']
        if stored_hash == hash_password(password):
            return teacher
    return None

def update_teacher_profile(teacher_id, name, email, department, password=None):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        if password:
            pwd_hash = hash_password(password)
            c.execute('''
                UPDATE teachers SET name = ?, email = ?, department = ?, password = ?
                WHERE teacher_id = ?
            ''', (name, email.strip().lower(), department, pwd_hash, teacher_id))
        else:
            c.execute('''
                UPDATE teachers SET name = ?, email = ?, department = ?
                WHERE teacher_id = ?
            ''', (name, email.strip().lower(), department, teacher_id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error updating profile: {str(e)}")
        return False
    finally:
        conn.close()

def get_all_teachers():
    conn = get_db_connection()
    try:
        df = pd.read_sql_query('SELECT teacher_id, teacher_code, name, email, department FROM teachers ORDER BY name', conn)
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

# ---------- Subject Functions ----------
def add_subject(subject_code, subject_name, class_name, teacher_id=None):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO subjects (subject_code, subject_name, class, teacher_id)
            VALUES (?, ?, ?, ?)
        ''', (subject_code.strip(), subject_name, class_name, teacher_id))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_all_subjects(class_name=None):
    conn = get_db_connection()
    try:
        if class_name:
            query = '''
                SELECT s.*, t.name as teacher_name
                FROM subjects s
                LEFT JOIN teachers t ON s.teacher_id = t.teacher_id
                WHERE s.class = ?
                ORDER BY s.subject_name
            '''
            df = pd.read_sql_query(query, conn, params=(class_name,))
        else:
            query = '''
                SELECT s.*, t.name as teacher_name
                FROM subjects s
                LEFT JOIN teachers t ON s.teacher_id = t.teacher_id
                ORDER BY s.class, s.subject_name
            '''
            df = pd.read_sql_query(query, conn)
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def assign_subject_to_teacher(subject_id, teacher_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('UPDATE subjects SET teacher_id = ? WHERE subject_id = ?', (teacher_id, subject_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

def register_student_subjects(student_id, subject_ids):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        for sid in subject_ids:
            c.execute('''
                INSERT OR IGNORE INTO student_subjects (student_id, subject_id, status)
                VALUES (?, ?, 'Active')
            ''', (student_id, sid))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error registering subjects: {e}")
        return False
    finally:
        conn.close()

def get_student_subjects(student_id):
    conn = get_db_connection()
    try:
        query = '''
            SELECT s.subject_id, s.subject_code, s.subject_name, s.class,
                   t.name as teacher_name, ss.registration_date
            FROM student_subjects ss
            JOIN subjects s ON ss.subject_id = s.subject_id
            LEFT JOIN teachers t ON s.teacher_id = t.teacher_id
            WHERE ss.student_id = ? AND ss.status = 'Active'
            ORDER BY s.subject_name
        '''
        df = pd.read_sql_query(query, conn, params=(student_id,))
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def remove_student_subject(student_id, subject_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM student_subjects WHERE student_id = ? AND subject_id = ?', (student_id, subject_id))
        conn.commit()
        return True
    except:
        return False
    finally:
        conn.close()

# ---------- Forgot Password ----------
def forgot_password(email, user_type):
    email = email.strip().lower()
    conn = get_db_connection()
    c = conn.cursor()

    try:
        if user_type == "student":
            c.execute("SELECT student_id, name FROM students WHERE email = ?", (email,))
        else:
            c.execute("SELECT teacher_id, name FROM teachers WHERE email = ?", (email,))

        user = c.fetchone()

        if not user:
            conn.close()
            return False, "Email not found in our records."

        temp_password = generate_temp_password(8)
        password_hash = hash_password(temp_password)

        if user_type == "student":
            c.execute("UPDATE students SET password = ? WHERE email = ?", (password_hash, email))
        else:
            c.execute("UPDATE teachers SET password = ? WHERE email = ?", (password_hash, email))

        expires_at = datetime.now() + timedelta(hours=24)
        c.execute('''
            INSERT INTO password_reset (email, reset_code, expires_at)
            VALUES (?, ?, ?)
        ''', (email, temp_password, expires_at))

        conn.commit()
        conn.close()
        return True, temp_password

    except Exception as e:
        conn.close()
        return False, f"An error occurred: {str(e)}"

def reset_password(email, new_password):
    conn = get_db_connection()
    c = conn.cursor()
    email = email.strip().lower()
    c.execute("SELECT student_id FROM students WHERE email = ?", (email,))
    student = c.fetchone()
    if student:
        pwd_hash = hash_password(new_password)
        c.execute("UPDATE students SET password = ? WHERE email = ?", (pwd_hash, email))
        conn.commit()
        conn.close()
        return True, "student"

    c.execute("SELECT teacher_id FROM teachers WHERE email = ?", (email,))
    teacher = c.fetchone()
    if teacher:
        pwd_hash = hash_password(new_password)
        c.execute("UPDATE teachers SET password = ? WHERE email = ?", (pwd_hash, email))
        conn.commit()
        conn.close()
        return True, "teacher"

    conn.close()
    return False, None

# ---------- File Handling ----------
def get_file_download_link(file_path, file_name):
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            bytes_data = f.read()
            b64 = base64.b64encode(bytes_data).decode()
            href = f'<a href="data:application/octet-stream;base64,{b64}" download="{file_name}">📥 Download {file_name}</a>'
            return href
    return None

def get_file_view_link(file_path, file_name, file_type):
    if os.path.exists(file_path):
        if file_type and file_type.startswith('image/'):
            with open(file_path, "rb") as f:
                bytes_data = f.read()
                b64 = base64.b64encode(bytes_data).decode()
                return f'<img src="data:{file_type};base64,{b64}" style="max-width:100%; max-height:300px;">'
        elif file_type == 'application/pdf':
            with open(file_path, "rb") as f:
                bytes_data = f.read()
                b64 = base64.b64encode(bytes_data).decode()
                return f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="500px"></iframe>'
        elif file_type and file_type.startswith('text/'):
            with open(file_path, "r", encoding='utf-8', errors='ignore') as f:
                content = f.read()
                return f'<pre style="background:#f5f5f5; padding:10px;">{content}</pre>'
    return None

# ---------- Auto‑grading Functions ----------
def get_auto_grade_points(submission_type):
    mapping = {
        'Daily Homework': 5,
        'Weekly Assignment': 15,
        'Monthly Assignment': 30,
        'Seminar': 10,
        'Project': 15,
        'Research Paper': 25,
        'Lab Report': 8,
        'Extra Activity': 25
    }
    return mapping.get(submission_type, 5)

def get_auto_grade_letter(submission_type):
    mapping = {
        'Daily Homework': 'A',
        'Weekly Assignment': 'A',
        'Monthly Assignment': 'A+',
        'Seminar': 'A',
        'Project': 'A+',
        'Research Paper': 'A+',
        'Lab Report': 'A',
        'Extra Activity': 'A+'
    }
    return mapping.get(submission_type, 'A')

def add_submission_with_ai(student_id, submission_type, subject, title, description, date,
                           file_path=None, file_name=None, file_type=None, file_size=None):
    points = get_auto_grade_points(submission_type)
    grade = get_auto_grade_letter(submission_type)
    
    ai_result = validate_submission_with_ai(description, subject)
    adjusted_points = points * ai_result['confidence']
    
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO submissions (
                student_id, submission_type, subject, title, description,
                date, file_path, file_name, file_type, file_size,
                max_points, points_earned, grade,
                status, auto_graded, graded_at,
                ai_confidence, ai_feedback, plagiarism_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Graded', 1, CURRENT_TIMESTAMP, ?, ?, ?)
        ''', (student_id, submission_type, subject, title, description,
              date, file_path, file_name, file_type, file_size,
              points, adjusted_points, grade,
              ai_result['confidence'], ai_result['feedback'], ai_result['plagiarism_score']))

        submission_id = c.lastrowid

        c.execute('UPDATE students SET total_points = total_points + ?, last_active = DATE("now") WHERE student_id = ?',
                 (adjusted_points, student_id))

        c.execute('SELECT last_active FROM students WHERE student_id = ?', (student_id,))
        result = c.fetchone()
        if result:
            last_active = result[0]
            if last_active == str(date):
                c.execute('UPDATE students SET current_streak = current_streak + 1 WHERE student_id = ?', (student_id,))
                c.execute('UPDATE students SET best_streak = MAX(best_streak, current_streak) WHERE student_id = ?', (student_id,))
            else:
                c.execute('UPDATE students SET current_streak = 1 WHERE student_id = ?', (student_id,))

        c.execute('''
            INSERT INTO point_transactions (student_id, transaction_type, points, description, reference_id)
            VALUES (?, 'Auto Graded', ?, ?, ?)
        ''', (student_id, adjusted_points, f"AI-graded: {submission_type} (Conf: {ai_result['confidence']})", submission_id))

        update_daily_activity(student_id, date, 'submission', adjusted_points)
        conn.commit()
        
        st.session_state.submission_review = ai_result
        
        return submission_id
    except Exception as e:
        st.error(f"Error adding submission: {str(e)}")
        return None
    finally:
        conn.close()

def add_extra_activity(student_id, activity_type, topic, date, duration, remarks,
                       file_path=None, file_name=None):
    points = 25
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO activities (student_id, activity_type, topic, date, duration_minutes,
                                     remarks, points_earned, file_path, file_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (student_id, 'Extra Activity', topic, date, duration, remarks, points, file_path, file_name))

        c.execute('UPDATE students SET total_points = total_points + ? WHERE student_id = ?', (points, student_id))
        c.execute('''
            INSERT INTO point_transactions (student_id, transaction_type, points, description)
            VALUES (?, 'Extra Activity', ?, ?)
        ''', (student_id, points, f"Extra Activity: {topic}"))
        update_daily_activity(student_id, date, 'activity', points)
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error adding activity: {str(e)}")
        return False
    finally:
        conn.close()

def update_daily_activity(student_id, date, activity_type, points=0):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('SELECT * FROM daily_activity WHERE student_id = ? AND activity_date = ?', (student_id, date))
        existing = c.fetchone()
        if existing:
            if activity_type == 'submission':
                c.execute('''
                    UPDATE daily_activity SET submission_count = submission_count + 1,
                    total_points_earned = total_points_earned + ?
                    WHERE student_id = ? AND activity_date = ?
                ''', (points, student_id, date))
            else:
                c.execute('''
                    UPDATE daily_activity SET activity_count = activity_count + 1,
                    total_points_earned = total_points_earned + ?
                    WHERE student_id = ? AND activity_date = ?
                ''', (points, student_id, date))
        else:
            if activity_type == 'submission':
                c.execute('''
                    INSERT INTO daily_activity (student_id, activity_date, submission_count, total_points_earned)
                    VALUES (?, ?, 1, ?)
                ''', (student_id, date, points))
            else:
                c.execute('''
                    INSERT INTO daily_activity (student_id, activity_date, activity_count, total_points_earned)
                    VALUES (?, ?, 1, ?)
                ''', (student_id, date, points))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

# ---------- Query Functions ----------
def get_leaderboard(limit=20, class_filter=None):
    conn = get_db_connection()
    try:
        query = '''SELECT s.reg_no, s.name, s.class, s.total_points, s.current_streak, s.best_streak,
                  (SELECT COUNT(*) FROM submissions WHERE student_id = s.student_id) as submissions_total,
                  (SELECT COUNT(*) FROM activities WHERE student_id = s.student_id) as activities_count
                  FROM students s'''
        params = []
        if class_filter and class_filter != "All Classes":
            query += " WHERE s.class = ?"
            params.append(class_filter)
        query += ' ORDER BY s.total_points DESC, s.current_streak DESC LIMIT ?'
        params.append(limit)
        df = pd.read_sql_query(query, conn, params=params)
        if not df.empty:
            df.insert(0, 'Rank', range(1, len(df) + 1))
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_daily_activity(student_id, days=7):
    conn = get_db_connection()
    try:
        df = pd.read_sql_query('''
            SELECT activity_date, submission_count, activity_count, total_points_earned
            FROM daily_activity
            WHERE student_id = ? AND activity_date >= DATE("now", ?)
            ORDER BY activity_date DESC
        ''', conn, params=(student_id, f'-{days} days'))
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_student_progress(student_id):
    conn = get_db_connection()
    try:
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) as total_submissions, SUM(points_earned) as total_points_earned
            FROM submissions WHERE student_id = ?
        ''', (student_id,))
        subs = c.fetchone() or (0, 0)
        c.execute('''
            SELECT COUNT(*) as total_activities, SUM(points_earned) as activity_points
            FROM activities WHERE student_id = ?
        ''', (student_id,))
        acts = c.fetchone() or (0, 0)
        return {
            'total_submissions': subs[0] or 0,
            'submission_points': subs[1] or 0,
            'total_activities': acts[0] or 0,
            'activity_points': acts[1] or 0
        }
    except:
        return {'total_submissions': 0, 'submission_points': 0, 'total_activities': 0, 'activity_points': 0}
    finally:
        conn.close()

def get_all_students():
    conn = get_db_connection()
    try:
        df = pd.read_sql_query('''
            SELECT student_id, reg_no, name, class, email, phone, total_points,
                   current_streak, best_streak, last_active
            FROM students ORDER BY total_points DESC
        ''', conn)
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_student_submissions(student_id):
    conn = get_db_connection()
    try:
        df = pd.read_sql_query('''
            SELECT submission_id, submission_type, subject, title, description, date, status,
                   points_earned, max_points, grade, teacher_feedback, graded_at,
                   file_path, file_name, file_type, file_size,
                   ai_confidence, ai_feedback, plagiarism_score
            FROM submissions WHERE student_id = ? ORDER BY date DESC
        ''', conn, params=(student_id,))
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_student_activities(student_id):
    conn = get_db_connection()
    try:
        df = pd.read_sql_query('''
            SELECT activity_id, activity_type, topic, date, duration_minutes, points_earned, remarks,
                   file_path, file_name
            FROM activities WHERE student_id = ? ORDER BY date DESC
        ''', conn, params=(student_id,))
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_all_submissions_for_teacher():
    conn = get_db_connection()
    try:
        df = pd.read_sql_query('''
            SELECT s.submission_id, s.submission_type, s.subject, s.title, s.date,
                   s.file_path, s.file_name, s.file_type, s.file_size,
                   s.ai_confidence, s.ai_feedback, s.plagiarism_score,
                   st.name as student_name, st.reg_no, st.class
            FROM submissions s
            JOIN students st ON s.student_id = st.student_id
            ORDER BY s.date DESC
        ''', conn)
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def delete_student(student_id):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute('DELETE FROM submissions WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM activities WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM daily_activity WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM rewards WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM point_transactions WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM student_subjects WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM students WHERE student_id = ?', (student_id,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error deleting student: {str(e)}")
        return False
    finally:
        conn.close()

# ---------- Initialise ----------
init_database()
ensure_test_users()
cleanup_old_data()
Path("uploads").mkdir(exist_ok=True)

# ==================== STREAMLIT UI ====================
st.title("📚 Continuous Student Evaluation & Monitoring System")
st.markdown("---")

# Show sklearn availability warning if needed
if not SKLEARN_AVAILABLE:
    st.sidebar.warning("⚠️ Advanced AI features limited. Install scikit-learn for full functionality.")

# Sidebar
with st.sidebar:
    if st.session_state.user_role:
        if st.session_state.user_role == "student":
            student = st.session_state.current_student
            if student:
                # Get column names for safe indexing
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("PRAGMA table_info(students)")
                columns = [col[1] for col in c.fetchall()]
                conn.close()
                student_dict = dict(zip(columns, student))
                st.header("🎓 Student Info")
                st.success(f"**{student_dict.get('name', '')}**")
                st.info(f"Reg No: {student_dict.get('reg_no', '')}")
                st.info(f"Class: {student_dict.get('class', '')}")
                st.info(f"Email: {student_dict.get('email', '')}")
                st.info(f"Points: {student_dict.get('total_points', 0)} 🏆")
                st.info(f"Streak: {student_dict.get('current_streak', 0)} days 🔥")
                if st.button("✏️ Edit Registration"):
                    st.session_state.page = "edit_registration"
                    st.rerun()
            if st.button("Logout"):
                st.session_state.current_student = None
                st.session_state.user_role = None
                st.session_state.page = "Welcome"
                st.rerun()
        elif st.session_state.user_role == "teacher":
            teacher = st.session_state.current_teacher
            if teacher:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("PRAGMA table_info(teachers)")
                columns = [col[1] for col in c.fetchall()]
                conn.close()
                teacher_dict = dict(zip(columns, teacher))
                st.header("👨‍🏫 Teacher Info")
                st.success(f"**Prof. {teacher_dict.get('name', '')}**")
                st.info(f"Email: {teacher_dict.get('email', '')}")
                st.info(f"Dept: {teacher_dict.get('department', '')}")
            if st.button("Logout"):
                st.session_state.current_teacher = None
                st.session_state.user_role = None
                st.session_state.page = "Welcome"
                st.rerun()
    else:
        st.header("🔐 Login")
        login_tab1, login_tab2, login_tab3 = st.tabs(["Student Login", "Teacher Login", "Forgot Password"])

        with login_tab1:
            with st.expander("Test Credentials (use these)"):
                st.write("**Student:** test@student.com / test123")
                st.write("**Registration No:** TEST001 / test123")
            login_method = st.radio("Login with:", ["Email", "Registration Number"])
            if login_method == "Email":
                email = st.text_input("Email", key="student_email")
                password = st.text_input("Password", type="password", key="student_pass")
                if st.button("Student Login", key="student_login_btn"):
                    if email and password:
                        student = authenticate_student(email, password, use_regno=False)
                        if student:
                            st.session_state.current_student = student
                            st.session_state.user_role = "student"
                            st.session_state.page = "🏠 Dashboard"
                            st.rerun()
                        else:
                            st.error("Invalid email or password!")
            else:
                reg_no = st.text_input("Registration Number", key="student_regno")
                password = st.text_input("Password", type="password", key="student_pass_reg")
                if st.button("Student Login", key="student_login_reg_btn"):
                    if reg_no and password:
                        student = authenticate_student(reg_no, password, use_regno=True)
                        if student:
                            st.session_state.current_student = student
                            st.session_state.user_role = "student"
                            st.session_state.page = "🏠 Dashboard"
                            st.rerun()
                        else:
                            st.error("Invalid registration number or password!")

        with login_tab2:
            with st.expander("Test Credentials"):
                st.write("**Teacher:** test@teacher.com / test123")
            email = st.text_input("Email", key="teacher_email")
            password = st.text_input("Password", type="password", key="teacher_pass")
            if st.button("Teacher Login", key="teacher_login_btn"):
                if email and password:
                    teacher = authenticate_teacher(email, password)
                    if teacher:
                        st.session_state.current_teacher = teacher
                        st.session_state.user_role = "teacher"
                        st.session_state.page = "🏠 Teacher Dashboard"
                        st.rerun()
                    else:
                        st.error("Invalid email or password!")

        with login_tab3:
            st.subheader("🔑 Forgot Password")
            with st.form("forgot_password_form"):
                fp_email = st.text_input("Enter your registered email", key="fp_email").strip()
                fp_user_type = st.selectbox("I am a", ["Student", "Teacher"], key="fp_type")
                submitted = st.form_submit_button("Reset Password")

                if submitted:
                    if not fp_email:
                        st.error("Please enter your email address.")
                    else:
                        success, result = forgot_password(fp_email, fp_user_type.lower())
                        if success:
                            st.success("✅ Password reset successfully!")
                            st.info(f"🔑 **Your temporary password is:** `{result}`")
                            st.warning("Please copy this password and use it to log in. You can change it after logging in.")
                        else:
                            st.error(f"❌ {result}")

        with st.expander("🔧 Debug"):
            if st.button("🚀 Direct Login as Test Student"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT * FROM students WHERE email = ?", ("test@student.com",))
                student = c.fetchone()
                conn.close()
                if student:
                    st.session_state.current_student = student
                    st.session_state.user_role = "student"
                    st.session_state.page = "🏠 Dashboard"
                    st.rerun()
                else:
                    st.error("Test student not found.")
            if st.button("🔑 Show Stored Hashes"):
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT email, password FROM students WHERE email='test@student.com'")
                s = c.fetchone()
                c.execute("SELECT email, password FROM teachers WHERE email='test@teacher.com'")
                t = c.fetchone()
                conn.close()
                if s:
                    st.write(f"Student hash: {s[1]}")
                if t:
                    st.write(f"Teacher hash: {t[1]}")

    st.markdown("---")
    if st.session_state.user_role:
        st.header("📱 Navigation")
        if st.session_state.user_role == "student":
            if st.session_state.page != "edit_registration":
                selected = st.radio("Go to:", [
                    "🏠 Dashboard", "📚 My Subjects", "➕ New Submission", "➕ Extra Activity",
                    "📋 My Submissions", "📂 My Uploads", "📈 Daily Activity", "🏆 Leaderboard",
                    "🎁 Rewards", "👤 Edit Profile"
                ])
                if selected != st.session_state.page:
                    st.session_state.page = selected
                    st.rerun()
            else:
                st.radio("Go to:", [
                    "🏠 Dashboard", "📚 My Subjects", "➕ New Submission", "➕ Extra Activity",
                    "📋 My Submissions", "📂 My Uploads", "📈 Daily Activity", "🏆 Leaderboard",
                    "🎁 Rewards", "👤 Edit Profile"
                ], index=0, disabled=True)
                if st.button("← Back to Dashboard"):
                    st.session_state.page = "🏠 Dashboard"
                    st.rerun()
        else:
            selected = st.radio("Go to:", [
                "🏠 Teacher Dashboard", "📚 Subject Management", "👨‍🎓 Manage Students",
                "📂 View Submissions", "📊 Class Analytics", "🏆 Leaderboard", "👤 Edit Profile",
                "⚙️ Manage System", "🤖 AI Reference Answers"
            ])
            if selected != st.session_state.page:
                st.session_state.page = selected
                st.rerun()
    else:
        if st.session_state.page != "Welcome":
            st.session_state.page = "Welcome"

# ========== MAIN CONTENT ==========
if st.session_state.page == "Welcome":
    st.header("Welcome to Student Evaluation System")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📝 Student Registration")
        st.write("- Register with email and password")
        st.write("- Choose your subjects (dynamic classes)")
        st.write("- Submit assignments and earn points")
        st.write("- AI-powered validation system")
        st.write("- Track your progress")

        with st.expander("New Student Registration"):
            with st.form("new_student_form"):
                reg_no = st.text_input("Registration Number*")
                name = st.text_input("Full Name*")
                class_name = st.text_input("Class*", placeholder="e.g., BA I, BCom II, BCA III")
                email = st.text_input("Email*")
                phone = st.text_input("Phone")
                password = st.text_input("Password*", type="password")
                confirm_password = st.text_input("Confirm Password*", type="password")

                if st.form_submit_button("Register"):
                    if reg_no and name and class_name and email and password:
                        if password == confirm_password:
                            if add_student_with_password(reg_no, name, class_name, email, password, phone):
                                st.success("✅ Registration successful! Please login.")
                                st.info("📚 After login, you can select your subjects.")
                            else:
                                st.error("Registration failed! Email or Registration number may already exist.")
                        else:
                            st.error("Passwords do not match!")
                    else:
                        st.error("Please fill all required fields (*)")

    with col2:
        st.subheader("👨‍🏫 Teacher Registration")
        st.write("- Register with email and password")
        st.write("- Create and manage subjects")
        st.write("- Assign subjects to yourself")
        st.write("- Monitor student performance")
        st.write("- Manage AI reference answers")

        with st.expander("Teacher Registration"):
            with st.form("teacher_reg_form"):
                t_code = st.text_input("Teacher Code*")
                t_name = st.text_input("Full Name*")
                t_email = st.text_input("Email*")
                t_password = st.text_input("Password*", type="password")
                t_confirm = st.text_input("Confirm Password*", type="password")
                t_dept = st.text_input("Department*", placeholder="e.g., History, Mathematics, Computer Science")

                if st.form_submit_button("Register as Teacher"):
                    if all([t_code, t_name, t_email, t_password, t_confirm, t_dept]):
                        if t_password == t_confirm:
                            if register_teacher_with_password(t_code, t_name, t_email, t_password, t_dept):
                                st.success("✅ Registration successful! Please login.")
                                st.info("📚 After login, you can create and manage subjects and AI reference answers.")
                            else:
                                st.error("Teacher code or email already exists!")
                        else:
                            st.error("Passwords do not match!")
                    else:
                        st.error("Please fill all fields")

# ========== STUDENT SECTION ==========
elif st.session_state.user_role == "student":
    student = st.session_state.current_student
    if not student:
        st.error("Please login first!")
        st.stop()

    # Get column names for this student
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(students)")
    columns = [col[1] for col in c.fetchall()]
    conn.close()
    student_dict = dict(zip(columns, student))
    student_id = student_dict['student_id']
    student_reg = student_dict['reg_no']
    student_name = student_dict['name']
    student_class = student_dict['class']
    student_email = student_dict['email']
    student_phone = student_dict['phone']
    total_points = student_dict['total_points']
    current_streak = student_dict['current_streak']
    best_streak = student_dict['best_streak']
    
    if st.session_state.page == "edit_registration":
        st.header("✏️ Edit Your Registration Details")
        st.info("Update your personal information below. Registration number cannot be changed.")
        
        with st.form("edit_registration_form"):
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Registration Number", value=student_reg, disabled=True)
                name = st.text_input("Full Name*", value=student_name)
                class_name = st.text_input("Class*", value=student_class, 
                                          placeholder="e.g., BA I, BCom II, BCA III")
            with col2:
                st.info("Your registration number is permanent and cannot be changed.")
                email = st.text_input("Email*", value=student_email if student_email else "")
                phone = st.text_input("Phone", value=student_phone if student_phone else "")
            
            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                if st.form_submit_button("💾 Save Changes", type="primary"):
                    if name and class_name and email:
                        if edit_student_registration(student_id, name, class_name, email, phone):
                            st.success("✅ Registration details updated successfully!")
                            st.session_state.page = "🏠 Dashboard"
                            st.rerun()
                    else:
                        st.error("Please fill all required fields (*)")
            with col2:
                if st.form_submit_button("↩️ Cancel"):
                    st.session_state.page = "🏠 Dashboard"
                    st.rerun()
        
        st.info("📚 Note: Changing your class may affect which subjects are available to you. You can manage your subject registrations in the 'My Subjects' page.")
        
    elif st.session_state.page == "🏠 Dashboard":
        st.header(f"Welcome back, {student_name}! 👋")

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Points", total_points, "🏆")
        with col2:
            st.metric("Current Streak", f"{current_streak} days", "🔥")
        with col3:
            st.metric("Best Streak", f"{best_streak} days", "⭐")
        with col4:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM submissions WHERE student_id = ?', (student_id,))
            total_subs = c.fetchone()[0] or 0
            conn.close()
            st.metric("Total Submissions", total_subs, "📝")

        st.markdown("---")

        st.subheader("📚 Your Registered Subjects")
        subjects_df = get_student_subjects(student_id)
        if not subjects_df.empty:
            st.dataframe(subjects_df[['subject_code', 'subject_name', 'teacher_name']], use_container_width=True)
        else:
            st.info("You haven't registered for any subjects yet. Go to 'My Subjects' to register!")

        progress = get_student_progress(student_id)
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Submission Progress")
            st.metric("Total Submissions", progress['total_submissions'])
            st.metric("Submission Points", progress['submission_points'])
        with col2:
            st.subheader("🎯 Activity Progress")
            st.metric("Total Activities", progress['total_activities'])
            st.metric("Activity Points", progress['activity_points'])

        st.subheader("📅 Recent Activity (Last 7 Days)")
        daily_activity = get_daily_activity(student_id, 7)
        if not daily_activity.empty:
            st.dataframe(daily_activity, use_container_width=True)
        else:
            st.info("No recent activity found. Start submitting!")

        if st.session_state.submission_review:
            with st.expander("📊 Latest AI Submission Analysis", expanded=True):
                review = st.session_state.submission_review
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("AI Confidence", f"{review['confidence']*100:.0f}%")
                with col2:
                    st.metric("Originality Score", f"{(1-review['plagiarism_score'])*100:.0f}%")
                with col3:
                    st.metric("Quality Score", f"{review['quality_score']*100:.0f}%")
                st.info(f"📝 **AI Feedback:**\n{review['feedback']}")

    # My Subjects
    elif st.session_state.page == "📚 My Subjects":
        st.header("📚 Subject Registration")
        tab1, tab2 = st.tabs(["➕ Register New Subjects", "📋 My Registered Subjects"])

        with tab1:
            st.subheader(f"Available Subjects for {student_class}")
            available_subjects = get_all_subjects(student_class)

            if not available_subjects.empty:
                registered_df = get_student_subjects(student_id)
                registered_ids = registered_df['subject_id'].tolist() if not registered_df.empty else []
                available_subjects = available_subjects[~available_subjects['subject_id'].isin(registered_ids)]

                if not available_subjects.empty:
                    subject_options = []
                    for _, row in available_subjects.iterrows():
                        teacher = row['teacher_name'] if row['teacher_name'] else "Not Assigned"
                        subject_options.append({
                            'id': row['subject_id'],
                            'display': f"{row['subject_code']} - {row['subject_name']} (Teacher: {teacher})"
                        })

                    selected_subjects = st.multiselect(
                        "Select Subjects to Register",
                        options=[s['display'] for s in subject_options]
                    )

                    if st.button("Register Selected Subjects", type="primary"):
                        selected_ids = [s['id'] for s in subject_options if s['display'] in selected_subjects]
                        if selected_ids:
                            if register_student_subjects(student_id, selected_ids):
                                st.success(f"✅ Successfully registered for {len(selected_ids)} subjects!")
                                st.rerun()
                            else:
                                st.error("Failed to register subjects.")
                else:
                    st.info("You have already registered for all available subjects in your class!")
            else:
                st.info("No subjects available for your class yet. Please check with your teachers.")

        with tab2:
            st.subheader("Your Registered Subjects")
            subjects_df = get_student_subjects(student_id)
            if not subjects_df.empty:
                st.dataframe(subjects_df[['subject_code', 'subject_name', 'teacher_name', 'registration_date']],
                           use_container_width=True)
                with st.expander("Remove Subject Registration"):
                    subject_to_remove = st.selectbox(
                        "Select Subject to Remove",
                        subjects_df['subject_name'].tolist()
                    )
                    if st.button("Remove Subject"):
                        subject_id = subjects_df[subjects_df['subject_name'] == subject_to_remove]['subject_id'].iloc[0]
                        if remove_student_subject(student_id, subject_id):
                            st.success(f"Removed {subject_to_remove} successfully!")
                            st.rerun()
            else:
                st.info("You haven't registered for any subjects yet.")

    # New Submission with AI
    elif st.session_state.page == "➕ New Submission":
        st.header("New Submission - AI Powered!")
        if not SKLEARN_AVAILABLE:
            st.warning("⚠️ Running in basic mode. Install scikit-learn for advanced AI features.")
        st.info("✅ Your submission will be analyzed by AI for quality and originality.")

        subjects_df = get_student_subjects(student_id)
        if subjects_df.empty:
            st.warning("⚠️ Please register for subjects first before submitting assignments!")
            st.info("Go to 'My Subjects' to register for subjects.")
        else:
            with st.form("submission_form"):
                col1, col2 = st.columns(2)
                with col1:
                    subject_list = subjects_df['subject_name'].tolist()
                    selected_subject = st.selectbox("Subject*", subject_list)
                    submission_type = st.selectbox("Submission Type*",
                        ["Daily Homework", "Weekly Assignment", "Monthly Assignment",
                         "Seminar", "Project", "Research Paper", "Lab Report"])
                    title = st.text_input("Title*")
                    date = st.date_input("Date*", datetime.now().date())
                with col2:
                    base_points = get_auto_grade_points(submission_type)
                    st.info(f"📊 Base points: **{base_points}**")
                    st.info("🤖 AI will adjust points based on quality")

                description = st.text_area("Description*", height=200, 
                    placeholder="Write your detailed submission here... The AI will analyze your content for quality, relevance, and originality.")

                uploaded_file = st.file_uploader("Upload File (optional)",
                    type=['pdf', 'docx', 'txt', 'jpg', 'png', 'zip', 'py', 'java', 'cpp'])

                if st.form_submit_button("Submit", type="primary"):
                    if title and description:
                        file_path = None
                        file_name = None
                        file_type = None
                        file_size = None

                        if uploaded_file:
                            upload_dir = Path("uploads") / student_reg / "submissions"
                            upload_dir.mkdir(parents=True, exist_ok=True)
                            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                            file_name = f"{timestamp}_{uploaded_file.name}"
                            file_path = str(upload_dir / file_name)
                            file_type = uploaded_file.type
                            file_size = uploaded_file.size

                            with open(file_path, "wb") as f:
                                f.write(uploaded_file.getbuffer())

                        submission_id = add_submission_with_ai(student_id, submission_type, selected_subject,
                                                              title, description, date,
                                                              file_path, file_name, file_type, file_size)
                        if submission_id:
                            st.success("✅ Submission recorded! AI analysis complete.")
                            st.balloons()
                            st.rerun()
                        else:
                            st.error("Failed to record submission.")
                    else:
                        st.error("Please fill all required fields (*)")

    # Extra Activity
    elif st.session_state.page == "➕ Extra Activity":
        st.header("Add Extra Activity")
        st.success("🎯 Extra Activities earn **25 points** each!")

        with st.form("extra_activity_form"):
            col1, col2 = st.columns(2)
            with col1:
                activity_type = st.selectbox("Activity Type",
                    ["Workshop", "Sports", "Cultural", "Competition",
                     "Volunteer", "Club Meeting", "Guest Lecture", "Other"])
                topic = st.text_input("Topic*")
                date = st.date_input("Activity Date*", datetime.now().date())
            with col2:
                duration = st.number_input("Duration (minutes)", min_value=1, value=60)
                remarks = st.text_area("Remarks")
                uploaded_file = st.file_uploader("Upload Supporting Document",
                    type=['pdf', 'docx', 'txt', 'jpg', 'png', 'zip'])

            if st.form_submit_button("Add Activity"):
                if topic:
                    file_path = None
                    file_name = None

                    if uploaded_file:
                        upload_dir = Path("uploads") / student_reg / "activities"
                        upload_dir.mkdir(parents=True, exist_ok=True)
                        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                        file_name = f"{timestamp}_{uploaded_file.name}"
                        file_path = str(upload_dir / file_name)

                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())

                    if add_extra_activity(student_id, activity_type, topic, date, duration, remarks, file_path, file_name):
                        st.success("✅ Activity added! You earned 25 points!")
                        st.balloons()
                        st.rerun()
                else:
                    st.error("Please enter topic")

    # My Submissions
    elif st.session_state.page == "📋 My Submissions":
        st.header("My Submissions")
        df = get_student_submissions(student_id)

        if not df.empty:
            total_subs = len(df)
            total_pts = df['points_earned'].sum()
            avg_pts = df['points_earned'].mean()
            avg_confidence = df['ai_confidence'].mean()

            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Submissions", total_subs)
            with col2:
                st.metric("Total Points", total_pts)
            with col3:
                st.metric("Avg Points", f"{avg_pts:.1f}")
            with col4:
                st.metric("Avg AI Confidence", f"{avg_confidence*100:.0f}%")

            for idx, row in df.iterrows():
                with st.expander(f"📄 {row['title']} - {row['date']} (Grade: {row['grade']}, Points: {row['points_earned']})"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Subject:** {row['subject']}")
                        st.write(f"**Type:** {row['submission_type']}")
                        st.write(f"**Description:** {row['description']}")
                    with col2:
                        st.write(f"**Status:** {row['status']}")
                        st.write(f"**Submitted:** {row['date']}")
                        if row['teacher_feedback']:
                            st.write(f"**Teacher Feedback:** {row['teacher_feedback']}")
                    
                    if row['ai_confidence'] > 0:
                        st.markdown("---")
                        st.write("**🤖 AI Analysis:**")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("AI Confidence", f"{row['ai_confidence']*100:.0f}%")
                        with col2:
                            st.metric("Originality", f"{(1-row['plagiarism_score'])*100:.0f}%")
                        if row['ai_feedback']:
                            st.info(f"📝 **AI Feedback:**\n{row['ai_feedback']}")

                    if row['file_path'] and os.path.exists(row['file_path']):
                        st.markdown("---")
                        st.write("**📎 Attached File:**")
                        col1, col2 = st.columns(2)
                        with col1:
                            download_link = get_file_download_link(row['file_path'], row['file_name'] or "file")
                            if download_link:
                                st.markdown(download_link, unsafe_allow_html=True)
                        with col2:
                            if st.button(f"👁️ Preview", key=f"preview_{row['submission_id']}"):
                                st.session_state.view_file = {
                                    'path': row['file_path'],
                                    'name': row['file_name'],
                                    'type': row['file_type']
                                }

                    if st.session_state.get('view_file') and st.session_state.view_file['path'] == row['file_path']:
                        preview = get_file_view_link(
                            st.session_state.view_file['path'],
                            st.session_state.view_file['name'],
                            st.session_state.view_file['type']
                        )
                        if preview:
                            st.markdown("---")
                            st.write("**📄 Preview:**")
                            st.markdown(preview, unsafe_allow_html=True)
        else:
            st.info("No submissions found.")

    # My Uploads
    elif st.session_state.page == "📂 My Uploads":
        st.header("📂 My Uploaded Files")

        tab1, tab2 = st.tabs(["📤 Submissions", "🎯 Activities"])

        with tab1:
            st.subheader("Submission Files")
            submissions = get_student_submissions(student_id)
            files_found = False

            for _, row in submissions.iterrows():
                if row['file_path'] and os.path.exists(row['file_path']):
                    files_found = True
                    with st.container():
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.write(f"**{row['title']}** ({row['subject']})")
                            st.write(f"📅 {row['date']} | 📄 {row['file_name']}")
                        with col2:
                            download_link = get_file_download_link(row['file_path'], row['file_name'])
                            if download_link:
                                st.markdown(download_link, unsafe_allow_html=True)
                        with col3:
                            if st.button("👁️ View", key=f"view_sub_{row['submission_id']}"):
                                preview = get_file_view_link(row['file_path'], row['file_name'], row['file_type'])
                                if preview:
                                    st.session_state.view_content = preview
                        st.markdown("---")

            if not files_found:
                st.info("No files uploaded yet.")

        with tab2:
            st.subheader("Activity Files")
            activities = get_student_activities(student_id)
            files_found = False

            for _, row in activities.iterrows():
                if row['file_path'] and os.path.exists(row['file_path']):
                    files_found = True
                    with st.container():
                        col1, col2, col3 = st.columns([3, 1, 1])
                        with col1:
                            st.write(f"**{row['topic']}** ({row['activity_type']})")
                            st.write(f"📅 {row['date']} | 📄 {row['file_name']}")
                        with col2:
                            download_link = get_file_download_link(row['file_path'], row['file_name'])
                            if download_link:
                                st.markdown(download_link, unsafe_allow_html=True)
                        with col3:
                            if st.button("👁️ View", key=f"view_act_{row['activity_id']}"):
                                preview = get_file_view_link(row['file_path'], row['file_name'], None)
                                if preview:
                                    st.session_state.view_content = preview
                        st.markdown("---")

            if not files_found:
                st.info("No activity files uploaded yet.")

        if 'view_content' in st.session_state:
            st.markdown("---")
            st.subheader("Preview")
            st.markdown(st.session_state.view_content, unsafe_allow_html=True)
            if st.button("Close Preview"):
                del st.session_state.view_content

    # Daily Activity
    elif st.session_state.page == "📈 Daily Activity":
        st.header("Daily Activity Tracker")
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", datetime.now().date() - timedelta(days=30))
        with col2:
            end_date = st.date_input("End Date", datetime.now().date())

        conn = get_db_connection()
        df = pd.read_sql_query(
            'SELECT activity_date, submission_count, activity_count, total_points_earned FROM daily_activity WHERE student_id = ? AND activity_date BETWEEN ? AND ? ORDER BY activity_date DESC',
            conn, params=(student_id, start_date, end_date))
        conn.close()

        if not df.empty:
            total_days = len(df)
            active_days = len(df[df['total_points_earned'] > 0])
            total_pts = df['total_points_earned'].sum()
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Days", total_days)
            with col2:
                st.metric("Active Days", active_days)
            with col3:
                st.metric("Total Points", total_pts)
            st.subheader("📋 Daily Log")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No activity recorded for the selected period.")

    # Leaderboard
    elif st.session_state.page == "🏆 Leaderboard":
        st.header("🏆 Student Leaderboard")
        col1, col2 = st.columns(2)
        with col1:
            conn = get_db_connection()
            classes_df = pd.read_sql_query("SELECT DISTINCT class FROM students ORDER BY class", conn)
            conn.close()
            class_list = ["All Classes"] + classes_df['class'].tolist() if not classes_df.empty else ["All Classes"]
            class_filter = st.selectbox("Filter by Class", class_list)
        with col2:
            limit = st.slider("Top N Students", 5, 50, 20)

        leaderboard = get_leaderboard(limit, class_filter)

        if not leaderboard.empty:
            st.subheader("📊 Full Leaderboard")
            display_df = leaderboard[['Rank', 'name', 'class', 'total_points', 'current_streak', 'best_streak', 'submissions_total', 'activities_count']]
            display_df.columns = ['Rank', 'Name', 'Class', 'Total Points', 'Current Streak', 'Best Streak', 'Submissions', 'Activities']
            st.dataframe(display_df, use_container_width=True)

            current_rank = leaderboard[leaderboard['reg_no'] == student_reg]['Rank'].values
            if len(current_rank) > 0:
                st.info(f"🏅 Your current rank: **#{current_rank[0]}** with **{total_points} points**")
        else:
            st.info("No students found in the leaderboard.")

    # Rewards
    elif st.session_state.page == "🎁 Rewards":
        st.header("🎁 Reward Store")
        st.info(f"💰 You have **{total_points} points** available")

        rewards = [
            {"name": "📚 Book Voucher", "cost": 50, "description": "Get a voucher for academic books"},
            {"name": "🎮 Game Time", "cost": 30, "description": "Extra 2 hours of gaming time"},
            {"name": "🍕 Pizza Party", "cost": 100, "description": "Pizza party for your class"},
            {"name": "🏆 Trophy", "cost": 200, "description": "Custom achievement trophy"},
            {"name": "📱 Tech Gadget", "cost": 500, "description": "Latest tech gadget"},
            {"name": "🎉 Celebration", "cost": 80, "description": "Class celebration party"},
            {"name": "⭐ Star Badge", "cost": 20, "description": "Special recognition badge"},
            {"name": "📝 Extra Credit", "cost": 40, "description": "5% extra credit on next assignment"},
        ]

        cols = st.columns(2)
        for i, reward in enumerate(rewards):
            with cols[i % 2]:
                st.markdown(f"### {reward['name']}")
                st.markdown(f"**Cost:** {reward['cost']} points")
                st.markdown(reward['description'])
                if total_points >= reward['cost']:
                    if st.button(f"Claim {reward['name']}", key=f"claim_{i}"):
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute('UPDATE students SET total_points = total_points - ? WHERE student_id = ?', (reward['cost'], student_id))
                        c.execute('INSERT INTO rewards (student_id, reward_type, points_cost, reward_date, status) VALUES (?, ?, ?, DATE("now"), "Claimed")', (student_id, reward['name'], reward['cost']))
                        c.execute('INSERT INTO point_transactions (student_id, transaction_type, points, description) VALUES (?, "Reward Claimed", ?, ?)', (student_id, -reward['cost'], f"Claimed: {reward['name']}"))
                        conn.commit()
                        conn.close()
                        st.success(f"🎉 You claimed {reward['name']}!")
                        st.rerun()
                else:
                    st.warning(f"Need {reward['cost'] - total_points} more points")
                st.markdown("---")

    # Edit Profile
    elif st.session_state.page == "👤 Edit Profile":
        st.header("Edit Profile")
        with st.form("edit_profile_form"):
            name = st.text_input("Full Name", value=student_name)
            email = st.text_input("Email", value=student_email if student_email else "")
            phone = st.text_input("Phone", value=student_phone if student_phone else "")
            st.subheader("Change Password (Optional)")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("Update Profile"):
                if new_password:
                    if new_password == confirm_password:
                        if update_student_profile(student_id, name, email, phone, new_password):
                            st.success("✅ Profile updated successfully! Please login again.")
                            st.session_state.current_student = None
                            st.session_state.user_role = None
                            st.session_state.page = "Welcome"
                            st.rerun()
                    else:
                        st.error("Passwords do not match!")
                else:
                    if update_student_profile(student_id, name, email, phone):
                        st.success("✅ Profile updated successfully!")
                        student = list(student)
                        # Update session with new values
                        student[2] = name
                        student[4] = email
                        student[5] = phone
                        st.session_state.current_student = tuple(student)
                        st.rerun()

# ========== TEACHER SECTION ==========
elif st.session_state.user_role == "teacher":
    teacher = st.session_state.current_teacher
    if not teacher:
        st.error("Please login first!")
        st.stop()

    conn = get_db_connection()
    c = conn.cursor()
    c.execute("PRAGMA table_info(teachers)")
    columns = [col[1] for col in c.fetchall()]
    conn.close()
    teacher_dict = dict(zip(columns, teacher))
    teacher_id = teacher_dict['teacher_id']
    teacher_name = teacher_dict['name']
    teacher_email = teacher_dict['email']
    teacher_dept = teacher_dict['department']

    if st.session_state.page == "🏠 Teacher Dashboard":
        st.header(f"Teacher Dashboard 👨‍🏫")
        conn = get_db_connection()
        try:
            total_students = pd.read_sql_query("SELECT COUNT(*) FROM students", conn).iloc[0,0] or 0
            total_submissions = pd.read_sql_query("SELECT COUNT(*) FROM submissions", conn).iloc[0,0] or 0
            total_points = pd.read_sql_query("SELECT SUM(total_points) FROM students", conn).iloc[0,0] or 0
            total_subjects = pd.read_sql_query("SELECT COUNT(*) FROM subjects WHERE teacher_id = ?", conn, params=(teacher_id,)).iloc[0,0] or 0
        except:
            total_students = 0
            total_submissions = 0
            total_points = 0
            total_subjects = 0
        finally:
            conn.close()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Students", total_students)
        with col2:
            st.metric("Total Submissions", total_submissions)
        with col3:
            st.metric("Total Points Awarded", total_points)
        with col4:
            st.metric("My Subjects", total_subjects)

        st.markdown("---")
        st.subheader("📚 My Subjects")
        subjects_df = get_all_subjects()
        my_subjects = subjects_df[subjects_df['teacher_id'] == teacher_id] if not subjects_df.empty else pd.DataFrame()
        if not my_subjects.empty:
            st.dataframe(my_subjects[['subject_code', 'subject_name', 'class']], use_container_width=True)
        else:
            st.info("You haven't been assigned any subjects yet.")

        st.subheader("📊 Class Distribution")
        conn = get_db_connection()
        class_dist = pd.read_sql_query("SELECT class, COUNT(*) as count FROM students GROUP BY class", conn)
        conn.close()
        if not class_dist.empty:
            st.dataframe(class_dist, use_container_width=True)

    # Subject Management
    elif st.session_state.page == "📚 Subject Management":
        st.header("📚 Subject Management")
        tab1, tab2, tab3 = st.tabs(["➕ Create Subject", "📋 My Subjects", "👥 Assign Teachers"])

        with tab1:
            st.subheader("Create New Subject")
            with st.form("create_subject_form"):
                subject_code = st.text_input("Subject Code*", placeholder="e.g., HIST101, MATH202")
                subject_name = st.text_input("Subject Name*", placeholder="e.g., World History, Calculus")
                class_name = st.text_input("Class*", placeholder="e.g., BA I, BCom II, BCA III")
                assign_to_self = st.checkbox("Assign this subject to me")
                if st.form_submit_button("Create Subject"):
                    if subject_code and subject_name and class_name:
                        teacher_id_to_assign = teacher_id if assign_to_self else None
                        if add_subject(subject_code, subject_name, class_name, teacher_id_to_assign):
                            st.success(f"✅ Subject '{subject_name}' created successfully!")
                            st.rerun()
                        else:
                            st.error("Subject code already exists!")
                    else:
                        st.error("Please fill all required fields (*)")

        with tab2:
            st.subheader("Subjects I Teach")
            subjects_df = get_all_subjects()
            my_subjects = subjects_df[subjects_df['teacher_id'] == teacher_id] if not subjects_df.empty else pd.DataFrame()
            if not my_subjects.empty:
                st.dataframe(my_subjects[['subject_code', 'subject_name', 'class', 'created_at']],
                           use_container_width=True)
                with st.expander("Remove Subject from My List"):
                    subject_to_remove = st.selectbox(
                        "Select Subject to Remove",
                        my_subjects['subject_name'].tolist()
                    )
                    if st.button("Remove from My Subjects"):
                        subject_id = my_subjects[my_subjects['subject_name'] == subject_to_remove]['subject_id'].iloc[0]
                        if assign_subject_to_teacher(subject_id, None):
                            st.success(f"Removed {subject_to_remove} from your subjects!")
                            st.rerun()
            else:
                st.info("You haven't been assigned any subjects yet.")

        with tab3:
            st.subheader("Assign Subjects to Teachers")
            teachers_df = get_all_teachers()
            subjects_df = get_all_subjects()
            unassigned_subjects = subjects_df[pd.isna(subjects_df['teacher_id'])] if not subjects_df.empty else pd.DataFrame()

            if not teachers_df.empty and not unassigned_subjects.empty:
                col1, col2 = st.columns(2)
                with col1:
                    selected_teacher = st.selectbox(
                        "Select Teacher",
                        options=teachers_df['teacher_id'].tolist(),
                        format_func=lambda x: teachers_df[teachers_df['teacher_id'] == x]['name'].iloc[0]
                    )
                with col2:
                    selected_subject = st.selectbox(
                        "Select Subject to Assign",
                        options=unassigned_subjects['subject_id'].tolist(),
                        format_func=lambda x: f"{unassigned_subjects[unassigned_subjects['subject_id'] == x]['subject_code'].iloc[0]} - {unassigned_subjects[unassigned_subjects['subject_id'] == x]['subject_name'].iloc[0]}"
                    )
                if st.button("Assign Subject"):
                    if assign_subject_to_teacher(selected_subject, selected_teacher):
                        st.success("✅ Subject assigned successfully!")
                        st.rerun()
            else:
                if teachers_df.empty:
                    st.info("No teachers available for assignment.")
                if unassigned_subjects.empty:
                    st.info("No unassigned subjects available.")

    # Manage Students (with Faculty Edit)
    elif st.session_state.page == "👨‍🎓 Manage Students":
        st.header("Manage Students")
        st.info("👨‍🏫 Faculty: You can edit all student details including registration number and password.")
        
        students_df = get_all_students()
        if not students_df.empty:
            st.subheader("All Students")
            st.dataframe(students_df[['reg_no', 'name', 'class', 'email', 'phone', 'total_points']],
                        use_container_width=True)
            
            st.markdown("---")
            st.subheader("Edit Student Details (Faculty)")
            
            col1, col2 = st.columns(2)
            with col1:
                student_list = students_df['reg_no'].tolist()
                selected_reg = st.selectbox("Select Student by Registration Number", student_list)
                
                if selected_reg:
                    student_data = students_df[students_df['reg_no'] == selected_reg].iloc[0]
                    student_id = student_data['student_id']
                    
                    with st.form("faculty_edit_student_form"):
                        st.write(f"**Editing: {student_data['name']}**")
                        reg_no = st.text_input("Registration Number", value=student_data['reg_no'])
                        name = st.text_input("Name", value=student_data['name'])
                        class_name = st.text_input("Class", value=student_data['class'])
                        email = st.text_input("Email", value=student_data['email'] if student_data['email'] else "")
                        phone = st.text_input("Phone", value=student_data['phone'] if student_data['phone'] else "")
                        
                        st.subheader("Reset Password (Optional)")
                        new_password = st.text_input("New Password", type="password", 
                                                    help="Leave blank to keep current password")
                        
                        if st.form_submit_button("💾 Update Student"):
                            if reg_no and name and class_name and email:
                                if faculty_edit_student(student_id, reg_no, name, class_name, email, phone, 
                                                      new_password if new_password else None):
                                    st.success("Student updated successfully!")
                                    st.rerun()
                            else:
                                st.error("Please fill all required fields")
            
            with col2:
                if 'selected_reg' in locals() and selected_reg:
                    student_data = students_df[students_df['reg_no'] == selected_reg].iloc[0]
                    st.subheader("Student Details")
                    st.info(f"**Reg No:** {student_data['reg_no']}")
                    st.info(f"**Name:** {student_data['name']}")
                    st.info(f"**Class:** {student_data['class']}")
                    st.info(f"**Email:** {student_data['email']}")
                    st.info(f"**Phone:** {student_data['phone']}")
                    st.info(f"**Total Points:** {student_data['total_points']}")
                    st.info(f"**Current Streak:** {student_data['current_streak']} days")
                    
                    with st.expander("View Registered Subjects"):
                        subjects = get_student_subjects(student_data['student_id'])
                        if not subjects.empty:
                            st.dataframe(subjects[['subject_code', 'subject_name', 'teacher_name']])
                        else:
                            st.info("No subjects registered.")
                    with st.expander("View Student Submissions"):
                        submissions = get_student_submissions(student_data['student_id'])
                        if not submissions.empty:
                            st.dataframe(submissions[['submission_type', 'subject', 'title', 'date', 'grade', 'points_earned']])
                        else:
                            st.info("No submissions yet.")
        else:
            st.info("No students found.")

    # View Submissions with AI data
    elif st.session_state.page == "📂 View Submissions":
        st.header("📂 Student Submissions with AI Analysis")

        submissions_df = get_all_submissions_for_teacher()

        if not submissions_df.empty:
            col1, col2 = st.columns(2)
            with col1:
                class_filter = st.selectbox("Filter by Class", ["All"] + submissions_df['class'].unique().tolist())
            with col2:
                subject_filter = st.selectbox("Filter by Subject", ["All"] + submissions_df['subject'].unique().tolist())

            filtered_df = submissions_df.copy()
            if class_filter != "All":
                filtered_df = filtered_df[filtered_df['class'] == class_filter]
            if subject_filter != "All":
                filtered_df = filtered_df[filtered_df['subject'] == subject_filter]

            st.write(f"**Total Submissions:** {len(filtered_df)}")

            for idx, row in filtered_df.iterrows():
                with st.expander(f"📄 {row['title']} - {row['student_name']} ({row['date']})"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**Student:** {row['student_name']} ({row['reg_no']})")
                        st.write(f"**Class:** {row['class']}")
                        st.write(f"**Subject:** {row['subject']}")
                        st.write(f"**Type:** {row['submission_type']}")
                    with col2:
                        st.write(f"**Date:** {row['date']}")
                    
                    if row['ai_confidence'] > 0:
                        st.markdown("---")
                        st.write("**🤖 AI Analysis:**")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("AI Confidence", f"{row['ai_confidence']*100:.0f}%")
                        with col2:
                            st.metric("Originality", f"{(1-row['plagiarism_score'])*100:.0f}%")
                        if row['ai_feedback']:
                            st.info(f"📝 **AI Feedback:**\n{row['ai_feedback']}")

                    if row['file_path'] and os.path.exists(row['file_path']):
                        st.markdown("---")
                        st.write("**📎 Attached File:**")
                        download_link = get_file_download_link(row['file_path'], row['file_name'] or "file")
                        if download_link:
                            st.markdown(download_link, unsafe_allow_html=True)

                        if st.button(f"👁️ Preview", key=f"teacher_preview_{row['submission_id']}"):
                            preview = get_file_view_link(row['file_path'], row['file_name'], row['file_type'])
                            if preview:
                                st.session_state.teacher_view = preview

                    if st.session_state.get('teacher_view') and st.button("Close Preview"):
                        del st.session_state.teacher_view

                    if st.session_state.get('teacher_view'):
                        st.markdown("---")
                        st.markdown(st.session_state.teacher_view, unsafe_allow_html=True)
        else:
            st.info("No submissions found.")

    # AI Reference Answers Management
    elif st.session_state.page == "🤖 AI Reference Answers":
        st.header("🤖 AI Reference Answers Management")
        if not SKLEARN_AVAILABLE:
            st.warning("⚠️ scikit-learn not installed. AI similarity features will use basic word matching.")
        st.info("Add reference answers to help the AI validate student submissions more accurately.")
        
        tab1, tab2 = st.tabs(["➕ Add Reference Answer", "📋 View Reference Answers"])
        
        with tab1:
            with st.form("add_reference_form"):
                col1, col2 = st.columns(2)
                with col1:
                    subject = st.text_input("Subject*", placeholder="e.g., Database Management")
                    topic = st.text_input("Topic*", placeholder="e.g., SQL Basics")
                with col2:
                    st.info("This reference answer will be used by AI to compare student submissions.")
                
                answer_text = st.text_area("Reference Answer*", height=200, 
                    placeholder="Enter a comprehensive reference answer that demonstrates good quality...")
                
                if st.form_submit_button("Add Reference Answer"):
                    if subject and topic and answer_text:
                        if add_reference_answer(subject, topic, answer_text, teacher_id):
                            st.success("✅ Reference answer added successfully!")
                            st.rerun()
                        else:
                            st.error("Failed to add reference answer.")
                    else:
                        st.error("Please fill all required fields (*)")
        
        with tab2:
            conn = get_db_connection()
            try:
                df = pd.read_sql_query('''
                    SELECT answer_id, subject, topic, answer_text, created_at
                    FROM reference_answers ORDER BY subject, topic
                ''', conn)
                if not df.empty:
                    for _, row in df.iterrows():
                        with st.expander(f"📚 {row['subject']} - {row['topic']}"):
                            st.write(f"**Answer:** {row['answer_text']}")
                            st.write(f"*Added: {row['created_at']}*")
                else:
                    st.info("No reference answers added yet.")
            except:
                st.info("No reference answers found.")
            finally:
                conn.close()

    # Class Analytics
    elif st.session_state.page == "📊 Class Analytics":
        st.header("Class Analytics")
        conn = get_db_connection()
        class_performance = pd.read_sql_query('''
            SELECT class, COUNT(*) as student_count,
                   AVG(total_points) as avg_points,
                   MAX(total_points) as max_points,
                   MIN(total_points) as min_points,
                   SUM(total_points) as total_points
            FROM students GROUP BY class ORDER BY avg_points DESC
        ''', conn)
        if not class_performance.empty:
            st.subheader("📈 Class Performance")
            st.dataframe(class_performance, use_container_width=True)

        st.subheader("🤖 AI Performance Metrics")
        ai_metrics = pd.read_sql_query('''
            SELECT 
                AVG(ai_confidence) as avg_confidence,
                AVG(plagiarism_score) as avg_plagiarism,
                COUNT(*) as total_ai_graded
            FROM submissions WHERE ai_confidence > 0
        ''', conn)
        if not ai_metrics.empty and ai_metrics['total_ai_graded'][0] > 0:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Avg AI Confidence", f"{ai_metrics['avg_confidence'][0]*100:.0f}%")
            with col2:
                st.metric("Avg Originality", f"{(1-ai_metrics['avg_plagiarism'][0])*100:.0f}%")
            with col3:
                st.metric("AI-Graded Submissions", ai_metrics['total_ai_graded'][0])

        st.subheader("📚 Subject-wise Student Distribution")
        subject_stats = pd.read_sql_query('''
            SELECT s.subject_code, s.subject_name, s.class,
                   COUNT(ss.student_id) as student_count,
                   t.name as teacher_name
            FROM subjects s
            LEFT JOIN student_subjects ss ON s.subject_id = ss.subject_id
            LEFT JOIN teachers t ON s.teacher_id = t.teacher_id
            GROUP BY s.subject_id
            ORDER BY student_count DESC
        ''', conn)
        if not subject_stats.empty:
            st.dataframe(subject_stats, use_container_width=True)
        conn.close()

    # Leaderboard
    elif st.session_state.page == "🏆 Leaderboard":
        st.header("Teacher View: Student Leaderboard")
        leaderboard = get_leaderboard(50)
        if not leaderboard.empty:
            st.dataframe(leaderboard, use_container_width=True)
        else:
            st.info("No students in leaderboard.")

    # Edit Profile
    elif st.session_state.page == "👤 Edit Profile":
        st.header("Edit Profile")
        with st.form("edit_teacher_profile_form"):
            name = st.text_input("Full Name", value=teacher_name)
            email = st.text_input("Email", value=teacher_email)
            department = st.text_input("Department", value=teacher_dept if teacher_dept else "")
            st.subheader("Change Password (Optional)")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            if st.form_submit_button("Update Profile"):
                if new_password:
                    if new_password == confirm_password:
                        if update_teacher_profile(teacher_id, name, email, department, new_password):
                            st.success("✅ Profile updated successfully! Please login again.")
                            st.session_state.current_teacher = None
                            st.session_state.user_role = None
                            st.session_state.page = "Welcome"
                            st.rerun()
                    else:
                        st.error("Passwords do not match!")
                else:
                    if update_teacher_profile(teacher_id, name, email, department):
                        st.success("✅ Profile updated successfully!")
                        teacher = list(teacher)
                        teacher[2] = name
                        teacher[3] = email
                        teacher[5] = department
                        st.session_state.current_teacher = tuple(teacher)
                        st.rerun()

    # Manage System
    elif st.session_state.page == "⚙️ Manage System":
        st.header("System Management")
        tab1, tab2 = st.tabs(["📊 System Stats", "⚙️ Settings"])
        with tab1:
            st.subheader("System Statistics")
            conn = get_db_connection()
            stats_data = {"Metric": [], "Value": []}
            try:
                stats_data["Metric"].append("Total Students")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM students", conn).iloc[0,0] or 0)
                stats_data["Metric"].append("Total Teachers")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM teachers", conn).iloc[0,0] or 0)
                stats_data["Metric"].append("Total Subjects")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM subjects", conn).iloc[0,0] or 0)
                stats_data["Metric"].append("Total Submissions")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM submissions", conn).iloc[0,0] or 0)
                stats_data["Metric"].append("Total Activities")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM activities", conn).iloc[0,0] or 0)
                stats_data["Metric"].append("Total Points Awarded")
                stats_data["Value"].append(pd.read_sql_query("SELECT SUM(total_points) FROM students", conn).iloc[0,0] or 0)
                stats_data["Metric"].append("AI-Graded Submissions")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM submissions WHERE ai_confidence > 0", conn).iloc[0,0] or 0)
            except:
                pass
            finally:
                conn.close()
            if stats_data["Metric"]:
                stats_df = pd.DataFrame(stats_data)
                st.dataframe(stats_df, use_container_width=True)
            st.info("📌 Data is automatically cleaned - only last 6 months of submissions and activities are kept.")
        with tab2:
            st.subheader("System Settings")
            st.success("✅ Auto-grading with AI is enabled")
            st.write("**Current Points System:**")
            st.write("- Daily Homework: 5 points (AI-adjusted)")
            st.write("- Seminar: 10 points (AI-adjusted)")
            st.write("- Project: 15 points (AI-adjusted)")
            st.write("- Extra Activity: 25 points (AI-adjusted)")
            st.write("- Weekly Assignment: 15 points (AI-adjusted)")
            st.write("- Monthly Assignment: 30 points (AI-adjusted)")
            st.write("- Research Paper: 25 points (AI-adjusted)")
            st.write("- Lab Report: 8 points (AI-adjusted)")

st.markdown("---")
st.markdown("""
<div style='text-align: center; padding: 15px 0; margin-top: 20px; border-top: 1px solid #ddd;'>
    <p style='margin: 5px 0; font-weight: bold;'>Continuous Student Evaluation & Monitoring System v4.0</p>
    <p style='margin: 3px 0;'>Design and Maintained by: S P Sajjan, Assistant Professor, GFGCW, Jamkhandi</p>
    <p style='margin: 3px 0;'>📧 Contact: sajjanvsl@gmail.com | 📞 Help Desk: 9008802403</p>
    <p style='margin: 5px 0;'>✅ AI-Powered Validation | 📚 Faculty Edit | 🔐 Forgot Password | 📂 File Upload/Download/View</p>
    <p style='margin: 3px 0; color: #666; font-size: 0.9em;'>📅 Data retention: 6 months (automatic cleanup)</p>
</div>
""", unsafe_allow_html=True)
