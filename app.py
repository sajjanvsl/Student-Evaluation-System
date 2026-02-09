# -*- coding: utf-8 -*-
"""
Created on Mon Feb  9 21:24:09 2026

@author: Admin
"""

import streamlit as st
import pandas as pd
import sqlite3
import datetime
from pathlib import Path
import json
import os

# Set page configuration
st.set_page_config(
    page_title="Student Evaluation System",
    page_icon="📚",
    layout="wide"
)

# Initialize session state
if 'current_student' not in st.session_state:
    st.session_state.current_student = None
if 'submitted' not in st.session_state:
    st.session_state.submitted = False

# Database setup
def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    
    # Create students table
    c.execute('''
        CREATE TABLE IF NOT EXISTS students (
            reg_no TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            class TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create submissions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reg_no TEXT,
            submission_type TEXT NOT NULL,
            subject TEXT,
            description TEXT,
            date DATE NOT NULL,
            status TEXT DEFAULT 'Submitted',
            feedback TEXT,
            grade TEXT,
            file_path TEXT,
            FOREIGN KEY (reg_no) REFERENCES students (reg_no)
        )
    ''')
    
    # Create activities table
    c.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reg_no TEXT,
            activity_type TEXT NOT NULL,
            topic TEXT,
            date DATE NOT NULL,
            duration_minutes INTEGER,
            status TEXT DEFAULT 'Completed',
            remarks TEXT,
            FOREIGN KEY (reg_no) REFERENCES students (reg_no)
        )
    ''')
    
    conn.commit()
    conn.close()

def add_student(reg_no, name, class_name):
    """Add new student to database"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO students (reg_no, name, class) VALUES (?, ?, ?)",
            (reg_no, name, class_name)
        )
        conn.commit()
        st.success(f"Student {name} registered successfully!")
        return True
    except sqlite3.IntegrityError:
        st.error("Registration number already exists!")
        return False
    finally:
        conn.close()

def get_student(reg_no):
    """Get student details by registration number"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    c.execute("SELECT * FROM students WHERE reg_no = ?", (reg_no,))
    student = c.fetchone()
    conn.close()
    return student

def add_submission(reg_no, submission_type, subject, description, date, file_path=None):
    """Add new submission to database"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    c.execute(
        """INSERT INTO submissions 
        (reg_no, submission_type, subject, description, date, file_path) 
        VALUES (?, ?, ?, ?, ?, ?)""",
        (reg_no, submission_type, subject, description, date, file_path)
    )
    conn.commit()
    conn.close()

def add_activity(reg_no, activity_type, topic, date, duration, remarks):
    """Add new activity to database"""
    conn = sqlite3.connect('student_evaluation.db')
    c = conn.cursor()
    c.execute(
        """INSERT INTO activities 
        (reg_no, activity_type, topic, date, duration_minutes, remarks) 
        VALUES (?, ?, ?, ?, ?, ?)""",
        (reg_no, activity_type, topic, date, duration, remarks)
    )
    conn.commit()
    conn.close()

def get_student_submissions(reg_no):
    """Get all submissions for a student"""
    conn = sqlite3.connect('student_evaluation.db')
    df = pd.read_sql_query(
        "SELECT * FROM submissions WHERE reg_no = ? ORDER BY date DESC",
        conn,
        params=(reg_no,)
    )
    conn.close()
    return df

def get_student_activities(reg_no):
    """Get all activities for a student"""
    conn = sqlite3.connect('student_evaluation.db')
    df = pd.read_sql_query(
        "SELECT * FROM activities WHERE reg_no = ? ORDER BY date DESC",
        conn,
        params=(reg_no,)
    )
    conn.close()
    return df

def get_all_students():
    """Get all registered students"""
    conn = sqlite3.connect('student_evaluation.db')
    df = pd.read_sql_query("SELECT * FROM students ORDER BY reg_no", conn)
    conn.close()
    return df

def save_uploaded_file(uploaded_file, reg_no, submission_type):
    """Save uploaded file to disk"""
    upload_dir = Path("uploads") / reg_no / submission_type
    upload_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = upload_dir / f"{timestamp}_{uploaded_file.name}"
    
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    return str(file_path)

# Initialize database
init_database()

# Create uploads directory
Path("uploads").mkdir(exist_ok=True)

# Main application
st.title("📚 Continuous Student Evaluation & Monitoring System")
st.markdown("---")

# Sidebar for navigation
with st.sidebar:
    st.header("Navigation")
    page = st.radio("Go to", [
        "Student Portal",
        "New Submission",
        "View Records",
        "Student Registration",
        "Dashboard"
    ])
    
    st.markdown("---")
    st.header("Current Session")
    if st.session_state.current_student:
        st.success(f"Logged in as: {st.session_state.current_student[1]}")
        st.info(f"Reg No: {st.session_state.current_student[0]}")
        st.info(f"Class: {st.session_state.current_student[2]}")
        if st.button("Logout"):
            st.session_state.current_student = None
            st.session_state.submitted = False
            st.rerun()
    else:
        st.warning("No student logged in")

# Student Portal - Login/Student Identification
if page == "Student Portal":
    st.header("Student Portal")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        reg_no = st.text_input("Enter Registration Number", key="login_reg")
        
        if reg_no:
            student = get_student(reg_no)
            
            if student:
                st.session_state.current_student = student
                st.success(f"Welcome back, {student[1]}!")
                
                # Display student info
                with st.expander("Your Information", expanded=True):
                    st.info(f"**Name:** {student[1]}")
                    st.info(f"**Registration No:** {student[0]}")
                    st.info(f"**Class:** {student[2]}")
                    st.info(f"**Registered on:** {student[3]}")
            else:
                st.warning("Registration number not found. Please register below.")
                
                # Registration form
                with st.form("new_student_form"):
                    name = st.text_input("Full Name")
                    class_name = st.text_input("Class")
                    
                    if st.form_submit_button("Register"):
                        if name and class_name:
                            if add_student(reg_no, name, class_name):
                                student = get_student(reg_no)
                                st.session_state.current_student = student
                                st.rerun()
                        else:
                            st.error("Please fill all fields")
    
    with col2:
        st.image("https://cdn-icons-png.flaticon.com/512/3135/3135715.png", width=150)

# New Submission Page
elif page == "New Submission":
    st.header("New Submission")
    
    if not st.session_state.current_student:
        st.warning("Please identify yourself in the Student Portal first!")
        st.stop()
    
    reg_no, name, class_name, _ = st.session_state.current_student
    
    # Display current student info
    with st.container():
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Student", name)
        with col2:
            st.metric("Registration No", reg_no)
        with col3:
            st.metric("Class", class_name)
    
    st.markdown("---")
    
    # Submission type selector
    submission_type = st.selectbox(
        "Select Submission Type",
        ["Daily Homework", "Monthly Assignment", "Seminar", "Project", "Other Activity"]
    )
    
    # Submission form
    with st.form("submission_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            subject = st.text_input("Subject")
            date = st.date_input("Date", datetime.date.today())
            
        with col2:
            if submission_type == "Seminar":
                duration = st.number_input("Duration (minutes)", min_value=1, value=30)
                topic = st.text_input("Seminar Topic")
            elif submission_type == "Other Activity":
                activity_type = st.selectbox("Activity Type", ["Workshop", "Sports", "Cultural", "Competition", "Volunteer"])
                duration = st.number_input("Duration (minutes)", min_value=1, value=60)
        
        description = st.text_area("Description/Remarks", height=100)
        
        # File upload
        uploaded_file = st.file_uploader(
            f"Upload {submission_type} file (optional)",
            type=['pdf', 'docx', 'txt', 'jpg', 'png', 'ppt', 'pptx']
        )
        
        submitted = st.form_submit_button("Submit", type="primary")
        
        if submitted:
            if not subject and submission_type not in ["Seminar", "Other Activity"]:
                st.error("Please enter subject")
            else:
                file_path = None
                if uploaded_file:
                    file_path = save_uploaded_file(uploaded_file, reg_no, submission_type)
                
                # Add to database
                if submission_type in ["Seminar", "Other Activity"]:
                    if submission_type == "Seminar":
                        add_activity(reg_no, "Seminar", topic, date, duration, description)
                    else:
                        add_activity(reg_no, activity_type, topic, date, duration, description)
                    st.success(f"{submission_type} recorded successfully!")
                else:
                    add_submission(reg_no, submission_type, subject, description, date, file_path)
                    st.success(f"{submission_type} submitted successfully!")
                
                st.session_state.submitted = True
                st.balloons()

# View Records Page
elif page == "View Records":
    st.header("View Your Records")
    
    if not st.session_state.current_student:
        st.warning("Please identify yourself in the Student Portal first!")
        st.stop()
    
    reg_no, name, class_name, _ = st.session_state.current_student
    
    tab1, tab2 = st.tabs(["📄 Submissions", "📊 Activities"])
    
    with tab1:
        st.subheader("Your Submissions")
        submissions_df = get_student_submissions(reg_no)
        
        if not submissions_df.empty:
            # Display metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Submissions", len(submissions_df))
            with col2:
                homework_count = len(submissions_df[submissions_df['submission_type'] == 'Daily Homework'])
                st.metric("Homework", homework_count)
            with col3:
                assignment_count = len(submissions_df[submissions_df['submission_type'] == 'Monthly Assignment'])
                st.metric("Assignments", assignment_count)
            with col4:
                project_count = len(submissions_df[submissions_df['submission_type'] == 'Project'])
                st.metric("Projects", project_count)
            
            # Filter options
            col1, col2 = st.columns(2)
            with col1:
                filter_type = st.multiselect(
                    "Filter by Type",
                    submissions_df['submission_type'].unique(),
                    default=submissions_df['submission_type'].unique()
                )
            with col2:
                date_range = st.date_input(
                    "Date Range",
                    [datetime.date.today() - datetime.timedelta(days=30), datetime.date.today()]
                )
            
            # Apply filters
            filtered_df = submissions_df[
                submissions_df['submission_type'].isin(filter_type) &
                (submissions_df['date'] >= pd.Timestamp(date_range[0])) &
                (submissions_df['date'] <= pd.Timestamp(date_range[1]))
            ]
            
            # Display table
            st.dataframe(
                filtered_df[['date', 'submission_type', 'subject', 'status', 'grade']],
                use_container_width=True
            )
            
            # Download option
            csv = filtered_df.to_csv(index=False)
            st.download_button(
                label="Download as CSV",
                data=csv,
                file_name=f"{reg_no}_submissions.csv",
                mime="text/csv"
            )
        else:
            st.info("No submissions found")
    
    with tab2:
        st.subheader("Your Activities")
        activities_df = get_student_activities(reg_no)
        
        if not activities_df.empty:
            # Display activities
            st.dataframe(
                activities_df[['date', 'activity_type', 'topic', 'duration_minutes', 'status']],
                use_container_width=True
            )
            
            # Activity summary
            st.subheader("Activity Summary")
            activity_summary = activities_df.groupby('activity_type').agg({
                'duration_minutes': 'sum',
                'id': 'count'
            }).rename(columns={'id': 'count'})
            
            col1, col2 = st.columns(2)
            with col1:
                st.dataframe(activity_summary, use_container_width=True)
            with col2:
                st.bar_chart(activity_summary['count'])
        else:
            st.info("No activities found")

# Student Registration Page (Admin/New Students)
elif page == "Student Registration":
    st.header("New Student Registration")
    
    with st.form("registration_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            reg_no = st.text_input("Registration Number*")
            name = st.text_input("Full Name*")
        
        with col2:
            class_name = st.text_input("Class*")
            email = st.text_input("Email (optional)")
        
        st.markdown("**Required fields*")
        submitted = st.form_submit_button("Register Student")
        
        if submitted:
            if reg_no and name and class_name:
                if add_student(reg_no, name, class_name):
                    st.rerun()
            else:
                st.error("Please fill all required fields")

# Dashboard Page
elif page == "Dashboard":
    st.header("System Dashboard")
    
    all_students = get_all_students()
    
    if not all_students.empty:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Students", len(all_students))
        
        with col2:
            class_count = all_students['class'].nunique()
            st.metric("Classes", class_count)
        
        with col3:
            latest = all_students['created_at'].max()
            st.metric("Latest Registration", pd.to_datetime(latest).strftime('%Y-%m-%d'))
        
        st.subheader("All Registered Students")
        st.dataframe(all_students, use_container_width=True)
        
        # Class distribution
        st.subheader("Class Distribution")
        class_dist = all_students['class'].value_counts()
        st.bar_chart(class_dist)
        
        # Export data
        st.subheader("Export Data")
        col1, col2 = st.columns(2)
        
        with col1:
            student_csv = all_students.to_csv(index=False)
            st.download_button(
                label="Download Student List (CSV)",
                data=student_csv,
                file_name="all_students.csv",
                mime="text/csv"
            )
    else:
        st.info("No students registered yet")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style='text-align: center'>
        <p>Continuous Student Evaluation & Monitoring System v1.0</p>
        <p>📧 Contact: admin@university.edu | 📞 Help Desk: 1800-123-456</p>
    </div>
    """,
    unsafe_allow_html=True
)