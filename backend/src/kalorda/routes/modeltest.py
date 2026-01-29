import asyncio
import json
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)
from pdf2image import convert_from_path
from PIL import Image

import kalorda.core.gpu_task_monitor as gpu_task_monitor
from kalorda.config import config
from kalorda.constant import (
    DeepseekOCRCategory,
    DeepseekOCR2Category,
    DolphinCategory,
    DotsOCRCategory,
    GotOCRCategory,
    HunyuanOCRCategory,
    OCRBaseCategory,
    OcrModel,
    PaddleOCRVLCategory,
    TestOCRStatus,
    TrainingStatus,
)
from kalorda.database.database import (
    FineTuneTaskDB,
    TestOCRFileDB,
    TestOCRResultDB,
    TrainingRunDB,
    UserDB,
    db_manager,
    with_db_transaction,
)
from kalorda.models.modeltest import TestOCRFileResponse
from kalorda.utils.api_response import error_response, success_response
from kalorda.utils.data_verify import is_valid_email
from kalorda.utils.email_send import send_email
from kalorda.utils.i18n import _, t
from kalorda.utils.logger import logger
from kalorda.utils.security import CurrentUser, get_current_active_user, get_current_user
from kalorda.utils.upload_file import save_test_file

# 创建路由器
router = APIRouter(prefix="/modeltest", tags=["modeltest"])


# 测试文件上传接口
@router.post("/file/upload")
@with_db_transaction()
async def upload_test_file(
    file: UploadFile = File(...),
    remark: Optional[str] = Form(None, max_length=100),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    上传测试文件

    Args:
        file: 上传的文件
        remark: 文件备注（可选）
        current_user: 当前登录用户

    Returns:
        上传结果
    """
    try:
        # 保存文件
        success, file_path, file_hash = await save_test_file(file)
        if not success:
            err_message = file_path  # 保存失败，返回错误信息
            return error_response(err_message)

        # 检查文件是否已存在
        existing_file = TestOCRFileDB.select().where(TestOCRFileDB.file_hash == file_hash).first()
        if existing_file:
            os.remove(file_path)
            TestOCRFileDB.update(
                updated_at=datetime.now(),
                original_filename=file.filename,
                is_deleted=False,
            ).where(TestOCRFileDB.id == existing_file.id).execute()
            # TestOCRResultDB.update(
            #     status=TestOCRStatus.not_start["value"],
            #     ocr_result=None,
            # ).where(TestOCRResultDB.test_file == existing_file.id).execute()
            exist_file_info = TestOCRFileResponse(
                id=existing_file.id,
                original_filename=existing_file.original_filename,
                file_path=existing_file.file_path.replace(config.BASE_DIR, ""),
                file_size=existing_file.file_size,
                remark=existing_file.remark,
                images=json.loads(existing_file.images_info),
                create_at=existing_file.created_at,
                update_at=existing_file.updated_at,
            )
            return success_response(exist_file_info, _("文件已存在"))

        if not success:
            return error_response(t(_("文件上传失败:{file_path}")).format(file_path=file_path))

        # 文件转图片信息
        images = []  # 初始为空数组，后续处理时会更新

        # 如果是图片文件，获取宽高尺寸；非图片文件宽高设为0
        if file.content_type.startswith("image"):
            # 图片文件，获取尺寸
            with Image.open(file_path) as img:
                width, height = img.size
                images.append(
                    {
                        "image_uuid": str(uuid.uuid4()),
                        # "image_name": file.filename,
                        "image_path": file_path.replace(config.BASE_DIR, ""),
                        "image_width": width,
                        "image_height": height,
                        "image_size": os.path.getsize(file_path),
                    }
                )
        else:
            # "application/pdf"文件类型
            logger.info(f"file.content_type: {file.content_type}, file_path: {os.path.abspath(file_path)}")
            try:
                pdf_pages = convert_from_path(file_path, dpi=200, fmt="jpg", size=(2048, None))
            except Exception as e:
                logger.error(f"convert pdf to images error: {str(e)}", exc_info=True)
                return error_response(_("文件上传失败"))

            for i, page in enumerate(pdf_pages):
                # 生成唯一的文件名
                image_path = file_path.replace(".pdf", f"_{i}.jpg")
                # image_name = f"{file.filename.split('.')[0]}_{i}.jpg"
                # 保存图片
                page.save(image_path, "JPEG")
                # 获取图片信息
                img = Image.open(image_path)
                width, height = img.size
                img.close()
                images.append(
                    {
                        "image_uuid": str(uuid.uuid4()),
                        # "image_name": image_name,
                        "image_path": image_path.replace(config.BASE_DIR, ""),
                        "image_width": width,
                        "image_height": height,
                        "image_size": os.path.getsize(image_path),
                    }
                )
        # 保存到数据库
        test_file = TestOCRFileDB.create(
            original_filename=file.filename,
            file_path=file_path.replace(config.BASE_DIR, ""),
            file_hash=file_hash,
            file_size=os.path.getsize(file_path),
            images_info=json.dumps(images),
            remark=remark,
            uploaded_by=current_user.user_id,
        )

        file_info = TestOCRFileResponse(
            id=test_file.id,
            original_filename=test_file.original_filename,
            file_path=test_file.file_path,
            file_size=test_file.file_size,
            remark=test_file.remark,
            images=json.loads(test_file.images_info),
            create_at=test_file.created_at,
            update_at=test_file.updated_at,
        )
        return success_response(file_info, _("文件上传成功"))
    except Exception as e:
        logger.error(f"upload test file error: {str(e)}", exc_info=True)
        return error_response(_("文件上传失败"))


# 测试文件列表查询接口
@router.get("/file/list")
@with_db_transaction(use_transaction=False)
async def get_test_file_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=1000),
    keyword: Optional[str] = Query(None, description="搜索备注关键词"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取测试文件列表，支持关键词搜索文件备注

    Args:
        page: 页码
        page_size: 每页大小
        keyword: 搜索关键词
        current_user: 当前登录用户

    Returns:
        文件列表
    """
    try:
        # 构建查询
        query = TestOCRFileDB.select_active()

        # 如果有关键词，添加搜索条件
        if keyword:
            query = query.where(
                TestOCRFileDB.original_filename.contains(keyword) | TestOCRFileDB.remark.contains(keyword)
            )
        query = query.where(TestOCRFileDB.uploaded_by == current_user.user_id)
        # 计算总数
        total = query.count()

        # 分页查询
        offset = (page - 1) * page_size
        files = query.order_by(TestOCRFileDB.updated_at.desc(), TestOCRFileDB.id.desc()).offset(offset).limit(page_size)

        # 构建返回数据
        file_list = []
        for file in files:
            file_info = TestOCRFileResponse(
                id=file.id,
                original_filename=file.original_filename,
                file_path=file.file_path,
                file_size=file.file_size,
                remark=file.remark,
                images=json.loads(file.images_info),
                create_at=file.created_at,
                update_at=file.updated_at,
            )
            file_list.append(file_info)

        return success_response(
            {"list": file_list, "total": total, "page": page, "page_size": page_size},
            "获取文件列表成功",
        )

    except Exception as e:
        logger.error(f"获取测试文件列表失败: {str(e)}", exc_info=True)
        return error_response(_("获取文件列表失败"))


# 测试文件批量删除接口
@router.post("/file/delete")
@with_db_transaction()
async def delete_test_files(
    file_ids: List[int] = Body(..., description="要删除的文件ID列表"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    批量删除测试文件

    Args:
        file_ids: 要删除的文件ID列表
        current_user: 当前登录用户

    Returns:
        删除结果
    """
    try:
        # 查询要删除的文件
        TestOCRFileDB.select_active().where(TestOCRFileDB.id.in_(file_ids))
        # files = TestOCRFileDB.select_active().where(TestOCRFileDB.id.in_(file_ids))

        # 记录要删除的文件路径，用于物理删除
        # del_file_path = []
        # for file in files:
        #     del_file_path.append(file.file_path)

        # 软删除文件记录
        deleted_count = (
            TestOCRFileDB.update(is_deleted=True, updated_at=datetime.now())
            .where(TestOCRFileDB.id.in_(file_ids))
            .execute()
        )

        # 同时软删除相关的OCR结果
        # TestOCRResultDB.update(is_deleted=True, updated_at=datetime.now()).where(
        #     TestOCRResultDB.test_file.in_(file_ids)
        # ).execute()

        # 异步删除物理文件（非阻塞）
        # async def delete_physical_files():
        #     for file_path in del_file_path:
        #         try:
        #             if os.path.exists(file_path):
        #                 os.remove(file_path)
        #                 logger.info(f"物理删除文件成功: {file_path}")
        #         except Exception as e:
        #             logger.error(
        #                 f"物理删除文件失败 {file_path}: {str(e)}", exc_info=True
        #             )

        # 在后台执行物理删除
        # asyncio.create_task(delete_physical_files())

        return success_response(
            {"deleted_count": deleted_count},
            "文件删除成功",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除文件失败: {str(e)}", exc_info=True)
        return error_response(_("文件删除失败"))


# 修改测试文件备注的接口
@router.post("/file/update")
@with_db_transaction()
async def update_test_file(
    file_id: int = Body(..., description="文件ID"),
    file_name: str = Body(..., description="文件名称"),
    remark: Optional[str] = Body(None, description="新的备注内容"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    修改测试文件的备注

    Args:
        file_id: 文件ID
        file_name: 文件名称
        remark: 新的备注内容
        current_user: 当前登录用户

    Returns:
        更新结果
    """
    try:
        if not file_name or file_name.strip() == "":
            return error_response("文件名称不能为空")

        # 查询文件
        file = (
            TestOCRFileDB.select_active()
            .where((TestOCRFileDB.id == file_id) & (TestOCRFileDB.uploaded_by == current_user.user_id))
            .first()
        )

        if not file:
            return error_response(_("文件不存在"))

        # 更新备注
        ext_name = file.original_filename.split(".")[-1]
        if not file_name.endswith(f".{ext_name}"):
            file_name = f"{file_name}.{ext_name}"
        file.original_filename = file_name
        file.remark = remark
        file.last_update_date = datetime.now()
        file.save()

        logger.info(f"用户 {current_user.username} 更新了文件 {file.id} 的备注")

        return success_response(
            {
                "file_id": file.id,
                "original_filename": file.original_filename,
                "remark": file.remark,
            },
            _("更新成功"),
        )
    except Exception as e:
        logger.error(f"更新文件失败: {str(e)}", exc_info=True)
        return error_response(_("更新失败"))


# 获取已训练完成的模型列表
@router.get("/model/list")
@with_db_transaction(use_transaction=False)
async def get_completed_models(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=1000),
    training_type: Optional[str] = Query(None, description="训练类型筛选"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    """
    获取所有已训练完成的模型列表

    Args:
        page: 页码
        page_size: 每页大小
        training_type: 训练类型筛选（可选）
        current_user: 当前登录用户

    Returns:
        模型列表
    """
    try:
        # 构建返回数据
        model_list = []
        # 1. 先获取所有基础模型
        base_models = OcrModel.get_all_models()
        for model in base_models:
            # 返回基础模型数据
            model_list.append(
                {
                    "model_code": model["code"],  # 基础模型这里用code作为id
                    "model_name": model["name"],
                    "training_type": "base",
                }
            )

        if training_type and training_type == "base":
            return success_response(
                {
                    "list": model_list,
                    "total": len(model_list),
                    "page": 1,
                    "page_size": page_size,
                },
                _("获取模型列表成功"),
            )

        # 2. 再获取所有已训练完成的模型
        query = TrainingRunDB.select_active().where(TrainingRunDB.status == TrainingStatus.completed["value"])
        query = query.where(TrainingRunDB.created_by == current_user.user_id)

        if training_type and training_type in ["lora", "full"]:
            query = query.where(TrainingRunDB.training_type == training_type)
            model_list = []

        # 计算总数
        total = query.count() + len(model_list)

        # 分页查询
        offset = (page - 1) * page_size
        training_run_models = query.order_by(TrainingRunDB.end_time.desc()).offset(offset).limit(page_size)

        for model in training_run_models:
            # 获取关联的任务信息以获取模型类型
            task = None
            base_model_code = ""
            try:
                task = FineTuneTaskDB.select_active().where(FineTuneTaskDB.id == model.task).first()
                base_model_code = base_models[task.target_model - 1]["code"]
            except Exception as e:
                logger.error(f"获取任务信息失败: {str(e)}", exc_info=True)
                pass

            # 返回已训练模型，注意：字段信息比基础模型信息多，前端需要区分
            model_code = f"{base_model_code}:{model.id}:{model.model_code_suffix}"
            # 已训练模型的code采用training_run_id+区分后缀进行拼接
            model_info = {
                "model_code": model_code,
                "model_name": model.model_name,
                "training_type": model.training_type,
                "id": model.id,
                "task_id": task.id if task else None,
                "task_name": task.name if task else None,
                "run_name": model.run_name,
                "model_code_suffix": model.model_code_suffix,
                "start_time": model.start_time.isoformat() if model.start_time else None,
                "end_time": model.end_time.isoformat() if model.end_time else None,
                "duration": model.duration,
                "epochs": model.num_epochs,
                "learning_rate": model.learning_rate,
                "batch_size": model.batch_size,
            }
            model_list.append(model_info)

        return success_response(
            {"list": model_list, "total": total, "page": page, "page_size": page_size},
            _("获取模型列表成功"),
        )

    except Exception as e:
        logger.error(f"获取已训练模型列表失败: {str(e)}", exc_info=True)
        return error_response(_("获取模型列表失败"))


# 创建测试的文件中全部图片的ocr任务信息
@router.post("/ocr/create")
@with_db_transaction()
async def ocr_create(
    file_id_list: List[int] = Body(..., description="文件ID列表"),
    model_list: List[dict] = Body(..., description="模型列表"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not file_id_list:
        return error_response(_("文件ID列表为空"))
    if not model_list:
        return error_response(_("模型列表为空"))

    test_files = (
        TestOCRFileDB.select_active()
        .select(
            TestOCRFileDB.id,
            TestOCRFileDB.original_filename,
            TestOCRFileDB.images_info,
            TestOCRFileDB.file_size,
        )
        .where(TestOCRFileDB.id.in_(file_id_list))
        .where(TestOCRFileDB.uploaded_by == current_user.user_id)
        .order_by(TestOCRFileDB.updated_at.desc(), TestOCRFileDB.id.desc())
    )
    if not test_files:
        return error_response(_("文件ID列表不包含有效的测试文件"))

    create_count = 0
    exist_count = 0
    not_start_count = 0
    for test_file in test_files:
        images = json.loads(test_file.images_info)
        db_images = (
            TestOCRResultDB.select_active()
            .select(
                TestOCRResultDB.id,
                TestOCRResultDB.image_uuid,
                TestOCRResultDB.model_code,
                TestOCRResultDB.status,
            )
            .where(TestOCRResultDB.test_file == test_file.id)
            .where(TestOCRResultDB.model_code.in_([model["model_code"] for model in model_list]))
            .where(TestOCRResultDB.image_uuid.in_([image["image_uuid"] for image in images]))
        )
        for model in model_list:
            model_code = model["model_code"]
            model_name = model["model_name"]
            for image in images:
                image_uuid = image["image_uuid"]
                image_path = image["image_path"]
                image_width = image["image_width"]
                image_height = image["image_height"]
                image_size = image["image_size"]

                exist_image = db_images.filter(
                    TestOCRResultDB.image_uuid == image_uuid,
                    TestOCRResultDB.model_code == model_code,
                ).first()

                if not exist_image:
                    create_count += 1
                    not_start_count += 1
                    TestOCRResultDB.create(
                        test_file=test_file.id,
                        image_uuid=image_uuid,
                        image_path=image_path,
                        image_width=image_width,
                        image_height=image_height,
                        image_size=image_size,
                        model_code=model_code,
                        model_name=model_name,
                        ocr_result="",
                        duration=0,
                        token_usage=0,
                        status=TestOCRStatus.not_start["value"],
                    )
                else:
                    exist_count += 1
                    if exist_image.status == TestOCRStatus.not_start["value"]:
                        not_start_count += 1

    logger.info(f"新创建{create_count}条测试任务，{exist_count}条测试任务已存在，{not_start_count}条测试任务未开始")

    # 没有未识别的图片了直接返回，不用启动GPU任务避免vllm引擎无效启动
    if not_start_count == 0:
        return success_response(True, _("创建测试任务成功"))

    # 先清除当前用户的之前建的模型测试任务
    gpu_task_monitor.del_gpu_task("modeltest", current_user.user_id)
    # 检查是否有其他正在运行中的任务
    queue_count = gpu_task_monitor.gpu_task_queue_count()
    if queue_count > 0:
        return error_response(
            t(
                _("当前尚有{queue_count}个GPU任务正在运行或排队等待中，请确定其他任务完成后再进行测试任务"),
                **{"queue_count": str(queue_count)},
            )
        )

    gpu_task_monitor.add_gpu_task(
        name=f"模型测试任务-{current_user.user_id}",
        task_type="modeltest",
        handler="kalorda.core.modeltest_runner.modeltest_with_vllm",
        params={
            "user_id": current_user.user_id,
            "file_id_list": file_id_list,
            "model_list": model_list,
        },
        correlation_id=current_user.user_id,
        can_retry=False,
        run_times_limit=1,
    )

    return success_response(True, _("创建测试任务成功"))


@router.post("/ocr/stop")
async def ocr_stop(
    current_user: CurrentUser = Depends(get_current_active_user),
):
    gpu_task_monitor.del_gpu_task("modeltest", current_user.user_id)
    return success_response(True, _("停止测试任务成功"))


@router.get("/ocr/constants")
async def ocr_constants(
    current_user: CurrentUser = Depends(get_current_active_user),
):
    base_model_list = []
    ocr_model_list = OcrModel.get_all_models()
    for model in ocr_model_list:
        model_code = model["code"]
        model_name = model["name"]
        category_list = []
        if model_code == "dolphin":
            category_list = DolphinCategory.get_all_categories()
        elif model_code == "dotsocr":
            category_list = DotsOCRCategory.get_all_categories()
        elif model_code == "got_ocr":
            category_list = GotOCRCategory.get_all_categories()
        elif model_code == "deepseek_ocr":
            category_list = DeepseekOCRCategory.get_all_categories()
        elif model_code == "deepseek_ocr2":
            category_list = DeepseekOCR2Category.get_all_categories()
        elif model_code == "paddleocr_vl":
            category_list = PaddleOCRVLCategory.get_all_categories()
        elif model_code == "hunyuan_ocr":
            category_list = HunyuanOCRCategory.get_all_categories()

        base_model_list.append(
            {
                "model_code": model_code,
                "model_name": model_name,
                "category_list": category_list,
            }
        )

    data = {
        "base_model_list": base_model_list,
        "status_list": TestOCRStatus.get_all_status(),
    }
    return success_response(data)


@router.post("/ocr/file/list")
@with_db_transaction(use_transaction=False)
async def ocr_file_list(
    lazy_file_id_list: List[int] = Body(..., description="文件ID列表"),
    model_list: List[dict] = Body(..., description="模型列表"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not lazy_file_id_list:
        return error_response(_("文件ID列表为空"))
    if not model_list:
        return error_response(_("模型列表为空"))

    file_id_list = lazy_file_id_list

    test_files = (
        TestOCRFileDB.select_active()
        .select(
            TestOCRFileDB.id,
            TestOCRFileDB.original_filename,
            TestOCRFileDB.images_info,
            TestOCRFileDB.file_size,
        )
        .where(TestOCRFileDB.id.in_(file_id_list))
        .where(TestOCRFileDB.uploaded_by == current_user.user_id)
        .order_by(TestOCRFileDB.updated_at.desc(), TestOCRFileDB.id.desc())
    )
    if not test_files:
        return error_response(_("文件ID列表不包含有效的测试文件"))

    test_file_list = []
    for test_file in test_files:
        total_count = 0
        completed_count = 0
        failed_count = 0
        images = json.loads(test_file.images_info)

        db_images = (
            TestOCRResultDB.select_active()
            .select(
                TestOCRResultDB.id,
                TestOCRResultDB.image_uuid,
                TestOCRResultDB.model_code,
                TestOCRResultDB.status,
            )
            .where(TestOCRResultDB.test_file == test_file.id)
            .where(TestOCRResultDB.model_code.in_([model["model_code"] for model in model_list]))
            .where(TestOCRResultDB.image_uuid.in_([image["image_uuid"] for image in images]))
        )
        logger.info(f"查询到的数据库图像数量: {len(db_images)}")

        model_ocr_count = {}
        for model in model_list:
            model_code = model["model_code"]
            model_ocr_count[model_code] = {
                "total_count": len(images),
                "completed_count": 0,
                "failed_count": 0,
                "waiting": True,
            }

            for image in images:
                image_uuid = image["image_uuid"]
                exist_image = db_images.filter(
                    TestOCRResultDB.image_uuid == image_uuid,
                    TestOCRResultDB.model_code == model_code,
                ).first()

                total_count += 1
                if exist_image.status == TestOCRStatus.completed["value"]:
                    completed_count += 1
                    model_ocr_count[model_code]["completed_count"] += 1
                if exist_image.status == TestOCRStatus.failed["value"]:
                    failed_count += 1
                    model_ocr_count[model_code]["failed_count"] += 1

            if model_ocr_count[model_code]["completed_count"] + model_ocr_count[model_code]["failed_count"] == len(
                images
            ):
                model_ocr_count[model_code]["waiting"] = False

        # 返回文件信息
        test_file_list.append(
            {
                "id": test_file.id,
                "file_name": test_file.original_filename,
                "images_info": images,
                "file_size": test_file.file_size,
                "model_ocr_count": model_ocr_count,  # 按每个模型的OCR结果数量
                # 全部模型的ocr结果统计
                "total_count": len(images) * len(model_list),
                "completed_count": completed_count,
                "failed_count": failed_count,
                "waiting": False if completed_count + failed_count == len(images) * len(model_list) else True,
            }
        )
    return success_response(test_file_list)


@router.post("/ocr/result")
@with_db_transaction(use_transaction=False)
async def ocr_result(
    file_id: int = Body(..., description="文件ID"),
    model_code: str = Body(..., description="模型"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not file_id:
        return error_response(_("文件ID列表为空"))
    if not model_code:
        return error_response(_("模型列表为空"))

    ocr_results = (
        TestOCRResultDB.select_active()
        .select(
            TestOCRResultDB.id,
            TestOCRResultDB.image_uuid,
            TestOCRResultDB.image_path,
            TestOCRResultDB.model_code,
            TestOCRResultDB.status,
            TestOCRResultDB.ocr_result,
            TestOCRResultDB.duration,
            TestOCRResultDB.token_usage,
        )
        .where(TestOCRResultDB.test_file_id == file_id)
        .where(TestOCRResultDB.model_code == model_code)
    )
    if not ocr_results:
        return error_response(_("未查询到该文件的测试结果"))

    image_ocr_list = []
    duration_sum = 0
    token_usage_sum = 0
    for ocr_result in ocr_results:
        duration_sum += ocr_result.duration
        token_usage_sum += ocr_result.token_usage
        image_ocr_list.append(
            {
                "image_uuid": ocr_result.image_uuid,
                "image_path": ocr_result.image_path,
                "status": ocr_result.status,
                "ocr_result": ocr_result.ocr_result,
                "duration": ocr_result.duration,
                "token_usage": ocr_result.token_usage,
            }
        )

    data = {
        "file_id": file_id,
        "model_code": model_code,
        "duration_sum": duration_sum,
        "token_usage_sum": token_usage_sum,
        "image_ocr_list": image_ocr_list,
    }
    return success_response(data)


# 清除文件的全部的ocr识别结果
@router.post("/ocr/remove")
@with_db_transaction()
async def ocr_remove(
    file_id: int = Body(..., description="文件ID"),
    model_code: str = Body(..., description="模型"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not file_id:
        return error_response(_("文件ID为空"))

    test_file = TestOCRFileDB.select_active().where(TestOCRFileDB.id == file_id).first()
    if not test_file:
        return error_response(_("文件ID不存在"))
    if test_file.uploaded_by.id != current_user.user_id:
        return error_response(_("您没有权限删除该文件的测试结果"))

    TestOCRResultDB.update(is_deleted=True).where(TestOCRResultDB.test_file == file_id).execute()

    return success_response({"file_id": file_id}, _("测试结果已删除"))


@router.post("/ocr/sendmail")
@with_db_transaction()
async def ocr_sendmail(
    email: str = Body(..., description="邮箱"),
    email_subject: str = Body(..., description="邮件主题"),
    email_content: str = Body(..., description="邮件内容"),
    current_user: CurrentUser = Depends(get_current_active_user),
):
    if not email:
        return error_response(_("邮箱不能为空"))
    if not email_subject:
        return error_response(_("邮件主题不能为空"))
    if not email_content:
        return error_response(_("邮件内容不能为空"))

    is_valid = is_valid_email(email)
    if not is_valid:
        return error_response(_("邮箱格式错误"))

    # 发送邮件
    result = send_email(
        email,
        email_subject,
        f"<html>{email_content}</html>",
    )
    if not result.get("status"):
        return error_response(result.get("message"))
    return success_response(_("OCR识别结果已发送"))


# 导出路由器
__all__ = ["router"]
