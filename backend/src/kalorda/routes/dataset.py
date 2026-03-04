import base64
import json
import os
import random
import shutil
import uuid
import zipfile
from datetime import datetime
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, File, Form, Query, UploadFile
from PIL import Image
from transformers import AutoTokenizer

import kalorda.core.gpu_task_monitor as gpu_task_monitor
from kalorda.config import config
from kalorda.constant import (
    DeepseekOCRCategory,
    DeepseekOCR2Category,
    DolphinCategory,
    DotsOCRCategory,
    GotOCRCategory,
    HunyuanOCRCategory,
    OcrModel,
    PaddleOCRVLCategory,
    FireRedOCRCategory,
    PreOCRStatus,
)

# 导入数据库和模型
from kalorda.database.database import (
    DatasetDB,
    DatasetImageDB,
    SystemConfigDB,
    db_manager,
    with_db_transaction,
)
from kalorda.models.dataset import (
    DatasetCreateRequest,
    DatasetImagePageResponse,
    DatasetImageResponse,
    DatasetImageUpdateRequest,
    DatasetResponse,
    DatasetUpdateRequest,
)
from kalorda.utils.api_response import error_response, success_response
from kalorda.utils.i18n import _, t
from kalorda.utils.logger import logger
from kalorda.utils.security import (
    CurrentUser,
    get_annotator_user,
    get_current_active_user,
)
from kalorda.utils.upload_file import get_dataset_directory, save_dataset_file, save_dataset_zip


def _is_safe_relpath(path: str) -> bool:
    if not path or os.path.isabs(path):
        return False
    normalized = os.path.normpath(path)
    if normalized.startswith("..") or normalized.startswith("\\") or normalized.startswith("/"):
        return False
    return True


def _safe_extract_zip(zip_path: str, extract_dir: str) -> None:
    abs_extract_dir = os.path.abspath(extract_dir)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_name = member.filename
            if not _is_safe_relpath(member_name):
                raise ValueError(f"unsafe zip entry: {member_name}")
            dest_path = os.path.abspath(os.path.join(abs_extract_dir, member_name))
            if os.path.commonpath([abs_extract_dir, dest_path]) != abs_extract_dir:
                raise ValueError(f"unsafe zip entry: {member_name}")
            if member.is_dir():
                os.makedirs(dest_path, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with zf.open(member, "r") as src, open(dest_path, "wb") as dst:
                shutil.copyfileobj(src, dst)


def _get_label_text(item: dict) -> Optional[str]:
    label_text = item.get("label")
    if label_text is None:
        label_text = item.get("text")
    if label_text is None:
        return None
    if not isinstance(label_text, str):
        label_text = str(label_text)
    label_text = label_text.strip()
    if not label_text:
        return None
    return label_text


# 创建路由
router = APIRouter(
    prefix="/dataset",
    tags=["数据集"],
    responses={
        404: {"description": _("未找到")},
        422: {"description": _("请求参数验证失败")},
    },
)


# 创建数据集
@router.post("/create")
@with_db_transaction()
def create_dataset(
    dataset_data: DatasetCreateRequest,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    创建新数据集
    """
    try:
        # 检查系统管理员是否设置了该OCR权重目录
        model_type = (
            dataset_data.model_type
        )  # 注：model_type是从1开始排序的不是从0开始 1= got_ocr 2= dotsocr 3= dolphin 4= deepseek_ocr 5= paddleocr_vl, 6= hunyuan_ocr, 7= deepseek_ocr2, 8= firered_ocr
        matched_model = OcrModel.get_all_models()[model_type - 1]
        if not matched_model:
            return error_response(_("系统不支持此模型"))
        mode_code = matched_model.get("code")
        model_name = matched_model.get("name")
        ocr_weight_dir = (
            SystemConfigDB.select_active().where(SystemConfigDB.config_key == f"{mode_code}_weights_dir").first()
        )
        if not ocr_weight_dir or not ocr_weight_dir.config_value:
            return error_response(t(_("管理员未配置 {model_name} 模型的权重目录")).format(model_name=model_name))

        # 检查数据集名称是否已存在
        existing_dataset = DatasetDB.select_active().where(DatasetDB.name == dataset_data.name).first()
        if existing_dataset:
            return error_response(_("数据集名称已存在"))

        # 创建数据集
        dataset = DatasetDB.create(
            name=dataset_data.name,
            description=dataset_data.description,
            model_type=dataset_data.model_type,
            created_by=current_user.user_id,
        )

        logger.info(f"用户 {current_user.username} 创建数据集: {dataset.name}")

        # 转换为响应模型
        # 使用构造函数替代弃用的from_orm方法
        response_data = DatasetResponse(
            id=dataset.id,
            name=dataset.name,
            description=dataset.description,
            model_type=dataset.model_type,
            pre_ocr_status=dataset.pre_ocr_status,
            pre_ocr_error=dataset.pre_ocr_error,
            total_images=dataset.total_images,
            train_images=dataset.train_images,
            val_images=dataset.val_images,
            total_tokens=dataset.total_tokens,
            train_tokens=dataset.train_tokens,
            val_tokens=dataset.val_tokens,
            last_upload_time=dataset.last_upload_time,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )
        return success_response(response_data)

    except Exception as e:
        logger.error(f"创建数据集失败: {str(e)}", exc_info=True)
        return error_response(_("创建数据集失败，请稍后重试"))


# 更新数据集
@router.post("/update")
@with_db_transaction()
def update_dataset(
    dataset_data: DatasetUpdateRequest,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    更新数据集（注意：目标模型不能修改）
    """
    try:
        # 检查数据集是否存在
        dataset = DatasetDB.select().where(DatasetDB.id == dataset_data.id).first()
        if not dataset:
            return error_response(_("数据集不存在"))

        # 检查数据集名称是否已存在（如果名称有变化）
        if dataset.name != dataset_data.name:
            existing_dataset = DatasetDB.select().where(DatasetDB.name == dataset_data.name).first()
            if existing_dataset:
                return error_response(_("数据集名称已存在"))

        # 更新数据集信息
        dataset.name = dataset_data.name
        dataset.description = dataset_data.description
        dataset.save()

        logger.info(f"用户 {current_user.username} 更新数据集: {dataset.name}")

        # 转换为响应模型
        # 使用构造函数替代弃用的from_orm方法
        response_data = DatasetResponse(
            id=dataset.id,
            name=dataset.name,
            description=dataset.description,
            model_type=dataset.model_type,
            pre_ocr_status=dataset.pre_ocr_status,
            total_images=dataset.total_images,
            train_images=dataset.train_images,
            val_images=dataset.val_images,
            total_tokens=dataset.total_tokens,
            train_tokens=dataset.train_tokens,
            val_tokens=dataset.val_tokens,
            last_upload_time=dataset.last_upload_time,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )
        return success_response(response_data)

    except Exception as e:
        logger.error(f"更新数据集失败: {str(e)}", exc_info=True)
        return error_response(_("更新数据集失败，请稍后重试"))


# 获取数据集列表，目前后端是一次性返第一页(5000条)数据，前端再重新自己分页
@router.post("/list")
def dataset_list(
    skip: int = Body(0, description="跳过数量"),
    limit: int = Body(5000, description="限制查询量"),
    model_type: Optional[int] = Body(None, description="目标模型"),
    keyword: Optional[str] = Body(None, description="搜索"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取数据集列表（支持分页和条件查询）
    """
    try:
        # 确保数据库连接已打开
        db_manager.get_connection()
        # 构建查询
        query = DatasetDB.select_active()

        # 按用户过滤
        query = query.where(DatasetDB.created_by == current_user.user_id)

        # 按名称关键字过滤
        if keyword and keyword != "":
            query = query.where(DatasetDB.name.contains(keyword))

        # 按目标模型过滤
        if model_type and model_type > 0:
            query = query.where(DatasetDB.model_type == model_type)

        # 排序和分页
        datasets = query.order_by(DatasetDB.created_at.desc()).offset(skip).limit(limit)

        dataset_list = [DatasetResponse.model_validate(dataset) for dataset in datasets]

        # 转换为响应模型列表
        data = {
            "dataset_list": dataset_list,
            "total": len(datasets),
            "ocr_models": OcrModel.get_all_models(),
            "pre_ocr_status": PreOCRStatus.get_all_status(),
        }

        return success_response(data)

    except Exception as e:
        logger.error(f"获取数据集列表失败: {str(e)}", exc_info=True)
        return error_response(_("获取数据集列表失败，请稍后重试"))


# 获取数据集详情
@router.get("/{dataset_id}")
@with_db_transaction(use_transaction=False)
def get_dataset_detail(dataset_id: int, current_user: CurrentUser = Depends(get_current_active_user)):
    """
    获取数据集详情
    """
    try:
        # 检查数据集是否存在
        dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
        if not dataset:
            return error_response(_("数据集不存在"))

        # 转换为响应模型
        # 使用 model_validate 替代弃用的 from_orm
        data = {
            "dataset": DatasetResponse.model_validate(dataset),
            "ocr_models": OcrModel.get_all_models(),
        }
        return success_response(data)

    except Exception as e:
        logger.error(f"获取数据集详情失败: {str(e)}", exc_info=True)
        return error_response(_("获取数据集详情失败，请稍后重试"))


@router.post("/{dataset_id}/upload")
async def upload_dataset_files(
    dataset_id: int,
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    上传数据集文件
    """
    # 保存数据集文件
    success, file_path, file_hash = await save_dataset_file(file, dataset_id)
    if not success:
        err_message = file_path  # 保存失败，返回错误信息
        return error_response(err_message)

    # 如果是图片文件，获取宽高尺寸；非图片文件宽高设为0
    if file.content_type.startswith("image"):
        # 图片文件，获取尺寸
        with Image.open(file_path) as img:
            width, height = img.size
    else:
        # "application/pdf"文件类型，尺寸先设为0，后续识别任务会更新尺寸
        width, height = 0, 0

    DatasetImageDB.create(
        dataset=dataset_id,
        file_path=file_path.replace(config.BASE_DIR, ""),  # 数据库存储相对路径
        file_name=file.filename,
        file_size=os.path.getsize(file_path),
        is_preocr_completed=False,
        train_data_type=0,
        width=width,
        height=height,
        tokens=0,
    )
    return success_response(_("文件上传成功"))


@router.post("/{dataset_id}/import")
@with_db_transaction()
async def import_dataset_zip(
    dataset_id: int,
    train_ratio: float = Form(..., description="Train split ratio from 0 to 100"),
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    Import dataset from a zip file with labels.jsonl at the root level.
    """
    dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
    if not dataset:
        return error_response("dataset not found")
    if dataset.created_by.id != current_user.user_id:
        return error_response("permission denied")

    preprocessing_status = PreOCRStatus.get_all_status().index(PreOCRStatus.preprocessing) + 1
    if dataset.pre_ocr_status == preprocessing_status:
        return error_response("dataset is preprocessing")

    if train_ratio < 0 or train_ratio > 100:
        return error_response("train_ratio must be between 0 and 100")

    success, zip_path, _ = await save_dataset_zip(file, dataset_id)
    if not success:
        return error_response(zip_path)

    import_root = os.path.dirname(zip_path)
    extract_dir = os.path.join(import_root, "extracted")
    os.makedirs(extract_dir, exist_ok=True)

    errors = []
    entries = []
    allowed_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff"}

    try:
        _safe_extract_zip(zip_path, extract_dir)
        labels_path = os.path.join(extract_dir, "labels.jsonl")
        if not os.path.isfile(labels_path):
            return error_response("labels.jsonl not found at zip root")

        with open(labels_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append({"line": line_no, "reason": f"invalid json: {exc}"})
                    continue

                image_name = item.get("image")
                if image_name is None:
                    image_name = item.get("images")  # 兼容"images":"xxx.jpg"
                if not isinstance(image_name, str):
                    errors.append({"line": line_no, "reason": "missing image field"})
                    continue
                image_name = image_name.strip()
                if not image_name:
                    errors.append({"line": line_no, "reason": "empty image field"})
                    continue
                if not _is_safe_relpath(image_name) or os.path.basename(image_name) != image_name:
                    errors.append({"line": line_no, "reason": f"invalid image path: {image_name}"})
                    continue

                ext = os.path.splitext(image_name)[1].lower()
                if ext not in allowed_exts:
                    errors.append({"line": line_no, "reason": f"unsupported image extension: {image_name}"})
                    continue

                label_text = _get_label_text(item)
                if label_text is None:
                    errors.append({"line": line_no, "reason": "missing label text"})
                    continue

                image_path = os.path.join(extract_dir, image_name)
                if not os.path.isfile(image_path):
                    errors.append({"line": line_no, "reason": f"image not found: {image_name}"})
                    continue

                entries.append(
                    {
                        "line": line_no,
                        "image_name": image_name,
                        "image_path": image_path,
                        "label": label_text,
                    }
                )

        if not entries:
            return error_response("no valid entries found")

        models = OcrModel.get_all_models()
        if dataset.model_type <= 0 or dataset.model_type > len(models):
            return error_response("model not found")
        matched_model = models[dataset.model_type - 1]
        model_code = matched_model.get("code")
        config_entry = SystemConfigDB.get_or_none(SystemConfigDB.config_key == f"{model_code}_weights_dir")
        if not config_entry or not config_entry.config_value:
            return error_response("model weights dir not configured")
        model_weights_dir = config_entry.config_value

        tokenizer = AutoTokenizer.from_pretrained(model_weights_dir, trust_remote_code=True)

        random.shuffle(entries)
        total = len(entries)
        train_count = int(round(total * train_ratio / 100.0))
        train_count = max(0, min(train_count, total))

        dataset_dir = get_dataset_directory(dataset_id)
        total_added = 0
        train_added = 0
        val_added = 0
        train_tokens = 0
        val_tokens = 0

        for idx, entry in enumerate(entries):
            train_data_type = 1 if idx < train_count else 2
            try:
                with Image.open(entry["image_path"]) as img:
                    width, height = img.size
            except Exception as exc:
                errors.append({"line": entry["line"], "reason": f"invalid image: {exc}"})
                continue

            try:
                tokens = len(tokenizer.tokenize(entry["label"]))
            except Exception as exc:
                errors.append({"line": entry["line"], "reason": f"tokenize failed: {exc}"})
                continue

            ext = os.path.splitext(entry["image_name"])[1].lower()
            new_filename = f"{uuid.uuid4().hex}{ext}"
            dest_path = os.path.join(dataset_dir, new_filename)
            try:
                shutil.copy2(entry["image_path"], dest_path)
            except Exception as exc:
                errors.append({"line": entry["line"], "reason": f"copy failed: {exc}"})
                continue

            DatasetImageDB.create(
                dataset=dataset_id,
                file_path=dest_path.replace(config.BASE_DIR, ""),
                file_name=entry["image_name"],
                file_size=os.path.getsize(dest_path),
                is_preocr_completed=True,
                train_data_type=train_data_type,
                width=width,
                height=height,
                tokens=tokens,
                ocr_label=entry["label"],
            )

            total_added += 1
            if train_data_type == 1:
                train_added += 1
                train_tokens += tokens
            else:
                val_added += 1
                val_tokens += tokens

        if total_added > 0:
            completed_status = PreOCRStatus.get_all_status().index(PreOCRStatus.completed) + 1
            dataset.total_images += total_added
            dataset.train_images += train_added
            dataset.val_images += val_added
            dataset.total_tokens += train_tokens + val_tokens
            dataset.train_tokens += train_tokens
            dataset.val_tokens += val_tokens
            dataset.pre_ocr_status = completed_status
            dataset.last_upload_time = datetime.now()
            dataset.save()

        summary = {
            "total": total_added,
            "train": train_added,
            "val": val_added,
            "train_tokens": train_tokens,
            "val_tokens": val_tokens,
            "skipped": max(0, len(entries) - total_added),
        }
        return success_response({"summary": summary, "errors": errors})
    except Exception as exc:
        logger.error(f"import dataset error: {str(exc)}", exc_info=True)
        return error_response("import failed")
    finally:
        shutil.rmtree(import_root, ignore_errors=True)


# 添加数据集预处理任务到gpu任务队列
@router.post("/{dataset_id}/preprocess")
async def dataset_preprocess(
    dataset_id: int,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    数据集预处理
    """
    dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
    if not dataset:
        return error_response(_("数据集不存在"))
    if dataset.created_by.id != current_user.user_id:
        return error_response(_("您没有权限对该数据集进行预处理"))

    # 更新数据及状态
    current_pre_ocr_status = PreOCRStatus.get_all_status()[dataset.pre_ocr_status - 1]
    if current_pre_ocr_status["code"] != PreOCRStatus.preprocessing["code"]:
        # 设置数据集预处理状态为 等待中
        pre_ocr_status = PreOCRStatus.get_all_status().index(PreOCRStatus.waiting) + 1
        dataset.pre_ocr_status = pre_ocr_status
        dataset.save()
        logger.info(f"数据集 {dataset_id} 状态更新为 {pre_ocr_status}")

    # 创建数据集预识别处理任务加入到GPU任务队列中
    # 仅添加到队列不一定会立即执行，实际由GPU任务队列监视器负责处理
    gpu_task_monitor.add_gpu_task(
        name=f"ocr预识别-数据集{dataset_id}",
        task_type="preocr",
        handler="kalorda.core.dataset_preocr.preocr_with_vlm_model",
        params={"dataset_id": dataset_id},
        correlation_id=dataset_id,  # 关联数据集ID，用于查询
        can_retry=True,
        run_times_limit=3,
    )
    return success_response(True)


# 获取数据集文件列表
@router.get("/{dataset_id}/images")
def get_dataset_images(
    dataset_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=5, le=50),
    data_type: Optional[int] = Query(None, description="训练数据分类0=未分类1=微调数据2=验证数据"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    date_ranges: Optional[str] = Query(None, description="日期范围，格式：yyyy-MM-dd,yyyy-MM-dd"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取数据集文件列表
    """
    try:
        # 检查数据集是否存在
        dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
        if not dataset:
            return error_response(_("数据集不存在"))
        if dataset.created_by.id != current_user.user_id:
            return error_response(_("您没有权限查看该数据集的文件列表"))

        # 构建查询
        query = DatasetImageDB.select_active().where(DatasetImageDB.dataset == dataset_id)
        if data_type is not None:
            query = query.where(DatasetImageDB.train_data_type == data_type)
        if keyword is not None and len(keyword.strip()) > 0:
            query = query.where(DatasetImageDB.ocr_label.contains(keyword))
        logger.info(
            f"获取数据集文件列表，数据集ID：{dataset_id}，日期范围：{date_ranges}，数据类型：{data_type}，关键词：{keyword}"
        )
        if date_ranges is not None:
            try:
                start_date, end_date = date_ranges.split(",")
                query = query.where(DatasetImageDB.created_at.between(start_date, end_date))
            except ValueError:
                return error_response(_("日期范围格式错误，应为yyyy-MM-dd,yyyy-MM-dd"))

        # 排序
        query = query.order_by(DatasetImageDB.created_at.desc())

        # 分页
        total = query.count()
        images = query.paginate(page, page_size)

        # 转换为响应模型列表
        image_responses = []
        for image in images:
            response = DatasetImageResponse(
                id=image.id,
                dataset_id=image.dataset.id,
                file_path=image.file_path,
                file_name=image.file_name,
                file_size=image.file_size,
                width=image.width,
                height=image.height,
                tokens=image.tokens,
                ocr_result=image.ocr_result,
                ocr_label=image.ocr_label,
                is_preocr_completed=image.is_preocr_completed,
                is_correct=image.is_correct,
                train_data_type=image.train_data_type,
                processed_at=image.processed_at,
                created_at=image.created_at,
                updated_at=image.updated_at,
            )
            image_responses.append(response)

        # 构建分页响应
        response = DatasetImagePageResponse(total=total, page=page, page_size=page_size, images=image_responses)

        return success_response(response)

    except Exception as e:
        logger.error(f"获取数据集文件列表失败: {str(e)}", exc_info=True)
        return error_response(_("获取数据集文件列表失败，请稍后重试"))


# 仅返回图片序列id列表
@router.get("/label/image_id_list")
def get_label_image_id_list(
    dataset_id: int,
    data_type: Optional[int] = Query(None, description="训练数据分类0=未分类1=微调数据2=验证数据"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    date_ranges: Optional[str] = Query(None, description="日期范围，格式：yyyy-MM-dd,yyyy-MM-dd"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取数据集文件列表，仅返回图片序列id列表
    """
    dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
    if not dataset:
        return error_response(_("数据集不存在"))

    # 为了兼容审核员等其他人员审核，这里不要检查是否是本人的数据集了
    # if dataset.created_by.id != current_user.user_id:
    #     return error_response(_("您没有权限查看该数据集的文件列表"))
    # 构建查询
    query = (
        DatasetImageDB.select_active()
        .select(DatasetImageDB.id)
        .where((DatasetImageDB.dataset == dataset_id) & (DatasetImageDB.is_preocr_completed == 1))  # 仅返预处理完成的
    )
    if data_type is not None:
        query = query.where(DatasetImageDB.train_data_type == data_type)
    if keyword is not None and len(keyword.strip()) > 0:
        query = query.where(DatasetImageDB.ocr_label.contains(keyword))

    if date_ranges is not None:
        try:
            start_date, end_date = date_ranges.split(",")
            query = query.where(DatasetImageDB.created_at.between(start_date, end_date))
        except ValueError:
            return error_response(_("日期范围格式错误，应为yyyy-MM-dd,yyyy-MM-dd"))

    # 排序
    image_list = query.order_by(DatasetImageDB.created_at.desc())
    image_id_list = []
    for image in image_list:
        image_id_list.append(image.id)

    matched_model = OcrModel.get_all_models()[dataset.model_type - 1]
    if not matched_model:
        logger.info(f"模型不存在: model_type={dataset.model_type}")
        return

    if matched_model["code"] == "got_ocr":
        category_list = GotOCRCategory.get_all_categories()
    elif matched_model["code"] == "dotsocr":
        category_list = DotsOCRCategory.get_all_categories()
    elif matched_model["code"] == "dolphin":
        category_list = DolphinCategory.get_all_categories()
    elif matched_model["code"] == "deepseek_ocr":
        category_list = DeepseekOCRCategory.get_all_categories()
    elif matched_model["code"] == "deepseek_ocr2":
        category_list = DeepseekOCR2Category.get_all_categories()
    elif matched_model["code"] == "paddleocr_vl":
        category_list = PaddleOCRVLCategory.get_all_categories()
    elif matched_model["code"] == "hunyuan_vl":
        category_list = HunyuanOCRCategory.get_all_categories()
    elif matched_model["code"] == "firered_vl":
        category_list = FireRedOCRCategory.get_all_categories()
    else:
        category_list = []

    data = {
        "image_id_list": image_id_list,
        "category_list": category_list,
        "dataset": DatasetResponse.model_validate(dataset),
    }

    return success_response(data)


def PILimage_to_base64(file_path: str, format="JPEG", quality=100):
    buffered = BytesIO()
    image = Image.open(file_path).convert("RGB")
    image.save(buffered, format=format, quality=quality)
    base64_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
    return f"data:image/{format.lower()};base64,{base64_str}"


@router.post("/label/image_url_list")
def get_label_image_url_list(
    dataset_id: int = Body(..., description="数据集id"),
    image_ids: List[int] = Body(..., description="图片序列id列表"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    单纯图片id换url
    """
    dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
    if not dataset:
        return error_response(_("数据集不存在"))

    query = (
        DatasetImageDB.select_active()
        .select(DatasetImageDB.id, DatasetImageDB.file_path, DatasetImageDB.train_data_type)
        .where(DatasetImageDB.dataset == dataset_id)
        .where(DatasetImageDB.id.in_(image_ids))
    )
    data = []
    for image in query:
        data.append(
            {
                "id": image.id,
                "url": image.file_path,
                "train_data_type": image.train_data_type,
                # "url": PILimage_to_base64(image.file_path),
            }
        )
    return success_response(data)


# 获取当个图片完整信息
@router.get("/label/image_info/{image_id}")
def get_image_info(
    image_id: int,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取单个图片完整信息
    """
    # 检查文件是否存在
    image = DatasetImageDB.select_active().where(DatasetImageDB.id == image_id).first()
    if not image:
        return error_response(_("数据不存在"))

    data = {
        "image_info": DatasetImageResponse.model_validate(image),
        "base_64": PILimage_to_base64(f"{config.BASE_DIR}{image.file_path}"),
    }

    return success_response(data)


# 更新数据集文件（数据校对）
@router.post("/images/{image_id}/update")
@with_db_transaction()
def update_dataset_image(
    image_id: int,
    image_data: DatasetImageUpdateRequest,
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    更新数据集文件（数据校对）
    """
    try:
        # 检查文件是否存在
        image = DatasetImageDB.select_active().where(DatasetImageDB.id == image_id).first()
        if not image:
            return error_response(_("文件不存在"))

        # 获取数据集
        dataset = image.dataset.get()

        # 更新文件信息
        # 1. 更新ocr_label而不是ocr_result，保持原始识别结果不变
        if image_data.ocr_label is not None:
            image.ocr_label = image_data.ocr_label

        # 2. 更新正确性标记
        # image.is_preocr_completed = image_data.is_preocr_completed
        image.is_correct = image_data.is_correct

        # 3. 更新训练数据标记
        # 根据用户需求：修改了的就是训练数据，不修改的表示是验证数据
        # 这里直接使用请求中提供的train_data_type值
        image.train_data_type = image_data.train_data_type

        image.save()

        # 更新数据集的统计信息
        # 重新计算训练和验证数据数量
        train_count = (
            DatasetImageDB.select_active()
            .where((DatasetImageDB.dataset == dataset.id) & (DatasetImageDB.train_data_type == 1))
            .count()
        )

        val_count = (
            DatasetImageDB.select_active()
            .where((DatasetImageDB.dataset == dataset.id) & (DatasetImageDB.train_data_type == 2))
            .count()
        )

        # 重新计算tokens数量
        train_tokens = 0
        val_tokens = 0

        train_images = DatasetImageDB.select_active().where(
            (DatasetImageDB.dataset == dataset.id) & (DatasetImageDB.train_data_type == 1)
        )

        for train_image in train_images:
            if train_image.ocr_result:
                train_tokens += len(train_image.ocr_result)

        val_images = DatasetImageDB.select_active().where(
            (DatasetImageDB.dataset == dataset.id) & (DatasetImageDB.train_data_type == 2)
        )

        for val_image in val_images:
            if val_image.ocr_result:
                val_tokens += len(val_image.ocr_result)

        # 更新数据集
        dataset.train_images = train_count
        dataset.val_images = val_count
        dataset.total_images = train_count + val_count
        dataset.train_tokens = train_tokens
        dataset.val_tokens = val_tokens
        dataset.total_tokens = train_tokens + val_tokens
        dataset.save()

        logger.info(f"用户 {current_user.username} 更新了数据集文件: {image.file_name}")

        # 转换为响应模型
        response = DatasetImageResponse(
            id=image.id,
            dataset_id=image.dataset.id,
            file_path=image.file_path,
            file_name=image.file_name,
            file_size=image.file_size,
            width=image.width,
            height=image.height,
            ocr_result=image.ocr_result,
            ocr_label=image.ocr_label,
            is_preocr_completed=image.is_preocr_completed,
            is_correct=image.is_correct,
            train_data_type=image.train_data_type,
            processed_at=image.processed_at,
            created_at=image.created_at,
            updated_at=image.updated_at,
        )

        return success_response(response)

    except Exception as e:
        logger.error(f"更新数据集文件失败: {str(e)}", exc_info=True)
        return error_response(_("更新数据集文件失败，请稍后重试"))


# 删除数据集
@router.post("/delete")
@with_db_transaction()
def delete_dataset(
    dataset_id: int = Body(..., description="数据集ID"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    删除数据集
    """
    try:
        # 检查数据集是否存在
        dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
        if not dataset:
            return error_response(_("数据集不存在"))

        if dataset.created_by.id != current_user.user_id:
            return error_response(_("您没有权限删除此数据集"))

        # 软删除数据集
        dataset.is_deleted = True
        dataset.save()

        # 软删除相关的所有图片
        DatasetImageDB.update(is_deleted=True).where(DatasetImageDB.dataset == dataset_id).execute()

        logger.info(f"用户 {current_user.username} 删除了数据集: {dataset.name}")

        # 如果有关联的gpu任务则取消
        gpu_task_monitor.del_gpu_task(gpu_task_type="preocr", correlation_id=dataset_id)

        return success_response({"id": dataset_id})

    except Exception as e:
        logger.error(f"删除数据集失败: {str(e)}", exc_info=True)
        return error_response(_("删除数据集失败，请稍后重试"))


# 删除数据集中的数据
@router.post("/{dataset_id}/images/delete")
@with_db_transaction()
def delete_dataset_images(
    dataset_id: int,
    image_ids: List[int] = Body(..., description="要删除的图片ID列表"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    删除数据集中的数据
    """
    try:
        # 检查数据集是否存在
        dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
        if not dataset:
            return error_response(_("数据集不存在"))
        if dataset.created_by.id != current_user.user_id:
            return error_response(_("您没有权限删除此数据集中的数据"))

        # 检查文件是否存在
        images = DatasetImageDB.select_active().where(DatasetImageDB.id.in_(image_ids))
        if not images or len(images) == 0:
            return error_response(_("没有要删除的数据"))

        # 累计被删除的图片数量和tokens数量
        total_images = len(images)
        train_images = 0
        val_images = 0
        total_tokens = 0
        train_tokens = 0
        val_tokens = 0

        for image in images:
            if image.train_data_type == 1:  # 训练数据
                train_images += 1
                train_tokens += image.tokens
            elif image.train_data_type == 2:  # 验证数据
                val_images += 1
                val_tokens += image.tokens

            total_tokens += image.tokens
            image.is_deleted = True
            image.save()

        # 更新数据集
        dataset.total_images -= total_images
        dataset.train_images -= train_images
        dataset.val_images -= val_images

        dataset.total_tokens -= total_tokens
        dataset.train_tokens -= train_tokens
        dataset.val_tokens -= val_tokens

        if dataset.total_images <= 0:
            dataset.total_images = 0
            dataset.train_images = 0
            dataset.val_images = 0
            dataset.train_tokens = 0
            dataset.val_tokens = 0
            dataset.total_tokens = 0
            pre_ocr_status = PreOCRStatus.get_all_status().index(PreOCRStatus.not_start) + 1
            dataset.pre_ocr_status = pre_ocr_status

        dataset.save()

        logger.info(f"用户 {current_user.username} 删除了数据集数据: {total_images} 条, 共 {total_tokens} 个tokens")

        data = {"ok": True, "dataset": DatasetResponse.model_validate(dataset)}
        return success_response(data)

    except Exception as e:
        logger.error(f"删除数据集数据失败: {str(e)}", exc_info=True)
        return error_response(_("数据删除失败"))


# 移动数据集中的数据
@router.post("/{dataset_id}/images/move")
@with_db_transaction()
def move_dataset_images(
    dataset_id: int,
    target_dataset_id: int = Body(..., description="目标数据集ID"),
    image_ids: List[int] = Body(..., description="要移动的图片ID列表"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    移动数据集中的数据
    """
    try:
        # 检查目标数据集是否存在
        target_dataset = DatasetDB.select_active().where(DatasetDB.id == target_dataset_id).first()
        if not target_dataset:
            return error_response(_("目标数据集不存在"))
        if target_dataset.created_by.id != current_user.user_id:
            return error_response(_("您没有权限移动数据到此目标数据集"))
        if target_dataset.pre_ocr_status == PreOCRStatus.get_all_status().index(PreOCRStatus.preprocessing) + 1:
            return error_response(_("目标数据集预正在预识别中请稍候重试"))

        # 检查数据集是否存在
        dataset = DatasetDB.select_active().where(DatasetDB.id == dataset_id).first()
        if not dataset:
            return error_response(_("数据集不存在"))
        if dataset.created_by.id != current_user.user_id:
            return error_response(_("您没有权限删除此数据集中的数据"))
        if dataset.pre_ocr_status == PreOCRStatus.get_all_status().index(PreOCRStatus.preprocessing) + 1:
            return error_response(_("数据集预正在预识别中请稍候重试"))

        # 检查文件是否存在
        images = DatasetImageDB.select_active().where(DatasetImageDB.id.in_(image_ids))
        if not images or len(images) == 0:
            return error_response(_("没有要移动的数据"))

        # 累计被移动的图片数量和tokens数量
        total_images = len(images)
        train_images = 0
        val_images = 0
        total_tokens = 0
        train_tokens = 0
        val_tokens = 0

        for image in images:
            if image.train_data_type == 1:  # 训练数据
                train_images += 1
                train_tokens += image.tokens
            elif image.train_data_type == 2:  # 验证数据
                val_images += 1
                val_tokens += image.tokens

            total_tokens += image.tokens
            image.dataset_id = target_dataset_id  # 改变数据的关联数据集id
            image.save()

        # 更新数据集，和删除数据集逻辑类似，被移动数据集信息修改
        dataset.total_images -= total_images
        dataset.train_images -= train_images
        dataset.val_images -= val_images

        dataset.total_tokens -= total_tokens
        dataset.train_tokens -= train_tokens
        dataset.val_tokens -= val_tokens

        if dataset.total_images <= 0:
            dataset.total_images = 0
            dataset.train_images = 0
            dataset.val_images = 0
            dataset.train_tokens = 0
            dataset.val_tokens = 0
            dataset.total_tokens = 0
            pre_ocr_status = PreOCRStatus.get_all_status().index(PreOCRStatus.not_start) + 1
            dataset.pre_ocr_status = pre_ocr_status

        dataset.save()

        # 更新目标数据集
        target_dataset.total_images += total_images
        target_dataset.train_images += train_images
        target_dataset.val_images += val_images

        target_dataset.total_tokens += total_tokens
        target_dataset.train_tokens += train_tokens
        target_dataset.val_tokens += val_tokens
        if target_dataset.pre_ocr_status == PreOCRStatus.get_all_status().index(PreOCRStatus.not_start) + 1:
            pre_ocr_status = PreOCRStatus.get_all_status().index(PreOCRStatus.completed) + 1
            target_dataset.pre_ocr_status = pre_ocr_status

        target_dataset.save()

        logger.info(f"用户 {current_user.username} 移动了数据集数据: {total_images} 条, 共 {total_tokens} 个tokens")

        data = {"ok": True, "dataset": DatasetResponse.model_validate(dataset)}
        return success_response(data)

    except Exception as e:
        logger.error(f"移动数据集数据失败: {str(e)}", exc_info=True)
        return error_response(_("数据移动失败"))


# 保存图片标注结果
@router.post("/label/save")
@with_db_transaction()
def label_save(
    image_id: int = Body(..., description="图片ID"),
    data_type: int = Body(..., description="数据类型 1: 训练数据 2: 验证数据"),
    ocr_label: object = Body(..., description="OCR标注数据"),
    current_user: CurrentUser = Depends(get_annotator_user),  # 标注员权限
):
    if ocr_label is None or len(ocr_label.strip()) == 0:
        return error_response(_("OCR标注数据不能为空"))
    # 检查图片是否存在
    image = DatasetImageDB.select_active().where(DatasetImageDB.id == image_id).first()
    if not image:
        return error_response(_("图片不存在"))
    dataset = DatasetDB.select_active().where(DatasetDB.id == image.dataset_id).first()
    if not dataset:
        return error_response(_("数据集不存在"))
    if dataset.created_by.id != current_user.user_id:
        return error_response(_("您没有权限标注此图片"))

    # 通过找到对应的模型，加载transformers分词器计算标注文本的tokens数量
    matched_model = OcrModel.get_all_models()[dataset.model_type - 1]
    if not matched_model:
        return error_response(_("模型不存在"))
    model_code = matched_model.get("code")
    model_weights_dir = SystemConfigDB.get_or_none(
        SystemConfigDB.config_key == f"{model_code}_weights_dir"
    ).config_value
    if not model_weights_dir:
        return error_response(_("模型权重目录不存在"))

    tokenizer = AutoTokenizer.from_pretrained(model_weights_dir, trust_remote_code=True)
    tokens = tokenizer.tokenize(ocr_label.strip())
    old_tokens_length = image.tokens  # 旧token数量，注：数据库image表里tokens字段是表示token的数量，不是tokens内容
    tokens_length = len(tokens)  # 新token数量
    logger.info(f"用户 {current_user.username} 标注了图片 {image_id}，tokens数量为 {tokens_length}")

    old_data_type = image.train_data_type
    image.train_data_type = 1 if data_type == 1 else 2  # 1: 训练数据 2: 验证数据
    image.ocr_label = ocr_label
    image.tokens = tokens_length  # 更新token数量，注：数据库image表里tokens字段是表示token的数量，不是tokens内容
    image.save()

    # 更新数据集信息
    if old_data_type == 0:  # 之前未标注
        dataset.train_images += 1 if data_type == 1 else 0
        dataset.val_images += 1 if data_type == 2 else 0
        dataset.train_tokens += tokens_length if data_type == 1 else 0
        dataset.val_tokens += tokens_length if data_type == 2 else 0
    elif old_data_type == 1:  # 之前是训练数据
        dataset.train_images += 0 if data_type == 1 else -1
        dataset.val_images += 1 if data_type == 2 else 0
        dataset.train_tokens += 0 if data_type == 1 else -1 * old_tokens_length
        dataset.val_tokens += tokens_length if data_type == 2 else 0
    elif old_data_type == 2:  # 之前是验证数据
        dataset.train_images += 1 if data_type == 1 else 0
        dataset.val_images += 0 if data_type == 2 else -1
        dataset.train_tokens += tokens_length if data_type == 1 else 0
        dataset.val_tokens += 0 if data_type == 2 else -1 * old_tokens_length

    # 更新数据集4项信息
    DatasetDB.update(
        train_images=dataset.train_images,
        val_images=dataset.val_images,
        train_tokens=dataset.train_tokens,
        val_tokens=dataset.val_tokens,
    ).where(DatasetDB.id == dataset.id).execute()

    return success_response(
        {
            "dataset": {
                "train_images": dataset.train_images,
                "val_images": dataset.val_images,
                "train_tokens": dataset.train_tokens,
                "val_tokens": dataset.val_tokens,
            },
            "message": _("标注保存成功"),
        }
    )
