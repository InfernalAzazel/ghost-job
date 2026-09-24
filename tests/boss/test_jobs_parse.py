from pathlib import Path

from backend.boss.jobs import (
    Job,
    JobDetail,
    JobInfo,
    job_to_dict,
    looks_like_login_wall,
    parse_jobs_from_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "job_list_snippet.html"


def test_parse_jobs_from_html_extracts_fields():
    html = FIXTURE.read_text(encoding="utf-8")
    jobs = parse_jobs_from_html(html)
    assert len(jobs) == 2
    info = jobs[0].info
    assert info.title == "AI应用开发工程师"
    assert info.company == "某科技有限公司"
    assert info.salary == "25-40K"
    assert info.location == "广州·天河区"
    assert info.experience == "3-5年"
    assert info.education == "本科"
    assert info.job_id == "10001"
    assert info.link.endswith("/job_detail/10001.html")
    assert jobs[0].detail.description == ""
    assert jobs[1].info.title == "AI Agent 工程师"
    assert jobs[1].info.location == "广州·黄埔区·科学城"


def test_job_to_dict_flat_ws_shape():
    html = FIXTURE.read_text(encoding="utf-8")
    d = job_to_dict(parse_jobs_from_html(html)[0])
    assert d["jobId"] == "10001"
    assert d["title"] == "AI应用开发工程师"
    assert d["location"] == "广州·天河区"
    assert d["experience"] == "3-5年"
    assert d["education"] == "本科"
    assert d["description"] == ""


def test_job_to_dict_includes_description():
    d = job_to_dict(
        Job(
            info=JobInfo(title="T", company="C", salary="10K"),
            detail=JobDetail(description="负责 AI 应用开发"),
        )
    )
    assert d["description"] == "负责 AI 应用开发"


def test_job_to_dict_includes_hr_and_address():
    d = job_to_dict(
        Job(
            info=JobInfo(title="T", company="C", salary="10K"),
            detail=JobDetail(
                description="职责",
                hr_name="张三",
                hr_title="招聘经理",
                address="广州市天河区科韵路 XX 号",
            ),
        )
    )
    assert d["hrName"] == "张三"
    assert d["hrTitle"] == "招聘经理"
    assert d["address"] == "广州市天河区科韵路 XX 号"
    assert d["description"] == "职责"


def test_job_detail_from_list_item_hr():
    from backend.boss.jobs import job_detail_from_list_item

    d = job_detail_from_list_item({"bossName": "李四", "bossTitle": "HRBP"})
    assert d.hr_name == "李四"
    assert d.hr_title == "HRBP"
    assert d.description == ""
    assert d.address == ""


def test_job_detail_from_detail_payload():
    from backend.boss.jobs import job_detail_from_detail_payload

    d = job_detail_from_detail_payload(
        {
            "zpData": {
                "jobInfo": {
                    "postDescription": "负责产品落地",
                    "address": "广州市黄埔区科学城开源大道",
                },
                "bossInfo": {"name": "王五", "title": "技术负责人"},
            }
        }
    )
    assert d.description == "负责产品落地"
    assert d.address == "广州市黄埔区科学城开源大道"
    assert d.hr_name == "王五"
    assert d.hr_title == "技术负责人"


def test_merge_job_detail_fills_empty_only():
    from backend.boss.jobs import JobDetail, merge_job_detail

    merged = merge_job_detail(
        JobDetail(hr_name="API-HR", description="API desc"),
        JobDetail(hr_name="List-HR", hr_title="HR", address="地址A"),
        JobDetail(description="DOM desc", address="地址B", hr_title="DOM title"),
    )
    assert merged.hr_name == "API-HR"
    assert merged.hr_title == "HR"
    assert merged.address == "地址A"
    assert merged.description == "API desc"


def test_looks_like_login_wall_when_dialog_visible():
    html = '<div class="login-dialog-wrap"></div><div class="job-list-box"></div>'
    assert looks_like_login_wall(html) is True


def test_looks_like_login_wall_false_when_jobs_present():
    html = FIXTURE.read_text(encoding="utf-8")
    assert looks_like_login_wall(html) is False


def test_parse_jobs_from_job_card_wrapper():
    html = (Path(__file__).parent / "fixtures" / "job_card_wrapper_snippet.html").read_text(
        encoding="utf-8"
    )
    jobs = parse_jobs_from_html(html)
    assert len(jobs) == 1
    assert jobs[0].info.title == "前端工程师"
    assert jobs[0].info.company == "新结构公司"
    assert jobs[0].info.salary == "20-30K"
    assert jobs[0].info.job_id == "20001"
    assert jobs[0].info.link.endswith("/job_detail/20001.html")


def test_looks_like_font_encrypted_detects_pua():
    from backend.boss.jobs import looks_like_font_encrypted

    assert looks_like_font_encrypted("-K") is True
    assert looks_like_font_encrypted("25-40K") is False


def test_resolve_salary_prefers_api_map():
    from backend.boss.jobs import resolve_salary

    salary = resolve_salary(
        dom_salary="-K",
        job_id="abc",
        salary_by_id={"abc": "25-40K"},
        api_items=[],
        index=0,
    )
    assert salary == "25-40K"


def test_salary_map_from_joblist_payload():
    from backend.boss.jobs import salary_map_from_joblist_payload

    payload = {
        "zpData": {
            "jobList": [
                {"encryptJobId": "id1", "salaryDesc": "18-22K"},
                {"encryptJobId": "id2", "salaryDesc": "K"},
            ]
        }
    }
    m = salary_map_from_joblist_payload(payload)
    assert m == {"id1": "18-22K"}


def test_job_info_from_api_item():
    from backend.boss.jobs import job_info_from_api_item

    info = job_info_from_api_item(
        {
            "jobName": "人工智能应用专家",
            "salaryDesc": "18-35K·16薪",
            "brandName": "联通广州软件研究院",
            "cityName": "广州",
            "areaDistrict": "黄埔区",
            "businessDistrict": "科学城",
            "jobExperience": "5-10年",
            "jobDegree": "本科",
            "encryptJobId": "xyz",
        }
    )
    assert info.title == "人工智能应用专家"
    assert info.salary == "18-35K·16薪"
    assert info.company == "联通广州软件研究院"
    assert info.location == "广州·黄埔区·科学城"
    assert info.experience == "5-10年"
    assert info.education == "本科"
    assert info.job_id == "xyz"
