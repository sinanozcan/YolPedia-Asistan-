# UIComponents.py adında yeni bir dosya oluşturun

import streamlit as st

class UIComponents:
    @staticmethod
    def render_message(message):
        """Mesajı Streamlit'te görüntüler"""
        if isinstance(message, dict) and "role" in message:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])
        elif isinstance(message, str):
            st.markdown(message)
        else:
            # Diğer formatlar için
            with st.chat_message("assistant"):
                st.write(message)