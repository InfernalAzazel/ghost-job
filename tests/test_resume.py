"""Tests for resume PDF handling."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from pypdf import PdfWriter

from job.utils.resume import ResumePdf


def _blank_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extract_text_blank_pdf():
    assert ResumePdf.extract_text(_blank_pdf()) == ""


def test_extract_text_rejects_non_pdf():
    with pytest.raises(ValueError, match="简历文件无法识别"):
        ResumePdf.extract_text(b"not a pdf")


def test_save_keeps_file_name_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ResumePdf, "DIR", tmp_path)
    path = ResumePdf.save("../../evil/cv.pdf", b"%PDF")
    assert path == tmp_path / "cv.pdf"
    assert path.read_bytes() == b"%PDF"
