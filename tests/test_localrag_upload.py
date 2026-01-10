import importlib.util
import json
import pathlib

# Load modules from the LLM_CI directory (not installed as a package)
root = pathlib.Path(__file__).resolve().parents[1]
tools_path = str(root / 'LLM_CI' / 'Tools.py')
utils_path = str(root / 'LLM_CI' / 'Utils.py')

"""Tests for merged RAG/upload helpers.

Each test includes a short summary in its docstring explaining what it checks.
"""

spec_t = importlib.util.spec_from_file_location('LLM_CI.Tools', tools_path)
tools = importlib.util.module_from_spec(spec_t)
spec_t.loader.exec_module(tools)  # type: ignore

spec_u = importlib.util.spec_from_file_location('LLM_CI.Utils', utils_path)
utils = importlib.util.module_from_spec(spec_u)
spec_u.loader.exec_module(utils)  # type: ignore


def test_append_to_vault_text(tmp_path):
    """Summary: ensure `append_to_vault` chunks long text and writes to vault.

    This test creates a text file with several sentences to force chunking,
    calls `append_to_vault`, and asserts the vault file contains expected content.
    """
    # create a sample text file with multiple sentences to force chunking
    sample = (
        'This is sentence one. '
        'Here is sentence two about apples. '
        'Now sentence three mentions oranges and apples. '
        'Fourth sentence is short. '
        'Fifth sentence mentions bananas and apples again.'
    )
    f = tmp_path / 'sample.txt'
    f.write_text(sample, encoding='utf-8')

    vault = tmp_path / 'vault.txt'
    res = tools.append_to_vault(str(f), vault_path=str(vault))
    assert 'Appended' in res
    # vault should exist and contain at least one line
    assert vault.exists()
    lines = vault.read_text(encoding='utf-8').splitlines()
    assert len(lines) >= 1
    # ensure that some chunk contains the word 'apples' (normalized)
    assert any('apples' in line.lower() or 'apple' in line.lower() for line in lines)


# def test_get_relevant_context_simple():
#     """Summary: verify fallback relevance ranking by word-overlap.

#     The function should return the top-k documents matching query words when
#     embeddings are not provided.
#     """

#     vault_content = [
#         'Apples and oranges are tasty.',
#         'Bananas are yellow.',
#         'I like apple pie and apple tart.',
#     ]
#     # query that should match apple-related documents first
#     res = utils.get_relevant_context('apple pie', vault_embeddings=None, vault_content=vault_content, top_k=2)
#     assert isinstance(res, list)
#     assert len(res) == 2
#     # first result should mention apples or apple
#     assert any('apple' in s.lower() or 'apples' in s.lower() for s in res[0].split())


def test_rewrite_query_fallback():
    """Summary: rewrite_query returns original query when no LLM client is given.

    Ensures the fallback JSON structure is preserved.
    """

    conv = [{'role': 'user', 'content': 'previous'}]
    q = {'Query': 'Find all users'}
    out = utils.rewrite_query(json.dumps(q), conv, client=None)
    parsed = json.loads(out)
    assert 'Rewritten Query' in parsed
    assert parsed['Rewritten Query'] == 'Find all users'


def test_ollama_chat_fallback_echo():
    """Summary: ollama_chat returns an echo reply and appends assistant message when offline.

    Uses client=None fallback to validate that context injection and history
    mutation behave as expected.
    """

    conv = []
    reply = utils.ollama_chat('Hello there', 'system message', None, [], 'llama3', conv, client=None)
    assert reply.startswith('Echo:')
    # conversation history should have assistant appended
    assert any(m.get('role') == 'assistant' for m in conv)


def test_load_folder_to_vault_empty(tmp_path):
    """Summary: loading an empty folder should not error and should return informative message."""
    folder = tmp_path / 'empty_folder'
    folder.mkdir()
    res = tools.load_folder_to_vault(str(folder), vault_path=str(tmp_path / 'vault.txt'))
    # Should return a message indicating no files to load (but not raise)
    assert isinstance(res, str)


def test_upload_file_to_vault_wrapper(tmp_path):
    """Summary: upload_file_to_vault tool wrapper appends a supported file to the vault."""
    sample = 'Hello world. This file mentions apples.'
    f = tmp_path / 'doc.txt'
    f.write_text(sample, encoding='utf-8')
    vault = tmp_path / 'vault2.txt'
    # upload_file_to_vault may be a langchain StructuredTool (not directly callable).
    uploader = tools.upload_file_to_vault
    if callable(uploader):
        res = uploader(str(f), vault_path=str(vault))
    else:
        # try common wrappers
        if hasattr(uploader, 'func'):
            res = uploader.func(str(f), vault_path=str(vault))
        elif hasattr(uploader, 'run'):
            res = uploader.run(str(f), vault_path=str(vault))
        else:
            # fallback to calling append_to_vault directly
            res = tools.append_to_vault(str(f), vault_path=str(vault))

    assert isinstance(res, str) and ('Appended' in res or 'appended' in res)
    assert vault.exists()
