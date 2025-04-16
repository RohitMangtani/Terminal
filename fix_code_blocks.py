# Script to fix st.code blocks in streamlit_app.py
with open('streamlit_app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace all st.code blocks that use triple double quotes with triple single quotes
modified = content.replace('st.code("""', "st.code('''")
modified = modified.replace('""", language="python")', "''', language='python')")

with open('streamlit_app.py', 'w', encoding='utf-8') as f:
    f.write(modified)

print("All st.code blocks updated with single quotes") 