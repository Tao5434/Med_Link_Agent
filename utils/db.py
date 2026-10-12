"""数据访问层（MySQL）。

设计要点
--------
* **只支持 MySQL**。早期版本提供 ``auto`` 模式「MySQL 连不上就静默降级 SQLite」，
  结果是在 MySQL 不可用时整个系统悄悄把数据写进本地文件，看起来一切正常、
  实际数据库里一条记录都没有。本版本去掉该行为：
  连不上 MySQL 直接抛 ``DatabaseError``，让问题在启动时就暴露。
* 占位符统一使用 pymysql 原生的 ``%s``。
* 表结构由 ``utils/schema.py`` 声明，与现有 ``med_link_agent`` 库完全对齐
  （``create_time`` / ``update_time`` / ``metadata`` JSON 等），
  启动时按 ``CREATE TABLE IF NOT EXISTS`` 补齐缺失的表，不会改动已有表。
"""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Any, Dict, Iterable, List, Optional, Sequence

import pymysql
from pymysql.cursors import DictCursor

from config.settings import settings
from utils import schema

logger = logging.getLogger(__name__)


class DatabaseError(RuntimeError):
    """数据访问异常，由上层统一转换为 HTTP 响应。"""


class Database:
    """MySQL 访问封装。"""

    def __init__(self) -> None:
        self.backend = "mysql"
        self._lock = threading.Lock()
        self._initialized = False
        self.server_version: Optional[str] = None

    # ------------------------------------------------------------------
    # 连接
    # ------------------------------------------------------------------
    def _connect(self, with_database: bool = True):
        kwargs: Dict[str, Any] = dict(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            charset="utf8mb4",
            cursorclass=DictCursor,
            autocommit=True,
            connect_timeout=5,
            read_timeout=60,
            write_timeout=60,
        )
        if with_database:
            kwargs["database"] = settings.MYSQL_DATABASE
        return pymysql.connect(**kwargs)

    @contextmanager
    def connection(self, autocommit: bool = True):
        try:
            conn = self._connect()
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(
                f"无法连接 MySQL（{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/"
                f"{settings.MYSQL_DATABASE}）：{exc}"
            ) from exc
        try:
            conn.autocommit(autocommit)
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self):
        """事务上下文：正常结束提交，异常回滚。"""
        with self.connection(autocommit=False) as conn:
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # ------------------------------------------------------------------
    # 初始化
    # ------------------------------------------------------------------
    def init(self) -> "Database":
        """建库、补齐缺失表、写入种子数据。"""
        if self._initialized:
            return self
        with self._lock:
            if self._initialized:
                return self

            # 1) 先不带库名连接，确保数据库存在
            try:
                conn = self._connect(with_database=False)
            except Exception as exc:  # noqa: BLE001
                raise DatabaseError(
                    f"无法连接 MySQL（{settings.MYSQL_HOST}:{settings.MYSQL_PORT}）：{exc}"
                ) from exc
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_DATABASE}` "
                        f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                    cur.execute("SELECT VERSION() AS v")
                    row = cur.fetchone()
                    self.server_version = row["v"] if row else None
            finally:
                conn.close()

            # 2) 建表
            with self.connection() as conn:
                with conn.cursor() as cur:
                    for stmt in schema.SCHEMA_STATEMENTS:
                        cur.execute(stmt)

            # 3) 种子数据
            self._seed()

            self._initialized = True
            logger.info(
                "MySQL 就绪：%s:%s/%s (server %s)",
                settings.MYSQL_HOST,
                settings.MYSQL_PORT,
                settings.MYSQL_DATABASE,
                self.server_version,
            )
        return self

    def _seed(self) -> None:
        """补齐科室字典、医生排班与默认账号（只在缺失时插入）。"""
        # 科室
        for code, name, order in schema.DEPARTMENT_SEEDS:
            self.execute(
                "INSERT INTO departments (department_code, department_name, sort_order, is_active) "
                "VALUES (%s, %s, %s, 1) "
                "ON DUPLICATE KEY UPDATE department_name = VALUES(department_name)",
                (code, name, order),
            )

        # 医生排班：仅当该科室还没有排班时插入，避免覆盖 booked_slots
        row = self.query_one("SELECT COUNT(*) AS c FROM doctor_schedules")
        if not row or not row["c"]:
            for dept_code, doctor, title, total in schema.DOCTOR_SCHEDULE_SEEDS:
                self.execute(
                    "INSERT INTO doctor_schedules "
                    "(department_code, doctor, doctor_title, total_slots, booked_slots, is_active) "
                    "VALUES (%s, %s, %s, %s, 0, 1)",
                    (dept_code, doctor, title, total),
                )

        # 默认账号 admin / 123456
        row = self.query_one(
            "SELECT id FROM `user` WHERE account = %s", (schema.DEFAULT_ACCOUNT,)
        )
        if not row:
            self.execute(
                "INSERT INTO `user` (account, password) VALUES (%s, %s)",
                (schema.DEFAULT_ACCOUNT, schema.DEFAULT_PASSWORD_MD5),
            )

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def query_all(self, sql: str, params: Sequence[Any] = ()) -> List[dict]:
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))
                    return [dict(r) for r in cur.fetchall()]
        except DatabaseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(f"查询失败：{exc}") from exc

    def query_one(self, sql: str, params: Sequence[Any] = ()) -> Optional[dict]:
        rows = self.query_all(sql, params)
        return rows[0] if rows else None

    def query_limit(
        self, sql: str, params: Sequence[Any] = (), page_curr: int = 1, page_size: int = 5
    ) -> dict:
        """分页查询，返回 {count, total, data}。"""
        page_curr = max(1, int(page_curr))
        page_size = max(1, int(page_size))
        data = self.query_all(sql + " LIMIT %s OFFSET %s", (*params, page_size, (page_curr - 1) * page_size))
        row = self.query_one("SELECT COUNT(*) AS total FROM (" + sql + ") AS t", params) or {}
        return {"count": int(row.get("total") or 0), "total": len(data), "data": data}

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """执行写入语句，返回自增主键（无自增时返回受影响行数）。"""
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, tuple(params))
                    return cur.lastrowid or cur.rowcount
        except DatabaseError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(f"写入失败：{exc}") from exc

    def insert_one(self, sql: str, params: Sequence[Any] = ()) -> int:
        return self.execute(sql, params)

    def execute_many(self, sql: str, params: Iterable[Sequence[Any]]) -> int:
        rows = [tuple(p) for p in params]
        if not rows:
            return 0
        try:
            with self.connection() as conn:
                with conn.cursor() as cur:
                    cur.executemany(sql, rows)
                    return cur.rowcount
        except Exception as exc:  # noqa: BLE001
            raise DatabaseError(f"批量写入失败：{exc}") from exc

    def update(self, sql: str, params: Sequence[Any] = ()) -> int:
        return self.execute(sql, params)

    def delete(self, sql: str, params: Sequence[Any] = ()) -> int:
        return self.execute(sql, params)

    # ------------------------------------------------------------------
    def health(self) -> dict:
        try:
            row = self.query_one("SELECT DATABASE() AS db, VERSION() AS v")
            return {
                "backend": "mysql",
                "database": (row or {}).get("db"),
                "server_version": (row or {}).get("v"),
                "host": settings.MYSQL_HOST,
                "port": settings.MYSQL_PORT,
                "connected": True,
            }
        except DatabaseError as exc:
            return {"backend": "mysql", "connected": False, "error": str(exc)}


db = Database()
