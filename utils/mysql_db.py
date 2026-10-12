"""MySQL 通用访问助手（历史模块，保留兼容）。

注意：项目主数据访问层已统一为 ``utils/db.py``（支持 MySQL / SQLite 自动降级），
业务代码请使用 ``from utils.db import db``。本模块仅作为独立 MySQL 客户端保留。
"""
import pymysql
from pymysql.cursors import DictCursor
from dotenv import load_dotenv
import os


class MySQLDB:
    _instance = None
    _is_init = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, host, user, password, database, port=3306, charset="utf8mb4", autocommit=False):
        if not MySQLDB._is_init:
            self.host = host
            self.user = user
            self.password = password
            self.database = database
            self.port = port
            self.charset = charset
            self.autocommit = autocommit
            self.cursor = None
            self.conn = None
            MySQLDB._is_init = True

    def _connect(self):
        try:
            self.conn = pymysql.connect(
                host=self.host,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                charset=self.charset,
                autocommit=self.autocommit
            )
            self.cursor = self.conn.cursor(DictCursor)
        except Exception as e:
            self.conn = None
            self.cursor = None
            raise e

    def _close(self):
        """
        关闭数据库连接
        :return:
        """
        if self.cursor:
            self.cursor.close()
        if self.conn:
            self.conn.close()

    def query_one(self, sql: str, params: tuple = ()):
        """
        查询一条数据
        :param sql: sql语句
        :param params: sql参数
        :return: 查询结果
        """
        print(sql)
        print(params)
        try:
            self._connect()
            self.cursor.execute(sql, params)
            data = self.cursor.fetchone()
            return data
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()

    def query_all(self, sql: str, params: tuple = ()):
        """
        查询所有数据
        :param sql: sql语句
        :param params: sql参数
        :return: 查询结果
        """
        try:
            self._connect()
            self.cursor.execute(sql, params)
            data = self.cursor.fetchall()
            return data
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()

    def query_many(self, sql: str, params: tuple = ()):
        """
        查询指定数量的数据
        :param sql: sql语句
        :param params: sql参数
        :return: 获取指定数量的数据
        """
        try:
            self._connect()
            self.cursor.execute(sql, params)
            data = self.cursor.fetchmany()
            return data
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()

    def query_limit(self, sql: str, params: tuple = (), page_curr: int = 1, page_size: int = 5):
        """
        分页查询
        :param sql: sql语句
        :param params: sql参数
        :param page_curr: 当前页码
        :param page_size: 每页数量
        :return: 总条数，当前页条数，当前页数据
        """
        try:
            self._connect()
            limit_sql = sql + " LIMIT %s, %s"
            index = (page_curr - 1) * page_size
            limit_params = (*params, index, page_size)
            self.cursor.execute(limit_sql, limit_params)
            data = self.cursor.fetchall()

            # 获取总条数
            count_sql = "SELECT count(*) AS total FROM (" + sql + " ) AS t"
            self.cursor.execute(count_sql, params)
            count_result = self.cursor.fetchone()
            count = count_result.get('total') if count_result else 0
            total = len(data)
            return {
                "count": count,
                "total": total,
                "data": data
            }   # 返回总条数，当前页条数，当前页数据
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()

    def insert_one(self, sql: str, params: tuple | list = ()):
        """
        插入一条数据
        :param sql: sql语句
        :param params: sql参数
        :return: 插入的id
        """
        try:
            self._connect()
            self.cursor.execute(sql, params)
            self.conn.commit()
            return self.cursor.lastrowid   # 返回插入的id(最后一个id)
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()

    def insert_many(self, sql: str, params: tuple = ()):
        """
        插入多条数据
        :param sql: sql语句
        :param params: sql参数
        :return: 插入的最后一个id
        """
        try:
            self._connect()
            self.cursor.executemany(sql, params)
            self.conn.commit()
            return self.cursor.lastrowid   # 获取插入的id
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()

    def update_one(self, sql: str, params: tuple | list = ()):
        """
        更新一条数据
        :param sql: sql语句
        :param params: sql参数
        :return: 获取受影响行数
        """
        try:
            self._connect()
            self.cursor.execute(sql, params)
            self.conn.commit()
            return self.cursor.rowcount   # 获取受影响行数
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()

    def update_many(self, sql: str, params: tuple = ()):
        """
        更新多条数据
        :param sql: sql语句
        :param params: sql参数
        :return: 获取受影响行数
        """
        try:
            self._connect()
            self.cursor.executemany(sql, params)
            self.conn.commit()
            return self.cursor.rowcount   # 获取受影响行数
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()

    def delete_one(self, sql: str, params: tuple = ()):
        """
        删除一条数据
        :param sql: sql语句
        :param params: sql参数
        :return: 获取受影响行数
        """
        try:
            self._connect()
            self.cursor.execute(sql, params)
            self.conn.commit()
            return self.cursor.rowcount   # 获取受影响行数
        except Exception as e:
            self.conn.rollback()
            raise e
        finally:
            self._close()


load_dotenv()
db = MySQLDB(host=os.getenv("MYSQL_HOST"),
             user=os.getenv("MYSQL_USER"),
             password=os.getenv("MYSQL_PASSWORD"),
             database=os.getenv("MYSQL_DATABASE"))


