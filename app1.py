import streamlit as st
import pandas as pd
import sqlite3
import datetime
from pathlib import Path
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import hashlib
import os

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
    
    # Create students table with all columns
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
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
    
    # Check and add missing columns one by one
    c.execute("PRAGMA table_info(students)")
    columns = [col[1] for col in c.fetchall()]
    
    # Add missing columns one by one without problematic defaults
    if 'total_points' not in columns:
        try:
            c.execute("ALTER TABLE students ADD COLUMN total_points INTEGER DEFAULT 0")
        except:
            pass
    
    if 'current_streak' not in columns:
        try:
            c.execute("ALTER TABLE students ADD COLUMN current_streak INTEGER DEFAULT 0")
        except:
            pass
    
    if 'best_streak' not in columns:
        try:
            c.execute("ALTER TABLE students ADD COLUMN best_streak INTEGER DEFAULT 0")
        except:
            pass
    
    if 'last_active' not in columns:
        try:
            c.execute("ALTER TABLE students ADD COLUMN last_active DATE")
            # Update existing rows with current date
            c.execute("UPDATE students SET last_active = DATE('now') WHERE last_active IS NULL")
        except:
            pass
    
    # Create teachers table
    c.execute('''
        CREATE TABLE IF NOT EXISTS teachers (
            teacher_id INTEGER PRIMARY KEY AUTOINCREMENT,
            teacher_code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT,
            department TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create submissions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
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
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    
    # Create activities table
    c.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            activity_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            activity_type TEXT NOT NULL,
            topic TEXT,
            date DATE NOT NULL,
            duration_minutes INTEGER,
            points_earned INTEGER DEFAULT 0,
            status TEXT DEFAULT 'Completed',
            remarks TEXT,
            FOREIGN KEY (student_id) REFERENCES students (student_id)
        )
    ''')
    
    # Create daily activity table
    c.execute('''
        CREATE TABLE IF NOT EXISTS daily_activity (
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
    
    # Create rewards table
    c.execute('''
        CREATE TABLE IF NOT EXISTS rewards (
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
    
    # Create point transactions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS point_transactions (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            transaction_type TEXT NOT NULL,
            points INTEGER NOT NULL,
            description TEXT,
            reference_id INTEGER,
            transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def add_student(reg_no, name, class_name, email=None, phone=None):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO students (reg_no, name, class, email, phone, last_active) VALUES (?, ?, ?, ?, ?, DATE("now"))', (reg_no, name, class_name, email, phone))
        conn.commit()
        st.success(f"Student {name} registered successfully!")
        return True
    except sqlite3.IntegrityError:
        st.error("Registration number already exists!")
        return False
    finally:
        conn.close()

def register_teacher(teacher_code, name, email, password, department):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        password_hash = hash_password(password)
        c.execute('INSERT INTO teachers (teacher_code, name, email, password_hash, department) VALUES (?, ?, ?, ?, ?)', (teacher_code, name, email, password_hash, department))
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

def add_submission(student_id, submission_type, subject, title, description, date, file_path=None):
    default_points = {'Daily Homework': 10, 'Weekly Assignment': 25, 'Monthly Assignment': 50, 'Seminar': 30, 'Project': 100, 'Research Paper': 75, 'Lab Report': 20}
    max_points = default_points.get(submission_type, 10)
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO submissions (student_id, submission_type, subject, title, description, date, file_path, max_points) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (student_id, submission_type, subject, title, description, date, file_path, max_points))
        submission_id = c.lastrowid
        c.execute('UPDATE students SET last_active = DATE("now") WHERE student_id = ?', (student_id,))
        conn.commit()
        update_daily_activity(student_id, date, 'submission')
        return submission_id
    except Exception as e:
        st.error(f"Error adding submission: {str(e)}")
        return None
    finally:
        conn.close()

def add_activity(student_id, activity_type, topic, date, duration, remarks):
    activity_points = {'Workshop': 20, 'Sports': 15, 'Cultural': 25, 'Competition': 30, 'Volunteer': 25, 'Club Meeting': 10, 'Guest Lecture': 20}
    points = activity_points.get(activity_type, 10)
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('INSERT INTO activities (student_id, activity_type, topic, date, duration_minutes, remarks, points_earned) VALUES (?, ?, ?, ?, ?, ?, ?)', (student_id, activity_type, topic, date, duration, remarks, points))
        update_daily_activity(student_id, date, 'activity', points)
        conn.commit()
    except Exception as e:
        st.error(f"Error adding activity: {str(e)}")
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
                c.execute('UPDATE daily_activity SET submission_count = submission_count + 1, total_points_earned = total_points_earned + ? WHERE student_id = ? AND activity_date = ?', (points, student_id, date))
            else:
                c.execute('UPDATE daily_activity SET activity_count = activity_count + 1, total_points_earned = total_points_earned + ? WHERE student_id = ? AND activity_date = ?', (points, student_id, date))
        else:
            if activity_type == 'submission':
                c.execute('INSERT INTO daily_activity (student_id, activity_date, submission_count, total_points_earned) VALUES (?, ?, 1, ?)', (student_id, date, points))
            else:
                c.execute('INSERT INTO daily_activity (student_id, activity_date, activity_count, total_points_earned) VALUES (?, ?, 1, ?)', (student_id, date, points))
        update_streak(student_id)
        conn.commit()
    except Exception as e:
        pass  # Silently fail for now
    finally:
        conn.close()

def update_streak(student_id):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('SELECT COUNT(DISTINCT activity_date) FROM daily_activity WHERE student_id = ? AND activity_date >= DATE("now", "-7 days")', (student_id,))
        current_streak = c.fetchone()[0] or 0
        c.execute('UPDATE students SET current_streak = ?, last_active = DATE("now") WHERE student_id = ?', (current_streak, student_id))
        c.execute('SELECT best_streak FROM students WHERE student_id = ?', (student_id,))
        best_streak_result = c.fetchone()
        best_streak = best_streak_result[0] if best_streak_result else 0
        if current_streak > best_streak:
            c.execute('UPDATE students SET best_streak = ? WHERE student_id = ?', (current_streak, student_id))
        conn.commit()
    except Exception as e:
        pass  # Silently fail for now
    finally:
        conn.close()

def grade_submission(submission_id, grade, feedback, points_earned, graded_by):
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute('UPDATE submissions SET status = "Graded", grade = ?, teacher_feedback = ?, points_earned = ?, graded_at = CURRENT_TIMESTAMP, graded_by = ? WHERE submission_id = ?', (grade, feedback, points_earned, graded_by, submission_id))
        c.execute('SELECT student_id FROM submissions WHERE submission_id = ?', (submission_id,))
        result = c.fetchone()
        if result:
            student_id = result[0]
            c.execute('UPDATE students SET total_points = total_points + ? WHERE student_id = ?', (points_earned, student_id))
            c.execute('INSERT INTO point_transactions (student_id, transaction_type, points, description, reference_id) VALUES (?, "Submission Graded", ?, ?, ?)', (student_id, points_earned, f"Graded submission #{submission_id}", submission_id))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Error grading submission: {str(e)}")
        return False
    finally:
        conn.close()

def get_leaderboard(limit=20, class_filter=None):
    conn = sqlite3.connect('student_evaluation.db')
    try:
        query = '''SELECT s.reg_no, s.name, s.class, s.total_points, s.current_streak, s.best_streak, 
                  (SELECT COUNT(*) FROM submissions WHERE student_id = s.student_id AND status = "Graded") as submissions_graded, 
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
        df = pd.read_sql_query('SELECT activity_date, submission_count, activity_count, total_points_earned, study_hours, attendance_status, remarks FROM daily_activity WHERE student_id = ? AND activity_date >= DATE("now", ?) ORDER BY activity_date DESC', conn, params=(student_id, f'-{days} days'))
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_student_progress(student_id):
    conn = sqlite3.connect('student_evaluation.db')
    try:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) as total_submissions, SUM(CASE WHEN status = "Graded" THEN 1 ELSE 0 END) as graded_submissions, AVG(CASE WHEN status = "Graded" THEN points_earned ELSE NULL END) as avg_points, SUM(points_earned) as total_points_earned FROM submissions WHERE student_id = ?', (student_id,))
        submissions_data = c.fetchone() or (0, 0, 0, 0)
        c.execute('SELECT COUNT(*) as total_activities, SUM(points_earned) as activity_points FROM activities WHERE student_id = ?', (student_id,))
        activities_data = c.fetchone() or (0, 0)
        return {
            'total_submissions': submissions_data[0] or 0,
            'graded_submissions': submissions_data[1] or 0,
            'avg_points': round(float(submissions_data[2] or 0), 1),
            'submission_points': submissions_data[3] or 0,
            'total_activities': activities_data[0] or 0,
            'activity_points': activities_data[1] or 0
        }
    except:
        return {'total_submissions': 0, 'graded_submissions': 0, 'avg_points': 0, 'submission_points': 0, 'total_activities': 0, 'activity_points': 0}
    finally:
        conn.close()

def get_ungraded_submissions():
    conn = sqlite3.connect('student_evaluation.db')
    try:
        df = pd.read_sql_query('SELECT s.submission_id, s.submission_type, s.subject, s.title, s.description, s.date, s.max_points, st.name as student_name, st.reg_no, st.class FROM submissions s JOIN students st ON s.student_id = st.student_id WHERE s.status = "Submitted" ORDER BY s.date ASC', conn)
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

def get_student_submissions(student_id, status_filter="All", type_filter="All", days_filter="All"):
    conn = sqlite3.connect('student_evaluation.db')
    try:
        query = 'SELECT submission_id, submission_type, subject, title, date, status, points_earned, max_points, teacher_feedback, graded_at FROM submissions WHERE student_id = ?'
        params = [student_id]
        
        if status_filter != "All":
            query += " AND status = ?"
            params.append(status_filter)
        
        if type_filter != "All":
            query += " AND submission_type = ?"
            params.append(type_filter)
        
        if days_filter == "Last 7 days":
            query += " AND date >= DATE('now', '-7 days')"
        elif days_filter == "Last 30 days":
            query += " AND date >= DATE('now', '-30 days')"
        
        query += " ORDER BY date DESC"
        
        df = pd.read_sql_query(query, conn, params=params)
        return df
    except:
        return pd.DataFrame()
    finally:
        conn.close()

# Initialize database
init_database()
Path("uploads").mkdir(exist_ok=True)

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
                # Safely access tuple indices
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
            page = st.radio("Go to:", ["🏠 Dashboard", "➕ New Submission", "📋 My Submissions", "📊 My Activities", "📈 Daily Activity", "🏆 Leaderboard", "🎁 Rewards"])
        else:
            page = st.radio("Go to:", ["🏠 Teacher Dashboard", "📝 Grade Submissions", "👨‍🎓 View Students", "📊 Class Analytics", "🏆 Leaderboard", "⚙️ Manage System"])
    else:
        page = "Welcome"

if page == "Welcome":
    st.header("Welcome to Student Evaluation System")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("For Students")
        st.write("- Submit daily homework and assignments")
        st.write("- Track your learning progress")
        st.write("- Earn points and badges")
        st.write("- Compete on leaderboard")
        st.write("- Monitor daily activity")
        
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
        st.write("- Grade student submissions")
        st.write("- Monitor class performance")
        st.write("- Assign reward points")
        st.write("- Generate analytics")
        st.write("- Manage students")
        
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
        
        # Safely get student data
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
            c.execute('SELECT COUNT(*) FROM submissions WHERE student_id = ? AND status = "Submitted"', (student_id,))
            pending_result = c.fetchone()
            pending = pending_result[0] if pending_result else 0
            conn.close()
            st.metric("Pending Grading", pending, "📝")
        
        st.markdown("---")
        
        # Get progress
        progress = get_student_progress(student_id)
        
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("📊 Academic Progress")
            fig = go.Figure(data=[go.Bar(name='Submissions', x=['Total', 'Graded'], y=[progress['total_submissions'], progress['graded_submissions']])])
            fig.update_layout(barmode='group', height=300)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("🎯 Points Breakdown")
            if progress['submission_points'] + progress['activity_points'] > 0:
                labels = ['Submission Points', 'Activity Points']
                values = [progress['submission_points'], progress['activity_points']]
                fig = px.pie(values=values, names=labels, hole=0.3)
                fig.update_layout(height=300)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No points earned yet. Start submitting!")
        
        # Recent activity
        st.subheader("📅 Recent Activity")
        daily_activity = get_daily_activity(student_id, 7)
        if not daily_activity.empty:
            st.dataframe(daily_activity, use_container_width=True)
        else:
            st.info("No recent activity found. Start submitting!")
    
    elif page == "➕ New Submission":
        st.header("New Submission")
        
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
                points_info = {
                    'Daily Homework': 10, 'Weekly Assignment': 25, 
                    'Monthly Assignment': 50, 'Seminar': 30, 
                    'Project': 100, 'Research Paper': 75, 'Lab Report': 20
                }
                expected_points = points_info.get(submission_type, 10)
                st.info(f"📊 This submission can earn up to **{expected_points} points**")
            
            description = st.text_area("Description*", height=150, 
                placeholder="Describe your submission, include any important notes...")
            
            uploaded_file = st.file_uploader("Upload File (optional)", 
                type=['pdf', 'docx', 'txt', 'jpg', 'png', 'ppt', 'pptx', 'zip'])
            
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
                        st.success(f"✅ Submission recorded successfully! (ID: {submission_id})")
                        st.balloons()
                        st.info(f"📝 Your submission will be reviewed by a teacher. You can earn up to **{expected_points} points**.")
                    else:
                        st.error("Failed to record submission. Please try again.")
                else:
                    st.error("Please fill all required fields (*)")
    
    elif page == "📋 My Submissions":
        st.header("My Submissions")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.selectbox("Status", ["All", "Submitted", "Graded"])
        with col2:
            type_filter = st.selectbox("Type", ["All", "Daily Homework", "Weekly Assignment", "Monthly Assignment", "Project"])
        with col3:
            days_filter = st.selectbox("Time Period", ["Last 30 days", "Last 7 days", "All time"])
        
        df = get_student_submissions(student_id, status_filter, type_filter, days_filter)
        
        if not df.empty:
            total_subs = len(df)
            graded_subs = len(df[df['status'] == 'Graded'])
            avg_points = df['points_earned'].mean() if graded_subs > 0 else 0
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Submissions", total_subs)
            with col2:
                st.metric("Graded", graded_subs)
            with col3:
                st.metric("Avg Points", f"{avg_points:.1f}")
            
            st.dataframe(df[['submission_id', 'submission_type', 'subject', 'title', 
                            'date', 'status', 'points_earned', 'max_points']], 
                        use_container_width=True)
        else:
            st.info("No submissions found. Start by submitting your first assignment!")
    
    elif page == "📊 My Activities":
        st.header("My Activities")
        
        with st.expander("➕ Add New Activity"):
            with st.form("activity_form"):
                col1, col2 = st.columns(2)
                with col1:
                    activity_type = st.selectbox("Activity Type", 
                        ["Workshop", "Sports", "Cultural", "Competition", 
                         "Volunteer", "Club Meeting", "Guest Lecture"])
                    topic = st.text_input("Topic")
                    date = st.date_input("Activity Date", datetime.now().date())
                with col2:
                    duration = st.number_input("Duration (minutes)", min_value=1, value=60)
                    remarks = st.text_area("Remarks")
                
                if st.form_submit_button("Add Activity"):
                    add_activity(student_id, activity_type, topic, date, duration, remarks)
                    st.success("Activity added successfully!")
                    st.rerun()
        
        conn = sqlite3.connect('student_evaluation.db')
        df = pd.read_sql_query(
            'SELECT activity_type, topic, date, duration_minutes, points_earned, remarks FROM activities WHERE student_id = ? ORDER BY date DESC', 
            conn, params=(student_id,))
        conn.close()
        
        if not df.empty:
            total_activities = len(df)
            total_points = df['points_earned'].sum()
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Total Activities", total_activities)
            with col2:
                st.metric("Points Earned", total_points)
            
            st.subheader("Activity Breakdown")
            activity_counts = df['activity_type'].value_counts()
            fig = px.pie(values=activity_counts.values, names=activity_counts.index)
            st.plotly_chart(fig, use_container_width=True)
            
            st.subheader("All Activities")
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No activities recorded yet. Participate in workshops, sports, or other events!")
    
    elif page == "📈 Daily Activity":
        st.header("Daily Activity Tracker")
        
        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Start Date", datetime.now().date() - timedelta(days=30))
        with col2:
            end_date = st.date_input("End Date", datetime.now().date())
        
        conn = sqlite3.connect('student_evaluation.db')
        df = pd.read_sql_query(
            'SELECT activity_date, submission_count, activity_count, total_points_earned, study_hours, attendance_status FROM daily_activity WHERE student_id = ? AND activity_date BETWEEN ? AND ? ORDER BY activity_date DESC', 
            conn, params=(student_id, start_date, end_date))
        conn.close()
        
        if not df.empty:
            total_days = len(df)
            active_days = len(df[df['total_points_earned'] > 0])
            total_points = df['total_points_earned'].sum()
            avg_points = total_points / total_days if total_days > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Days", total_days)
            with col2:
                st.metric("Active Days", active_days)
            with col3:
                st.metric("Total Points", total_points)
            with col4:
                st.metric("Avg Points/Day", f"{avg_points:.1f}")
            
            st.subheader("📈 Activity Trends")
            fig = go.Figure()
            fig.add_trace(go.Bar(x=df['activity_date'], y=df['submission_count'], name='Submissions', marker_color='blue'))
            fig.add_trace(go.Bar(x=df['activity_date'], y=df['activity_count'], name='Activities', marker_color='green'))
            fig.update_layout(barmode='group', title='Daily Activity Overview', xaxis_title='Date', yaxis_title='Count')
            st.plotly_chart(fig, use_container_width=True)
            
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
            leaderboard['Is You'] = leaderboard['reg_no'] == student[1]
            
            st.subheader("🎖️ Top Performers")
            if len(leaderboard) >= 3:
                cols = st.columns(3)
                medals = ["🥇", "🥈", "🥉"]
                for i, col in enumerate(cols):
                    with col:
                        if i < len(leaderboard):
                            row = leaderboard.iloc[i]
                            st.metric(f"{medals[i]} {row['name']}", f"{row['total_points']} pts", row['class'])
            
            st.subheader("📊 Full Leaderboard")
            display_df = leaderboard.copy()
            display_df = display_df[['Rank', 'name', 'class', 'total_points', 'current_streak', 'best_streak', 'submissions_graded', 'activities_count']]
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
            {"name": "📚 Book Voucher", "cost": 500, "description": "Get a voucher for academic books"},
            {"name": "🎮 Game Time", "cost": 300, "description": "Extra 2 hours of gaming time"},
            {"name": "🍕 Pizza Party", "cost": 1000, "description": "Pizza party for your class"},
            {"name": "🏆 Trophy", "cost": 2000, "description": "Custom achievement trophy"},
            {"name": "📱 Tech Gadget", "cost": 5000, "description": "Latest tech gadget"},
            {"name": "🎉 Celebration", "cost": 800, "description": "Class celebration party"},
            {"name": "⭐ Star Badge", "cost": 200, "description": "Special recognition badge"},
            {"name": "📝 Extra Credit", "cost": 400, "description": "5% extra credit on next assignment"},
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
        
        st.subheader("📜 Your Reward History")
        conn = sqlite3.connect('student_evaluation.db')
        reward_history = pd.read_sql_query(
            'SELECT reward_type, points_cost, reward_date, status, claimed_at FROM rewards WHERE student_id = ? ORDER BY reward_date DESC', 
            conn, params=(student_id,))
        conn.close()
        
        if not reward_history.empty:
            st.dataframe(reward_history, use_container_width=True)
        else:
            st.info("You haven't claimed any rewards yet.")

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
            ungraded_submissions = pd.read_sql_query("SELECT COUNT(*) FROM submissions WHERE status = 'Submitted'", conn).iloc[0,0] or 0
            total_points = pd.read_sql_query("SELECT SUM(total_points) FROM students", conn).iloc[0,0] or 0
        except:
            total_students = 0
            total_submissions = 0
            ungraded_submissions = 0
            total_points = 0
        finally:
            conn.close()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total Students", total_students)
        with col2:
            st.metric("Total Submissions", total_submissions)
        with col3:
            st.metric("Pending Grading", ungraded_submissions)
        with col4:
            st.metric("Total Points Awarded", total_points)
        
        st.markdown("---")
        
        st.subheader("📝 Recent Submissions Needing Grading")
        recent_subs = get_ungraded_submissions()
        if not recent_subs.empty:
            st.dataframe(recent_subs.head(10), use_container_width=True)
        else:
            st.success("🎉 All submissions have been graded!")
        
        st.subheader("📊 Class Distribution")
        conn = sqlite3.connect('student_evaluation.db')
        class_dist = pd.read_sql_query("SELECT class, COUNT(*) as count FROM students GROUP BY class", conn)
        conn.close()
        if not class_dist.empty:
            fig = px.bar(class_dist, x='class', y='count', title='Students per Class')
            st.plotly_chart(fig, use_container_width=True)
    
    elif page == "📝 Grade Submissions":
        st.header("Grade Submissions")
        
        ungraded = get_ungraded_submissions()
        
        if not ungraded.empty:
            st.subheader(f"📋 Pending Grading ({len(ungraded)} submissions)")
            
            col1, col2 = st.columns(2)
            with col1:
                class_filter = st.selectbox("Filter by Class", ["All Classes"] + (ungraded['class'].unique().tolist() if 'class' in ungraded.columns else []))
            with col2:
                type_filter = st.selectbox("Filter by Type", ["All Types"] + (ungraded['submission_type'].unique().tolist() if 'submission_type' in ungraded.columns else []))
            
            filtered_subs = ungraded.copy()
            if class_filter != "All Classes":
                filtered_subs = filtered_subs[filtered_subs['class'] == class_filter]
            if type_filter != "All Types":
                filtered_subs = filtered_subs[filtered_subs['submission_type'] == type_filter]
            
            if not filtered_subs.empty:
                for idx, row in filtered_subs.iterrows():
                    with st.expander(f"📄 {row['submission_type']}: {row['title']} - {row['student_name']}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.info(f"**Student:** {row['student_name']}")
                            st.info(f"**Reg No:** {row['reg_no']}")
                            st.info(f"**Class:** {row['class']}")
                            st.info(f"**Subject:** {row['subject']}")
                            st.info(f"**Submitted:** {row['date']}")
                        with col2:
                            st.text_area("Description", row['description'], height=100, disabled=True)
                            
                            with st.form(f"grade_form_{row['submission_id']}"):
                                grade = st.selectbox("Grade", ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "D", "F"], key=f"grade_{row['submission_id']}")
                                feedback = st.text_area("Feedback", placeholder="Provide constructive feedback...", key=f"fb_{row['submission_id']}")
                                max_pts = row['max_points'] if 'max_points' in row and row['max_points'] else 50
                                points = st.slider("Points", 0, max_pts, max_pts // 2, key=f"pts_{row['submission_id']}")
                                
                                if st.form_submit_button("Submit Grade"):
                                    if grade_submission(row['submission_id'], grade, feedback, points, teacher_id):
                                        st.success(f"Graded {row['title']} successfully!")
                                        st.rerun()
            else:
                st.info("No submissions match the selected filters.")
        else:
            st.success("🎉 All submissions have been graded!")
    
    elif page == "👨‍🎓 View Students":
        st.header("View Students")
        
        conn = sqlite3.connect('student_evaluation.db')
        students = pd.read_sql_query('SELECT reg_no, name, class, email, total_points, current_streak, best_streak, last_active FROM students ORDER BY total_points DESC', conn)
        conn.close()
        
        if not students.empty:
            col1, col2 = st.columns(2)
            with col1:
                class_filter = st.multiselect("Filter by Class", students['class'].unique())
            with col2:
                search_name = st.text_input("Search by Name")
            
            filtered_students = students.copy()
            if class_filter:
                filtered_students = filtered_students[filtered_students['class'].isin(class_filter)]
            if search_name:
                filtered_students = filtered_students[filtered_students['name'].str.contains(search_name, case=False)]
            
            st.dataframe(filtered_students, use_container_width=True)
        else:
            st.info("No students found.")
    
    elif page == "📊 Class Analytics":
        st.header("Class Analytics")
        
        conn = sqlite3.connect('student_evaluation.db')
        class_performance = pd.read_sql_query('SELECT class, COUNT(*) as student_count, AVG(total_points) as avg_points, MAX(total_points) as max_points, MIN(total_points) as min_points, SUM(total_points) as total_points FROM students GROUP BY class ORDER BY avg_points DESC', conn)
        
        if not class_performance.empty:
            st.subheader("📈 Class Performance")
            fig = px.bar(class_performance, x='class', y='avg_points', title='Average Points per Class')
            st.plotly_chart(fig, use_container_width=True)
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
        
        tab1, tab2, tab3 = st.tabs(["📊 System Stats", "⚙️ Settings", "🔄 Maintenance"])
        
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
                
                stats_data["Metric"].append("Graded Submissions")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM submissions WHERE status = 'Graded'", conn).iloc[0,0] or 0)
                
                stats_data["Metric"].append("Pending Submissions")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM submissions WHERE status = 'Submitted'", conn).iloc[0,0] or 0)
                
                stats_data["Metric"].append("Total Activities")
                stats_data["Value"].append(pd.read_sql_query("SELECT COUNT(*) FROM activities", conn).iloc[0,0] or 0)
                
                stats_data["Metric"].append("Total Points Awarded")
                stats_data["Value"].append(pd.read_sql_query("SELECT SUM(total_points) FROM students", conn).iloc[0,0] or 0)
                
                stats_data["Metric"].append("Average Points per Student")
                avg_points = pd.read_sql_query("SELECT AVG(total_points) FROM students", conn).iloc[0,0] or 0
                stats_data["Value"].append(f"{avg_points:.1f}")
            except:
                pass
            finally:
                conn.close()
            
            if stats_data["Metric"]:
                stats_df = pd.DataFrame(stats_data)
                st.dataframe(stats_df, use_container_width=True)
            
            try:
                db_size = Path('student_evaluation.db').stat().st_size / 1024 / 1024
                st.info(f"📊 Database Size: {db_size:.2f} MB")
            except:
                pass
        
        with tab2:
            st.subheader("System Settings")
            st.info("Settings configuration will be available in the next update.")
        
        with tab3:
            st.subheader("System Maintenance")
            st.info("Maintenance functions will be available in the next update.")

st.markdown("---")
st.markdown("""
<div style='text-align: center'>
    <p>Continuous Student Evaluation & Monitoring System v2.0</p>
    <p>Design and maintained by: S P Sajjan</p>
    <p>📧 Contact: sajjanvsl@gmail.com | 📞 Help Desk: 9008802403</p>
</div>
""", unsafe_allow_html=True)