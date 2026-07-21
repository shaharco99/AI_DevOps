"""Unit tests for document text extraction.

Every parser is an attack surface, so the tests care as much about what is
refused as about what is read.
"""

import asyncio
import json

import pytest

from ai_devops_assistant.rag.loaders import (
    MAX_UPLOAD_BYTES,
    SUPPORTED_EXTENSIONS,
    DocumentTooLargeError,
    UnsupportedDocumentError,
    extract_text,
    extract_text_async,
    supported_extensions,
)


class TestPlainText:
    @pytest.mark.parametrize("name", ["a.txt", "a.md", "a.markdown", "a.rst", "a.log", "a.yaml"])
    def test_text_formats_are_read_directly(self, name):
        assert extract_text(name, b"hello world") == "hello world"

    def test_undecodable_bytes_are_replaced_not_fatal(self):
        """One bad byte must not cost the whole document."""
        text = extract_text("a.txt", b"ok \xff\xfe bytes")
        assert "ok" in text and "bytes" in text

    def test_the_extension_check_is_case_insensitive(self):
        assert extract_text("README.MD", b"content") == "content"


class TestStructured:
    def test_json_is_reindented_for_chunking(self):
        payload = json.dumps({"b": 2, "a": 1})
        text = extract_text("d.json", payload.encode())
        assert "\n" in text, "indented output gives the chunker line structure"
        assert json.loads(text) == {"b": 2, "a": 1}

    def test_invalid_json_degrades_to_plain_text(self):
        assert "not json" in extract_text("d.json", b"not json at all")

    def test_csv_rows_become_lines(self):
        text = extract_text("d.csv", b"name,role\nalice,sre\nbob,dev\n")
        assert "alice, sre" in text
        assert "bob, dev" in text

    def test_tsv_uses_tabs(self):
        text = extract_text("d.tsv", b"name\trole\nalice\tsre\n")
        assert "alice, sre" in text

    def test_empty_csv_is_not_an_error(self):
        assert extract_text("d.csv", b"") == ""


class TestRefusals:
    @pytest.mark.parametrize("name", ["evil.exe", "script.sh", "lib.so", "archive.zip", "noext"])
    def test_unsupported_extensions_are_refused_by_name(self, name):
        """Refused before any parser sees the bytes."""
        with pytest.raises(UnsupportedDocumentError) as exc:
            extract_text(name, b"anything")
        assert "Unsupported file type" in str(exc.value)

    def test_an_oversized_upload_is_refused(self):
        with pytest.raises(DocumentTooLargeError):
            extract_text("big.txt", b"x" * (MAX_UPLOAD_BYTES + 1))

    def test_a_file_at_the_limit_is_accepted(self):
        assert extract_text("ok.txt", b"x" * MAX_UPLOAD_BYTES)

    def test_the_size_check_runs_before_the_extension_check(self):
        """Cheapest rejection first: an oversized file is never parsed."""
        with pytest.raises(DocumentTooLargeError):
            extract_text("big.exe", b"x" * (MAX_UPLOAD_BYTES + 1))

    def test_a_corrupt_binary_is_reported_not_raised_raw(self):
        """A malformed PDF must produce our error, not a parser traceback."""
        with pytest.raises(UnsupportedDocumentError):
            extract_text("broken.pdf", b"this is definitely not a pdf")

    def test_a_double_extension_uses_the_last_one(self):
        with pytest.raises(UnsupportedDocumentError):
            extract_text("payload.txt.exe", b"content")


class TestSupportedExtensions:
    def test_the_advertised_list_is_sorted_and_complete(self):
        assert supported_extensions() == sorted(SUPPORTED_EXTENSIONS)

    def test_no_executable_formats_are_advertised(self):
        for dangerous in (".exe", ".sh", ".bat", ".so", ".dll", ".py"):
            assert dangerous not in SUPPORTED_EXTENSIONS


class TestAsyncExtraction:
    def test_it_returns_the_same_text(self):
        assert asyncio.run(extract_text_async("a.txt", b"hello")) == "hello"

    def test_errors_propagate_through_the_thread(self):
        with pytest.raises(UnsupportedDocumentError):
            asyncio.run(extract_text_async("a.exe", b"x"))

    def test_size_errors_propagate_too(self):
        with pytest.raises(DocumentTooLargeError):
            asyncio.run(extract_text_async("big.txt", b"x" * (MAX_UPLOAD_BYTES + 1)))

    def test_a_slow_parser_is_abandoned_rather_than_hanging_a_worker(self, monkeypatch):
        import ai_devops_assistant.rag.loaders as loaders

        def _slow(filename, data):
            import time

            time.sleep(2)
            return "never returned"

        monkeypatch.setattr(loaders, "extract_text", _slow)
        monkeypatch.setattr(loaders, "PARSE_TIMEOUT_SECONDS", 0.1)

        with pytest.raises(UnsupportedDocumentError) as exc:
            asyncio.run(loaders.extract_text_async("slow.pdf", b"x"))
        assert "longer than" in str(exc.value)
