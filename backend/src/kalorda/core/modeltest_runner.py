import asyncio
import gc
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import torch
import traceback

from kalorda.config import config
from kalorda.constant import OcrModel, TestOCRStatus
from kalorda.database.database import (
    DatasetDB,
    SystemConfigDB,
    TestOCRFileDB,
    TestOCRResultDB,
    TrainingRunDB,
    ZmqMessageDB,
    db_manager,
    resource_locks,
    with_db_transaction,
)
from kalorda.utils.logger import logger
from kalorda.utils.zmq_pubsub import MODELTEST_TOPIC, datetime_converter, get_message_id
from kalorda.vllm_infer.vllm_engine import get_vllm_engine


def parse_model_dir(model: dict):
    model_code, training_type, model_name = (
        model.get("model_code"),
        model.get("training_type"),  # base\lora\full
        model.get("model_name"),
    )
    logger.info(f"parse_model_dir 模型 {model_code} 训练类型 {training_type} 模型名称 {model_name}")

    base_model_code = ""
    base_model_weights_dir = ""
    model_weights_dir = ""
    lora_weights_dir = None

    # 基础模型的权重
    if training_type == "base":
        base_model_code = model_code
        base_model_weights_dir = SystemConfigDB.get_or_none(
            SystemConfigDB.config_key == f"{base_model_code}_weights_dir"
        ).config_value
        model_weights_dir = base_model_weights_dir
        # lora_weights_dir = None

    # lora微调的基础模型权重+lora权重
    if training_type == "lora":
        #  model_code = f"{base_mode_code}:{training_run_id}:{model_code_suffix}"
        base_model_code = model_code.split(":")[0]
        training_run_id = model_code.split(":")[1]
        base_model_weights_dir = SystemConfigDB.get_or_none(
            SystemConfigDB.config_key == f"{base_model_code}_weights_dir"
        ).config_value
        model_weights_dir = base_model_weights_dir
        lora_weights_dir = TrainingRunDB.get_or_none(TrainingRunDB.id == training_run_id).model_output_path
        logger.info(f"模型 {model_code} lora_weights_dir: {lora_weights_dir}")

    # 全量微调的模型权重
    if training_type == "full":
        #  model_code = f"{base_mode_code}:{training_run_id}:{model_code_suffix}"
        base_model_code = model_code.split(":")[0]
        training_run_id = model_code.split(":")[1]
        model_weights_dir = TrainingRunDB.get_or_none(TrainingRunDB.id == training_run_id).model_output_path

    return (base_model_code, model_weights_dir, lora_weights_dir)


async def vllm_engine_shutdown(engine: Any):
    if engine:
        try:
            del engine
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
            gc.collect()
            logger.info("VLLM 引擎成功退出")
        except Exception as e:
            logger.error(f"VLLM 引擎终止失败: {str(e)}")


async def modeltest_with_vllm(user_id: int, file_id_list: list[int], model_list: list[dict], gpu_device: str):
    for model in model_list:
        base_model_code, model_weights_dir, lora_weights_dir = parse_model_dir(model)
        time1 = time.time()
        if gpu_device != "auto":
            os.environ["CUDA_VISIBLE_DEVICES"] = gpu_device
        vllm_engine = None
        try:
            vllm_engine = get_vllm_engine(base_model_code, model_weights_dir, lora_weights_dir)
        except Exception as e:
            logger.error(f"获取模型 {base_model_code} 失败: {str(e)}")

        time2 = time.time()
        logger.info(f"模型 {base_model_code} 加载耗时: {time2 - time1} 秒")

        model_code = model.get("model_code")
        db_images = (
            TestOCRResultDB.select_active()
            .select(
                TestOCRResultDB.id,
                TestOCRResultDB.test_file_id,
                TestOCRResultDB.image_uuid,
                TestOCRResultDB.image_path,
            )
            .where(TestOCRResultDB.test_file_id.in_(file_id_list))
            .where(TestOCRResultDB.model_code == model_code)
            .where(TestOCRResultDB.status == TestOCRStatus.not_start["value"])
        )

        # 将查询结果转换为列表解决数据库死锁问题
        images = list(db_images)

        for image in images:
            test_file_id = image.test_file_id
            image_uuid = image.image_uuid
            image_file = image.image_path
            time1 = time.time()
            try:
                logger.info(f"模型测试 {model_code} 识别图片 {image_file} 开始")
                ocr_result, tokens_count = vllm_engine.generate(
                    f"{config.BASE_DIR}{image_file}"
                )  # 相对路径转换为绝对路径
                status = TestOCRStatus.completed["value"]
            except Exception as e:
                # ocr_result = (
                #     f"[Error] 识别失败: {str(e)}"
                #     if vllm_engine is not None
                #     else f"[Error] vllm engine 加载 {model_code} 模型失败"
                # )
                traceback.print_exc()
                ocr_result = ""
                tokens_count = 0
                status = TestOCRStatus.failed["value"]
                logger.error(f"模型 {model_code} 识别图片 {image_uuid} 失败: {str(e)}")
            time2 = time.time()

            # 1、 保存识别结果到数据库
            TestOCRResultDB.update(
                ocr_result=ocr_result,
                duration=time2 - time1,
                token_usage=tokens_count,
                status=status,
            ).where(TestOCRResultDB.id == image.id).execute()

            # 2、 发送zmq消息，通知前端识别完成
            msg_id = get_message_id()
            ZmqMessageDB.create(
                topic=MODELTEST_TOPIC.format(user_id),  # zmq消息转sse消息的微调任务的主题
                type="modeltest",  # 消息类型：模型测试消息
                msg_id=msg_id,
                data=json.dumps(
                    {
                        "file_id": test_file_id,
                        "model_code": model_code,
                        "image_uuid": image_uuid,
                        "status": status,
                    },
                    default=datetime_converter,
                ),
            )

        # 最后主动关闭vllm引擎
        await vllm_engine_shutdown(vllm_engine)
