"""职位接口数据 → Job 的解析测试。"""

from job.boss.jobs import Job

LIST_ITEM = {
    "encryptJobId": "xyz",
    "jobName": "人工智能应用专家",
    "salaryDesc": "18-35K·16薪",
    "brandName": "联通广州软件研究院",
    "cityName": "广州",
    "areaDistrict": "黄埔区",
    "businessDistrict": "科学城",
    "jobExperience": "5-10年",
    "jobDegree": "本科",
    "bossName": "李四",
    "bossTitle": "HRBP",
}


def test_parse_list_item_by_alias():
    job = Job.model_validate(LIST_ITEM)
    assert job.job_id == "xyz"
    assert job.title == "人工智能应用专家"
    assert job.salary == "18-35K·16薪"
    assert job.company == "联通广州软件研究院"
    assert job.location == "广州·黄埔区·科学城"
    assert job.experience == "5-10年"
    assert job.education == "本科"
    assert job.link.endswith("/job_detail/xyz.html")
    assert (job.hr_name, job.hr_title) == ("李四", "HRBP")
    assert job.description == ""


def test_parse_list_item_drops_encrypted_salary():
    job = Job.model_validate({**LIST_ITEM, "salaryDesc": "\ue031-\ue032K"})
    assert job.salary == ""


def test_parse_list_item_treats_null_as_empty():
    job = Job.model_validate({**LIST_ITEM, "bossTitle": None, "businessDistrict": None})
    assert job.hr_title == ""
    assert job.location == "广州·黄埔区"


def test_build_by_field_name():
    job = Job(job_id="abc", title="T", location="深圳")
    assert (job.job_id, job.title, job.location) == ("abc", "T", "深圳")
    assert job.link.endswith("/job_detail/abc.html")


def test_with_detail_fills_description_address_and_hr():
    job = Job.model_validate(LIST_ITEM).with_detail(
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
    assert job.description == "负责产品落地"
    assert job.address == "广州市黄埔区科学城开源大道"
    assert (job.hr_name, job.hr_title) == ("王五", "技术负责人")
    assert job.title == "人工智能应用专家"


def test_with_detail_reads_job_card_and_keeps_existing_values():
    job = Job.model_validate(LIST_ITEM).with_detail(
        {"zpData": {"jobCard": {"postDescription": "卡片描述"}}}
    )
    assert job.description == "卡片描述"
    assert (job.hr_name, job.hr_title) == ("李四", "HRBP")


def test_with_detail_ignores_malformed_payload():
    job = Job.model_validate(LIST_ITEM)
    assert job.with_detail({"zpData": None}) == job
