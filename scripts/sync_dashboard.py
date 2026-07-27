#!/usr/bin/env python3
"""
同步检测数据到看板HTML
读取 data/records/ 下所有记录，嵌入到 dashboard.html 中
每次自动检测后自动运行
"""
import json
import os
import re
from datetime import datetime, timezone, timedelta

# 北京时区 UTC+8（GitHub Actions 默认 UTC 环境）
CST = timezone(timedelta(hours=8))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECORDS_DIR = os.path.join(BASE_DIR, "data", "records")
MONTHLY_DIR = os.path.join(BASE_DIR, "data", "monthly")
DASHBOARD_PATH = os.path.join(BASE_DIR, "dashboard.html")
TEAM_CONFIG_PATH = os.path.join(BASE_DIR, "config", "team.json")
COST_LOG_PATH = os.path.join(BASE_DIR, "data", "cost_log.json")


def load_team_config():
    with open(TEAM_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_all_records():
    records = {}
    if not os.path.exists(RECORDS_DIR):
        return records
    for fname in sorted(os.listdir(RECORDS_DIR)):
        if fname.endswith(".json"):
            date_str = fname.replace(".json", "")
            fpath = os.path.join(RECORDS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    records[date_str] = json.load(f)
            except Exception as e:
                print(f"  跳过 {fname}: {e}")
    return records


def load_monthly_data():
    """加载所有月度统计数据"""
    monthly = {}
    if not os.path.exists(MONTHLY_DIR):
        return monthly
    for fname in sorted(os.listdir(MONTHLY_DIR)):
        if fname.endswith(".json"):
            month_str = fname.replace(".json", "")
            fpath = os.path.join(MONTHLY_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    monthly[month_str] = json.load(f)
            except Exception as e:
                print(f"  跳过月度 {fname}: {e}")
    return monthly


def load_cost_data():
    """加载 API 成本日志"""
    if not os.path.exists(COST_LOG_PATH):
        return None
    try:
        with open(COST_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"  跳过成本日志: {e}")
        return None


def build_embedded_js(team_config, records, monthly_data=None, cost_data=None):
    members = []
    for m in team_config.get("members", []):
        members.append({
            "id": m["id"],
            "name": m["name"],
            "channel_name": m.get("channel_name", "")
        })

    embed = {
        "team_name": team_config.get("team_name", ""),
        "last_update_time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "members": members,
        "records": records,
        "monthly": monthly_data or {},
        "cost": cost_data,
        "sync_time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
    }
    # Use application/json block for robustness (handles newlines safely)
    return json.dumps(embed, ensure_ascii=False, indent=2)


def update_dashboard(embedded_json):
    with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace embedded data block - use JSON script block to avoid newline escaping issues
    pattern = r'<script type="application/json" id="embedded-data">.*?</script>'
    replacement = f"""<script type="application/json" id="embedded-data">
{embedded_json}
</script>"""

    if re.search(pattern, html, re.DOTALL):
        # Use lambda to avoid re.sub interpreting \n in JSON as newlines
        html = re.sub(pattern, lambda m: replacement, html, flags=re.DOTALL)
    else:
        # Fallback: replace old style block or insert before config section
        old_pattern = r'// ===== EMBEDDED_DATA_START =====.*?// ===== EMBEDDED_DATA_END ====='
        if re.search(old_pattern, html, re.DOTALL):
            html = re.sub(old_pattern, lambda m: replacement, html, flags=re.DOTALL)
        else:
            html = html.replace(
                "// ===== 配置 =====",
                f"{replacement}\n\n// ===== 配置 ====="
            )

    # Safety check: ensure JS code after JSON block is wrapped in <script> tag
    # (previous sync runs could have accidentally removed it)
    json_close = '</script>'
    idx = html.find(json_close)
    if idx != -1:
        after_json = html[idx + len(json_close):]
        stripped = after_json.lstrip()
        # Check if there's JS code not wrapped in <script>
        if stripped and not stripped.startswith('<script'):
            # Find the last </script> (end of JS code)
            last_close = html.rfind('</script>')
            if last_close > idx + len(json_close):
                # Insert <script> tag after JSON block
                js_start = idx + len(json_close)
                # Find where the actual JS code starts (skip whitespace/newlines)
                js_code_start = js_start
                while js_code_start < len(html) and html[js_code_start] in ' \t\n\r':
                    js_code_start += 1
                html = html[:js_code_start] + '<script>\n// 解析嵌入的JSON数据（带容错）\nlet EMBEDDED_DATA = {};\ntry {\n  EMBEDDED_DATA = JSON.parse(document.getElementById(\'embedded-data\').textContent);\n} catch(e) {\n  console.error(\'嵌入数据解析失败:\', e);\n}\n\n' + html[js_code_start:]

    with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    # 写入后自动验证JSON是否正确
    verify_result = verify_embedded_json(DASHBOARD_PATH)
    if not verify_result[0]:
        print(f"  [警告] 写入后验证失败: {verify_result[1]}")
        print("  尝试重新写入...")
        # 从embedded_json重新解析，用紧凑模式写入
        try:
            embed_obj = json.loads(embedded_json)
            compact_json = json.dumps(embed_obj, ensure_ascii=False)
        except Exception:
            compact_json = embedded_json.replace('\n', '')  # 最后手段：去掉所有换行
        compact_replacement = f"""<script type="application/json" id="embedded-data">
{compact_json}
</script>"""
        with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
            html2 = f.read()
        html2 = re.sub(pattern, lambda m: compact_replacement, html2, flags=re.DOTALL)
        with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
            f.write(html2)
        verify2 = verify_embedded_json(DASHBOARD_PATH)
        if verify2[0]:
            print("  [OK] 重新写入后验证通过（紧凑模式）")
        else:
            print(f"  [ERROR] 重新写入仍失败: {verify2[1]}")
    else:
        print("  [OK] 写入后JSON验证通过")


def verify_embedded_json(path):
    """验证dashboard.html中嵌入的JSON是否能正确解析"""
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    m = re.search(r'<script type="application/json" id="embedded-data">(.*?)</script>', html, re.DOTALL)
    if not m:
        return (False, "找不到embedded-data标签")
    try:
        data = json.loads(m.group(1).strip())
        if "records" not in data:
            return (False, "JSON中缺少records字段")
        return (True, f"records={len(data.get('records',{}))}天")
    except json.JSONDecodeError as e:
        return (False, str(e))


def main():
    print("同步检测数据到看板...")
    team_config = load_team_config()
    records = load_all_records()
    monthly_data = load_monthly_data()
    cost_data = load_cost_data()
    print(f"  团队: {team_config.get('team_name', '')}")
    print(f"  人数: {len(team_config.get('members', []))}")
    print(f"  历史记录: {len(records)} 天")
    print(f"  月度统计: {len(monthly_data)} 个月")
    if cost_data:
        print(f"  API成本: ${cost_data.get('estimated_cost', 0):.3f} / ${cost_data.get('budget', 5):.2f}")
    for date_str in sorted(records.keys(), reverse=True):
        rec = records[date_str]
        published = sum(1 for v in rec.values() if v.get("status") == "published")
        total = len(rec)
        print(f"    {date_str}: {published}/{total} 已发布")
    for month_str in sorted(monthly_data.keys(), reverse=True):
        mdata = monthly_data[month_str]
        print(f"    {month_str}: 合计 {mdata.get('total', 0)} 条, 人均 {mdata.get('average', 0)} 条")

    embedded_js = build_embedded_js(team_config, records, monthly_data, cost_data)
    update_dashboard(embedded_js)
    print(f"\n看板已更新: {DASHBOARD_PATH}")
    print(f"同步时间: {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}")

    # 自动复制到部署目录，供 CloudStudio 部署使用
    deploy_site_dir = os.path.join(BASE_DIR, "deploy", "site")
    deploy_index = os.path.join(deploy_site_dir, "index.html")
    try:
        os.makedirs(deploy_site_dir, exist_ok=True)
        import shutil
        shutil.copy2(DASHBOARD_PATH, deploy_index)
        print(f"\n[部署准备] 已复制到 {deploy_index}")
        print(f"[部署准备] 下一步: 用 workbuddy_cloudstudio_deploy 部署 deploy/site 目录到云端")
    except Exception as e:
        print(f"\n[警告] 复制到部署目录失败: {e}")


if __name__ == "__main__":
    main()
