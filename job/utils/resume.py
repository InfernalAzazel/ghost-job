"""简历 PDF：保存到本地数据目录并解析为纯文本。"""

from __future__ import annotations

import io
import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class ResumePdf:
    """简历 PDF 的保存与文本提取。"""

    # 简历存放目录
    DIR = Path.home() / ".ghost-job" / "resumes"

    @classmethod
    def save(cls, filename: str, data: bytes) -> Path:
        """把上传的 PDF 存到 ``DIR``（同名覆盖），返回本地路径。"""
        cls.DIR.mkdir(parents=True, exist_ok=True)
        path = cls.DIR / Path(filename).name
        path.write_bytes(data)
        return path

    @staticmethod
    def extract_text(data: bytes) -> str:
        """逐页提取文字，压掉多余空行；无法解析时抛 ``ValueError``。"""
        try:
            pages = PdfReader(io.BytesIO(data)).pages
            text = "\n".join(page.extract_text() or "" for page in pages)
        except PdfReadError as exc:
            raise ValueError("简历文件无法识别，请确认是有效的 PDF") from exc
        return re.sub(r"\n\s*\n+", "\n", text).strip()
