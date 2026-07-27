#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
视频号发布日报生成脚本
功能：读取打卡数据，生成 HTML 日报，并输出文字摘要
用法：python generate_report.py [--date 2026-07-24]
"""

import json
import os
import sys
import argparse
from datetime import datetime, date, timezone, timedelta

# 北京时区 UTC+8（GitHub Actions 默认 UTC 环境）
CST = timezone(timedelta(hours=8))

# ===== 路径配置 =====
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "team.json")
RECORDS_DIR = os.path.join(BASE_DIR, "data", "records")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

WEEKDAY_MAP = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def load_config():
    """加载团队配置"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_record(date_str):
    """读取某天的打卡记录"""
    record_path = os.path.join(RECORDS_DIR, f"{date_str}.json")
    if os.path.exists(record_path):
        with open(record_path, "r", encoding="utf-8") as f:
            return json.load(f)
    # 返回默认空记录
    config = load_config()
    record = {}
    for m in config["members"]:
        record[m["id"]] = {"status": "pending", "time": "", "note": ""}
    return record


def analyze(record, config):
    """分析打卡数据"""
    published, pending, missed = [], [], []
    for m in config["members"]:
        s = record.get(m["id"], {}).get("status", "pending")
        entry = {"name": m["name"], "channel": m["channel_name"], "time": record.get(m["id"], {}).get("time", "")}
        if s == "published":
            published.append(entry)
        elif s == "pending":
            pending.append(entry)
        else:
            missed.append(entry)
    total = len(config["members"])
    rate = round(len(published) / total * 100) if total > 0 else 0
    return {
        "published": published,
        "pending": pending,
        "missed": missed,
        "total": total,
        "pub_count": len(published),
        "pend_count": len(pending),
        "miss_count": len(missed),
        "rate": rate,
    }


def generate_text_summary(date_str, analysis, config):
    """生成纯文字摘要（用于消息汇报）"""
    weekday = WEEKDAY_MAP[date.fromisoformat(date_str).weekday()]
    lines = []
    lines.append(f"========== 视频号发布日报 ==========")
    lines.append(f"日期：{date_str} {weekday}")
    lines.append(f"团队：{config['team_name']}")
    lines.append(f"应发人数：{analysis['total']}人")
    lines.append(f"已发布：{analysis['pub_count']}人")
    lines.append(f"待确认：{analysis['pend_count']}人")
    lines.append(f"未发布：{analysis['miss_count']}人")
    lines.append(f"完成率：{analysis['rate']}%")
    lines.append("")

    if analysis["published"]:
        lines.append(f"【已发布 {len(analysis['published'])}人】")
        for p in analysis["published"]:
            t = f" ({p['time']})" if p["time"] else ""
            lines.append(f"  ✓ {p['name']} - {p['channel']}{t}")
        lines.append("")

    if analysis["pending"]:
        lines.append(f"【待确认 {len(analysis['pending'])}人】")
        for p in analysis["pending"]:
            lines.append(f"  ? {p['name']} - {p['channel']}")
        lines.append("")

    if analysis["missed"]:
        lines.append(f"【未发布 {len(analysis['missed'])}人】")
        for p in analysis["missed"]:
            lines.append(f"  ✗ {p['name']} - {p['channel']}")
        lines.append("")

    lines.append("=" * 38)
    return "\n".join(lines)


def generate_html_report(date_str, analysis, config):
    """生成 HTML 日报"""
    weekday = WEEKDAY_MAP[date.fromisoformat(date_str).weekday()]
    now_time = datetime.now(CST).strftime("%H:%M")

    rate = analysis["rate"]
    if rate >= 80:
        bar_gradient = "linear-gradient(90deg,#52c41a,#73d13d)"
        bar_color = "#389e0d"
    elif rate >= 50:
        bar_gradient = "linear-gradient(90deg,#faad14,#ffc53d)"
        bar_color = "#d48806"
    else:
        bar_gradient = "linear-gradient(90deg,#ff4d4f,#ff7875)"
        bar_color = "#cf1322"

    def member_items(lst, bg, border, badge_bg, badge_color, badge_text):
        if not lst:
            return ""
        items = "".join([
            f'<div class="list-item" style="background:{bg};border:1px solid {border}">'
            f'<span>{p["name"]} <small style="color:#999">{p["channel"]}</small>'
            f'{f" <small style=	color:#bbb>{p[chr(116)+chr(105)+chr(109)+chr(101)]}</small>" if p.get("time") else ""}</span>'
            f'<span class="badge" style="background:{badge_bg};color:{badge_color}">{badge_text}</span></div>'
            for p in lst
        ])
        return items

    pub_html = member_items(analysis["published"], "#f6ffed", "#b7eb8f", "#d9f7be", "#389e0d", "已发")
    pend_html = member_items(analysis["pending"], "#fffbe6", "#ffe58f", "#fff7e6", "#d48806", "待确认")
    miss_html = member_items(analysis["missed"], "#fff1f0", "#ffa39e", "#ffccc7", "#cf1322", "未发")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>视频号发布日报 - {date_str}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:#f0f2f5;color:#333;padding:20px}}
.report{{max-width:680px;margin:0 auto;background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08)}}
.rh{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:28px 24px}}
.rh h1{{font-size:24px;font-weight:700}}
.rh .meta{{font-size:14px;opacity:0.85;margin-top:8px}}
.rb{{padding:24px}}
.summary{{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}}
.si{{flex:1;min-width:100px;text-align:center;padding:16px 8px;border-radius:12px;background:#f8f9fc}}
.si .n{{font-size:32px;font-weight:800}}
.si .l{{font-size:13px;color:#888;margin-top:4px}}
.rate-bar{{height:12px;background:#e8e8e8;border-radius:6px;overflow:hidden;margin:8px 0 20px}}
.rate-fill{{height:100%;border-radius:6px}}
.section{{margin-bottom:20px}}
.section h3{{font-size:16px;font-weight:700;margin-bottom:10px}}
.list-item{{padding:10px 14px;border-radius:8px;margin-bottom:6px;font-size:14px;display:flex;align-items:center;justify-content:space-between}}
.badge{{font-size:12px;padding:2px 8px;border-radius:10px;font-weight:600}}
.footer{{text-align:center;padding:16px;color:#999;font-size:12px;border-top:1px solid #f0f0f0;margin-top:8px}}
</style></head><body>
<div class="report">
  <div class="rh">
    <h1>{config['team_name']}</h1>
    <div class="meta">{date_str} {weekday} | 生成时间 {now_time}</div>
  </div>
  <div class="rb">
    <div class="summary">
      <div class="si"><div class="n" style="color:#52c41a">{analysis['pub_count']}</div><div class="l">已发布</div></div>
      <div class="si"><div class="n" style="color:#faad14">{analysis['pend_count']}</div><div class="l">待确认</div></div>
      <div class="si"><div class="n" style="color:#ff4d4f">{analysis['miss_count']}</div><div class="l">未发布</div></div>
      <div class="si"><div class="n" style="color:#667eea">{rate}%</div><div class="l">完成率</div></div>
    </div>
    <div class="rate-bar"><div class="rate-fill" style="width:{rate}%;background:{bar_gradient}"></div></div>
    {"<div class='section'><h3 style='color:#389e0d'>已发布 ("+str(analysis['pub_count'])+")</h3>"+pub_html+"</div>" if pub_html else ""}
    {"<div class='section'><h3 style='color:#d48806'>待确认 ("+str(analysis['pend_count'])+")</h3>"+pend_html+"</div>" if pend_html else ""}
    {"<div class='section'><h3 style='color:#cf1322'>未发布 ("+str(analysis['miss_count'])+")</h3>"+miss_html+"</div>" if miss_html else ""}
    <div class="footer">视频号发布打卡系统 | {datetime.now(CST).strftime('%Y-%m-%d %H:%M')} 自动生成</div>
  </div>
</div>
</body></html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="视频号发布日报生成")
    parser.add_argument("--date", default=None, help="指定日期 (YYYY-MM-DD)，默认今天")
    args = parser.parse_args()

    date_str = args.date or datetime.now(CST).date().isoformat()
    config = load_config()
    record = get_record(date_str)
    analysis = analyze(record, config)

    # 生成文字摘要
    summary = generate_text_summary(date_str, analysis, config)
    print(summary)

    # 生成 HTML 报告
    os.makedirs(REPORTS_DIR, exist_ok=True)
    html = generate_html_report(date_str, analysis, config)
    report_path = os.path.join(REPORTS_DIR, f"日报_{date_str}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n[报告已保存] {report_path}")
    return summary, report_path


if __name__ == "__main__":
    main()
