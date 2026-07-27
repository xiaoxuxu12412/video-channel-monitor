#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikHub API 成本跟踪模块
记录每次 API 请求，估算累计消耗，并提供预算预警。
"""
import json
import os
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
COST_LOG_PATH = os.path.join(DATA_DIR, "cost_log.json")

CST = timezone(timedelta(hours=8))


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_log():
    ensure_data_dir()
    if not os.path.exists(COST_LOG_PATH):
        return {"requests": 0, "estimated_cost": 0.0, "entries": [], "budget": 5.0}
    with open(COST_LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_log(log):
    ensure_data_dir()
    with open(COST_LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)


def get_cost_per_request(api_config=None):
    """从 api_config 读取单次请求成本，默认 0.001 USD"""
    if api_config and "cost_per_request" in api_config:
        return float(api_config["cost_per_request"])
    return 0.001


def log_request(endpoint, description="", cost_per_request=None, api_config=None):
    """
    记录一次 API 请求。
    返回当前累计请求数和估算成本。
    """
    cpr = cost_per_request if cost_per_request is not None else get_cost_per_request(api_config)
    log = load_log()
    log["requests"] = log.get("requests", 0) + 1
    log["estimated_cost"] = round(log.get("estimated_cost", 0.0) + cpr, 4)
    entry = {
        "time": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
        "endpoint": endpoint,
        "description": description,
        "cost": cpr
    }
    log.setdefault("entries", []).append(entry)
    # 保留最近 500 条明细，防止文件过大
    if len(log["entries"]) > 500:
        log["entries"] = log["entries"][-500:]
    save_log(log)
    return log["requests"], log["estimated_cost"]


def get_budget_status():
    log = load_log()
    budget = log.get("budget", 5.0)
    used = log.get("estimated_cost", 0.0)
    remaining = round(budget - used, 2)
    percent = round(used / budget * 100, 1) if budget > 0 else 0
    return {
        "budget": budget,
        "used": used,
        "remaining": remaining,
        "percent": percent,
        "requests": log.get("requests", 0)
    }


def set_budget(budget_usd):
    log = load_log()
    log["budget"] = float(budget_usd)
    save_log(log)
    return log["budget"]


def print_summary():
    status = get_budget_status()
    print(f"\n[API成本] 累计请求: {status['requests']} 次 | 估算消耗: ${status['used']:.3f}")
    print(f"[API成本] 预算: ${status['budget']:.2f} | 剩余: ${status['remaining']:.2f} ({100 - status['percent']:.1f}%)")
    if status["percent"] >= 80:
        print(f"⚠️ 预算已使用 {status['percent']}%，建议充值或降低检测频率。")
    elif status["percent"] >= 50:
        print(f"⚠️ 预算已使用 {status['percent']}%，请注意控制月度查询次数。")
    return status


if __name__ == "__main__":
    print_summary()
