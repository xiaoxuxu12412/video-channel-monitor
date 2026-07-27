#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速更新打卡状态
用法：
  python update_status.py 张三 published
  python update_status.py 张三,李四 published
  python update_status.py 张三 missed 李四 published
  python update_status.py --list
"""
import json
import os
import sys
from datetime import date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "team.json")
RECORDS_DIR = os.path.join(BASE_DIR, "data", "records")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def find_member(config, keyword):
    """模糊匹配成员名"""
    for m in config["members"]:
        if keyword in m["name"] or keyword in m["channel_name"]:
            return m
    return None


def update(member_name, status, config):
    today = date.today().isoformat()
    record_path = os.path.join(RECORDS_DIR, f"{today}.json")

    # 确保记录存在
    os.makedirs(RECORDS_DIR, exist_ok=True)
    if os.path.exists(record_path):
        with open(record_path, "r", encoding="utf-8") as f:
            record = json.load(f)
    else:
        record = {}
        for m in config["members"]:
            record[m["id"]] = {"status": "pending", "time": "", "note": ""}

    member = find_member(config, member_name)
    if not member:
        print(f"[错误] 未找到成员: {member_name}")
        return False

    from datetime import datetime
    now_time = datetime.now().strftime("%H:%M")
    record[member["id"]] = {"status": status, "time": now_time, "note": ""}

    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    status_text = {"published": "已发布", "pending": "待确认", "missed": "未发布"}.get(status, status)
    print(f"[更新] {member['name']} -> {status_text} ({now_time})")
    return True


def show_status(config):
    today = date.today().isoformat()
    record_path = os.path.join(RECORDS_DIR, f"{today}.json")
    if not os.path.exists(record_path):
        print(f"今日({today})尚无记录")
        return

    with open(record_path, "r", encoding="utf-8") as f:
        record = json.load(f)

    print(f"今日打卡状态 ({today}):")
    for m in config["members"]:
        s = record.get(m["id"], {}).get("status", "pending")
        t = record.get(m["id"], {}).get("time", "")
        icon = {"published": "✓", "pending": "?", "missed": "✗"}.get(s, "?")
        text = {"published": "已发布", "pending": "待确认", "missed": "未发布"}.get(s, s)
        time_str = f" ({t})" if t else ""
        print(f"  {icon} {m['name']:6s} {m['channel_name']:12s} -> {text}{time_str}")


def main():
    config = load_config()

    if "--list" in sys.argv or len(sys.argv) < 2:
        show_status(config)
        return

    # 解析参数：支持 "张三 published" 和 "张三,李四 published" 和 "张三 missed 李四 published"
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--list":
            i += 1
            continue
        name = args[i]
        if i + 1 < len(args) and args[i + 1] in ("published", "pending", "missed"):
            status = args[i + 1]
            # 支持逗号分隔多人
            for n in name.split(","):
                n = n.strip()
                if n:
                    update(n, status, config)
            i += 2
        else:
            # 没有状态参数，默认为 published
            for n in name.split(","):
                n = n.strip()
                if n:
                    update(n, "published", config)
            i += 1

    print()
    show_status(config)


if __name__ == "__main__":
    main()
