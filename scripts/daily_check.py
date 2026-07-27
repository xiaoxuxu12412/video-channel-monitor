#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日记录初始化 & 截止检查脚本
功能：
  1. 如果当天记录文件不存在，自动创建（所有人状态为 pending）
  2. 如果已过截止时间，将 pending 自动转为 missed
用法：python daily_check.py [--finalize]
"""

import json
import os
import sys
from datetime import datetime, date

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "team.json")
RECORDS_DIR = os.path.join(BASE_DIR, "data", "records")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_today_str():
    return date.today().isoformat()


def init_today_record(config):
    """创建当天的空记录文件"""
    os.makedirs(RECORDS_DIR, exist_ok=True)
    today = get_today_str()
    record_path = os.path.join(RECORDS_DIR, f"{today}.json")

    if os.path.exists(record_path):
        print(f"[跳过] 今日记录已存在: {record_path}")
        return record_path

    record = {}
    for m in config["members"]:
        record[m["id"]] = {
            "status": "pending",
            "time": "",
            "note": ""
        }

    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"[创建] 今日记录已初始化: {record_path}")
    return record_path


def finalize_record(config):
    """截止时间后，将 pending 转为 missed"""
    today = get_today_str()
    record_path = os.path.join(RECORDS_DIR, f"{today}.json")

    if not os.path.exists(record_path):
        print("[错误] 今日记录不存在，请先运行初始化")
        return

    with open(record_path, "r", encoding="utf-8") as f:
        record = json.load(f)

    changed = 0
    now_time = datetime.now().strftime("%H:%M")
    for m in config["members"]:
        if record.get(m["id"], {}).get("status") == "pending":
            record[m["id"]] = {"status": "missed", "time": now_time, "note": "截止时间自动标记"}
            changed += 1

    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)

    print(f"[截止检查] {changed} 人由「待确认」转为「未发布」")
    return changed


def main():
    config = load_config()

    # 初始化今日记录
    init_today_record(config)

    # 如果带 --finalize 参数，执行截止检查
    if "--finalize" in sys.argv:
        finalize_record(config)

    # 打印当前状态摘要
    today = get_today_str()
    record_path = os.path.join(RECORDS_DIR, f"{today}.json")
    with open(record_path, "r", encoding="utf-8") as f:
        record = json.load(f)

    pub = sum(1 for v in record.values() if v["status"] == "published")
    pend = sum(1 for v in record.values() if v["status"] == "pending")
    miss = sum(1 for v in record.values() if v["status"] == "missed")
    total = len(record)
    rate = round(pub / total * 100) if total > 0 else 0

    print(f"\n今日状态 ({today}):")
    print(f"  已发布: {pub}  待确认: {pend}  未发布: {miss}  完成率: {rate}%")


if __name__ == "__main__":
    main()
