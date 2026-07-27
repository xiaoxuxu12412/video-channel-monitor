#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
月度统计快照对比工具
对比两个日期的快照，识别每个成员发布量的变化（新增/删除/不变）。

用法：
  python diff_snapshots.py 2026-07-24 2026-07-25
  python diff_snapshots.py 2026-07-25            # 对比最新两份快照
  python diff_snapshots.py --list                 # 列出所有可用快照日期
"""

import json
import os
import sys
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAPSHOT_DIR = os.path.join(BASE_DIR, "data", "monthly_snapshots")


def load_snapshot(date_str):
    """加载指定日期的快照文件"""
    path = os.path.join(SNAPSHOT_DIR, f"{date_str}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[错误] 读取 {path} 失败: {e}")
        return None


def list_snapshots():
    """列出所有可用快照日期"""
    if not os.path.exists(SNAPSHOT_DIR):
        print(f"快照目录不存在: {SNAPSHOT_DIR}")
        return []
    files = sorted([
        f.replace(".json", "")
        for f in os.listdir(SNAPSHOT_DIR)
        if f.endswith(".json")
    ])
    return files


def diff_snapshots(date_a, date_b):
    """对比两个快照，输出每个成员的变化"""
    snap_a = load_snapshot(date_a)
    snap_b = load_snapshot(date_b)

    if not snap_a or not snap_b:
        missing = [d for d, s in [(date_a, snap_a), (date_b, snap_b)] if not s]
        print(f"[错误] 缺少快照: {', '.join(missing)}")
        print(f"可用快照: {', '.join(list_snapshots()) or '(无)'}")
        return

    results_a = snap_a.get("results", {})
    results_b = snap_b.get("results", {})

    all_ids = set(results_a.keys()) | set(results_b.keys())

    print(f"\n{'='*70}")
    print(f"  月度统计快照对比: {date_a}  →  {date_b}")
    print(f"{'='*70}")
    print(f"  快照A: {snap_a.get('snapshot_time', '?')} | 合计 {snap_a.get('total', 0)} 条")
    print(f"  快照B: {snap_b.get('snapshot_time', '?')} | 合计 {snap_b.get('total', 0)} 条")
    print(f"{'─'*70}")
    print(f"  {'成员':<8} {'A':>4} {'B':>4} {'变化':>6}   说明")
    print(f"{'─'*70}")

    rows = []
    for mid in sorted(all_ids):
        name = results_b.get(mid, results_a.get(mid, {})).get("name", mid)
        ca = results_a.get(mid, {}).get("count", 0)
        cb = results_b.get(mid, {}).get("count", 0)
        delta = cb - ca

        detail = ""
        if delta > 0:
            detail = "新增"
        elif delta < 0:
            detail = "减少"
        elif ca == 0 and cb == 0:
            detail = "无数据"
        else:
            detail = "无变化"

        # 检查内容是否真的变了（同计数但实际有修改）
        if delta == 0 and ca > 0:
            videos_a = sorted([v.get("id", v.get("title", "")) for v in results_a.get(mid, {}).get("videos", [])])
            videos_b = sorted([v.get("id", v.get("title", "")) for v in results_b.get(mid, {}).get("videos", [])])
            if videos_a != videos_b:
                detail = "替换"

        rows.append((name, ca, cb, delta, detail))

    # 按变化量降序排列
    rows.sort(key=lambda r: (r[3] == 0, -r[3], r[0]))

    for name, ca, cb, delta, detail in rows:
        if delta > 0:
            delta_str = f"+{delta}"
        else:
            delta_str = f"{delta}"

        icon = {"新增": "[+]", "减少": "[-]", "替换": "[~]", "无变化": "[ ]", "无数据": "[?]"}
        mark = icon.get(detail, "[ ]")
        print(f"  {name:<8} {ca:>4} {cb:>4} {delta_str:>6}   {mark} {detail}")

    total_delta = snap_b.get("total", 0) - snap_a.get("total", 0)
    print(f"{'─'*70}")
    total_str = f"+{total_delta}" if total_delta > 0 else f"{total_delta}"
    print(f"  {'合计':<8} {snap_a.get('total', 0):>4} {snap_b.get('total', 0):>4} {total_str:>6}")
    print(f"{'='*70}\n")


def main():
    args = sys.argv[1:]

    if not args or args == ["--list"]:
        snaps = list_snapshots()
        print(f"\n可用快照日期 ({len(snaps)} 个):")
        if snaps:
            for s in snaps:
                print(f"  - {s}")
        else:
            print("  (暂无快照)")
        print()
        return

    if len(args) == 1:
        # 对比最新两份
        snaps = list_snapshots()
        if len(snaps) < 2:
            print("[错误] 至少需要 2 个快照才能对比")
            print(f"当前只有: {snaps}")
            return
        date_b = args[0] if args[0] in snaps else snaps[-1]
        # 找 date_b 之前的最近一个
        idx = snaps.index(date_b)
        if idx == 0:
            print(f"[错误] {date_b} 是最早的一个快照，没有更早的可对比对象")
            return
        date_a = snaps[idx - 1]
        diff_snapshots(date_a, date_b)
    elif len(args) == 2:
        diff_snapshots(args[0], args[1])
    else:
        print("用法: python diff_snapshots.py [日期A] [日期B]  |  --list")
        sys.exit(1)


if __name__ == "__main__":
    main()
