import streamlit as st
import streamlit_shadcn_ui as ui
import pandas as pd
import psycopg2 
import hashlib
import random
import datetime
import calendar

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
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            role TEXT DEFAULT 'student',
            grade INTEGER,
            room INTEGER,
            number INTEGER,
            sex TEXT,
            name TEXT,
            password_hash TEXT,
            UNIQUE(grade, room, number, role)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id SERIAL PRIMARY KEY,
            user_id INTEGER REFERENCES users(id),
            week INTEGER,
            score REAL
        )
    """)
    
    # [스마트 달력 도입] 기존 records 테이블에 month 컬럼이 없으면 자동 추가 및 제약조건 갱신
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='records' AND column_name='month'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE records ADD COLUMN month INTEGER DEFAULT 5")
        cursor.execute("ALTER TABLE records DROP CONSTRAINT IF EXISTS records_user_id_week_key")
        try:
            cursor.execute("ALTER TABLE records ADD CONSTRAINT records_user_id_month_week_key UNIQUE(user_id, month, week)")
        except Exception:
            pass
    else:
        try:
            cursor.execute("ALTER TABLE records ADD CONSTRAINT records_user_id_month_week_key UNIQUE(user_id, month, week)")
        except Exception:
            pass
            
    cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name='users' AND column_name='sex'")
    if not cursor.fetchone():
        cursor.execute("ALTER TABLE users ADD COLUMN sex TEXT DEFAULT 'male'")
        
    conn.commit()
    conn.close()

init_db()

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

if "login_user_id" not in st.session_state: st.session_state.login_user_id = None
if "login_user_name" not in st.session_state: st.session_state.login_user_name = None
if "login_user_sex" not in st.session_state: st.session_state.login_user_sex = None
if "login_role" not in st.session_state: st.session_state.login_role = None
if "needs_password_change" not in st.session_state: st.session_state.needs_password_change = False
if "current_step" not in st.session_state: st.session_state.current_step = 0
if "survey_responses" not in st.session_state: st.session_state.survey_responses = {}
if "survey_completed" not in st.session_state: st.session_state.survey_completed = False

# ==========================================
# 2. 모던 스타일 CSS (반응형 여백 및 디자인 고도화)
# ==========================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght=400;600;800&display=swap');
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #F3F4F6;
        font-family: 'Pretendard', sans-serif;
    }
    
    .block-container { padding: 2rem 5% !important; max-width: 100% !important; }
    @media (min-width: 768px) {
        .block-container { padding: 3rem 15% !important; max-width: 90% !important; }
    }
    
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 16px !important;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05) !important;
        padding: 2rem !important;
        margin-top: 1rem !important;
    }
    
    @media (max-width: 768px) {
        div[data-testid="stVerticalBlockBorderWrapper"] { padding: 1.2rem !important; }
    }
    
    /* 모든 입력창 흰색 바탕 강제 스크립트 */
    div[data-testid="stTextInput"] input, 
    div[data-baseweb="select"] > div,
    div[data-testid="stNumberInput"] input {
        background-color: #FFFFFF !important;
        border: 2px solid #D1D5DB !important;
        color: #1F2937 !important;
    }
    
    .question-text { 
        font-size: 1.4rem !important; 
        font-weight: 800; 
        line-height: 1.8 !important; 
        color: #1F2937; 
        margin-bottom: 20px; 
        text-align: center; 
        word-break: keep-all; 
    }
    
    div.row-widget.stRadio > div { gap: 14px; margin-bottom: 20px; padding: 20px; background-color: #F9FAFB; border: 2px solid #E5E7EB; border-radius: 12px; }
    label { line-height: 1.8 !important; font-size: 1.1rem !important; color: #374151; font-weight: 600; word-break: keep-all; }
    .stButton>button { width: 100%; font-size: 1.2rem !important; font-weight: 600 !important; padding: 12px !important; border-radius: 10px !important; }
    </style>
""", unsafe_allow_html=True)

SURVEY_DATA = {
    "depression": {"icon": "🖥️", "question": "지금 당장 내가 제일 좋아하는 유튜브 영상이나 게임을 볼 수 있다면,<br>내 마음이 어떨 것 같나요?", "options": ["평소처럼 생각만 해도 신나고 빨리 보고 싶다.", "오늘따라 귀찮거나 별로 하고 싶은 생각이 안 든다."], "weight_m": 1.60, "weight_f": 1.17},
    "loneliness": {"icon": "🍱", "question": "오늘 학교 쉬는 시간이나 점심시간에 보낼 내 모습을 상상해보면,<br>내 마음이 어떨 것 같나요?", "options": ["친구들과 신나게 어울려 놀거나,\n혹은 혼자서 책 읽기나 그리기를 하더라도 내 마음이 편안하고 만족스러울 것 같다.", "같이 놀거나 이야기할 친구가 없어서 교실에 가만히 있거나,\n어떻게 시간을 보내야 할지 몰라 마음이 불안하고 쓸쓸할 것 같다."], "weight_m": 0.90, "weight_f": 0.91},
    "stress": {"icon": "📝", "question": "오늘 학교에서 예상하지 못한 작은 과제나 귀찮은 일이 갑자기 생긴다면,<br>내 마음이 어떨 것 같나요?", "options": ["‘얼른 해버려야지!’ 하고 가벼운 마음으로 편안하게 받아들일 수 있을 것 같다.", "오늘따라 마음의 여유가 없어서, 아주 작은 일 하나도 평소보다 훨씬 더 무겁고 답답하게 느껴질 것 같다."], "weight_m": 0.97, "weight_f": 0.97},
    "anxiety": {"icon": "🎮", "question": "이번 주 일주일 동안 일어날 일들을 생각할 때,<br>걱정하는 마음 때문에 지금 내가 해야 할 공부나 놀이에 집중하기가 힘든가요?", "options": ["걱정이 조금 되더라도, 내가 할 일이나 친구들과 노는 것에는 별로 지장이 없다.", "걱정스러운 생각이 머릿속을 가득 채워서, 다른 일에 집중하기 어렵고 마음이 온통 그곳에 쏠려 있다."], "weight_m": 0.76, "weight_f": 0.80},
    "sleep_deprivation": {"icon": "🔋", "question": "오늘 아침에 눈을 떴을 때, 내 몸과 마음의 배터리가 어느 정도 충전된 느낌이었나요?", "options": ["이불 속에서 조금 더 자고 싶긴 했지만,\n막상 일어나서 세수를 하니 평소처럼 학교에 가서 활동할 에너지는 충분한 것 같다.", "잠을 자긴 했는데 피로가 전혀 풀리지 않은 것처럼 온몸이 무겁고,\n하루를 시작하기도 전에 이미 에너지가 바닥난 것처럼 지친다."], "weight_m": 0.22, "weight_f": 0.19}
}

# ==========================================
# 3. 사이드바 제어판
# ==========================================
st.sidebar.title("🔐 시스템 제어판")
if st.session_state.login_user_id is not None:
    st.sidebar.success(f"🟩 {st.session_state.login_user_name}님")
    if st.sidebar.button("로그아웃"):
        st.session_state.login_user_id = None
        st.session_state.login_user_name = None
        st.session_state.login_user_sex = None
        st.session_state.login_role = None
        st.session_state.needs_password_change = False
        st.session_state.current_step = 0
        st.session_state.survey_responses = {}
        st.session_state.survey_completed = False
        st.rerun()
else:
    app_mode = st.sidebar.radio("접속 권한 선택", ["🧑‍🎓 학생용 채널", "🧑‍🏫 교사 관리자 채널"])

# ==========================================
# 🧑‍🎓 4. 학생용 채널
# ==========================================
if st.session_state.login_user_id is None and 'app_mode' in locals() and app_mode == "🧑‍🎓 학생용 채널":
    ui.card(title="오늘 하루 나의 기분은?", content="요즘 자신의 기분이 어떤지 기록하는 공간입니다.", description="선생님이 여러분의 학교생활에 참고하기 위한 질문들이에요").render()
    
    st.divider()
    _, center_col, _ = st.columns([1, 8, 1])
    with center_col:
        with st.container(border=True):
            st.subheader("🧑‍🎓 학생 로그인 및 등록")
            
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
                if s_number == 0: st.error("❌ 번호는 1번 이상이어야 합니다.")
                elif not s_name or not s_password: st.error("❌ 이름과 비밀번호를 모두 입력해 주세요.")
                elif not (8 <= len(s_password) <= 16): st.error("❌ 비밀번호는 반드시 8자 이상, 16자 이하여야 합니다.")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, name, password_hash, sex FROM users WHERE grade=%s AND room=%s AND number=%s AND role='student'", (s_grade, s_room, s_number))
                    user = cursor.fetchone()
                    hashed_pw = make_hash(s_password)
                    
                    if user is None:
                        try:
                            cursor.execute("INSERT INTO users (role, grade, room, number, sex, name, password_hash) VALUES ('student', %s, %s, %s, %s, %s, %s)", 
                                           (s_grade, s_room, s_number, s_sex, s_name, hashed_pw))
                            conn.commit()
                            cursor.execute("SELECT id, sex FROM users WHERE grade=%s AND room=%s AND number=%s AND role='student'", (s_grade, s_room, s_number))
                            new_user = cursor.fetchone()
                            st.session_state.login_user_id = new_user[0]
                            st.session_state.login_user_sex = new_user[1]
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
            st.title(f"🌈 {st.session_state.login_user_name} 친구, 고생했어요!")
            random_message = random.choice(ENCOURAGING_MESSAGES)
            st.success(f"### 🎉 요즘의 마음 전달이 완료되었습니다!\n\n---\n\n## 💌 **{random_message}**\n\n---\n\n선생님께서 소중한 마음을 확인하실 거예요.\n\n안전을 위해 왼쪽의 **[로그아웃]** 버튼을 눌러 창을 닫아주세요.")
            
        else:
            st.title(f"🌈 {st.session_state.login_user_name} 친구, 환영해요!")
            keys = list(SURVEY_DATA.keys())
            total_steps = len(keys)
            step = st.session_state.current_step
            key = keys[step]
            data = SURVEY_DATA[key]
            
            _, main_col, _ = st.columns([1, 8, 1])
            with main_col:
                # [수정] 1번 아키텍처: 스마트 달력 월간/주차 자동 매핑
                if step == 0:
                    current_year = 2026
                    st.session_state.select_month = st.selectbox("📅 몇 월 기록인가요?", list(range(1, 13)), format_func=lambda x: f"{x}월", index=datetime.date.today().month - 1)
                    
                    # 선택된 월의 월요일 날짜들 자동 연산
                    num_days = calendar.monthrange(current_year, st.session_state.select_month)[1]
                    mondays = []
                    for day in range(1, num_days + 1):
                        if datetime.date(current_year, st.session_state.select_month, day).weekday() == 0:
                            mondays.append(day)
                    
                    st.session_state.select_week = st.selectbox(
                        "📅 확인할 주차의 월요일을 선택해 주세요", 
                        list(range(1, len(mondays) + 1)), 
                        format_func=lambda x: f"{x}주차 ({st.session_state.select_month}월 {mondays[x-1]}일)"
                    )
                
                st.progress((step + 1) / total_steps)
                st.caption(f"총 {total_steps}개 질문 중 {step + 1}번째 질문")
                
                with st.container(border=True):
                    st.markdown(f"<div style='text-align: center; font-size: 4rem; margin-bottom: 20px;'>{data['icon']}</div>", unsafe_allow_html=True)
                    st.markdown(f"<p class='question-text'>{data['question']}</p>", unsafe_allow_html=True)
                    
                    current_val = st.session_state.survey_responses.get(key, 0)
                    default_idx = 1 if current_val == 1 else 0
                    choice = st.radio(f"choice_{key}", data["options"], index=default_idx, label_visibility="collapsed")
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
                            
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            
                            # 직전 연산 피드백 추적 알고리즘 (동일 월 내 또는 전월 말일 주차 추적 보정)
                            prev_week = st.session_state.select_week - 1
                            prev_month = st.session_state.select_month
                            if prev_week == 0:
                                prev_month = st.session_state.select_month - 1 if st.session_state.select_month > 1 else 12
                                p_num_days = calendar.monthrange(2026, prev_month)[1]
                                p_m_count = sum(1 for d in range(1, p_num_days + 1) if datetime.date(2026, prev_month, d).weekday() == 0)
                                prev_week = p_m_count

                            cursor.execute("SELECT score FROM records WHERE user_id=%s AND month=%s AND week=%s", (st.session_state.login_user_id, prev_month, prev_week))
                            prev_row = cursor.fetchone()
                            prev_ema = prev_row[0] if prev_row else None
                            
                            if prev_ema is None: new_ema = raw_score
                            else: new_ema = (raw_score * 0.6) + (prev_ema * 0.4)
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
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE role='teacher'")
            teacher_exists = cursor.fetchone()
            conn.close()
            
            if not teacher_exists:
                t_reg_name = st.text_input("교사 성함 입력")
                t_reg_pw = st.text_input("신규 비밀번호 입력 (8~16자)", type="password")
                if st.button("🔐 마스터 계정 등록 승인"):
                    if t_reg_name and (8 <= len(t_reg_pw) <= 16):
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO users (role, name, password_hash) VALUES ('teacher', %s, %s)", (t_reg_name, make_hash(t_reg_pw)))
                        conn.commit()
                        conn.close()
                        st.rerun()
            else:
                st.subheader("🔒 관리자 로그인")
                t_login_name = st.text_input("교사 성함")
                t_login_pw = st.text_input("관리자 비밀번호", type="password")
                if st.button("🚪 관리자 시스템 로그인", type="primary"):
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    cursor.execute("SELECT id, name, password_hash FROM users WHERE name=%s AND role='teacher'", (t_login_name,))
                    t_user = cursor.fetchone()
                    conn.close()
                    
                    if t_user and t_user[2] == make_hash(t_login_pw):
                        st.session_state.login_user_id = t_user[0]
                        st.session_state.login_user_name = t_user[1]
                        st.session_state.login_role = "teacher"
                        st.rerun()
                    else: st.error("❌ 관리자 인증 정보가 불일치합니다.")

elif st.session_state.login_user_id and st.session_state.login_role == "teacher":
    st.title(f"👩‍🏫 {st.session_state.login_user_name} 마스터 관리자 통제실")
    st.divider()
    
    conn = get_db_connection()
    df_students = pd.read_sql_query("SELECT id, grade, room, sex, number, name FROM users WHERE role='student' ORDER BY grade ASC, room ASC, sex ASC, number ASC", conn)
    
    if not df_students.empty:
        st.subheader("🔍 학생 데이터베이스 다중 필터링")
        f_col1, f_col2, f_col3 = st.columns(3)
        
        grades_list = sorted(df_students['grade'].unique().tolist())
        rooms_list = sorted(df_students['room'].unique().tolist())
        
        with f_col1: filter_grade = st.selectbox("학년 필터", ["전체"] + grades_list)
        with f_col2: filter_room = st.selectbox("반 필터", ["전체"] + rooms_list)
        with f_col3: filter_sex = st.selectbox("성별 필터", ["전체", "남자", "여자"])
        
        filtered_df = df_students.copy()
        if filter_grade != "전체": filtered_df = filtered_df[filtered_df['grade'] == filter_grade]
        if filter_room != "전체": filtered_df = filtered_df[filtered_df['room'] == filter_room]
        if filter_sex != "전체":
            s_val = 'male' if filter_sex == "남자" else 'female'
            filtered_df = filtered_df[filtered_df['sex'] == s_val]
            
        filtered_df["display_name"] = filtered_df.apply(lambda r: f"{r['grade']}학년 {r['room']}반 {r['number']}번 {r['name']} ({'남' if r['sex']=='male' else '여'})", axis=1)
        
        display_table = filtered_df[['grade', 'room', 'number', 'sex', 'name']].copy()
        display_table['sex'] = display_table['sex'].apply(lambda x: '남' if x == 'male' else '여')
        display_table.columns = ['학년', '반', '번호', '성별', '이름']
        st.dataframe(display_table, use_container_width=True, hide_index=True)
        st.divider()

        # [추가] 체크박스 기반의 학생 다중 일괄 삭제 기능 탑재
        st.subheader("👥 학생 계정 일괄 관리 및 다중 삭제")
        with st.expander("❌ 일괄 삭제를 진행할 학생들을 다중 선택하세요 (체크박스)"):
            selected_to_delete = []
            for idx, r in filtered_df.iterrows():
                chk = st.checkbox(f"{r['grade']}학년 {r['room']}반 {r['number']}번 {r['name']} ({'남' if r['sex']=='male' else '여'})", key=f"bulk_del_{r['id']}")
                if chk:
                    selected_to_delete.append(r['id'])
            
            if selected_to_delete:
                st.warning(f"⚠️ 경고: 선택한 {len(selected_to_delete)}명의 학생 학적과 모든 주차별 마음 기록이 영구 파괴됩니다.")
                if st.button("🗑️ 선택된 학생 전원 일괄 삭제", type="primary"):
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM records WHERE user_id = ANY(%s)", (selected_to_delete,))
                    cursor.execute("DELETE FROM users WHERE id = ANY(%s)", (selected_to_delete,))
                    conn.commit()
                    st.success("🎉 선택한 모든 학생 데이터가 일괄 제거되었습니다.")
                    st.rerun()

        st.divider()

        if not filtered_df.empty:
            selected_student_id = st.selectbox("📊 상세 분석 대상 개별 지정", filtered_df["id"].tolist(), format_func=lambda x: filtered_df[filtered_df["id"]==x]["display_name"].values[0])
            target_student = filtered_df[filtered_df['id'] == selected_student_id].iloc[0]
            student_sex = target_student['sex']
            
            df_records = pd.read_sql_query("SELECT month, week, score FROM records WHERE user_id=%s ORDER BY month ASC, week ASC", conn, params=(int(selected_student_id),))
            
            col_dash1, col_dash2 = st.columns([1, 2])
            with col_dash1:
                st.markdown("### 📉 주간 캘리브레이션 분석 결과")
                
                for _, row in df_records.iterrows():
                    m = int(row['month'])
                    w = int(row['week'])
                    sc = row['score']
                    
                    if student_sex == 'male':
                        if sc >= 2.6: status = "🚨 위험군 (즉각 개입 요망)"
                        elif sc >= 1.0: status = "🟠 주의군 (정기 관찰 필요)"
                        else: status = "🟢 안정군"
                    else:
                        if sc >= 2.9: status = "🚨 위험군 (즉각 개입 요망)"
                        elif sc >= 1.0: status = "🟠 주의군 (정기 관찰 필요)"
                        else: status = "🟢 안정군"
                    st.markdown(f"• **{m}월 {w}주차**: `{sc}` $\rightarrow$ {status}")
                
                st.divider()
                st.markdown("⚙️ **개별 학생 기록 및 제어 조치**")
                
                if not df_records.empty:
                    record_options = df_records.apply(lambda r: f"{int(r['month'])}월 {int(r['week'])}주차 기록", axis=1).tolist()
                    record_mapping = {f"{int(r['month'])}월 {int(r['week'])}주차 기록": (int(r['month']), int(r['week'])) for _, r in df_records.iterrows()}
                    
                    del_label = st.selectbox("초기화 대상 주차 지정", record_options)
                    if st.button("🗑️ 지정 주차 정서 기록 삭제"):
                        del_m, del_w = record_mapping[del_label]
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM records WHERE user_id=%s AND month=%s AND week=%s", (int(selected_student_id), del_m, del_w))
                        conn.commit()
                        st.success(f"🎉 {del_label}이 완벽히 정제되었습니다.")
                        st.rerun()
                else:
                    st.info("초기화할 주차 기록이 존재하지 않습니다.")

                if st.button("🔄 본 학생 비밀번호 '12345678' 원격 초기화"):
                    cursor = conn.cursor()
                    cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (make_hash("12345678"), int(selected_student_id)))
                    conn.commit()
                    st.success("해당 학생 암호가 초기화 규격으로 원격 변경되었습니다.")
                        
            with col_dash2:
                df_chart = df_records.dropna()
                if not df_chart.empty:
                    df_chart["label"] = df_chart.apply(lambda r: f"{int(r['month'])}월 {int(r['week'])}주차", axis=1)
                    df_chart = df_chart.set_index("label")
                    st.line_chart(df_chart[["score"]])
                else:
                    st.info("시계열 변화 그래프를 렌더링할 정서 응답 데이터가 없습니다.")
        else:
            st.warning("지정된 다중 필터 조건에 부합하는 학생이 데이터베이스에 없습니다.")
    else:
        st.info("📁 등록된 학생 데이터가 없습니다. 학생 채널에서 먼저 등록을 진행해 주세요.")
        
    conn.close()