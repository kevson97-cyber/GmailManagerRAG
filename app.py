"""
app.py — Streamlit entry point for GmailManagerRAG.

Run with:  streamlit run app.py
"""
import time

import streamlit as st

from config import OLLAMA_MODEL, CREDENTIALS_FILE, MAX_EMAILS_PER_SYNC, TOKEN_FILE
from gmail_client import GmailClient
from vector_store import EmailVectorStore
from rag_engine import RAGEngine
from email_categorizer import EmailCategorizer

# ── Page configuration ────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Gmail RAG Assistant",
    page_icon="📧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    /* ── Global ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    .block-container { padding-top: 1.2rem !important; padding-bottom: 1rem !important; }

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] { background: #0d0f14; }
    section[data-testid="stSidebar"] .stRadio label {
        font-size: 13px; padding: 6px 10px; border-radius: 6px;
        transition: background 0.15s;
    }
    section[data-testid="stSidebar"] .stRadio label:hover { background: #1e2130; }

    /* ── Buttons ── */
    .stButton > button {
        border-radius: 8px !important;
        padding: 5px 14px !important;
        font-size: 12.5px !important;
        font-weight: 500 !important;
        letter-spacing: 0.01em;
        transition: transform 0.1s ease, box-shadow 0.1s ease, opacity 0.1s ease !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
    }
    .stButton > button:hover { opacity: 0.88; }
    .stButton > button:active {
        transform: scale(0.94) !important;
        box-shadow: 0 0 0 2px rgba(255,255,255,0.18) !important;
        opacity: 1 !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4f8ef7, #6c63ff) !important;
        border: none !important;
        color: #fff !important;
    }
    .stButton > button[kind="primary"]:active {
        transform: scale(0.94) !important;
        box-shadow: 0 0 0 3px rgba(99,102,241,0.45) !important;
    }

    /* ── Inputs ── */
    .stTextInput > div > div > input,
    .stNumberInput > div > div > input {
        border-radius: 8px !important;
        padding: 6px 10px !important;
        font-size: 13px !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        background: #161b27 !important;
    }
    .stTextInput > label, .stNumberInput > label { font-size: 12px !important; opacity: 0.65; }

    /* ── Metrics ── */
    [data-testid="metric-container"] {
        background: #161b27;
        border: 1px solid rgba(255,255,255,0.06);
        border-radius: 10px;
        padding: 10px 14px !important;
    }
    [data-testid="metric-container"] label { font-size: 11px !important; opacity: 0.5; }
    [data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 18px !important; font-weight: 600; }

    /* ── Chat bubbles ── */
    .chat-bubble-user {
        background: linear-gradient(135deg, #4f8ef7, #6c63ff);
        color: #fff;
        border-radius: 18px 18px 4px 18px;
        padding: 10px 15px;
        margin: 4px 0 4px 60px;
        font-size: 14px;
        line-height: 1.5;
        max-width: 88%;
        margin-left: auto;
        word-wrap: break-word;
        box-shadow: 0 2px 8px rgba(79,142,247,0.25);
    }
    .chat-bubble-assistant {
        background: #1e2433;
        color: #e8eaf0;
        border-radius: 18px 18px 18px 4px;
        padding: 10px 15px;
        margin: 4px auto 4px 0;
        font-size: 14px;
        line-height: 1.5;
        max-width: 88%;
        word-wrap: break-word;
        border: 1px solid rgba(255,255,255,0.06);
    }
    .chat-avatar { font-size: 18px; margin-bottom: 2px; }
    .chat-row { display: flex; flex-direction: column; margin-bottom: 8px; }
    .chat-row-user { align-items: flex-end; }
    .chat-row-assistant { align-items: flex-start; }

    /* ── Voice button ── */
    .voice-btn-idle {
        background: #1e2433;
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 50%;
        width: 40px; height: 40px;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer; font-size: 18px;
        transition: all 0.2s ease;
    }
    .voice-btn-recording {
        background: rgba(239,68,68,0.15);
        border: 1px solid #ef4444;
        animation: pulse 1s infinite;
    }
    @keyframes pulse {
        0%,100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.4); }
        50% { box-shadow: 0 0 0 6px rgba(239,68,68,0); }
    }

    /* ── Label chip ── */
    .label-chip {
        display: inline-block; padding: 3px 10px;
        border-radius: 20px; color: white;
        font-weight: 600; font-size: 12px; letter-spacing: 0.02em;
    }

    /* ── Expanders ── */
    .streamlit-expanderHeader { font-size: 13px !important; }

    /* ── Suggestion chips ── */
    .suggestion-chip .stButton > button {
        background: #161b27 !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        border-radius: 20px !important;
        font-size: 12px !important;
        padding: 4px 12px !important;
        white-space: nowrap;
    }

    /* ── Delete checklist ── */
    .delete-item { font-size: 13px; padding: 4px 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Cached singletons (created once per server process, not per rerun) ────────
@st.cache_resource
def _get_vector_store() -> EmailVectorStore:
    return EmailVectorStore()


@st.cache_resource
def _get_rag(_vs: EmailVectorStore) -> RAGEngine:
    return RAGEngine(_vs)


@st.cache_resource
def _get_categorizer(_vs: EmailVectorStore, _rag: RAGEngine) -> EmailCategorizer:
    return EmailCategorizer(_vs, _rag)


# ── Session state ─────────────────────────────────────────────────────────────
def _init_state():
    if "gmail" not in st.session_state:
        client = GmailClient()
        # Auto-connect if a saved token exists (no browser needed)
        if TOKEN_FILE.exists() and CREDENTIALS_FILE.exists():
            try:
                client.authenticate()
            except Exception:
                pass  # Token expired or invalid — user will connect manually
        st.session_state.gmail = client
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "categories" not in st.session_state:
        st.session_state.categories = []
    if "pending_delete" not in st.session_state:
        # list[dict]: emails awaiting trash confirmation
        st.session_state.pending_delete = []


_init_state()

gmail: GmailClient = st.session_state.gmail
vs: EmailVectorStore = _get_vector_store()
rag: RAGEngine = _get_rag(vs)
cat_engine: EmailCategorizer = _get_categorizer(vs, rag)

# ── Sidebar ────────────────────────────────────────────────────────────────────
st.sidebar.markdown(
    '<div style="font-size:14px;font-weight:700;padding:4px 0 10px">📧 Gmail Assistant</div>',
    unsafe_allow_html=True,
)

page = st.sidebar.radio(
    "Go to",
    ["🏠 Dashboard", "💬 Email Assistant", "🏷️ Categorize & Filter"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
_ollama_ok, _ollama_msg = rag.is_available()
count = vs.count()
st.sidebar.markdown(
    f'<div style="font-size:11px;opacity:0.5;line-height:1.8">'
    f'{"✅" if _ollama_ok else "⚠️"} Ollama<br>'
    f'{"✅" if gmail.is_authenticated() else "○"} Gmail<br>'
    f'📚 {count:,} indexed</div>',
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — DASHBOARD + SYNC
# ══════════════════════════════════════════════════════════════════════════════
if page == "🏠 Dashboard":
    stats = cat_engine.get_inbox_stats()
    _ok, _omsg = rag.is_available()
    _gmail_connected = gmail.is_authenticated()

    # ── Compact header + stat pills ───────────────────────────────────────────
    _gmail_val = gmail.user_email if _gmail_connected else "—"
    _ollama_val = "Ready" if _ok else "Offline"
    _ollama_col = "#22c55e" if _ok else "#ef4444"
    _gmail_col = "#22c55e" if _gmail_connected else "#f59e0b"

    st.markdown(
        f"""
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
          <span style="font-size:20px;font-weight:700">📧 Gmail Assistant</span>
        </div>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px">
          <div style="background:#161b27;border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:10px 12px">
            <div style="font-size:10px;opacity:0.45;letter-spacing:.04em;text-transform:uppercase">Indexed</div>
            <div style="font-size:20px;font-weight:700;margin-top:2px">{stats['total_indexed']:,}</div>
          </div>
          <div style="background:#161b27;border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:10px 12px">
            <div style="font-size:10px;opacity:0.45;letter-spacing:.04em;text-transform:uppercase">Senders</div>
            <div style="font-size:20px;font-weight:700;margin-top:2px">{stats['unique_senders']:,}</div>
          </div>
          <div style="background:#161b27;border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:10px 12px;overflow:hidden">
            <div style="font-size:10px;opacity:0.45;letter-spacing:.04em;text-transform:uppercase">Gmail</div>
            <div style="font-size:12px;font-weight:600;margin-top:4px;color:{_gmail_col};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{_gmail_val}</div>
          </div>
          <div style="background:#161b27;border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:10px 12px">
            <div style="font-size:10px;opacity:0.45;letter-spacing:.04em;text-transform:uppercase">Ollama</div>
            <div style="font-size:12px;font-weight:600;margin-top:4px;color:{_ollama_col}">{_ollama_val}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Gmail connection strip ────────────────────────────────────────────────
    st.markdown(
        '<div style="background:#161b27;border:1px solid rgba(255,255,255,0.07);'
        'border-radius:10px;padding:10px 14px;margin-bottom:12px;display:flex;'
        'align-items:center;gap:8px">'
        '<span style="font-size:12px;font-weight:600;opacity:0.6">Gmail</span>',
        unsafe_allow_html=True,
    )
    if not _gmail_connected:
        if not CREDENTIALS_FILE.exists():
            st.error("credentials.json missing.")
        else:
            _gc1, _gc2 = st.columns([3, 1])
            with _gc1:
                st.caption("⚠️ Not connected")
            with _gc2:
                if st.button("🔗 Connect", type="primary", use_container_width=True):
                    with st.spinner("Opening OAuth…"):
                        try:
                            gmail.authenticate()
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
    else:
        _gc1, _gc2 = st.columns([4, 1])
        with _gc1:
            st.caption(f"✅ {gmail.user_email}")
        with _gc2:
            st.markdown(
                '<style>.disconnect-btn > div > button{'
                'background:rgba(239,68,68,0.15)!important;'
                'border:1px solid rgba(239,68,68,0.5)!important;'
                'color:#f87171!important;font-weight:600!important;}'
                '.disconnect-btn > div > button:hover{'
                'background:rgba(239,68,68,0.28)!important;}'
                '.disconnect-btn > div > button:active{'
                'transform:scale(0.94)!important;'
                'box-shadow:0 0 0 2px rgba(239,68,68,0.35)!important;}'
                '</style><div class="disconnect-btn">',
                unsafe_allow_html=True,
            )
            if st.button("🔓 Disconnect", use_container_width=True):
                gmail.disconnect()
                st.session_state.gmail = GmailClient()
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Sync controls card ────────────────────────────────────────────────────
    st.markdown(
        '<div style="background:#161b27;border:1px solid rgba(255,255,255,0.07);'
        'border-radius:10px;padding:12px 14px;margin-bottom:12px">',
        unsafe_allow_html=True,
    )
    st.markdown('<span style="font-size:12px;font-weight:600;opacity:0.6">Sync Emails</span>', unsafe_allow_html=True)

    _sc1, _sc2 = st.columns([1, 2])
    with _sc1:
        max_emails = st.number_input(
            "Max emails", min_value=10, max_value=10000,
            value=MAX_EMAILS_PER_SYNC, step=50, label_visibility="collapsed",
        )
    with _sc2:
        _CATEGORY_FILTERS = {
            "All": "", "Social": "category:social", "Promos": "category:promotions",
            "Updates": "category:updates", "Forums": "category:forums", "Personal": "category:personal",
        }
        if "sync_category_filter" not in st.session_state:
            st.session_state.sync_category_filter = ""
        _bcols = st.columns(len(_CATEGORY_FILTERS))
        for _bc, (_bl, _bf) in zip(_bcols, _CATEGORY_FILTERS.items()):
            if _bc.button(_bl, key=f"cat_{_bl}", use_container_width=True):
                st.session_state.sync_category_filter = _bf
                st.rerun()
        query_filter = st.text_input(
            "filter", value=st.session_state.sync_category_filter,
            placeholder="category:social / newer_than:30d…", label_visibility="collapsed",
        )
        st.session_state.sync_category_filter = query_filter

    _sb1, _sb2 = st.columns([3, 1])
    with _sb1:
        if st.button("▶️ Start Sync", type="primary", use_container_width=True,
                     disabled=not _gmail_connected or not _ok):
            progress_bar = st.progress(0, text="Starting…")
            status_text = st.empty()
            try:
                status_text.info(f"Fetching up to {max_emails} email IDs…")
                ids = gmail.get_message_ids(max_results=max_emails, query=query_filter)
                total = len(ids)
                status_text.info(f"Found **{total}** emails. Downloading…")
                emails_data = []
                for i, msg in enumerate(ids):
                    detail = gmail.get_message_detail(msg["id"])
                    if detail:
                        emails_data.append(detail)
                    if i % 20 == 0:
                        progress_bar.progress((i + 1) / total * 0.6,
                                              text=f"Downloading {i+1}/{total}…")
                progress_bar.progress(0.65, text="Embedding…")

                def _embed_progress(done: int, total_embed: int):
                    progress_bar.progress(min(0.65 + (done / total_embed) * 0.35, 1.0),
                                          text=f"Embedding {done}/{total_embed}…")

                added = vs.add_emails(emails_data, progress_callback=_embed_progress)
                progress_bar.progress(1.0, text="Done!")
                status_text.success(f"✅ {added} new emails added · {vs.count():,} total")
                time.sleep(1)
                st.rerun()
            except Exception as exc:
                st.error(f"Sync failed: {exc}")
    with _sb2:
        if st.button("🗑️ Clear", use_container_width=True):
            vs.clear()
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Top senders ───────────────────────────────────────────────────────────
    if stats["total_indexed"] > 0:
        st.markdown(
            '<div style="background:#161b27;border:1px solid rgba(255,255,255,0.07);'
            'border-radius:10px;padding:12px 14px">',
            unsafe_allow_html=True,
        )
        st.markdown('<span style="font-size:12px;font-weight:600;opacity:0.6">Top Senders</span>', unsafe_allow_html=True)
        for sender, n in cat_engine.get_top_senders(8):
            pct = min(int(n / max(1, stats["total_indexed"]) * 100), 100)
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px">'
                f'<div style="flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;opacity:0.85">{sender}</div>'
                f'<div style="width:60px;background:rgba(255,255,255,0.06);border-radius:4px;height:5px">'
                f'<div style="width:{pct}%;background:#4f8ef7;height:5px;border-radius:4px"></div></div>'
                f'<div style="font-size:11px;opacity:0.45;min-width:28px;text-align:right">{n}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — EMAIL ASSISTANT (RAG CHAT)
# ══════════════════════════════════════════════════════════════════════════════
elif page == "💬 Email Assistant":
    _ok, _msg = rag.is_available()
    if not _ok:
        st.error(f"**Ollama not available** — {_msg}")
        st.stop()
    if vs.count() == 0:
        st.warning("No emails indexed yet. Go to **🏠 Dashboard** to sync first.")
        st.stop()

    # Header row
    _h1, _h2 = st.columns([6, 1])
    with _h1:
        st.markdown("### 💬 Email Assistant")
        st.caption("Ask anything about your inbox · say **delete** to remove emails · tap 🎤 to speak")
    with _h2:
        if st.session_state.chat_history:
            if st.button("Clear", help="Clear conversation"):
                st.session_state.chat_history = []
                st.session_state.pending_delete = []
                st.rerun()

    # ── Voice input via st.audio_input (native widget, proper mic permissions) ─
    try:
        import speech_recognition as _sr
        _sr_available = True
    except ImportError:
        _sr_available = False

    # ── Deletion confirmation panel ───────────────────────────────────────────
    if st.session_state.pending_delete:
        candidates = st.session_state.pending_delete
        st.markdown(
            f'<div style="background:#1e1a2e;border:1px solid #6c63ff44;border-radius:10px;'
            f'padding:10px 14px;margin-bottom:10px;font-size:13px">'
            f'<span style="font-weight:600;color:#a78bfa">⚠️ {len(candidates)} emails matched</span>'
            f' — review and confirm</div>',
            unsafe_allow_html=True,
        )
        selected_ids: list[str] = []
        with st.expander(f"Select emails ({len(candidates)} found)", expanded=True):
            for i, email in enumerate(candidates):
                if st.checkbox(
                    f"{email['subject'] or '(no subject)'}  ·  {email['sender']}",
                    value=True, key=f"del_check_{i}",
                ):
                    selected_ids.append(email["id"])

        _dc1, _dc2, _ = st.columns([1, 1, 4])
        with _dc1:
            if st.button(f"🗑️ Trash {len(selected_ids)}", type="primary",
                         disabled=not selected_ids or not gmail.is_authenticated()):
                with st.spinner("Moving to Trash…"):
                    trashed_ids, errors = gmail.trash_emails(selected_ids)
                    if trashed_ids:
                        vs.remove_emails(trashed_ids)
                st.session_state.pending_delete = []
                summary = f"✅ Moved **{len(trashed_ids)}** to Trash." if trashed_ids else "⚠️ No emails moved."
                if errors:
                    summary += f" ({len(errors)} failed)"
                st.session_state.chat_history.append({"role": "assistant", "content": summary})
                st.rerun()
        with _dc2:
            if st.button("✖ Cancel"):
                st.session_state.pending_delete = []
                st.session_state.chat_history.append({"role": "assistant", "content": "Deletion cancelled."})
                st.rerun()

    # ── Chat history ──────────────────────────────────────────────────────────
    for msg in st.session_state.chat_history:
        role = msg["role"]
        content = msg["content"].replace("\n", "<br>")
        if role == "user":
            st.markdown(
                f'<div class="chat-row chat-row-user"><div class="chat-bubble-user">{content}</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="chat-row chat-row-assistant">'
                f'<div class="chat-avatar">🤖</div>'
                f'<div class="chat-bubble-assistant">{content}</div></div>',
                unsafe_allow_html=True,
            )

    # ── Suggestion chips (empty state) ────────────────────────────────────────
    if not st.session_state.chat_history and not st.session_state.pending_delete:
        suggestions = [
            "What newsletters am I subscribed to?",
            "Who emails me most?",
            "Any unread order confirmations?",
            "What topics come up most?",
            "Emails needing urgent attention?",
            "Delete all promotions",
        ]
        st.markdown(
            '<div style="font-size:11px;opacity:0.4;margin:16px 0 8px">Try asking</div>',
            unsafe_allow_html=True,
        )
        # 2-column grid of chips — works well on mobile
        for i in range(0, len(suggestions), 2):
            _c1, _c2 = st.columns(2)
            for _col, _sug in zip([_c1, _c2], suggestions[i:i+2]):
                if _col.button(_sug, use_container_width=True, key=f"sug_{_sug[:12]}"):
                    st.session_state["_pending"] = _sug
                    st.rerun()

    # ── Process pending prompt (from suggestion or voice) ─────────────────────
    def _process(prompt: str):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        if rag.is_delete_intent(prompt):
            if not gmail.is_authenticated():
                reply = "⚠️ Gmail isn't connected. Go to **🏠 Dashboard** to connect first."
            else:
                with st.spinner("Searching…"):
                    candidates = rag.find_emails_for_deletion(prompt, n_results=1500)
                if candidates:
                    st.session_state.pending_delete = candidates
                    reply = f"Found **{len(candidates)}** matching emails. Review above. ☝️"
                else:
                    reply = "I couldn't find any emails matching that description."
        else:
            with st.spinner("Thinking…"):
                reply = rag.chat(prompt, st.session_state.chat_history[:-1])
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.rerun()

    if "_pending" in st.session_state:
        _process(st.session_state.pop("_pending"))

    # ── Input: text + voice ───────────────────────────────────────────────────
    user_input = st.chat_input("Ask about your emails, or say 'delete …'")
    if user_input:
        _process(user_input)

    # Voice input — uses native st.audio_input widget (no iframe, proper mic access)
    # The key rotates after each successful transcription so the widget resets
    # and doesn't re-fire the same audio on the next st.rerun().
    if _sr_available:
        if "voice_key" not in st.session_state:
            st.session_state.voice_key = 0
        with st.expander("🎤 Voice input", expanded=False):
            audio = st.audio_input(
                "Tap the mic, speak, then stop",
                key=f"voice_{st.session_state.voice_key}",
            )
            if audio:
                with st.spinner("Transcribing…"):
                    try:
                        import io as _io
                        _rec = _sr.Recognizer()
                        with _sr.AudioFile(_io.BytesIO(audio.read())) as _src:
                            _audio_data = _rec.record(_src)
                        _text = _rec.recognize_google(_audio_data)
                        if _text.strip():
                            # Rotate key BEFORE processing to reset the widget
                            st.session_state.voice_key += 1
                            st.session_state["_pending"] = _text.strip()
                            st.rerun()
                    except _sr.UnknownValueError:
                        st.warning("Could not understand — try again")
                        st.session_state.voice_key += 1
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Transcription error: {_e}")
    else:
        st.caption("💡 Install `SpeechRecognition` to enable voice input")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4 — CATEGORIZE & FILTER
# ══════════════════════════════════════════════════════════════════════════════
elif page == "🏷️ Categorize & Filter":
    st.title("🏷️ Categorize & Filter")
    st.caption(
        "AI analyses your inbox and suggests labels + Gmail filters. "
        "Apply them in one click."
    )

    _ok, _msg = rag.is_available()
    if not _ok:
        st.error(f"**Ollama is not available.** {_msg}")
        st.stop()

    if vs.count() == 0:
        st.warning("No emails indexed yet. Go to **🏠 Dashboard** to sync first.")
        st.stop()

    if not gmail.is_authenticated():
        st.info(
            "Gmail not connected — you can preview suggestions, "
            "but connect Gmail (via Dashboard) to apply labels/filters."
        )

    # ── Analyse button ───────────────────────────────────────────────────────
    if st.button("🔍 Analyse My Inbox", type="primary"):
        with st.spinner("AI is analysing your inbox patterns…"):
            st.session_state.categories = cat_engine.suggest_and_analyze()

    categories: list[dict] = st.session_state.categories

    if not categories:
        st.info("Click **Analyse My Inbox** to generate AI-powered category suggestions.")

    # ── Category cards ────────────────────────────────────────────────────────
    for i, cat in enumerate(categories):
        color = cat.get("color", "#4a90d9")
        label_html = (
            f'<span class="label-chip" style="background:{color}">{cat["name"]}</span>'
        )
        with st.expander(f"{cat['name']} — {cat['description']}", expanded=True):
            col_info, col_actions = st.columns([3, 1])

            with col_info:
                st.markdown(label_html, unsafe_allow_html=True)
                st.markdown(f"**Description:** {cat['description']}")

                criteria = cat.get("filter_criteria", {})
                if criteria:
                    st.markdown("**Suggested filter criteria:**")
                    for k, v in criteria.items():
                        st.markdown(f"- `{k}`: {v}")

                matching = cat.get("matching_emails", [])
                if matching:
                    st.markdown(f"**Sample matching emails ({len(matching)} found):**")
                    for e in matching[:5]:
                        st.markdown(
                            f"&emsp;📧 *{e['subject']}*  ·  {e['sender']}  "
                            f"·  score {e['score']}"
                        )

            with col_actions:
                st.markdown("**Apply to Gmail**")
                is_connected = gmail.is_authenticated()

                # Create label
                if st.button(
                    "➕ Create Label",
                    key=f"label_{i}",
                    disabled=not is_connected,
                    help="Creates this label in your Gmail account",
                ):
                    try:
                        gmail.create_label(cat["name"], bg_color=color)
                        st.success(f"Label '{cat['name']}' created!")
                    except Exception as exc:
                        st.error(f"Error: {exc}")

                # Create filter
                if st.button(
                    "⚙️ Create Filter",
                    key=f"filter_{i}",
                    disabled=not is_connected,
                    help="Generates and applies a Gmail filter for this category",
                ):
                    try:
                        matching_emails = cat.get("matching_emails", [])
                        filter_rules = rag.generate_filter_rules(cat, matching_emails)

                        if not filter_rules or "criteria" not in filter_rules:
                            st.warning("Could not generate filter criteria from sample emails.")
                        else:
                            # Find or create the label
                            labels = gmail.get_labels()
                            label_id = next(
                                (
                                    lbl["id"]
                                    for lbl in labels
                                    if lbl["name"].lower() == cat["name"].lower()
                                ),
                                None,
                            )
                            if not label_id:
                                new_lbl = gmail.create_label(cat["name"], bg_color=color)
                                label_id = new_lbl["id"]

                            # Substitute real label ID
                            action = filter_rules.get("action", {})
                            if "addLabelIds" in action:
                                action["addLabelIds"] = [label_id]
                            else:
                                action["addLabelIds"] = [label_id]

                            gmail.create_filter(
                                criteria=filter_rules["criteria"],
                                action=action,
                            )
                            st.success(f"Filter for '{cat['name']}' created!")
                    except Exception as exc:
                        st.error(f"Error: {exc}")

    # ── Existing labels / filters ─────────────────────────────────────────────
    if gmail.is_authenticated():
        st.markdown("---")
        st.subheader("Your Existing Gmail Setup")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Labels**")
            if st.button("Load Labels"):
                labels = gmail.get_labels()
                user_labels = [lbl for lbl in labels if lbl.get("type") == "user"]
                if user_labels:
                    for lbl in user_labels:
                        st.markdown(f"- {lbl['name']}")
                else:
                    st.info("No user labels found.")

        with col2:
            st.markdown("**Filters**")
            if st.button("Load Filters"):
                filters = gmail.get_filters()
                if filters:
                    for f in filters:
                        with st.expander(f"Filter {f['id'][:10]}…"):
                            st.json(f)
                else:
                    st.info("No filters found.")
