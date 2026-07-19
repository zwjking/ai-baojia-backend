# Railway 部署 - 环境变量配置

## 需要添加的变量（点右上角「+ 新变量」）

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `DATABASE_URL` | `postgresql://postgres.xxxxxxxxxxxxx:你的密码@aws-0-cn-northwest-1.pooler.supabase.com:5432/postgres` | Supabase 数据库连接串 |
| `AGNES_API_KEY` | `sk-RN0a1mhziEX2NBfSI1i34HYa20A3ovzkrZl4zjMDBxLRalU9` | Agnes AI API Key |
| `ADMIN_TOKEN` | `wj-quote-admin-20260709` | 管理接口令牌 |

## 已有变量（Railway 自动识别的，确认值正确即可）

- `AGNES_BASE_URL` = `https://apihub.agnes-ai.com/v1` ✅
- `AGNES_MODEL` = `agnes-2.0-flash` ✅
- `APP_HOST` = `0.0.0.0` ✅
- `APP_PORT` = `8000` ✅
- `APP_DEBUG` = `false` ✅
- `LOGIN_FIXED_CODE` = `123456` ✅

## 操作步骤

1. 点右上角 **+ 新变量**
2. 输入变量名和值
3. 点 **添加**
4. 每添加一个关键变量后，Railway 会自动重新部署

## 获取 Supabase 连接串

1. 打开 https://supabase.com/dashboard
2. 找到你的项目
3. 进入 **Settings** → **Database**
4. 复制 **Connection string**（URI 模式）
5. 粘贴到 DATABASE_URL 变量中
