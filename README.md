# 🍳 Recipe Assistant

An AI-powered culinary companion built with Google's Agent Development Kit (ADK), Google GenAI, and Vertex AI Agent Engine.

![Recipe Assistant Demo](demo.gif)

---

## 🌟 Architecture & Implemented Capabilities

Recipe Assistant integrates with Google Cloud services and AI tools to deliver a full-stack culinary agent experience:

### 1. 🧠 Vertex AI Memory Bank
- **Session Fact Preservation**: Automatically preloads and updates long-term memory across sessions using `PreloadMemoryTool` and `add_session_to_memory` callbacks.
- Remembers user dietary preferences, allergies, and favorite cuisines automatically across turns.

### 2. 🗄️ Google Cloud Firestore
- **Recipe Management & Search**: Queries recipes by cuisine, ingredients, maximum prep time, and dietary restrictions (`[Gluten-Free]`, `⚠️ Contains Peanuts`).
- **Grocery List Management**: Adds items and retrieves saved grocery lists in real-time.

### 3. 🖼️ Google GenAI Image Generation & Cloud Storage
- **Dish Photography**: Generates high-quality culinary dish photographs using `gemini-3.1-flash-lite-image` in the `global` region.
- **Public Cloud Storage (GCS)**: Uploads generated images directly to a public Cloud Storage bucket (`recipe-assistant-assets-qwiklabs-gcp-03-2b2a39607757`) and saves in-memory artifacts for the Agent Playground.

### 4. 📹 Google GenAI Omni Video Generation
- **Cooking Process Videos**: Generates short culinary videos using Google's Omni model (`gemini-omni-flash-preview`) in the `global` region.
- **In-Memory Upload**: Processes raw video bytes directly into Cloud Storage and Playground artifacts without local disk writes.

### 5. 📍 Google Maps Places & Geocoding APIs
- **Location Lookup**: Geocodes address strings into geographical coordinates.
- **Nearby Supermarkets**: Finds real-world supermarkets and grocery stores near specified locations with user ratings and full addresses.

### 6. 🌐 External Recipe Database (TheMealDB REST API)
- **Global Recipe Search**: Fallback integration with TheMealDB REST API to search thousands of international recipes by dish or main ingredient.

### 7. 🎨 A2UI v0.8 Integration
- **Structured UI Components**: Emits structured UI trees (Cards, Columns, Rows, Text, Images) sanitized for rendering directly in ADK Dev UI / A2UI clients.

### 8. 💻 Sandboxed Code Execution
- **Python Sandbox**: Uses `AgentEngineSandboxCodeExecutor` to perform calculation tasks and data formatting safely.

### 9. 🎨 Custom FastAPI Proxy & Modern Chat UI
- **Responsive UI**: Custom FastAPI backend proxying A2A requests to Agent Engine.
- **Rich Interface**: Plain HTML/JS frontend featuring dynamic user and agent avatar chat bubbles, quick prompt row, glassmorphic header status pill, and pulsing 3-dot typing indicator.

---

## 📁 Repository Structure

```
recipe-assistant/
├── app/                        # Agent implementation code
│   ├── agent.py                # Main ADK Agent, tools, and callbacks
│   ├── a2ui_utils.py           # A2UI v0.8 schema response formatter
│   └── fast_api_app.py         # Agent Engine entrypoint
├── frontend/                   # Plain FastAPI proxy server & Chat UI
│   ├── main.py                 # FastAPI proxy server targeting A2A Agent Engine
│   └── static/index.html       # Rebranded responsive HTML/CSS/JS frontend
├── demo.gif                    # Looping demo recording of frontend interactions
├── pyproject.toml              # Python dependencies (uv package manager)
└── agents-cli-manifest.yaml    # Deployment manifest for agents-cli
```

---

## 🛠️ Prerequisites & Setup

Ensure you have the following installed on your machine:
- **Python**: Version 3.11+
- **uv**: Package manager (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- **agents-cli**: Agents CLI (`uv tool install google-agents-cli`)
- **Google Cloud SDK**: Logged in with access to your GCP project (`gcloud auth application-default login`)

---

## 🚀 Running Locally

### 1. Install Dependencies
```bash
uv sync
```

### 2. Configure Environment Variables
Create a `.env` file in the root directory:
```env
GOOGLE_GENAI_USE_VERTEXAI=true
GOOGLE_CLOUD_LOCATION=global
GOOGLE_MAPS_API_KEY=YOUR_GOOGLE_MAPS_API_KEY
```

### 3. Start the Agent Playground
Run the local ADK agent playground:
```bash
agents-cli playground
```

### 4. Start the Custom Frontend (Optional)
Navigate to the `frontend` folder and run the local FastAPI proxy server:
```bash
cd frontend
uv run uvicorn main:app --port 8080
```
Then open your browser to your local host address on port 8080.

---

## ☁️ Deployment

### Deploying the Agent to Agent Platform (Vertex AI Agent Engine)
```bash
gcloud config set project YOUR_PROJECT_ID
agents-cli deploy --project YOUR_PROJECT_ID
```

### Deploying the Frontend to Cloud Run
```bash
gcloud run deploy recipe-assistant-frontend \
  --source ./frontend \
  --region us-east1 \
  --allow-unauthenticated \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME="YOUR_REASONING_ENGINE_RESOURCE_NAME",AGENT_DIRECTORY="app"
```
