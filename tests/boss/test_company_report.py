import io

from pypdf import PdfReader

from job.boss.company_report import company_pdf

REPORT = {
    "name": "恒达传媒",
    "full_name": "普宁恒达文化传媒有限公司",
    "checked_at": "2026-09-29 18:48",
    "risk": "low",
    "risk_label": "低风险",
    "summary": "未发现欠薪记录",
    "points": [{"text": "工商显示在营", "href": "https://example.com/a?x=1&y=2"}],
    "info": [{"label": "法定代表人", "value": "肖丽文"}],
    "hits": [
        {
            "title": "恒达 <公司> 招聘",
            "href": "https://example.com/b",
            "body": "Aug 14 · 小微企业",
            "query": "欠薪",
        }
    ],
}


def test_pdf_contains_all_sections():
    pdf = PdfReader(io.BytesIO(company_pdf(REPORT)))
    text = "".join(page.extract_text() for page in pdf.pages)
    for part in (
        "普宁恒达文化传媒有限公司",
        "低风险",
        "未发现欠薪记录",
        "工商显示在营",
        "肖丽文",
        "网上搜索（1 条）",
        "恒达 <公司> 招聘",
        "小微企业",
    ):
        assert part in text
    links = [a.get_object()["/A"]["/URI"] for p in pdf.pages for a in p["/Annots"]]
    assert links == ["https://example.com/a?x=1&y=2", "https://example.com/b"]


def test_pdf_without_info_or_hits():
    pdf = PdfReader(io.BytesIO(company_pdf({"name": "某公司", "risk": "unknown"})))
    text = pdf.pages[0].extract_text()
    assert "BOSS 公司主页上没有工商信息" in text
    assert "网上搜索（0 条）" in text
