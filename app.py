# app.py
import json
import time
import streamlit as st
from openai import AzureOpenAI
from datetime import datetime
from zoneinfo import ZoneInfo

# Page config
st.set_page_config(page_title="AI Assistant", page_icon="🤖", layout="centered")
st.title("🤖 AI Assistant")
st.caption("Upload files, ask questions, check the time, or do math!")

# Client setup
client = AzureOpenAI(
    azure_endpoint=st.secrets["endpoint"],
    api_key=st.secrets["apikey"],
    api_version="2024-05-01-preview"
)

deployment_name = "gpt-4o-mini-10ai028"

# Timezone data
TIMEZONE_DATA = {
    "tokyo": "Asia/Tokyo",
    "san francisco": "America/Los_Angeles",
    "paris": "Europe/Paris",
    "london": "Europe/London",
    "new york": "America/New_York",
    "seoul": "Asia/Seoul",
}

# Tool functions
def get_current_time(location):
    location_lower = location.lower()
    for key, timezone in TIMEZONE_DATA.items():
        if key in location_lower:
            current_time = datetime.now(ZoneInfo(timezone)).strftime("%I:%M %p")
            return json.dumps({"location": location, "current_time": current_time})
    return json.dumps({"location": location, "current_time": "unknown"})

def add_two_numbers(a, b):
    return json.dumps({"a": a, "b": b, "result": a + b})

def dispatch_tool(tool_name, args):
    if tool_name == "get_current_time":
        return get_current_time(args.get("location"))
    elif tool_name == "add_two_numbers":
        return add_two_numbers(args.get("a"), args.get("b"))
    return json.dumps({"error": "unknown tool"})

# Tool definitions
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current time in a given city",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city name, e.g. Tokyo"
                    }
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_two_numbers",
            "description": "Add two numbers and return the sum",
            "parameters": {
                "type": "object",
                "properties": {
                    "a": {"type": "number", "description": "The first number"},
                    "b": {"type": "number", "description": "The second number"}
                },
                "required": ["a", "b"]
            }
        }
    }
]

# Assistant setup (file search)
@st.cache_resource
def create_assistant():
    return client.beta.assistants.create(
        model=deployment_name,
        instructions="You are a helpful assistant. Answer based on uploaded files if provided.",
        tools=[{"type": "file_search"}, {"type": "code_interpreter"}],
        temperature=1,
        top_p=1
    )

assistant = create_assistant()

# Session state init
if "thread_id" not in st.session_state:
    st.session_state.thread_id = client.beta.threads.create().id

if "messages" not in st.session_state:
    st.session_state.messages = []

if "file_id_to_name" not in st.session_state:
    st.session_state.file_id_to_name = {}

if "uploaded_file_ids" not in st.session_state:
    st.session_state.uploaded_file_ids = []

if "file_summaries" not in st.session_state:
    st.session_state.file_summaries = {}

# Helper: file summary
def get_file_summary(file_id):
    temp_thread = client.beta.threads.create()
    client.beta.threads.messages.create(
        thread_id=temp_thread.id,
        role="user",
        content="Please summarize the contents of this file in 3-5 sentences.",
        attachments=[{"file_id": file_id, "tools": [{"type": "file_search"}]}]
    )
    run = client.beta.threads.runs.create(
        thread_id=temp_thread.id,
        assistant_id=assistant.id
    )
    while run.status in ['queued', 'in_progress', 'cancelling']:
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(
            thread_id=temp_thread.id,
            run_id=run.id
        )
    if run.status == 'completed':
        msgs = client.beta.threads.messages.list(thread_id=temp_thread.id)
        return msgs.data[0].content[0].text.value
    return "Summary unavailable."

# Helper: parse citations
def parse_citations(message_obj):
    text_block = message_obj.content[0].text
    raw_text = text_block.value
    annotations = text_block.annotations
    citations = []
    seen = {}
    for i, annotation in enumerate(annotations):
        raw_text = raw_text.replace(annotation.text, f" `[{i+1}]`")
        if hasattr(annotation, "file_citation"):
            cited_file_id = annotation.file_citation.file_id
            filename = st.session_state.file_id_to_name.get(cited_file_id, cited_file_id)
            if filename not in seen:
                seen[filename] = i + 1
                citations.append(f"[{i+1}] 📄 {filename}")
    return raw_text, citations

# Helper: run with tool calling (no files)
def run_with_tools(user_message):
    messages = [{"role": "user", "content": user_message}]
    response = client.chat.completions.create(
        model=deployment_name,
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )
    response_message = response.choices[0].message
    messages.append(response_message)

    tool_calls_made = []
    if response_message.tool_calls:
        for tool_call in response_message.tool_calls:
            tool_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            result = dispatch_tool(tool_name, args)
            tool_calls_made.append({
                "tool": tool_name,
                "args": args,
                "result": json.loads(result)
            })
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": tool_name,
                "content": result
            })
        final_response = client.chat.completions.create(
            model=deployment_name,
            messages=messages
        )
        return final_response.choices[0].message.content, tool_calls_made
    return response_message.content, []

# Helper: run with assistant (with files)
def run_with_assistant(user_message):
    attachments = [
        {"file_id": fid, "tools": [{"type": "file_search"}, {"type": "code_interpreter"}]}
        for fid in st.session_state.uploaded_file_ids
    ]
    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=user_message,
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
    return run

# Sidebar
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
                with st.spinner(f"Summarizing {uploaded_file.name}..."):
                    summary = get_file_summary(st.session_state[file_key])
                    st.session_state.file_summaries[st.session_state[file_key]] = summary
            else:
                st.info(f"✅ {uploaded_file.name}")
            current_file_ids.append(st.session_state[file_key])
        st.session_state.uploaded_file_ids = current_file_ids
    else:
        st.session_state.uploaded_file_ids = []
        st.info("You can also ask questions without a file.")

    if st.session_state.uploaded_file_ids:
        st.divider()
        st.markdown(f"**{len(st.session_state.uploaded_file_ids)} file(s) active:**")
        for fid in st.session_state.uploaded_file_ids:
            fname = st.session_state.file_id_to_name.get(fid, fid)
            summary = st.session_state.file_summaries.get(fid)
            with st.expander(f"📄 {fname}"):
                st.markdown(summary if summary else "No summary available.")

    st.divider()
    st.markdown("**💡 Try asking:**")
    st.markdown("- What time is it in Tokyo?")
    st.markdown("- What is 123 + 456?")
    st.markdown("- What time is it in Paris and what is 99 + 1?")

    st.divider()
    if st.button("🔄 New Conversation"):
        st.session_state.thread_id = client.beta.threads.create().id
        st.session_state.messages = []
        st.rerun()

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["type"] == "text":
            st.markdown(msg["content"])
            if msg.get("citations"):
                with st.expander("📚 Sources"):
                    for c in msg["citations"]:
                        st.markdown(c)
            if msg.get("tool_calls"):
                with st.expander("🔧 Tool Calls"):
                    for tc in msg["tool_calls"]:
                        st.markdown(f"**Tool:** `{tc['tool']}`")
                        st.markdown(f"**Input:** `{tc['args']}`")
                        st.markdown(f"**Result:** `{tc['result']}`")
                        st.divider()
        elif msg["type"] == "image":
            st.image(msg["content"])

# Chat input
if prompt := st.chat_input("Type your question here..."):

    st.session_state.messages.append({"role": "user", "type": "text", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):

            # Use tool calling if no files uploaded
            if not st.session_state.uploaded_file_ids:
                answer, tool_calls_made = run_with_tools(prompt)
                st.markdown(answer)
                if tool_calls_made:
                    with st.expander("🔧 Tool Calls"):
                        for tc in tool_calls_made:
                            st.markdown(f"**Tool:** `{tc['tool']}`")
                            st.markdown(f"**Input:** `{tc['args']}`")
                            st.markdown(f"**Result:** `{tc['result']}`")
                            st.divider()
                st.session_state.messages.append({
                    "role": "assistant", "type": "text",
                    "content": answer, "tool_calls": tool_calls_made
                })

            # Use assistant if files are uploaded
            else:
                run = run_with_assistant(prompt)
                if run.status == 'completed':
                    msgs = client.beta.threads.messages.list(
                        thread_id=st.session_state.thread_id
                    )
                    response_msg = msgs.data[0]
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
                                "content": cleaned_text, "citations": citations
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
