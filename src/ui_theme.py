"""
YourKart UI theme (Flipkart-inspired) with a light/dark mode switch.

Streamlit can't switch its built-in theme at runtime, so this module injects
CSS that overrides the app colours based on `st.session_state.dark_mode`.
Both Streamlit apps call `apply_theme()` once, right after set_page_config().
"""

import streamlit as st

BRAND = "YourKart"

LIGHT = {
    "bg": "#F1F3F6",
    "surface": "#FFFFFF",
    "text": "#212121",
    "muted": "#878787",
    "border": "#E0E0E0",
    "bot_bubble": "#FFFFFF",
    "bot_text": "#212121",
    "shadow": "0 1px 3px rgba(0,0,0,.12)",
}
DARK = {
    "bg": "#0E1116",
    "surface": "#1A1F29",
    "text": "#E8EAED",
    "muted": "#9AA3B2",
    "border": "#2C3442",
    "bot_bubble": "#232B38",
    "bot_text": "#E8EAED",
    "shadow": "0 1px 3px rgba(0,0,0,.6)",
}

PRIMARY = "#2874F0"   # Flipkart-style blue
ACCENT = "#FFE11B"    # yellow accent
ORANGE = "#FB641B"    # call-to-action orange


def _css(c: dict) -> str:
    return f"""
<style>
:root {{
  --yk-primary: {PRIMARY};
  --yk-accent: {ACCENT};
  --yk-orange: {ORANGE};
  --yk-bg: {c['bg']};
  --yk-surface: {c['surface']};
  --yk-text: {c['text']};
  --yk-muted: {c['muted']};
  --yk-border: {c['border']};
  --yk-bot: {c['bot_bubble']};
  --yk-bot-text: {c['bot_text']};
  --yk-shadow: {c['shadow']};
}}

/* App shell */
.stApp, [data-testid="stAppViewContainer"] {{ background: var(--yk-bg); color: var(--yk-text); }}
[data-testid="stHeader"] {{ background: transparent; }}
.stDeployButton, [data-testid="stAppDeployButton"], #MainMenu, footer {{ display: none !important; }}
.block-container {{ max-width: 820px; padding-top: 1.2rem; padding-bottom: 6rem; }}
[data-testid="stSidebar"] {{ background: var(--yk-surface); border-right: 1px solid var(--yk-border); }}
[data-testid="stSidebar"] * {{ color: var(--yk-text); }}
h1, h2, h3, h4, p, li, label, span, div {{ color: inherit; }}
.stMarkdown, .stCaption, [data-testid="stCaptionContainer"] {{ color: var(--yk-text); }}
[data-testid="stCaptionContainer"] {{ color: var(--yk-muted); }}

/* Brand header bar */
.yk-header {{
  background: var(--yk-primary); color: #fff; border-radius: 12px;
  padding: 14px 18px; display: flex; align-items: center;
  justify-content: space-between; box-shadow: var(--yk-shadow); margin-bottom: 14px;
}}
.yk-logo {{ font-style: italic; font-weight: 800; font-size: 26px; line-height: 1; color: #fff; }}
.yk-logo small {{ display: block; font-size: 11px; font-weight: 500; margin-top: 3px; color: #fff; }}
.yk-logo small b {{ color: var(--yk-accent); }}
.yk-status {{ font-size: 13px; color: #fff; display: flex; align-items: center; gap: 8px; text-align: right; }}
.yk-dot {{ width: 9px; height: 9px; border-radius: 50%; background: #4cd964; display: inline-block; }}
.yk-header * {{ color: #fff; }}
.yk-header .yk-logo small b {{ color: var(--yk-accent); }}

/* Chat bubbles */
[data-testid="stChatMessage"] {{ background: transparent; padding: .3rem 0; gap: .6rem; }}
[data-testid="stChatMessageContent"] {{
  background: var(--yk-bot); color: var(--yk-bot-text);
  border-radius: 4px 16px 16px 16px; padding: .7rem 1rem;
  width: fit-content; max-width: 82%; box-shadow: var(--yk-shadow);
  border: 1px solid var(--yk-border);
}}
[data-testid="stChatMessageContent"] p, [data-testid="stChatMessageContent"] li,
[data-testid="stChatMessageContent"] td, [data-testid="stChatMessageContent"] th {{ color: inherit; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ flex-direction: row-reverse; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {{
  background: var(--yk-primary); color: #fff; border-radius: 16px 4px 16px 16px; border: none;
  margin-left: auto;
}}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] * {{ color: #fff; }}
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"] {{
  background: var(--yk-accent); color: #212121; border-radius: 50%;
}}

/* Chat input */
[data-testid="stBottom"], [data-testid="stBottom"] > div {{ background: var(--yk-bg); }}
[data-testid="stChatInput"] {{ background: var(--yk-surface); border: 1px solid var(--yk-border); border-radius: 24px; }}
[data-testid="stChatInput"] textarea {{ color: var(--yk-text); background: transparent; }}
[data-testid="stChatInput"] button {{ background: var(--yk-primary); color: #fff; border-radius: 50%; }}

/* Buttons (quick-reply chips) */
.stButton > button {{
  border-radius: 20px; border: 1px solid var(--yk-primary); color: var(--yk-primary);
  background: var(--yk-surface); font-weight: 600; padding: .35rem .9rem;
}}
.stButton > button:hover {{ background: var(--yk-primary); color: #fff; border-color: var(--yk-primary); }}
.stButton > button p {{ color: inherit; }}
[data-testid="stFormSubmitButton"] > button {{
  background: var(--yk-orange); border: none; color: #fff; border-radius: 4px; width: 100%; padding: .6rem;
}}
[data-testid="stFormSubmitButton"] > button:hover {{ background: #e5581a; color: #fff; }}

/* Form fields and cards */
[data-testid="stTextInput"] input {{ background: var(--yk-surface); color: var(--yk-text); border: 1px solid var(--yk-border); }}
[data-testid="stForm"] {{ background: var(--yk-surface); border: 1px solid var(--yk-border); border-radius: 12px; box-shadow: var(--yk-shadow); }}
[data-testid="stExpander"] {{ background: var(--yk-surface); border: 1px solid var(--yk-border); border-radius: 10px; }}
[data-testid="stSelectbox"] > div > div {{ background: var(--yk-surface); color: var(--yk-text); }}
hr {{ border-color: var(--yk-border); }}
</style>
"""


def apply_theme() -> bool:
    """Render the dark-mode toggle in the sidebar and inject the theme CSS.
    Returns True when dark mode is on."""
    st.session_state.setdefault("dark_mode", False)
    with st.sidebar:
        st.toggle("🌙 Dark mode", key="dark_mode")
    dark = bool(st.session_state.dark_mode)
    st.markdown(_css(DARK if dark else LIGHT), unsafe_allow_html=True)
    return dark


def render_header(subtitle: str = "Virtual Assistant · Online") -> None:
    st.markdown(
        f"""
<div class="yk-header">
  <div class="yk-logo">{BRAND}<small>Explore <b>Plus</b> ✦</small></div>
  <div class="yk-status"><span class="yk-dot"></span>{subtitle}</div>
</div>
""",
        unsafe_allow_html=True,
    )
