import importlib.util
import pathlib

import chromadb

# Load modules from the LLM_CI directory (not installed as a package)
root = pathlib.Path(__file__).resolve().parents[1]
tools_path = str(root / 'LLM_CI' / 'Tools.py')
utils_path = str(root / 'LLM_CI' / 'Utils.py')

spec_t = importlib.util.spec_from_file_location('LLM_CI.Tools', tools_path)
tools = importlib.util.module_from_spec(spec_t)
spec_t.loader.exec_module(tools)  # type: ignore

spec_u = importlib.util.spec_from_file_location('LLM_CI.Utils', utils_path)
utils = importlib.util.module_from_spec(spec_u)
spec_u.loader.exec_module(utils)  # type: ignore


def test_rag_end_to_end(tmp_path):
    """Summary: ensure text can be uploaded to the vault and retrieved.

    This test performs an end-to-end check of the RAG system by:
    1. Creating a sample text file with unique content.
    2. Calling `upload_file_to_vault` to add it to the vault.
    3. Calling `get_relevant_context` to retrieve the content.
    4. Asserting that the retrieved context contains the unique content.
    """
    # 1. Create a sample text file with unique content
    unique_content = 'The quick brown fox jumps over the lazy dog.'
    f = tmp_path / 'sample.txt'
    f.write_text(unique_content, encoding='utf-8')

    # 2. Add the file to the vault
    collection_name = 'test_rag_collection'
    uploader = tools.upload_file_to_vault
    if callable(uploader):
        res = uploader(str(f), collection_name=collection_name)
    else:
        # try common wrappers
        if hasattr(uploader, 'func'):
            res = uploader.func(str(f), collection_name=collection_name)
        elif hasattr(uploader, 'run'):
            res = uploader.run(str(f), collection_name=collection_name)
        else:
            # fallback to calling append_to_vault directly
            res = tools.append_to_vault(str(f), collection_name=collection_name)

    assert 'Appended' in res

    # 3. Retrieve the content
    retrieved_context = utils.get_relevant_context(
        'quick brown fox',
        collection_name=collection_name,
        top_k=1
    )

    # 4. Assert that the retrieved context is correct
    assert isinstance(retrieved_context, list)
    assert len(retrieved_context) == 1
    assert unique_content in retrieved_context[0]

    # 5. Clean up the collection
    try:
        client = chromadb.Client()
        client.delete_collection(name=collection_name)
    except Exception as e:
        print(f"Error cleaning up collection: {e}")
