"""
SQLAlchemy ORM 模型 - W2 P1 / V2 登录改造

支持双数据库:
  - SQLite (本地开发, DATABASE_URL 不含 postgresql://)
  - PostgreSQL/Supabase (线上, DATABASE_URL 含 postgresql://)

四张表(实际三张,users 加 password_hash 字段):
  users    - 用户(手机号注册,V2 加 password_hash)
  quotes   - 报价记录(含原始问卷+返回JSON)
  leads    - 留资记录

启动时自动建表 + V2 ALTER TABLE 兼容老库。
"""
from __future__ import annotations

import logging
import os
from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

# ===== 数据库 URL: 优先读环境变量, 否则 fallback 到 SQLite =====
# ===== 数据库 URL: 优先读环境变量, 否则 fallback 到 SQLite =====
# Railway 免费套餐不支持出站网络，默认用 SQLite
DATABASE_URL = os.getenv("DATABASE_URL", None)

if not DATABASE_URL or "postgresql" not in DATABASE_URL.lower() or os.getenv("USE_SQLITE", "true").lower() == "true":
    # 本地开发/Railway免费套餐: 用 SQLite
    _DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
    os.makedirs(_DATA_DIR, exist_ok=True)
    DATABASE_URL = f"sqlite:///{os.path.join(_DATA_DIR, 'quote.db')}"
    logger.warning("Using SQLite (Railway free tier / no DATABASE_URL) — set USE_SQLITE=false to force PostgreSQL")
else:
    # Supabase 强制 SSL 连接
    if "postgresql://" in DATABASE_URL and "sslmode=" not in DATABASE_URL:
        sep = "&" if "?" in DATABASE_URL else "?"
        DATABASE_URL += f"{sep}sslmode=require"
    logger.info("Using PostgreSQL: ***@%s", DATABASE_URL.split('@')[1] if '@' in DATABASE_URL else DATABASE_URL)

# ===== 引擎配置 =====
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL: 连接超时 10s，防止启动卡死
    engine_kwargs["connect_args"] = {"connect_timeout": 10}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    mobile = Column(String(11), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=True)  # V2: bcrypt 加密, 老用户为空
    created_at = Column(DateTime, default=func.now())
    quote_count = Column(Integer, default=0)
    # P0-5: 密码版本号, 改密时 +1, JWT payload.ver < 当前 ver 即失效
    password_version = Column(Integer, default=0, nullable=False)


class Quote(Base):
    """报价记录表"""
    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)  # 未登录用户可为空
    survey_json = Column(Text, nullable=False)  # 原始问卷 JSON
    quote_json = Column(Text, nullable=False)   # agnes 或 fallback 返回的 JSON
    source = Column(String(20))  # 'agnes' or 'fallback'
    request_id = Column(String(64))  # agnes request id
    generated_at = Column(DateTime, default=func.now())
    # V5: ML 特征(14 维 JSON 字典, 为未来决策树模型训练准备)
    ml_features_json = Column(Text, nullable=True)
    # V5: 报价金额独立字段(避免反序列化 quote_json, 方便 SQL 聚合训练)
    total_amount = Column(Float, nullable=True)


class Lead(Base):
    """留资表"""
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    name = Column(String(20))
    phone = Column(String(11))
    district = Column(String(20))
    remark = Column(String(200))
    created_at = Column(DateTime, default=func.now())


# ===== 迁移: 老库加 password_hash / password_version 列 =====
def _migrate_users_add_password_hash():
    """V2: 兼容老库, ALTER TABLE 加 password_hash 列(若不存在)
    老用户 password_hash 保持 NULL,走验证码登录;新用户走密码登录
    """
    if DATABASE_URL.startswith("sqlite"):
        import sqlite3
        db_path = DATABASE_URL.replace("sqlite:///", "")
        if not os.path.exists(db_path):
            return
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(users)")
            cols = [row[1] for row in cur.fetchall()]
            if "password_hash" not in cols:
                cur.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(128)")
                conn.commit()
                logger.info("V2 migration: ALTER TABLE users ADD COLUMN password_hash")
            else:
                logger.info("V2 migration: password_hash already exists, skip")
            if "password_version" not in cols:
                cur.execute("ALTER TABLE users ADD COLUMN password_version INTEGER DEFAULT 0 NOT NULL")
                conn.commit()
                logger.info("P0-5 migration: ALTER TABLE users ADD COLUMN password_version")
            else:
                logger.info("P0-5 migration: password_version already exists, skip")
            conn.close()
        except Exception as e:
            logger.warning("V2 migration users.password_hash skipped: %s", e)
    # PostgreSQL 不需要手动 ALTER，SQLAlchemy 建表时自动处理


_migrate_users_add_password_hash()


# ============== 盲点 2: 个保法合规 - 用户同意日志表 ==============
class UserConsentLog(Base):
    """
    用户协议同意日志(个保法要求保留 3 年)

    字段:
      - id              主键
      - user_id         关联 users.id
      - mobile          手机号(冗余, 便于审计)
      - ip              客户端 IP
      - user_agent      浏览器 UA
      - policy_version  协议版本号
      - agreed_at       同意时间
    """
    __tablename__ = "user_consent_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    mobile = Column(String(11), nullable=False)
    ip = Column(String(64), nullable=True)
    user_agent = Column(String(512), nullable=True)
    policy_version = Column(String(16), nullable=False, default="v1.0")
    agreed_at = Column(DateTime, default=func.now(), nullable=False)


# ===== 启动时建表（容错：PostgreSQL 连不上就 fallback 到 SQLite）=====
def _create_tables():
    """建表，如果 PostgreSQL 连接失败则自动降级到 SQLite"""
    original_url = DATABASE_URL
    try:
        logger.info("Attempting to create tables on %s...", 
                    DATABASE_URL.replace(DATABASE_URL.split('@')[0] + '@', 'postgresql://***@') 
                    if DATABASE_URL.startswith('postgresql') else DATABASE_URL)
        Base.metadata.create_all(bind=engine)
        logger.info("Table creation successful.")
    except Exception as e:
        logger.error("PostgreSQL table creation failed: %s", str(e)[:200])
        # Fallback to SQLite
        sqlite_url = f"sqlite:///{os.path.join(os.path.dirname(__file__), '..', 'data', 'quote.db')}"
        logger.warning("Falling back to SQLite: %s", sqlite_url)
        global DATABASE_URL
        DATABASE_URL = sqlite_url
        # Recreate engine with SQLite
        from sqlalchemy import create_engine as _ce
        global engine, SessionLocal
        engine = _ce(sqlite_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        # Re-bind all models to new engine
        for model in Base._decl_class_registry.values():
            if hasattr(model, '__table__'):
                model.__table__.bind = engine
        try:
            Base.metadata.create_all(bind=engine)
            logger.info("SQLite table creation successful (fallback).")
        except Exception as e2:
            logger.critical("SQLite fallback also failed: %s", str(e2))
            raise

_create_tables()
