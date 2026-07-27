# 视频号发布自动检测系统 - 使用说明

## 系统原理

通过 TikHub 第三方 API 自动查询每个团队成员的视频号作品列表，判断今天是否发布了新视频。**无需手动打卡，系统自动检测。**

## 系统组成

| 文件 | 作用 |
|------|------|
| `config/api_config.json` | API 配置（TikHub API Key） |
| `config/team.json` | 团队配置（人员名单 + 视频号用户名） |
| `scripts/auto_detect.py` | **核心：自动检测脚本**，调 API 查每个人的作品列表 |
| `scripts/generate_report.py` | 生成日报（HTML + 文字摘要） |
| `scripts/daily_check.py` | 记录初始化 + 截止检查（备用） |
| `scripts/update_status.py` | 手动更新状态（备用） |
| `dashboard.html` | 可视化看板（查看历史记录） |
| `data/records/` | 每日检测数据（JSON） |
| `reports/` | 生成的日报 HTML |

## 配置步骤（一次性）

### 第1步：注册 TikHub 获取 API Key
1. 打开 https://user.tikhub.io/register 注册账号
2. 注册后免费送 $0.05 额度（约50次请求，够用5天）
3. 在 https://user.tikhub.io/dashboard/api 获取 API Key
4. 将 Key 填入 `config/api_config.json` 的 `api_key` 字段

### 第2步：配置团队成员的视频号用户名
在 `config/team.json` 中，为每个成员填写 `finder_username` 字段。

获取 finder_username 的方法：
- **方法1**：让每个人在微信里分享自己的视频号名片，链接中包含 username
- **方法2**：运行搜索命令查找：`python scripts/auto_detect.py --search 张三看房`
- **方法3**：直接把视频号分享链接填入 `share_url` 字段

### 第3步：测试检测
```bash
python scripts/auto_detect.py
```
看到每个人的检测结果（✓已发布 / ✗未发布）说明配置成功。

## 自动化时间表

| 时间 | 自动化任务 | 说明 |
|------|-----------|------|
| 每天 09:00 | 早间提醒 | 提醒大家今天发视频 |
| 每天 21:00 | **自动检测 + 汇报** | API 自动查询每人视频号 → 生成日报 → 汇报给店长 |

## 费用说明

- TikHub API 按次计费：约 $0.001/次请求
- 10人每天检测1次 = 10次请求 = 约 $0.01/天
- 每月约 $0.30（不到3元人民币）
- 新注册免费送 $0.05 额度

## 日常使用

配置完成后，**你什么都不用做**：
- 早上9点收到提醒
- 晚上21点自动收到检测日报
- 随时可以手动运行检测：跟我说"检测一下今天的发布情况"

## 关于数据准确性

- API 返回的是视频号公开数据，与微信内看到的一致
- 检测的是"今天是否有新作品发布"
- 如果某人设了私密/仅好友可见，可能检测不到（极少见）
- API 偶尔可能有延迟（发完视频后几分钟内同步）
