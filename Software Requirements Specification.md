# 🧩 Software Requirements Specification (SRS): **“LLM-CI”**

## **1. Introduction**
**Purpose:**
A lightweight Python command-line tool that uses Large Language Models (LLMs) to review or improve code directly inside CI/CD pipelines.

**Scope:**
Runs in any CI/CD environment (e.g., Jenkins, GitLab CI, GitHub Actions).
It’s a console-based tool — no graphical interface required.
The goal is to help beginner DevOps engineers learn coding, automation, and the Software Development Life Cycle (SDLC).

---

## **2. Overview**
**Target User:**
DevOps engineers with basic Python skills who want to understand coding structure, configuration, and pipeline integration.

**Assumptions:**
- Python **3.8+** is installed.
- The user has API access to an LLM provider (e.g., OpenAI).
- Configuration is stored in a YAML file (`llm-ci.config.yaml`).

---

## **3. Core Features**

### 3.1 Command-Line Execution
Run the tool directly:
```bash
python llm-ci/cli.py --prompt "Review this Python script"
````

Or from a file:

```bash
python llm-ci/cli.py --prompt-file ./prompt.txt
```

### 3.2 Configurable LLM Profiles

* Defined in `llm-ci.config.yaml`.
* Each profile defines `provider`, `model`, and `name`.
* Select via:

  ```bash
  --profile openai-gpt4
  ```
* Reads the API key from an environment variable named after the profile.

### 3.3 Prompt Variables

Use environment variables dynamically:

```text
Review file {{FILENAME}} for errors.
```

`{{FILENAME}}` is replaced automatically when running in CI.

### 3.4 Local Knowledge Base (Optional)

For context-aware answers:

```bash
python llm-ci/cli.py --ingest ./docs/
```

Stores local text files for smarter prompt responses.

### 3.5 Error Handling & Logging

* Use `try/except` for predictable errors.
* Log to **stderr** (not mixed with stdout).
* Allow configurable log levels with `--log-level` (default: `INFO`).

---

## **4. Development Steps**

### 4.1 Setup

```bash
mkdir llm-ci && cd llm-ci
python -m venv venv
source venv/bin/activate
pip install -r requirements/dev.txt
```

### 4.2 Dependencies

```
pyyaml
openai
anthropic
ollama
chromadb
sentence-transformers
```

### 4.3 Folder Structure

```
llm-ci/
  ├── llm_ci/
  │   ├── cli.py
  │   ├── config.py
  │   ├── llm_manager.py
  │   ├── rag_engine.py
  ├── llm-ci.config.yaml
  ├── requirements/
  └── README.md
```

---

## **5. Coding Best Practices**

| Principle           | Description                                           |
| ------------------- | ----------------------------------------------------- |
| **Follow PEP8**     | Use consistent naming, indentation, and formatting.   |
| **Use Functions**   | Avoid long scripts — break logic into reusable parts. |
| **Add Comments**    | Explain *why*, not just *what*.                       |
| **Handle Errors**   | Wrap risky operations with `try/except`.              |
| **No Hardcoding**   | Use environment variables for secrets.                |
| **Separate Output** | Logs → stderr, Responses → stdout.                    |
| **Modular Code**    | Split logic into separate files (CLI, config, etc.).  |

---

## **6. Example: Jenkins Pipeline Integration**

```groovy
pipeline {
    agent any
    environment {
        OPENAI_GPT4_API_KEY = credentials('OPENAI_API_KEY')
        FILENAME = 'app.py'
    }

    stages {
        stage('AI Code Review') {
            steps {
                script {
                    sh '''
                        python llm-ci/llm_ci/cli.py \
                          --profile "openai-gpt4" \
                          --prompt "Review the file {{FILENAME}} for code quality and security issues."
                    '''
                }
            }
        }
    }
}
```

---

## **7. Future Learning & Extensions**

* Add **quality gates**: fail the build if serious issues are found.
* Add **unit tests** (e.g., `pytest`) to validate CLI and logic.
* Add **CI/CD caching** for local model use.
* Learn about **DevSecOps integrations** (security linting via AI).
* Explore **RAG pipelines** for smarter contextual answers.

---

## **8. Summary**

This project helps new DevOps engineers learn how to:
✅ Build a simple Python CLI tool
✅ Follow SDLC stages (Requirements → Design → Implementation → Testing)
✅ Apply coding best practices
✅ Integrate AI logic into CI/CD pipelines

---

**Document Version:** 1.0
**Author:** Training Material for DevOps Beginners
**License:** MIT
