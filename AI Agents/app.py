import streamlit as st
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Optional, Dict
import calendar as cal
from dataclasses import dataclass
import json

# Add debug mode toggle at the top
DEBUG_MODE = True

def debug_log(message: str):
    """Helper function to log debug messages"""
    if DEBUG_MODE:
        st.sidebar.write(f"🐛 {message}")
        print(f"DEBUG: {message}")

# Try importing and show what works
try:
    from optimized_agent import (
        extract_semester_info,
        generate_full_calendar,
        regenerate_weeks,
        generate_quiz,
        generate_multiple_weeks_batch,
        SemesterCalendar,
        WeeklyCalendar,
        SemesterInfo
    )
    debug_log("✅ All imports successful!")
except ImportError as e:
    st.error(f"❌ Import Error: {str(e)}")
    st.error(f"Full traceback: {traceback.format_exc()}")
    st.stop()


# ============ Streamlit Configuration ============
st.set_page_config(
    page_title="AI Study Planner",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 2rem;
    }
    
    .week-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 15px;
        margin: 10px 0;
        color: white;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    
    .generating-animation {
        border: 3px solid #667eea;
        border-radius: 10px;
        padding: 30px;
        text-align: center;
        background: linear-gradient(45deg, #f3f4f6, #e5e7eb);
        margin: 20px 0;
    }
    
    .study-block {
        background: #f8fafc;
        border-left: 4px solid #667eea;
        padding: 15px;
        margin: 10px 0;
        border-radius: 8px;
    }
    
    .day-header {
        background: #667eea;
        color: white;
        padding: 10px 15px;
        border-radius: 8px;
        font-weight: bold;
        margin: 15px 0 10px 0;
    }
    
    .goal-item {
        background: #eff6ff;
        border-left: 3px solid #3b82f6;
        padding: 10px;
        margin: 5px 0;
        border-radius: 5px;
    }
    
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    }
</style>
""", unsafe_allow_html=True)


# ============ Session State Initialization ============
if 'calendar_generated' not in st.session_state:
    st.session_state.calendar_generated = False
    debug_log("Initialized calendar_generated = False")
    
if 'semester_calendar' not in st.session_state:
    st.session_state.semester_calendar = None
    debug_log("Initialized semester_calendar = None")

if 'semester_info' not in st.session_state:
    st.session_state.semester_info = None
    debug_log("Initialized semester_info = None")
    
if 'syllabus_text' not in st.session_state:
    st.session_state.syllabus_text = ""
    debug_log("Initialized syllabus_text = ''")
    
if 'generating' not in st.session_state:
    st.session_state.generating = False
    debug_log("Initialized generating = False")

if 'selected_weeks' not in st.session_state:
    st.session_state.selected_weeks = []
    debug_log("Initialized selected_weeks = []")

if 'error_log' not in st.session_state:
    st.session_state.error_log = []


# ============ Helper Functions ============

def create_generating_animation(week_number: int, total_weeks: int):
    """Creates an animated loading display for week generation"""
    progress = week_number / total_weeks
    
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col2:
        st.markdown(f"""
        <div class="generating-animation">
            <h2>🔮 Generating Week {week_number} of {total_weeks}</h2>
            <p style="font-size: 1.2rem; margin-top: 20px;">
                Creating your personalized study schedule...
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.progress(progress)
        
        # Animated dots
        dots = "." * (week_number % 4)
        st.markdown(f"<p style='text-align: center; font-size: 1.5rem;'>✨ Working{dots}</p>", 
                   unsafe_allow_html=True)


def generate_calendar_stream(syllabus: str, progress_placeholder):
    """
    Generates calendar with streaming progress updates
    """
    debug_log(f"Starting calendar generation, syllabus length: {len(syllabus)}")
    
    try:
        # Extract semester info first
        with progress_placeholder.container():
            st.info("📊 Analyzing syllabus and extracting semester information...")
            time.sleep(0.5)
        
        debug_log("Calling extract_semester_info...")
        semester_info = extract_semester_info(syllabus)
        debug_log(f"Semester info extracted: {semester_info.total_weeks} weeks")
        
        # Store semester info in session state
        st.session_state.semester_info = semester_info
        
        with progress_placeholder.container():
            st.success(f"✓ Found {semester_info.total_weeks} weeks, {len(semester_info.key_deadlines)} deadlines")
            time.sleep(1)
        
        # Generate calendar with progress callback
        total_weeks = semester_info.total_weeks
        weeks_completed = [0]  # Use list to allow modification in nested function
        
        def progress_callback(wave_num, total_waves, completed, total):
            """Callback for progress updates"""
            debug_log(f"Progress callback - Wave {wave_num}/{total_waves}, Completed: {completed}/{total}")
            
            with progress_placeholder.container():
                # Show wave progress
                st.info(f"🌊 Wave {wave_num}/{total_waves}")
                
                # Calculate which week we're on
                current_week = completed + 1
                if current_week <= total:
                    create_generating_animation(current_week, total)
                
                weeks_completed[0] = completed
        
        # Generate full calendar
        debug_log("Calling generate_full_calendar...")
        calendar = generate_full_calendar(syllabus, callback=progress_callback)
        debug_log(f"Calendar generated successfully with {len(calendar.weeks)} weeks")
        
        return calendar
        
    except Exception as e:
        error_msg = f"Error in generate_calendar_stream: {str(e)}\n{traceback.format_exc()}"
        debug_log(error_msg)
        st.session_state.error_log.append(error_msg)
        raise


def display_week_calendar(week: WeeklyCalendar, week_index: int):
    """Displays a single week's calendar in an attractive format"""
    
    with st.expander(f"📅 Week {week.week_number}: {week.week_dates}", expanded=(week_index < 2)):
        # Weekly Goals
        st.markdown("### 🎯 Weekly Goals")
        for goal in week.weekly_goals:
            st.markdown(f'<div class="goal-item">• {goal}</div>', unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Daily Schedule
        st.markdown("### 📋 Study Schedule")
        
        for day_schedule in week.schedule:
            if day_schedule.blocks:
                st.markdown(f'<div class="day-header">{day_schedule.day}</div>', 
                          unsafe_allow_html=True)
                
                for block in day_schedule.blocks:
                    notes_html = f'<br><em>📝 Note: {block.notes}</em>' if block.notes else ''
                    st.markdown(f"""
                    <div class="study-block">
                        <strong>⏰ {block.time_range}</strong><br>
                        <strong>📖 Topic:</strong> {block.topic}<br>
                        <strong>📚 Course:</strong> {block.course}
                        {notes_html}
                    </div>
                    """, unsafe_allow_html=True)


def display_month_calendar(semester_calendar, selected_month: int, selected_year: int):
    """Displays a month view of the calendar"""
    
    st.markdown(f"## 📅 {cal.month_name[selected_month]} {selected_year}")
    
    # Create calendar grid
    month_cal = cal.monthcalendar(selected_year, selected_month)
    
    # Days of week header
    cols = st.columns(7)
    days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    for i, day in enumerate(days):
        with cols[i]:
            st.markdown(f"**{day}**")
    
    # Calendar grid
    for week_idx, week in enumerate(month_cal):
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                if day == 0:
                    st.write("")
                else:
                    st.write(f"{day}")


def regenerate_selected_weeks_ui(syllabus: str, selected_weeks: List[int], 
                              semester_info: SemesterInfo, current_calendar: SemesterCalendar):
    """Regenerates only the selected weeks with UI updates"""
    
    debug_log(f"Regenerating weeks: {selected_weeks}")
    progress_placeholder = st.empty()
    
    try:
        with progress_placeholder.container():
            st.info(f"🔄 Regenerating {len(selected_weeks)} selected week(s)...")
        
        def regen_callback(current, total, week_num):
            """Callback for regeneration progress"""
            debug_log(f"Regen callback - {current}/{total}, week {week_num}")
            with progress_placeholder.container():
                st.info(f"Regenerating week {week_num}... ({current}/{total})")
                create_generating_animation(current, total)
        
        # Use the public API function
        updated_calendar = regenerate_weeks(
            syllabus,
            semester_info,
            selected_weeks,
            current_calendar,
            callback=regen_callback
        )
        
        debug_log("Regeneration completed successfully")
        
        with progress_placeholder.container():
            st.success(f"✅ Successfully regenerated {len(selected_weeks)} week(s)!")
            time.sleep(1)
        
        progress_placeholder.empty()
        
        return updated_calendar
        
    except Exception as e:
        error_msg = f"Error in regeneration: {str(e)}\n{traceback.format_exc()}"
        debug_log(error_msg)
        st.error(error_msg)
        raise


# ============ Main App ============

def main():
    # Header
    st.markdown('<h1 class="main-header">🎓 AI-Powered Study Planner</h1>', 
               unsafe_allow_html=True)
    
    # Debug panel in sidebar
    if DEBUG_MODE:
        with st.sidebar:
            st.markdown("---")
            st.markdown("## 🐛 Debug Info")
            st.write(f"calendar_generated: {st.session_state.calendar_generated}")
            st.write(f"generating: {st.session_state.generating}")
            st.write(f"syllabus_length: {len(st.session_state.syllabus_text)}")
            st.write(f"has_calendar: {st.session_state.semester_calendar is not None}")
            
            if st.session_state.error_log:
                with st.expander("Error Log", expanded=True):
                    for error in st.session_state.error_log:
                        st.code(error)
    
    # Sidebar
    with st.sidebar:
        st.markdown("## 📝 Syllabus Input")
        
        # File upload option
        uploaded_file = st.file_uploader("Upload Syllabus (PDF/TXT)", 
                                        type=['pdf', 'txt'])
        
        # Text area option
        syllabus_input = st.text_area(
            "Or paste syllabus text here:",
            height=300,
            placeholder="Paste your course syllabus here..."
        )
        
        if uploaded_file:
            debug_log(f"File uploaded: {uploaded_file.name}")
            # Handle file upload
            if uploaded_file.type == "text/plain":
                syllabus_input = uploaded_file.read().decode()
                debug_log(f"File loaded, length: {len(syllabus_input)}")
        
        st.session_state.syllabus_text = syllabus_input
        
        st.markdown("---")
        
        # View options
        st.markdown("## 👁️ View Options")
        view_mode = st.radio(
            "Display Mode:",
            ["Week View", "Month View", "List View"]
        )
    
    # Main content area
    debug_log(f"Main render - generated: {st.session_state.calendar_generated}, generating: {st.session_state.generating}")
    
    # IMPORTANT: Check generating state FIRST before showing the button
    if st.session_state.generating:
        debug_log("In generating mode")
        # Show generation progress
        progress_placeholder = st.empty()
        
        try:
            debug_log("Starting generation process...")
            # Generate calendar with streaming
            calendar = generate_calendar_stream(
                st.session_state.syllabus_text,
                progress_placeholder
            )
            
            debug_log(f"Generation complete, storing calendar with {len(calendar.weeks)} weeks")
            # Store in session state
            st.session_state.semester_calendar = calendar
            st.session_state.calendar_generated = True
            st.session_state.generating = False
            
            progress_placeholder.empty()
            st.success("✅ Calendar generated successfully!")
            time.sleep(1)
            debug_log("About to rerun after successful generation")
            st.rerun()
            
        except Exception as e:
            error_msg = f"❌ Error generating calendar: {str(e)}\n\nFull traceback:\n{traceback.format_exc()}"
            st.error(error_msg)
            st.session_state.error_log.append(error_msg)
            st.session_state.generating = False
            debug_log(f"Error occurred: {error_msg}")
            
            # Add a button to try again
            if st.button("Try Again"):
                st.session_state.generating = False
                st.rerun()
            st.stop()
    
    elif not st.session_state.calendar_generated:
        debug_log("In generating mode")
        # Show generation progress
        progress_placeholder = st.empty()
        
        try:
            debug_log("Starting generation process...")
            # Generate calendar with streaming
            calendar = generate_calendar_stream(
                st.session_state.syllabus_text,
                progress_placeholder
            )
            
            debug_log(f"Generation complete, storing calendar with {len(calendar.weeks)} weeks")
            # Store in session state
            st.session_state.semester_calendar = calendar
            st.session_state.calendar_generated = True
            st.session_state.generating = False
            
            progress_placeholder.empty()
            st.success("✅ Calendar generated successfully!")
            time.sleep(1)
            debug_log("About to rerun after successful generation")
            st.rerun()
            
        except Exception as e:
            error_msg = f"❌ Error generating calendar: {str(e)}\n\nFull traceback:\n{traceback.format_exc()}"
            st.error(error_msg)
            st.session_state.error_log.append(error_msg)
            st.session_state.generating = False
            debug_log(f"Error occurred: {error_msg}")
            
            # Add a button to try again
            if st.button("Try Again"):
                st.session_state.generating = False
                st.rerun()
            st.stop()
    
    else:
        debug_log("In display mode")
        # Calendar is generated - show it
        calendar = st.session_state.semester_calendar
        semester_info = st.session_state.semester_info
        
        if calendar is None:
            st.error("Calendar is None! This shouldn't happen.")
            debug_log("ERROR: Calendar is None in display mode")
            if st.button("Reset"):
                st.session_state.calendar_generated = False
                st.rerun()
            st.stop()
        
        # Action buttons
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        
        with col1:
            if st.button("🔄 Regenerate Selected Weeks", use_container_width=True):
                if st.session_state.selected_weeks:
                    try:
                        calendar = regenerate_selected_weeks_ui(
                            st.session_state.syllabus_text,
                            st.session_state.selected_weeks,
                            semester_info,
                            calendar
                        )
                        st.session_state.semester_calendar = calendar
                        st.session_state.selected_weeks = []
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error regenerating: {str(e)}")
                        st.session_state.error_log.append(traceback.format_exc())
                else:
                    st.warning("Please select weeks to regenerate first!")
        
        with col2:
            if st.button("📥 Export Calendar", use_container_width=True):
                try:
                    # Export functionality
                    calendar_json = {
                        "course_name": calendar.course_name,
                        "semester": calendar.semester,
                        "weeks": [
                            {
                                "week_number": w.week_number,
                                "week_dates": w.week_dates,
                                "goals": w.weekly_goals,
                                "schedule": [
                                    {
                                        "day": d.day,
                                        "blocks": [
                                            {
                                                "topic": b.topic,
                                                "time": b.time_range,
                                                "course": b.course,
                                                "notes": b.notes
                                            } for b in d.blocks
                                        ]
                                    } for d in w.schedule
                                ]
                            } for w in calendar.weeks
                        ]
                    }
                    
                    st.download_button(
                        label="Download as JSON",
                        data=json.dumps(calendar_json, indent=2),
                        file_name="study_calendar.json",
                        mime="application/json"
                    )
                except Exception as e:
                    st.error(f"Export error: {str(e)}")
        
        with col3:
            if st.button("🎯 Generate Quiz", use_container_width=True):
                try:
                    with st.spinner("Generating quiz..."):
                        quiz = generate_quiz(st.session_state.syllabus_text, semester_info)
                    
                    st.markdown("### 📝 Practice Quiz")
                    st.markdown(f"**Topic:** {quiz.topic}")
                    st.markdown("---")
                    
                    for i, question in enumerate(quiz.questions, 1):
                        st.markdown(f"**{i}.** {question}")
                    
                except Exception as e:
                    st.error(f"Error generating quiz: {str(e)}")
                    st.session_state.error_log.append(traceback.format_exc())
        
        with col4:
            if st.button("🔄 Start Over"):
                debug_log("Start Over clicked")
                st.session_state.calendar_generated = False
                st.session_state.semester_calendar = None
                st.session_state.semester_info = None
                st.session_state.selected_weeks = []
                st.session_state.error_log = []
                st.rerun()
        
        st.markdown("---")
        
        # Week selection for regeneration
        if calendar and hasattr(calendar, 'weeks'):
            st.markdown("### 🎯 Select Weeks to Regenerate")
            
            week_numbers = [w.week_number for w in calendar.weeks]
            selected = st.multiselect(
                "Choose weeks:",
                week_numbers,
                default=st.session_state.selected_weeks,
                format_func=lambda x: f"Week {x}"
            )
            st.session_state.selected_weeks = selected
            
            if selected:
                st.info(f"📌 Selected: Week(s) {', '.join(map(str, selected))}")
            
            st.markdown("---")
        
        # Display calendar based on view mode
        if calendar and hasattr(calendar, 'weeks'):
            if view_mode == "Week View":
                st.markdown(f"## 📚 {calendar.course_name} - {calendar.semester}")
                
                for i, week in enumerate(calendar.weeks):
                    display_week_calendar(week, i)
            
            elif view_mode == "Month View":
                # Month selector
                col1, col2 = st.columns(2)
                with col1:
                    month = st.selectbox("Month", range(1, 13), 
                                       format_func=lambda x: cal.month_name[x])
                with col2:
                    year = st.selectbox("Year", [2025, 2026], index=0)
                
                display_month_calendar(calendar, month, year)
            
            elif view_mode == "List View":
                st.markdown(f"## 📚 {calendar.course_name} - {calendar.semester}")
                
                for week in calendar.weeks:
                    st.markdown(f"### Week {week.week_number}: {week.week_dates}")
                    
                    # Goals
                    with st.expander("🎯 Goals", expanded=False):
                        for goal in week.weekly_goals:
                            st.write(f"• {goal}")
                    
                    # Schedule
                    for day in week.schedule:
                        if day.blocks:
                            st.markdown(f"**{day.day}:**")
                            for block in day.blocks:
                                st.write(f"  ⏰ {block.time_range}: {block.topic}")
                    
                    st.markdown("---")


if __name__ == "__main__":
    main()
