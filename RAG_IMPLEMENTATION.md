# RAG Implementation

This document outlines the Retrieval-Augmented Generation (RAG) implementation within the `LLM_CI` application. The RAG system has been updated to use ChromaDB as a vector store, following best practices for production-ready RAG systems.

## Overview

The RAG system enhances the LLM's responses by providing relevant context from a local knowledge base. This allows the model to answer questions and generate content based on information that it was not originally trained on. The new implementation uses ChromaDB, a modern, open-source vector database, to store and retrieve document embeddings efficiently.

## How it Works

1.  **Knowledge Base (ChromaDB):** The knowledge base is now managed by ChromaDB. Instead of a text file, documents are chunked, embedded, and stored in a ChromaDB collection. The collection name is configurable via the `CHROMA_COLLECTION` environment variable in your `.env` file (defaults to `rag_collection`).

2.  **Ingestion:** Content is added to the knowledge base using the `upload_file_to_vault` tool. This tool is available to the LLM and can be invoked by asking the agent to upload a file. For example:

    ```
    "Please upload the file 'docs/my_document.pdf' to the vault."
    ```

    The tool supports various file types (PDF, TXT, MD, etc.), splits the content into sentence-aware chunks, and adds them to the configured ChromaDB collection. Each chunk is stored with metadata, including the source file path.

3.  **Embeddings:** ChromaDB automatically handles the embedding process. When a document is added to a collection, ChromaDB's configured embedding function is used to generate the vector embedding for the document.

4.  **Retrieval:** When you send a prompt to the agent, the `get_relevant_context` function (in `LLM_CI/Utils.py`) is executed. It:
    *   Takes your query.
    *   Queries the ChromaDB collection to find the most relevant document chunks based on semantic similarity.

5.  **Augmentation:** The top-k relevant chunks retrieved from the ChromaDB collection are then injected into the system prompt that is sent to the LLM. This provides the model with the necessary context to answer your query accurately.

## How to Use the RAG System

Using the RAG system is straightforward:

1.  **Set up your environment:** Ensure your `.env` file is configured with the desired `LLM_PROVIDER` (e.g., `ollama` or `openai`) and any necessary API keys or model names.
2.  **Install dependencies:** Make sure you have installed the dependencies from `requirements/base.txt`, including `chromadb`.
3.  **Run the application:**
    ```bash
    python LLM_CI/cli.py
    ```
4.  **Add documents to the vault:** Use natural language to instruct the agent to upload files.
    > **You:** "Upload `LLM_CI/docs/sample-local-pdf.pdf` to the vault."
5.  **Ask questions:** Once a document is in the vault, you can ask questions related to its content. The RAG system will work automatically in the background.
    > **You:** "What is this document about?"

## Best Practices for RAG in CI/CD

To ensure the RAG implementation is robust, testable, and maintainable, especially in a CI/CD environment, the following best practices have been adopted:

*   **Vector Database:** Using ChromaDB as a dedicated vector database is a significant improvement over a text file. It provides efficient storage, indexing, and querying of vector embeddings, which is crucial for a scalable RAG system.
*   **Configuration:** The ChromaDB collection name is configurable via an environment variable (`CHROMA_COLLECTION`). This allows for different collections to be used in different environments (e.g., a dedicated collection for testing in a CI/CD pipeline).
*   **Modularity:** The RAG logic is encapsulated within `LLM_CI/Utils.py` (retrieval) and `LLM_CI/Tools.py` (ingestion). This modular design makes the system easier to understand, maintain, and extend.
*   **Testing:** The RAG system can be tested end-to-end. The `tests/test_rag.py` file provides an example of how to test the new ChromaDB-based implementation. This is a critical component of a CI/CD pipeline, as it ensures that changes to the RAG system do not break existing functionality.

## Extending the RAG Implementation

If you wish to modify or extend the RAG functionality, here are the key files to focus on:

*   `LLM_CI/Utils.py`: This file contains the core logic for the RAG system's retrieval.
    *   `get_relevant_context`: Modify this function to change the retrieval strategy (e.g., different query parameters, filtering).
*   `LLM_CI/Tools.py`: This file defines the ingestion pipeline.
    *   `append_to_vault`: Modify this function to change how files are processed, chunked, or stored in the ChromaDB collection.

By modifying these files, you can adapt the RAG system to fit different needs, such as connecting to a different vector database or changing the chunking and embedding logic.
