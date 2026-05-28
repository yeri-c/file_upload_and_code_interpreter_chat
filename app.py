# app.py
import time
import streamlit as st
from openai import AzureOpenAI

# Page
st.set_page_config(page_title="AI Assistant", page_icon="🤖", layout="centered")
st.title("🤖 AI Assistant")
st.caption("Upload files and ask anything!")

# Client setup
client = AzureOpenAI(
    azure_endpoint=st.secrets["endpoint"],
    api_key=st.secrets["apikey"],
    api_version="2024-05-01-preview"
)

# Assistant setup
@st.cache_resource
def create_assistant():
    return client.beta.assistants.create(
        model="gpt-4o-mini-10ai028",
        instructions="You are a helpful assistant. Answer based on the uploaded files if provided.",
        tools=[{"type": "file_search"}, {"type": "code_interpreter"}],
        temperature=1,
        top_p=1
    )

assistant = create_assistant()

# Session state
if "thread_id" not in st.session_state:
    thread = client.beta.threads.create()
    st.session_state.thread_id = thread.id

if "messages" not in st.session_state:
    st.session_state.messages = []

if "file_id_to_name" not in st.session_state:
    st.session_state.file_id_to_name = {}

if "uploaded_file_ids" not in st.session_state:
    st.session_state.uploaded_file_ids = []  # list of currently active file IDs

# Sidebar: file upload
with st.sidebar:
    st.header("📎 File Upload")
    uploaded_files = st.file_uploader(
        "Upload one or more files",
        type=["pdf", "txt", "docx", "csv", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    if uploaded_files:
        current_file_ids = []
        for uploaded_file in uploaded_files:
            file_key = f"uploaded_{uploaded_file.name}"
            if file_key not in st.session_state:
                with st.spinner(f"Uploading {uploaded_file.name}..."):
                    response = client.files.create(
                        file=(uploaded_file.name, uploaded_file.getvalue()),
                        purpose="assistants"
                    )
                    st.session_state[file_key] = response.id
                    st.session_state.file_id_to_name[response.id] = uploaded_file.name
                    st.success(f"✅ Uploaded: {uploaded_file.name}")
            else:
                st.info(f"✅ {uploaded_file.name}")

            current_file_ids.append(st.session_state[file_key])

        st.session_state.uploaded_file_ids = current_file_ids

    else:
        st.session_state.uploaded_file_ids = []
        st.info("You can also ask questions without a file.")

    # Show active files summary
    if st.session_state.uploaded_file_ids:
        st.divider()
        st.markdown(f"**{len(st.session_state.uploaded_file_ids)} file(s) active:**")
        for fid in st.session_state.uploaded_file_ids:
            fname = st.session_state.file_id_to_name.get(fid, fid)
            st.markdown(f"- 📄 {fname}")

    st.divider()
    if st.button("🔄 New Conversation"):
        st.session_state.thread_id = client.beta.threads.create().id
        st.session_state.messages = []
        st.rerun()

# Parse citations
def parse_citations(message_obj):
    text_block = message_obj.content[0].text
    raw_text = text_block.value
    annotations = text_block.annotations

    citations = []
    seen = {}  # avoid duplicate citations from same file
    for i, annotation in enumerate(annotations):
        raw_text = raw_text.replace(annotation.text, f" `[{i+1}]`")
        if hasattr(annotation, "file_citation"):
            cited_file_id = annotation.file_citation.file_id
            filename = st.session_state.file_id_to_name.get(cited_file_id, cited_file_id)
            if filename not in seen:
                seen[filename] = i + 1
                citations.append(f"[{i+1}] 📄 {filename}")

    return raw_text, citations

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["type"] == "text":
            st.markdown(msg["content"])
            if msg.get("citations"):
                with st.expander("📚 Sources"):
                    for c in msg["citations"]:
                        st.markdown(c)
        elif msg["type"] == "image":
            st.image(msg["content"])

# Chat input
if prompt := st.chat_input("Type your question here..."):

    st.session_state.messages.append({"role": "user", "type": "text", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            # Attach all active files
            attachments = [
                {
                    "file_id": fid,
                    "tools": [{"type": "file_search"}, {"type": "code_interpreter"}]
                }
                for fid in st.session_state.uploaded_file_ids
            ]

            client.beta.threads.messages.create(
                thread_id=st.session_state.thread_id,
                role="user",
                content=prompt,
                attachments=attachments if attachments else None
            )

            run = client.beta.threads.runs.create(
                thread_id=st.session_state.thread_id,
                assistant_id=assistant.id
            )

            while run.status in ['queued', 'in_progress', 'cancelling']:
                time.sleep(1)
                run = client.beta.threads.runs.retrieve(
                    thread_id=st.session_state.thread_id,
                    run_id=run.id
                )

            if run.status == 'completed':
                messages = client.beta.threads.messages.list(
                    thread_id=st.session_state.thread_id
                )
                response_msg = messages.data[0]

                for block in response_msg.content:
                    if block.type == "text":
                        cleaned_text, citations = parse_citations(response_msg)
                        st.markdown(cleaned_text)
                        if citations:
                            with st.expander("📚 Sources"):
                                for c in citations:
                                    st.markdown(c)
                        st.session_state.messages.append({
                            "role": "assistant", "type": "text",
                            "content": cleaned_text,
                            "citations": citations
                        })
                    elif block.type == "image_file":
                        image_bytes = client.files.content(block.image_file.file_id).read()
                        st.image(image_bytes)
                        st.session_state.messages.append({
                            "role": "assistant", "type": "image",
                            "content": image_bytes
                        })
            else:
                st.error(f"Something went wrong: {run.status}")
