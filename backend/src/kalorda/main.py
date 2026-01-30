import argparse
import os
import platform
from contextlib import asynccontextmanager
from datetime import datetime

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# 挂载Vue3前端静态文件
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from kalorda.config import config

# 导入数据库相关
from kalorda.database.database import close_database, init_database, open_database

# 导入配置模块
from kalorda.package import description, name, version

# 导入路由模块
from kalorda.routes import api_router

# 导入并设置异常处理器
from kalorda.utils.exception_handler import setup_exception_handlers

# # 导入并设置i18n中间件
from kalorda.utils.i18n import setup_i18n_middleware

# 导入自定义日志工具
from kalorda.utils.logger import error, info, setup_logger
from kalorda.utils.zmq_pubsub import (
    DEFAULT_PORT,
    zmq_message_publisher,
    zmq_publish,
)

# Ensure plugins are registered in every new Python process.
import kalorda.vllm_infer.vllm_plugins  # noqa: F401

os.environ.setdefault("VLLM_IMPORTS", "kalorda.vllm_infer.vllm_plugins")

# 设置日志
logger = setup_logger("kalorda", log_level=config.LOG_LEVEL)

app_name = name()
app_version = version()
app_description = description()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """worker进程启动时执行"""
    try:
        # 打开数据库连接
        open_database()
        info(f"{app_name} worker进程启动成功，数据库已连接")
    except Exception as e:
        error(f"worker进程启动失败: {str(e)}", exc_info=True)

    yield

    """worker进程关闭时执行"""
    try:
        # 关闭数据库连接
        close_database()
        info(f"{app_name} worker进程已关闭，数据库连接已断开")
    except Exception as e:
        error(f"worker进程关闭失败: {str(e)}", exc_info=True)


# 创建FastAPI应用
app = FastAPI(
    title=app_name,
    description=app_description,
    version=app_version,
    docs_url=config.API_DOCS_URL,
    redoc_url=config.API_REDOC_URL,
    lifespan=lifespan,
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=config.CORS_METHODS,
    allow_headers=config.CORS_HEADERS,
)
# 注册i18n中间件
setup_i18n_middleware(app)
# 注册异常处理器
setup_exception_handlers(app)


# ------------------------------------集成前端页面访问------------------------------------
# 配置前端访问端点、挂载路径
web_visit_endpoint = "/web"
web_dist_dir = "web_dist"
frontend_dist_path = os.path.join(config.BASE_DIR, web_dist_dir)
include_frontend = os.path.exists(frontend_dist_path)


# 为单页应用配置catch-all路由，处理前端路由
@app.get(web_visit_endpoint + "/{path:path}", tags=["前端路由"], include_in_schema=False)
async def frontend_catch_all(path: str):
    # 尝试直接返回静态文件
    file_path = os.path.join(frontend_dist_path, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return FileResponse(file_path)
    # 如果文件不存在，返回index.html以支持前端路由
    index_path = os.path.join(frontend_dist_path, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"error": "Not found"}


# 挂载静态文件服务到/web路径，设置html=True以支持SPA
if include_frontend:
    app.mount(
        web_visit_endpoint,
        StaticFiles(directory=frontend_dist_path, html=True),
        name="frontend",
    )

    # 站点index - 首页
    @app.get("/", tags=["index"])
    @app.get("/index", tags=["index"])
    @app.get("/index.htm", tags=["index"])
    @app.get("/index.html", tags=["index"])
    async def index():
        # 跳转到/web路径
        return RedirectResponse(url=web_visit_endpoint)


# ------------------------------------集成前端访问结束------------------------------------

# 配置uploads文件目录
# logger.info(f"=================uploads文件目录: {config.UPLOAD_DIR}")
app.mount("/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")


# @app.get("/", tags=["index"])
@app.get("/api", tags=["api"])
async def root():
    return {
        "message": f"欢迎使用{app_name} API服务",
        "docs": config.API_DOCS_URL,
        "redoc": config.API_REDOC_URL,
    }


# api健康检查端点
@app.get("/api/health", tags=["health_check"])
async def health_check():
    return {
        "status": "ok",
        "time": datetime.now().isoformat(),
        "version": app_version,
    }


# 注册路由
app.include_router(api_router)

# 应用启动和关闭事件
# @app.on_event("startup")
# def startup_event():
#     """worker进程启动时执行"""
#     try:
#         # 打开数据库连接
#         open_database()
#         info(f"{app_name} worker进程启动成功，数据库已连接")
#     except Exception as e:
#         error(f"worker进程启动失败: {str(e)}", exc_info=True)


# @app.on_event("shutdown")
# async def shutdown_event():
#     """worker进程关闭时执行"""
#     try:
#         # 关闭数据库连接
#         close_database()
#         info(f"{app_name} worker进程已关闭，数据库连接已断开")
#     except Exception as e:
#         error(f"worker进程关闭失败: {str(e)}", exc_info=True)

cuda_visible_devices = ""


# 全局任务队列执行启动
def gpu_task_monitor():
    from threading import Thread

    from kalorda.core.gpu_task_monitor import task_monitor
    from kalorda.core.system_env_info import get_gpu_info

    gpu_info = get_gpu_info()
    available = gpu_info["available"]
    if not available:
        logger.error("当前系统GPU不可用，无法执行任务队列")
        return
    gpu_count = len(gpu_info["gpus"])
    gpu_devices = os.environ.get("GPU_DEVICES", "")

    if gpu_count > 0:
        # 如果未指定GPU设备，默认使用所有GPU
        if gpu_devices.strip() == "":
            gpu_devices = ",".join([str(i) for i in range(gpu_count)])

        gpu_devices_check = []
        gpu_devices_list = gpu_devices.split(",")
        for gpu_device in gpu_devices_list:
            gpu_device_index = int(gpu_device.strip())
            if gpu_device_index < gpu_count:
                gpu_devices_check.append(gpu_device_index)

        logger.info(
            f"GPU设备总数: {gpu_count}个；系统允许使用的GPU数量：{len(gpu_devices_check)}个，"
            f"设备索引：{','.join([str(i) for i in gpu_devices_check])}"
        )

        if len(gpu_devices_check) == 0:
            logger.error("未指定可用的有效GPU设备，系统将会无法执行GPU任务")
            return
        # 指定了几个GPU设备，就开几个任务执行器
        for i in gpu_devices_check:
            memory_total = gpu_info["gpus"][i]["memory_total"]
            memory_free = gpu_info["gpus"][i]["memory_free"]
            logger.info(f"GPU {i} 显存总量: {memory_total} GB，当前可用: {memory_free} GB")
            task_executor_thread = Thread(target=task_monitor, args=(str(i),))
            task_executor_thread.daemon = True
            task_executor_thread.start()


# 在worker进程启动前只在主进程执行一次
def application_run():
    # 初始化系统数据库
    init_database()
    # 启动GPU任务队列执行器
    gpu_task_monitor()
    # 打开zmq发布者套接字并执行日志提取推送
    zmq_publish(DEFAULT_PORT, zmq_message_publisher)
    # 检查前端目录是否存在，并只在主进程打印警告日志
    if not include_frontend:
        logger.warning(
            f'The front-end static file directory "{frontend_dist_path}" does not exist, '
            "only used as a back-end API service."
        )


def main():
    # 项目启动端口通过命令行获取
    parser = argparse.ArgumentParser(description="启动Kalorda系统")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="指定API服务主机，默认0.0.0.0",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8800,
        help="指定API服务端口，默认8800",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=2,
        help="指定worker进程数量，默认2",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="info",
        help="指定日志级别，默认info",
    )
    parser.add_argument(
        "--gpu-devices",
        type=str,
        default="",
        help="指定GPU设备索引，默认所有GPU",
    )

    args = parser.parse_args()
    host = args.host
    port = args.port
    workers = args.workers
    log_level = args.log_level

    gpu_devices = []
    gpu_devices_param = args.gpu_devices
    gpu_devices_param_split = gpu_devices_param.strip().split(",")
    for gpu_index in gpu_devices_param_split:
        if gpu_index.strip().isdigit():
            gpu_devices.append(gpu_index.strip())

    if len(gpu_devices) > 0:
        os.environ["GPU_DEVICES"] = ",".join(gpu_devices)

    if platform.system() != "Linux":
        logger.error("Only supported on Linux systems.")
        exit(0)

    # 根据环境配置选择启动参数
    if hasattr(config, "DEV_API_CONFIG") and getattr(config, "DEV_API_CONFIG", {}).get("enable_hot_reload", False):
        # 开发环境启用热重载
        reload = True
        reload_dirs = ["."]
        workers = 1
    else:
        # 生产环境不启用热重载
        reload = False
        reload_dirs = None
        workers = getattr(config, "PROD_PERFORMANCE_CONFIG", {}).get("workers", workers)

    # 在worker进程启动前只会在主进程全局执行一次
    application_run()

    # uvicorn 启动应用
    uvicorn.run(
        "kalorda.main:app",
        host=host,
        port=port,
        workers=workers,
        log_level=log_level,
        reload=reload,
        reload_dirs=reload_dirs,
        loop="asyncio",
    )


# 启动应用
if __name__ == "__main__":
    main()
