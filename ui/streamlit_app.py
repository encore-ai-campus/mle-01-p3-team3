"""커리(Curri) · CareerGraph 진로 탐색 채팅 화면.

실행(프로젝트 루트에서): streamlit run ui/streamlit_app.py
Streamlit Community Cloud 의 Main file path 도 ui/streamlit_app.py 로 둔다.
"""
from __future__ import annotations

import sys
import base64
from html import escape
import uuid
from pathlib import Path

import streamlit as st

UI_DIR = Path(__file__).resolve().parent
PROJECT_DIR = UI_DIR.parent
for path in (str(PROJECT_DIR), str(UI_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from catalog import (  # noqa: E402
    GUARD_LABELS,
    SEARCH_LABELS,
    STEP_LABELS,
    VERIFY_LABELS,
    list_demo_members,
    load_member_career,
    summarize_turn,
)

AVATAR = str(UI_DIR / "assets" / "curri_avatar.png")
MASCOT = str(UI_DIR / "assets" / "curri_full.png")
USER_AVATAR = ":material/person:"

GENERAL_EXAMPLES = [
    "간호사가 되려면 어떤 전공이 필요해?",
    "데이터를 분석하는 일을 하는 직업을 알려줘",
    "정보보안 관련 자격증에는 뭐가 있어?",
]
MEMBER_EXAMPLES = [
    "내 목표 직업에 필요한 자격증 알려줘",
    "지금 내 전공으로 갈 수 있는 다른 직업은?",
]

ERROR_REPLY = "지금은 답변을 만들 수 없어요. 잠시 후 다시 물어봐 주세요."

st.set_page_config(
    page_title="커리 · CareerGraph",
    page_icon=AVATAR,
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(f"<style>{(UI_DIR / 'styles.css').read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


# ===== 상태 =====

def init_state() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("thread_id", str(uuid.uuid4()))
    st.session_state.setdefault("pending_question", None)


def reset_conversation() -> None:
    """회원을 바꾸거나 새 대화를 열면 대화 기억(thread)도 새로 만든다."""

    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.pending_question = None


def ask(question: str) -> None:
    st.session_state.pending_question = question


@st.cache_resource(show_spinner=False)
def get_runner():
    """그래프·레일을 프로세스당 한 번만 만든다(처음 한 번은 1분 가까이 걸린다)."""

    from backend import AgentRunner

    return AgentRunner()


@st.cache_data(show_spinner=False)
def cached_members() -> list[dict[str, str]]:
    return list_demo_members()


# ===== 사이드바 =====

def render_topbar():
    """회원 선택과 대화 설정을 상단에 모은다."""
    with st.container(key="brandbar"):
        brand, action = st.columns([5, 1], vertical_alignment="center")
        brand.markdown("<div class='curri-brand'>🧭 <strong>커리 Curri</strong><span>진로 탐색 도우미</span></div>", unsafe_allow_html=True)
        action.button("새 대화", icon=":material/add_comment:", on_click=reset_conversation, width="stretch")
    members = cached_members()
    names = {member["user_id"]: member["display_name"] for member in members}
    with st.container(key="settings"):
        member, trace = st.columns([7, 4], vertical_alignment="center")
        with member:
            label, field = st.columns([1, 4], vertical_alignment="center")
            label.markdown("**시연 회원**")
            with field:
                user_id = st.selectbox("시연 회원", options=[None, *names],
                    format_func=lambda uid: "게스트 (회원 정보 없이)" if uid is None else f"{names[uid]} · {uid}",
                    key="user_id", on_change=reset_conversation, label_visibility="collapsed")
                st.caption("가상 회원을 선택해 맞춤 질문을 체험해 보세요. 실제 본인 인증은 아니에요.")
        with trace:
            st.toggle("답을 찾은 과정 보기", value=True, key="show_trace")
    if user_id:
        career = load_member_career(user_id)
        with st.expander("선택한 회원의 커리어 정보", expanded=True):
            current, target = st.columns(2)
            for column, title, prefix in ((current, "지금", "current"), (target, "🧭 목표", "target")):
                column.markdown(f"**{title}**")
                column.write(career.get(f"{prefix}_job", "-"))
                column.caption(f"{career.get(f'{prefix}_major', '-')} · {career.get(f'{prefix}_certificate', '-')}")
    return user_id


def render_welcome(user_id: str | None):
    with st.container(key="welcome"):
        mascot = base64.b64encode(Path(MASCOT).read_bytes()).decode()
        st.markdown(
            "<div class='curri-hero'><div class='curri-copy'>"
            "<div class='curri-eyebrow'>커리와 시작하는 진로 탐색</div>"
            "<h1>궁금한 진로 이야기,<br>여기서 시작해 볼까요?</h1>"
            "<p>직업·학과·자격증에 대해 편하게 물어보세요.</p></div>"
            f"<div class='curri-mascot'><img alt='나침반을 든 커리 마스코트' src='data:image/png;base64,{mascot}'></div></div>",
            unsafe_allow_html=True,
        )
        typed = st.chat_input("예: 간호사가 되려면 어떤 전공이 필요해?", key="welcome_input")
        st.markdown("<div class='curri-suggestions-title'>바로 시작하고 싶다면, 질문을 골라보세요</div>", unsafe_allow_html=True)
        labels = ["직업과 전공", "관심 분야와 직업", "직업과 자격증"]
        icons = [":material/school:", ":material/bar_chart:", ":material/workspace_premium:"]
        columns = st.columns(3, gap="small")
        for index, (column, example) in enumerate(zip(columns, GENERAL_EXAMPLES)):
            with column, st.container(key=f"question_{index}"):
                st.button(f"{labels[index]}\n\n**{example}**", key=f"example_{index}", on_click=ask,
                    args=(example,), icon=icons[index], width="stretch")
        if user_id:
            personal = st.columns(2)
            for index, example in enumerate(MEMBER_EXAMPLES):
                personal[index].button(example, key=f"personal_{index}", on_click=ask, args=(example,), width="stretch", icon="🧭")
        else:
            st.markdown("<div class='curri-tip'><span>ⓘ</span> 상단에서 시연 회원을 선택하면 ‘내 목표 직업’ 같은 맞춤 질문도 할 수 있어요.</div>", unsafe_allow_html=True)
    return typed




# ===== 메시지 =====

def flow_html(trace: list[str]) -> str:
    chips = []
    for name in trace:
        icon, label = STEP_LABELS[name]
        stop = " stop" if name in {"abstain"} else ""
        chips.append(f"<span class='curri-step{stop}'>{icon} {label}</span>")
    arrow = "<span class='curri-arrow'>›</span>"
    return f"<div class='curri-flow'>{arrow.join(chips)}</div>"


def render_trace(meta: dict) -> None:
    with st.expander("커리가 답을 찾은 과정", icon=":material/route:"):
        st.markdown(flow_html(meta["trace"]), unsafe_allow_html=True)

        columns = st.columns(4)
        columns[0].markdown(f"**질문 검사**  \n{GUARD_LABELS.get(meta['input_guard'], '—')}")
        columns[1].markdown(
            f"**검색**  \n{SEARCH_LABELS.get(meta['search_mode'], '—')}"
            + (f" · 재검색 {meta['retry_count']}회" if meta["retry_count"] else "")
        )
        columns[2].markdown(f"**근거 대조**  \n{VERIFY_LABELS.get(meta['verification'], '—')}")
        columns[3].markdown(f"**답변 검사**  \n{GUARD_LABELS.get(meta['output_guard'], '—')}")

        rules = [rule for rule in (meta["input_rule"], meta["output_rule"]) if rule]
        if rules:
            st.caption("막은 규칙: " + ", ".join(rules))
        if meta["profile_used"]:
            st.caption("🗂️ 선택한 회원의 저장된 커리어를 참고했어요.")

        if meta["evidence"]:
            st.markdown(f"**찾은 근거 {len(meta['evidence'])}개**")
            st.dataframe(meta["evidence"], hide_index=True, width="stretch")


def is_guard_stop(meta: dict) -> bool:
    return meta.get("input_guard") in {"blocked", "modified"} or meta.get("output_guard") in {"blocked", "modified"}


def render_answer(content: str, meta: dict | None) -> None:
    if meta and is_guard_stop(meta):
        st.badge("가드레일", icon=":material/shield:", color="orange")
    elif meta and meta.get("status") == "abstain":
        st.badge("답변 보류", icon=":material/help:", color="gray")
    st.markdown(content)
    if meta and st.session_state.get("show_trace"):
        render_trace(meta)


def render_history() -> None:
    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user", avatar=USER_AVATAR):
                st.markdown(message["content"])
        else:
            with st.chat_message("assistant", avatar=AVATAR):
                render_answer(message["content"], message.get("meta"))


def answer_question(question: str, user_id: str | None) -> None:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(question)

    with st.chat_message("assistant", avatar=AVATAR):
        status = st.status("커리가 답을 찾고 있어요…", expanded=False)
        meta = None
        try:
            if "engine_ready" not in st.session_state:
                status.update(label="커리가 준비 중이에요… (처음 한 번은 1분 정도 걸려요)")
            runner = get_runner()
            st.session_state.engine_ready = True

            final_state = None
            for kind, payload in runner.stream(question, st.session_state.thread_id, user_id):
                if kind == "step" and payload in STEP_LABELS:
                    icon, label = STEP_LABELS[payload]
                    status.update(label=f"{icon} {label} 중…")
                    status.write(f"{icon} {label}")
                elif kind == "final":
                    final_state = payload
                elif kind == "error":
                    raise payload

            meta = summarize_turn(final_state or {})
            content = meta["answer"] or ERROR_REPLY
            if is_guard_stop(meta):
                done_label = "🛡️ 가드레일이 확인했어요"
            elif meta["status"] == "abstain":
                done_label = "🤔 근거가 부족해 답을 보류했어요"
            else:
                done_label = "답을 찾았어요"
            status.update(label=done_label, state="complete")
        except Exception as exc:  # noqa: BLE001 - 사용자에게는 오류 종류만 보인다
            content = ERROR_REPLY
            status.update(label=f"문제가 생겼어요 ({type(exc).__name__})", state="error")

        render_answer(content, meta)

    st.session_state.messages.append({"role": "assistant", "content": content, "meta": meta})


# ===== 화면 =====

init_state()
user_id = render_topbar()

welcome = not st.session_state.messages and not st.session_state.pending_question
if welcome:
    typed = render_welcome(user_id)
    if typed:
        ask(typed)
        st.rerun()
else:
    with st.container(key="conversation"):
        render_history()
        if st.session_state.pending_question:
            question = st.session_state.pending_question
            st.session_state.pending_question = None
            answer_question(question, user_id)
            st.rerun()
    typed = st.chat_input("직업, 학과, 자격증에 대해 물어보세요", key="conversation_input")
    if typed:
        ask(typed)
        st.rerun()

with st.container(key="footer"):
    status_col, source_col = st.columns([1, 2])
    engine_slot = status_col.empty()
    source_col.markdown("<div class='curri-source'>커리어넷 자료 기반 · 확인된 근거 안에서 안내해요.</div>", unsafe_allow_html=True)

# 기존 엔진 사전 준비 동작은 유지하며, 상태 안내는 화면 하단에 표시한다.
if "engine_ready" not in st.session_state:
    with engine_slot, st.spinner("답변을 준비하고 있어요…"):
        try:
            get_runner()
            st.session_state.engine_ready = True
        except Exception as exc:  # noqa: BLE001
            engine_slot.caption("🟠 답변 연결을 확인해 주세요.")
            with st.expander("연결 상태 자세히 보기"):
                st.error(f"엔진을 준비하지 못했어요: {type(exc).__name__}. Secrets 설정을 확인해 주세요.")
if st.session_state.get("engine_ready"):
    engine_slot.markdown("<div class='curri-ready'>● <span>대화할 준비가 되었어요</span></div>", unsafe_allow_html=True)
