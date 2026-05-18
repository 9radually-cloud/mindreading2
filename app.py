import streamlit as st
import streamlit_shadcn_ui as ui
import pandas as pd
import psycopg2  # 인터넷 금고 연결용 부품
import hashlib
import os

# ==========================================
# 1. 시스템 설정 및 데이터베이스(Supabase PostgreSQL) 보안 초기화
# ==========================================
st.set_page_config(page_title="마음 배터리 충전소", page_icon="🌈", layout="wide")

def get_db_connection():
    # 코드에는 주소가 안 보이지만, 인터넷에 배포될 때 비밀 주소를 알아서 읽어옵니다.
    return psycopg2.connect(st.secrets["db_url"])

def init_db():
    """수파베이스(PostgreSQL) 문법에 맞게 테이블 생성자 전면 수정"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # [수정] AUTOINCREMENT 대신 SERIAL PRIMARY KEY 문법 적용
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            role TEXT DEFAULT 'student',
            grade INTEGER,
            room INTEGER,
            number INTEGER,
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
            score REAL,
            UNIQUE(user_id, week)
        )
    """)
    conn.commit()
    conn.close()

# 앱 켜질 때 인터넷 금고에 방이 없으면 자동으로 방을 만듭니다.
init_db()

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

if "login_user_id" not in st.session_state: st.session_state.login_user_id = None
if "login_user_name" not in st.session_state: st.session_state.login_user_name = None
if "login_role" not in st.session_state: st.session_state.login_role = None
if "needs_password_change" not in st.session_state: st.session_state.needs_password_change = False

# ==========================================
# 2. 고급 CSS 오버라이딩 (모던 스타일 고도화)
# ==========================================
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght=400;600;800&display=swap');
    html, body, [data-testid="stAppViewContainer"] {
        background-color: #F3F4F6;
        font-family: 'Pretendard', sans-serif;
    }
    
    .block-container { padding-left: 8rem; padding-right: 8rem; max-width: 90%; }
    
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF !important;
        border: 1px solid #E5E7EB !important;
        border-radius: 16px !important;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.05) !important;
        padding: 2.5rem !important;
        margin-top: 1rem !important;
    }
    
    div[data-testid="stTextInput"] input {
        background-color: #FFFFFF !important;
        border: 2px solid #D1D5DB !important;
        color: #1F2937 !important;
        border-radius: 8px !important;
        padding: 10px !important;
    }
    div[data-testid="stSelectbox"] div[data-baseweb="select"] {
        background-color: #FFFFFF !important;
        border: 2px solid #D1D5DB !important;
        border-radius: 8px !important;
    }
    
    .question-text { font-size: 1.3rem !important; font-weight: 600; line-height: 1.8 !important; color: #1F2937; margin-bottom: 12px; }
    div.row-widget.stRadio > div { gap: 14px; margin-bottom: 40px; padding: 15px; background-color: #FFFFFF; border: 1px solid #E5E7EB; border-radius: 12px; }
    label { line-height: 1.6 !important; font-size: 1.1rem !important; color: #4B5563; font-weight: 500; }
    .stButton>button { width: 100%; font-size: 1.2rem !important; font-weight: 600 !important; padding: 12px !important; border-radius: 10px !important; }
    </style>
""", unsafe_allow_html=True)

SURVEY_DATA = {
    "depression": {"icon": "🖥️", "question": "지금 당장 내가 제일 좋아하는 유튜브 영상이나 게임을 볼 수 있다면, 내 마음이 어떨 것 같나요?", "options": ["평소처럼 생각만 해도 신나고 빨리 보고 싶다.", "오늘따라 귀찮거나 별로 하고 싶은 생각이 안 든다."], "weight": 1.37},
    "loneliness": {"icon": "🍱", "question": "오늘 학교 쉬는 시간이나 점심시간에 보낼 내 모습을 상상해보면 내 마음이 어떨 것 같나요?", "options": ["친구들과 신나게 어울려 놀거나, 혹은 혼자서 책 읽기나 그리기를 하더라도 내 마음이 편안하고 만족스러울 것 같다.", "같이 놀거나 이야기할 친구가 없어서 교실에 가만히 있거나, 어떻게 시간을 보내야 할지 몰라 마음이 불안하고 쓸쓸할 것 같다."], "weight": 1.27},
    "unhappiness": {"icon": "💭", "question": "지나간 일주일 동안 나에게 일어났던 일들을 가만히 떠올려 보면 어떤 생각이 가장 먼저 드나요?", "options": ["속상한 일도 아주 없진 않았지만, 가만히 생각해 보면 즐겁고 괜찮았던 일들이 더 먼저 떠오른다.", "즐거웠던 일은 잘 기억이 나지 않고, 자꾸 나만 힘들었거나 마음대로 되지 않아 속상했던 일들만 더 많이 떠오른다."], "weight": 1.04},
    "stress": {"icon": "📝", "question": "오늘 학교에서 예상하지 못한 작은 과제나 귀찮은 일이 갑자기 생긴다면, 내 마음이 어떨 것 같나요?", "options": ["‘얼른 해버려야지!’ 하고 가벼운 마음으로 편안하게 받아들일 수 있을 것 같다.", "오늘따라 마음의 여유가 없어서, 아주 작은 일 하나도 평소보다 훨씬 더 무겁고 답답하게 느껴질 것 같다."], "weight": 0.92},
    "anxiety": {"icon": "🎮", "question": "이번 주 일주일 동안 일어날 일들을 생각할 때, 걱정하는 마음 때문에 지금 내가 해야 할 공부나 놀이에 집중하기가 힘든가요?", "options": ["걱정이 조금 되더라도, 내가 할 일이나 친구들과 노는 것에는 별로 지장이 없다.", "걱정스러운 생각이 머릿속을 가득 채워서, 다른 일에 집중하기 어렵고 마음이 온통 그곳에 쏠려 있다."], "weight": 0.68},
    "sleep_deprivation": {"icon": "🔋", "question": "오늘 아침에 눈을 떴을 때, 내 몸과 마음의 배터리가 어느 정도 충전된 느낌이었나요?", "options": ["이불 속에서 조금 더 자고 싶긴 했지만, 막상 일어나서 세수를 하니 평소처럼 학교에 가서 활동할 에너지는 충분한 것 같다.", "잠을 자긴 했는데 피로가 전혀 풀리지 않은 것처럼 온몸이 무겁고, 하루를 시작하기도 전에 이미 에너지가 바닥난 것처럼 지친다."], "weight": 0.17}
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
        st.session_state.login_role = None
        st.session_state.needs_password_change = False
        st.rerun()
else:
    app_mode = st.sidebar.radio("접속 권한 선택", ["🧑‍🎓 학생용 채널", "🧑‍🏫 교사 관리자 채널"])

# ==========================================
# 🧑‍🎓 4. 학생용 채널
# ==========================================
if st.session_state.login_user_id is None and 'app_mode' in locals() and app_mode == "🧑‍🎓 학생용 채널":
    
    ui.card(
        title="안전한 마음 배터리 충전소",
        content="우리 반 친구들의 솔직한 이야기를 기록하는 무기명 보안 공간입니다.",
        description="2024 대한민국 청소년 빅데이터 검증 알고리즘 탑재"
    ).render()
    
    chosen_tab = ui.tabs(options=["시스템 안내", "비밀번호 규칙", "도움 청하기"], default="시스템 안내", key="info_tabs")
    
    if chosen_tab == "시스템 안내":
        st.info("💡 매주 월요일 아침, 내 마음의 배터리 용량을 솔직하게 점검하는 공간입니다. 답변은 암호화되어 안전하게 보호됩니다.")
    elif chosen_tab == "비밀번호 규칙":
        st.warning("🔒 첫 로그인 시 입력한 비밀번호가 내 고유 암호로 등록됩니다. 도용 방지를 위해 반드시 '8자 이상 16자 이하'로 만들어 주세요.")
    elif chosen_tab == "도움 청하기":
        st.error("🤝 마음이 너무 힘들거나 이야기 정리가 필요할 때는 언제든 담임 선생님을 찾아오거나, 학교 Wee 클래스 상담실의 문을 두드려 주세요.")
        
    st.divider()
    
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        with st.container(border=True):
            st.subheader("🧑‍🎓 학생 로그인 및 등록")
            
            c1, c2, c3 = st.columns(3)
            with c1: s_grade = st.selectbox("학년", list(range(1, 7)), index=3)
            with c2: s_room = st.selectbox("반", list(range(1, 13)), index=0)
            with c3: s_number = st.selectbox("번호", list(range(1, 41)), index=0)
            
            s_name = st.text_input("이름")
            s_password = st.text_input("비밀번호 (8자 ~ 16자)", type="password")
            
            if st.button("🚪 학생 로그인 / 최초 등록", type="primary"):
                if not s_name or not s_password:
                    st.error("❌ 이름과 비밀번호를 모두 입력해 주세요.")
                elif not (8 <= len(s_password) <= 16):
                    st.error("❌ 비밀번호는 반드시 8자 이상, 16자 이하여야 합니다.")
                else:
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    
                    # [수정] ? 기호를 %s 기호로 전면 교정 완료
                    cursor.execute("SELECT id, name, password_hash FROM users WHERE grade=%s AND room=%s AND number=%s AND role='student'", (s_grade, s_room, s_number))
                    user = cursor.fetchone()
                    hashed_pw = make_hash(s_password)
                    
                    if user is None:
                        try:
                            # [수정] ? 기호를 %s 기호로 전면 교정 완료
                            cursor.execute("INSERT INTO users (role, grade, room, number, name, password_hash) VALUES ('student', %s, %s, %s, %s, %s)", 
                                           (s_grade, s_room, s_number, s_name, hashed_pw))
                            conn.commit()
                            st.session_state.login_user_id = cursor.lastrowid if cursor.lastrowid else 1
                            
                            # PostgreSQL 처리를 위해 새로 저장된 ID 강제 추적 로직 보정
                            cursor.execute("SELECT id FROM users WHERE grade=%s AND room=%s AND number=%s AND role='student'", (s_grade, s_room, s_number))
                            st.session_state.login_user_id = cursor.fetchone()[0]
                            
                            st.session_state.login_user_name = f"{s_grade}학년 {s_room}반 {s_number}번 {s_name}"
                            st.session_state.login_role = "student"
                            st.session_state.needs_password_change = (s_password == "12345678")
                            st.rerun()
                        # [수정] 예외 처리 클래스를 psycopg2용으로 정밀화
                        except psycopg2.IntegrityError:
                            st.error("❌ 이미 등록된 학적 정보입니다.")
                    else:
                        if user[2] == hashed_pw:
                            if user[1] != s_name:
                                st.error(f"❌ 등록된 학생 이름과 다릅니다.")
                            else:
                                st.session_state.login_user_id = user[0]
                                st.session_state.login_user_name = f"{s_grade}학년 {s_room}반 {s_number}번 {s_name}"
                                st.session_state.login_role = "student"
                                st.session_state.needs_password_change = (s_password == "12345678")
                                st.rerun()
                        else:
                            st.error("❌ 비밀번호가 올바르지 않습니다.")
                    conn.close()

# 로그인 완료된 학생 공간
elif st.session_state.login_user_id and st.session_state.login_role == "student":
    if st.session_state.needs_password_change:
        st.title("🔒 안전을 위한 비밀번호 변경")
        st.markdown("#### 담임 선생님께서 비밀번호를 초기화하셨습니다. 첫 이용을 위해 본인만의 비밀번호를 새로 정해 주세요.")
        st.divider()
        
        _, change_col, _ = st.columns([1, 2, 1])
        with change_col:
            with st.container(border=True):
                st.subheader("⚙️ 비밀번호 재설정")
                new_pw = st.text_input("새로운 비밀번호 (8자 ~ 16자)", type="password", key="new_pw_input")
                new_pw_confirm = st.text_input("새로운 비밀번호 확인", type="password", key="new_pw_confirm_input")
                
                if st.button("🔐 변경 완료 후 입장하기", type="primary"):
                    if not (8 <= len(new_pw) <= 16):
                        st.error("❌ 새로운 비밀번호 역시 8자 이상, 16자 이하여야 합니다.")
                    elif new_pw == "12345678":
                        st.error("❌ 초기화용 임시 비밀번호('12345678')는 안전을 위해 다시 사용할 수 없습니다.")
                    elif new_pw != new_pw_confirm:
                        st.error("❌ 두 비밀번호가 서로 다릅니다. 똑같이 입력했는지 확인해 주세요.")
                    else:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        # [수정] ? -> %s
                        cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (make_hash(new_pw), st.session_state.login_user_id))
                        conn.commit()
                        conn.close()
                        
                        st.session_state.needs_password_change = False
                        st.success("🎉 비밀번호가 안전하게 변경되었습니다!")
                        st.rerun()
            
    else:
        st.title(f"🌈 {st.session_state.login_user_name} 친구, 환영해요!")
        _, w_col, _ = st.columns([1, 2, 1])
        with w_col:
            select_week = st.selectbox("📅 몇 주차 월요일 기록인가요?", [1, 2, 3, 4], format_func=lambda x: f"{x}주차")
        st.divider()
        
        responses = {}
        for key, data in SURVEY_DATA.items():
            img_col, q_col = st.columns([1, 14])
            with img_col:
                st.markdown(f"<h1 style='text-align: center; margin-top: 10px;'>{data['icon']}</h1>", unsafe_allow_html=True)
            with q_col:
                st.markdown(f"<p class='question-text'>{data['question']}</p>", unsafe_allow_html=True)
                choice = st.radio(f"choice_{key}", data["options"], label_visibility="collapsed", key=f"q_{key}")
                responses[key] = 1 if choice == data["options"][1] else 0

        _, btn_col, _ = st.columns([1, 2, 1])
        with btn_col:
            if st.button("📊 나의 마음 충전 완료!", type="primary"):
                raw_score = sum(SURVEY_DATA[k]["weight"] * responses[k] for k in SURVEY_DATA)
                raw_score = round(raw_score, 2)
                
                conn = get_db_connection()
                cursor = conn.cursor()
                prev_week = select_week - 1
                # [수정] ? -> %s
                cursor.execute("SELECT score FROM records WHERE user_id=%s AND week=%s", (st.session_state.login_user_id, prev_week))
                prev_row = cursor.fetchone()
                prev_ema = prev_row[0] if prev_row else None
                
                if prev_ema is None: new_ema = raw_score
                else: new_ema = (raw_score * 0.6) + (prev_ema * 0.4)
                new_ema = round(new_ema, 2)
                
                # PostgreSQL 대응 Upsert 구조 고도화
                cursor.execute("""
                    INSERT INTO records (user_id, week, score) VALUES (%s, %s, %s)
                    ON CONFLICT(user_id, week) DO UPDATE SET score=EXCLUDED.score
                """, (st.session_state.login_user_id, select_week, new_ema))
                conn.commit()
                conn.close()
                st.balloons()
                st.success("🎉 마음 배터리 충전 완료! 로그아웃 버튼을 눌러 창을 닫아주세요.")

# ==========================================
# 🧑‍🏫 5. 교사용 채널
# ==========================================
elif st.session_state.login_user_id is None and 'app_mode' in locals() and app_mode == "🧑‍🏫 교사 관리자 채널":
    st.title("👩‍🏫 관리자 보안 게이트")
    
    _, center_col, _ = st.columns([1, 2, 1])
    with center_col:
        with st.container(border=True):
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM users WHERE role='teacher'")
            teacher_exists = cursor.fetchone()
            conn.close()
            
            if not teacher_exists:
                st.warning("🚨 시스템 마스터 교사 계정을 신규 가입합니다.")
                t_reg_name = st.text_input("교사 성함 입력")
                t_reg_pw = st.text_input("신규 비밀번호 입력 (8자 ~ 16자)", type="password")
                
                if st.button("🔐 마스터 계정 등록 승인"):
                    if t_reg_name and t_reg_pw:
                        if not (8 <= len(t_reg_pw) <= 16):
                            st.error("❌ 비밀번호는 반드시 8자 이상, 16자 이하여야 합니다.")
                        else:
                            conn = get_db_connection()
                            cursor = conn.cursor()
                            # [수정] ? -> %s
                            cursor.execute("INSERT INTO users (role, name, password_hash) VALUES ('teacher', %s, %s)", (t_reg_name, make_hash(t_reg_pw)))
                            conn.commit()
                            conn.close()
                            st.success("등록 완료! 로그인을 진행하세요.")
                            st.rerun()
            else:
                st.subheader("🔒 관리자 로그인")
                t_login_name = st.text_input("교사 성함")
                t_login_pw = st.text_input("관리자 비밀번호", type="password")
                
                if st.button("🚪 관리자 시스템 로그인", type="primary"):
                    if not (8 <= len(t_login_pw) <= 16):
                        st.error("❌ 비밀번호 글자 수가 규격(8~16자)에 맞지 않습니다.")
                    else:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        # [수정] ? -> %s
                        cursor.execute("SELECT id, name, password_hash FROM users WHERE name=%s AND role='teacher'", (t_login_name,))
                        t_user = cursor.fetchone()
                        conn.close()
                        
                        if t_user and t_user[2] == make_hash(t_login_pw):
                            st.session_state.login_user_id = t_user[0]
                            st.session_state.login_user_name = t_user[1]
                            st.session_state.login_role = "teacher"
                            st.rerun()
                        else:
                            st.error("❌ 관리자 인증 정보가 불일치합니다.")

elif st.session_state.login_user_id and st.session_state.login_role == "teacher":
    st.title(f"👩‍🏫 {st.session_state.login_user_name} 마스터 관리자 통제실")
    st.divider()
    
    conn = get_db_connection()
    df_students = pd.read_sql_query("SELECT id, grade, room, number, name FROM users WHERE role='student' ORDER BY grade, room, number ASC", conn)
    
    if not df_students.empty:
        df_students["display_name"] = df_students.apply(lambda r: f"{r['grade']}학년 {r['room']}반 {r['number']}번 {r['name']}", axis=1)
        selected_student_id = st.selectbox("📊 관리 및 분석 대상 학생 지정", df_students["id"].tolist(), format_func=lambda x: df_students[df_students["id"]==x]["display_name"].values[0])
        
        # [수정] 판다스 쿼리문 내 파라미터도 ? 에서 %s 로 변경
        df_records = pd.read_sql_query("SELECT week, score FROM records WHERE user_id=%s ORDER BY week ASC", conn, params=(int(selected_student_id),))
        conn.close()
        
        col_dash1, col_dash2 = st.columns([1, 2])
        with col_dash1:
            st.markdown("### 📉 주간 캘리브레이션 지표")
            full_weeks = pd.DataFrame({"week": [1, 2, 3, 4]})
            df_merged = pd.merge(full_weeks, df_records, on="week", how="left")
            
            for _, row in df_merged.iterrows():
                w = int(row['week'])
                sc = row['score']
                if pd.isna(sc): st.text(f"• {w}주차 월요일: 미입력")
                else:
                    if sc >= 4.0: status = "🚨 고위험 (개입 필요)"
                    elif sc >= 3.0: status = "🔴 위험 (전화 상담 요망)"
                    elif sc >= 2.0: status = "🟠 보통/주의"
                    else: status = "🟢 안전/편안"
                    st.markdown(f"• **{w}주차**: `{sc}` $\rightarrow$ {status}")
            
            st.divider()
            st.markdown("⚙️ **해당 학생 비밀번호 관리**")
            if st.button("🔄 이 학생의 비밀번호를 '12345678'로 강제 초기화"):
                conn = get_db_connection()
                cursor = conn.cursor()
                reset_hash = make_hash("12345678")
                # [수정] ? -> %s
                cursor.execute("UPDATE users SET password_hash=%s WHERE id=%s", (reset_hash, int(selected_student_id)))
                conn.commit()
                conn.close()
                st.success("해당 학생의 비밀번호가 '12345678'로 변경되었습니다.")
                    
        with col_dash2:
            df_chart = df_records.dropna()
            if not df_chart.empty:
                df_chart["week_label"] = df_chart["week"].apply(lambda x: f"{x}주차")
                df_chart = df_chart.set_index("week_label")
                st.line_chart(df_chart[["score"]])
            else:
                st.info("선택한 학생의 누적된 주차별 정서 응답 데이터 그래프가 없습니다.")
    else:
        conn.close()
        st.info("📁 등록된 학생 데이터가 없습니다. 학생 채널에서 먼저 등록을 진행해 주세요.")