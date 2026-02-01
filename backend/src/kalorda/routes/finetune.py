import json
import os
import re
import uuid
import zipfile
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import FileResponse

import kalorda.core.gpu_task_monitor as gpu_task_monitor
from kalorda.config import config
from kalorda.constant import CombineDataStatus, OcrModel, TrainingStatus
from kalorda.core.finetune_trainer import get_finetune_task_directory
from kalorda.core.sft_data_builder import SFTDataBuilder

# 导入数据库和模型
from kalorda.database.database import (
    DatasetDB,
    DatasetImageDB,
    FineTuneTaskDatasetThrough,
    FineTuneTaskDB,
    TrainingRunDB,
    db_manager,
    with_db_transaction,
)
from kalorda.models.finetune import (
    FineTuneTaskCreateRequest,
    FineTuneTaskResponse,
    FineTuneTaskUpdateRequest,
    TrainingRunBrief,
    TrainingRunParamsRequest,
    TrainingRunResponse,
)
from kalorda.utils.api_response import error_response, success_response
from kalorda.utils.i18n import _, t
from kalorda.utils.logger import logger
from kalorda.utils.security import (
    CurrentUser,
    get_current_active_user,
    get_trainer_user,
)

# 创建路由
router = APIRouter(
    prefix="/finetune",
    tags=["微调任务"],
    responses={
        404: {"description": _("未找到")},
        422: {"description": _("请求参数验证失败")},
    },
)


# 创建微调任务
@router.post("/task/create")
@with_db_transaction()
def create_finetune_task(
    task_data: FineTuneTaskCreateRequest,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    创建新的微调任务
    """
    try:
        # 检查任务名称是否已存在
        existing_task = FineTuneTaskDB.select_active().where(FineTuneTaskDB.name == task_data.name).first()
        if existing_task:
            return error_response(_("微调任务名称已存在"))

        # 验证数据集是否存在且属于当前用户
        datasets = DatasetDB.select_active().where(
            DatasetDB.id.in_(task_data.dataset_ids),
            DatasetDB.created_by == current_user.user_id,
        )
        if len(datasets) != len(task_data.dataset_ids):
            return error_response(_("部分数据集不存在或无权限访问"))

        # 创建微调任务
        task = FineTuneTaskDB.create(
            name=task_data.name,
            description=task_data.description,
            target_model=task_data.target_model,
            data_format=task_data.data_format,
            created_by=current_user.user_id,
            data_combine_status=CombineDataStatus.not_combined["value"],
            train_data_count=0,
            val_data_count=0,
        )

        # 关联数据集
        for dataset_id in task_data.dataset_ids:
            FineTuneTaskDatasetThrough.create(dataset=dataset_id, finetune_task=task.id)

        # 创建时统计微调数据量
        combine_finetune_task_data(task.id)

        # 转换为响应模型
        response_data = FineTuneTaskResponse(
            id=task.id,
            name=task.name,
            description=task.description,
            target_model=task.target_model,
            data_format=task.data_format,
            train_data_path=task.train_data_path,
            val_data_path=task.val_data_path,
            total_runs=0,
            created_by=task.created_by.id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            data_last_combined=task.data_last_combined,
            data_combine_status=task.data_combine_status,
            train_data_count=task.train_data_count,
            val_data_count=task.val_data_count,
            datasets=[],
        )
        return success_response(response_data)

    except Exception as e:
        logger.error(f"创建微调任务失败: {str(e)}", exc_info=True)
        return error_response(_("创建微调任务失败，请稍后重试"))


# 刷新合并微调数据
@router.post("/task/{task_id}/combine_data")
# @with_db_transaction()
def combine_data(
    task_id: int,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    刷新合并微调任务数据
    """
    try:
        # 确保数据库连接已打开
        db_manager.get_connection()

        task = (
            FineTuneTaskDB.select_active()
            .where(
                FineTuneTaskDB.id == task_id,
                FineTuneTaskDB.created_by == current_user.user_id,
            )
            .first()
        )
        if not task:
            return error_response(_("微调任务不存在或无权限访问"))
        # Combine data
        combine_result = combine_finetune_task_data(task_id, only_combine_count=False)
        status = combine_result.get("status")
        if combine_result.get("ok"):
            if status == "combining":
                return success_response(
                    {"status": status, "data_combine_status": CombineDataStatus.combining["value"]},
                    message=_("正在合并中，请稍后刷新查看结果"),
                )
            return success_response(
                {"status": status, "data_combine_status": CombineDataStatus.combined["value"]},
                message=_("合并数据成功"),
            )
        return error_response(_("刷新合并微调数据失败，请稍后重试"))
    except Exception as e:
        logger.error(f"刷新合并微调数据失败: {str(e)}", exc_info=True)
        return error_response(_("刷新合并微调数据失败，请稍后重试"))


def combine_finetune_task_data(task_id: int, only_combine_count: bool = True) -> dict:
    """
    Combine finetune task data.
    """
    # Ensure the DB connection is open
    db_manager.get_connection()

    # Fetch task instance
    task = FineTuneTaskDB.select_active().where(FineTuneTaskDB.id == task_id).first()
    if not task or not task.datasets:
        return {"ok": False, "status": "missing"}

    if not only_combine_count:
        # Try to acquire combine status to avoid duplicate work
        updated_rows = (
            FineTuneTaskDB.update(data_combine_status=CombineDataStatus.combining["value"])
            .where(
                FineTuneTaskDB.id == task.id,
                FineTuneTaskDB.data_combine_status != CombineDataStatus.combining["value"],
            )
            .execute()
        )
        if updated_rows == 0:
            # Already combining, just refresh counts
            only_count_sft_data(task)
            return {"ok": True, "status": "combining"}

        task.data_combine_status = CombineDataStatus.combining["value"]
        task.save()
        # Combine data (includes counts)
        try:
            combine_sft_data(task)
        except Exception:
            return {"ok": False, "status": "failed"}
        return {"ok": True, "status": "combined"}

    # Count only
    only_count_sft_data(task)
    return {"ok": True, "status": "counted"}


def only_count_sft_data(task: int):
    """
    只统计微调任务数据量
    """
    dataset_throughs = FineTuneTaskDatasetThrough.select().where(FineTuneTaskDatasetThrough.finetune_task == task.id)
    train_data_count = 0
    val_data_count = 0
    for through in dataset_throughs:
        dataset = through.dataset
        logger.info(f"数据集 {dataset.name} 训练数据量: {dataset.train_images}, 验证数据量: {dataset.val_images}")
        train_data_count += dataset.train_images
        val_data_count += dataset.val_images
    task.train_data_count = train_data_count
    task.val_data_count = val_data_count
    task.data_last_combined = datetime.now()
    task.save()


def combine_sft_data(task: FineTuneTaskDB):
    """
    Combine finetune task data.
    """
    __, task_data_dir = get_finetune_task_directory(task.id)

    train_data_path = task_data_dir + f"/train_{uuid.uuid4()}.jsonl"
    val_data_path = task_data_dir + f"/val_{uuid.uuid4()}.jsonl"

    # Write SFT data files
    try:
        train_data_count, val_data_count = write_sft_data_file(task, train_data_path, val_data_path)

        # Old files
        old_train_data_path = task.train_data_path
        old_val_data_path = task.val_data_path

        task.train_data_path = train_data_path
        task.val_data_path = val_data_path
        task.train_data_count = train_data_count
        task.val_data_count = val_data_count
        task.data_last_combined = datetime.now()
        task.data_combine_status = CombineDataStatus.combined["value"]
        task.save()
        try:
            # Delete old data files
            if old_train_data_path and os.path.exists(old_train_data_path):
                os.remove(old_train_data_path)
            if old_val_data_path and os.path.exists(old_val_data_path):
                os.remove(old_val_data_path)
        except Exception as e:
            logger.error(f"Failed to delete old data files: task_id={task.id}, {str(e)}", exc_info=True)
        logger.info(f"Combine finetune data succeeded: task_id={task.id}")
    except Exception as e:
        logger.error(f"Combine finetune data failed: task_id={task.id}, {str(e)}", exc_info=True)
        FineTuneTaskDB.update(data_combine_status=CombineDataStatus.not_combined["value"]).where(
            FineTuneTaskDB.id == task.id
        ).execute()
        task.data_combine_status = CombineDataStatus.not_combined["value"]
        task.save()
        raise


def write_sft_data_file(task: FineTuneTaskDB, train_data_file_path: str, val_data_file_path: str):
    """
    Write SFT data files.
    """
    import kalorda.core.sft_data_prompt as sft_data_prompt

    # Get prompt for training model
    matched_model = OcrModel.get_all_models()[task.target_model - 1]
    sft_prompt = sft_data_prompt.get_sft_prompt(matched_model.get("code"))

    train_data_written = False
    val_data_written = False

    # Get dataset IDs for the task
    dataset_ids = []
    dataset_throughs = FineTuneTaskDatasetThrough.select().where(FineTuneTaskDatasetThrough.finetune_task == task.id)
    for through in dataset_throughs:
        dataset = through.dataset
        dataset_ids.append(dataset.id)

    # chatml/query_response/sharegpt/alpaca
    data_builder = SFTDataBuilder(task.data_format)
    query = (
        DatasetImageDB.select_active()
        .select(
            DatasetImageDB.id,
            DatasetImageDB.train_data_type,
            DatasetImageDB.file_path,
            DatasetImageDB.ocr_label,
            DatasetImageDB.width,
            DatasetImageDB.height,
        )
        .where(DatasetImageDB.dataset_id.in_(dataset_ids) & (DatasetImageDB.train_data_type > 0))
    )

    # Remove files if they already exist
    if os.path.exists(train_data_file_path):
        os.remove(train_data_file_path)
    if os.path.exists(val_data_file_path):
        os.remove(val_data_file_path)

    append_write_file(train_data_file_path, "[")
    append_write_file(val_data_file_path, "[")

    train_data_count = 0
    val_data_count = 0

    page = 1
    page_size = 100
    while True:
        train_data_json_list = []
        val_data_json_list = []
        images = query.paginate(page, page_size)
        if not images or len(images) == 0:
            break
        page += 1
        for image in images:
            if image.file_path.startswith("./"):
                image.file_path = image.file_path[1:]
            # Convert relative path to absolute
            image.file_path = config.BASE_DIR + image.file_path

            data_json = data_builder.to_json(
                image.file_path,
                sft_prompt,
                convert_ocr_label(image, matched_model),
            )
            if image.train_data_type == 1:  # train data
                train_data_json_list.append(data_json)
                train_data_count += 1
            elif image.train_data_type == 2:  # validation data
                val_data_json_list.append(data_json)
                val_data_count += 1

        # Write page chunk once per page to avoid duplicates
        train_chunk = ",\n".join(train_data_json_list)
        if train_chunk:
            if train_data_written:
                train_chunk = ",\n" + train_chunk
            append_write_file(train_data_file_path, train_chunk)
            train_data_written = True

        val_chunk = ",\n".join(val_data_json_list)
        if val_chunk:
            if val_data_written:
                val_chunk = ",\n" + val_chunk
            append_write_file(val_data_file_path, val_chunk)
            val_data_written = True

    append_write_file(train_data_file_path, "]")
    append_write_file(val_data_file_path, "]")
    # Return accurate train/val counts
    return train_data_count, val_data_count


def html_format(html: str):
    """
    格式化HTML字符串，去除表格多余属性、数学公式处理等
    """

    # 1、正则替换quill/table-better表格属性保留<table><td><tr>标签
    html = re.sub(r"<table.*?>", "<table>", html)
    html = re.sub(r"<td.*?>", "<td>", html)
    html = re.sub(r"<tr.*?>", "<tr>", html)
    html = re.sub(r"<temporary.*?></temporary>", "", html)
    html = re.sub(r'<p class="ql-table-block".*?><br></p>', "", html)
    html = re.sub(r'<p class="ql-table-block".*?>', "<p>", html)

    # div标签替换
    html = re.sub(r"<div></div>", "", html)
    html = re.sub(r"<div>([\s\S]*?)</div>", r"\1 \n ", html)

    # 正则去掉开头或结尾有多余的\n\r空格等无用字符串
    html = re.sub(r"^\s+|\s+$", "", html)

    return html


def convert_ocr_label(image: DatasetImageDB, ocr_model: OcrModel):
    """
    转换标注内容为模型的自己原来的数据格式：因为经过前端标注后的结果都统一按dotsOCR的格式（作为标准格式）保存到后端的，
    而模型训练时需要的各家模型的格式不同的，所以需要转换回去。
    """
    ocr_label_json_str = image.ocr_label

    if ocr_label_json_str is None or len(ocr_label_json_str.strip()) == 0:
        return ""

    # ocr_label_json_str 格式：
    # [{"bbox": [x1, y1, x2, y2], "category": "Title", "text": "文本内容"}]

    image_width = int(image.width)
    image_height = int(image.height)

    # 1、got_ocr 模型，只返回文本内容，该模型不包含bbox信息
    if ocr_model == OcrModel.got_ocr:
        # got_ocr模型因为没有bbox信息，训练时需要合并为一个整体字符串，忽略掉标注后的bbox信息
        json_labels = json.loads(ocr_label_json_str)
        ocr_text = []
        for item in json_labels:
            ocr_text.append(html_format(item["text"]))  # 只取text
        return "\n".join(ocr_text)

    # 2、dotsOCR 模型
    if ocr_model == OcrModel.dotsocr:
        json_labels = json.loads(ocr_label_json_str)
        ocr_text = []
        for item in json_labels:
            item["text"] = html_format(item["text"])
        return json.dumps(json_labels, ensure_ascii=False)

    # 3、dolphin 模型
    if ocr_model == OcrModel.dolphin:
        json_labels = json.loads(ocr_label_json_str)
        ocr_text = []
        for item in json_labels:
            ocr_text.append(html_format(item["text"]))  # 只取text
            # TODO: 后续可补充构造 layout 信息参与微调
        return "\n".join(ocr_text)

    # 4、deepseek_ocr 模型
    if ocr_model == OcrModel.deepseek_ocr:
        json_labels = json.loads(ocr_label_json_str)
        ocr_text = []
        for item in json_labels:
            x1, y1, x2, y2 = item["bbox"]
            # 坐标处理，前端处理的逆操作
            x1, y1, x2, y2 = (
                int(x1 * 999 / image_width),
                int(y1 * 999 / image_height),
                int(x2 * 999 / image_width),
                int(y2 * 999 / image_height),
            )
            ocr_text.append(
                f"<|ref|>{item['category']}<|/ref|><|det|>[[{x1},{y1},{x2},{y2}]]<|/det|>\n{html_format(item['text'])}"
            )
        return "\n".join(ocr_text)

    # 7、deepseek_ocr2 模型
    if ocr_model == OcrModel.deepseek_ocr2:
        json_labels = json.loads(ocr_label_json_str)
        ocr_text = []
        for item in json_labels:
            x1, y1, x2, y2 = item["bbox"]
            # 坐标处理，前端处理的逆操作
            x1, y1, x2, y2 = (
                int(x1 * 999 / image_width),
                int(y1 * 999 / image_height),
                int(x2 * 999 / image_width),
                int(y2 * 999 / image_height),
            )
            ocr_text.append(
                f"<|ref|>{item['category']}<|/ref|><|det|>[[{x1},{y1},{x2},{y2}]]<|/det|>\n{html_format(item['text'])}"
            )
        return "\n".join(ocr_text)

    # 5、paddleocr_vl 模型
    if ocr_model == OcrModel.paddleocr_vl:
        # 合并为一个整体字符串，忽略掉标注后的bbox信息
        json_labels = json.loads(ocr_label_json_str)
        ocr_text = []
        for item in json_labels:
            ocr_text.append(html_format(item["text"]))  # 只取text
        return "\n".join(ocr_text)

    # 6、hunyuan_ocr 模型
    if ocr_model == OcrModel.hunyuan_ocr:
        # 合并为一个整体字符串，忽略掉标注后的bbox信息
        json_labels = json.loads(ocr_label_json_str)
        ocr_text = []
        for item in json_labels:
            ocr_text.append(html_format(item["text"]))  # 只取text
        return "\n".join(ocr_text)


def append_write_file(file_path: str, content: str):
    if not content or content == "":
        return

    # 追加保存文件
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(content)


# 修改微调任务
@router.post("/task/update")
@with_db_transaction()
def update_finetune_task(
    task_data: FineTuneTaskUpdateRequest,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    修改微调任务
    """
    try:
        # 检查任务是否存在且属于当前用户
        task = (
            FineTuneTaskDB.select_active()
            .where(
                FineTuneTaskDB.id == task_data.id,
                FineTuneTaskDB.created_by == current_user.user_id,
            )
            .first()
        )
        if not task:
            return error_response(_("微调任务不存在或无权限操作"))

        # 检查任务名称是否已存在（如果名称有变化）
        if task_data.name and task.name != task_data.name:
            existing_task = FineTuneTaskDB.select_active().where(FineTuneTaskDB.name == task_data.name).first()
            if existing_task:
                return error_response(_("微调任务名称已存在"))
            task.name = task_data.name

        # 更新描述
        if task_data.description is not None:
            task.description = task_data.description

        # 更新目标模型
        if task_data.target_model is not None:
            task.target_model = task_data.target_model

        # 更新数据格式
        if task_data.data_format is not None:
            task.data_format = task_data.data_format

        # 更新关联数据集
        if task_data.dataset_ids is not None:
            # 验证数据集是否存在且属于当前用户
            datasets = DatasetDB.select_active().where(
                DatasetDB.id.in_(task_data.dataset_ids),
                DatasetDB.created_by == current_user.user_id,
            )
            if len(datasets) != len(task_data.dataset_ids):
                return error_response(_("部分数据集不存在或无权限访问"))

            # 删除旧的关联
            FineTuneTaskDatasetThrough.delete().where(FineTuneTaskDatasetThrough.finetune_task == task.id).execute()

            # 创建新的关联
            for dataset_id in task_data.dataset_ids:
                FineTuneTaskDatasetThrough.create(dataset=dataset_id, finetune_task=task.id)

        task.save()

        # 更新时候统计微调数据量
        combine_finetune_task_data(task.id)

        # 获取关联数据集信息
        dataset_throughs = FineTuneTaskDatasetThrough.select().where(
            FineTuneTaskDatasetThrough.finetune_task == task.id
        )
        datasets = []
        for through in dataset_throughs:
            dataset = through.dataset
            datasets.append(
                {
                    "id": dataset.id,
                    "name": dataset.name,
                    "model_type": dataset.model_type,
                    "total_images": dataset.total_images,
                    "train_images": dataset.train_images,
                    "val_images": dataset.val_images,
                }
            )

        # 转换为响应模型
        response_data = FineTuneTaskResponse(
            id=task.id,
            name=task.name,
            description=task.description,
            target_model=task.target_model,
            data_format=task.data_format,
            train_data_path=task.train_data_path,
            val_data_path=task.val_data_path,
            total_runs=task.training_runs.count(),
            created_by=task.created_by.id,
            created_at=task.created_at,
            updated_at=task.updated_at,
            data_last_combined=task.data_last_combined,
            data_combine_status=task.data_combine_status,
            train_data_count=task.train_data_count,
            val_data_count=task.val_data_count,
            datasets=datasets,
        )
        return success_response(response_data)

    except Exception as e:
        logger.error(f"更新微调任务失败: {str(e)}", exc_info=True)
        return error_response(_("更新微调任务失败，请稍后重试"))


# 删除微调任务
@router.post("/task/delete/{task_id}")
@with_db_transaction()
def delete_finetune_task(
    task_id: int,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    删除微调任务（软删除）
    """
    try:
        # 检查任务是否存在且属于当前用户
        task = (
            FineTuneTaskDB.select_active()
            .where(
                FineTuneTaskDB.id == task_id,
                FineTuneTaskDB.created_by == current_user.user_id,
            )
            .first()
        )
        if not task:
            return error_response(_("微调任务不存在或无权限操作"))

        # 查找全部的训练实例并软删除
        training_runs = TrainingRunDB.select_active().select(TrainingRunDB.id).where(TrainingRunDB.task == task.id)
        if training_runs:
            # 软删除所有训练实例
            TrainingRunDB.update(is_deleted=True).where(
                TrainingRunDB.id.in_([run.id for run in training_runs])
            ).execute()

        # 软删除任务
        task.is_deleted = True
        task.save()

        logger.info(f"用户 {current_user.username} 删除微调任务: {task.name}")

        return success_response({"message": _("删除成功")})

    except Exception as e:
        logger.error(f"删除微调任务失败: {str(e)}", exc_info=True)
        return error_response(_("删除微调任务失败，请稍后重试"))


# 合成训练和验证数据
@router.post("/task/{task_id}/combine-data")
@with_db_transaction()
def combine_task_data(
    task_id: int,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    合成该任务下的训练和验证数据
    """
    try:
        # 检查任务是否存在且属于当前用户
        task = (
            FineTuneTaskDB.select_active()
            .where(
                FineTuneTaskDB.id == task_id,
                FineTuneTaskDB.created_by == current_user.user_id,
            )
            .first()
        )
        if not task:
            return error_response(_("微调任务不存在或无权限操作"))

        # TODO: 实现数据合成逻辑
        # 这里暂时留空，不具体实现

        return success_response({"message": _("数据合成任务已开始")})

    except Exception as e:
        logger.error(f"合成数据失败: {str(e)}", exc_info=True)
        return error_response(_("合成数据失败，请稍后重试"))


# 查询用户创建的全部训练任务分页列表
@router.post("/task/list")
@with_db_transaction(use_transaction=False)
def get_finetune_tasks(
    page: int = Body(1, ge=1, description="页码"),
    page_size: int = Body(10, ge=1, le=100, description="每页大小"),
    task_ids: Optional[List[int]] = Body(None, description="任务ID列表"),
    keyword: Optional[str] = Body(None, description="任务名称关键词搜索"),
    target_model: Optional[int] = Body(None, description="目标模型类型"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    查询该用户创建的全部训练任务分页列表
    """
    try:
        # 构建查询
        query = FineTuneTaskDB.select_active().where(FineTuneTaskDB.created_by == current_user.user_id)

        # 按任务ID列表过滤
        if task_ids and len(task_ids) > 0:
            query = query.where(FineTuneTaskDB.id.in_(task_ids))

        # 按名称关键字过滤
        if keyword and keyword != "":
            query = query.where(FineTuneTaskDB.name.contains(keyword))

        # 按目标模型过滤
        if target_model is not None and target_model > 0:
            query = query.where(FineTuneTaskDB.target_model == target_model)

        # 计算总数
        total = query.count()

        # 分页查询
        skip = (page - 1) * page_size
        tasks = query.order_by(FineTuneTaskDB.created_at.desc()).offset(skip).limit(page_size)

        # 转换为响应模型列表
        task_list = []
        for task in tasks:
            # 获取最新训练运行信息
            latest_run = task.training_runs.order_by(TrainingRunDB.created_at.desc()).first()
            latest_run_info = None
            if latest_run:
                latest_run_info = TrainingRunBrief(
                    id=latest_run.id,
                    run_name=latest_run.run_name,
                    training_type=latest_run.training_type,
                    status=latest_run.status,
                    start_time=latest_run.start_time,
                    end_time=latest_run.end_time,
                    duration=latest_run.duration,
                    train_data_count=latest_run.train_data_count,
                    val_data_count=latest_run.val_data_count,
                    metrics=json.loads(latest_run.metrics) if latest_run.metrics else None,
                    model_code_suffix=latest_run.model_code_suffix,
                )

            # 获取关联数据集信息
            dataset_throughs = FineTuneTaskDatasetThrough.select().where(
                FineTuneTaskDatasetThrough.finetune_task == task.id
            )
            datasets = []
            for through in dataset_throughs:
                dataset = through.dataset
                datasets.append(
                    {
                        "id": dataset.id,
                        "name": dataset.name,
                        "model_type": dataset.model_type,
                        "total_images": dataset.total_images,
                        "train_images": dataset.train_images,
                        "val_images": dataset.val_images,
                    }
                )

            task_response = FineTuneTaskResponse(
                id=task.id,
                name=task.name,
                description=task.description,
                target_model=task.target_model,
                data_format=task.data_format,
                train_data_path=task.train_data_path,
                val_data_path=task.val_data_path,
                total_runs=task.training_runs.count(),
                created_by=task.created_by.id,
                created_at=task.created_at,
                updated_at=task.updated_at,
                data_last_combined=task.data_last_combined,
                data_combine_status=task.data_combine_status,
                train_data_count=task.train_data_count,
                val_data_count=task.val_data_count,
                latest_run_id=latest_run.id if latest_run else None,
                latest_run_status=latest_run.status if latest_run else None,
                latest_run_metrics=json.loads(latest_run.metrics) if latest_run and latest_run.metrics else None,
                latest_model_path=latest_run.best_model_path if latest_run else None,
                datasets=datasets,
                latest_run=latest_run_info,
            )
            task_list.append(task_response)

        # 计算总页数
        total_pages = (total + page_size - 1) // page_size

        # 获取所有可用的模型列表
        from kalorda.constant import OcrModel

        ocr_models = OcrModel.get_all_models()

        # 返回任务列表和模型列表
        response_data = {
            "task_list": task_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "ocr_models": ocr_models,
        }

        return success_response(response_data)

    except Exception as e:
        logger.error(f"获取微调任务列表失败: {str(e)}", exc_info=True)
        return error_response(_("获取微调任务列表失败，请稍后重试"))


# ============================================
# 训练实例相关接口
# ============================================


# 创建训练实例
@router.post("/run/create")
@with_db_transaction()
def create_training_run(
    run_data: TrainingRunParamsRequest,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    在具体的微调任务下创建训练实例（不启动训练）
    """
    try:
        model_name, error_msg = format_new_model_name(run_data.model_name)
        if error_msg:
            return error_response(error_msg)

        # 检查微调任务是否存在且属于当前用户
        task = (
            FineTuneTaskDB.select_active()
            .where(
                FineTuneTaskDB.id == run_data.task_id,
                FineTuneTaskDB.created_by == current_user.user_id,
            )
            .first()
        )
        if not task:
            return error_response(_("微调任务不存在或无权限操作"))

        # 验证训练数据是否已合成
        if not task.train_data_path:
            return error_response(_("请先合成训练数据"))

        # 生成运行名称
        run_count = task.training_runs.count() + 1
        run_name = t(_("第 {run_count} 次训练"), **{"run_count": str(run_count)})

        # 创建训练实例
        training_run = TrainingRunDB.create(
            task=task.id,
            created_by=current_user.user_id,
            training_type=run_data.training_type,
            custom_params=run_data.custom_params,
            num_epochs=run_data.num_epochs,
            learning_rate=run_data.learning_rate,
            target_modules=json.dumps(run_data.target_modules) if run_data.target_modules else None,
            lora_rank=run_data.lora_rank,
            lora_alpha=run_data.lora_alpha,
            batch_size=run_data.batch_size,
            gradient_accumulation_steps=run_data.gradient_accumulation_steps,
            logging_steps=run_data.logging_steps,
            eval_steps=run_data.eval_steps,
            warmup_ratio=run_data.warmup_ratio,
            weight_decay=run_data.weight_decay,
            max_seq_len=run_data.max_seq_len,
            max_grad_norm=run_data.max_grad_norm,
            split_dataset_ratio=run_data.split_dataset_ratio,
            lr_warmup_iters_ratio=run_data.lr_warmup_iters_ratio,
            do_early_stop=run_data.do_early_stop,
            early_stop_patience=run_data.early_stop_patience,
            seed=run_data.seed,
            run_name=run_name,
            model_name=model_name,
            status=1,  # 初始状态：未开始 = 1
        )

        logger.info(f"用户 {current_user.username} 创建训练实例: {run_name}")

        # 转换为响应模型
        response_data = TrainingRunResponse(
            id=training_run.id,
            task_id=training_run.task.id,
            training_type=training_run.training_type,
            custom_params=training_run.custom_params,
            num_epochs=training_run.num_epochs,
            learning_rate=training_run.learning_rate,
            target_modules=run_data.target_modules,
            lora_rank=training_run.lora_rank,
            lora_alpha=training_run.lora_alpha,
            batch_size=training_run.batch_size,
            gradient_accumulation_steps=training_run.gradient_accumulation_steps,
            logging_steps=training_run.logging_steps,
            eval_steps=training_run.eval_steps,
            warmup_ratio=training_run.warmup_ratio,
            weight_decay=training_run.weight_decay,
            max_seq_len=training_run.max_seq_len,
            max_grad_norm=training_run.max_grad_norm,
            split_dataset_ratio=training_run.split_dataset_ratio,
            lr_warmup_iters_ratio=training_run.lr_warmup_iters_ratio,
            do_early_stop=training_run.do_early_stop,
            early_stop_patience=training_run.early_stop_patience,
            seed=training_run.seed,
            run_name=training_run.run_name,
            model_output_path=training_run.model_output_path,
            log_path=training_run.log_path,
            status=training_run.status,
            start_time=training_run.start_time,
            end_time=training_run.end_time,
            duration=training_run.duration,
            train_data_count=training_run.train_data_count,
            val_data_count=training_run.val_data_count,
            error_message=training_run.error_message,
            metrics=None,
            best_model_path=training_run.best_model_path,
            model_code_suffix=training_run.model_code_suffix,
            model_name=training_run.model_name,
            created_at=training_run.created_at,
            updated_at=training_run.updated_at,
        )
        return success_response(response_data)

    except Exception as e:
        logger.error(f"创建训练实例失败: {str(e)}", exc_info=True)
        return error_response(_("创建训练实例失败，请稍后重试"))


def format_new_model_name(model_name: str):
    """
    格式化前端输入的微调模型名称，移除特殊字符
    """
    if not model_name:
        return None, _("模型名称不能为空，请重新设置")
    model_name = model_name.replace("'", "").replace('"', "").replace("/", "").replace("\\", "")
    for base_model in OcrModel.get_all_models():
        if base_model["name"].lower() == model_name.lower():
            return None, _("模型名称已存在，请重新设置")
    return model_name, None


# 修改训练实例的超参数设置
@router.post("/run/{run_id}/update")
@with_db_transaction()
def update_training_run(
    run_id: int,
    run_data: TrainingRunParamsRequest,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    在具体的微调任务下修改训练实例超参数（不启动训练）
    """
    try:
        model_name, error_msg = format_new_model_name(run_data.model_name)
        if error_msg:
            return error_response(error_msg)

        # 创建训练实例
        training_run = TrainingRunDB.select_active().where(TrainingRunDB.id == run_id).first()
        if not training_run or training_run.task.created_by.id != current_user.user_id:
            return error_response(_("训练实例不存在或无权限操作"))

        exist_run = (
            TrainingRunDB.select_active()
            .where(TrainingRunDB.task_id == run_id & TrainingRunDB.model_name == model_name)
            .first()
        )
        if exist_run:
            return error_response(_("模型名称已存在，请重新设置"))

        # 更新训练实例超参数
        training_run.training_type = run_data.training_type
        training_run.custom_params = run_data.custom_params
        training_run.num_epochs = run_data.num_epochs
        training_run.learning_rate = run_data.learning_rate
        training_run.target_modules = json.dumps(run_data.target_modules) if run_data.target_modules else None
        training_run.lora_rank = run_data.lora_rank
        training_run.lora_alpha = run_data.lora_alpha
        training_run.batch_size = run_data.batch_size
        training_run.gradient_accumulation_steps = run_data.gradient_accumulation_steps
        training_run.logging_steps = run_data.logging_steps
        training_run.eval_steps = run_data.eval_steps
        training_run.warmup_ratio = run_data.warmup_ratio
        training_run.weight_decay = run_data.weight_decay
        training_run.max_seq_len = run_data.max_seq_len
        training_run.max_grad_norm = run_data.max_grad_norm
        training_run.split_dataset_ratio = run_data.split_dataset_ratio
        training_run.lr_warmup_iters_ratio = run_data.lr_warmup_iters_ratio
        training_run.do_early_stop = run_data.do_early_stop
        training_run.early_stop_patience = run_data.early_stop_patience
        training_run.seed = run_data.seed
        training_run.model_name = model_name
        training_run.save()

        # 转换为响应模型
        response_data = TrainingRunResponse(
            id=training_run.id,
            task_id=training_run.task.id,
            training_type=training_run.training_type,
            custom_params=training_run.custom_params,
            num_epochs=training_run.num_epochs,
            learning_rate=training_run.learning_rate,
            target_modules=run_data.target_modules,
            lora_rank=training_run.lora_rank,
            lora_alpha=training_run.lora_alpha,
            batch_size=training_run.batch_size,
            gradient_accumulation_steps=training_run.gradient_accumulation_steps,
            logging_steps=training_run.logging_steps,
            eval_steps=training_run.eval_steps,
            warmup_ratio=training_run.warmup_ratio,
            weight_decay=training_run.weight_decay,
            max_seq_len=training_run.max_seq_len,
            max_grad_norm=training_run.max_grad_norm,
            split_dataset_ratio=training_run.split_dataset_ratio,
            lr_warmup_iters_ratio=training_run.lr_warmup_iters_ratio,
            do_early_stop=training_run.do_early_stop,
            early_stop_patience=training_run.early_stop_patience,
            seed=training_run.seed,
            run_name=training_run.run_name,
            model_output_path=training_run.model_output_path,
            log_path=training_run.log_path,
            status=training_run.status,
            start_time=training_run.start_time,
            end_time=training_run.end_time,
            duration=training_run.duration,
            train_data_count=training_run.train_data_count,
            val_data_count=training_run.val_data_count,
            error_message=training_run.error_message,
            metrics=None,
            best_model_path=training_run.best_model_path,
            model_code_suffix=training_run.model_code_suffix,
            model_name=training_run.model_name,
            created_at=training_run.created_at,
            updated_at=training_run.updated_at,
        )
        return success_response(response_data)

    except Exception as e:
        logger.error(f"更新训练实例超参数失败: {str(e)}", exc_info=True)
        return error_response(_("更新训练实例超参数失败，请稍后重试"))


# 删除训练实例
@router.post("/run/{run_id}/delete")
@with_db_transaction()
def delete_training_run(
    run_id: int,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    删除训练实例（软删除）
    """
    try:
        # 检查训练实例是否存在且所属任务属于当前用户
        training_run = (
            TrainingRunDB.select_active()
            .join(FineTuneTaskDB)
            .where(
                TrainingRunDB.id == run_id,
                FineTuneTaskDB.created_by == current_user.user_id,
            )
            .first()
        )
        if not training_run:
            return error_response(_("训练实例不存在或无权限操作"))

        # 已启动但未结束的实例暂时不能删除
        # if training_run.status > 1 or training_run.status < 6:  # 1=未开始, 6=已完成
        #     return error_response("已启动但未结束的实例暂时不能删除")

        # 软删除训练实例
        training_run.is_deleted = True
        training_run.save()

        logger.info(f"用户 {current_user.username} 删除训练实例: {training_run.run_name}")

        return success_response({"message": _("删除成功")})

    except Exception as e:
        logger.error(f"删除训练实例失败: {str(e)}", exc_info=True)
        return error_response(_("删除训练实例失败，请稍后重试"))


# 查询某微调任务下所有已创建的未删除训练实例的分页接口
@router.post("/task/{task_id}/runs/list")
def get_training_runs(
    task_id: int,
    page: int = Body(1, ge=1, description="页码"),
    page_size: int = Body(10, ge=1, le=100, description="每页大小"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    查询该任务下所有已创建的未删除的训练实例的分页列表
    """
    try:
        # 检查微调任务是否存在且属于当前用户
        task = (
            FineTuneTaskDB.select_active()
            .where(
                FineTuneTaskDB.id == task_id,
                FineTuneTaskDB.created_by == current_user.user_id,
            )
            .first()
        )
        if not task:
            return error_response(_("微调任务不存在或无权限操作"))

        # 查询该任务下的所有未删除训练实例
        query = TrainingRunDB.select_active().where(TrainingRunDB.task == task_id)

        # 计算总数
        total = query.count()

        # 分页查询
        skip = (page - 1) * page_size
        runs = query.order_by(TrainingRunDB.created_at.asc()).offset(skip).limit(page_size)

        # 转换为响应模型列表
        run_list = []
        for run in runs:
            run_response = TrainingRunResponse(
                id=run.id,
                task_id=run.task.id,
                training_type=run.training_type,
                custom_params=run.custom_params,
                num_epochs=run.num_epochs,
                learning_rate=run.learning_rate,
                target_modules=run.target_modules if run.target_modules else None,
                lora_rank=run.lora_rank,
                lora_alpha=run.lora_alpha,
                batch_size=run.batch_size,
                gradient_accumulation_steps=run.gradient_accumulation_steps,
                logging_steps=run.logging_steps if run.logging_steps else 1,
                eval_steps=run.eval_steps if run.eval_steps else 1,
                warmup_ratio=run.warmup_ratio,
                weight_decay=run.weight_decay,
                max_seq_len=run.max_seq_len,
                max_grad_norm=run.max_grad_norm,
                split_dataset_ratio=run.split_dataset_ratio,
                lr_warmup_iters_ratio=run.lr_warmup_iters_ratio,
                do_early_stop=run.do_early_stop,
                early_stop_patience=run.early_stop_patience,
                seed=run.seed,
                run_name=run.run_name,
                model_output_path=run.model_output_path,
                log_path=run.log_path,
                status=run.status,
                start_time=run.start_time,
                end_time=run.end_time,
                duration=run.duration,
                train_data_count=run.train_data_count,
                val_data_count=run.val_data_count,
                error_message=run.error_message,
                metrics=json.loads(run.metrics) if run.metrics else None,
                best_model_path=run.best_model_path,
                model_code_suffix=run.model_code_suffix,
                model_name=run.model_name,
                created_at=run.created_at,
                updated_at=run.updated_at,
            )
            run_list.append(run_response)

        # 计算总页数
        total_pages = (total + page_size - 1) // page_size

        response_data = {
            "training_statuses": TrainingStatus.get_all_status(),
            "run_list": run_list,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
        }

        return success_response(response_data)

    except Exception as e:
        logger.error(f"获取训练实例列表失败: {str(e)}", exc_info=True)
        return error_response(_("获取训练实例列表失败，请稍后重试"))


# 启动训练实例
@router.post("/run/{run_id}/start")
def start_training_run(
    run_id: int,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    启动训练实例
    """
    try:
        # 检查训练实例是否存在且所属任务属于当前用户
        training_run = (
            TrainingRunDB.select()
            .join(FineTuneTaskDB)
            .where(
                TrainingRunDB.id == run_id,
                FineTuneTaskDB.created_by == current_user.user_id,
                TrainingRunDB.status == 1,  # 1=未开始
            )
            .first()
        )
        if not training_run:
            return error_response(_("训练实例不存在或无权限操作"))

        # 步骤1：添加GPU任务表
        gpu_task_monitor.add_gpu_task(
            name=f"微调训练实例-{run_id}",
            task_type="finetune",
            handler="kalorda.core.finetune_trainer.finetune_with_ms_swift",
            params={"training_run_id": run_id},
            correlation_id=run_id,  # 关联训练实例ID，用于查询
            can_retry=False,
            run_times_limit=1,
        )

        # 步骤2：更新训练实例状态为排队等待中
        waitingStatusValue = TrainingStatus.waiting["value"]
        logger.info(f"更新训练实例状态为排队等待中: {waitingStatusValue}")
        TrainingRunDB.update(status=waitingStatusValue).where(TrainingRunDB.id == run_id).execute()

        data = {
            "training_run_id": run_id,
            "status": waitingStatusValue,
        }
        return success_response(data)

    except Exception as e:
        logger.error(f"启动训练失败: {str(e)}", exc_info=True)
        return error_response(_("启动训练失败，请稍后重试"))


@router.post("/run/{run_id}/reset")
def reset_training_run(
    run_id: int,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    重新设为未开始状态
    """
    try:
        # 检查训练实例是否存在且所属任务属于当前用户
        training_run = (
            TrainingRunDB.select()
            .join(FineTuneTaskDB)
            .where(
                TrainingRunDB.id == run_id,
                FineTuneTaskDB.created_by == current_user.user_id,
                TrainingRunDB.status != 1,  # 1=未开始
            )
            .first()
        )
        if not training_run:
            return error_response(_("训练实例不存在或无权限操作"))

        # 步骤2：更新训练实例状态为未开始
        notStartStatusValue = TrainingStatus.not_start["value"]
        logger.info(f"更新训练实例状态为未开始: {notStartStatusValue}")
        TrainingRunDB.update(status=notStartStatusValue).where(TrainingRunDB.id == run_id).execute()
        # 如果有关联的gpu任务则取消
        gpu_task_monitor.del_gpu_task(gpu_task_type="finetune", correlation_id=run_id)

        # 步骤3：删除已有日志文件
        task_id = training_run.task_id
        task_base_dir, __ = get_finetune_task_directory(task_id)
        log_file = f"{task_base_dir}/train_log_{run_id}.log"
        if os.path.exists(log_file):
            os.remove(log_file)

        data = {
            "training_run_id": run_id,
            "status": notStartStatusValue,
        }
        return success_response(data)

    except Exception as e:
        logger.error(f"重新设为未开始状态失败: {str(e)}", exc_info=True)
        return error_response(_("重新设为未开始状态失败，请稍后重试"))


@router.post("/run/{run_id}/cancel")
def cancel_training_run(
    run_id: int,
    current_user: CurrentUser = Depends(get_trainer_user),
):
    """
    中止运行中的训练实例
    """
    try:
        # 检查训练实例是否存在且所属任务属于当前用户
        training_run = (
            TrainingRunDB.select()
            .join(FineTuneTaskDB)
            .where(
                TrainingRunDB.id == run_id,
                FineTuneTaskDB.created_by == current_user.user_id,
            )
            .first()
        )
        if not training_run:
            return error_response(_("训练实例不存在或无权限操作"))

        if training_run.status not in (
            TrainingStatus.starting["value"],
            TrainingStatus.running["value"],
            TrainingStatus.saving["value"],
        ):
            return error_response(_("训练实例当前状态不支持取消"))

        # 步骤2：更新训练实例状态为未开始
        canceledStatus = training_run.status + 20
        logger.info(f"更新训练实例状态为未开始: {canceledStatus}")
        TrainingRunDB.update(status=canceledStatus).where(TrainingRunDB.id == run_id).execute()

        # 如果有关联的gpu任务则取消
        gpu_task_monitor.del_gpu_task(gpu_task_type="finetune", correlation_id=run_id)

        data = {
            "training_run_id": run_id,
            "status": canceledStatus,
        }
        return success_response(data)

    except Exception as e:
        logger.error(f"重新设为未开始状态失败: {str(e)}", exc_info=True)
        return error_response(_("重新设为未开始状态失败，请稍后重试"))


@router.post("/run/{run_id}/waiting_rank")
def get_waiting_rank(
    run_id: int,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取训练实例排队位置信息
    """
    waiting_rank, waiting_rank_total = gpu_task_monitor.get_waiting_rank(
        gpu_task_type="finetune", correlation_id=run_id
    )
    data = {
        "training_run_id": run_id,
        "waiting_rank": waiting_rank,
        "waiting_rank_total": waiting_rank_total,
    }
    return success_response(data)


@router.get("/task/{task_id}/run/{run_id}/log")
def get_training_run_log(
    task_id: int,
    run_id: int,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取训练实例日志
    """
    task_base_dir, __ = get_finetune_task_directory(task_id)
    log_file = f"{task_base_dir}/train_log_{run_id}.log"
    logger.info(f"获取训练实例日志: {log_file}")
    log_content = ""
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            log_content = f.read()
        if log_content:
            log_content = log_content[:-1]

    data = {
        "task_id": task_id,
        "run_id": run_id,
        "log_content": f"[{log_content}]",
    }

    return success_response(data)


@router.get("/task/{task_id}/run/{run_id}/checkpoint")
@with_db_transaction(use_transaction=False)
def get_training_run_checkpoint(
    task_id: int,
    run_id: int,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取训练实例检查点
    """
    training_run = (
        TrainingRunDB.select()
        .join(FineTuneTaskDB)
        .where(
            TrainingRunDB.id == run_id,
            FineTuneTaskDB.created_by == current_user.user_id,
        )
        .first()
    )
    if not training_run:
        return error_response(_("训练实例不存在或无权限操作"))

    checkpoint_dir = f"{training_run.model_output_path}"
    files_info = []
    if os.path.exists(checkpoint_dir):
        for filename in os.listdir(checkpoint_dir):
            file_path = os.path.join(checkpoint_dir, filename)
            try:
                # 获取文件状态信息
                stat_info = os.stat(file_path)
                # 计算文件大小（字节）
                file_size = stat_info.st_size
                # 获取修改时间
                modified_time = datetime.fromtimestamp(stat_info.st_mtime)
                # 判断文件类型
                if os.path.isdir(file_path):
                    file_type = "directory"
                else:
                    # 获取文件扩展名作为类型
                    __, extension = os.path.splitext(filename)
                    file_type = extension[1:] if extension else "file"

                # 添加文件信息到列表
                files_info.append(
                    {
                        "name": filename,
                        "date": modified_time.isoformat(),
                        "size": file_size,
                        "type": file_type,
                    }
                )
            except Exception as e:
                # 记录错误但继续处理其他文件
                logger.error(f"获取文件信息失败 {file_path}: {str(e)}")
    data = {
        "task_id": task_id,
        "run_id": run_id,
        "files_info": files_info,
    }
    return success_response(data)


@router.post("/run/checkpoint/filecontent")
def checkpoint_file_content(
    task_id: int = Body(..., description="任务ID"),
    run_id: int = Body(..., description="训练实例ID"),
    file_name: str = Body(..., description="检查点文件名"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取训练实例检查点文件内容
    """
    training_run = (
        TrainingRunDB.select()
        .join(FineTuneTaskDB)
        .where(
            TrainingRunDB.id == run_id,
            FineTuneTaskDB.created_by == current_user.user_id,
        )
        .first()
    )
    if not training_run:
        return error_response(_("训练实例不存在或无权限操作"))
    checkpoint_dir = f"{training_run.model_output_path}"
    file_path = f"{checkpoint_dir}/{file_name}"
    if not os.path.exists(file_path):
        return error_response(_("检查点文件不存在"))
    with open(file_path, "r") as f:
        file_content = f.read()
    data = {
        "task_id": task_id,
        "run_id": run_id,
        "file_name": file_name,
        "file_content": file_content,
    }
    return success_response(data)


@router.get("/run/checkpoint/download/{run_id}")
def download_checkpoint_file(
    run_id: int,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    下载训练实例检查点文件
    """
    training_run = (
        TrainingRunDB.select_active()
        .where(TrainingRunDB.id == run_id)
        .where(TrainingRunDB.created_by == current_user.user_id)
        .first()
    )
    if not training_run:
        return error_response(_("训练实例不存在或无权限操作"))
    checkpoint_dir = f"{training_run.model_output_path}"
    if not checkpoint_dir:
        return error_response(_("检查点目录不存在"))
    # 检查checkpoint_dir是否存在
    if not os.path.exists(checkpoint_dir):
        return error_response(_("检查点目录不存在"))

    # 压缩文件夹
    zip_file_path = f"{checkpoint_dir}.zip"
    # 检查压缩文件是否存在
    if not os.path.exists(zip_file_path):
        with zipfile.ZipFile(zip_file_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, __, files in os.walk(checkpoint_dir):
                for file in files:
                    zipf.write(
                        os.path.join(root, file),
                        os.path.relpath(os.path.join(root, file), checkpoint_dir),
                    )

    # 返回压缩文件路径
    return FileResponse(
        path=zip_file_path,
        filename=f"checkpoint_{run_id}.zip",
        media_type="application/zip",
    )
