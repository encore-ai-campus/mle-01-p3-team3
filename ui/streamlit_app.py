"""커리(Curri) · CareerGraph 진로 탐색 채팅 화면.

실행(프로젝트 루트에서): streamlit run ui/streamlit_app.py
Streamlit Community Cloud 의 Main file path 도 ui/streamlit_app.py 로 둔다.
"""
from __future__ import annotations

import sys
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
    layout="centered",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .curri-hero-title { font-size: 1.9rem; font-weight: 700; margin: 0 0 .25rem 0; }
    .curri-hero-title span { color: #1F9E89; }
    .curri-hero-sub { color: #4B5B68; line-height: 1.6; margin-bottom: .5rem; }
    .curri-flow { display: flex; flex-wrap: wrap; gap: .35rem; align-items: center; margin: .25rem 0 .75rem 0; }
    .curri-step { background: #E7F5F1; border: 1px solid #CFE8E2; color: #1E2B37;
                  border-radius: 999px; padding: .15rem .6rem; font-size: .82rem; white-space: nowrap; }
    .curri-step.stop { background: #FFF4E5; border-color: #F3D19C; }
    .curri-arrow { color: #8AA6A0; font-size: .8rem; }
    .curri-card-label { font-size: .75rem; color: #5D7A74; font-weight: 700; letter-spacing: .02em; margin-bottom: .1rem; }
    .curri-card-value { font-size: .95rem; margin-bottom: .45rem; }
    .curri-gold { color: #B7832A; }
    </style>
    """,
    unsafe_allow_html=True,
)


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

def render_sidebar():
    """사이드바를 그리고 (선택한 회원 id, 엔진 상태 표시 자리) 를 돌려준다."""
    with st.sidebar:
        left, mid, right = st.columns([1, 2, 1])
        mid.image(MASCOT, width="stretch")
        st.markdown(
            "<div style='text-align:center'><b style='font-size:1.15rem'>커리 Curri</b><br>"
            "<span style='color:#4B5B68;font-size:.85rem'>커리어 그래프로 길을 찾는<br>진로 탐색 도우미</span></div>",
            unsafe_allow_html=True,
        )
        st.divider()

        members = cached_members()
        names = {member["user_id"]: member["display_name"] for member in members}
        user_id = st.selectbox(
            "시연 회원",
            options=[None, *names],
            format_func=lambda uid: "게스트 (회원 정보 없이)" if uid is None else f"{names[uid]} · {uid}",
            key="user_id",
            on_change=reset_conversation,
        )
        st.caption("시연용 가상 회원이에요. 실제 본인 인증이 아니에요.")

        if user_id:
            career = load_member_career(user_id)
            with st.container(border=True):
                st.markdown(
                    "<div class='curri-card-label'>지금</div>"
                    f"<div class='curri-card-value'>{career.get('current_job', '-')}<br>"
                    f"<small>{career.get('current_major', '-')} · {career.get('current_certificate', '-')}</small></div>"
                    "<div class='curri-card-label curri-gold'>🧭 목표</div>"
                    f"<div class='curri-card-value'>{career.get('target_job', '-')}<br>"
                    f"<small>{career.get('target_major', '-')} · {career.get('target_certificate', '-')}</small></div>",
                    unsafe_allow_html=True,
                )

        st.toggle("답을 찾은 과정 보기", value=True, key="show_trace")
        st.button(
            "새 대화 시작",
            icon=":material/add_comment:",
            on_click=reset_conversation,
            width="stretch",
        )

        st.divider()
        engine_slot = st.empty()
        st.caption(
            "자료: 커리어넷 직업·학과·자격 정보  \n"
            "커리는 찾은 근거 안에서만 답하고, 근거가 없으면 모른다고 말해요."
        )
    return user_id, engine_slot


# ===== 첫 화면 =====

def render_welcome(user_id: str | None) -> None:
    left, right = st.columns([1, 2], vertical_alignment="center")
    left.image(MASCOT, width="stretch")
    with right:
        st.markdown(
            "<div class='curri-hero-title'>안녕하세요, 저는 <span>커리</span>예요!</div>"
            "<div class='curri-hero-sub'>궁금한 직업·학과·자격증을 물어보면 커리어 그래프에서 "
            "근거를 찾아 길을 안내해 드릴게요.</div>",
            unsafe_allow_html=True,
        )

    st.markdown("##### 이렇게 물어보세요")
    examples = (MEMBER_EXAMPLES if user_id else []) + GENERAL_EXAMPLES
    columns = st.columns(2)
    for index, example in enumerate(examples[:4]):
        columns[index % 2].button(
            example,
            key=f"example_{index}",
            on_click=ask,
            args=(example,),
            width="stretch",
            icon="🧭" if example in MEMBER_EXAMPLES else "💬",
        )
    if not user_id:
        st.caption("왼쪽에서 시연 회원을 고르면 '내 목표 직업' 같은 맞춤 질문도 할 수 있어요.")


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
user_id, engine_slot = render_sidebar()

if not st.session_state.messages and not st.session_state.pending_question:
    render_welcome(user_id)

render_history()

typed = st.chat_input("직업, 학과, 자격증에 대해 물어보세요")
question = typed or st.session_state.pending_question
if question:
    st.session_state.pending_question = None
    answer_question(question, user_id)

# 첫 질문을 기다리지 않도록 화면을 다 그린 뒤 엔진을 미리 준비한다.
if "engine_ready" not in st.session_state:
    with engine_slot, st.spinner("커리 엔진 준비 중…"):
        try:
            get_runner()
            st.session_state.engine_ready = True
        except Exception as exc:  # noqa: BLE001
            engine_slot.error(f"엔진을 준비하지 못했어요: {type(exc).__name__}. Secrets 설정을 확인해 주세요.")
if st.session_state.get("engine_ready"):
    engine_slot.caption("🟢 커리 엔진 준비 완료")
