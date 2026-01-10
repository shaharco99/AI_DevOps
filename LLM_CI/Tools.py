from __future__ import annotations

import ast
import logging
import os
import re
from typing import List, Optional

from langchain.tools import tool
from langchain_community.document_loaders import BSHTMLLoader, CSVLoader, JSONLoader, PyPDFLoader, TextLoader
from pathspec import PathSpec

# Module logger
logger = logging.getLogger(__name__)
_lvl = os.getenv('LOG_LEVEL', 'INFO').upper()
try:
    logger.setLevel(getattr(logging, _lvl))
except Exception:
    logger.setLevel(logging.INFO)
# Vault file can be configured via environment variable
VAULT_FILE = os.getenv('VAULT_FILE', 'vault.txt')
try:
    # Some environments include pypdf; loaders are preferred but guard anyway
    import pypdf  # type: ignore
    pypdf_AVAILABLE = True
except Exception:
    pypdf_AVAILABLE = False

# Optional loaders
try:
    from langchain_community.document_loaders import Docx2txtLoader
    DOCX_AVAILABLE = True
except ImportError:
    DOCX_AVAILABLE = False

try:
    from langchain_community.document_loaders import UnstructuredPowerPointLoader
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

try:
    from langchain_community.document_loaders import UnstructuredExcelLoader
    XLSX_AVAILABLE = True
except ImportError:
    XLSX_AVAILABLE = False


def load_gitignore(base_dir: str) -> PathSpec:
    """Load .gitignore from base_dir and return a compiled PathSpec matcher."""
    gitignore_path = os.path.join(base_dir, '.gitignore')

    if not os.path.exists(gitignore_path):
        # no .gitignore -> allow all files
        return PathSpec.from_lines('gitwildmatch', [])

    try:
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return PathSpec.from_lines('gitwildmatch', lines)
    except Exception:
        # If .gitignore unreadable -> do not ignore anything
        return PathSpec.from_lines('gitwildmatch', [])


def recursive_find(filename: str, base_dir: str) -> List[str]:
    """
    Return list of all paths matching the filename recursively from base_dir,
    ignoring files and folders matched by .gitignore.
    """

    spec = load_gitignore(base_dir)
    matches = []
    filename_lower = filename.lower()

    for root, dirs, files in os.walk(base_dir):
        # Skip ignored folders
        dirs[:] = [
            d for d in dirs
            if not spec.match_file(os.path.relpath(os.path.join(root, d), base_dir))
        ]

        for f in files:
            rel = os.path.relpath(os.path.join(root, f), base_dir)

            # Skip ignored files
            if spec.match_file(rel):
                continue

            if f.lower() == filename_lower:
                matches.append(os.path.join(root, f))

    return matches


# ---------------------------------------------------------------------
# Utility: Loader Selector
# ---------------------------------------------------------------------
def get_loader_for_file(file_path):
    """Return appropriate loader instance based on file extension."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.pdf':
        return PyPDFLoader(file_path)

    if ext in ['.txt', '.md']:
        return TextLoader(file_path)

    if ext == '.csv':
        return CSVLoader(file_path)

    if ext == '.json':
        try:
            return JSONLoader(file_path, jq_schema='.')
        except Exception:
            return TextLoader(file_path)

    if ext in ['.html', '.htm']:
        return BSHTMLLoader(file_path)

    if ext == '.docx' and DOCX_AVAILABLE:
        return Docx2txtLoader(file_path)

    if ext == '.pptx' and PPTX_AVAILABLE:
        return UnstructuredPowerPointLoader(file_path)

    if ext in ['.xls', '.xlsx'] and XLSX_AVAILABLE:
        return UnstructuredExcelLoader(file_path)

    return TextLoader(file_path)  # best fallback


# ---------------------------------------------------------------------
# DOC LOADER TOOL (Recursive, Multi-file Search)
# ---------------------------------------------------------------------
@tool
def doc_loader(
    file_name: str,
    search_query: Optional[str] = None,
    re_search: Optional[str] = None,
    line_number: Optional[int] = None,
) -> str:
    """
    Load and read/search files **recursively** from the current directory.

    Supported:
    PDF, TXT, MD, CSV, JSON, HTML, DOCX, PPTX, XLS/XLSX

    Args:
        file_name: filename to search recursively
        search_query: simple string search
        re_search: regex search (advanced)
        line_number: return specific line

    Returns:
        Content or matched results
    """
    base_dir = os.getcwd()

    # Search recursively
    matches = recursive_find(file_name, base_dir)
    if not matches:
        return f"Error: '{file_name}' was not found anywhere under {base_dir}"

    if len(matches) > 1:
        return (
            'Error: Multiple files found. Please specify a more exact filename:\n\n\n'.join(matches)
        )

    file_path = matches[0]

    # Choose loader
    try:
        loader = get_loader_for_file(file_path)
    except Exception as e:
        return f"Error determining loader: {e}"

    # Load content
    try:
        documents = loader.load()
    except Exception as e:
        return f"Error loading file '{file_path}': {e}"

    full_text = '\n'.join(doc.page_content for doc in documents)

    # Line number
    if line_number is not None:
        lines = full_text.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1]
        return f"Error: File has only {len(lines)} lines"

    # String search
    if search_query:
        hits = [
            f"Section {i + 1}:\n{doc.page_content}"
            for i, doc in enumerate(documents)
            if search_query.lower() in doc.page_content.lower()
        ]
        return '\n\n'.join(hits) if hits else 'No matches.'

    # Regex search
    if re_search:
        try:
            pattern = re.compile(re_search, re.IGNORECASE)
        except Exception as e:
            return f"Invalid regex: {e}"

        matches = pattern.findall(full_text)
        if not matches:
            return 'No regex matches.'
        return '\n'.join(map(str, matches))

    return full_text


# ---------------------------------------------------------------------
# CODE REVIEWER (Recursive, with better heuristics)
# ---------------------------------------------------------------------
@tool
def code_reviewer(
    file_name: str,
    line_number: Optional[int] = None,
    scope: Optional[str] = None,  # ignored
) -> str:
    """
    Static Python code reviewer with recursive file search.
    """
    base_dir = os.getcwd()

    matches = recursive_find(file_name, base_dir)
    if not matches:
        return f"Error: '{file_name}' not found under {base_dir}"

    if len(matches) > 1:
        return (
            'Error: Multiple .py files found matching that name:\n\n\n'.join(matches)
        )

    file_path = matches[0]

    if not file_path.endswith('.py'):
        return 'Error: Only Python (.py) files are supported'

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
    except Exception as e:
        return f"Error reading file: {e}"

    if line_number:
        lines = source.splitlines()
        if 1 <= line_number <= len(lines):
            return lines[line_number - 1]
        return 'Error: Line number out of range'

    issues = []

    # TODO/FIXME detection
    for idx, line in enumerate(source.splitlines(), 1):
        if 'TODO' in line or 'FIXME' in line:
            issues.append((idx, 'TODO/FIXME', line.strip()))

    # AST parsing
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return f"SyntaxError: {e.msg} at line {e.lineno}"

    import_names = set()
    used_names = set()

    for node in ast.walk(tree):
        # imports
        if isinstance(node, ast.Import):
            for n in node.names:
                import_names.add(n.asname or n.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for n in node.names:
                import_names.add(n.asname or n.name)

        # usage
        if isinstance(node, ast.Name):
            used_names.add(node.id)

        # bare except
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append((node.lineno, 'Bare except', 'Use specific exception classes'))

        # print()
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'print':
            issues.append((node.lineno, 'print() used', 'Use logging instead of print()'))

        # functions
        if isinstance(node, ast.FunctionDef):
            # mutable defaults
            for d in node.args.defaults:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    issues.append(
                        (node.lineno, 'Mutable default', f"{node.name} uses a mutable default value")
                    )

            # docstring
            if ast.get_docstring(node) is None:
                issues.append((node.lineno, 'Missing docstring', node.name))

            # type hints heuristic
            if not any(param.annotation for param in node.args.args):
                issues.append((node.lineno, 'Missing type hints', node.name))

            # long function
            end = getattr(node, 'end_lineno', None)
            if end and end - node.lineno + 1 > 120:
                issues.append(
                    (node.lineno, 'Long function', f"{node.name} is over 120 lines")
                )

    # unused imports
    unused = sorted(n for n in import_names if n not in used_names)
    for name in unused:
        issues.append((1, 'Unused import', name))

    if not issues:
        return 'No issues found. Code looks clean.'

    # formatted output
    issues = sorted(set(issues), key=lambda x: x[0])
    out = ['Code Review:']
    for ln, kind, msg in issues:
        out.append(f"- Line {ln}: {kind} — {msg}")

    return '\n'.join(out)


# ---------------------------------------------------------------------
# Vault append / upload helpers (replaces separate upload.py)
# ---------------------------------------------------------------------


def _chunk_text(text: str, max_size: int = 1000) -> list[str]:
    """Split long text into sentence-aware chunks up to max_size characters."""
    if not text:
        logger.debug('_chunk_text received empty text')
        return []
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks: list[str] = []
    cur = ''
    for s in sentences:
        if len(cur) + len(s) + 1 < max_size:
            cur = (cur + ' ' + s).strip() if cur else s.strip()
        else:
            if cur:
                chunks.append(cur.strip())
            cur = s.strip()
    if cur:
        chunks.append(cur.strip())
    logger.debug('_chunk_text produced %d chunks', len(chunks))
    return chunks


def append_to_vault(file_path: str, vault_path: str = 'vault.txt') -> str:
    """Load a file and append its textual chunks to `vault_path`.

    This is a non-interactive replacement for the old GUI upload script. It
    supports PDF, TXT, JSON and other formats via the same loader used by
    `doc_loader` when possible.
    """
    vp = vault_path or VAULT_FILE
    logger.info("Appending '%s' to vault '%s'", file_path, vp)
    try:
        loader = get_loader_for_file(file_path)
    except Exception as e:
        logger.exception("Error determining loader for '%s'", file_path)
        return f"Error determining loader for '{file_path}': {e}"

    try:
        documents = loader.load()
    except Exception as e:
        logger.warning("Primary loader failed for '%s': %s", file_path, e)
        # Fallback: try a very simple PDF reader if pypdf available
        if file_path.lower().endswith('.pdf') and pypdf_AVAILABLE:
            try:
                text = ''
                with open(file_path, 'rb') as fh:
                    reader = pypdf.PdfReader(fh)
                    for p in reader.pages:
                        page_txt = p.extract_text() or ''
                        text += page_txt + ' '
                documents = [type('D', (), {'page_content': text})]
                logger.info("PDF fallback succeeded for '%s'", file_path)
            except Exception as e2:
                logger.exception("PDF fallback failed for '%s'", file_path)
                return f"Error loading PDF fallback: {e2}"
        else:
            logger.exception("Loader failed for '%s' and no fallback available", file_path)
            return f"Error loading file '{file_path}': {e}"

    # Consolidate text from documents
    full_text = '\n'.join(getattr(doc, 'page_content', '') for doc in documents)
    # Normalize whitespace
    full_text = re.sub(r'\s+', ' ', full_text).strip()

    chunks = _chunk_text(full_text, max_size=1000)

    try:
        os.makedirs(os.path.dirname(vp) or '.', exist_ok=True)
        with open(vp, 'a', encoding='utf-8') as vault_file:
            for chunk in chunks:
                vault_file.write(chunk.strip() + '\n')
        logger.info("Wrote %d chunks to vault '%s'", len(chunks), vp)
    except Exception as e:
        logger.exception("Error writing to vault '%s'", vp)
        return f"Error writing to vault '{vp}': {e}"

    return f"Appended {len(chunks)} chunk(s) from '{file_path}' to '{vault_path}'"


@tool
def upload_file_to_vault(file_path: str, vault_path: Optional[str] = None) -> str:
    """Tool wrapper for appending a file to the vault. Returns a status message.

    Args:
        file_path: Path to the file to append.
        vault_path: Optional path to vault file (defaults to `vault.txt` in cwd).
    """
    vp = vault_path or VAULT_FILE
    logger.debug('upload_file_to_vault called with %s -> %s', file_path, vp)
    return append_to_vault(file_path, vault_path=vp)


def load_folder_to_vault(folder_path: str, vault_path: str = 'vault.txt', recursive: bool = True) -> str:
    """Load all supported documents from a folder into the vault file.

    - `folder_path`: path to directory containing documents (if empty or missing, no error).
    - `vault_path`: path to vault file to append to.
    - `recursive`: whether to walk directories recursively.

    Returns a short summary string with counts.
    """
    if not folder_path:
        logger.info('load_folder_to_vault: no folder_path provided, skipping')
        return 'No folder provided'

    if not os.path.exists(folder_path) or not os.path.isdir(folder_path):
        logger.warning("load_folder_to_vault: folder '%s' does not exist or is not a directory", folder_path)
        return f"Folder '{folder_path}' not found"

    # resolve vault path (allow env/configured default via VAULT_FILE)
    vp = vault_path or VAULT_FILE
    supported_exts = {'.pdf', '.txt', '.md', '.csv', '.json', '.html', '.htm', '.docx', '.pptx', '.xls', '.xlsx'}
    files_found = []
    for root, dirs, files in os.walk(folder_path):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in supported_exts:
                files_found.append(os.path.join(root, f))
        if not recursive:
            break

    if not files_found:
        logger.info("load_folder_to_vault: no supported files found in '%s'", folder_path)
        return 'No files to load'

    appended = 0
    errors = []
    for fp in files_found:
        try:
            res = append_to_vault(fp, vault_path=vp)
            logger.info('Loaded %s -> %s', fp, res)
            appended += 1
        except Exception as e:
            logger.exception("Error appending '%s' to vault", fp)
            errors.append((fp, str(e)))

    return f"Scanned {len(files_found)} file(s), appended {appended} to '{vp}'" + (f", {len(errors)} errors" if errors else '')


def get_vault_count(vault_path: str | None = None) -> int:
    """Return number of lines (chunks) in the vault file. Returns 0 if missing."""
    vp = vault_path or VAULT_FILE
    try:
        if not os.path.exists(vp):
            return 0
        with open(vp, 'r', encoding='utf-8') as fh:
            return sum(1 for _ in fh)
    except Exception:
        logger.exception('get_vault_count failed for %s', vp)
        return 0
