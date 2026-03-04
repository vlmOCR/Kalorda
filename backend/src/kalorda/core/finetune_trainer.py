import asyncio
import json
import os
import re
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from tokenize import Special

from kalorda.config import config
from kalorda.constant import OcrModel, TrainingStatus
from kalorda.core.package_installer import install_branch_package
from kalorda.core.system_env_info import get_virtual_env
from kalorda.database.database import (
    DatasetDB,
    DatasetImageDB,
    FineTuneTaskDB,
    SystemConfigDB,
    TrainingRunDB,
    ZmqMessageDB,
    db_manager,
    resource_locks,
    with_db_transaction,
)
from kalorda.models.finetune import TrainingRunResponse
from kalorda.utils.logger import logger
from kalorda.utils.zmq_pubsub import FINETUNE_TOPIC, datetime_converter, get_message_id


def get_finetune_task_directory(task_id: int) -> str:
    """
    获取指定微调任务的工作目录，每个任务有独立的目录
    """
    FINETUNE_WORK_DIR = getattr(config, "FINETUNE_WORK_DIR", "./finetune_works")
    if not os.path.exists(FINETUNE_WORK_DIR):
        os.makedirs(FINETUNE_WORK_DIR, exist_ok=True)

    task_base_dir = os.path.join(FINETUNE_WORK_DIR, str(task_id))
    task_data_dir = os.path.join(task_base_dir, "data")

    if not os.path.exists(task_base_dir):
        os.makedirs(task_base_dir, exist_ok=True)

    if not os.path.exists(task_data_dir):
        os.makedirs(task_data_dir, exist_ok=True)

    return task_base_dir, task_data_dir


@dataclass
class TrainingRunInfo:
    """
    训练运行配置数据类
    """

    task_id: int
    run_id: int
    user_id: int
    base_dir: str
    data_dir: str
    train_data_path: str
    val_data_path: str
    train_data_count: int
    val_data_count: int
    log_file: str


async def finetune_with_ms_swift(training_run_id: int, gpu_device: str):
    """
    使用MS-Swift微调模型
    """

    # 从数据库获取训练运行实例的配置
    training_run = TrainingRunDB.get_or_none(id=training_run_id)
    if not training_run:
        logger.error(f"训练运行实例 {training_run_id} 不存在")
        return

    finetune_task = FineTuneTaskDB.get_or_none(id=training_run.task.id)
    if not finetune_task:
        logger.error(f"训练运行实例 {training_run_id} 没有关联的微调任务")
        return

    # 获取微调任务的工作目录
    task_base_dir, task_data_dir = get_finetune_task_directory(finetune_task.id)
    # 日志保存文件
    log_file = os.path.join(task_base_dir, f"train_log_{training_run.id}.log")
    if os.path.exists(log_file):
        os.remove(log_file)

    # 训练的基本信息数据
    training_run_info = TrainingRunInfo(
        task_id=finetune_task.id,
        run_id=training_run.id,
        user_id=finetune_task.created_by.id,
        base_dir=task_base_dir,
        data_dir=task_data_dir,
        train_data_path=finetune_task.train_data_path,
        val_data_path=finetune_task.val_data_path,
        train_data_count=finetune_task.train_data_count,  # 训练的样本数量
        val_data_count=finetune_task.val_data_count,  # 验证的样本数量
        log_file=log_file,
    )

    # 更新训练运行状态为启动中 status = 3
    update_training_run_status(training_run_info, TrainingStatus.starting)
    # TODO: 数据更新任务

    # 构建MS-Swift训练命令
    command = []
    try:
        matched_model = OcrModel.get_all_models()[finetune_task.target_model - 1]
        model_code = matched_model.get("code")
        model_config = SystemConfigDB.get_or_none(config_key=f"{model_code}_weights_dir")
        model_weights_dir = model_config.config_value

        target_modules = "all-linear"
        if training_run.target_modules:
            modules = json.loads(training_run.target_modules.replace("'", '"'))
            if len(modules) > 0 and len(modules) < 7:
                target_modules = ""
                for module in modules:
                    target_modules += f" {module}" if len(target_modules) > 0 else module

        # TODO: 检查硬件、内存是否足够
        command_part1 = [
            "swift sft",
            # "--model_type",
            # "got_ocr2",
            "--model",
            model_weights_dir,
            # "--template",
            # "dots_ocr",
            # "--dataset",
            # finetune_task.train_data_path,
            # "--val_dataset",
            # finetune_task.val_data_path,
            "--output_dir",
            task_base_dir,
            "--logging_steps",
            str(training_run.logging_steps),
            "--eval_steps",
            str(training_run.eval_steps),
            "--save_total_limit",
            "1",
        ]

        # 自定义参数里追加的数据集（如果有）
        custom_append_dataset = ""
        custome_append_val_dataset = ""
        if training_run.training_type == "custom":
            # 手动设置的参数
            command_part2 = []
            custom_params = training_run.custom_params.replace("\\n", "").replace("\\", "").split("--")
            for custom_param in custom_params:
                if len(custom_param.strip()) > 0:
                    param = custom_param.strip()
                    lower_param = param.lower()  # 转换为小写
                    if (
                        lower_param.startswith("model")
                        # or lower_param.startswith("dataset")
                        # or lower_param.startswith("val_dataset")
                        or lower_param.startswith("output_dir")
                        or lower_param.startswith("logging_steps")
                        or lower_param.startswith("eval_steps")
                        or lower_param.startswith("save_total_limit")
                    ):
                        continue
                    if lower_param.startswith("dataset"):
                        # 不区分大小写替换掉dataset，只保留参数值
                        custom_append_dataset = re.sub(r"dataset", "", param, flags=re.IGNORECASE).strip()
                        continue
                    elif lower_param.startswith("val_dataset"):
                        # 不区分大小写替换掉val_dataset，只保留参数值
                        custome_append_val_dataset = re.sub(r"val_dataset", "", param, flags=re.IGNORECASE).strip()
                        continue

                    command_part2.append(f"--{param}")
            logger.info(f"自定义参数: {command_part2}")
            logger.info(f"自定义数据集: {custom_append_dataset} 验证集：{custome_append_val_dataset}")
        else:
            # 可视界面选的参数
            command_part2 = [
                "--train_type",
                "lora" if training_run.training_type == "lora" else "full",
                "--lora_rank",
                str(training_run.lora_rank),
                "--lora_alpha",
                str(training_run.lora_alpha),
                "--target_modules",
                target_modules,
                "--freeze_vit",
                "false",
                "--gradient_checkpointing",
                "true",  # 可节约显存
                "--max_epochs",
                str(training_run.num_epochs),
                "--num_train_epochs",
                str(training_run.num_epochs),
                "--learning_rate",
                str(training_run.learning_rate),
                "--per_device_train_batch_size",
                str(training_run.batch_size),
                "--gradient_accumulation_steps",
                str(training_run.gradient_accumulation_steps),
                "--warmup_ratio",
                str(training_run.warmup_ratio),
                "--weight_decay",
                str(training_run.weight_decay),
                "--max_grad_norm",
                str(training_run.max_grad_norm),
                # "--dataset_shuffle", # 是否打乱数据集
                # "true",
                "--lr_scheduler_type",
                "cosine",
                "--save_steps",
                "500",
                # "--deepspeed",
                # os.getcwd() + "/zero_config/zero3.json",
            ]

        # 后置确定训练数据集和验证集
        command_part1.append(f"--dataset {finetune_task.train_data_path} {custom_append_dataset}".strip())
        command_part1.append(f"--val_dataset {finetune_task.val_data_path} {custome_append_val_dataset}".strip())

        command = command_part1 + command_part2

    except Exception as e:
        # 更新训练运行状态为启动失败 status = 13
        update_training_run_status(training_run_info, TrainingStatus.failed1)
        logger.error(f"构建MS-Swift训练命令失败: {str(e)}", exc_info=True)
        return

    # 当前虚拟环境名称
    virtual_env_name = get_virtual_env().get("env_name").replace("/", "").replace(".", "").replace("-", "").strip()
    # 拷贝当前环境变量给环境变量打补丁
    env = os.environ.copy()

    # if gpu_device != "auto":
    #     env["CUDA_VISIBLE_DEVICES"] = gpu_device

    model_env_patch = True

    # 微调dotsOCR的特殊处理
    if matched_model == OcrModel.dotsocr:
        pass

    # 微调dolphin模型的特殊处理
    if matched_model == OcrModel.dolphin:
        # dolphin模型需要显示指定模型类型为qwen2_5_vl否则ms-swift会报错
        command.append("--model_type qwen2_5_vl")
        command.append("--template qwen2_5_vl")

    # 微调hunyuan_ocr模型的特殊处理(暂时transformers正式库尚未支持hunyuan_ocr模型使用临时库)
    if matched_model == OcrModel.hunyuan_ocr:
        install_path = f"{tempfile.gettempdir()}/hunyuan_ocr_finetune_{virtual_env_name}_env"
        # 微调hunyuan_ocr模型需要使用特殊版本4.57.1.dev0版本transformers库
        # 等transformers正式库支持hunyuan_ocr模型后，再撤掉该部分逻辑
        transformers_4_57_1_dev0 = config.BASE_DIR + "/vllm_infer/hunyuan_ocr/transformers-4.57.1.dev0-py3-none-any.whl"
        success = install_branch_package(
            transformers_4_57_1_dev0,
            install_path,
        )
        if not success:
            model_env_patch = False
        else:
            # 指定的transformers库植入环境变量
            env["PYTHONPATH"] = install_path + os.pathsep + env.get("PYTHONPATH", "")

    # 微调deepseek ocr模型的特殊处理，需要使用指定的4.46.3版本transformers库
    if matched_model == OcrModel.deepseek_ocr or matched_model == OcrModel.deepseek_ocr2:
        install_path = f"{tempfile.gettempdir()}/deepseek_ocr_finetune_{virtual_env_name}_env"
        success = install_branch_package("transformers==4.46.3", install_path)
        if not success:
            model_env_patch = False
        else:
            # 指定的transformers库植入环境变量
            env["PYTHONPATH"] = install_path + os.pathsep + env.get("PYTHONPATH", "")

    # 微调paddleocr模型的特殊处理，需要使用不能高于4.57.1版本transformers库
    if matched_model == OcrModel.paddleocr_vl:
        install_path = f"{tempfile.gettempdir()}/paddleocr_finetune_{virtual_env_name}_env"
        success = install_branch_package("transformers==4.57.1", install_path)
        if not success:
            model_env_patch = False
        else:
            # 指定的transformers库植入环境变量
            env["PYTHONPATH"] = install_path + os.pathsep + env.get("PYTHONPATH", "")
            command.append(
                "--max_length 16384"
            )  # max_tokens 最大长度限制 参见 /vllm_infer/paddleocr_vl/vlm_offline_infer.py
            # command.append("--truncation_strategy raise") # 默认就是raise报错提醒数据异常

    if model_env_patch is False:
        # 如果给训练环境变量打补丁失败 也等于 启动失败 status = 13
        update_training_run_status(training_run_info, TrainingStatus.failed1)
    else:
        # 保存训练命令到文件
        command_file = os.path.join(task_base_dir, f"train_command_{training_run.id}.sh")
        with open(command_file, "w") as f:
            f.write(" ".join(command))
        logger.info(f"MS-Swift 训练命令: {' '.join(command)}")

        # 启动子进程正式启动ms-swift执行微调命令
        await start_subprocess_shell(command, training_run_info, env)


async def start_subprocess_shell(command: list, training_run_info: TrainingRunInfo, env: dict):
    """
    运行异步子进程并捕获输出
    """
    exit_code = 0
    start_time = datetime.now()
    process = await asyncio.create_subprocess_shell(
        " ".join(command),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    # 更新训练运行状态为运行中 status = 4
    update_training_run_status(training_run_info, TrainingStatus.running)
    try:
        await asyncio.gather(
            asyncio.create_task(read_subprocess_log(process, "stdout", training_run_info)),
            asyncio.create_task(read_subprocess_log(process, "stderr", training_run_info)),
        )
        exit_code = await process.wait()
        logger.info(f"子进程退出码: {exit_code}")
    except Exception as e:
        process.kill()
        logger.error(f"Error waiting for process: {e}")
        exit_code = 1

    if exit_code == 0:
        # 更新训练运行状态为训练成功 status = 6
        update_training_run_status(training_run_info, TrainingStatus.completed)
    elif exit_code == 1:
        # 更新训练运行状态为运行失败 status = 14
        update_training_run_status(training_run_info, TrainingStatus.failed2)

    # 训练结束，推送训练结束实例信息
    train_end(training_run_info, start_time)

    return exit_code == 0


async def read_subprocess_log(
    process: asyncio.subprocess.Process,
    source: str,
    training_run_info: TrainingRunInfo,
):
    buffer = ""
    while True:
        try:
            if source == "stdout":
                chunk = await process.stdout.read(1024)
            if source == "stderr":
                chunk = await process.stderr.read(1024)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="ignore")
            # 处理完整的行
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if line:
                    save_subprocess_log(line, training_run_info)
        except Exception as e:
            logger.error(f"Error reading stderr: {e}")
            break
    # 处理缓冲区中剩余的内容
    if buffer:
        save_subprocess_log(buffer, training_run_info)


def save_subprocess_log(log: str, training_run_info: TrainingRunInfo):
    """
    实时保存从MS-Swift输出的日志
    """
    if len(log.strip()) == 0:
        return
    if "Train:" in log:
        return

    # 1、子线程日志打印在主线程控制台，不要改成logger.info打印
    print(log)

    # 2、从日志中提取关键信息：保存节点日志、模型保存路径
    if "The model will be saved and the training will be exited" in log:
        # 这时就更新训练运行状态为保存中 status = 5 保证前端UI体验最好
        update_training_run_status(training_run_info, TrainingStatus.saving)

    if "last_model_checkpoint:" in log:
        model_save_path = log.split("last_model_checkpoint:")[1].strip()
        if model_save_path and os.path.exists(model_save_path):
            TrainingRunDB.update(
                model_output_path=model_save_path,
            ).where(TrainingRunDB.id == training_run_info.run_id).execute()

    if "best_model_checkpoint:" in log:
        model_save_path = log.split("best_model_checkpoint:")[1].strip()
        if model_save_path and os.path.exists(model_save_path):
            TrainingRunDB.update(
                best_model_path=model_save_path,
            ).where(TrainingRunDB.id == training_run_info.run_id).execute()

    # 3、保存日志到zmq消息表（zmq转sse系统会实时推送）
    msg_id = get_message_id()
    ZmqMessageDB.create(
        topic=FINETUNE_TOPIC.format(training_run_info.task_id),  # zmq消息转sse消息的微调任务的主题
        type="trainlog",  # 消息类型：训练日志
        msg_id=msg_id,
        data=json.dumps(
            {
                "log": log,
                "task_id": training_run_info.task_id,
                "run_id": training_run_info.run_id,
            }
        ),
    )

    # 4、保存日志到本地文本文件（供前端一次性加载的那部分日志）
    with open(
        training_run_info.log_file,
        "a",
    ) as log_file:
        message = {
            "msg_id": msg_id,
            "data": {
                "log": log,
                "task_id": training_run_info.task_id,
                "run_id": training_run_info.run_id,
            },
        }
        log_file.write(f"{json.dumps(message)},")

    if log.startswith("{'loss':") or log.startswith("{'train_runtime':") or "Total optimization steps = " in log:
        pass


def update_training_run_status(training_run_info: TrainingRunInfo, status: TrainingStatus):
    """
    更新训练实例的运行状态
    """
    TrainingRunDB.update(
        status=status.get("value"),
    ).where(TrainingRunDB.id == training_run_info.run_id).execute()

    # 保存到zmq消息订阅表--》sse推送
    msg_id = get_message_id()
    ZmqMessageDB.create(
        topic=FINETUNE_TOPIC.format(training_run_info.task_id),  # zmq消息转sse消息的微调任务的主题
        type="trainstatus",  # 消息类型：更新后的训练状态
        msg_id=msg_id,
        data=json.dumps(
            {
                "status": status.get("value"),
                "task_id": training_run_info.task_id,
                "run_id": training_run_info.run_id,
            }
        ),
    )


# 训练结束收尾工作
def train_end(training_run_info: TrainingRunInfo, start_time: datetime):
    """
    训练结束，更新训练实例的运行状态
    """
    # 更新训练起止时间和实际运行时长、训练数据量、验证数据量
    end_time = datetime.now()
    duration = end_time - start_time
    logger.info(f"训练耗时: {duration.seconds} 秒")
    TrainingRunDB.update(
        start_time=start_time,
        end_time=end_time,
        duration=duration.seconds,
        train_data_count=training_run_info.train_data_count,
        val_data_count=training_run_info.val_data_count,
        model_code_suffix=str(uuid.uuid4())[:8],  # 每次训练完都会更新一个区分码
    ).where(TrainingRunDB.id == training_run_info.run_id).execute()
    training_run = TrainingRunDB.get_or_none(id=training_run_info.run_id)
    # 训练结束，推送训练结束实例信息
    if training_run:
        # 保存到zmq消息订阅表--》sse推送
        msg_id = get_message_id()
        ZmqMessageDB.create(
            topic=FINETUNE_TOPIC.format(training_run_info.task_id),  # zmq消息转sse消息的微调任务的主题
            type="trainend",  # 消息类型：训练结束消息
            msg_id=msg_id,
            data=json.dumps(
                TrainingRunResponse.model_validate(training_run).model_dump(),
                default=datetime_converter,
            ),
        )
