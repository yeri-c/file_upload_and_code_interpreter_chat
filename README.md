# 🤖 AI Assistant

A conversational AI assistant powered by Azure OpenAI.  
Upload files and ask questions about them, or just chat freely.

🔗 **Live Demo**: https://fileuploadandcodeinterpreterchat.streamlit.app/

---

## Features

- 💬 Chat with an AI assistant
- 📎 Upload files (PDF, TXT, DOCX, CSV, PNG, JPG) and ask questions about them
- 📚 Citations showing which file the answer came from
- 🖼️ Supports image output (charts, graphs) via Code Interpreter
- 🔄 Start a new conversation anytime

---

## Setup

### 1. Clone the repository
git clone https://github.com/your-username/your-repo.git
cd your-repo

### 2. Install dependencies
pip install -r requirements.txt

### 3. Add your credentials
Create a file at .streamlit/secrets.toml:

endpoint = "https://YOUR-RESOURCE.openai.azure.com/"
apikey = "your-api-key-here"

### 4. Run locally
streamlit run app.py

---

## Deployment (Streamlit Cloud)

1. Push this repo to GitHub (make sure secrets.toml is NOT pushed)
2. Go to streamlit.io/cloud and connect your GitHub repo
3. In Advanced Settings, paste your secrets
4. Click Deploy

---

## Project Structure

├── app.py               # Main Streamlit app

├── requirements.txt     # Python dependencies

├── .gitignore           # Files to exclude from Git

└── README.md            # This file

---

## Tech Stack

- [Streamlit](https://streamlit.io) — frontend UI
- [Azure OpenAI](https://azure.microsoft.com/en-us/products/ai-services/openai-service) — AI backend
- [OpenAI Assistants API](https://platform.openai.com/docs/assistants/overview) — file search & code interpreter
