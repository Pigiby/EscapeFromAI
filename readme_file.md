# How to Run `my_project`

## Prerequisites
- [Ollama](https://ollama.com/) installed
- [ComfyUI](https://github.com/comfyanonymous/ComfyUI) set up
- Python 3.8+ (for project dependencies)

---

## Step 1: Set up Ollama + Gemma 3 4B
1. Download and install Ollama from [ollama.com](https://ollama.com/)
2. Pull the `gemma3:4b` model:
   ```bash
   ollama pull gemma3:4b
   ```
3. Verify the model is available:
   ```bash
   ollama list
   ```

---

## Step 2: Set up ComfyUI
1. Clone/download ComfyUI from its [GitHub repo](https://github.com/comfyanonymous/ComfyUI) and follow its setup instructions to start the server (default: `http://localhost:8000`)
2. Import the `image_generation.json` workflow file into ComfyUI via the UI
3. Download all models required by the workflow (ComfyUI will prompt for missing models, or check the workflow JSON for model paths)

---

## Step 3: Finalize Codebase Setup
1. Navigate to the project root directory (the directory containing `docker-compose.yml`):
   ```bash
   cd /path/to/project-root
   ```
   (Replace `/path/to/project-root` with the actual path to the directory where `docker-compose.yml` is located.)
2. 
   ```bash
   docker compose up --build
   ```
   This will build and start all necessary services for the project.

---

## Verification
- Ensure Ollama is running (`ollama serve` if not auto-started)
- Confirm ComfyUI is accessible at `http://localhost:8000`
- Check that the project successfully connects to both Ollama and ComfyUI instances
