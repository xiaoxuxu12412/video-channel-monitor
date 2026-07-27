#!/usr/bin/env python3
"""看板健康检查脚本 - 全面检查 dashboard.html 的完整性"""
import re
import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DASHBOARD_PATH = os.path.join(BASE_DIR, "dashboard.html")


def check():
    with open(DASHBOARD_PATH, 'r', encoding='utf-8') as f:
        html = f.read()

    errors = []
    warnings = []
    checks = 0

    # 1. JSON数据块解析
    checks += 1
    m = re.search(r'<script type="application/json" id="embedded-data">(.*?)</script>', html, re.DOTALL)
    if not m:
        errors.append('找不到embedded-data JSON块')
    else:
        try:
            data = json.loads(m.group(1).strip())
            rec_count = len(data.get('records', {}))
            mon_count = len(data.get('monthly', {}))
            print(f'[OK] JSON解析: {rec_count}天记录, {mon_count}月统计')
            # 验证7月24日数据
            rec24 = data.get('records', {}).get('2026-07-24', {})
            pub24 = sum(1 for v in rec24.values() if v.get('status') == 'published')
            print(f'      7月24日: {pub24}/10 已发布')
        except json.JSONDecodeError as e:
            errors.append(f'JSON解析失败: {e}')

    # 2. script标签配对
    checks += 1
    open_count = html.count('<script')
    close_count = html.count('</script>')
    if open_count != close_count:
        errors.append(f'script标签不配对: {open_count}开 vs {close_count}闭')
    else:
        print(f'[OK] script标签配对: {open_count}对')

    # 3. EMBEDDED_DATA 容错解析
    checks += 1
    if 'let EMBEDDED_DATA = {};' in html:
        print('[OK] EMBEDDED_DATA 容错解析存在')
    else:
        errors.append('EMBEDDED_DATA 缺少容错解析')

    # 4. 检查所有函数定义
    checks += 1
    func_pattern = r'function\s+(\w+)\s*\([^)]*\)\s*\{'
    funcs = re.findall(func_pattern, html)
    print(f'[OK] 找到 {len(funcs)} 个函数定义')

    # 5. 检查大括号配对
    checks += 1
    js_start_match = re.search(r'<script>\n// 解析嵌入的JSON数据', html)
    js_end_match = re.search(r'</script>\s*</body>', html)
    if js_start_match and js_end_match:
        js_code = html[js_start_match.start():js_end_match.end()]
        brace_open = js_code.count('{')
        brace_close = js_code.count('}')
        paren_open = js_code.count('(')
        paren_close = js_code.count(')')
        bracket_open = js_code.count('[')
        bracket_close = js_code.count(']')
        brace_diff = brace_open - brace_close
        paren_diff = paren_open - paren_close
        bracket_diff = bracket_open - bracket_close
        print(f'[INFO] 括号: {{}}={brace_open}/{brace_close}(差{brace_diff}), ()={paren_open}/{paren_close}(差{paren_diff}), []={bracket_open}/{bracket_close}(差{bracket_diff})')
        if brace_diff != 0:
            errors.append(f'大括号不配对: 差值{brace_diff}')
        if paren_diff != 0:
            errors.append(f'圆括号不配对: 差值{paren_diff}')
        if bracket_diff != 0:
            errors.append(f'方括号不配对: 差值{bracket_diff}')
    else:
        errors.append('找不到JS代码区域')

    # 6. 检查JS引用的DOM ID
    checks += 1
    ids_in_js = set(re.findall(r"getElementById\(['\"](\w+)['\"]\)", html))
    ids_in_html = set(re.findall(r'id="(\w+)"', html))
    missing_ids = ids_in_js - ids_in_html
    if not missing_ids:
        print(f'[OK] 所有JS引用的ID({len(ids_in_js)}个)在HTML中都存在')
    else:
        errors.append(f'JS引用了不存在的ID: {missing_ids}')

    # 7. 关键函数检查
    checks += 1
    required_funcs = [
        'syncEmbeddedData', 'renderDaily', 'renderHistory', 'renderPerson',
        'renderMonthly', 'queryMonthly', 'queryDate', 'switchTab', 'getRecord',
        'saveRecord', 'formatDate', 'todayStr', 'getDataKey', 'renderCostBadge',
        'exportData', 'importData', 'generateReport', 'getDayStats', 'getAllDates',
        'setStatus', 'cycleStatus', 'batchMarkAll'
    ]
    missing_funcs = [fn for fn in required_funcs if f'function {fn}' not in html]
    if not missing_funcs:
        print(f'[OK] 所有关键函数({len(required_funcs)}个)都存在')
    else:
        errors.append(f'缺少函数: {missing_funcs}')

    # 8. 检查游离代码 - 每个function声明后紧跟的行
    checks += 1
    lines = html.split('\n')
    in_js = False
    stray_found = False
    for i, line in enumerate(lines):
        if '<script>' in line and 'application/json' not in line:
            in_js = True
        if in_js and line.strip() == '}' and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # } 后面合法的开头
            valid_starts = ('function', '//', 'document', 'window', 'if ', 'if(',
                           'const', 'let', 'var', '}', 'try', 'catch', 'return',
                           'grid', 'currentDate', '// =====', 'for', 'switchTab',
                           '', 'setTimeout')
            is_valid = any(next_line.startswith(v) for v in valid_starts) if next_line else True
            if not is_valid:
                stray_found = True
                warnings.append(f'L{i+2}: 可能游离代码 -> {next_line[:80]}')
    if not stray_found:
        print('[OK] 未发现游离代码')

    # 9. 初始化代码
    checks += 1
    init_idx = html.rfind('currentDate = todayStr()')
    if init_idx != -1:
        init_section = html[init_idx:init_idx + 500]
        if 'syncEmbeddedData()' in init_section and 'renderDaily()' in init_section and 'try' in init_section:
            print('[OK] 初始化代码有try-catch保护')
        else:
            warnings.append('初始化代码可能缺少try-catch保护')
    else:
        warnings.append('找不到初始化代码')

    # 10. CSS类检查
    checks += 1
    css_classes = ['member-card', 'status-published', 'status-pending', 'status-missed',
                   'status-tag', 'status-single', 'status-legend', 'cost-badge', 'progress-bar']
    missing_css = [cls for cls in css_classes if f'.{cls}' not in html]
    if missing_css:
        warnings.append(f'缺少CSS类: {missing_css}')
    else:
        print(f'[OK] CSS类检查通过({len(css_classes)}个)')

    # 11. onclick绑定检查
    checks += 1
    onclicks = re.findall(r'onclick="(\w+)\(', html)
    bad_onclicks = [oc for oc in set(onclicks) if f'function {oc}' not in html]
    if bad_onclicks:
        errors.append(f'onclick调用不存在的函数: {bad_onclicks}')
    else:
        print(f'[OK] onclick绑定检查通过({len(set(onclicks))}个)')

    # 12. 反引号配对
    checks += 1
    backtick_count = html.count('`')
    if backtick_count % 2 != 0:
        errors.append(f'反引号数量为奇数({backtick_count})，可能有未闭合的模板字符串')
    else:
        print(f'[OK] 反引号配对: {backtick_count}个')

    # 13. 检查 setStatus 和 cycleStatus 是否正确定义
    checks += 1
    if 'function setStatus(memberId, status) {' in html:
        print('[OK] setStatus 函数定义完整')
    else:
        errors.append('setStatus 函数定义不完整')

    if 'function cycleStatus(memberId) {' in html:
        print('[OK] cycleStatus 函数定义完整')
    else:
        errors.append('cycleStatus 函数定义不完整')

    # 14. 检查每个函数的大括号是否闭合
    checks += 1
    func_decls = list(re.finditer(r'function\s+(\w+)\s*\([^)]*\)\s*\{', html))
    brace_issues = []
    for fd in func_decls:
        fn_name = fd.group(1)
        # 从 { 开始计数大括号
        brace_pos = fd.end() - 1  # position of {
        depth = 0
        i = brace_pos
        found_close = False
        while i < len(html):
            if html[i] == '{':
                depth += 1
            elif html[i] == '}':
                depth -= 1
                if depth == 0:
                    found_close = True
                    break
            i += 1
        if not found_close:
            brace_issues.append(fn_name)
    if brace_issues:
        errors.append(f'函数大括号未闭合: {brace_issues}')
    else:
        print(f'[OK] 所有函数({len(func_decls)}个)大括号正确闭合')

    # 结果汇总
    print()
    print(f'=== 检查完成: {checks}项 ===')
    if errors:
        print(f'[ERROR] {len(errors)}个错误:')
        for e in errors:
            print(f'  - {e}')
    if warnings:
        print(f'[WARN] {len(warnings)}个警告:')
        for w in warnings:
            print(f'  - {w}')
    if not errors and not warnings:
        print('全部通过，无错误无警告!')

    return len(errors) == 0


if __name__ == '__main__':
    ok = check()
    sys.exit(0 if ok else 1)
