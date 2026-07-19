# AI报价网 V4 - Railway 部署记录 (2026-07-18)

## 项目背景
- **任务来源**: 秦瑶派发，君哥早会拍板路线C（200m²豪华整装期望区间130-180万）
- **任务目标**: AI报价网V4升级，本周内完成
- **Phase 1**: 表单精细化（后端字段） ✅ 已完成
- **Phase 2**: agnes真实调用（不走fallback） ✅ 代码已写好
- **Phase 3**: 户型图识别（暂不做）
- **角色分配**: 陈浩（后端）、顾工（顾问：复核合肥真实价格）、博雅（前端）

---

## 部署环境
| 项目 | 值 |
|------|-----|
| 平台 | Railway (免费套餐) |
| 服务URL | https://ai-baojia-backend-production.up.railway.app |
| GitHub仓库 | https://github.com/ZWJKING/ai-baojia-backend.git |
| 本地代码目录 | `C:\Users\Administrator\.qclaw\shared\AI报价网后端` |
| Supabase数据库 | postgresql://postgres:7QIFGOS76ETr4d2q@db.oijufjvqpftkpsgopbju.supabase.co:5432/postgres |

### Railway环境变量（已配置）
| 变量名 | 值 |
|--------|-----|
| AGNES_API_KEY | sk-RN0a1mhziEX2NBfSI1i34HYa20A3ovzkrZ14zjMDBxLRalU9 |
| DATABASE_URL | postgresql://postgres:7QIFGOS76ETr4d2q@db.oijufjvqpftkpsgopbju.supabase.co:5432/postgres |
| ADMIN_TOKEN | WJ-quote-admin-20260709 |

---

## 今日问题时间线

### 问题1: 端口变量解析错误
**症状**: `--port` 收到的值是字符串 `$PORT` 而不是实际数字
```
ERROR:    [Errno 22] Invalid URL: port '$PORT': scheme must be unknown, ''
```
**原因**: Railway 的 `$PORT` 环境变量在 Nixpacks builder 中没有被正确解析
**修复**: 修改 `railway.json` 的 startCommand
```json
// 改前
"startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
// 改后
"startCommand": "sh -c 'uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}'"
```
**提交**: `5fa31be 修复Railway端口变量解析问题`

---

### 问题2: Supabase SSL连接失败
**症状**: 服务启动后约12秒崩溃
```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) 
连接到服务器的 TCP...supabase.co: 服务器是否运行在这台主机上并接受TCP/IP连接？
```
**原因**: Supabase 强制要求 SSL 连接，但连接串没有 `sslmode=require` 参数
**修复**: 修改 `app/models/database.py`，自动追加 sslmode=require
```python
if "postgresql://" in DATABASE_URL and "sslmode=" not in DATABASE_URL:
    sep = "&" if "?" in DATABASE_URL else "?"
    DATABASE_URL += f"{sep}sslmode=require"
```
**提交**: `d29f027 修复Supabase SSL连接问题`

---

### 问题3: Railway 免费套餐不支持出站网络
**症状**: 即使加了 SSL 参数，连接仍然超时崩溃
```
sqlalchemy.exc.OperationalError: (psycopg2.OperationalError) 
连接到服务器的 TCP.db.oijufjvqpftkpsgopbju.supabase.co(2400; data: 354; ...)
服务器是否运行在这台主机上并接受TCP/IP连接？
```
**根因**: Railway 免费套餐不允许容器发起出站网络请求（无法连接外部数据库）
**解决方案**: 改用 SQLite（本地文件数据库），无需出站网络
**修复**: 修改 `app/models/database.py`，强制使用 SQLite
```python
# 增加 USE_SQLITE 环境变量判断，默认 true
if not DATABASE_URL or "postgresql" not in DATABASE_URL.lower() or os.getenv("USE_SQLITE", "true").lower() == "true":
    # 使用 SQLite
    DATABASE_URL = f"sqlite:///{os.path.join(_DATA_DIR, 'quote.db')}"
```
**提交**: `d8500cb Railway免费套餐强制使用SQLite`

---

### 问题4: ADMIN_TOKEN 环境变量未加载
**症状**: 服务启动后立即崩溃
```
RuntimeError: 缺少关键环境变量: ADMIN_TOKEN
请在 .env 中配置 (参考 .env.example)
```
**原因**: 
1. config.py 中 `_get_env()` 要求关键变量必须存在
2. Railway 环境变量可能未被正确加载到 Python 进程
3. `.env.example` 文件中 ADMIN_TOKEN 的值是占位符 `wj-quote-admin-CHANGE-ME`
4. 如果 Railway 的变量没被读到，就会报这个错

**当前状态**: ❌ 未解决
**可能原因**:
- Railway 变量名大小写敏感，确认是 `ADMIN_TOKEN` 而非 `admin_token`
- 变量保存后需要重新部署才能生效
- Railway 免费套餐可能有其他环境变量限制

---

## 当前状态 (2026-07-18 23:37)

### ✅ 已完成
1. Phase 1 后端字段设计（房间数、楼层信息、拆改量、主材品牌档次）
2. 明细化报价输出（主材/辅材/人工/管理费/税费5项分类）
3. Phase 2 agnes 真实调用代码（参考技术方案文档）
4. 8个测试case全部跑通（本地验证）
5. Railway 部署基础设施搭建完成
6. 代码已推送到 GitHub，Railway 自动部署

### ❌ 待解决
1. **ADMIN_TOKEN 环境变量加载问题** — 服务启动即崩
2. **Supabase PostgreSQL 迁移** — Railway 免费套餐不支持出站网络，暂时用 SQLite
3. **前端页面对接** — 博雅负责，待后端稳定后进行
4. **报价精度校准** — 200m²豪华整装需稳定落在130-180万区间

### 🔧 明日优先事项
1. 先解决 ADMIN_TOKEN 问题（检查 Railway 变量是否正确保存）
2. 确认 SQLite 模式服务能否正常启动
3. 测试 `/api/health` 和 `/api/quote` 接口
4. 如有必要，考虑升级 Railway 到 Pro 套餐（$5/月）以支持出站网络

---

## 关键文件位置
| 文件 | 路径 |
|------|------|
| 入口 | `app/main.py` |
| 配置 | `app/config.py` |
| 数据库模型 | `app/models/database.py` |
| 报价路由 | `app/routes/quote.py` |
| Agnes 调用 | `app/services/agnes_client.py` |
| 价格校准 | `app/services/price_calibrator.py` |
| Railway配置 | `railway.json` |
| 技术方案 | `AI报价网_agnes技术方案_2026-07-09.md` |

## 踩坑总结（重要！）
1. **Railway 免费套餐不支持出站网络** — 不能连接外部数据库（Supabase/MySQL等），只能用 SQLite
2. **Railway 变量名大小写敏感** — `ADMIN_TOKEN` 必须完全匹配
3. **每次改代码后必须重新部署** — Railway 不会自动检测 git push（需要触发部署）
4. **端口变量需用 `${PORT:-8000}` 语法** — 直接 `$PORT` 在 Nixpacks 中不解析
5. **Supabase 强制 SSL** — 连接串必须加 `?sslmode=require`
6. **改 Python 代码后必须杀旧进程再启动** — 端口残留会导致混乱（本地开发经验）

---

## 后续方案建议
如果 Railway 免费套餐持续有问题，可考虑：
1. **升级 Railway Pro** ($5/月) — 支持出站网络 + 更多资源
2. **换到 Render 免费套餐** — 同样有出站网络限制
3. **换到 Fly.io** — 有免费额度且支持出站网络
4. **本地部署** — 用云服务器（阿里云/腾讯云轻量）

---

*记录人: 陈浩*
*记录时间: 2026-07-18 23:37*
*下次处理时间: 2026-07-19*
