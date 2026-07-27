#!/usr/bin/env python3
"""
从月度统计数据回填每日检测记录
读取 data/monthly/YYYY-MM.json，按日期拆分成 data/records/YYYY-MM-DD.json
不需要额外调用API，完全复用已有数据
"""
import json
import os
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MONTHLY_DIR = os.path.join(BASE_DIR, "data", "monthly")
RECORDS_DIR = os.path.join(BASE_DIR, "data", "records")
TEAM_CONFIG_PATH = os.path.join(BASE_DIR, "config", "team.json")


def load_team_config():
    with open(TEAM_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_monthly_data(month_str):
    fpath = os.path.join(MONTHLY_DIR, f"{month_str}.json")
    if not os.path.exists(fpath):
        print(f"  月度数据文件不存在: {fpath}")
        return None
    with open(fpath, "r", encoding="utf-8") as f:
        return json.load(f)


def get_all_dates_in_month(month_str):
    """获取某个月从1号到今天的所有日期"""
    year, mon = map(int, month_str.split("-"))
    today = datetime.now().date()
    dates = []
    day = 1
    while True:
        try:
            d = datetime(year, mon, day).date()
        except ValueError:
            break
        if d > today:
            break
        dates.append(d.strftime("%Y-%m-%d"))
        day += 1
    return dates


def backfill(month_str=None):
    if not month_str:
        # 默认当前月
        now = datetime.now()
        month_str = f"{now.year}-{str(now.month).zfill(2)}"

    print(f"=== 回填 {month_str} 每日记录 ===")

    team_config = load_team_config()
    members = team_config.get("members", [])
    monthly_data = load_monthly_data(month_str)

    if not monthly_data:
        print("  无月度数据，退出")
        return

    results = monthly_data.get("results", {})

    # 按 (member_id) -> {date: [videos]} 组织数据
    member_by_date = {}  # {member_id: {date: [video, video, ...]}}
    for member in members:
        mid = member["id"]
        member_by_date[mid] = defaultdict(list)
        r = results.get(mid, {})
        seen_vids = set()  # 按video_id去重
        for video in r.get("videos", []):
            vid = video.get("video_id", "")
            if vid and vid in seen_vids:
                continue
            if vid:
                seen_vids.add(vid)
            vdate = video.get("date", "")
            if vdate:
                member_by_date[mid][vdate].append(video)

    # 获取该月所有日期
    all_dates = get_all_dates_in_month(month_str)
    print(f"  日期范围: {all_dates[0]} ~ {all_dates[-1]} ({len(all_dates)} 天)")

    os.makedirs(RECORDS_DIR, exist_ok=True)
    created_count = 0
    updated_count = 0

    for date_str in all_dates:
        fpath = os.path.join(RECORDS_DIR, f"{date_str}.json")

        # 读取已有记录（如果有）
        existing = {}
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        # 为每个成员生成记录
        record = {}
        for member in members:
            mid = member["id"]
            videos_on_date = member_by_date[mid].get(date_str, [])

            # 如果已有auto_detect数据，保留（当天的自动检测比月度回填更准确）
            if mid in existing and existing[mid].get("source") == "auto_detect":
                record[mid] = existing[mid]
                continue

            if videos_on_date:
                titles = [v.get("title", "(无标题)") for v in videos_on_date]
                times = [v.get("time", "") for v in videos_on_date]
                record[mid] = {
                    "status": "published",
                    "time": times[0] if times else "",
                    "video_count": len(videos_on_date),
                    "video_titles": titles,
                    "source": "backfill"
                }
            else:
                # 检查是否有最近发布的视频时间
                all_videos = member_by_date[mid]
                latest = None
                for d, vids in all_videos.items():
                    for v in vids:
                        ts = v.get("publish_ts", 0)
                        if latest is None or ts > latest[0]:
                            latest = (ts, f"{d} {v.get('time', '')}")
                record[mid] = {
                    "status": "missed",
                    "time": "",
                    "latest_video_time": latest[1] if latest else "",
                    "source": "backfill"
                }

        # 写入记录
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

        if existing:
            updated_count += 1
        else:
            created_count += 1

        # 统计
        published = sum(1 for v in record.values() if v.get("status") == "published")
        total = len(record)
        print(f"  {date_str}: {published}/{total} 已发布")

    print(f"\n完成! 新建 {created_count} 天, 更新 {updated_count} 天")
    print(f"记录目录: {RECORDS_DIR}")


if __name__ == "__main__":
    import sys
    month = sys.argv[1] if len(sys.argv) > 1 else None
    backfill(month)
