"""Voice Practice: daily conversation, workplace, presentation, role-play and free talk."""

import streamlit as st

from ui.conversation_view import ConversationView

st.title("Voice Practice")
st.caption("Speak with your offline AI partner. Recording only starts when you press the microphone.")

ConversationView("voice", ["daily", "workplace", "presentation", "roleplay", "free"]).render()
