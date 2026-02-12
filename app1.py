import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import hashlib

st.set_page_config(page_title="Student Evaluation System", page_icon="📚", layout="wide", initial_sidebar_state="expanded")

if 'current_student' not in st.session_state:
    st.session_state.current_student = None
if 'current_teacher' not in st.session_state:
    st.session_state.current_teacher = None
if 'user_role' not in st.session_state:
    st.session_state.user_role = None

def init_database():
    """Initialize database with proper schema"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    
    # Check if tables exist and alter them if needed
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='submissions'")
    table_exists = c.fetchone()
    
    if table_exists:
        # Check if auto_graded column exists
        c.execute("PRAGMA table_info(submissions)")
        columns = [column[1] for column in c.fetchall()]
        if 'auto_graded' not in columns:
            c.execute('ALTER TABLE submissions ADD COLUMN auto_graded INTEGER DEFAULT 0')
    else:
        # Create submissions table with all columns
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
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                graded_at TIMESTAMP,
                graded_by INTEGER,
                auto_graded INTEGER DEFAULT 0
            )
        ''')
    
    # Check and create other tables if they don't exist
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='students'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE students (
                student_id INTEGER PRIMARY KEY AUTOINCREMENT,
                reg_no TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                class TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                total_points INTEGER DEFAULT 0,
                current_streak INTEGER DEFAULT 0,
                best_streak INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active DATE
            )
        ''')
    
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='teachers'")
    if not c.fetchone():
        c.execute('''
            CREATE TABLE teachers (
                teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
                teacher_code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                department TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
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
                remarks TEXT
            )
        ''')
    
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
    
    # Create indexes if they don't exist
    try:
        c.execute('CREATE INDEX IF NOT EXISTS idx_submissions_date ON submissions(date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_activities_date ON activities(date)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_submissions_student ON submissions(student_id)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_activities_student ON activities(student_id)')
    except:
        pass
    
    conn.commit()
    conn.close()

def cleanup_old_data():
    """Delete data older than 6 months"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    six_months_ago = (datetime.now() - timedelta(days=180)).strftime('%Y-%m-%d')
    
    try:
        # Delete old submissions
        c.execute('DELETE FROM submissions WHERE date < ?', (six_months_ago,))
        # Delete old activities
        c.execute('DELETE FROM activities WHERE date < ?', (six_months_ago,))
        # Keep only last 6 months of daily activity
        c.execute('DELETE FROM daily_activity WHERE activity_date < ?', (six_months_ago,))
        conn.commit()
    except Exception as e:
        print(f"Cleanup error: {e}")
    finally:
        conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def add_student(reg_no, name, class_name, email=None, phone=None):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO students (reg_no, name, class, email, phone, last_active) VALUES (?, ?, ?, ?, ?, DATE("now"))', 
                 (reg_no, name, class_name, email, phone))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def update_student(student_id, name, class_name, email, phone):
    """Edit student details"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('UPDATE students SET name = ?, class = ?, email = ?, phone = ? WHERE student_id = ?',
                 (name, class_name, email, phone, student_id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error updating student: {str(e)}")
        return False
    finally:
        conn.close()

def delete_student(student_id):
    """Delete student and all their records"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        # Delete all related records first
        c.execute('DELETE FROM submissions WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM activities WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM daily_activity WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM rewards WHERE student_id = ?', (student_id,))
        c.execute('DELETE FROM point_transactions WHERE student_id = ?', (student_id,))
        # Delete the student
        c.execute('DELETE FROM students WHERE student_id = ?', (student_id,))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error deleting student: {str(e)}")
        return False
    finally:
        conn.close()

def register_teacher(teacher_code, name, email, password, department):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        password_hash = hash_password(password)
        c.execute('INSERT INTO teachers (teacher_code, name, email, password_hash, department) VALUES (?, ?, ?, ?, ?)',
                 (teacher_code, name, email, password_hash, department))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def authenticate_teacher(email, password):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    c.execute("SELECT * FROM teachers WHERE email = ?", (email,))
    teacher = c.fetchone()
    conn.close()
    if teacher and verify_password(password, teacher[4]):
        return teacher
    return None

def get_student(reg_no):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE reg_no = ?", (reg_no,))
    student = c.fetchone()
    conn.close()
    return student

def get_student_by_id(student_id):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE student_id = ?", (student_id,))
    student = c.fetchone()
    conn.close()
    return student

# AUTO-GRADING SYSTEM - UPDATED POINTS
def get_auto_grade_points(submission_type):
    """Return automatic points for different submission types"""
    points_mapping = {
        'Daily Homework': 5,
        'Weekly Assignment': 15,
        'Monthly Assignment': 30,
        'Seminar': 10,
        'Project': 15,
        'Research Paper': 25,
        'Lab Report': 8,
        'Extra Activity': 25
    }
    return points_mapping.get(submission_type, 5)

def get_auto_grade_letter(submission_type):
    """Return automatic grade for different submission types"""
    grade_mapping = {
        'Daily Homework': 'A',
        'Weekly Assignment': 'A',
        'Monthly Assignment': 'A+',
        'Seminar': 'A',
        'Project': 'A+',
        'Research Paper': 'A+',
        'Lab Report': 'A',
        'Extra Activity': 'A+'
    }
    return grade_mapping.get(submission_type, 'A')

def add_submission(student_id, submission_type, subject, title, description, date, file_path=None):
    """Add submission with auto-grading"""
    points = get_auto_grade_points(submission_type)
    grade = get_auto_grade_letter(submission_type)
    
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO submissions (
                student_id, submission_type, subject, title, description, 
                date, file_path, max_points, points_earned, grade, 
                status, auto_graded, graded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Graded', 1, CURRENT_TIMESTAMP)
        ''', (student_id, submission_type, subject, title, description, 
              date, file_path, points, points, grade))
        
        submission_id = c.lastrowid
        
        # Update student points and streak
        c.execute('UPDATE students SET total_points = total_points + ?, last_active = DATE("now") WHERE student_id = ?', 
                 (points, student_id))
        
        # Update streak
        c.execute('SELECT last_active FROM students WHERE student_id = ?', (student_id,))
        result = c.fetchone()
        if result:
            last_active = result[0]
            
            if last_active == str(date):
                c.execute('UPDATE students SET current_streak = current_streak + 1 WHERE student_id = ?', (student_id,))
                c.execute('UPDATE students SET best_streak = MAX(best_streak, current_streak) WHERE student_id = ?', (student_id,))
            else:
                c.execute('UPDATE students SET current_streak = 1 WHERE student_id = ?', (student_id,))
        
        # Add point transaction
        c.execute('''
            INSERT INTO point_transactions (student_id, transaction_type, points, description, reference_id) 
            VALUES (?, 'Auto Graded', ?, ?, ?)
        ''', (student_id, points, f"Auto-graded: {submission_type}", submission_id))
        
        # Update daily activity
        update_daily_activity(student_id, date, 'submission', points)
        
        conn.commit()
        return submission_id
    except Exception as e:
        st.error(f"Error adding submission: {str(e)}")
        return None
    finally:
        conn.close()

def add_extra_activity(student_id, activity_type, topic, date, duration, remarks):
    """Add extra curricular activity with points"""
    points = 25
    
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('''
            INSERT INTO activities (student_id, activity_type, topic, date, duration_minutes, remarks, points_earned) 
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (student_id, 'Extra Activity', topic, date, duration, remarks, points))
        
        # Update student points
        c.execute('UPDATE students SET total_points = total_points + ? WHERE student_id = ?', (points, student_id))
        
        # Add point transaction
        c.execute('''
            INSERT INTO point_transactions (student_id, transaction_type, points, description) 
            VALUES (?, 'Extra Activity', ?, ?)
        ''', (student_id, points, f"Extra Activity: {topic}"))
        
        # Update daily activity
        update_daily_activity(student_id, date, 'activity', points)
        
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error adding activity: {str(e)}")
        return False
    finally:
        conn.close()

def update_daily_activity(student_id, date, activity_type, points=0):
    conn = sqlite3.connect('student_evaluation.db')
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
    except Exception as e:
        pass
    finally:
        conn.close()

def get_leaderboard(limit=20, class_filter=None):
    conn = sqlite3.connect('student_evaluation.db')
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
    except Exception as e:
        return pd.DataFrame()
    finally:
        conn.close()

def get_daily_activity(student_id, days=7):
    conn = sqlite3.connect('student_evaluation.db')
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
    conn = sqlite3.connect('student_evaluation.db')
    try:
        c = conn.cursor()
        c.execute('''
            SELECT COUNT(*) as total_submissions, SUM(points_earned) as total_points_earned 
            FROM submissions WHERE student_id = ?
        ''', (student_id,))
        submissions_data = c.fetchone() or (0, 0)
        
        c.execute('''
            SELECT COUNT(*) as total_activities, SUM(points_earned) as activity_points 
            FROM activities WHERE student_id = ?
        ''', (student_id,))
        activities_data = c.fetchone() or (0, 0)
        
        return {
            'total_submissions': submissions_data[0] or 0,
            'submission_points': submissions_data[1] or 0,
            'total_activities': activities_data[0] or 0,
            'activity_points': activities_data[1] or 0
        }
    except:
        return {'total_submissions': 0, 'submission_points': 0, 'total_activities': 0, 'activity_points': 0}
    finally:
        conn.close()

def get_all_students():
    """Get all students for teacher view"""
    conn = sqlite3.connect('student_evaluation.db')
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
    """Get all submissions for a student"""
    conn = sqlite3.connect('student_evaluation.db')
    try:
        df = pd.read_sql_query('''
            SELECT submission_id, submission_type, subject, title, date, status, 
                   points_earned, max_points, grade, teacher_feedback, graded_at 
            FROM submissions WHERE student_id = ? ORDER BY date DESC
        ''', conn, params=(student_id,))
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_student_activities(student_id):
    """Get all activities for a student"""
    conn = sqlite3.connect('student_evaluation.db')
    try:
        df = pd.read_sql_query('''
            SELECT activity_type, topic, date, duration_minutes, points_earned, remarks 
            FROM activities WHERE student_id = ? ORDER BY date DESC
        ''', conn, params=(student_id,))
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

# Initialize database and cleanup old data
init_database()
cleanup_old_data()
Path("uploads").mkdir(exist_ok=True)

# ==================== STREAMLIT UI CODE ====================
st.title("📚 Continuous Student Evaluation & Monitoring System")
st.markdown("---")

with st.sidebar:
    if st.session_state.user_role:
        if st.session_state.user_role == "student":
            student = st.session_state.current_student
            if student:
                st.header("🎓 Student Info")
                st.success(f"**{student[2]}**")
                st.info(f"Reg No: {student[1]}")
                st.info(f"Class: {student[3]}")
                total_points = student[6] if len(student) > 6 else 0
                current_streak = student[7] if len(student) > 7 else 0
                st.info(f"Points: {total_points} 🏆")
                st.info(f"Streak: {current_streak} days 🔥")
            if st.button("Logout"):
                st.session_state.current_student = None
                st.session_state.user_role = None
                st.rerun()
        elif st.session_state.user_role == "teacher":
            teacher = st.session_state.current_teacher
            if teacher:
                st.header("👨‍🏫 Teacher Info")
                st.success(f"**Prof. {teacher[2]}**")
                dept = teacher[5] if len(teacher) > 5 else "N/A"
                st.info(f"Dept: {dept}")
            if st.button("Logout"):
                st.session_state.current_teacher = None
                st.session_state.user_role = None
                st.rerun()
    else:
        st.header("🔐 Login")
        login_option = st.radio("Login as:", ["Student", "Teacher"])
        if login_option == "Student":
            reg_no = st.text_input("Registration Number")
            if st.button("Student Login"):
                if reg_no:
                    student = get_student(reg_no)
                    if student:
                        st.session_state.current_student = student
                        st.session_state.user_role = "student"
                        st.success(f"Welcome, {student[2]}!")
                        st.rerun()
                    else:
                        st.error("Registration number not found!")
        else:
            col1, col2 = st.columns(2)
            with col1:
                email = st.text_input("Email")
            with col2:
                password = st.text_input("Password", type="password")
            if st.button("Teacher Login"):
                if email and password:
                    teacher = authenticate_teacher(email, password)
                    if teacher:
                        st.session_state.current_teacher = teacher
                        st.session_state.user_role = "teacher"
                        st.success(f"Welcome, Professor {teacher[2]}!")
                        st.rerun()
                    else:
                        st.error("Invalid credentials!")
    
    st.markdown("---")
    if st.session_state.user_role:
        st.header("📱 Navigation")
        if st.session_state.user_role == "student":
            page = st.radio("Go to:", ["🏠 Dashboard", "➕ New Submission", "➕ Extra Activity", "📋 My Submissions", "📈 Daily Activity", "🏆 Leaderboard", "🎁 Rewards"])
        else:
            page = st.radio("Go to:", ["🏠 Teacher Dashboard", "👨‍🎓 Manage Students", "📊 Class Analytics", "🏆 Leaderboard", "⚙️ Manage System"])
    else:
        page = "Welcome"

if page == "Welcome":
    st.header("Welcome to Student Evaluation System")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("For Students")
        st.write("- Submit daily homework and assignments")
        st.write("- **Auto-grading**: Earn points instantly!")
        st.write("- Daily Homework: 5 points")
        st.write("- Seminar: 10 points")
        st.write("- Project: 15 points")
        st.write("- Extra Activity: 25 points")
        st.write("- Track your learning progress")
        st.write("- Compete on leaderboard")
        
        with st.expander("New Student Registration"):
            with st.form("new_student_form"):
                reg_no = st.text_input("Registration Number*")
                name = st.text_input("Full Name*")
                class_name = st.text_input("Class*")
                email = st.text_input("Email")
                phone = st.text_input("Phone")
                if st.form_submit_button("Register"):
                    if reg_no and name and class_name:
                        if add_student(reg_no, name, class_name, email, phone):
                            st.success("Registration successful! Please login.")
                    else:
                        st.error("Please fill required fields (*)")
    with col2:
        st.subheader("For Teachers")
        st.write("- Manage student records")
        st.write("- Edit/Delete student details")
        st.write("- Monitor class performance")
        st.write("- View student submissions")
        st.write("- Generate analytics")
        
        with st.expander("Teacher Registration"):
            with st.form("teacher_reg_form"):
                t_code = st.text_input("Teacher Code*")
                t_name = st.text_input("Full Name*")
                t_email = st.text_input("Email*")
                t_password = st.text_input("Password*", type="password")
                t_dept = st.text_input("Department*")
                if st.form_submit_button("Register as Teacher"):
                    if all([t_code, t_name, t_email, t_password, t_dept]):
                        if register_teacher(t_code, t_name, t_email, t_password, t_dept):
                            st.success("Registration successful! Please login.")
                        else:
                            st.error("Teacher code or email already exists!")
                    else:
                        st.error("Please fill all fields")

elif st.session_state.user_role == "student":
    student = st.session_state.current_student
    if not student:
        st.error("Please login first!")
        st.stop()
    
    student_id = student[0]
    
    if page == "🏠 Dashboard":
        st.header(f"Welcome back, {student[2]}! 👋")
        
        total_points = student[6] if len(student) > 6 else 0
        current_streak = student[7] if len(student) > 7 else 0
        best_streak = student[8] if len(student) > 8 else 0
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Points", total_points, "🏆")
        with col2:
            st.metric("Current Streak", f"{current_streak} days", "🔥")
        with col3:
            st.metric("Best Streak", f"{best_streak} days", "⭐")
        with col4:
            conn = sqlite3.connect('student_evaluation.db')
            c = conn.cursor()
            c.execute('SELECT COUNT(*) FROM submissions WHERE student_id = ?', (student_id,))
            total_subs = c.fetchone()[0] or 0
            conn.close()
            st.metric("Total Submissions", total_subs, "📝")
        
        st.markdown("---")
        
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
    
    elif page == "➕ New Submission":
        st.header("New Submission - Auto Graded!")
        st.info("✅ Your submissions will be automatically graded and points added instantly!")
        
        with st.form("submission_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                submission_type = st.selectbox("Submission Type*", 
                    ["Daily Homework", "Weekly Assignment", "Monthly Assignment", 
                     "Seminar", "Project", "Research Paper", "Lab Report"])
                subject = st.text_input("Subject*")
                title = st.text_input("Title*")
                date = st.date_input("Date*", datetime.now().date())
            
            with col2:
                points = get_auto_grade_points(submission_type)
                grade = get_auto_grade_letter(submission_type)
                st.success(f"📊 You will earn: **{points} points**")
                st.info(f"📝 Auto Grade: **{grade}**")
            
            description = st.text_area("Description*", height=150, 
                placeholder="Describe your submission...")
            
            uploaded_file = st.file_uploader("Upload File (optional)", 
                type=['pdf', 'docx', 'txt', 'jpg', 'png'])
            
            submitted = st.form_submit_button("Submit", type="primary")
            
            if submitted:
                if subject and title and description:
                    file_path = None
                    if uploaded_file:
                        upload_dir = Path("uploads") / student[1] / submission_type.replace(" ", "_")
                        upload_dir.mkdir(parents=True, exist_ok=True)
                        file_path = str(upload_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uploaded_file.name}")
                        with open(file_path, "wb") as f:
                            f.write(uploaded_file.getbuffer())
                    
                    submission_id = add_submission(student_id, submission_type, 
                                                  subject, title, description, 
                                                  date, file_path)
                    if submission_id:
                        st.success(f"✅ Submission graded automatically! You earned {points} points!")
                        st.balloons()
                        st.info(f"📝 Grade: {grade} | Points: {points}")
                    else:
                        st.error("Failed to record submission.")
                else:
                    st.error("Please fill all required fields (*)")
    
    elif page == "➕ Extra Activity":
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
            
            if st.form_submit_button("Add Activity"):
                if topic:
                    if add_extra_activity(student_id, activity_type, topic, date, duration, remarks):
                        st.success("✅ Activity added! You earned 25 points!")
                        st.balloons()
                        st.rerun()
                else:
                    st.error("Please enter topic")
    
    elif page == "📋 My Submissions":
        st.header("My Submissions")
        
        df = get_student_submissions(student_id)
        
        if not df.empty:
            total_subs = len(df)
            total_points = df['points_earned'].sum()
            avg_points = df['points_earned'].mean()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Submissions", total_subs)
            with col2:
                st.metric("Total Points", total_points)
            with col3:
                st.metric("Avg Points", f"{avg_points:.1f}")
            
            st.dataframe(df[['submission_id', 'submission_type', 'subject', 'title', 
                            'date', 'grade', 'points_earned', 'max_points']], 
                        use_container_width=True)
        else:
            st.info("No submissions found.")
    
    elif page == "📈 Daily Activity":
        st.header("Daily Activity Tracker")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", datetime.now().date() - timedelta(days=30))
        with col2:
            end_date = st.date_input("End Date", datetime.now().date())
        
        conn = sqlite3.connect('student_evaluation.db')
        df = pd.read_sql_query(
            'SELECT activity_date, submission_count, activity_count, total_points_earned FROM daily_activity WHERE student_id = ? AND activity_date BETWEEN ? AND ? ORDER BY activity_date DESC', 
            conn, params=(student_id, start_date, end_date))
        conn.close()
        
        if not df.empty:
            total_days = len(df)
            active_days = len(df[df['total_points_earned'] > 0])
            total_points = df['total_points_earned'].sum()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Days", total_days)
            with col2:
                st.metric("Active Days", active_days)
            with col3:
                st.metric("Total Points", total_points)
            
            st.subheader("📋 Daily Log")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No activity recorded for the selected period.")
    
    elif page == "🏆 Leaderboard":
        st.header("🏆 Student Leaderboard")
        
        col1, col2 = st.columns(2)
        with col1:
            conn = sqlite3.connect('student_evaluation.db')
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
            
            current_rank = leaderboard[leaderboard['reg_no'] == student[1]]['Rank'].values
            if len(current_rank) > 0:
                student_points = student[6] if len(student) > 6 else 0
                st.info(f"🏅 Your current rank: **#{current_rank[0]}** with **{student_points} points**")
        else:
            st.info("No students found in the leaderboard.")
    
    elif page == "🎁 Rewards":
        st.header("🎁 Reward Store")
        
        student_points = student[6] if len(student) > 6 else 0
        st.info(f"💰 You have **{student_points} points** available")
        
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
                
                if student_points >= reward['cost']:
                    if st.button(f"Claim {reward['name']}", key=f"claim_{i}"):
                        conn = sqlite3.connect('student_evaluation.db')
                        c = conn.cursor()
                        c.execute('UPDATE students SET total_points = total_points - ? WHERE student_id = ?', (reward['cost'], student_id))
                        c.execute('INSERT INTO rewards (student_id, reward_type, points_cost, reward_date, status) VALUES (?, ?, ?, DATE("now"), "Claimed")', (student_id, reward['name'], reward['cost']))
                        c.execute('INSERT INTO point_transactions (student_id, transaction_type, points, description) VALUES (?, "Reward Claimed", ?, ?)', (student_id, -reward['cost'], f"Claimed: {reward['name']}"))
                        conn.commit()
                        conn.close()
                        st.success(f"🎉 You claimed {reward['name']}!")
                        st.rerun()
                else:
                    st.warning(f"Need {reward['cost'] - student_points} more points")
                st.markdown("---")

elif st.session_state.user_role == "teacher":
    teacher = st.session_state.current_teacher
    if not teacher:
        st.error("Please login first!")
        st.stop()
    
    teacher_id = teacher[0]
    
    if page == "🏠 Teacher Dashboard":
        st.header(f"Teacher Dashboard 👨‍🏫")
        
        conn = sqlite3.connect('student_evaluation.db')
        try:
            total_students = pd.read_sql_query("SELECT COUNT(*) FROM students", conn).iloc[0,0] or 0
            total_submissions = pd.read_sql_query("SELECT COUNT(*) FROM submissions", conn).iloc[0,0] or 0
            total_points = pd.read_sql_query("SELECT SUM(total_points) FROM students", conn).iloc[0,0] or 0
        except:
            total_students = 0
            total_submissions = 0
            total_points = 0
        finally:
            conn.close()
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Students", total_students)
        with col2:
            st.metric("Total Submissions", total_submissions)
        with col3:
            st.metric("Total Points Awarded", total_points)
        
        st.markdown("---")
        
        st.subheader("📊 Class Distribution")
        conn = sqlite3.connect('student_evaluation.db')
        class_dist = pd.read_sql_query("SELECT class, COUNT(*) as count FROM students GROUP BY class", conn)
        conn.close()
        if not class_dist.empty:
            st.dataframe(class_dist, use_container_width=True)
    
    elif page == "👨‍🎓 Manage Students":
        st.header("Manage Students")
        
        students_df = get_all_students()
        
        if not students_df.empty:
            st.subheader("All Students")
            st.dataframe(students_df[['reg_no', 'name', 'class', 'email', 'phone', 'total_points']], 
                        use_container_width=True)
            
            st.markdown("---")
            st.subheader("Edit/Delete Student")
            
            col1, col2 = st.columns(2)
            with col1:
                student_list = students_df['reg_no'].tolist()
                selected_reg = st.selectbox("Select Student by Registration Number", student_list)
                
                if selected_reg:
                    student_data = students_df[students_df['reg_no'] == selected_reg].iloc[0]
                    student_id = student_data['student_id']
                    
                    with st.form("edit_student_form"):
                        st.write(f"**Editing: {student_data['name']}**")
                        name = st.text_input("Name", value=student_data['name'])
                        class_name = st.text_input("Class", value=student_data['class'])
                        email = st.text_input("Email", value=student_data['email'] if student_data['email'] else "")
                        phone = st.text_input("Phone", value=student_data['phone'] if student_data['phone'] else "")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.form_submit_button("💾 Update Student"):
                                if update_student(student_id, name, class_name, email, phone):
                                    st.success("Student updated successfully!")
                                    st.rerun()
                        with col2:
                            if st.form_submit_button("🗑️ Delete Student"):
                                # Simple confirmation
                                if delete_student(student_id):
                                    st.success("Student deleted successfully!")
                                    st.rerun()
            
            with col2:
                if 'selected_reg' in locals() and selected_reg:
                    student_data = students_df[students_df['reg_no'] == selected_reg].iloc[0]
                    st.subheader("Student Details")
                    st.info(f"**Reg No:** {student_data['reg_no']}")
                    st.info(f"**Name:** {student_data['name']}")
                    st.info(f"**Class:** {student_data['class']}")
                    st.info(f"**Total Points:** {student_data['total_points']}")
                    st.info(f"**Current Streak:** {student_data['current_streak']} days")
                    
                    # View student submissions
                    with st.expander("View Student Submissions"):
                        submissions = get_student_submissions(student_data['student_id'])
                        if not submissions.empty:
                            st.dataframe(submissions[['submission_type', 'subject', 'title', 'date', 'grade', 'points_earned']])
                        else:
                            st.info("No submissions yet.")
        else:
            st.info("No students found.")
    
    elif page == "📊 Class Analytics":
        st.header("Class Analytics")
        
        conn = sqlite3.connect('student_evaluation.db')
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
        
        conn.close()
    
    elif page == "🏆 Leaderboard":
        st.header("Teacher View: Student Leaderboard")
        
        leaderboard = get_leaderboard(50)
        if not leaderboard.empty:
            st.dataframe(leaderboard, use_container_width=True)
        else:
            st.info("No students in leaderboard.")
    
    elif page == "⚙️ Manage System":
        st.header("System Management")
        
        tab1, tab2 = st.tabs(["📊 System Stats", "⚙️ Settings"])
        
        with tab1:
            st.subheader("System Statistics")
            
            conn = sqlite3.connect('student_evaluation.db')
            stats_data = {"Metric": [], "Value": []}
            
            try:
                stats_data["Metric"].append("Total Students")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM students", conn).iloc[0,0] or 0)
                
                stats_data["Metric"].append("Total Teachers")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM teachers", conn).iloc[0,0] or 0)
                
                stats_data["Metric"].append("Total Submissions")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM submissions", conn).iloc[0,0] or 0)
                
                stats_data["Metric"].append("Total Activities")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM activities", conn).iloc[0,0] or 0)
                
                stats_data["Metric"].append("Total Points Awarded")
                stats_data["Value"].append(pd.read_sql_query("SELECT SUM(total_points) FROM students", conn).iloc[0,0] or 0)
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
            st.success("✅ Auto-grading is enabled")
            st.write("**Current Points System:**")
            st.write("- Daily Homework: 5 points")
            st.write("- Seminar: 10 points")
            st.write("- Project: 15 points")
            st.write("- Extra Activity: 25 points")
            st.write("- Weekly Assignment: 15 points")
            st.write("- Monthly Assignment: 30 points")
            st.write("- Research Paper: 25 points")
            st.write("- Lab Report: 8 points")

st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>Continuous Student Evaluation & Monitoring System v2.0</p>
    <p>Design and Maintained by: S P Sajjan, Assistant Professor, GFGCW, Jamkhandi</p>
    <p>📧 Contact: sajjanvsl@gmail.com | 📞 Help Desk: 9008802403</p>
    <p>✅ Auto-grading enabled | 📅 Data retention: 6 months (automatic cleanup)</p>
</div>
""", unsafe_allow_html=True)
