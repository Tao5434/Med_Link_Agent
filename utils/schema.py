"""数据库结构定义（与 med_link_agent 现有 MySQL 库保持一致）。

本模块只做两件事：
1. 声明业务表的建表语句（``CREATE TABLE IF NOT EXISTS``），用于全新环境初始化；
2. 声明科室字典与医生排班的种子数据，保证空库也能跑起来。

注意：字段名与类型严格对齐现有数据库，**不要**改写成 ``created_at`` /
``updated_at`` 之类的别名——现有库使用的是 ``create_time`` / ``update_time``。
"""

# ----------------------------------------------------------------------
# 建表语句
# ----------------------------------------------------------------------
SCHEMA_STATEMENTS = [
    # ---------------- 用户表 ----------------
    """
    CREATE TABLE IF NOT EXISTS `user` (
      `id` int NOT NULL AUTO_INCREMENT COMMENT '用户ID',
      `account` varchar(255) COLLATE utf8mb4_0900_bin NOT NULL COMMENT '用户账号',
      `password` varchar(255) COLLATE utf8mb4_0900_bin NOT NULL COMMENT '用户密码',
      `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin COMMENT='用户表'
    """,
    # ---------------- 登录令牌表（本项目新增） ----------------
    """
    CREATE TABLE IF NOT EXISTS `user_tokens` (
      `token` char(64) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '登录令牌',
      `user_id` int NOT NULL COMMENT '用户ID，关联 user.id',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '签发时间',
      `expire_time` datetime NOT NULL COMMENT '过期时间',
      PRIMARY KEY (`token`),
      KEY `idx_user_tokens_user` (`user_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='登录令牌表'
    """,
    # ---------------- 科室字典 ----------------
    """
    CREATE TABLE IF NOT EXISTS `departments` (
      `id` int unsigned NOT NULL AUTO_INCREMENT COMMENT '科室ID，字典主键',
      `department_code` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '科室编码',
      `department_name` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '科室名称',
      `sort_order` int NOT NULL DEFAULT '0' COMMENT '排序号，前端展示顺序',
      `is_active` tinyint NOT NULL DEFAULT '1' COMMENT '是否启用：1 启用，0 停用',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
      PRIMARY KEY (`id`),
      UNIQUE KEY `uk_department_name` (`department_name`),
      UNIQUE KEY `uk_department_code` (`department_code`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='科室字典表'
    """,
    # ---------------- 医生排班号源 ----------------
    """
    CREATE TABLE IF NOT EXISTS `doctor_schedules` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '排班ID',
      `department_code` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '科室编码',
      `doctor` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '医生姓名',
      `doctor_title` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '医生职称',
      `total_slots` int NOT NULL DEFAULT '1' COMMENT '总号源数',
      `booked_slots` int NOT NULL DEFAULT '0' COMMENT '已预约数',
      `is_active` tinyint NOT NULL DEFAULT '1' COMMENT '是否启用：1 启用，0 停用',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
      PRIMARY KEY (`id`),
      KEY `idx_department_schedule_date` (`department_code`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='医生排班号源表'
    """,
    # ---------------- 会话 ----------------
    """
    CREATE TABLE IF NOT EXISTS `sessions` (
      `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '会话ID，UUID 主键',
      `user_id` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '用户ID',
      `title` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '会话标题',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
      PRIMARY KEY (`id`),
      KEY `idx_user_id` (`user_id`),
      KEY `idx_updated_at` (`update_time`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话表'
    """,
    # ---------------- 会话消息 ----------------
    """
    CREATE TABLE IF NOT EXISTS `messages` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '消息ID',
      `session_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '会话ID',
      `role` varchar(10) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '角色：user / assistant',
      `content` text COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '消息内容',
      `metadata` json DEFAULT NULL COMMENT '元数据 JSON',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      PRIMARY KEY (`id`),
      KEY `idx_session_id_created` (`session_id`,`create_time`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话消息表'
    """,
    # ---------------- 问诊记录 ----------------
    """
    CREATE TABLE IF NOT EXISTS `encounters` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '记录ID',
      `session_id` char(36) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '会话ID',
      `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户ID',
      `scene` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '场景：triage / consultation / medication',
      `chief_complaint` text COLLATE utf8mb4_unicode_ci COMMENT '主诉',
      `risk_level` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '风险等级：low / medium / high',
      `department` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '推荐科室',
      `summary` text COLLATE utf8mb4_unicode_ci COMMENT '回答摘要',
      `metadata` json DEFAULT NULL COMMENT '元数据 JSON',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      PRIMARY KEY (`id`),
      KEY `idx_session_id` (`session_id`),
      KEY `idx_user_id_created` (`user_id`,`create_time`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='问诊记录表'
    """,
    # ---------------- 健康档案 ----------------
    """
    CREATE TABLE IF NOT EXISTS `health_profiles` (
      `id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'ID',
      `user_id` int DEFAULT NULL COMMENT '用户ID',
      `age` tinyint unsigned DEFAULT NULL COMMENT '年龄',
      `gender` varchar(10) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '性别：male / female / other',
      `chronic_diseases` json DEFAULT NULL COMMENT '既往病史',
      `allergy_history` json DEFAULT NULL COMMENT '过敏史',
      `medication_history` json DEFAULT NULL COMMENT '用药史',
      `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
      PRIMARY KEY (`id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='健康档案表'
    """,
    # ---------------- 预约 ----------------
    """
    CREATE TABLE IF NOT EXISTS `appointments` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '预约ID',
      `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户ID',
      `department` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '预约科室',
      `doctor` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '出诊医生',
      `doctor_title` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '医生职称',
      `visit_date` date NOT NULL COMMENT '就诊日期',
      `period` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '时段：morning / afternoon',
      `time_slot` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '时间片，如 08:30-11:30',
      `status` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL DEFAULT 'booked' COMMENT '状态：booked / cancelled',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      `update_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
      PRIMARY KEY (`id`),
      KEY `idx_user_id` (`user_id`),
      KEY `idx_department_date` (`department`,`visit_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='预约表'
    """,
    # ---------------- 报告主表 ----------------
    """
    CREATE TABLE IF NOT EXISTS `reports` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '报告ID',
      `report_no` varchar(40) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '报告编号',
      `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '用户ID',
      `report_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '报告名称',
      `report_type` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '类型：laboratory / examination',
      `hospital` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '医院名称',
      `department` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '开单科室',
      `report_date` date DEFAULT NULL COMMENT '报告日期',
      `summary` text COLLATE utf8mb4_unicode_ci COMMENT '报告摘要',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      PRIMARY KEY (`id`),
      UNIQUE KEY `uk_report_no` (`report_no`),
      KEY `idx_user_id_report_date` (`user_id`,`report_date`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告主表'
    """,
    # ---------------- 报告指标明细 ----------------
    """
    CREATE TABLE IF NOT EXISTS `report_items` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '明细ID',
      `report_id` bigint NOT NULL COMMENT '报告ID',
      `item_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '指标名称',
      `item_code` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '指标编码',
      `item_value` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '检测结果',
      `unit` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '单位',
      `reference_range` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '参考范围',
      `abnormal_flag` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '异常标记：normal / high / low / abnormal',
      `sort_order` int NOT NULL DEFAULT '0' COMMENT '排序号',
      `create_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
      PRIMARY KEY (`id`),
      KEY `idx_report_id` (`report_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告指标明细表'
    """,
    # ---------------- 报告附件（报告上传功能新增） ----------------
    """
    CREATE TABLE IF NOT EXISTS `report_files` (
      `id` bigint NOT NULL AUTO_INCREMENT COMMENT '附件ID',
      `report_id` bigint NOT NULL COMMENT '报告ID，关联 reports.id',
      `user_id` char(36) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '上传用户',
      `file_name` varchar(255) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '原始文件名',
      `file_path` varchar(500) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT '服务器存储相对路径',
      `file_size` bigint NOT NULL DEFAULT '0' COMMENT '文件大小（字节）',
      `content_type` varchar(100) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'MIME 类型',
      `parse_note` varchar(255) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '解析说明',
      `upload_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
      PRIMARY KEY (`id`),
      KEY `idx_report_files_report` (`report_id`),
      KEY `idx_report_files_user` (`user_id`)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='报告附件表'
    """,
]


# ----------------------------------------------------------------------
# 种子数据
# ----------------------------------------------------------------------
# 科室字典（16 个，含急诊科）
DEPARTMENT_SEEDS = [
    ("D001", "消化科", 1),
    ("D002", "妇产科", 2),
    ("D003", "皮肤科", 3),
    ("D004", "内分泌科", 4),
    ("D005", "神经内科", 5),
    ("D006", "骨科", 6),
    ("D007", "外科", 7),
    ("D008", "内科", 8),
    ("D009", "男科", 9),
    ("D010", "生殖医学科", 10),
    ("D011", "眼科", 11),
    ("D012", "肾脏病中心", 12),
    ("D013", "泌尿外科", 13),
    ("D014", "呼吸科", 14),
    ("D015", "药学门诊", 15),
    ("D016", "急诊科", 16),
]

# 医生排班号源（每个科室 2 名医生）
DOCTOR_SCHEDULE_SEEDS = [
    ("D001", "周杰", "主任医师", 10),
    ("D001", "吴敏", "副主任医师", 15),
    ("D002", "郑丽", "主任医师", 7),
    ("D002", "王芳", "副主任医师", 12),
    ("D003", "李强", "主任医师", 15),
    ("D003", "赵静", "副主任医师", 10),
    ("D004", "孙伟", "主任医师", 13),
    ("D004", "刘洋", "副主任医师", 15),
    ("D005", "陈晨", "主任医师", 16),
    ("D005", "杨光", "副主任医师", 9),
    ("D006", "黄磊", "主任医师", 15),
    ("D006", "徐娜", "副主任医师", 15),
    ("D007", "胡军", "主任医师", 12),
    ("D007", "朱婷", "副主任医师", 20),
    ("D008", "林峰", "主任医师", 20),
    ("D008", "何梅", "副主任医师", 15),
    ("D009", "郭涛", "主任医师", 15),
    ("D009", "马超", "副主任医师", 10),
    ("D010", "罗静", "主任医师", 10),
    ("D010", "高翔", "副主任医师", 15),
    ("D011", "梁明", "主任医师", 25),
    ("D011", "宋佳", "副主任医师", 16),
    ("D012", "唐斌", "主任医师", 15),
    ("D012", "冯雪", "副主任医师", 10),
    ("D013", "韩磊", "主任医师", 20),
    ("D013", "曹倩", "副主任医师", 15),
    ("D014", "彭勇", "主任医师", 13),
    ("D014", "董洁", "副主任医师", 12),
    ("D015", "袁华", "主任医师", 10),
    ("D015", "邓丽", "副主任医师", 5),
    ("D016", "周涛", "主任医师", 15),
    ("D016", "高鹏", "副主任医师", 20),
]

# 默认账号（密码为 MD5("123456")，与现有库中的 admin 记录一致）
DEFAULT_ACCOUNT = "admin"
DEFAULT_PASSWORD_MD5 = "e10adc3949ba59abbe56e057f20f883e"

# 各职称挂号费（appointments 表无 fee 字段，按职称派生）
TITLE_FEE = {
    "主任医师": 50,
    "副主任医师": 35,
    "主治医师": 20,
}
DEFAULT_FEE = 30
