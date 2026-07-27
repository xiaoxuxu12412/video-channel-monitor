import json
import re

DASHBOARD_PATH = "C:/Users/Administrator/WorkBuddy/Claw/dashboard.html"

with open(DASHBOARD_PATH, "r", encoding="utf-8") as f:
    html = f.read()

# Remove the old broken inline embedded data block
old_pattern = r'<script>\n// ===== EMBEDDED_DATA_START =====.*?// ===== EMBEDDED_DATA_END =====\n\n'
html = re.sub(old_pattern, '', html, flags=re.DOTALL)

# Also remove the old-style inline var if it exists without the markers
old_pattern2 = r'<script>\nconst EMBEDDED_DATA = \{.*?\};\n</script>\n\n'
html = re.sub(old_pattern2, '', html, flags=re.DOTALL)

# Insert the JSON script block and the new reader right after <body> or before the existing script
new_block = '''<script type="application/json" id="embedded-data">
{
  "team_name": "鼎泰地产",
  "last_update_time": "--",
  "members": [],
  "records": {},
  "monthly": {},
  "sync_time": ""
}
</script>

<script>
// ===== 读取嵌入数据 =====
let EMBEDDED_DATA = {};
try {
  const embeddedEl = document.getElementById('embedded-data');
  if (embeddedEl) {
    EMBEDDED_DATA = JSON.parse(embeddedEl.textContent);
  }
} catch (e) {
  console.error('读取嵌入数据失败:', e);
  EMBEDDED_DATA = {};
}

'''

# Find the first <script> tag after the body and replace it with our new block
# The first <script> tag should be at the start of the JS section
html = re.sub(r'<script>\n// ===== 配置 =====', new_block + r'// ===== 配置 =====', html, count=1)

with open(DASHBOARD_PATH, "w", encoding="utf-8") as f:
    f.write(html)

print("Dashboard HTML fixed")
