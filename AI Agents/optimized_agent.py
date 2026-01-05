"""
Optimized Study Planner Agent with Parallel Generation
This module can be imported by the Streamlit frontend.
"""

from langchain_ollama import ChatOllama
from pydantic import BaseModel, Field
from typing import Optional, List, Literal
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage, SystemMessage
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed


# ============ LLM Setup ============
llm = ChatOllama(model="llama3.1:8b", temperature=0.2)


# ============ Schemas =============
class Plan(BaseModel):
    """Ordered list of steps to complete"""
    steps: List[Literal[
        "extract_semester_info",
        "generate_calendar",
        "generate_quiz"
    ]] = Field(
        description="Ordered steps required to build the study experience"
    )


class SemesterInfo(BaseModel):
    """Key information about the semester"""
    start_date: str = Field(description="Semester start date (YYYY-MM-DD)")
    end_date: str = Field(description="Semester end date (YYYY-MM-DD)")
    total_weeks: int = Field(description="Total number of weeks in semester")
    key_deadlines: List[dict] = Field(
        description="List of important deadlines with dates and descriptions"
    )
    major_topics: List[str] = Field(
        description="Main topics/modules covered in the course"
    )


class StudyBlock(BaseModel):
    """A single study session"""
    course: str = Field(description="Course name")
    topic: str = Field(description="Topic to study")
    time_range: str = Field(description="Time range, e.g. '6:00pm - 8:00pm'")
    notes: Optional[str] = Field(None, description="Additional notes or context")


class DaySchedule(BaseModel):
    """Schedule for one day"""
    day: str = Field(description="Day of the week, e.g. Monday")
    blocks: List[StudyBlock]


class WeeklyCalendar(BaseModel):
    """Complete weekly study calendar"""
    week_number: int = Field(description="Week number (1-based)")
    week_dates: str = Field(description="Date range for this week, e.g. 'Aug 29 - Sep 4'")
    schedule: List[DaySchedule]
    weekly_goals: List[str] = Field(
        description="Goals to accomplish this week"
    )


class MultiWeekCalendar(BaseModel):
    """Multiple weeks generated in one call"""
    weeks: List[WeeklyCalendar]


class SemesterCalendar(BaseModel):
    """Complete semester study calendar"""
    course_name: str = Field(description="Course name")
    semester: str = Field(description="Semester identifier, e.g. 'Fall 2025'")
    weeks: List[WeeklyCalendar] = Field(
        description="Calendar for each week of the semester"
    )


class QuizData(BaseModel):
    """Generated quiz data"""
    topic: str = Field(description="Main topic of the quiz")
    questions: List[str] = Field(description="List of quiz questions")


# ============ Agent State =============
class AgentState(TypedDict):
    """Shared state across all agents"""
    syllabus: str
    plan: Optional[Plan]
    current_step_index: int
    semester_info: Optional[SemesterInfo]
    current_week: int
    weeks_generated: List[WeeklyCalendar]
    full_calendar: Optional[SemesterCalendar]
    quiz: Optional[QuizData]
    completed_steps: List[str]


# ============ Helper Functions =============

def _parse_date(date_str: str) -> datetime:
    """Parses a date string in multiple formats."""
    formats = [
        "%Y-%m-%d",
        "%a %b %d, %Y",
        "%B %d, %Y",
        "%b %d, %Y",
        "%m/%d/%Y",
        "%d/%m/%Y",
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    
    print(f"⚠️  Warning: Could not parse date '{date_str}', using default")
    return datetime(2025, 1, 1)


def _format_deadlines(deadlines: List[dict]) -> str:
    """Formats deadlines for display"""
    if not deadlines:
        return "No major deadlines this week"
    
    result = []
    for d in deadlines:
        result.append(f"- {d.get('description', 'Unknown')}: {d.get('date', 'TBD')}")
    return '\n'.join(result)


def _extract_course_name(syllabus: str) -> str:
    """Extracts course name from syllabus"""
    lines = syllabus.split('\n')[:10]
    for line in lines:
        if 'CS' in line or 'Course' in line:
            return line.strip()
    return "Course"


def _extract_semester_term(syllabus: str) -> str:
    """Extracts semester term from syllabus"""
    if 'Fall 2025' in syllabus:
        return 'Fall 2025'
    elif 'Spring 2025' in syllabus:
        return 'Spring 2025'
    elif 'Fall 2026' in syllabus:
        return 'Fall 2026'
    elif 'Spring 2026' in syllabus:
        return 'Spring 2026'
    return 'Semester 2025'


def _validate_semester_info(info: SemesterInfo) -> SemesterInfo:
    """Validates and normalizes dates in semester info."""
    start_dt = _parse_date(info.start_date)
    end_dt = _parse_date(info.end_date)
    
    info.start_date = start_dt.strftime("%Y-%m-%d")
    info.end_date = end_dt.strftime("%Y-%m-%d")
    
    for deadline in info.key_deadlines:
        if 'date' in deadline:
            deadline_dt = _parse_date(deadline['date'])
            deadline['date'] = deadline_dt.strftime("%Y-%m-%d")
    
    return info


# ============ Core Agent Functions =============

def extract_semester_info(syllabus: str) -> SemesterInfo:
    """
    Public function to extract semester information.
    Can be called directly by frontend.
    """
    system_prompt = """You are analyzing a course syllabus to extract key information.

Extract the following:
1. Semester start and end dates
2. Total number of weeks (typically 15-16 for a semester)
3. All major deadlines (assignments, exams, presentations, projects)
4. Main topics or modules covered

CRITICAL DATE FORMAT RULES:
- ALL dates MUST be in YYYY-MM-DD format (e.g., "2025-08-29")
- For deadlines, the 'date' field MUST be YYYY-MM-DD format
- Convert any dates you find (like "Fri Aug 29, 2025") to YYYY-MM-DD format

Guidelines:
- Parse dates carefully from the syllabus
- For deadlines, extract both the date and what's due in this format:
  {"date": "2025-08-29", "description": "Student Introductions due"}
- Identify the major topics/themes of the course

Output format must match the SemesterInfo schema exactly.
"""

    structured_llm = llm.with_structured_output(SemesterInfo)
    
    result = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=syllabus)
    ])
    
    return _validate_semester_info(result)


def generate_multiple_weeks_batch(
    syllabus: str,
    semester_info: SemesterInfo,
    start_week: int,
    num_weeks: int,
    previous_weeks: List[WeeklyCalendar]
) -> List[WeeklyCalendar]:
    """
    Public function to generate multiple weeks in a batch.
    Can be called directly by frontend for regeneration.
    """
    start_date = _parse_date(semester_info.start_date)
    week_info = []
    
    for i in range(num_weeks):
        week_num = start_week + i
        week_start = start_date + timedelta(weeks=week_num - 1)
        week_end = week_start + timedelta(days=6)
        week_dates = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}"
        
        week_deadlines = []
        for deadline in semester_info.key_deadlines:
            try:
                deadline_date = _parse_date(deadline.get('date', '2025-01-01'))
                week_start_midnight = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
                week_end_midnight = week_end.replace(hour=23, minute=59, second=59)
                deadline_midnight = deadline_date.replace(hour=0, minute=0, second=0, microsecond=0)
                
                if week_start_midnight <= deadline_midnight <= week_end_midnight:
                    week_deadlines.append(deadline)
            except Exception:
                continue
        
        week_info.append({
            'week_number': week_num,
            'week_dates': week_dates,
            'deadlines': week_deadlines
        })
    
    previous_topics = []
    if previous_weeks:
        for prev_week in previous_weeks[-3:]:
            for day in prev_week.schedule:
                for block in day.blocks:
                    if block.topic not in previous_topics:
                        previous_topics.append(block.topic)
    
    system_prompt = f"""Generate {num_weeks} weekly SELF-STUDY calendars for weeks {start_week}-{start_week + num_weeks - 1} of {semester_info.total_weeks}.

Topics: {', '.join(semester_info.major_topics[:8])}
Previous: {', '.join(previous_topics[-8:]) if previous_topics else 'None'}

Week Details:
{chr(10).join([f"Week {w['week_number']} ({w['week_dates']}): {_format_deadlines(w['deadlines'])}" for w in week_info])}

Rules:
- Self-study only (reading, projects, review)
- 8-10 hrs/week, Monday-Friday
- 1-2 hour blocks
- Prioritize deadlines
- Build progressively

Output {num_weeks} WeeklyCalendar objects."""

    structured_llm = llm.with_structured_output(MultiWeekCalendar)
    
    result = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"Generate weeks {start_week}-{start_week + num_weeks - 1}")
    ])
    
    for i, calendar in enumerate(result.weeks):
        if i < len(week_info):
            calendar.week_number = week_info[i]['week_number']
            calendar.week_dates = week_info[i]['week_dates']
    
    return result.weeks


def generate_weeks_hybrid(
    syllabus: str, 
    semester_info: SemesterInfo,
    callback=None
) -> List[WeeklyCalendar]:
    """
    Generates all weeks using hybrid parallel approach.
    
    Args:
        syllabus: Course syllabus text
        semester_info: Extracted semester information
        callback: Optional callback function(wave_num, total_waves, weeks_completed, total_weeks)
    
    Returns:
        List of WeeklyCalendar objects
    """
    WEEKS_PER_BATCH = 2
    BATCHES_PER_WAVE = 2
    
    total_weeks = semester_info.total_weeks
    weeks_per_wave = WEEKS_PER_BATCH * BATCHES_PER_WAVE
    
    all_weeks = []
    
    wave_num = 1
    total_waves = (total_weeks + weeks_per_wave - 1) // weeks_per_wave
    
    for wave_start in range(1, total_weeks + 1, weeks_per_wave):
        wave_end = min(wave_start + weeks_per_wave - 1, total_weeks)
        
        if callback:
            callback(wave_num, total_waves, len(all_weeks), total_weeks)
        
        batch_configs = []
        for batch_start in range(wave_start, wave_end + 1, WEEKS_PER_BATCH):
            batch_end = min(batch_start + WEEKS_PER_BATCH - 1, wave_end)
            num_weeks = batch_end - batch_start + 1
            
            batch_configs.append({
                'start_week': batch_start,
                'num_weeks': num_weeks
            })
        
        with ThreadPoolExecutor(max_workers=len(batch_configs)) as executor:
            futures = {}
            
            for config in batch_configs:
                future = executor.submit(
                    generate_multiple_weeks_batch,
                    syllabus,
                    semester_info,
                    config['start_week'],
                    config['num_weeks'],
                    all_weeks
                )
                futures[future] = config['start_week']
            
            wave_results = []
            for future in as_completed(futures):
                batch_weeks = future.result()
                wave_results.extend(batch_weeks)
            
            wave_results.sort(key=lambda w: w.week_number)
            all_weeks.extend(wave_results)
        
        wave_num += 1
    
    return all_weeks


def generate_quiz(syllabus: str, semester_info: Optional[SemesterInfo]) -> QuizData:
    """
    Public function to generate quiz questions.
    """
    system_prompt = """Generate practice questions based on the course syllabus.

Guidelines:
- Focus on key concepts and learning outcomes
- Mix question types (conceptual, application-based)
- Generate 5-10 questions
- Make questions clear and specific
- Cover different difficulty levels
"""

    context = syllabus
    if semester_info:
        context += f"\n\nKey topics: {', '.join(semester_info.major_topics[:10])}"
    
    structured_llm = llm.with_structured_output(QuizData)
    
    quiz = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=context)
    ])
    
    return quiz


# ============ Agent Workflow Nodes =============

def planner_node(state: AgentState) -> AgentState:
    """Analyzes syllabus and creates execution plan."""
    system_prompt = """You are a study planning assistant.

Analyze the course syllabus and determine what study materials to generate.

Rules:
- First extract semester information (dates, deadlines, topics)
- Then generate a full semester calendar
- Generate quizzes if the syllabus mentions assignments, exams, or assessments
- Output ONLY the ordered list of steps needed

Available steps:
- extract_semester_info: Extracts key semester dates and deadlines
- generate_calendar: Creates full semester study schedule
- generate_quiz: Generates practice questions
"""

    planner_llm = llm.with_structured_output(Plan)
    
    plan = planner_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["syllabus"])
    ])
    
    return {
        **state,
        "plan": plan,
        "current_step_index": 0,
        "current_week": 1,
        "weeks_generated": [],
        "completed_steps": []
    }


def executor_node(state: AgentState) -> AgentState:
    """Central dispatcher that executes the next step in the plan."""
    plan = state["plan"]
    step_idx = state["current_step_index"]
    
    if not plan or step_idx >= len(plan.steps):
        return state
    
    current_step = plan.steps[step_idx]
    
    if current_step == "extract_semester_info":
        print("📊 Extracting semester information...")
        result = extract_semester_info(state["syllabus"])
        print(f"   ✓ Found {result.total_weeks} weeks, {len(result.key_deadlines)} deadlines")
        return {
            **state,
            "semester_info": result,
            "current_step_index": step_idx + 1,
            "completed_steps": state["completed_steps"] + ["extract_semester_info"]
        }
    
    elif current_step == "generate_calendar":
        semester_info = state.get("semester_info")
        
        if not semester_info:
            return {
                **state,
                "current_step_index": step_idx + 1,
                "completed_steps": state["completed_steps"] + ["generate_calendar"]
            }
        
        if state.get("weeks_generated"):
            print("📚 Compiling full semester calendar...")
            full_calendar = SemesterCalendar(
                course_name=_extract_course_name(state["syllabus"]),
                semester=_extract_semester_term(state["syllabus"]),
                weeks=state["weeks_generated"]
            )
            
            return {
                **state,
                "full_calendar": full_calendar,
                "current_step_index": step_idx + 1,
                "completed_steps": state["completed_steps"] + ["generate_calendar"]
            }
        
        print(f"⚡ Generating {semester_info.total_weeks} weeks using parallel batches...")
        all_weeks = generate_weeks_hybrid(state["syllabus"], semester_info)
        
        print("📚 Compiling full semester calendar...")
        full_calendar = SemesterCalendar(
            course_name=_extract_course_name(state["syllabus"]),
            semester=_extract_semester_term(state["syllabus"]),
            weeks=all_weeks
        )
        
        return {
            **state,
            "full_calendar": full_calendar,
            "weeks_generated": all_weeks,
            "current_step_index": step_idx + 1,
            "completed_steps": state["completed_steps"] + ["generate_calendar"]
        }
    
    elif current_step == "generate_quiz":
        print("📝 Generating practice quiz...")
        result = generate_quiz(state["syllabus"], state.get("semester_info"))
        print(f"   ✓ Created {len(result.questions)} questions")
        return {
            **state,
            "quiz": result,
            "current_step_index": step_idx + 1,
            "completed_steps": state["completed_steps"] + ["generate_quiz"]
        }
    
    return state


def should_continue(state: AgentState) -> Literal["executor", "end"]:
    """Routing function: Determines if there are more steps to execute."""
    plan = state["plan"]
    step_idx = state["current_step_index"]
    
    if not plan or step_idx >= len(plan.steps):
        return "end"
    
    return "executor"


# ============ Workflow Builder =============

def build_workflow() -> StateGraph:
    """Constructs the agent workflow graph."""
    graph = StateGraph(AgentState)
    
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "executor")
    
    graph.add_conditional_edges(
        "executor",
        should_continue,
        {
            "executor": "executor",
            "end": END
        }
    )
    
    return graph.compile()


# ============ High-Level API Functions =============

def generate_full_calendar(syllabus: str, callback=None) -> SemesterCalendar:
    """
    High-level function to generate a complete semester calendar.
    
    Args:
        syllabus: Course syllabus text
        callback: Optional callback function for progress updates
        
    Returns:
        Complete SemesterCalendar object
    """
    workflow = build_workflow()
    
    initial_state = {
        "syllabus": syllabus,
        "plan": None,
        "current_step_index": 0,
        "semester_info": None,
        "current_week": 1,
        "weeks_generated": [],
        "full_calendar": None,
        "quiz": None,
        "completed_steps": []
    }
    
    result = workflow.invoke(initial_state)
    
    return result.get("full_calendar")


def regenerate_weeks(
    syllabus: str,
    semester_info: SemesterInfo,
    week_numbers: List[int],
    existing_calendar: SemesterCalendar,
    callback=None
) -> SemesterCalendar:
    """
    Regenerates specific weeks in an existing calendar.
    
    Args:
        syllabus: Course syllabus text
        semester_info: Semester information
        week_numbers: List of week numbers to regenerate
        existing_calendar: Current calendar to update
        callback: Optional callback function for progress updates
        
    Returns:
        Updated SemesterCalendar object
    """
    regenerated_weeks = []
    
    for i, week_num in enumerate(sorted(week_numbers)):
        if callback:
            callback(i + 1, len(week_numbers), week_num)
        
        previous_weeks = [w for w in existing_calendar.weeks if w.week_number < week_num]
        
        new_week = generate_multiple_weeks_batch(
            syllabus,
            semester_info,
            week_num,
            1,
            previous_weeks
        )
        regenerated_weeks.extend(new_week)
    
    updated_weeks = existing_calendar.weeks.copy()
    for new_week in regenerated_weeks:
        for i, week in enumerate(updated_weeks):
            if week.week_number == new_week.week_number:
                updated_weeks[i] = new_week
                break
    
    existing_calendar.weeks = updated_weeks
    
    return existing_calendar
