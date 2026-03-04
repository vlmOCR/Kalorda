# 导入asyncio以支持异步操作
import asyncio
import random

# 使用Python标准库的锁
import threading
import time
from datetime import datetime
from functools import wraps
from multiprocessing import Lock

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    FloatField,
    ForeignKeyField,
    IntegerField,
    ManyToManyField,
    Model,
    MySQLDatabase,
    OperationalError,
    SqliteDatabase,
    TextField,
)

from kalorda.config import config
from kalorda.constant import SysRole
from kalorda.utils.logger import logger
from kalorda.utils.security import get_password_hash


# 创建一个兼容的lock对象，提供RLock方法
class MockLockModule:
    @staticmethod
    def RLock():
        return threading.RLock()


lock = MockLockModule()


# 资源锁管理器，用于细粒度的并发控制
class ResourceLockManager:
    """资源锁管理器，为特定资源提供细粒度的锁控制"""

    def __init__(self):
        self.locks = {}
        self.global_lock = threading.RLock()

    def get_lock(self, resource_id):
        """获取特定资源的锁"""
        with self.global_lock:
            if resource_id not in self.locks:
                self.locks[resource_id] = threading.RLock()
            return self.locks[resource_id]


# 创建资源锁管理器实例
resource_locks = ResourceLockManager()


# 事务和重试装饰器
def with_db_transaction(use_transaction=True, retry_count=0, retry_delay=0.1, backoff_factor=2):
    """
    数据库事务装饰器，支持开启/关闭事务和重试机制

    参数:
        use_transaction: 是否使用事务
        retry_count: 重试次数，默认为0（不重试）
        retry_delay: 初始重试延迟时间（秒）
        backoff_factor: 重试延迟的指数退避因子

    使用示例:
        @with_db_transaction(use_transaction=True, retry_count=3)
        async def my_route_handler(request):
            # 数据库操作
            pass
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            attempt = 0
            last_exception = None

            while attempt <= retry_count:
                try:
                    db_manager.get_connection()

                    if use_transaction:
                        with database.atomic():
                            return await func(*args, **kwargs)
                    else:
                        return await func(*args, **kwargs)
                except OperationalError as e:
                    # 仅对操作错误进行重试，如锁争用等
                    last_exception = e
                    attempt += 1

                    if attempt > retry_count:
                        logger.error(
                            f"数据库操作失败，已达到最大重试次数 {retry_count}",
                            exc_info=True,
                        )
                        raise

                    # 计算退避延迟时间，添加随机抖动避免雪崩
                    delay = retry_delay * (backoff_factor ** (attempt - 1)) * (0.9 + 0.2 * random.random())
                    logger.warning(
                        f"数据库操作失败，将在 {delay:.2f} 秒后重试 (第 {attempt}/{retry_count} 次)",
                        exc_info=True,
                    )
                    await asyncio.sleep(delay)
                except Exception as e:
                    logger.error(f"数据库操作异常 {str(e)}", exc_info=True)
                    raise

            # 理论上不会执行到这里，因为达到最大重试次数后会抛出异常
            if last_exception:
                raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            attempt = 0
            last_exception = None

            while attempt <= retry_count:
                try:
                    db_manager.get_connection()

                    if use_transaction:
                        with database.atomic():
                            return func(*args, **kwargs)
                    else:
                        return func(*args, **kwargs)
                except OperationalError as e:
                    # 仅对操作错误进行重试，如锁争用等
                    last_exception = e
                    attempt += 1

                    if attempt > retry_count:
                        logger.error(
                            f"数据库操作失败，已达到最大重试次数 {retry_count}",
                            exc_info=True,
                        )
                        raise

                    # 计算退避延迟时间，添加随机抖动避免雪崩
                    delay = retry_delay * (backoff_factor ** (attempt - 1)) * (0.9 + 0.2 * random.random())
                    logger.warning(
                        f"数据库操作失败，将在 {delay:.2f} 秒后重试 (第 {attempt}/{retry_count} 次)",
                        exc_info=True,
                    )
                    time.sleep(delay)
                except Exception as e:
                    logger.error(f"数据库操作异常 {str(e)}", exc_info=True)
                    raise

            # 理论上不会执行到这里，因为达到最大重试次数后会抛出异常
            if last_exception:
                raise last_exception

        # 根据被装饰函数是否为协程函数，返回不同的包装器
        import inspect

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


# 创建数据库连接
if config.DB_TYPE == "sqlite":
    # 使用SqliteDatabase，配置为支持高并发写入
    database = SqliteDatabase(
        config.DB_PATH,
        pragmas={
            "foreign_keys": 1,
            "journal_mode": "wal",  # WAL模式提高并发性能
            "synchronous": "normal",  # 正常同步级别，平衡性能和安全性
            "cache_size": 64 * 1024,  # 64MB缓存
            "page_size": 4096,  # 4KB页面大小
            "temp_store": 2,  # 使用内存临时存储
            "mmap_size": 268435456,  # 256MB
        },
        check_same_thread=False,  # 允许在不同线程中使用同一连接
    )
elif config.DB_TYPE == "mysql":
    # 使用MySQLDatabase
    database = MySQLDatabase(
        config.DB_NAME,  # 数据库名称
        host=config.DB_HOST,  # 数据库主机
        port=config.DB_PORT,  # 数据库端口
        user=config.DB_USER,  # 数据库用户名
        password=config.DB_PASSWORD,  # 数据库密码
        charset="utf8mb4",  # 字符集
        autoconnect=False,  # 不自动连接
    )
else:
    # 默认使用SQLite
    database = SqliteDatabase(
        config.DB_PATH,
        pragmas={"foreign_keys": 1, "journal_mode": "wal", "synchronous": "normal"},
        check_same_thread=False,
    )


# 创建一个简单的连接管理器
class DatabaseManager:
    """数据库连接管理器，处理连接的获取和释放"""

    def __init__(self, db):
        self.db = db
        self._connection_count = 0
        self._lock = lock.RLock()

    def get_connection(self):
        """获取数据库连接"""
        with self._lock:
            if self.db.is_closed():
                self.db.connect()
                self._connection_count += 1
                logger.debug(f"数据库连接已打开，当前连接数: {self._connection_count}")
            return self.db

    def close_connection(self):
        """关闭数据库连接"""
        with self._lock:
            if not self.db.is_closed():
                self.db.close()
                if self._connection_count > 0:
                    self._connection_count -= 1
                logger.debug(f"数据库连接已关闭，当前连接数: {self._connection_count}")

    def execute(self, query, *args, **kwargs):
        """执行数据库查询"""
        self.get_connection()
        return query.execute(*args, **kwargs)

    def save(self, model, *args, **kwargs):
        """保存模型实例"""
        self.get_connection()
        return model.save(*args, **kwargs)


# 创建数据库管理器实例
db_manager = DatabaseManager(database)


# 基础模型类
class BaseDBModel(Model):
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)
    is_deleted = BooleanField(default=False)

    class Meta:
        database = database
        # 自动更新updated_at字段
        # 使用更明确的索引配置格式
        indexes = ((("is_deleted",), False),)
        # 表名自动转换为复数形式
        # 如果需要自定义表名，可以在这里设置

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        result = super().save(*args, **kwargs)
        return result

    @classmethod
    def select_active(cls, *args, **kwargs):
        # 直接返回查询构建器，不使用装饰器包装以保持链式调用能力
        query = cls.select(*args, **kwargs).where(cls.is_deleted == 0)
        return query


# 用户模型
class UserDB(BaseDBModel):
    username = CharField(unique=True, max_length=50)
    email = CharField(unique=True, max_length=100)
    password = CharField(max_length=255)  # 存储哈希后的密码
    role = CharField(max_length=20, default="admin")  # 数据库中role字段实际存储的是角色code(多个role_code用,隔开)
    status = CharField(max_length=20, default="active")  # active或inactive
    department = CharField(max_length=100, null=True)
    position = CharField(max_length=100, null=True)
    last_login = DateTimeField(null=True)
    login_count = IntegerField(default=0)
    password_updated_at = DateTimeField(null=True)
    avatar = CharField(max_length=255, null=True)

    class Meta:
        table_name = "users"
        # 修改索引配置，使用更明确的格式以避免解析错误
        indexes = (
            # 为role字段创建非唯一索引
            (("role",), False),
            # 为status字段创建非唯一索引
            (("status",), False),
        )


# 操作日志模型
class OperationLogDB(BaseDBModel):
    user = ForeignKeyField(UserDB, backref="logs", null=True)
    action = TextField()
    resource_type = CharField(max_length=50, null=True)
    resource_id = CharField(max_length=100, null=True)
    ip_address = CharField(max_length=50, null=True)
    device = TextField(null=True)
    details = TextField(null=True)

    class Meta:
        table_name = "operation_logs"
        # 修改索引配置，使用更明确的格式以避免解析错误
        indexes = (
            # 为resource_type字段创建非唯一索引
            (("resource_type",), False),
            # 为resource_id字段创建非唯一索引
            (("resource_id",), False),
        )


# 系统配置模型
class SystemConfigDB(BaseDBModel):
    config_key = CharField(max_length=100, unique=True)
    config_value = TextField()
    description = TextField(null=True)

    class Meta:
        table_name = "system_configs"
        # config_key字段已在定义时设置了unique=True，无需再在indexes中重复定义


# 数据集模型
class DatasetDB(BaseDBModel):
    name = CharField(max_length=50)
    description = TextField(null=True)
    model_type = IntegerField()  # 1=got_ocr, 2=dotsOCR, 3=dolphin, 4=deepseek_ocr, 5=paddleocr_vl, 6=hunyuan_ocr, 7=deepseek_ocr2, 8=firered_ocr
    pre_ocr_status = IntegerField(default=1)  # 1=未开始预处理, 2=等待中, 3=正在预处理中, 4=预处理完成, 5=预处理失败
    pre_ocr_error = TextField(null=True)  # 预处理错误信息
    total_images = IntegerField(default=0)  # 总图片数量
    train_images = IntegerField(default=0)  # 训练图片数量
    val_images = IntegerField(default=0)  # 验证图片数量
    total_tokens = IntegerField(default=0)  # 总tokens数量
    train_tokens = IntegerField(default=0)  # 训练tokens数量
    val_tokens = IntegerField(default=0)  # 验证tokens数量
    last_upload_time = DateTimeField(null=True)  # 最后上传时间
    created_by = ForeignKeyField(UserDB, backref="datasets", null=True)

    class Meta:
        table_name = "datasets"
        # 修改索引配置，使用更明确的格式以避免解析错误
        indexes = (
            # 为name字段创建非唯一索引
            (("name",), False),
            # 为model_type字段创建非唯一索引
            (("model_type",), False),
            # 为pre_ocr_status字段创建非唯一索引
            (("pre_ocr_status",), False),
        )


# 数据集图片信息模型
class DatasetImageDB(BaseDBModel):
    dataset = ForeignKeyField(DatasetDB, backref="images")
    file_path = TextField()  # 文件路径
    file_name = CharField(max_length=255)  # 文件名
    file_size = IntegerField()  # 文件大小(字节)
    width = IntegerField(null=True)  # 图片宽度
    height = IntegerField(null=True)  # 图片高度
    tokens = IntegerField(null=True)  # 图片tokens数量
    ocr_result = TextField(null=True)  # OCR识别结果（原始，不可修改）
    ocr_label = TextField(null=True)  # OCR标注结果（校对后，可修改）
    is_preocr_completed = BooleanField(default=False)  # 是否已预处理
    is_correct = BooleanField(null=True)  # 是否正确
    train_data_type = IntegerField(default=0)  # 训练数据类型 0=未指定, 1=训练数据, 2=验证数据
    processed_at = DateTimeField(null=True)  # 处理时间

    class Meta:
        table_name = "dataset_images"
        # 修改索引配置，使用更明确的格式以避免解析错误
        indexes = (
            # 为train_data_type字段创建非唯一索引
            (("train_data_type",), False),
            # 为is_preocr_completed字段创建非唯一索引
            (("is_preocr_completed",), False),
            # 为is_correct字段创建非唯一索引
            (("is_correct",), False),
        )


# 任务列表模型
class GPUTaskDB(BaseDBModel):
    name = CharField(max_length=100)  # 任务名称
    task_type = CharField(max_length=50)  # 任务类型
    handler = CharField(max_length=500)  # 任务处理器（方法名称）
    params = TextField(null=True)  # 任务参数（JSON序列化的字典）
    correlation_id = IntegerField(default=0)  # 关联ID
    status = IntegerField(default=1)  # 任务状态 (1=等待中, 2=执行中, 3=执行成功, 4=执行失败)
    can_retry = BooleanField(default=True)  # 出错是否可以重新执行
    run_times_limit = IntegerField(default=0)  # 最大执行次数
    run_times = IntegerField(default=0)  # 已执行次数
    last_run_pid = IntegerField(null=True)  # 最后执行的进程ID
    last_run_start_time = DateTimeField(null=True)  # 最后执行开始时间
    last_run_end_time = DateTimeField(null=True)  # 最后执行结束时间
    last_error_message = TextField(null=True)  # 错误信息

    class Meta:
        table_name = "gpu_tasks"
        # 修改索引配置，使用更明确的格式以避免解析错误
        indexes = (
            # 为status字段创建非唯一索引
            (("status",), False),
            # 为task_type字段创建非唯一索引
            (("task_type",), False),
        )


# 微调任务模型
class FineTuneTaskDB(BaseDBModel):
    name = CharField(max_length=100)  # 任务名称
    description = TextField(null=True)  # 任务描述
    target_model = IntegerField()  # 目标模型: 1=got_ocr, 2=dotsOCR, 3=dolphin, 4=deepseek_ocr, 5=paddleocr_vl, 6=hunyuan_ocr, 7=deepseek_ocr2, 8=firered_ocr
    # 暂时不设置through_model，稍后设置
    datasets = ManyToManyField(DatasetDB, backref="finetune_tasks")
    data_format = CharField(max_length=20, default="Alpaca")  # 数据格式: Alpaca, ShareGPT, ChatML, QueryResponse
    train_data_path = TextField(null=True)  # 训练数据jsonl文件路径
    val_data_path = TextField(null=True)  # 验证数据json文件路径
    total_runs = IntegerField(default=0)  # 总训练次数
    created_by = ForeignKeyField(UserDB, backref="finetune_tasks", null=True)
    data_last_combined = DateTimeField(null=True)  # 数据最后合成的时间
    data_combine_status = IntegerField(default=0)  # 数据合成状态: 0=未合成, 1=合成中, 2=合成完成, 3=合成失败
    train_data_count = IntegerField(default=0)  # 训练数据数量
    val_data_count = IntegerField(default=0)  # 验证数据数量
    latest_run_id = IntegerField(null=True)  # 最新训练实例ID
    latest_run_status = IntegerField(null=True)  # 最新训练状态
    latest_run_metrics = TextField(null=True)  # 最新训练指标(JSON格式)
    latest_model_path = TextField(null=True)  # 最新模型保存路径

    class Meta:
        table_name = "finetune_tasks"
        indexes = (
            # 为target_model字段创建非唯一索引
            (("target_model",), False),
        )


# 定义微调任务和数据集的多对多关系表
class FineTuneTaskDatasetThrough(Model):
    dataset = ForeignKeyField(DatasetDB, backref="finetune_tasks")
    finetune_task = ForeignKeyField(FineTuneTaskDB, backref="datasets")

    class Meta:
        table_name = "finetune_task_datasets"
        database = database


# 更新through_model
FineTuneTaskDB.datasets.through_model = FineTuneTaskDatasetThrough
finetune_task_dataset_through = FineTuneTaskDatasetThrough


# 训练实例模型
class TrainingRunDB(BaseDBModel):
    task = ForeignKeyField(FineTuneTaskDB, backref="training_runs")
    created_by = IntegerField(null=True)  # 创建者ID
    training_type = CharField(max_length=50)  # 训练类型: "lora", "full", "custom" 1
    custom_params = TextField(null=True)  # 自定义ms-swift训练参数
    num_epochs = IntegerField(default=3)  # 训练轮数 1
    learning_rate = FloatField(default=1e-5)  # 学习率 1
    target_modules = TextField(null=True)  # 目标模块(JSON字符串)
    lora_rank = IntegerField(default=8)  # LoRA秩
    lora_alpha = IntegerField(default=16)  # LoRA alpha
    batch_size = IntegerField(default=8)  # 批次大小 1
    logging_steps = IntegerField(default=1)  # 日志保存间隔步数
    eval_steps = IntegerField(default=1)  # 评估间隔步数
    gradient_accumulation_steps = IntegerField(default=1)  # 梯度累积步数 1
    warmup_ratio = FloatField(default=0.1)  # 预热比例 1
    weight_decay = FloatField(default=0.01)  # 权重衰减 1
    max_seq_len = IntegerField(default=8192)  # 最大序列长度 1
    max_grad_norm = FloatField(default=1.0)  # 最大梯度范数 1
    split_dataset_ratio = FloatField(default=0.1)  # 数据集划分比例 1
    lr_warmup_iters_ratio = FloatField(default=0.001)  # 学习率预热迭代比例 1
    do_early_stop = BooleanField(default=True)  # 是否启用早停
    early_stop_patience = IntegerField(default=3)  # 早停耐心值
    seed = IntegerField(null=True)  # 随机种子
    run_name = CharField(max_length=200)  # 运行名称
    model_output_path = TextField(null=True)  # 模型保存路径 1
    log_path = TextField(null=True)  # 日志路径
    status = IntegerField(default=0)  # 训练状态
    start_time = DateTimeField(null=True)  # 开始时间
    end_time = DateTimeField(null=True)  # 结束时间
    duration = FloatField(null=True)  # 持续时间(秒)
    train_data_count = IntegerField(default=0)  # 实际参与训练数据数量
    val_data_count = IntegerField(default=0)  # 实际参与验证数据数量
    error_message = TextField(null=True)  # 错误信息
    metrics = TextField(null=True)  # 训练指标(JSON字符串)
    best_model_path = TextField(null=True)  # 最佳模型路径
    model_code_suffix = CharField(max_length=50, null=True)  # 生成的模型编码后缀
    model_name = CharField(max_length=200, null=True)  # 微调后模型的名称

    class Meta:
        table_name = "training_runs"
        indexes = (
            # 为status字段创建非唯一索引
            (("status",), False),
        )


# zmq消息模型
class ZmqMessageDB(BaseDBModel):
    topic = CharField(max_length=500)  # 消息主题
    msg_id = CharField(max_length=100)  # 消息唯一uuid
    type = CharField(max_length=100)  # 消息分类
    data = TextField(null=True)  # 消息内容
    priority = IntegerField(default=0)  # 消息优先级

    class Meta:
        table_name = "zmq_messages"
        indexes = (
            # 为topic字段创建非唯一索引
            (("topic",), False),
            # 为type字段创建非唯一索引
            (("type",), False),
        )


class TestOCRFileDB(BaseDBModel):
    """用户上传的测试文件表"""

    original_filename = CharField(max_length=255)  # 原始文件名
    file_path = TextField()  # 实际保存的存储路径
    file_hash = CharField(max_length=100)  # 文件去重校对hash
    file_size = IntegerField()  # 文件大小(字节)
    images_info = TextField(null=True)  # 图片信息(JSON格式)，包含各图片uuid、存储路径和文件大小
    remark = CharField(max_length=100, null=True)  # 备注标签
    uploaded_by = ForeignKeyField(UserDB, backref="test_files", null=True)  # 上传用户id

    class Meta:
        table_name = "test_files"
        indexes = ((("file_hash",), False),)


class TestOCRResultDB(BaseDBModel):
    """测试文件转出来的图片的OCR识别结果表"""

    test_file = ForeignKeyField(TestOCRFileDB, backref="test_results")  # 关联文件id
    image_uuid = CharField(max_length=100)  # 图片uuid
    image_path = TextField()  # 图片的存储路径
    image_width = IntegerField()  # 图片宽度
    image_height = IntegerField()  # 图片高度
    image_size = IntegerField()  # 文件大小(字节)
    model_code = CharField(max_length=200)  # 识别模型的代号
    model_name = CharField(max_length=200)  # 识别模型的名称
    ocr_result = TextField(null=True)  # 识别结果
    duration = FloatField(null=True)  # 识别耗时(秒)
    token_usage = IntegerField(null=True)  # 消耗token
    status = IntegerField(default=1)  # TestOCRStatus状态: 1=未识别, 2=识别成功, 3=识别失败

    class Meta:
        table_name = "test_results"
        indexes = (
            (("image_uuid",), False),
            (("model_code",), False),
        )


def _ensure_training_run_columns_patch():
    # Temporary startup patch: add logging_steps/eval_steps if missing.
    try:
        db_manager.get_connection()
        table_name = TrainingRunDB._meta.table_name
        if not database.table_exists(table_name):
            return

        if config.DB_TYPE == "mysql":
            columns = set()
            cursor = database.execute_sql(
                "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s",
                (config.DB_NAME, table_name),
            )
            for row in cursor.fetchall():
                columns.add(row[0])

            if "logging_steps" not in columns:
                database.execute_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN logging_steps INT NOT NULL DEFAULT 1"
                )
                logger.info("Added column logging_steps to training_runs")
            if "eval_steps" not in columns:
                database.execute_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN eval_steps INT NOT NULL DEFAULT 1"
                )
                logger.info("Added column eval_steps to training_runs")
        else:
            columns = set()
            cursor = database.execute_sql(f"PRAGMA table_info('{table_name}')")
            for row in cursor.fetchall():
                columns.add(row[1])

            if "logging_steps" not in columns:
                database.execute_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN logging_steps INTEGER DEFAULT 1"
                )
                database.execute_sql(
                    f"UPDATE {table_name} SET logging_steps = 1 WHERE logging_steps IS NULL"
                )
                logger.info("Added column logging_steps to training_runs")
            if "eval_steps" not in columns:
                database.execute_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN eval_steps INTEGER DEFAULT 1"
                )
                database.execute_sql(
                    f"UPDATE {table_name} SET eval_steps = 1 WHERE eval_steps IS NULL"
                )
                logger.info("Added column eval_steps to training_runs")
    except Exception as e:
        logger.error(f"Failed to ensure training_runs columns: {str(e)}", exc_info=True)
        raise


lock = Lock()


# 更新初始化数据库函数
def init_database():
    """初始化数据库，创建所有表并添加默认数据"""
    # 延迟导入装饰器

    def _init_database():
        try:
            # 连接数据库
            db_manager.get_connection()

            # 创建所有表
            # 获取所有模型类
            models = [
                UserDB,
                OperationLogDB,
                SystemConfigDB,
                DatasetDB,
                DatasetImageDB,
                GPUTaskDB,
                FineTuneTaskDB,
                FineTuneTaskDatasetThrough,
                TrainingRunDB,
                ZmqMessageDB,
                TestOCRFileDB,
                TestOCRResultDB,
            ]

            # 首先创建所有表
            for model in models:
                # 使用db_manager确保连接已打开
                db_manager.get_connection()
                if not database.table_exists(model._meta.table_name):
                    database.create_tables([model])
                    logger.info(f"创建表: {model._meta.table_name}")
            _ensure_training_run_columns_patch()

            # 然后添加默认数据
            # 检查并创建默认管理员用户
            admin_password = get_password_hash(
                "admin123"
            )  # 加密后的值为"$2b$12$fdlq5b3ghySNcjkMCwoGv.UJB5lodjiXDzaGGpU0SvEbPcu8Tg/eq"
            admin_role = SysRole.admin["code"]  # 管理员角色代码role_code
            if not UserDB.select().where(UserDB.role.contains(admin_role)).exists():
                # 创建默认管理员用户
                admin_user = UserDB.create(
                    username="Admin",
                    email="admin@example.com",
                    password=admin_password,  # admin123 (加密后的值)
                    role=admin_role,
                    status="active",
                    created_at=datetime.now(),
                    updated_at=datetime.now(),
                )
                logger.info(f"创建默认管理员用户: {admin_user.username}，初始登录密码为: admin123")

            # 系统初始配置
            system_default_configs = [
                {
                    "key": "free_regist",
                    "value": "True",
                    "description": "是否开放外部注册",
                },
                {
                    "key": "smtp_host",
                    "value": "",
                    "description": "SMTP主机",
                },
                {"key": "smtp_port", "value": "", "description": "SMTP端口"},
                {
                    "key": "smtp_user",
                    "value": "",
                    "description": "SMTP发件人",
                },
                {
                    "key": "smtp_password",
                    "value": "",
                    "description": "SMTP发件人密码",
                },
                {
                    "key": "got_ocr_weights_dir",
                    "value": "",
                    "description": "GOT_OCR权重本地路径",
                },
                {
                    "key": "dotsocr_weights_dir",
                    "value": "",
                    "description": "DOTSOCR权重本地路径",
                },
                {
                    "key": "dolphin_weights_dir",
                    "value": "",
                    "description": "DOLPHIN权重本地路径",
                },
                {
                    "key": "deepseek_ocr_weights_dir",
                    "value": "",
                    "description": "DEEPSEEK_OCR权重本地路径",
                },
                {
                    "key": "paddleocr_vl_weights_dir",
                    "value": "",
                    "description": "PADDLEOCR_VL权重本地路径",
                },
                {
                    "key": "hunyuan_ocr_weights_dir",
                    "value": "",
                    "description": "HUNYUAN_OCR权重本地路径",
                },
                {
                    "key": "deepseek_ocr2_weights_dir",
                    "value": "",
                    "description": "DEEPSEEK_OCR2权重本地路径",
                },
                {
                    "key": "firered_ocr_weights_dir",
                    "value": "",
                    "description": "FIRERED_OCR权重本地路径",
                },
            ]

            # 检查并创建基本系统配置
            for system_config in system_default_configs:
                if not SystemConfigDB.select().where(SystemConfigDB.config_key == system_config["key"]).exists():
                    SystemConfigDB.create(
                        config_key=system_config["key"],
                        config_value=system_config["value"],
                        description=system_config["description"],
                    )

            logger.info("数据库初始化成功")
        except Exception as e:
            logger.error(f"数据库初始化失败: {str(e)}", exc_info=True)
            raise

    return _init_database()


def open_database():
    """打开数据库连接"""
    # 使用db_manager确保线程安全的连接管理
    return db_manager.get_connection()


# 关闭数据库连接
def close_database():
    # 使用db_manager确保线程安全的连接管理
    db_manager.close_connection()


# 导出数据库连接和模型
export = {
    "database": database,
    "db_manager": db_manager,
    "BaseModel": BaseDBModel,
    "User": UserDB,
    "OperationLog": OperationLogDB,
    "SystemConfig": SystemConfigDB,
    "Dataset": DatasetDB,
    "DatasetImage": DatasetImageDB,
    "Task": GPUTaskDB,
    "FineTuneTask": FineTuneTaskDB,
    "TrainingRun": TrainingRunDB,
    "ZmqMessage": ZmqMessageDB,
    "TestOCRFile": TestOCRFileDB,
    "TestOCRResult": TestOCRResultDB,
    "init_database": init_database,
    "close_database": close_database,
    "with_db_transaction": with_db_transaction,
    "resource_locks": resource_locks,
}
