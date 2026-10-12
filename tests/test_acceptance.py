"""诊小通 Agent 后端验收自测脚本（MySQL + 登录鉴权版）。

覆盖需求第 7.2 节验收标准 AC-1 ~ AC-10，并额外验证：
* 登录鉴权（未登录 401、登录、注册、退出、资料、令牌失效）；
* 数据真实写入 MySQL（分诊记录 / 报告 / 预约 / 令牌 / 医生号源计数）。

运行：
    python tests/test_acceptance.py
"""
from __future__ import annotations

import os
import re
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from config.settings import settings  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []

DEFAULT_ACCOUNT = "admin"
DEFAULT_PASSWORD = "123456"
RUN_ID = str(int(time.time()) % 1000000)


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(f"  [PASS] {name}" + (f" — {detail}" if detail else ""))
    else:
        FAILED.append(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def login(client: TestClient, account: str = DEFAULT_ACCOUNT, password: str = DEFAULT_PASSWORD):
    resp = client.post("/api/user/login", json={"account": account, "password": password})
    return resp.json().get("token") if resp.status_code == 200 else None


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def main_test() -> None:
    with TestClient(main.app) as client:
        # ---------------- AC-1 后端启动 ----------------
        section("AC-1 后端启动")
        r = client.get("/api/health")
        check("GET /api/health 返回 200", r.status_code == 200, f"status={r.status_code}")
        body = r.json()
        check("返回 status=ok", body.get("status") == "ok")
        db_info = body.get("database", {})
        check("数据库为 MySQL", db_info.get("backend") == "mysql", str(db_info.get("backend")))
        check("MySQL 已连接", db_info.get("connected") is True, str(db_info.get("database")))
        print(f"  数据库：MySQL {db_info.get('host')}:{db_info.get('port')}/"
              f"{db_info.get('database')}（server {db_info.get('server_version')}）")

        # ---------------- 登录鉴权 ----------------
        section("登录鉴权（数据库 user 表）")
        r = client.get("/api/departments")
        check("未登录访问受保护接口返回 401", r.status_code == 401, f"status={r.status_code}")

        r = client.post("/api/user/login", json={"account": DEFAULT_ACCOUNT, "password": "bad"})
        check("错误密码登录失败", r.status_code == 400, f"status={r.status_code}")

        token = login(client)
        check("admin/123456 登录成功并返回令牌", bool(token), f"token 长度 {len(token or '')}")
        headers = auth(token)

        r = client.get("/api/user/profile", headers=headers)
        check("GET /api/user/profile 返回 200", r.status_code == 200, f"status={r.status_code}")
        profile = r.json().get("data", {})
        check("资料返回账号 admin", profile.get("account") == DEFAULT_ACCOUNT, str(profile.get("account")))

        account = f"user{RUN_ID}"
        r = client.post("/api/user/register", json={"account": account, "password": "123456"})
        check("新账号注册成功（写入 user 表）", r.json().get("code") == 200, r.text[:100])
        r = client.post("/api/user/register", json={"account": account, "password": "123456"})
        check("重复注册被拒绝", r.json().get("code") == 400, r.text[:80])
        r = client.post("/api/user/register", json={"account": "ab", "password": "123456"})
        check("非法账号被拒绝", r.json().get("code") == 400, r.text[:80])

        r = client.get("/api/departments", headers=headers)
        check("带令牌访问成功", r.status_code == 200, f"status={r.status_code}")

        # ---------------- AC-3 分诊闭环 ----------------
        section("AC-3 分诊闭环")
        r = client.post("/api/triage", json={
            "message": "发热两天、咳嗽有黄痰、体温 38.7℃",
            "patient_context": {"age": "26", "gender": "男"},
        }, headers=headers)
        check("POST /api/triage 返回 200", r.status_code == 200, f"status={r.status_code}")
        tri = r.json()
        departments = _db_departments(client, headers)
        check("返回推荐科室", bool(tri.get("recommended_department")), str(tri.get("recommended_department")))
        check("科室在数据库科室列表中", tri.get("recommended_department") in departments,
              str(tri.get("recommended_department")))
        check("返回风险等级", tri.get("risk_level") in settings.RISK_LEVELS, str(tri.get("risk_level")))
        check("返回证据", len(tri.get("evidence") or []) > 0, f"{len(tri.get('evidence') or [])} 条")
        agents = [t["agent"] for t in (tri.get("traces") or [])]
        check("返回 Agent 链路", len(agents) >= 5, " → ".join(agents))
        check("返回推理步骤", len(tri.get("thinking_steps") or []) > 0)
        check("返回 metrics", bool(tri.get("metrics")))
        print(f"  科室={tri.get('recommended_department')} 风险={tri.get('risk_level')}")
        print(f"  链路：{' → '.join(agents)}")

        # ---------------- AC-4 问诊记忆 ----------------
        section("AC-4 问诊记忆（同一会话追问）")
        r = client.post("/api/consultation", json={"message": "头痛三天了，晚上睡不着"}, headers=headers)
        check("首轮问诊返回 200", r.status_code == 200, f"status={r.status_code}")
        sid = r.json().get("session_id")
        r2 = client.post("/api/consultation",
                         json={"message": "那我这个情况应该挂什么科？", "session_id": sid}, headers=headers)
        check("追问返回 200", r2.status_code == 200, f"status={r2.status_code}")
        msgs = client.get(f"/api/sessions/{sid}/messages", headers=headers).json()
        check("会话消息已落库", (msgs.get("data", {}).get("total") or 0) >= 4,
              f"{msgs.get('data', {}).get('total')} 条")

        # ---------------- AC-5 用药咨询 ----------------
        section("AC-5 用药咨询")
        r = client.post("/api/medication", json={"message": "布洛芬和感冒灵能一起吃吗"}, headers=headers)
        check("用药咨询返回 200", r.status_code == 200, f"status={r.status_code}")
        med = r.json()
        check("科室归一化为药学门诊", med.get("recommended_department") == "药学门诊",
              str(med.get("recommended_department")))
        answer = med.get("answer") or ""
        check("包含免责声明", settings.DISCLAIMER in answer)
        dosage = re.search(r"(每次|每日|每天|一日)\s*\d+(\.\d+)?\s*(片|粒|袋|支|毫升|ml|mg|g|克)", answer)
        check("无具体处方剂量", dosage is None, dosage.group(0) if dosage else "")

        # ---------------- AC-6 报告解读 ----------------
        section("AC-6 报告解读（数据来自 reports / report_items 表）")
        r = client.get("/api/reports", headers=headers)
        check("报告列表返回 200", r.status_code == 200, f"status={r.status_code}")
        reports = r.json().get("data", {}).get("reports", [])
        check("内置 3 份报告（已写入数据库）", len(reports) == 3, f"{len(reports)} 份")
        check("报告含指标明细", all(len(x.get("items") or []) > 0 for x in reports))
        r = client.get(f"/api/reports/{reports[0]['id']}/interpret", headers=headers)
        check("报告解读返回 200", r.status_code == 200, f"status={r.status_code}")
        interp = r.json().get("data", {})
        check("返回分析文本", bool(interp.get("analysis")))
        check("返回解读文本", bool(interp.get("interpretation")))
        check("返回风险等级", interp.get("risk_level") in settings.RISK_LEVELS, str(interp.get("risk_level")))
        print(f"  报告={reports[0]['title']} 风险={interp.get('risk_level')} "
              f"异常项={interp.get('abnormal_count')} 解读来源={interp.get('interpreter')}")

        # ---------------- 报告上传 ----------------
        section("报告上传（report_files + 指标自动解析）")
        sample = (
            "血常规检验报告\n"
            "项目 结果 单位 参考范围 提示\n"
            "白细胞计数 WBC 12.6 10^9/L 3.5~9.5 偏高\n"
            "中性粒细胞百分比 NEUT% 82.4 % 40~75 偏高\n"
            "红细胞计数 RBC 4.72 10^12/L 4.3~5.8 正常\n"
            "血红蛋白 HGB 143 g/L 130~175 正常\n"
            "C 反应蛋白 CRP 28.5 mg/L 0~8 偏高\n"
        ).encode("utf-8")
        before_total = len(client.get("/api/reports", headers=headers).json()["data"]["reports"])

        r = client.post(
            "/api/reports/upload",
            headers=headers,
            files={"file": ("验收-血常规.txt", sample, "text/plain")},
            data={"hospital": "验收测试医院", "report_date": "2026-10-01"},
        )
        check("上传报告返回 200", r.status_code == 200, f"status={r.status_code}")
        payload = r.json()
        check("上传成功", payload.get("code") == 200, str(payload.get("message")))
        uploaded = payload["data"]["report"]
        parse_info = payload["data"]["parse"]
        check("自动解析出指标", parse_info["item_count"] >= 5, f"{parse_info['item_count']} 项")
        check("报告来源标记为 upload", uploaded.get("source") == "upload", str(uploaded.get("source")))
        check("自动识别报告名称", uploaded.get("title") == "血常规", str(uploaded.get("title")))
        check("报告带附件信息", bool(uploaded.get("file")), str((uploaded.get("file") or {}).get("name")))
        check("附件解析说明已记录", bool((uploaded.get("file") or {}).get("parse_note")))
        check("异常项已自动判定", uploaded.get("abnormal_count") == 3,
              str(uploaded.get("abnormal_count")))
        new_report_id = uploaded["id"]
        print(f"  上传解析：{parse_info['item_count']} 项 / 解析器 {parse_info['parser']} / "
              f"异常 {uploaded.get('abnormal_count')} 项")

        after_total = len(client.get("/api/reports", headers=headers).json()["data"]["reports"])
        check("报告列表数量 +1", after_total == before_total + 1, f"{before_total} → {after_total}")

        r = client.get("/api/reports", headers=headers)
        check("统计含上传报告数", r.json()["data"].get("uploaded_total") == 1,
              str(r.json()["data"].get("uploaded_total")))

        r = client.get(f"/api/reports/{new_report_id}/interpret", headers=headers)
        check("上传的报告可以 AI 解读", r.status_code == 200 and bool(r.json()["data"].get("analysis")),
              f"status={r.status_code}")

        r = client.get(f"/api/reports/{new_report_id}/file", headers=headers)
        check("附件可下载", r.status_code == 200 and len(r.content) == len(sample),
              f"status={r.status_code} size={len(r.content)}")

        r = client.post("/api/reports/upload", headers=headers,
                        files={"file": ("bad.exe", b"MZ", "application/octet-stream")})
        check("非法文件类型被拒绝", r.json().get("code") == 400, str(r.json().get("message"))[:60])

        r = client.post("/api/reports/upload", headers=headers,
                        files={"file": ("empty.txt", b"", "text/plain")})
        check("空文件被拒绝", r.json().get("code") == 400, str(r.json().get("message"))[:60])

        r = client.delete(f"/api/reports/{new_report_id}", headers=headers)
        check("删除上传的报告", r.status_code == 200, f"status={r.status_code}")
        back_total = len(client.get("/api/reports", headers=headers).json()["data"]["reports"])
        check("删除后列表数量恢复", back_total == before_total, f"{after_total} → {back_total}")
        r = client.get(f"/api/reports/{new_report_id}/interpret", headers=headers)
        check("删除后无法再解读", r.json().get("code") == 400, str(r.json().get("message"))[:40])

        # ---------------- AC-7 预约挂号 ----------------
        section("AC-7 预约挂号（排班来自 doctor_schedules 表）")
        check("科室数量为 16（含急诊科）", len(departments) == 16, f"{len(departments)} 个")
        check("包含急诊科", "急诊科" in departments)

        r = client.get("/api/appointments/schedule", params={"department": "呼吸科"}, headers=headers)
        check("排班返回 200", r.status_code == 200, f"status={r.status_code}")
        schedules = r.json().get("data", {}).get("schedules", [])
        check("排班为 7 天 × 2 时段 = 14 条", len(schedules) == 14, f"{len(schedules)} 条")
        check("号源来自 doctor_schedules（含医生与总号源）",
              all(s.get("doctor") and s.get("quota") for s in schedules))
        r2 = client.get("/api/appointments/schedule", params={"department": "呼吸科"}, headers=headers)
        check("同科室排班可复现",
              [s["doctor"] for s in schedules] == [s["doctor"] for s in r2.json()["data"]["schedules"]])

        # 选一个仍有余号的时段做「预约 → 幂等 → 取消」验证（保证脚本可重复运行）
        slot = next((s for s in schedules if s["remaining"] > 0), None)
        check("存在可预约号源", slot is not None)
        if slot is not None:
            before = slot["remaining"]
            r = client.post("/api/appointments", json={
                "department": slot["department"], "doctor": slot["doctor"],
                "doctor_title": slot["doctor_title"], "visit_date": slot["visit_date"],
                "period": slot["period"], "time_slot": slot["time_slot"],
            }, headers=headers)
            check("创建预约返回 200", r.status_code == 200, f"status={r.status_code} {r.text[:100]}")
            appt_id = r.json().get("data", {}).get("appointment_id")
            check("返回预约 ID", bool(appt_id), str(appt_id))
            check("单号格式 YL+6位", str(r.json().get("data", {}).get("code", "")).startswith("YL"))

            r = client.post("/api/appointments", json={
                "department": slot["department"], "doctor": slot["doctor"],
                "visit_date": slot["visit_date"], "period": slot["period"],
            }, headers=headers)
            check("重复提交幂等返回既有 ID",
                  r.json().get("data", {}).get("appointment_id") == appt_id,
                  str(r.json().get("data", {}).get("appointment_id")))

            after = client.get("/api/appointments/schedule",
                               params={"department": slot["department"]}, headers=headers)
            nxt = next(s for s in after.json()["data"]["schedules"]
                       if s["visit_date"] == slot["visit_date"] and s["period"] == slot["period"])
            check("预约后剩余号源减 1", nxt["remaining"] == before - 1, f"{before} → {nxt['remaining']}")

            r = client.delete(f"/api/appointments/{appt_id}", headers=headers)
            check("取消预约返回 200", r.status_code == 200, f"status={r.status_code}")
            r = client.delete(f"/api/appointments/{appt_id}", headers=headers)
            check("重复取消返回 400", r.status_code == 400, f"status={r.status_code}")
            back = client.get("/api/appointments/schedule",
                              params={"department": slot["department"]}, headers=headers)
            nxt2 = next(s for s in back.json()["data"]["schedules"]
                        if s["visit_date"] == slot["visit_date"] and s["period"] == slot["period"])
            check("取消后剩余号源恢复", nxt2["remaining"] == before, str(nxt2["remaining"]))

        # 号源约满 → 400：用「药学门诊」这种小号源科室，多账号占满
        pharm = client.get("/api/appointments/schedule",
                           params={"department": "药学门诊"}, headers=headers).json()["data"]["schedules"]
        small = min(pharm, key=lambda s: s["quota"])
        for i in range(small["quota"]):
            acc = f"bk{RUN_ID}{i}"
            client.post("/api/user/register", json={"account": acc, "password": "123456"})
            t = login(client, acc, "123456")
            if t:
                client.post("/api/appointments", json={
                    "department": small["department"], "doctor": small["doctor"],
                    "visit_date": small["visit_date"], "period": small["period"],
                }, headers=auth(t))
        now_slot = next(
            s for s in client.get("/api/appointments/schedule",
                                  params={"department": "药学门诊"}, headers=headers)
            .json()["data"]["schedules"]
            if s["visit_date"] == small["visit_date"] and s["period"] == small["period"]
        )
        check("号源已被占满（remaining=0）", now_slot["remaining"] == 0, str(now_slot["remaining"]))

        # 全新账号（未预约过该号源）应被拒绝
        late_acc = f"late{RUN_ID}"
        client.post("/api/user/register", json={"account": late_acc, "password": "123456"})
        late = login(client, late_acc, "123456")
        r = client.post("/api/appointments", json={
            "department": small["department"], "doctor": small["doctor"],
            "visit_date": small["visit_date"], "period": small["period"],
        }, headers=auth(late))
        check("号源约满返回 400 且提示「当前号源已约满」",
              r.status_code == 400 and "当前号源已约满" in r.text, f"status={r.status_code} {r.text[:80]}")

        # ---------------- AC-8 记录查询 ----------------
        section("AC-8 记录查询")
        for days in (7, 30, 180):
            r = client.get("/api/records", params={"days": days}, headers=headers)
            check(f"近 {days} 天记录返回 200", r.status_code == 200, f"status={r.status_code}")
        records = r.json().get("data", {}).get("records", [])
        check("记录包含完整摘要字段",
              all("summary" in x and "risk_level" in x and "department" in x for x in records),
              f"{len(records)} 条")
        check("风险等级已由英文枚举转为中文",
              all(x["risk_level"] in settings.RISK_LEVELS for x in records))
        r = client.get("/api/records", params={"days": 400}, headers=headers)
        check("days 超范围返回 422", r.status_code == 422, f"status={r.status_code}")

        # ---------------- AC-9 合规 ----------------
        section("AC-9 合规")
        for path, msg in [
            ("/api/triage", "我胸痛，呼吸困难，出冷汗"),
            ("/api/consultation", "我是不是得了胃癌？一定是吧"),
            ("/api/medication", "阿莫西林我该每次吃几片？剂量是多少"),
        ]:
            r = client.post(path, json={"message": msg}, headers=headers)
            ans = r.json().get("answer") or ""
            check(f"{path} 回答含免责声明", settings.DISCLAIMER in ans)
            check(f"{path} 无「确诊为」", "确诊为" not in ans)
            check(f"{path} 无绝对化「一定是」", "一定是" not in ans)
            check(f"{path} 无具体剂量", "每次吃几片" not in ans and "剂量是" not in ans)
        r = client.post("/api/triage", json={"message": "我胸痛，呼吸困难，出冷汗"}, headers=headers)
        check("红旗信号识别为高风险", r.json().get("risk_level") == "高风险", str(r.json().get("risk_level")))
        check("高风险引导到急诊科", r.json().get("recommended_department") == "急诊科",
              str(r.json().get("recommended_department")))

        # ---------------- AC-10 降级 ----------------
        section("AC-10 降级（关闭 LLM）")
        from agent.llm import llm_client
        original_enabled, original_client = llm_client.enabled, llm_client._client
        llm_client.enabled = False
        llm_client._client = None
        try:
            r = client.post("/api/triage", json={"message": "腹泻一天，伴有腹痛，没有发热"}, headers=headers)
            check("关闭 LLM 后仍返回 200", r.status_code == 200, f"status={r.status_code}")
            d = r.json()
            check("仍返回推荐科室", bool(d.get("recommended_department")), str(d.get("recommended_department")))
            check("仍返回风险等级", d.get("risk_level") in settings.RISK_LEVELS, str(d.get("risk_level")))
            check("标记为降级", d.get("degraded") is True, str(d.get("degraded")))
            check("回答含免责声明", settings.DISCLAIMER in (d.get("answer") or ""))
            agents = [t["agent"] for t in (d.get("traces") or [])]
            check("降级链路含 FormatterAgent", "FormatterAgent" in agents, " → ".join(agents))
            print(f"  降级科室={d.get('recommended_department')} 风险={d.get('risk_level')}")
        finally:
            llm_client.enabled = original_enabled
            llm_client._client = original_client

        # ---------------- 系统设置 / 指标 ----------------
        section("FR-SETTINGS / FR-METRICS")
        r = client.get("/api/settings", headers=headers)
        check("GET /api/settings 返回 200", r.status_code == 200, f"status={r.status_code}")
        s = r.json().get("data", {})
        for key in ("llm_enabled", "base_url", "model_name", "api_key_configured",
                    "deep_search_enabled", "rag_top_k", "database", "department_total"):
            check(f"settings 含 {key}", key in s)
        check("不返回 API Key 明文", "api_key" not in s or not s.get("api_key"), str(s.get("api_key")))
        check("科室总数来自数据库", s.get("department_total") == 16, str(s.get("department_total")))
        r = client.get("/api/metrics", headers=headers)
        check("GET /api/metrics 返回 200", r.status_code == 200, f"status={r.status_code}")
        metrics = r.json().get("data", {})
        check("指标含数据库信息",
              metrics.get("database", {}).get("database") == settings.MYSQL_DATABASE)

        # ---------------- 联网增强 DeepResearch ----------------
        section("联网增强 DeepResearch")
        r = client.get("/api/settings", headers=headers)
        ds = r.json().get("data", {}).get("deep_search") or {}
        check("settings 暴露搜索引擎配置", bool(ds.get("order")), str(ds.get("labels")))
        check("默认引擎为 Bing（境内可直连）", (ds.get("order") or [None])[0] == "bing",
              str(ds.get("order")))

        from agent import research

        items = research.deep_search("发热咳嗽 应该挂什么科", 3)
        check("deep_search 返回非空列表且不抛异常", isinstance(items, list) and len(items) > 0,
              f"{len(items)} 条")
        check("证据结构完整",
              all({"source", "title", "content", "kind"} <= set(i) for i in items))
        kind = items[0].get("kind")
        check("联网可用或已规范降级", kind in ("web", "fallback"),
              f"kind={kind}" + ("（网络不可达，已降级）" if kind == "fallback" else "（联网命中）"))
        print(f"  引擎={ds.get('labels')} 结果类型={kind} 条数={len(items)}")

        r = client.post("/api/triage", json={"message": "头痛三天", "enable_deep_search": True},
                        headers=headers)
        tri_web = r.json()
        agents = {t["agent"]: t for t in tri_web["traces"]}
        check("开启联网后 ResearchAgent 参与执行",
              agents.get("ResearchAgent", {}).get("status") in ("ok", "degraded"),
              str(agents.get("ResearchAgent", {}).get("status")))
        check("开启联网后存在联网证据或降级证据",
              tri_web["metrics"].get("web_evidence_count", 0) > 0
              or any(e["kind"] == "fallback" for e in tri_web["evidence"]),
              f"web={tri_web['metrics'].get('web_evidence_count')}")

        # ---------------- 退出登录 ----------------
        section("退出登录")
        temp_token = login(client)
        temp_headers = auth(temp_token)
        check("临时令牌可用", client.get("/api/user/profile", headers=temp_headers).status_code == 200)
        r = client.post("/api/user/logout", headers=temp_headers)
        check("退出登录返回 200", r.status_code == 200, f"status={r.status_code}")
        r = client.get("/api/user/profile", headers=temp_headers)
        check("退出后令牌立即失效（401）", r.status_code == 401, f"status={r.status_code}")

    # ---------------- 汇总 ----------------
    print("\n" + "=" * 64)
    for line in PASSED:
        print(line)
    for line in FAILED:
        print(line)
    print("=" * 64)
    print(f"通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")

    # 清理本次自测注册的临时账号及其数据（--no-cleanup 可跳过）
    if "--no-cleanup" not in sys.argv:
        try:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from cleanup_test_data import cleanup

            result = cleanup()
            print(f"已清理测试账号 {result['test_accounts']} 个"
                  f"（保留：{'、'.join(result['kept']) or '无'}）")
        except Exception as exc:  # noqa: BLE001
            print(f"测试数据清理失败（不影响验收结果）：{exc}")

    if FAILED:
        sys.exit(1)


def _db_departments(client, headers) -> list:
    try:
        return client.get("/api/departments", headers=headers).json()["data"]["names"]
    except Exception:  # noqa: BLE001
        return list(settings.DEPARTMENTS)


if __name__ == "__main__":
    main_test()
