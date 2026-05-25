import streamlit as st
import streamlit_shadcn_ui as ui
import pandas as pd
import psycopg2 
import hashlib
import random
import datetime
import calendar
import plotly.graph_objects as go

# ==========================================
# 💌 선생님 전용: 응원 메시지 보관함
# ==========================================
ENCOURAGING_MESSAGES = [
    "오늘 하루도 넌 충분히 빛나고 있어! ✨",
    "너의 마음을 솔직하게 말해줘서 고마워. 푹 쉬고 내일 또 웃으며 만나자. 💖",
    "힘든 일도 다 지나갈 거야. 선생님은 늘 네 편이란다. 🌈",
    "스스로 마음을 돌아볼 줄 아는 넌 정말 멋진 사람이야! 👍",
    "마음 배터리 충전 완료! 오늘 하루도 기분 좋게 보내길 바라. 🔋"
]

# ==========================================
# 1. 시스템 설정 및 데이터베이스 초기화
# ==========================================
st.set_page_config(page_title="요즘 내 기분은", page_icon="🌈", layout="wide")

def get_db_connection():
    return psycopg2.connect(st.secrets["db_url"])

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. 기본 테이블 생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            role TEXT DEFAULT 'student',
            grade INTEGER,
            room INTEGER,
            number INTEGER,
            sex TEXT DEFAULT 'male',
            name TEXT,
            password_hash TEXT,
            UNIQUE(grade, room, number, role)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            month INTEGER DEFAULT 5,
            week INTEGER,
            score REAL
        )
    """)
    # [신규] 학급별 설정 테이블 (③번 - 학급 기본 α)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS class_settings (
            id SERIAL PRIMARY KEY,
            school TEXT,
            grade INTEGER,
            room INTEGER,
            default_alpha REAL DEFAULT 0.6,
            UNIQUE(school, grade, room)
        )
    """)
    conn.commit()
    
    # 2. month 컬럼 추가 (기존 호환)
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='records' AND column_name='month'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE records ADD COLUMN month INTEGER DEFAULT 5")
            conn.commit()
    except Exception:
        conn.rollback()
        
    # 3. records 고유 제약조건 업데이트
    try:
        cursor.execute("ALTER TABLE records DROP CONSTRAINT IF EXISTS records_user_id_week_key")
        cursor.execute("ALTER TABLE records ADD CONSTRAINT records_user_id_month_week_key UNIQUE(user_id, month, week)")
        conn.commit()
    except Exception:
        conn.rollback()  
        
    # 4. sex 컬럼 추가
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='sex'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE users ADD COLUMN sex TEXT DEFAULT 'male'")
            conn.commit()
    except Exception:
        conn.rollback()
    
    # 5. [신규] users 테이블에 school 컬럼 추가 (②번 - 다교사)
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='school'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE users ADD COLUMN school TEXT")
            conn.commit()
    except Exception:
        conn.rollback()
    
    # 6. [신규] users 테이블에 teacher_grade, teacher_room 컬럼 (②번)
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='teacher_grade'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE users ADD COLUMN teacher_grade INTEGER")
            cursor.execute("ALTER TABLE users ADD COLUMN teacher_room INTEGER")
            conn.commit()
    except Exception:
        conn.rollback()
    
    # 7. [신규] users 테이블에 custom_alpha 컬럼 (③번 - 학생 개별 α)
    try:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='custom_alpha'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE users ADD COLUMN custom_alpha REAL")
            conn.commit()
    except Exception:
        conn.rollback()
        
    conn.close()

init_db()

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# ==========================================
# [신규 함수] 현재 날짜 기준 자동 월/주차 계산 (④번)
# ==========================================
def get_current_month_week():
    """오늘 날짜 기준으로 (월, 주차) 자동 계산"""
    today = datetime.date.today()
    year, month, day = today.year, today.month, today.day
    
    # 이번 달의 모든 월요일 찾기
    num_days = calendar.monthrange(year, month)[1]
    mondays = []
    for d in range(1, num_days + 1):
        if datetime.date(year, month, d).weekday() == 0:
            mondays.append(d)
    
    # 오늘이 속한 주차 계산 (가장 가까운 이전 월요일 기준)
    week_num = 1
    for i, mday in enumerate(mondays):
        if mday <= day:
            week_num = i + 1
        else:
            break
    
    return month, week_num, year, mondays[week_num - 1]

# ==========================================
# [신규 함수] 학급 기본 α 조회 (③번)
# ==========================================
def get_class_alpha(school, grade, room):
    """해당 학급의 기본 α 값 조회. 없으면 0.6 기본값"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT default_alpha FROM class_settings WHERE school=%s AND grade=%s AND room=%s",
                   (school, grade, room))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else 0.6

# ==========================================
# [신규 함수] 학생용 α 계산 (학생 개별 우선, 없으면 학급 기본)
# ==========================================
def get_effective_alpha(student_id, school, grade, room):
    """학생 개별 α가 있으면 그걸, 없으면 학급 기본 α 사용"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT custom_alpha FROM users WHERE id=%s", (student_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] is not None:
        return row[0]
    return get_class_alpha(school, grade, room)

# ==========================================
# 세션 상태 초기화
# ==========================================
if "login_user_id" not in st.session_state: st.session_state.login_user_id = None
if "login_user_name" not in st.session_state: st.session_state.login_user_name = None
if "login_user_sex" not in st.session_state: st.session_state.login_user_sex = None
if "login_user_school" not in st.session_state: st.session_state.login_user_school = None
if "login_user_grade" not in st.session_state: st.session_state.login_user_grade = None
if "login_user_room" not in st.session_state: st.session_state.login_user_room = None
if "login_role" not in st.session_state: st.session_state.login_role = None
if "needs_password_change" not in st.session_state: st.session_state.needs_password_change = False
if "current_step" not in st.session_state: st.session_state.current_step = 0
if "survey_responses" not in st.session_state: st.session_state.survey_responses = {}
if "survey_completed" not in st.session_state: st.session_state.survey_completed = False
if "question_order" not in st.session_state: st.session_state.question_order = None  # ①번 - 셔플 순서

# ==========================================
# 2. 모던 스타일 CSS
# ==========================================
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
    
    /* ============================================================
       Fresh Green Theme v2 — 강력 적용 버전
       메인 포인트: #6BBE5A (녹색)
       정책: 질문/답변에 무조건 시선 집중
       ============================================================ */
    
    :root {
        --bg-main: #F5F4F1;
        --bg-card: #FFFFFF;
        --bg-answer-zone: #F4FAF1;
        --ink-strong: #2D3B2A;
        --ink-soft: #5C6B58;
        --ink-light: #9BA597;
        --green: #6BBE5A;
        --green-deep: #4A9A3E;
        --green-soft: #A8DB9C;
        --green-light: #E8F5E4;
        --green-bg: #F4FAF1;
        --coral: #FF9F66;
        --coral-light: #FFEDDD;
        --blue: #7AA8E8;
        --blue-light: #E1ECFA;
        --border-soft: #E8E6E0;
        --border-green: #BFE3B3;
        --shadow-card: 0 6px 24px rgba(45, 59, 42, 0.06);
        --shadow-hover: 0 12px 32px rgba(45, 59, 42, 0.10);
    }
    
    html, body, [data-testid="stAppViewContainer"], .stApp {
        background: var(--bg-main) !important;
        font-family: 'Pretendard', -apple-system, BlinkMacSystemFont, sans-serif !important;
        color: var(--ink-strong) !important;
    }
    [data-testid="stHeader"] { background: transparent !important; }
    
    /* ============================================================
       전체 폭 확대 — 컨테이너 좌우 여백 크게 줄임
       ============================================================ */
    .block-container { 
        padding: 1.2rem 1.5rem !important; 
        max-width: 100% !important;
    }
    @media (min-width: 768px) {
        .block-container { 
            padding: 1.5rem 4% !important; 
            max-width: 1280px !important;
            margin: 0 auto !important;
        }
    }
    
    /* ===== 일반 카드 (Streamlit container border=True) ===== */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: var(--bg-card) !important;
        border: 1px solid var(--border-soft) !important;
        border-radius: 22px !important;
        box-shadow: var(--shadow-card) !important;
        padding: 3rem 2.5rem !important;
        margin-top: 1.2rem !important;
        transition: box-shadow 0.25s ease !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        box-shadow: var(--shadow-hover) !important;
    }
    @media (max-width: 768px) {
        div[data-testid="stVerticalBlockBorderWrapper"] { padding: 2rem 1.4rem !important; border-radius: 18px !important; }
    }
    
    /* ===== 헤딩 ===== */
    h1 {
        color: var(--ink-strong) !important;
        font-weight: 800 !important; font-size: 2.0rem !important; letter-spacing: -0.02em !important;
        text-align: center !important; margin-bottom: 0.4rem !important;
    }
    h2, h3 { color: var(--ink-strong) !important; font-weight: 800 !important; letter-spacing: -0.01em !important; }
    p, span, div { color: var(--ink-strong); }
    
    /* ===== 입력 필드 ===== */
    div[data-testid="stTextInput"] input, 
    div[data-testid="stNumberInput"] input {
        background-color: #FFFFFF !important; border: 1.5px solid var(--border-soft) !important;
        border-radius: 12px !important; color: var(--ink-strong) !important;
        font-size: 1rem !important; padding: 12px 16px !important; transition: all 0.2s ease !important;
    }
    div[data-testid="stTextInput"] input:focus, div[data-testid="stNumberInput"] input:focus {
        border-color: var(--green) !important; box-shadow: 0 0 0 4px rgba(107, 190, 90, 0.15) !important; outline: none !important;
    }
    
    /* ===== 셀렉트박스 ===== */
    div[data-baseweb="select"] > div {
        background-color: #FFFFFF !important; border: 1.5px solid var(--border-soft) !important;
        border-radius: 12px !important; transition: all 0.2s ease !important;
    }
    div[data-baseweb="select"]:hover > div { border-color: var(--green-soft) !important; }
    div[data-baseweb="select"] div[data-baseweb="select-control"] *,
    div[data-baseweb="select"] span, div[data-baseweb="select"] div { color: var(--ink-strong) !important; }
    ul[role="listbox"] { background-color: #FFFFFF !important; border-radius: 12px !important; }
    ul[role="listbox"] li { color: var(--ink-strong) !important; background-color: #FFFFFF !important; }
    ul[role="listbox"] li:hover { background-color: var(--green-light) !important; color: var(--ink-strong) !important; }
    
    /* ============================================================
       ⭐⭐⭐ 핵심 1: 질문 텍스트 — 흰 둥근 네모, 부모 풀 폭
       ============================================================ */
    .question-text,
    p.question-text,
    div.question-text { 
        font-size: 1.85rem !important; 
        font-weight: 800 !important; 
        line-height: 1.6 !important; 
        color: var(--ink-strong) !important;
        margin: 16px 0 28px 0 !important;
        text-align: center !important; 
        word-break: keep-all !important;
        letter-spacing: -0.02em !important;
        background: #FFFFFF !important;
        border: 1.5px solid var(--border-soft) !important;
        border-radius: 20px !important;
        padding: 32px 36px !important;
        width: 100% !important;
        box-sizing: border-box !important;
        box-shadow: 0 4px 16px rgba(45, 59, 42, 0.06) !important;
    }
    
    /* ============================================================
       ⭐⭐⭐ 핵심 2: 답변 라디오 — 질문과 동일한 폭(부모 카드 풀 폭)
       
       Streamlit 라디오 구조:
       <div data-testid="stRadio">             ← 풀 폭
         <label>(위젯 라벨, collapsed로 숨김)
         <div role="radiogroup">                ← 풀 폭 컨테이너
           <label data-baseweb="radio">         ← 풀 폭 흰 카드
             <div>(라디오 동그라미)
             <div>(텍스트)
       ============================================================ */
    
    /* stRadio 위젯 — 부모 폭 풀 사용 (질문과 동일) */
    div[data-testid="stRadio"] {
        width: 100% !important;
        margin: 0 0 28px 0 !important;
    }
    
    /* 라디오 옵션 컨테이너 — 풀 폭 세로 정렬 */
    div[data-testid="stRadio"] > div[role="radiogroup"],
    div[data-testid="stRadio"] > div:not([data-testid]),
    div.row-widget.stRadio > div { 
        gap: 14px !important; 
        margin: 0 !important;
        padding: 0 !important;
        background: transparent !important;
        border: none !important;
        width: 100% !important;
        display: flex !important;
        flex-direction: column !important;
    }
    
    /* 각 답변 라벨 = 흰 카드 (질문과 동일한 폭, 동일한 좌우 정렬) */
    div[data-testid="stRadio"] label[data-baseweb="radio"],
    div.row-widget.stRadio label {
        background: #FFFFFF !important; 
        border: 2px solid var(--border-soft) !important;
        border-radius: 20px !important; 
        padding: 22px 36px !important;
        transition: all 0.2s ease !important; 
        cursor: pointer !important;
        box-shadow: 0 3px 12px rgba(45, 59, 42, 0.06) !important;
        min-height: 80px !important;
        width: 100% !important;
        box-sizing: border-box !important;
        margin: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        gap: 18px !important;
    }
    
    /* hover */
    div[data-testid="stRadio"] label[data-baseweb="radio"]:hover,
    div.row-widget.stRadio label:hover {
        border-color: var(--green-soft) !important; 
        background: #FAFFF8 !important;
        box-shadow: 0 8px 22px rgba(107, 190, 90, 0.18) !important;
        transform: translateY(-1px) !important;
    }
    
    /* ⭐ 선택된 라벨 = 강한 강조 */
    div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked),
    div.row-widget.stRadio label:has(input:checked) {
        border: 2.5px solid var(--green) !important;
        background: var(--green-light) !important;
        box-shadow: 0 8px 24px rgba(107, 190, 90, 0.28) !important;
        transform: translateY(-1px) !important;
    }
    /* 선택된 라벨의 텍스트 — 더 진하고 굵게 */
    div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p,
    div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) div[data-testid="stMarkdownContainer"] p,
    div.row-widget.stRadio label:has(input:checked) p {
        color: var(--green-deep) !important;
        font-weight: 800 !important;
    }
    
    /* ============================================================
       라디오 동그라미 — 표준 라디오 모양 (도넛: 바깥 원 + 안 점)
       ============================================================ */
    /* 동그라미 컨테이너 (첫번째 자식) */
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child {
        flex-shrink: 0 !important;
        background-color: transparent !important;
        width: 24px !important;
        height: 24px !important;
        position: relative !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    /* 바깥 원 — 항상 회색 보더 (선택 상태 무관) */
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child > div {
        width: 22px !important;
        height: 22px !important;
        border: 2px solid #C4C8C0 !important;
        border-radius: 50% !important;
        background-color: #FFFFFF !important;
        box-sizing: border-box !important;
        position: relative !important;
        display: block !important;
    }
    /* hover 시 바깥 원 보더만 살짝 진해짐 */
    div[data-testid="stRadio"] label[data-baseweb="radio"]:hover > div:first-child > div {
        border-color: var(--green-soft) !important;
    }
    /* 선택된 상태: 바깥 원은 녹색 보더 + 안에 점 */
    div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-child > div {
        border-color: var(--green) !important;
        background-color: #FFFFFF !important;
    }
    /* 안쪽 점 — ::after 의사 요소로 그림 */
    div[data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) > div:first-child > div::after {
        content: '' !important;
        position: absolute !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        width: 12px !important;
        height: 12px !important;
        border-radius: 50% !important;
        background-color: var(--green) !important;
    }
    
    /* 텍스트 wrapper(마지막 자식) — 왼쪽 정렬 */
    div[data-testid="stRadio"] label[data-baseweb="radio"] > div:last-child {
        flex: 1 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: flex-start !important;
        text-align: left !important;
    }
    
    /* 답변 텍스트 — 왼쪽 정렬, 크고 진하게 */
    div[data-testid="stRadio"] label[data-baseweb="radio"] p,
    div[data-testid="stRadio"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"],
    div[data-testid="stRadio"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] p { 
        line-height: 1.7 !important; 
        font-size: 1.25rem !important; 
        color: var(--ink-strong) !important;
        font-weight: 700 !important; 
        word-break: keep-all !important; 
        white-space: pre-wrap !important;
        text-align: left !important;
        margin: 0 !important;
        width: 100% !important;
    }
    
    label { color: var(--ink-strong) !important; font-weight: 600 !important; }
    
    /* ============================================================
       일반 버튼 (이전 등) — 흰 배경
       ============================================================ */
    .stButton > button {
        width: 100% !important; font-size: 1.1rem !important; font-weight: 700 !important;
        padding: 14px 22px !important; border-radius: 14px !important;
        background: #FFFFFF !important;
        color: var(--ink-strong) !important; 
        border: 2px solid var(--border-soft) !important;
        box-shadow: 0 2px 8px rgba(45, 59, 42, 0.06) !important;
        transition: all 0.2s ease !important; letter-spacing: -0.01em !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        border-color: var(--green) !important;
        color: var(--green-deep) !important;
        box-shadow: 0 6px 18px rgba(107, 190, 90, 0.18) !important;
    }
    .stButton > button:active { transform: translateY(0) !important; }
    
    /* ============================================================
       Primary 버튼 (다음/제출) — 녹색 + 흰 글자 (자식까지 강제)
       ============================================================ */
    .stButton > button[kind="primary"],
    .stButton > button[kind="primary"] *,
    .stButton > button[kind="primary"] p,
    .stButton > button[kind="primary"] div,
    .stButton > button[kind="primary"] span {
        background: var(--green) !important;
        color: #FFFFFF !important;
        border: none !important;
    }
    .stButton > button[kind="primary"] {
        background: var(--green) !important;
        color: #FFFFFF !important;
        border: none !important;
        box-shadow: 0 6px 18px rgba(107, 190, 90, 0.30) !important;
        font-weight: 800 !important;
    }
    .stButton > button[kind="primary"]:hover,
    .stButton > button[kind="primary"]:hover *,
    .stButton > button[kind="primary"]:hover p,
    .stButton > button[kind="primary"]:hover div,
    .stButton > button[kind="primary"]:hover span {
        background: var(--green-deep) !important;
        color: #FFFFFF !important;
    }
    .stButton > button[kind="primary"]:hover {
        box-shadow: 0 10px 26px rgba(74, 154, 62, 0.40) !important;
        transform: translateY(-2px) !important;
    }
    
    /* ===== 진행바 — 녹색 ===== */
    div[data-testid="stProgress"] > div > div > div {
        background: var(--green) !important;
        border-radius: 10px !important; height: 10px !important;
    }
    div[data-testid="stProgress"] > div > div {
        background-color: var(--green-light) !important; border-radius: 10px !important; height: 10px !important;
    }
    
    /* ===== 사이드바 ===== */
    [data-testid="stSidebar"] {
        background: #FFFFFF !important;
        border-right: 1px solid var(--border-soft) !important;
    }
    [data-testid="stSidebar"] h1 { font-size: 1.4rem !important; }
    
    /* ===== 알림 ===== */
    div[data-testid="stAlert"] {
        border-radius: 14px !important; border: none !important; padding: 14px 18px !important;
        box-shadow: 0 2px 10px rgba(45, 59, 42, 0.05) !important;
        background: var(--green-light) !important;
    }
    div[data-testid="stAlert"] * { color: var(--ink-strong) !important; }
    div[data-testid="stDataFrame"] {
        border-radius: 14px !important; overflow: hidden !important; 
        box-shadow: 0 2px 10px rgba(45, 59, 42, 0.06) !important;
    }
    div[data-testid="stCaptionContainer"] { 
        text-align: center !important; color: var(--ink-light) !important; font-weight: 500 !important; 
    }
    div[data-testid="stExpander"] {
        border-radius: 14px !important; border: 1px solid var(--border-soft) !important;
        background: #FFFFFF !important;
    }
    
    /* ===== 이모지 뱃지 ===== */
    .emoji-badge {
        display: flex; align-items: center; justify-content: center;
        width: 100px; height: 100px; margin: 0 auto 22px auto;
        background: var(--green-light);
        border-radius: 50%; font-size: 3.6rem;
        box-shadow: 0 8px 22px rgba(107, 190, 90, 0.20);
    }
    
    /* ===== Hero 헤더 (설문 진행 중) — 컴팩트 한 줄 ===== */
    .hero-header {
        text-align: center; padding: 12px 18px;
        background: #FFFFFF;
        border: 1px solid var(--border-soft);
        border-radius: 14px; margin-bottom: 16px;
        box-shadow: var(--shadow-card);
        display: flex; align-items: center; justify-content: center; gap: 12px;
        flex-wrap: wrap;
    }
    .hero-header .hero-emoji { font-size: 1.5rem; margin: 0; display: inline-block; }
    .hero-header h2 {
        color: var(--ink-strong) !important;
        font-weight: 700; font-size: 1.05rem; margin: 0; display: inline-block;
    }
    .hero-header p { 
        color: var(--ink-soft); font-size: 0.85rem; margin: 0; font-weight: 500;
        display: inline-block;
    }
    
    /* ===== Hero 헤더 LARGE (로그인 전) ===== */
    .hero-header-lg {
        text-align: center; padding: 28px 24px;
        background: #FFFFFF;
        border: 1px solid var(--border-soft);
        border-radius: 20px; margin-bottom: 22px;
        box-shadow: var(--shadow-card);
    }
    .hero-header-lg .hero-emoji { font-size: 2.8rem; margin-bottom: 10px; display: inline-block; }
    .hero-header-lg h2 {
        color: var(--ink-strong) !important;
        font-weight: 800; font-size: 1.6rem; margin: 0;
    }
    .hero-header-lg p { color: var(--ink-soft); font-size: 0.98rem; margin: 6px 0 0 0; font-weight: 500; }
    
    /* ===== 완료 카드 ===== */
    .completion-card {
        text-align: center; padding: 44px 32px;
        background: #FFFFFF;
        border: 1px solid var(--border-soft);
        border-radius: 24px; box-shadow: var(--shadow-card);
        margin-top: 20px;
    }
    .completion-card .big-emoji { font-size: 4.5rem; margin-bottom: 16px; display: inline-block; }
    .completion-card .message {
        background: var(--green-light); 
        border-radius: 16px; padding: 24px 20px; margin-top: 20px;
        font-size: 1.2rem; font-weight: 700; color: var(--ink-strong); line-height: 1.7;
    }
    
    /* ===== 반응형 ===== */
    @media (max-width: 768px) {
        h1 { font-size: 1.5rem !important; }
        .question-text { 
            font-size: 1.35rem !important; 
            padding: 22px 20px !important;
            border-radius: 16px !important;
        }
        div[data-testid="stRadio"] label[data-baseweb="radio"],
        div.row-widget.stRadio label { 
            padding: 18px 18px 18px 18px !important; 
            min-height: 70px !important;
            gap: 14px !important;
        }
        div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child,
        div[data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child > div {
            width: 22px !important;
            height: 22px !important;
        }
        div[data-testid="stRadio"] label[data-baseweb="radio"] p,
        div[data-testid="stRadio"] label[data-baseweb="radio"] div[data-testid="stMarkdownContainer"] p { 
            font-size: 1.05rem !important; 
        }
        .emoji-badge { width: 80px; height: 80px; font-size: 2.8rem; }
        .stButton > button { font-size: 1rem !important; padding: 12px !important; }
        .hero-header { padding: 10px 14px; gap: 8px; }
        .hero-header h2 { font-size: 0.95rem; }
    }
    </style>
""", unsafe_allow_html=True)

SURVEY_DATA = {
    "depression": {"icon": "🖥️", "question": "지금 당장 내가 제일 좋아하는 유튜브 영상이나 게임을 볼 수 있다면,<br>내 마음이 어떨 것 같나요?", "options": ["평소처럼 생각만 해도 신나고 빨리 보고 싶다.", "오늘따라 귀찮거나 별로 하고 싶은 생각이 안 든다."], "weight_m": 1.60, "weight_f": 1.17},
    "loneliness": {"icon": "🍱", "question": "오늘 학교 쉬는 시간이나 점심시간에 보낼 내 모습을 상상해보면,<br>내 마음이 어떨 것 같나요?", "options": ["친구들과 신나게 어울려 놀거나,\n혹은 혼자서 책 읽기나 그리기를 하더라도 내 마음이 편안하고 만족스러울 것 같다.", "같이 놀거나 이야기할 친구가 없어서 교실에 가만히 있거나,\n어떻게 시간을 보내야 할지 몰라 마음이 불안하고 쓸쓸할 것 같다."], "weight_m": 0.90, "weight_f": 0.91},
    "stress": {"icon": "📝", "question": "오늘 학교에서 예상하지 못한 작은 과제나 귀찮은 일이 갑자기 생긴다면,<br>내 마음이 어떨 것 같나요?", "options": ["'얼른 해버려야지!' 하고 가벼운 마음으로 편안하게 받아들일 수 있을 것 같다.", "오늘따라 마음의 여유가 없어서, 아주 작은 일 하나도 평소보다 훨씬 더 무겁고 답답하게 느껴질 것 같다."], "weight_m": 0.97, "weight_f": 0.97},
    "anxiety": {"icon": "🎮", "question": "이번 주 일주일 동안 일어날 일들을 생각할 때,<br>걱정하는 마음 때문에 지금 내가 해야 할 공부나 놀이에 집중하기가 힘든가요?", "options": ["걱정이 조금 되더라도, 내가 할 일이나 친구들과 노는 것에는 별로 지장이 없다.", "걱정스러운 생각이 머릿속을 가득 채워서, 다른 일에 집중하기 어렵고 마음이 온통 그곳에 쏠려 있다."], "weight_m": 0.76, "weight_f": 0.80},
    "sleep_deprivation": {"icon": "🔋", "question": "오늘 아침에 눈을 떴을 때,<br>내 몸과 마음의 배터리가 어느 정도 충전된 느낌이었나요?", "options": ["이불 속에서 조금 더 자고 싶긴 했지만,\n막상 일어나서 세수를 하니 평소처럼 학교에 가서 활동할 에너지는 충분한 것 같다.", "잠을 자긴 했는데 피로가 전혀 풀리지 않은 것처럼 온몸이 무겁고,\n하루를 시작하기도 전에 이미 에너지가 바닥난 것처럼 지친다."], "weight_m": 0.22, "weight_f": 0.19}
}

# ==========================================
# 3. 사이드바 제어판
# ==========================================
st.sidebar.title("🔐 시스템 제어판")
if st.session_state.login_user_id is not None:
    st.sidebar.success(f"🟩 {st.session_state.login_user_name}님")
    if st.sidebar.button("로그아웃"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()
else:
    app_mode = st.sidebar.radio("접속 권한 선택", ["🧑‍🎓 학생용 채널", "🧑‍🏫 교사 관리자 채널"])

# ==========================================
# 🧑‍🎓 4. 학생용 채널
# ==========================================
if st.session_state.login_user_id is None and 'app_mode' in locals() and app_mode == "🧑‍🎓 학생용 채널":
    st.markdown("""
        <div class="hero-header-lg">
            <div class="hero-emoji">🌈</div>
            <h2>오늘 하루 나의 기분은?</h2>
            <p>여러분의 마음을 기록하는 안전한 공간이에요 💖</p>
        </div>
    """, unsafe_allow_html=True)
    
    _, center_col, _ = st.columns([1, 8, 1])
    with center_col:
        with st.container(border=True):
            st.subheader("🧑‍🎓 학생 로그인 및 등록")
            
            # [수정] 학교 입력 추가 (②번 - 다교사 지원)
            s_school = st.text_input("🏫 학교 이름", placeholder="예: 한국초등학교")
            
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1: s_grade = st.selectbox("학년", list(range(1, 7)), index=3)
            with c2: s_room = st.selectbox("반", list(range(1, 13)), index=0)
            with c3: s_num_tens = st.selectbox("번호(십)", list(range(0, 10)), index=0)
            with c4: s_num_units = st.selectbox("번호(일)", list(range(0, 10)), index=1)
            with c5: s_sex_kor = st.selectbox("성별", ["남자", "여자"])
            
            s_number = s_num_tens * 10 + s_num_units
            s_sex = 'male' if s_sex_kor == "남자" else 'female'
            
            s_name = st.text_input("이름")
            s_password = st.text_input("비밀번호 (8자 ~ 16자)", type="password")
            
            if st.button("🚪 학생 로그인 / 최초 등록", type="primary"):
                if not s_school: st.error("❌ 학교 이름을 입력해 주세요.")
                elif s_number == 0: st.error("❌ 번호는 1번 이상이어야 합니다.")
                elif not s_name or not s_password: st.error("❌ 이름과 비밀번호를 모두 입력해 주세요.")
                elif not (8 <= len(s_password) <= 16): st.error("❌ 비밀번호는 반드시 8자 이상, 16자 이하여야 합니다.")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, name, password_hash, sex, school FROM users WHERE school=%s AND grade=%s AND room=%s AND number=%s AND role='student'", 
                                   (s_school, s_grade, s_room, s_number))
                    user = cursor.fetchone()
                    hashed_pw = make_hash(s_password)
                    
                    if user is None:
                        try:
                            cursor.execute("""INSERT INTO users (role, school, grade, room, number, sex, name, password_hash) 
                                              VALUES ('student', %s, %s, %s, %s, %s, %s, %s)""", 
                                           (s_school, s_grade, s_room, s_number, s_sex, s_name, hashed_pw))
                            conn.commit()
                            cursor.execute("SELECT id, sex FROM users WHERE school=%s AND grade=%s AND room=%s AND number=%s AND role='student'", 
                                           (s_school, s_grade, s_room, s_number))
                            new_user = cursor.fetchone()
                            st.session_state.login_user_id = new_user[0]
                            st.session_state.login_user_sex = new_user[1]
                            st.session_state.login_user_school = s_school
                            st.session_state.login_user_grade = s_grade
                            st.session_state.login_user_room = s_room
                            st.session_state.login_user_name = f"{s_grade}학년 {s_room}반 {s_number}번 {s_name}"
                            st.session_state.login_role = "student"
                            st.session_state.needs_password_change = (s_password == "12345678")
                            st.rerun()
                        except psycopg2.IntegrityError: st.error("❌ 이미 등록된 학적 정보입니다.")
                    else:
                        if user[2] == hashed_pw:
                            if user[1] != s_name: st.error("❌ 등록된 학생 이름과 다릅니다.")
                            else:
                                st.session_state.login_user_id = user[0]
                                st.session_state.login_user_sex = user[3]
                                st.session_state.login_user_school = user[4]
                                st.session_state.login_user_grade = s_grade
                                st.session_state.login_user_room = s_room
                                st.session_state.login_user_name = f"{s_grade}학년 {s_room}반 {s_number}번 {s_name}"
                                st.session_state.login_role = "student"
                                st.session_state.needs_password_change = (s_password == "12345678")
                                st.rerun()
                        else: st.error("❌ 비밀번호가 올바르지 않습니다.")
                    conn.close()

elif st.session_state.login_user_id and st.session_state.login_role == "student":
    if st.session_state.needs_password_change:
        st.title("🔒 안전을 위한 비밀번호 변경")
        _, change_col, _ = st.columns([1, 4, 1])
        with change_col:
            with st.container(border=True):
                new_pw = st.text_input("새로운 비밀번호 (8자 ~ 16자)", type="password")
                new_pw_confirm = st.text_input("새로운 비밀번호 확인", type="password")
                if st.button("🔐 변경 완료 후 입장하기", type="primary"):
                    if not (8 <= len(new_pw) <= 16): st.error("❌ 8자 이상, 16자 이하여야 합니다.")
                    elif new_pw == "12345678": st.error("❌ 임시 비밀번호는 쓸 수 없습니다.")
                    elif new_pw != new_pw_confirm: st.error("❌ 두 비밀번호가 다릅니다.")
                    else:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (make_hash(new_pw), st.session_state.login_user_id))
                        conn.commit()
                        conn.close()
                        st.session_state.needs_password_change = False
                        st.success("🎉 변경 완료!")
                        st.rerun()
    else:
        if st.session_state.survey_completed:
            st.balloons()
            st.markdown(f"""
                <div class="hero-header-lg">
                    <div class="hero-emoji">🌈</div>
                    <h2>{st.session_state.login_user_name} 친구, 정말 고생했어요!</h2>
                    <p>마음을 솔직하게 들려줘서 고마워요 💝</p>
                </div>
            """, unsafe_allow_html=True)
            random_message = random.choice(ENCOURAGING_MESSAGES)
            st.markdown(f"""
                <div class="completion-card">
                    <div class="big-emoji">🎉</div>
                    <h3 style="color:#2D3B2A; font-weight:800; margin:0;">마음 전달이 완료되었어요!</h3>
                    <div class="message">💌 {random_message}</div>
                    <p style="color:#5C6B58; font-size:0.95rem; margin-top:20px; font-weight:500;">
                        선생님께서 소중한 마음을 확인하실 거예요.<br>
                        안전을 위해 왼쪽의 <b>[로그아웃]</b> 버튼을 눌러주세요.
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
        else:
            st.markdown(f"""
                <div class="hero-header">
                    <span class="hero-emoji">🌈</span>
                    <h2>{st.session_state.login_user_name} 친구, 환영해요!</h2>
                    <p>마음 가는 대로 솔직하게 답해주면 돼요 💝</p>
                </div>
            """, unsafe_allow_html=True)
            
            # ===== ①번 개선: 문항 순서 셔플 =====
            # 학생 한 번 입장 시 셔플된 순서를 세션에 저장 (중간에 바뀌지 않도록)
            if st.session_state.question_order is None:
                keys = list(SURVEY_DATA.keys())
                random.shuffle(keys)
                st.session_state.question_order = keys
            
            keys = st.session_state.question_order
            total_steps = len(keys)
            step = st.session_state.current_step
            key = keys[step]
            data = SURVEY_DATA[key]
            
            # 설문은 풀 폭으로 표시 (질문/답변 시선 집중)
            # ===== ④번 개선: 학생은 월/주차 선택 불가, 자동 결정 =====
            if step == 0:
                auto_month, auto_week, auto_year, auto_monday_day = get_current_month_week()
                st.session_state.select_month = auto_month
                st.session_state.select_week = auto_week
                
                st.info(f"📅 **{auto_year}년 {auto_month}월 {auto_week}주차** ({auto_month}월 {auto_monday_day}일 주) 기록입니다.\n\n오늘 날짜를 기준으로 자동 입력되었어요.")
            
            st.progress((step + 1) / total_steps)
            st.caption(f"총 {total_steps}개 질문 중 {step + 1}번째 질문")
            
            with st.container(border=True):
                st.markdown(f"<div class='emoji-badge'>{data['icon']}</div>", unsafe_allow_html=True)
                st.markdown(f"<p class='question-text'>{data['question']}</p>", unsafe_allow_html=True)
                
                current_val = st.session_state.survey_responses.get(key, 0)
                default_idx = 1 if current_val == 1 else 0
                choice = st.radio(" ", data["options"], index=default_idx, label_visibility="collapsed", key=f"radio_{key}")
                st.session_state.survey_responses[key] = 1 if choice == data["options"][1] else 0

            col_prev, col_blank, col_next = st.columns([1, 1, 1])
            with col_prev:
                if step > 0:
                    if st.button("⬅️ 이전", use_container_width=True):
                        st.session_state.current_step -= 1
                        st.rerun()
            with col_next:
                if step < total_steps - 1:
                    if st.button("다음 ➡️", type="primary", use_container_width=True):
                        st.session_state.current_step += 1
                        st.rerun()
                else:
                    if st.button("📊 제출하기", type="primary", use_container_width=True):
                        weight_key = "weight_m" if st.session_state.login_user_sex == 'male' else "weight_f"
                        raw_score = sum(SURVEY_DATA[k][weight_key] * st.session_state.survey_responses.get(k, 0) for k in SURVEY_DATA)
                        raw_score = round(raw_score, 2)
                        
                        # ===== ③번 개선: 학급 기본 α + 학생 개별 α =====
                        alpha = get_effective_alpha(
                            st.session_state.login_user_id,
                            st.session_state.login_user_school,
                            st.session_state.login_user_grade,
                            st.session_state.login_user_room
                        )
                        
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        
                        # 직전 주차 EMA 추적
                        prev_week = st.session_state.select_week - 1
                        prev_month = st.session_state.select_month
                        if prev_week == 0:
                            prev_month = st.session_state.select_month - 1 if st.session_state.select_month > 1 else 12
                            p_year = datetime.date.today().year if prev_month <= datetime.date.today().month else datetime.date.today().year - 1
                            p_num_days = calendar.monthrange(p_year, prev_month)[1]
                            p_m_count = sum(1 for d in range(1, p_num_days + 1) if datetime.date(p_year, prev_month, d).weekday() == 0)
                            prev_week = p_m_count

                        cursor.execute("SELECT score FROM records WHERE user_id=%s AND month=%s AND week=%s", 
                                       (st.session_state.login_user_id, prev_month, prev_week))
                        prev_row = cursor.fetchone()
                        prev_ema = prev_row[0] if prev_row else None
                        
                        if prev_ema is None: 
                            new_ema = raw_score
                        else: 
                            new_ema = (raw_score * alpha) + (prev_ema * (1 - alpha))
                        new_ema = round(new_ema, 2)
                        
                        cursor.execute("""
                            INSERT INTO records (user_id, month, week, score) VALUES (%s, %s, %s, %s)
                            ON CONFLICT(user_id, month, week) DO UPDATE SET score=EXCLUDED.score
                        """, (st.session_state.login_user_id, st.session_state.select_month, st.session_state.select_week, new_ema))
                        conn.commit()
                        conn.close()
                        
                        st.session_state.survey_completed = True
                        st.rerun()

# ==========================================
# 🧑‍🏫 5. 교사용 채널
# ==========================================
elif st.session_state.login_user_id is None and 'app_mode' in locals() and app_mode == "🧑‍🏫 교사 관리자 채널":
    st.title("👩‍🏫 관리자 보안 게이트")
    _, center_col, _ = st.columns([1, 4, 1])
    with center_col:
        with st.container(border=True):
            # ===== ②번 개선: 다교사 지원 + 비번 분실 복구 =====
            tab1, tab2, tab3 = st.tabs(["🔒 교사 로그인", "📝 신규 교사 등록", "🆘 비밀번호 분실"])
            
            with tab1:
                t_login_school = st.text_input("🏫 학교 이름", key="login_school")
                t_login_name = st.text_input("교사 성함", key="login_name")
                t_login_pw = st.text_input("관리자 비밀번호", type="password", key="login_pw")
                if st.button("🚪 관리자 시스템 로그인", type="primary"):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("""SELECT id, name, password_hash, school, teacher_grade, teacher_room 
                                      FROM users WHERE school=%s AND name=%s AND role='teacher'""", 
                                   (t_login_school, t_login_name))
                    t_user = cursor.fetchone()
                    conn.close()
                    
                    if t_user and t_user[2] == make_hash(t_login_pw):
                        st.session_state.login_user_id = t_user[0]
                        st.session_state.login_user_name = t_user[1]
                        st.session_state.login_user_school = t_user[3]
                        st.session_state.login_user_grade = t_user[4]
                        st.session_state.login_user_room = t_user[5]
                        st.session_state.login_role = "teacher"
                        st.rerun()
                    else: 
                        st.error("❌ 학교명/교사명/비밀번호를 다시 확인해 주세요.")
            
            with tab2:
                t_reg_school = st.text_input("🏫 소속 학교 이름", key="reg_school")
                t_reg_name = st.text_input("교사 성함", key="reg_name")
                col_g, col_r = st.columns(2)
                with col_g: t_reg_grade = st.selectbox("담임 학년", list(range(1, 7)), key="reg_grade")
                with col_r: t_reg_room = st.selectbox("담임 반", list(range(1, 13)), key="reg_room")
                t_reg_pw = st.text_input("비밀번호 (8~16자)", type="password", key="reg_pw")
                
                if st.button("🔐 신규 교사 계정 등록"):
                    if not (t_reg_school and t_reg_name and (8 <= len(t_reg_pw) <= 16)):
                        st.error("❌ 모든 정보를 입력해 주세요. 비밀번호는 8~16자입니다.")
                    else:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        # 중복 체크
                        cursor.execute("SELECT id FROM users WHERE school=%s AND name=%s AND role='teacher'",
                                       (t_reg_school, t_reg_name))
                        if cursor.fetchone():
                            st.error("❌ 같은 학교에 이미 등록된 교사 성함입니다.")
                        else:
                            cursor.execute("""INSERT INTO users (role, school, teacher_grade, teacher_room, name, password_hash) 
                                              VALUES ('teacher', %s, %s, %s, %s, %s)""", 
                                           (t_reg_school, t_reg_grade, t_reg_room, t_reg_name, make_hash(t_reg_pw)))
                            # 학급 기본 α 자동 생성
                            cursor.execute("""INSERT INTO class_settings (school, grade, room, default_alpha) 
                                              VALUES (%s, %s, %s, 0.6) 
                                              ON CONFLICT(school, grade, room) DO NOTHING""",
                                           (t_reg_school, t_reg_grade, t_reg_room))
                            conn.commit()
                            conn.close()
                            st.success("🎉 등록 완료! 위 탭에서 로그인하세요.")
            
            with tab3:
                st.markdown("""
                <div style="background:#FFEDDD; padding:20px 24px; border-radius:16px; border-left:6px solid #FF9F66; margin-bottom:16px;">
                    <h3 style="margin:0; color:#2D3B2A; font-weight:800;">⚠️ 시스템 관리자 전용 화면</h3>
                    <p style="margin-top:10px; color:#5C6B58; font-size:1rem; line-height:1.6;">
                    이 화면은 <b>시스템 관리자(데이터베이스 접근 권한 보유자)</b>만 사용할 수 있어요.<br>
                    일반 교사는 비밀번호 분실 시 <b>시스템 관리자에게 직접 연락</b>해 주세요.
                    </p>
                </div>
                """, unsafe_allow_html=True)
                
                # ===== 일반 교사용: 비번 분실 신고 안내 =====
                with st.expander("🙋 **나는 비번을 잊은 일반 교사예요. 어떻게 해야 하나요?**"):
                    st.markdown("""
                    ### 📞 비밀번호 분실 시 처리 절차
                    
                    **1️⃣ 시스템 관리자에게 연락하세요**
                    - 본인의 **학교명, 성함, 담당 학년/반**을 알려주세요
                    - 연락 수단: 직접 만남 > 학교 메신저 > 카톡 1:1
                    
                    **2️⃣ 관리자가 임시 비번을 전달해주면 → 로그인**
                    
                    **3️⃣ 로그인 직후 비번 변경 화면이 자동으로 떠요**
                    - 거기서 본인이 원하는 새 비번으로 변경하시면 끝!
                    
                    ---
                    
                    > 💡 **왜 관리자만 처리할 수 있나요?**  
                    > 외부 침입자가 단순히 교사 이름만 알아내서 비번을 바꿔버리는 일을 막기 위해서예요.  
                    > 데이터베이스 직접 접근 권한이 있는 관리자만 비번을 변경할 수 있게 설계되어 있습니다.
                    """)
                
                st.markdown("---")
                
                st.markdown("""
                ### 🛠️ 시스템 관리자: 비번 초기화 도구
                
                아래에 정보를 입력하면 **데이터베이스에 붙여넣을 SQL 코드**가 자동으로 만들어져요.  
                이 SQL을 Supabase 대시보드에서 실행해야 비밀번호가 실제로 초기화됩니다.
                """)
                
                with st.expander("📖 **관리자 전용: 단계별 SQL 실행 가이드 (처음이라면 꼭 읽어주세요)**", expanded=False):
                    st.markdown("""
                    **1️⃣ 아래에 학교명, 교사 성함, 새 임시 비번 입력**
                    
                    **2️⃣ 아래에 생성되는 SQL 코드 복사 (📋 버튼)**
                    
                    **3️⃣ Supabase 대시보드 접속**
                    - https://supabase.com/dashboard
                    - 본인 프로젝트 선택
                    
                    **4️⃣ 왼쪽 사이드바에서 `SQL Editor` (`</>` 모양) 클릭**
                    
                    **5️⃣ 가운데 빈 박스에 복사한 SQL 붙여넣기**
                    
                    **6️⃣ 오른쪽 아래 초록색 `Run` 버튼 클릭**
                    
                    **7️⃣ 사이트로 돌아와 새 비밀번호로 로그인**
                    
                    > 💡 로그인 후 곧바로 비밀번호 변경 화면이 떠요. 거기서 진짜 비밀번호로 바꾸시면 됩니다.
                    """)
                
                st.markdown("---")
                st.markdown("##### 🛠️ SQL 자동 생성 도구")
                
                reset_school = st.text_input("🏫 학교 이름", key="reset_school", placeholder="예: 한국초등학교")
                reset_name = st.text_input("교사 성함", key="reset_name", placeholder="예: 김지훈")
                reset_new_pw = st.text_input("새 임시 비밀번호 (8~16자)", key="reset_new_pw", 
                                              placeholder="예: temp1234", type="password")
                
                if st.button("🔧 SQL 코드 생성", key="generate_sql"):
                    if not reset_school or not reset_name:
                        st.error("❌ 학교명과 교사 성함을 모두 입력해 주세요.")
                    elif not (8 <= len(reset_new_pw) <= 16):
                        st.error("❌ 임시 비밀번호는 8자~16자여야 합니다.")
                    else:
                        # SQL Injection 방어: 작은따옴표 이스케이프
                        safe_school = reset_school.replace("'", "''")
                        safe_name = reset_name.replace("'", "''")
                        new_hash = make_hash(reset_new_pw)
                        
                        generated_sql = f"""UPDATE users 
SET password_hash = '{new_hash}' 
WHERE role = 'teacher' 
  AND school = '{safe_school}' 
  AND name = '{safe_name}';"""
                        
                        st.success("✅ SQL 생성 완료! 아래 코드를 복사해서 Supabase SQL Editor에 붙여넣으세요.")
                        st.code(generated_sql, language="sql")
                        
                        st.info(f"""
                        📝 **요약**
                        - 학교: `{reset_school}`
                        - 교사: `{reset_name}`
                        - 새 임시 비번: `{reset_new_pw}`
                        
                        ⚠️ SQL 실행 후 해당 교사에게 새 비번으로 로그인하라고 전달하세요.
                        """)
                        
                        st.warning("""
                        🔒 **임시 비번 전달 시 보안 수칙**
                        - ✅ 직접 만나서 알려주기 (가장 안전)
                        - ✅ 학교 메신저 또는 카톡 1:1
                        - ❌ 단톡방 또는 공개된 공간 금지
                        - ⚠️ 해당 교사에게 **로그인 직후 반드시 비번을 변경**하라고 안내해 주세요
                        """)

elif st.session_state.login_user_id and st.session_state.login_role == "teacher":
    teacher_school = st.session_state.login_user_school
    teacher_grade = st.session_state.login_user_grade
    teacher_room = st.session_state.login_user_room
    
    st.title(f"👩‍🏫 {st.session_state.login_user_name} 선생님 통제실")
    st.caption(f"🏫 {teacher_school} | {teacher_grade}학년 {teacher_room}반 담임")
    st.divider()
    
    conn = get_db_connection()
    
    # ===== ③번: 학급 기본 α 설정 UI =====
    with st.expander("⚙️ **학급 EMA 민감도 설정** (전체 학생 기본값)", expanded=False):
        current_alpha = get_class_alpha(teacher_school, teacher_grade, teacher_room)
        
        st.markdown(f"""
        ### 🎚️ α(알파) 값이란?
        
        학생이 매주 답한 점수를 **얼마나 빨리 반영할지** 결정하는 숫자예요.  
        (현재 학급 기본값: **`{current_alpha}`**)
        
        ---
        
        #### 📊 쉽게 이해하기 — "이번 주 점수 vs 누적 점수의 비율"
        
        설문 점수 계산은 이렇게 돼요:
        
        > **최종 점수 = (이번 주 점수 × α) + (지난 주까지의 누적 점수 × (1−α))**
        """)
        
        col_low, col_mid, col_high = st.columns(3)
        with col_low:
            st.markdown("""
            <div style='padding:20px; background:#FFFFFF; border:1px solid #E8E6E0; border-left:5px solid #7AA8E8; border-radius:14px; height:260px; box-shadow:0 4px 14px rgba(45,43,82,0.05);'>
                <h4 style='margin:0; color:#2D3B2A; font-weight:800;'>🐢 낮은 α (0.1 ~ 0.3)</h4>
                <p style='font-size:0.95rem; margin-top:10px; color:#5C6B58; line-height:1.7;'>
                <b style='color:#2D3B2A;'>안정 우선형</b><br><br>
                ✅ 변화에 둔감<br>
                ✅ 일시적 기분 무시<br>
                ❌ 위기 신호 늦게 감지<br><br>
                <i>"오늘 하루 기분만으로<br>평가하지 말자"</i>
                </p>
            </div>
            """, unsafe_allow_html=True)
        with col_mid:
            st.markdown("""
            <div style='padding:20px; background:#FFFFFF; border:1px solid #E8E6E0; border-left:5px solid #6BBE5A; border-radius:14px; height:260px; box-shadow:0 4px 14px rgba(45,43,82,0.05);'>
                <h4 style='margin:0; color:#2D3B2A; font-weight:800;'>⚖️ 중간 α (0.4 ~ 0.7)</h4>
                <p style='font-size:0.95rem; margin-top:10px; color:#5C6B58; line-height:1.7;'>
                <b style='color:#6BBE5A;'>균형형 (권장)</b><br><br>
                ✅ 변화도 감지<br>
                ✅ 노이즈도 완충<br>
                ✅ 일반적인 학급에 적합<br><br>
                <i>"적당히 빠르게,<br>적당히 신중하게"</i>
                </p>
            </div>
            """, unsafe_allow_html=True)
        with col_high:
            st.markdown("""
            <div style='padding:20px; background:#FFFFFF; border:1px solid #E8E6E0; border-left:5px solid #FF9F66; border-radius:14px; height:260px; box-shadow:0 4px 14px rgba(45,43,82,0.05);'>
                <h4 style='margin:0; color:#2D3B2A; font-weight:800;'>🐇 높은 α (0.7 ~ 0.9)</h4>
                <p style='font-size:0.95rem; margin-top:10px; color:#5C6B58; line-height:1.7;'>
                <b style='color:#FF9F66;'>민감 우선형</b><br><br>
                ✅ 위기 빠르게 감지<br>
                ✅ 작은 변화도 포착<br>
                ❌ 일시적 변동에 흔들림<br><br>
                <i>"한 번이라도 안 좋으면<br>바로 신호 받자"</i>
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown(f"""
        ---
        
        #### 💡 예시로 이해하기
        
        지난 주까지 학생의 누적 점수가 **2.0** 이었고, 이번 주 점수가 **3.0** 이라고 가정해볼게요:
        
        | α 값 | 계산 | 최종 점수 |
        |------|------|----------|
        | **α = 0.3** (낮음) | 3.0×0.3 + 2.0×0.7 = | **2.30** (변화 작음) |
        | **α = 0.6** (중간, 기본값) | 3.0×0.6 + 2.0×0.4 = | **2.60** (균형) |
        | **α = 0.9** (높음) | 3.0×0.9 + 2.0×0.1 = | **2.90** (이번 주 거의 그대로) |
        
        > **💼 추천 사용 시나리오**
        > - **학기 초**: 0.5~0.6 (균형) — 학생 패턴을 파악 중
        > - **위기 감지가 중요한 시기 (시험·학년말)**: 0.7~0.8 (높음)
        > - **변동이 잦은 학급 (예: 친구 관계 변화 多)**: 0.3~0.4 (낮음)
        """)
        
        st.markdown("---")
        new_alpha = st.slider(
            f"🎯 학급 기본 α 설정 (현재값: {current_alpha})", 
            0.1, 0.9, float(current_alpha), 0.05
        )
        if st.button("💾 학급 기본값 저장"):
            cursor = conn.cursor()
            cursor.execute("""INSERT INTO class_settings (school, grade, room, default_alpha) 
                              VALUES (%s, %s, %s, %s)
                              ON CONFLICT(school, grade, room) DO UPDATE SET default_alpha=EXCLUDED.default_alpha""",
                           (teacher_school, teacher_grade, teacher_room, new_alpha))
            conn.commit()
            st.success(f"✅ 학급 기본 α 가 {new_alpha} 로 저장되었습니다.")
            st.rerun()
    
    # ===== 학생 필터링 - 본인 학급만 =====
    df_students = pd.read_sql_query(
        """SELECT id, grade, room, sex, number, name, custom_alpha 
           FROM users WHERE role='student' AND school=%s AND grade=%s AND room=%s
           ORDER BY number ASC""", 
        conn, params=(teacher_school, teacher_grade, teacher_room))
    
    if not df_students.empty:
        st.subheader(f"📚 {teacher_grade}학년 {teacher_room}반 학생 명단")
        
        f_col1, f_col2 = st.columns(2)
        with f_col1: filter_sex = st.selectbox("성별 필터", ["전체", "남자", "여자"])
        
        filtered_df = df_students.copy()
        if filter_sex != "전체":
            s_val = 'male' if filter_sex == "남자" else 'female'
            filtered_df = filtered_df[filtered_df['sex'] == s_val]
            
        filtered_df["display_name"] = filtered_df.apply(lambda r: f"{r['number']}번 {r['name']} ({'남' if r['sex']=='male' else '여'})", axis=1)
        
        display_table = filtered_df[['number', 'sex', 'name', 'custom_alpha']].copy()
        display_table['sex'] = display_table['sex'].apply(lambda x: '남' if x == 'male' else '여')
        display_table['custom_alpha'] = display_table['custom_alpha'].apply(lambda x: f"개별 {x}" if pd.notna(x) else f"기본 {get_class_alpha(teacher_school, teacher_grade, teacher_room)}")
        display_table.columns = ['번호', '성별', '이름', '적용 α']
        st.dataframe(display_table, use_container_width=True, hide_index=True)
        st.divider()

        # 학생 일괄 삭제
        with st.expander("👥 학생 계정 일괄 삭제"):
            selected_to_delete = []
            for idx, r in filtered_df.iterrows():
                chk = st.checkbox(f"{r['number']}번 {r['name']} ({'남' if r['sex']=='male' else '여'})", key=f"bulk_del_{r['id']}")
                if chk:
                    selected_to_delete.append(r['id'])
            
            if selected_to_delete:
                st.warning(f"⚠️ 선택한 {len(selected_to_delete)}명의 학적과 기록이 영구 삭제됩니다.")
                if st.button("🗑️ 선택된 학생 일괄 삭제", type="primary"):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM records WHERE user_id = ANY(%s)", (selected_to_delete,))
                    cursor.execute("DELETE FROM users WHERE id = ANY(%s)", (selected_to_delete,))
                    conn.commit()
                    st.success("🎉 일괄 삭제 완료.")
                    st.rerun()

        st.divider()

        if not filtered_df.empty:
            selected_student_id = st.selectbox("📊 상세 분석 대상 학생", filtered_df["id"].tolist(), 
                                                format_func=lambda x: filtered_df[filtered_df["id"]==x]["display_name"].values[0])
            target_student = filtered_df[filtered_df['id'] == selected_student_id].iloc[0]
            student_sex = target_student['sex']
            
            df_records = pd.read_sql_query("SELECT month, week, score FROM records WHERE user_id=%s ORDER BY month ASC, week ASC", 
                                            conn, params=(int(selected_student_id),))
            
            col_dash1, col_dash2 = st.columns([1, 2])
            with col_dash1:
                st.markdown("### 📉 주차별 분석 결과")
                
                for _, row in df_records.iterrows():
                    m, w, sc = int(row['month']), int(row['week']), row['score']
                    if student_sex == 'male':
                        if sc >= 2.6: status = "🚨 위험군 (즉각 개입)"
                        elif sc >= 1.0: status = "🟠 주의군"
                        else: status = "🟢 안정군"
                    else:
                        if sc >= 2.9: status = "🚨 위험군 (즉각 개입)"
                        elif sc >= 1.0: status = "🟠 주의군"
                        else: status = "🟢 안정군"
                    st.markdown(f"• **{m}월 {w}주차**: `{sc}` → {status}")
                
                st.divider()
                
                # ===== ③번: 학생 개별 α 설정 =====
                st.markdown("⚙️ **이 학생 개별 α 설정**")
                current_custom = target_student['custom_alpha']
                class_alpha = get_class_alpha(teacher_school, teacher_grade, teacher_room)
                
                with st.expander("ℹ️ 개별 α는 언제 쓰나요?"):
                    st.markdown("""
                    학급 기본값과 다른 α를 적용하고 싶을 때 사용해요.
                    
                    - 🐇 **개별 α를 더 높게**: 이 학생은 평소 감정 표현이 작아서 작은 변화도 빠르게 잡고 싶을 때
                    - 🐢 **개별 α를 더 낮게**: 이 학생은 변동이 잦아서 일시적 기복을 완충하고 싶을 때
                    - ⚖️ **체크 해제**: 학급 기본값으로 자동 복귀
                    """)
                
                if pd.notna(current_custom):
                    st.info(f"🎯 현재 개별 α: **{current_custom}** (학급 기본값 `{class_alpha}` 대신 적용 중)")
                else:
                    st.info(f"🎯 현재 학급 기본값 적용: **{class_alpha}**")
                
                use_custom = st.checkbox("이 학생에게 개별 α 적용", value=pd.notna(current_custom))
                if use_custom:
                    custom_val = st.slider("개별 α 값 (낮을수록 안정, 높을수록 민감)", 0.1, 0.9, 
                                            float(current_custom) if pd.notna(current_custom) else float(class_alpha), 
                                            0.05, key=f"custom_alpha_{selected_student_id}")
                    if st.button("💾 개별 α 저장"):
                        cursor = conn.cursor()
                        cursor.execute("UPDATE users SET custom_alpha=%s WHERE id=%s", (custom_val, int(selected_student_id)))
                        conn.commit()
                        st.success("✅ 개별 α 저장됨")
                        st.rerun()
                else:
                    if pd.notna(current_custom):
                        if st.button("🔄 개별 설정 해제 (학급 기본값 사용)"):
                            cursor = conn.cursor()
                            cursor.execute("UPDATE users SET custom_alpha=NULL WHERE id=%s", (int(selected_student_id),))
                            conn.commit()
                            st.success("✅ 학급 기본값으로 복귀")
                            st.rerun()
                
                st.divider()
                st.markdown("⚙️ **기록 및 계정 관리**")
                
                if not df_records.empty:
                    record_options = df_records.apply(lambda r: f"{int(r['month'])}월 {int(r['week'])}주차 기록", axis=1).tolist()
                    record_mapping = {f"{int(r['month'])}월 {int(r['week'])}주차 기록": (int(r['month']), int(r['week'])) for _, r in df_records.iterrows()}
                    
                    del_label = st.selectbox("초기화 대상 주차", record_options)
                    if st.button("🗑️ 지정 주차 기록 삭제"):
                        del_m, del_w = record_mapping[del_label]
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM records WHERE user_id=%s AND month=%s AND week=%s", 
                                       (int(selected_student_id), del_m, del_w))
                        conn.commit()
                        st.success(f"🎉 {del_label} 삭제 완료.")
                        st.rerun()
                
                if st.button("🔄 본 학생 비밀번호 초기화"):
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (make_hash("12345678"), int(selected_student_id)))
                    conn.commit()
                    st.success("✅ 비밀번호가 '12345678'로 초기화되었습니다.")
                        
            with col_dash2:
                # ===== ⑤번 개선: Plotly 차트로 위험 임계선 시각화 =====
                df_chart = df_records.dropna()
                if not df_chart.empty:
                    df_chart["label"] = df_chart.apply(lambda r: f"{int(r['month'])}월 {int(r['week'])}주차", axis=1)
                    
                    # 성별에 따른 임계선
                    if student_sex == 'male':
                        danger_line = 2.6
                        warning_line = 1.0
                    else:
                        danger_line = 2.9
                        warning_line = 1.0
                    
                    fig = go.Figure()
                    
                    # 위험 영역 (빨간 띠)
                    fig.add_hrect(y0=danger_line, y1=4.5, fillcolor="rgba(239, 68, 68, 0.15)", 
                                  line_width=0, annotation_text="🚨 위험군", annotation_position="top left",
                                  annotation_font_color="#DC2626", annotation_font_size=12)
                    # 주의 영역 (주황 띠)
                    fig.add_hrect(y0=warning_line, y1=danger_line, fillcolor="rgba(251, 146, 60, 0.15)", 
                                  line_width=0, annotation_text="🟠 주의군", annotation_position="top left",
                                  annotation_font_color="#EA580C", annotation_font_size=12)
                    # 안정 영역 (초록 띠)
                    fig.add_hrect(y0=0, y1=warning_line, fillcolor="rgba(34, 197, 94, 0.15)", 
                                  line_width=0, annotation_text="🟢 안정군", annotation_position="top left",
                                  annotation_font_color="#16A34A", annotation_font_size=12)
                    
                    # 임계선
                    fig.add_hline(y=danger_line, line_dash="dash", line_color="#DC2626", line_width=2,
                                  annotation_text=f"위험 임계선 {danger_line}", annotation_position="right")
                    fig.add_hline(y=warning_line, line_dash="dash", line_color="#EA580C", line_width=2,
                                  annotation_text=f"주의 임계선 {warning_line}", annotation_position="right")
                    
                    # 학생 데이터
                    fig.add_trace(go.Scatter(
                        x=df_chart["label"], y=df_chart["score"],
                        mode='lines+markers',
                        line=dict(color='#667eea', width=3),
                        marker=dict(size=12, color='#764ba2', line=dict(color='#FFFFFF', width=2)),
                        name='EMA 점수',
                        hovertemplate='%{x}<br>점수: %{y}<extra></extra>'
                    ))
                    
                    fig.update_layout(
                        title=dict(text=f"📈 {target_student['name']} 학생 정서 추이", font=dict(size=16, color='#1F2937')),
                        xaxis=dict(title="주차", gridcolor='rgba(0,0,0,0.05)'),
                        yaxis=dict(title="EMA 점수", gridcolor='rgba(0,0,0,0.05)', range=[0, 4.5]),
                        plot_bgcolor='rgba(255,255,255,0.6)',
                        paper_bgcolor='rgba(0,0,0,0)',
                        height=450,
                        showlegend=False,
                        margin=dict(l=50, r=80, t=60, b=50)
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("📊 시계열 차트에 표시할 데이터가 없습니다.")
        else:
            st.warning("필터 조건에 부합하는 학생이 없습니다.")
    else:
        st.info(f"📁 {teacher_grade}학년 {teacher_room}반에 등록된 학생이 없습니다. 학생들이 등록을 마치면 여기에 표시됩니다.")
        
    conn.close()