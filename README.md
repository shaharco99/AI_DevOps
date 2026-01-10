
# LLM CI Tools

The `LLM_CI/` directory contains AI-powered DevOps assistant tools that can analyze files, provide technical guidance, and query databases.

## 🆕 Database Query Feature

**NEW!** Your AI assistant can now answer questions about your database directly!

- **Natural language queries**: Ask questions like "Show me customers from the USA"
- **Automatic SQL generation**: The AI generates appropriate SQL queries
- **Safe execution**: User must approve each query before it runs
- **Multiple databases**: SQLite, PostgreSQL, and MySQL supported
- **PDF export**: Generate professional reports with results

**Quick start**:
```bash
python quick_start_database.py
python LLM_CI/Chat.py
# Then ask: "Show me all customers from the USA"
```

📖 **Documentation**: See [GETTING_STARTED_DATABASE.md](GETTING_STARTED_DATABASE.md) for complete setup and usage guide.

### Chat.py - Interactive Chat Interface

An interactive command-line chat interface for DevOps assistance with file analysis capabilities.

#### Features
- **Interactive conversation**: Continuous chat loop until user exits
- **Multi-LLM support**: Works with OLLAMA, OPENAI, GOOGLE, and ANTHROPIC providers
- **Automatic tool execution**: Automatically uses `doc_loader` tool when files are referenced
- **Tool call handling**: Supports multi-step tool execution chains
- **Error handling**: Graceful error handling for LLM failures and user interruptions
- **Output separation**: Logs to stderr, responses to stdout

#### Usage
```bash
# From project root
cd LLM_CI
python Chat.py

# Or from project root
python LLM_CI/Chat.py
```

#### How it works
1. Initializes LLM provider from environment variables (`.env` file)
2. Starts interactive chat loop
3. For each user question:
   - Sends question to LLM with full chat history
   - If LLM requests tool usage (e.g., `doc_loader`), automatically executes it
   - Loops until final response (no more tool calls)
   - Displays AI response to user
4. Continues until user types 'exit' or 'quit', or presses Ctrl+C

#### Example Session
```
You: Load test_document.pdf and summarize it
tools in use: doc_loader : parameters : {"file_name": "test_document.pdf"}
Output:
[PDF content...]

AI: The document contains...
```

#### Configuration
- Set `LLM_PROVIDER` in `.env` file (OLLAMA, OPENAI, GOOGLE, ANTHROPIC)
- Provider-specific settings (e.g., `OLLAMA_MODEL`, `OPENAI_API_KEY`) in `.env`
- See `LLM_CI/.env.template` for all available options

---

### cli.py - Command-Line Interface

A non-interactive CLI tool for executing single prompts via command line, suitable for scripting and automation.

#### Features
- **Single execution**: Processes one prompt and exits
- **Multiple input methods**: Direct prompt text or prompt file
- **Verbose mode**: Optional tool execution logging
- **Script-friendly**: Output to stdout for piping/redirection
- **Error handling**: Proper exit codes and error messages

#### Usage

**Direct prompt:**
```bash
python LLM_CI/cli.py --prompt "Review this Python script"
```

**From file:**
```bash
python LLM_CI/cli.py --prompt-file ./prompt.txt
```

**With verbose output (shows tool execution):**
```bash
python LLM_CI/cli.py --prompt "Load test_document.pdf" --verbose
```

**Pipe output to file:**
```bash
python LLM_CI/cli.py --prompt "Analyze config.json" > output.txt
```

#### Command-Line Arguments

| Argument | Short | Required | Description |
|----------|-------|----------|-------------|
| `--prompt` | - | Yes* | Direct prompt text to execute |
| `--prompt-file` | - | Yes* | Path to file containing the prompt |
| `--verbose` | `-v` | No | Show tool execution details (to stderr) |

*Either `--prompt` or `--prompt-file` must be provided (mutually exclusive)

#### Examples

**Code review:**
```bash
python LLM_CI/cli.py --prompt "Review the code in Chat.py for best practices"
```

**File analysis:**
```bash
python LLM_CI/cli.py --prompt "Load requirements/dev.txt and suggest improvements"
```

**Complex prompt from file:**
```bash
echo "Load test_document.pdf and extract all key points" > prompt.txt
python LLM_CI/cli.py --prompt-file prompt.txt
```

**With debugging:**
```bash
python LLM_CI/cli.py --prompt "Load config.json" --verbose
# Shows:
# Using LLM provider: OLLAMA
# tools in use: doc_loader : parameters : {"file_name": "config.json"}
# Output:
# [file content...]
```

#### Output Behavior
- **Main response**: Printed to stdout (can be piped/redirected)
- **Errors and verbose logs**: Printed to stderr (won't interfere with output)
- **Exit codes**:
  - `0` on success
  - `1` on error (file not found, LLM error, etc.)

#### Integration Examples

**Shell script:**
```bash
#!/bin/bash
RESPONSE=$(python LLM_CI/cli.py --prompt "Check if requirements/dev.txt has security issues")
echo "Analysis: $RESPONSE"
```

**CI/CD pipeline:**
```yaml
- name: Code Review
  run: |
    python LLM_CI/cli.py --prompt-file review_prompt.txt > review_output.txt
```

---

### Shared Capabilities

Both `Chat.py` and `cli.py` share the following capabilities:

#### Document Loading Tool (`doc_loader`)
Automatically loads and analyzes various file types:

**Supported formats:**
- **PDF** (`.pdf`) - Requires `pypdf`
- **Text files** (`.txt`, `.md`) - Built-in
- **CSV** (`.csv`) - Built-in
- **JSON** (`.json`) - Built-in
- **HTML** (`.html`, `.htm`) - Built-in
- **Word Documents** (`.docx`) - Requires `python-docx`
- **PowerPoint** (`.pptx`) - Requires `unstructured`
- **Excel** (`.xlsx`, `.xls`) - Requires `unstructured`

**Tool features:**
- Full content loading
- Text search within documents
- Line number retrieval
- Automatic file type detection

#### LLM Provider Support

Both tools support multiple LLM providers configured via environment variables:

1. **OLLAMA** (default)
   - Local model execution
   - Auto-pulls missing models
   - No API key required

---

## RAG (Retrieval-Augmented Generation)

This repository includes a simple RAG pipeline that lets the assistant use a local "vault" of document chunks to provide context to the LLM. Vector-based retrieval and embeddings are used by default when possible (a deterministic fallback is available for offline testing).

- **Vault file**: The default vault file is `LLM_CI/vault.txt` (configurable via the `VAULT_FILE` environment variable). Each line in the vault is treated as a chunk/document fragment.
- **Upload / indexing**: The Chat GUI `Upload` button and the `load_folder_to_vault()` tool in `LLM_CI/Tools.py` append text chunks to the vault.
- **Embeddings & vector search**: Use `LLM_CI/Utils.compute_and_cache_vault_embeddings()` to compute embeddings for every vault line and cache them to `<vault>.emb.npz`. When available, vector cosine similarity is used to retrieve the top-k relevant chunks. If no external embedding provider is available, a deterministic hash-based fallback embedding is used so retrieval still works offline.

Quick steps to use RAG with the GUI (vector retrieval is enabled by default):

1. (Optional) Set a directory of documents to preload at startup:

```bash
export RAG_DOCS_DIR=/path/to/your/docs
```

2. Start the GUI from the repo root:

```bash
python LLM_CI/ChatGUI.py
```

During startup the GUI will call `load_folder_to_vault()` (if `RAG_DOCS_DIR` is set) and then `compute_and_cache_vault_embeddings()` so vector retrieval is available by default.

3. Upload single files using the GUI `📎` button. After uploading the assistant will prefill the input with an example prompt like `Analyze the file <filename>...`.

4. Ask a question in the GUI. The assistant will:
- rewrite the query (best-effort) via `LLM_CI/Utils.rewrite_query()`
- retrieve the top-k relevant vault chunks via `LLM_CI/Utils.get_relevant_context()`
- append the retrieved context to the prompt as `Relevant Context:` before calling the LLM

5. (Optional) Precompute embeddings manually for faster startup or after large vault updates:

```bash
python -c "from LLM_CI.Utils import compute_and_cache_vault_embeddings; compute_and_cache_vault_embeddings()"
```

Environment variables that affect RAG behavior:
- `VAULT_FILE` — path to the vault file (default `LLM_CI/vault.txt`)
- `RAG_DOCS_DIR` or `VAULT_DIR` — folder to preload into the vault at GUI/CLI startup
- `OLLAMA_EMBED_MODEL` / `OPENAI_EMBED_MODEL` — preferred embedding model names when those providers are available

Notes on offline behavior:
- If Ollama/OpenAI embeddings are not available the code falls back to a deterministic SHA256-based vector embedding so retrieval still works locally.
- If no LLM provider is configured the GUI/CLI will still operate and return deterministic fallback replies (e.g. `Echo: ...`) so you can test the RAG pipeline without external services.

Where to look in code:
- `LLM_CI/Tools.py` — `append_to_vault()`, `upload_file_to_vault()`, `load_folder_to_vault()`, `get_vault_count()`
- `LLM_CI/Utils.py` — `get_relevant_context()`, `compute_and_cache_vault_embeddings()`, `rewrite_query()`, `ollama_chat()`
- `LLM_CI/ChatGUI.py` — GUI wiring; upload button and startup preload


2. **OPENAI**
   - Requires `OPENAI_API_KEY`
   - Configurable model via `OPENAI_MODEL`

3. **GOOGLE**
   - Requires `GOOGLE_API_KEY`
   - Configurable model via `GOOGLE_MODEL`

4. **ANTHROPIC**
   - Requires `ANTHROPIC_API_KEY`
   - Configurable model via `ANTHROPIC_MODEL`

#### Configuration

Create a `.env` file in `LLM_CI/` directory (see `LLM_CI/.env.template`):

```bash
LLM_PROVIDER=OLLAMA
OLLAMA_MODEL=llama3.1:latest
# OPENAI_API_KEY=your_key_here
# OPENAI_MODEL=gpt-3.5-turbo
```

#### Error Handling

Both tools include comprehensive error handling:
- LLM initialization failures
- Network/API errors
- File not found errors
- Invalid user input
- Keyboard interrupts (Ctrl+C)

#### Output Stream Separation

Following best practices:
- **User-facing content** (AI responses) → `stdout`
- **Logging/debugging** (tool usage, errors) → `stderr`

This allows proper output redirection:
```bash
# Only capture the AI response
python LLM_CI/cli.py --prompt "..." > response.txt

# Capture everything
python LLM_CI/cli.py --prompt "..." > response.txt 2> debug.log
```


----
# MCP (DevOps Tools)

This repository runs a small MCP (Multi-Chat Plugin) server exposing DevOps tools (minikube, kubectl, docker, terraform, git, playwright).

## Goals
- Provide local devops tooling over MCP protocol
- Allow safe shell operations for admins (whitelisted)
- Work well on Windows with Docker Desktop + Minikube (docker driver)

## Prerequisites
- Windows 10/11
- Docker Desktop (running)
- Minikube (installed) - optional: `choco install minikube` or download from https://minikube.sigs.k8s.io/
- Node + npm (for npx servers used by MCP clients)
- Python 3.11, virtualenv

## Quickstart (local)
```powershell
# create venv and install
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements/dev.txt

# run server
python server.py
```

## Useful commands (PowerShell)
```powershell
# Docker
docker version
docker ps -a

# Minikube
minikube start --driver=docker
minikube status
minikube kubectl -- get namespaces

# MCP tools (via HTTP client or mcp-cli)
# - start minikube: call minikube_start()
# - stop minikube: call minikube_stop()
# - check namespaces: call kubectl(args="get namespaces")
# - run whitelisted shell: call run_shell(cmd="docker ps")
```

## Security
- `run_shell` is intentionally whitelisted and rejects pipes/redirections. Do not expand without considering risk.
