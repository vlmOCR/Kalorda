import os
import time
from datetime import datetime

from pdf2image import convert_from_path
from PIL import Image

from kalorda.config import config
from kalorda.constant import OcrModel, PreOCRStatus
from kalorda.database.database import (
    DatasetDB,
    DatasetImageDB,
    SystemConfigDB,
    UserDB,
    db_manager,
    resource_locks,
    with_db_transaction,
)
from kalorda.utils.logger import logger
from kalorda.utils.upload_file import get_dataset_directory
from kalorda.vllm_infer.vllm_engine import get_vllm_engine


def _convert_if_pdf_to_image(dataset_id: int):
    """
    将数据集中所有PDF文件（如果有）转换为图片
    """
    try:
        dataset_dir = get_dataset_directory(dataset_id)

        # 如果有pdf开始转图：获取数据集目录中的所有PDF文件
        pdf_files = DatasetImageDB.select_active().where(
            DatasetImageDB.dataset == dataset_id,
            DatasetImageDB.width == 0,  # 宽度为0的文件为非图片文件
            DatasetImageDB.height == 0,
        )

        # 处理每个PDF文件
        for pdf_file in pdf_files:
            # 获取原始文件名
            pdf_file_path = f"{config.BASE_DIR}{pdf_file.file_path}"
            pdf_filename = os.path.basename(pdf_file_path)

            # 检查文件是否存在
            if not os.path.exists(pdf_file_path):
                logger.warning(f"PDF文件不存在: {pdf_file_path}")
                continue

            # 转换PDF为图片
            try:
                pdf_pages = convert_from_path(pdf_file_path, dpi=200, fmt="jpg", size=(2048, None))
            except Exception as e:
                logger.error(f"转换PDF文件 {pdf_file_path} 失败: {str(e)}")
                continue

            # 为每一页创建新的图片记录
            for i, page in enumerate(pdf_pages):
                # 生成唯一的文件名
                img_filename = f"{os.path.splitext(pdf_filename)[0]}_page_{i + 1}.jpg"
                img_path = os.path.join(dataset_dir, img_filename)
                # 保存图片
                page.save(img_path, "JPEG")
                # 获取图片信息
                img = Image.open(img_path)
                width, height = img.size
                img.close()

                # 创建新的图片记录
                DatasetImageDB.create(
                    dataset=dataset_id,
                    file_path=img_path.replace(config.BASE_DIR, ""),  # 数据库存储相对路径
                    file_name=img_filename,
                    file_size=os.path.getsize(img_path),
                    width=width,
                    height=height,
                    tokens=0,
                    is_preocr_completed=False,
                    train_data_type=0,
                )

        # 删除原始PDF文件
        for pdf_file in pdf_files:
            try:
                pdf_file_path = f"{config.BASE_DIR}{pdf_file.file_path}"
                if os.path.exists(pdf_file_path):
                    os.remove(pdf_file_path)
                # 数据库记录清理
                DatasetImageDB.delete().where(DatasetImageDB.id == pdf_file.id).execute()
            except Exception as e:
                logger.warning(f"删除PDF文件 {pdf_file.file_path} 失败: {str(e)}")

    except Exception as e:
        logger.error(f"集中处理PDF文件失败: {str(e)}", exc_info=True)
        raise


def _get_dataset_images(dataset_id: int, offset: int, limit: int):
    dataset = DatasetDB.get_or_none(DatasetDB.id == dataset_id)
    if not dataset:
        return None

    images = (
        DatasetImageDB.select_active()
        .where(
            DatasetImageDB.dataset == dataset_id,
            DatasetImageDB.is_preocr_completed == 0,
        )
        .offset(offset)
        .limit(limit)
    )
    return images


# 主方法：调用vlm模型进行批量预识别
def preocr_with_vlm_model(dataset_id: int, gpu_device: str):
    """
    调用OCR模型进行识别
    """
    # 更新数据集状态为正在预处理中
    dataset = DatasetDB.get_or_none(DatasetDB.id == dataset_id)
    if not dataset:
        logger.error(f"数据集 {dataset_id} 不存在")
        return

    # 更新数据集状态为正在预处理中
    pre_ocr_status = PreOCRStatus.get_all_status().index(PreOCRStatus.preprocessing) + 1
    dataset.pre_ocr_status = pre_ocr_status
    dataset.save()
    logger.info(f"数据集 {dataset_id} 状态更新为 {pre_ocr_status}")

    # 如果有pdf文件，先转换为图片
    _convert_if_pdf_to_image(dataset_id)

    # 检查是否存在未识别的图片
    check_images = _get_dataset_images(dataset_id, 0, 1)
    if not check_images:
        logger.info(f"数据集 {dataset_id} 当前已不存在未识别的图片")
        # 更新数据集状态为已完成
        dataset.pre_ocr_status = PreOCRStatus.get_all_status().index(PreOCRStatus.completed) + 1
        dataset.save()
        # 先查一遍还有无图片需要识别，尽量减少后面vllm空载启动的次数
        return

    # 调用vllm加载模型进行图片识别
    # 获取模型的权重加载路径
    matched_model = OcrModel.get_all_models()[dataset.model_type - 1]
    if not matched_model:
        logger.info(f"模型不存在: model_type={dataset.model_type}")
        return

    model_code = matched_model.get("code")
    model_weights_dir = SystemConfigDB.get_or_none(
        SystemConfigDB.config_key == f"{model_code}_weights_dir"
    ).config_value

    total_tokens_increment = 0  # 累加预识别tokens数量

    try:
        time1 = time.time()
        if gpu_device != "auto":
            os.environ["CUDA_VISIBLE_DEVICES"] = gpu_device
        vllm_engine = get_vllm_engine(model_code, model_weights_dir)
        time2 = time.time()
        logger.info(f"模型 {model_code} 加载耗时: {time2 - time1}")

        while True:
            # 分页获取待识别的图片，每100张图片数据一次批处理
            dataset_images = _get_dataset_images(dataset_id, 0, 100)
            if not dataset_images:
                break

            for image in dataset_images:
                image_file_path = f"{config.BASE_DIR}{image.file_path}"  # 数据库存储相对路径转换为绝对路径
                ocr_result, tokens_count = vllm_engine.generate(image_file_path)

                # 更新图片信息(即使中途被软删除了)
                DatasetImageDB.update(
                    is_preocr_completed=1,
                    ocr_result=ocr_result,
                    ocr_label=ocr_result,  # 此时ocr_label等于ocr_result
                    tokens=tokens_count,  # 当个图片预识别tokens数量
                    processed_at=datetime.now(),
                ).where(DatasetImageDB.id == image.id).execute()

                # 校验图片是否未被软删除
                vaild_image = DatasetImageDB.select_active().where(DatasetImageDB.id == image.id).first()
                if vaild_image:
                    # 是否累计到数据集需要看图片是否没被删除
                    total_tokens_increment += tokens_count

        # 预识别全部完成
        dataset.pre_ocr_status = PreOCRStatus.get_all_status().index(PreOCRStatus.completed) + 1
    except Exception as e:
        # 预处理过程出错
        dataset.pre_ocr_status = PreOCRStatus.get_all_status().index(PreOCRStatus.failed) + 1
        dataset.pre_ocr_error = str(e)
        logger.error(f"数据集 {dataset_id} 预处理失败，状态更新为 {pre_ocr_status}, 错误1: {str(e)}")
    finally:
        # 统计总数
        total_images = (
            DatasetImageDB.select_active()
            .where(
                DatasetImageDB.dataset == dataset_id,
            )
            .count()
        )
        dataset.total_images = total_images
        dataset.total_tokens += total_tokens_increment
        dataset.last_upload_time = datetime.now()
        dataset.save()
