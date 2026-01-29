import asyncio
import importlib
import inspect
import json
import multiprocessing
import time
from datetime import datetime
import traceback
import psutil

from kalorda.database.database import GPUTaskDB, database, db_manager, resource_locks
from kalorda.utils.logger import logger

# 纯GPU任务执行单元本身状态常量
# 不要与数据集预识别业务状态、预训练任务的业务状态混淆
# 数据集、微调任务 的业务状态是需要返前端用户信息，设计的状态个数一般会多一点
STATUS_PENDING = 1  # 等待执行中
STATUS_RUNNING = 2  # 执行中
STATUS_SUCCESS = 3  # 执行成功
STATUS_FAILED = 4  # 执行失败


def dynamically_load_handler(handler_path):
    """动态加载处理函数

    Args:
        handler_path: 处理器路径，格式为'module.submodule.function'

    Returns:
        function: 加载的函数对象

    Raises:
        ImportError: 模块导入失败
        AttributeError: 函数不存在
    """
    try:
        # 分割模块名和函数名
        if "." not in handler_path:
            raise ValueError(f"处理器路径格式不正确: {handler_path}，应为'module.function'格式")

        module_name, func_name = handler_path.rsplit(".", 1)
        logger.debug(f"正在加载模块: {module_name}，函数: {func_name}")

        # 使用importlib.import_module加载模块，支持多级嵌套
        module = importlib.import_module(module_name)

        # 获取函数
        handler_func = getattr(module, func_name)

        # 验证是否为可调用对象
        if not callable(handler_func):
            raise TypeError(f"{handler_path} 不是一个可调用的函数")

        logger.debug(f"成功加载处理器: {handler_path}")
        return handler_func

    except (ImportError, AttributeError, ValueError, TypeError) as e:
        traceback.print_exc()
        logger.error(f"动态加载处理器失败: {e}")
        raise


def task_monitor(gpu_device: str):
    sleep_time = 3  # 每个任务执行间隔时间3秒
    try:
        while True:
            time.sleep(sleep_time)
            # 在多线程环境下，确保数据库连接已建立
            try:
                db_manager.get_connection()
                if not database.table_exists(GPUTaskDB._meta.table_name):
                    continue
            except Exception as e:
                logger.error(f"数据库连接或表检查失败: {e}")
                continue
            lock = resource_locks.get_lock("task_query_lock")
            with lock:
                task: GPUTaskDB = (
                    GPUTaskDB.select_active()
                    .where(
                        (GPUTaskDB.status == STATUS_PENDING)
                        | (
                            (GPUTaskDB.status == STATUS_FAILED)
                            & (GPUTaskDB.can_retry == 1)
                            & (GPUTaskDB.run_times < GPUTaskDB.run_times_limit)
                        )
                    )
                    .order_by(GPUTaskDB.id.asc())
                    .limit(1)
                    .first()
                )
            if not task:
                continue
            try:
                # 更新任务状态为执行中
                _update_gpu_task(task, STATUS_RUNNING)

                # 动态加载处理函数
                handler_func = dynamically_load_handler(task.handler)
                # 解析参数
                params = json.loads(task.params.replace("'", '"')) if task.params else {}
                params["gpu_device"] = gpu_device

                if inspect.iscoroutinefunction(handler_func):
                    # 创建一个同步包装函数来运行异步函数
                    def run_async_handler():
                        asyncio.run(handler_func(**params))

                    p = multiprocessing.Process(target=run_async_handler)
                else:
                    p = multiprocessing.Process(target=handler_func, kwargs=params)
                p.start()
                # 记录子进程ID
                _update_gpu_task(task, pid=p.pid)

                p.join()
                if p.exitcode == 0:
                    _update_gpu_task(task, STATUS_SUCCESS, f"子进程执行成功，退出码: {p.exitcode}")
                else:
                    _update_gpu_task(
                        task,
                        STATUS_FAILED,
                        f"子进程执行失败，退出码: {p.exitcode}",
                    )
            except Exception as e:
                logger.error(f"任务执行失败: {e}")
                _update_gpu_task(
                    task,
                    STATUS_FAILED,
                    str(e),
                )
    except KeyboardInterrupt:
        logger.info("GPU任务队列服务器收到中断信号")
    finally:
        logger.info("任务执行器已退出")


def _update_gpu_task(
    task: GPUTaskDB,
    status: int = None,
    message: str = None,
    pid: int = None,
):
    """更新GPU任务状态

    Args:
        task: GPUTaskDB实例
        status: 任务状态
        message: 任务执行信息
    """
    if status is not None:
        task.status = status
    if status == STATUS_RUNNING:
        task.last_run_start_time = datetime.now()
    if status == STATUS_SUCCESS:
        task.run_times += 1
        task.last_run_end_time = datetime.now()
    if status == STATUS_FAILED:
        task.run_times += 1
        task.last_run_end_time = datetime.now()
    if message:
        task.last_error_message = message
    if pid is not None:
        task.last_run_pid = pid
    task.save()


def add_gpu_task(
    name: str,
    task_type: str,  # 预识别=preocr, 微调训练=finetune
    handler: str,
    params: dict,
    correlation_id: int,
    can_retry: bool = True,
    run_times_limit: int = 3,
):
    """添加GPU任务到队列

    Args:
        name: 任务名称
        task_type: 任务类型
        handler: 处理函数路径
        params: 任务参数
        correlation_id: 关联ID
        can_retry: 是否可重试
        run_times_limit: 最大重试次数
    """
    gpu_task = GPUTaskDB.create(
        name=name,
        task_type=task_type,
        handler=handler,
        params=json.dumps(params),
        correlation_id=correlation_id,
        can_retry=can_retry,
        run_times_limit=run_times_limit,
    )
    gpu_task.save()


def gpu_task_queue_count():
    """检查当前是否没有运行中（包括等待中）的GPU任务

    Returns:
        int: 执行+等待中的任务数量
    """
    count = (
        GPUTaskDB.select_active()
        .where((GPUTaskDB.status == STATUS_PENDING) | (GPUTaskDB.status == STATUS_RUNNING))
        .count()
    )
    return count


# 获取任务排队等待的位置
def get_waiting_rank(gpu_task_type: str, correlation_id: int):
    gpu_tasks = (
        GPUTaskDB.select_active()
        .select(GPUTaskDB.id, GPUTaskDB.params)
        .where(
            (GPUTaskDB.status == STATUS_PENDING)
            | (
                (GPUTaskDB.status == STATUS_FAILED)
                & (GPUTaskDB.can_retry == 1)
                & (GPUTaskDB.run_times < GPUTaskDB.run_times_limit)
            )
        )
    )

    waiting_rank = 0
    waiting_rank_total = len(gpu_tasks)
    for gpu_task in gpu_tasks:
        if gpu_task.task_type == gpu_task_type and gpu_task.correlation_id == correlation_id:
            break
        waiting_rank += 1
    return waiting_rank, waiting_rank_total


def del_gpu_task(gpu_task_type: str, correlation_id: int):
    """删除指定类型和关联ID的GPU任务

    Args:
        task_type: 任务类型
        correlation_id: 关联ID
    """
    gpu_task_list = GPUTaskDB.select_active().where(
        (GPUTaskDB.task_type == gpu_task_type) & (GPUTaskDB.correlation_id == correlation_id)
    )
    for gpu_task in gpu_task_list:
        if gpu_task.status == STATUS_RUNNING:
            stop_gpu_task_process(gpu_task.id)
        gpu_task.is_deleted = True
        gpu_task.save()


def stop_gpu_task_process(task_id: int):
    """停止指定ID的GPU任务

    Args:
        task_id: GPU任务ID
    """
    try:
        task: GPUTaskDB = GPUTaskDB.select_active().where(GPUTaskDB.id == task_id).first()
        if task and task.status == STATUS_RUNNING:
            pid = task.last_run_pid
            if pid:
                try:
                    # 根据进程ID获取进程对象
                    p = psutil.Process(pid)
                    # 终止所有子进程
                    for child in p.children(recursive=True):
                        child.terminate()
                    p.terminate()
                    p.wait(timeout=3)
                    logger.info(f"任务 {task.id} 手动终止 pid: {pid}")
                except Exception as e:
                    p.kill()
                    logger.error(f"任务 {task.id} 中止过程中异常： {str(e)}")
    except Exception as e:
        logger.error(f"任务 {task_id} 停止异常： {str(e)}")
