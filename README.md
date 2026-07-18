# AI 报价网 W1 - FastAPI 后端

> 截止 2026-07-15 17:00 交付
> 前置: agnes 方案 (`AI报价网_agnes技术方案_2026-07-09.md`) + 合肥价格清单 (`AI报价网_合肥价格数据清单_2026-07-09.md`)

## 快速启动

```bash
cd "C:\Users\Administrator\.qclaw\shared\AI报价网后端"
# 1. 准备 .env (已有,无需操作)
# 2. 安装依赖
pip install -r requirements.txt
# 3. 启动
python -m uvicorn app.main:app --reload --port 8000
```

## 验证

```bash
# 健康检查
curl http://127.0.0.1:8000/health

# 8 步问卷
curl -X POST http://127.0.0.1:8000/api/quote -H "Content-Type: application/json" -d '{
  "area": 89.0, "layout": "3室2厅", "grade": "中档", "pack": "半包",
  "style": "现代", "special": [], "district": "蜀山区", "contact": "13800138000"
}'

# 端到端 demo
python scripts/test_quote.py
```

## 项目结构

```
AI报价网后端/
├── .env                    # 本地开发用 (含真实 API Key,严禁入代码)
├── .env.example            # 模板
├── .gitignore              # 已排除 .env
├── requirements.txt
├── app/
│   ├── main.py             # FastAPI 入口
│   ├── config.py           # .env 加载 + 掩码
│   ├── routers/
│   │   ├── health.py       # GET /health
│   │   ├── quote.py        # POST /api/quote (主路)
│   │   └── lead.py         # POST /api/lead
│   ├── services/
│   │   ├── agnes_client.py # 真实 agnes-2.0-flash 调用 + 失败重试 1 次
│   │   └── fallback.py     # L2 本地价格基线计算
│   ├── models/
│   │   └── schemas.py      # Pydantic 强校验
│   ├── data/
│   │   └── fallback_prices.json  # 8 主材 + 5 辅材 + 5 工种 + 4 档
│   └── utils/
│       ├── logger.py
│       └── rate_limit.py   # 5 QPS 滑动窗口
├── scripts/
│   ├── test_quote.py       # 端到端 demo (主交付)
│   ├── test_retry.py       # 边界场景测试
│   ├── test_retry_logic.py # 直接验证失败重试机制
│   ├── verify_prices.py    # 价格基线完整性检查
│   ├── warmup_agnes.py     # agnes 连接预热(降低冷启动延迟)
│   └── ...
└── logs/
    ├── app.log             # 服务日志
    ├── demo_2026-07-15.log # demo 验证日志
    └── ...
```

## 3 级降级链路

```
POST /api/quote
  ↓
Pydantic 强校验(8 步问卷)
  ↓
限流 5 QPS
  ↓
L1: agnes-2.0-flash 调用
  ↓ 失败(超时/HTTP错误/JSON 解析失败/Schema 校验失败)
重试 1 次(max_retries=1)
  ↓ 仍失败
L2: fallback (本地价格基线)
  ↓ 仍失败(极少见,数据文件损坏)
HTTP 500
```

## Pydantic 强校验(硬约束)

输入 `QuoteRequest`:
- `area`: float, 30-300 m²
- `layout`: str, 必须含"室"或"厅"
- `grade`: enum(简装/中档/高档/豪华)
- `pack`: enum(半包/全包/整装)
- `style`: str, 必须在 13 种风格列表中
- `special`: list, ≤10 项
- `district`: enum(蜀山/包河/瑶海/庐阳/滨湖)
- `contact`: str, 11 位 1[3-9] 开头手机号

输出 `QuoteResponse`:
- `total` > 0
- `breakdown`: 4 类(material/labor/management/tax),和 == total(容差 5 元)
- `items`: ≥ 10 行,每行 `total = quantity × unit_price`(容差 1 元)
- 全部 `items` 合价之和 ≈ total(容差 50 元,考虑 agnes 凑整)

## 验收 7 项(全部通过)

| # | 验收项 | 证据 |
|---|--------|------|
| 1 | FastAPI `/health` 200 | `curl /health` → 200, 12ms |
| 2 | 真 agnes 调用通 | `request_id=041db10a3bbf49df87331cfa2c1615e6`, elapsed 79s |
| 3 | Pydantic 校验生效 | `contact=12345` → 422, `area=10` → 422 |
| 4 | fallback_prices.json 齐全 | 8 主材 + 5 辅材 + 5 工种 + 4 档管理费 |
| 5 | 89m² 3室2厅中档半包蜀山区返回 total | ¥34,528.01 (来自 agnes) |
| 6 | 失败重试 1 次生效 | `test_retry_logic.py` 验证: 401 重试 1 次 → 抛 AgnesCallError |
| 7 | 代码无 PII / 无 hardcoded key | API Key 仅在 `.env` (已 gitignore), 日志自动掩码 |

## 注意事项

1. **冷启动**: agnes-2.0-flash 第一次连接需 ~3-5s SSL 握手,生产建议 pre-warm
2. **响应慢**: agnes "thinking" 模式消耗大量 token,89m² 简单报价 55-80s,前端需要 loading 状态
3. **JSON 稳定**: prompt 强约束 schema 后,经过 2 次实测均通过 Pydantic 校验
4. **API Key 安全**: 严禁把 `.env` 提交到 git;日志中 key 自动掩码为 `sk-R***alU9`
5. **限流**: 当前是单进程 5 QPS,生产多进程需替换为 Redis
6. **税务模型**: 简装/中档走 3% 小规模,高档/豪华走 9% 一般(财税〔2016〕36号)

## 后续(W2+ 计划)

- W2: 接入 SQLite (users / quotes / lead_capture 3 表)
- W2: 留资接口落地 (lead_capture)
- W3: 前端对接 (result.html) + PDF/Excel 导出
- W4: 部署到腾讯云轻量 + 压测
