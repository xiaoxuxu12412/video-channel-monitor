#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频号发布自动检测脚本
功能：通过 TikHub API 自动查询每个团队成员的视频号作品列表，
      判断今天是否发布了新视频，无需人工打卡。

使用前提：
  1. 在 config/api_config.json 中填入 TikHub API Key
  2. 在 config/team.json 中填入每个成员的 finder_username 或 share_url

用法：
  python auto_detect.py              # 检测今天
  python auto_detect.py --date 2026-07-24  # 检测指定日期
  python auto_detect.py --search 张三看房   # 搜索视频号账号获取username
"""

import json
import os
import sys
import time
import argparse
import re
from datetime import datetime, date, timezone, timedelta

# 引入成本跟踪模块
import cost_tracker

# ===== 路径 =====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "team.json")
API_CONFIG_PATH = os.path.join(BASE_DIR, "config", "api_config.json")
RECORDS_DIR = os.path.join(BASE_DIR, "data", "records")

# 中国时区 UTC+8
CST = timezone(timedelta(hours=8))

WEEKDAY_MAP = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_api_config():
    """加载 API 配置，优先使用环境变量中的 API Key（GitHub Actions Secrets 注入）"""
    cfg = load_json(API_CONFIG_PATH)
    env_key = os.environ.get("TIKHUB_API_KEY")
    if env_key:
        cfg["api_key"] = env_key
    return cfg


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_today_str():
    return datetime.now(CST).strftime("%Y-%m-%d")


def today_timestamps():
    """返回今天0点和明天0点的时间戳（CST）"""
    now = datetime.now(CST)
    start = datetime(now.year, now.month, now.day, tzinfo=CST)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


# ===== HTTP 请求 =====
_cost_per_request = None

def _log_api(endpoint, description=""):
    global _cost_per_request
    if _cost_per_request is None:
        try:
            cfg = load_json(API_CONFIG_PATH)
            _cost_per_request = cost_tracker.get_cost_per_request(cfg)
        except Exception:
            _cost_per_request = 0.001
    cost_tracker.log_request(endpoint, description, _cost_per_request)


def make_request(api_config, endpoint, params=None):
    """调用 TikHub API (GET 备用)"""
    import urllib.request
    import urllib.error
    import urllib.parse

    base_url = api_config["base_url"]
    url = f"{base_url}{endpoint}"

    if params:
        query = urllib.parse.urlencode(params)
        url = f"{url}?{query}"

    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {api_config['api_key']}")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

    _log_api(endpoint, "GET fallback")
    timeout = api_config.get("request_timeout", 30)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {"code": e.code, "error": error_body, "message": f"HTTP {e.code}"}
    except Exception as e:
        return {"code": -1, "error": str(e), "message": str(e)}


def make_request_post(api_config, endpoint, data=None):
    """POST 方式调用 TikHub API"""
    import urllib.request
    import urllib.error

    base_url = api_config["base_url"]
    url = f"{base_url}{endpoint}"

    body = json.dumps(data or {}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {api_config['api_key']}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

    _log_api(endpoint, "POST")
    timeout = api_config.get("request_timeout", 30)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {"code": e.code, "error": error_body, "message": f"HTTP {e.code}"}
    except Exception as e:
        return {"code": -1, "error": str(e), "message": str(e)}


# ===== 解析视频列表 =====
def extract_videos(api_response):
    """
    从 API 响应中提取视频列表。
    TikHub 的响应格式可能有多种结构，这里做兼容处理。
    """
    if not api_response or api_response.get("code") != 200:
        return []

    data = api_response.get("data", {})

    # 可能的视频列表字段名（object 是视频号 API 的实际字段名）
    possible_keys = ["object", "videos", "objectDescList", "feeds", "list", "objects", "items"]
    videos = []
    for key in possible_keys:
        if key in data and isinstance(data[key], list):
            videos = data[key]
            break

    # 如果 data 本身就是列表
    if not videos and isinstance(data, list):
        videos = data

    # 如果 data.data 是列表
    if not videos and isinstance(data, dict):
        for key in possible_keys:
            if key in data and isinstance(data[key], list):
                videos = data[key]
                break

    return videos


def extract_video_info(video):
    """
    从单个视频对象中提取发布时间戳和标题。
    兼容多种可能的字段名。
    """
    # 发布时间可能的字段名（Unix 时间戳）
    time_fields = [
        "create_time", "createTime", "pubTime", "pub_time",
        "publishTime", "publish_time", "time", "timestamp",
        "objectDesc_createTime", "createtime"
    ]

    publish_ts = None
    for field in time_fields:
        val = video.get(field)
        if val and isinstance(val, (int, float)):
            publish_ts = int(val)
            break

    # 如果视频对象嵌套在 objectDesc 里
    if publish_ts is None:
        obj_desc = video.get("objectDesc", video.get("object_desc", {}))
        if isinstance(obj_desc, dict):
            for field in time_fields:
                val = obj_desc.get(field)
                if val and isinstance(val, (int, float)):
                    publish_ts = int(val)
                    break

    # 标题可能的字段名
    title_fields = ["desc", "description", "title", "text", "objectDesc_desc"]
    title = ""
    for field in title_fields:
        val = video.get(field)
        if val and isinstance(val, str):
            title = val
            break

    if not title:
        obj_desc = video.get("objectDesc", {})
        if isinstance(obj_desc, dict):
            for field in title_fields:
                val = obj_desc.get(field)
                if val and isinstance(val, str):
                    title = val
                    break

    # 视频 ID
    video_id = video.get("object_id") or video.get("objectId") or video.get("id", "")

    return {
        "publish_ts": publish_ts,
        "title": title[:50],
        "video_id": str(video_id),
    }


def is_published_today(publish_ts, target_date_str=None):
    """判断视频是否在目标日期发布"""
    if not publish_ts:
        return False

    if target_date_str:
        d = datetime.fromisoformat(target_date_str)
    else:
        d = datetime.now(CST)

    start = datetime(d.year, d.month, d.day, tzinfo=CST)
    end = start + timedelta(days=1)
    start_ts = int(start.timestamp())
    end_ts = int(end.timestamp())

    return start_ts <= publish_ts < end_ts


# ===== 核心检测逻辑 =====
def detect_member(api_config, member, target_date_str=None):
    """
    检测单个成员今天是否发布了视频。
    返回: {"status": "published"/"missed"/"error", "detail": {...}}
    """
    username = member.get("finder_username", "").strip()
    share_url = member.get("share_url", "").strip()

    if not username and not share_url:
        return {
            "status": "error",
            "detail": {"error": "未配置 finder_username 或 share_url", "videos_today": []}
        }

    # 构建请求参数
    params = {}
    if username:
        params["username"] = username
    if share_url:
        params["share_url"] = share_url

    endpoint = api_config["endpoint_user_videos"]

    # 视频号接口使用 POST，已验证稳定，不再额外回退 GET（避免多扣一次费用）
    resp = make_request_post(api_config, endpoint, params)

    if resp.get("code") != 200:
        error_msg = resp.get("message", "未知错误")
        return {
            "status": "error",
            "detail": {"error": error_msg, "raw": str(resp)[:200], "videos_today": []}
        }

    videos = extract_videos(resp)
    if not videos:
        return {
            "status": "error",
            "detail": {"error": "API返回数据中未找到视频列表", "videos_today": []}
        }

    # 检查是否有今天的视频，同时找最新视频
    today_videos = []
    latest_video = None
    latest_ts = 0
    for v in videos[:15]:  # 检查最近15条（含置顶视频）
        info = extract_video_info(v)
        if is_published_today(info["publish_ts"], target_date_str):
            today_videos.append(info)
        if info["publish_ts"] and info["publish_ts"] > latest_ts:
            latest_ts = info["publish_ts"]
            latest_video = info

    status = "published" if today_videos else "missed"
    return {
        "status": status,
        "detail": {
            "total_videos_checked": len(videos[:15]),
            "videos_today": today_videos,
            "latest_video": latest_video
        }
    }


def run_detection(target_date_str=None):
    """执行全团队检测"""
    config = load_json(CONFIG_PATH)
    api_config = load_api_config()

    # 检查 API Key
    if "在这里" in api_config.get("api_key", "") or "REPLACE" in api_config.get("api_key", ""):
        print("[错误] 请先在 config/api_config.json 中填入 TikHub API Key")
        print("       获取地址: https://user.tikhub.io/register")
        return None

    target_date = target_date_str or get_today_str()
    print(f"\n{'='*50}")
    print(f"  视频号发布自动检测 - {target_date}")
    print(f"  团队: {config['team_name']}")
    print(f"  人数: {len(config['members'])}人")
    print(f"{'='*50}\n")

    results = {}
    record = {}

    for i, member in enumerate(config["members"]):
        name = member["name"]
        channel = member.get("channel_name", "")
        print(f"[{i+1}/{len(config['members'])}] 检测 {name} ({channel})...")

        result = detect_member(api_config, member, target_date)
        results[member["id"]] = result

        status = result["status"]
        detail = result["detail"]

        if status == "published":
            vids = detail.get("videos_today", [])
            titles = [v["title"] for v in vids if v["title"]]
            title_str = f" - {titles[0]}" if titles else ""
            print(f"  ✓ 已发布{title_str}")
            record[member["id"]] = {
                "status": "published",
                "time": datetime.now(CST).strftime("%H:%M"),
                "video_count": len(vids),
                "video_titles": titles,
                "source": "auto_detect"
            }
        elif status == "missed":
            latest = detail.get("latest_video")
            latest_str = ""
            if latest and latest["publish_ts"]:
                latest_dt = datetime.fromtimestamp(latest["publish_ts"], tz=CST)
                latest_str = f" (最近一条: {latest_dt.strftime('%m-%d %H:%M')})"
            print(f"  ✗ 未发布{latest_str}")
            record[member["id"]] = {
                "status": "missed",
                "time": datetime.now(CST).strftime("%H:%M"),
                "latest_video_time": latest_dt.strftime("%Y-%m-%d %H:%M") if latest and latest.get("publish_ts") else "",
                "source": "auto_detect"
            }
        else:
            error = detail.get("error", "未知错误")
            print(f"  ! 检测失败: {error}")
            record[member["id"]] = {
                "status": "pending",
                "time": datetime.now(CST).strftime("%H:%M"),
                "error": error,
                "source": "auto_detect"
            }

        # 请求间隔，避免频率限制
        if i < len(config["members"]) - 1:
            time.sleep(1)

    # 保存记录
    record_path = os.path.join(RECORDS_DIR, f"{target_date}.json")
    save_json(record_path, record)
    print(f"\n[记录已保存] {record_path}")

    # 统计
    pub_count = sum(1 for v in record.values() if v["status"] == "published")
    miss_count = sum(1 for v in record.values() if v["status"] == "missed")
    err_count = sum(1 for v in record.values() if v["status"] == "pending")
    total = len(record)
    rate = round(pub_count / total * 100) if total > 0 else 0

    print(f"\n{'─'*50}")
    print(f"  检测完成!")
    print(f"  已发布: {pub_count}  未发布: {miss_count}  检测失败: {err_count}")
    print(f"  完成率: {rate}%")
    print(f"{'─'*50}\n")

    # 打印成本消耗
    cost_tracker.print_summary()

    # 同步更新月度统计（全团队当前月份），确保看板月度数据与最新抓取一致
    try:
        print("\n[月度统计] 开始同步更新全团队当月发布统计...")
        run_monthly_query()
        print("[月度统计] 同步完成")
    except Exception as e:
        print(f"[月度统计] 同步失败（不影响当日检测）: {e}")

    return {"record": record, "results": results, "summary": {
        "date": target_date,
        "total": total,
        "published": pub_count,
        "missed": miss_count,
        "error": err_count,
        "rate": rate
    }}


def search_account(api_config, keyword):
    """搜索视频号账号，帮助用户找到 finder_username"""
    print(f"搜索视频号账号: {keyword}")

    # 使用搜一搜接口搜索（POST 方式）
    endpoint = api_config.get("endpoint_search", "/api/v1/wechat_search/v2/fetch_search")
    data = {"keyword": keyword, "type": "channels"}

    resp = make_request_post(api_config, endpoint, data)

    if resp.get("code") != 200:
        print(f"搜索失败: {resp.get('message', '未知错误')}")
        return

    # 解析搜索结果：data.results.data[].subBoxes[].items[]
    resp_data = resp.get("data", {})
    results = resp_data.get("results", {})
    data_blocks = results.get("data", [])

    accounts = []
    for block in data_blocks:
        for sub in block.get("subBoxes", []):
            for item in sub.get("items", []):
                if item.get("accTypeName") == "视频号":
                    # 清除 HTML 高亮标签
                    title = re.sub(r'<[^>]+>', '', item.get("title", ""))
                    finder_username = item.get("noticeParam", {}).get("finderUsername", "")
                    thumb = item.get("thumbUrl", "")
                    accounts.append({
                        "nickname": title,
                        "finder_username": finder_username,
                        "avatar": thumb
                    })

    if not accounts:
        print("未找到相关视频号账号")
        return

    print(f"\n找到 {len(accounts)} 个相关账号:")
    for i, acc in enumerate(accounts[:10]):
        print(f"  {i+1}. {acc['nickname']}")
        print(f"     finder_username: {acc['finder_username']}")
    print(f"\n将 finder_username 填入 config/team.json 即可。")


def fetch_all_videos_page(api_config, username, cursor=0, count=20):
    """拉取一页视频列表，返回 (videos, next_cursor, has_more)"""
    # TikHub 视频号接口的翻页参数名是 last_buffer（不是 max_cursor），
    # 之前用 max_cursor 时无论怎么翻页都返回同样的前 15 条，导致月度统计被截断
    params = {"username": username, "last_buffer": str(cursor) if cursor else "", "count": count}
    endpoint = api_config["endpoint_user_videos"]

    # 月度查询统一使用 POST，不再 GET 回退
    resp = make_request_post(api_config, endpoint, params)

    if resp.get("code") != 200:
        return [], 0, False

    data = resp.get("data", {})
    videos = data.get("object", [])
    next_cursor = data.get("lastBuffer", data.get("last_buffer", ""))
    has_more = data.get("continueFlag", 0) == 1

    return videos, next_cursor, has_more


def query_monthly(api_config, member, year, month):
    """
    查询某成员指定月份的视频发布情况。
    自动翻页，直到视频日期早于目标月份。
    """
    username = member.get("finder_username", "").strip()
    if not username:
        return {"count": 0, "videos": [], "error": "未配置 finder_username"}

    # 目标月份的起止时间戳
    start_dt = datetime(year, month, 1, tzinfo=CST)
    if month == 12:
        end_dt = datetime(year + 1, 1, 1, tzinfo=CST)
    else:
        end_dt = datetime(year, month + 1, 1, tzinfo=CST)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    month_videos = []
    seen_ids = set()  # 按video_id去重
    cursor = 0
    page = 0
    max_pages = 1  # 月度查询只翻 1 页（15 条），按用户要求先按1页跑

    while page < max_pages:
        page += 1
        videos, next_cursor, has_more = fetch_all_videos_page(api_config, username, cursor, 20)

        if not videos:
            break

        for v in videos:
            info = extract_video_info(v)
            ts = info["publish_ts"]
            if not ts:
                continue

            # 按video_id去重
            vid = info.get("video_id", "")
            if vid and vid in seen_ids:
                continue

            if ts >= end_ts:
                # 比目标月份还晚，跳过
                continue
            if ts < start_ts:
                # 比目标月份早，跳过（不停止翻页，因为API返回顺序不保证按时间排序）
                continue
            # 在目标月份内
            if vid:
                seen_ids.add(vid)
            dt = datetime.fromtimestamp(ts, tz=CST)
            info["date"] = dt.strftime("%Y-%m-%d")
            info["time"] = dt.strftime("%H:%M")
            month_videos.append(info)

        if not has_more:
            break

        cursor = next_cursor
        time.sleep(0.5)  # 请求间隔

    # 按日期排序（新的在前）
    month_videos.sort(key=lambda x: x["publish_ts"], reverse=True)

    return {"count": len(month_videos), "videos": month_videos, "error": None}


def run_monthly_query(target_name=None, target_month=None):
    """执行月度查询，可查单人或全团队"""
    config = load_json(CONFIG_PATH)
    api_config = load_api_config()

    if "在这里" in api_config.get("api_key", "") or "REPLACE" in api_config.get("api_key", ""):
        print("[错误] 请先在 config/api_config.json 中填入 TikHub API Key")
        return None

    # 解析目标月份
    if target_month:
        parts = target_month.split("-")
        year, month = int(parts[0]), int(parts[1])
    else:
        now = datetime.now(CST)
        year, month = now.year, now.month

    month_str = f"{year}年{month}月"

    # 筛选目标成员
    if target_name:
        members = [m for m in config["members"]
                   if target_name in m["name"] or target_name in m.get("channel_name", "")]
        if not members:
            print(f"未找到匹配 '{target_name}' 的团队成员")
            print(f"团队成员: {', '.join(m['name'] for m in config['members'])}")
            return None
    else:
        members = config["members"]

    print(f"\n{'='*55}")
    print(f"  视频号月度发布统计 - {month_str}")
    print(f"  查询范围: {'全团队' if not target_name else members[0]['name']}")
    print(f"  人数: {len(members)}人")
    print(f"{'='*55}\n")

    all_results = {}

    for i, member in enumerate(members):
        name = member["name"]
        channel = member.get("channel_name", "")
        print(f"[{i+1}/{len(members)}] 查询 {name} ({channel}) {month_str}发布量...")

        result = query_monthly(api_config, member, year, month)

        if result["error"]:
            print(f"  ! 查询失败: {result['error']}")
            all_results[member["id"]] = {
                "name": name,
                "channel": channel,
                "count": 0,
                "videos": [],
                "error": result["error"]
            }
        else:
            count = result["count"]
            print(f"  → 本月发布 {count} 条")
            for v in result["videos"][:5]:
                print(f"    {v['date']} {v['time']} | {v['title'][:40]}")
            if count > 5:
                print(f"    ... 还有 {count - 5} 条")
            all_results[member["id"]] = {
                "name": name,
                "channel": channel,
                "count": count,
                "videos": result["videos"],
                "error": None
            }

        if i < len(members) - 1:
            time.sleep(1)

    # 汇总
    print(f"\n{'─'*55}")
    print(f"  {month_str} 发布统计汇总")
    print(f"{'─'*55}")

    # 按发布量排序
    sorted_results = sorted(all_results.values(), key=lambda x: x["count"], reverse=True)

    for rank, r in enumerate(sorted_results, 1):
        if r["error"]:
            print(f"  {rank}. {r['name']:6s} | 查询失败")
        else:
            bar = "█" * r["count"] if r["count"] <= 30 else "█" * 30 + f"+{r['count']-30}"
            print(f"  {rank}. {r['name']:6s} | {r['count']:3d} 条 | {bar}")

    total = sum(r["count"] for r in all_results.values() if not r["error"])
    avg = total / len([r for r in all_results.values() if not r["error"]]) if all_results else 0
    print(f"\n  全团队合计: {total} 条 | 人均: {avg:.1f} 条")

    # 保存结果（与已有数据合并，避免覆盖其他成员）
    monthly_dir = os.path.join(BASE_DIR, "data", "monthly")
    os.makedirs(monthly_dir, exist_ok=True)
    output_path = os.path.join(monthly_dir, f"{year}-{month:02d}.json")
    
    # 读取已有数据
    existing_data = {}
    if os.path.exists(output_path):
        try:
            existing_data = load_json(output_path)
        except Exception:
            existing_data = {}
    
    # 合并：用新查询结果覆盖对应成员，保留其他成员的旧数据
    merged_results = existing_data.get("results", {})
    merged_results.update(all_results)
    
    # 重新计算汇总
    total = sum(r["count"] for r in merged_results.values() if not r.get("error"))
    valid_count = len([r for r in merged_results.values() if not r.get("error")])
    avg = total / valid_count if valid_count > 0 else 0
    
    save_json(output_path, {
        "month": f"{year}-{month:02d}",
        "query_time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "results": merged_results,
        "total": total,
        "average": round(avg, 1)
    })
    print(f"\n[结果已保存] {output_path}")

    # 同步保存一份带日期的快照到 data/monthly_snapshots/YYYY-MM-DD.json
    # 用于跨日对比，识别新增/删除/修改
    try:
        snapshot_dir = os.path.join(BASE_DIR, "data", "monthly_snapshots")
        os.makedirs(snapshot_dir, exist_ok=True)
        snapshot_date = datetime.now(CST).strftime("%Y-%m-%d")
        snapshot_path = os.path.join(snapshot_dir, f"{snapshot_date}.json")
        save_json(snapshot_path, {
            "month": f"{year}-{month:02d}",
            "snapshot_time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
            "results": merged_results,
            "total": total,
            "average": round(avg, 1)
        })
        print(f"[快照已备份] {snapshot_path}")
    except Exception as e:
        print(f"[警告] 快照备份失败: {e}")

    # 打印成本消耗
    cost_tracker.print_summary()

    return all_results


def main():
    parser = argparse.ArgumentParser(description="视频号发布自动检测")
    parser.add_argument("--date", default=None, help="指定日期 (YYYY-MM-DD)")
    parser.add_argument("--search", default=None, help="搜索视频号账号")
    parser.add_argument("--monthly", nargs="?", const="", default=None,
                        help="查询月度发布量。可选跟人员名，如 --monthly 阿涛；不跟则查全团队")
    parser.add_argument("--month", default=None, help="指定月份 (YYYY-MM)，配合 --monthly 使用")
    args = parser.parse_args()

    if args.search:
        api_config = load_api_config()
        if "在这里" in api_config.get("api_key", "") or "REPLACE" in api_config.get("api_key", ""):
            print("[错误] 请先填入 TikHub API Key")
            return
        search_account(api_config, args.search)
        return

    if args.monthly is not None:
        # --monthly 后面可以跟人名，也可以不跟（查全团队）
        target_name = args.monthly.strip() if args.monthly else None
        run_monthly_query(target_name, args.month)
        return

    result = run_detection(args.date)
    if result:
        # 打印详细汇总
        config = load_json(CONFIG_PATH)
        record = result["record"]
        print("\n详细汇总:")
        for member in config["members"]:
            r = record.get(member["id"], {})
            status = r.get("status", "pending")
            icon = {"published": "✓", "missed": "✗", "pending": "!"}.get(status, "?")
            text = {"published": "已发布", "missed": "未发布", "pending": "检测失败"}.get(status, status)
            extra = ""
            if status == "published" and r.get("video_titles"):
                extra = f" - {r['video_titles'][0][:30]}"
            elif status == "missed" and r.get("latest_video_time"):
                extra = f" (最近: {r['latest_video_time']})"
            print(f"  {icon} {member['name']:6s} -> {text}{extra}")

        # 自动同步看板数据（减少 automation 中间步骤，降低中断风险）
        auto_sync()


def auto_sync():
    """检测完成后自动同步看板数据，减少 automation 步骤数"""
    sync_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sync_dashboard.py")
    if os.path.exists(sync_script):
        print("\n" + "="*50)
        print("[自动同步] 开始同步看板数据...")
        import subprocess
        python_exe = sys.executable
        result = subprocess.run([python_exe, sync_script], capture_output=True, text=True, encoding="utf-8")
        if result.returncode == 0:
            print("[自动同步] 看板同步完成")
        else:
            print(f"[自动同步] 同步失败: {result.stderr[:200]}")
    else:
        print("[自动同步] sync_dashboard.py 不存在，跳过")


if __name__ == "__main__":
    main()
