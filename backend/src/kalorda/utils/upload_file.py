# 确保上传目录存在
import hashlib
import os
import uuid

from fastapi import File, UploadFile

from kalorda.config import config

# 允许上传的文件类型
allowed_file_types = [
    "image/jpeg",
    "image/png",
    "image/jpg",
    "image/bmp",
    "image/tiff",
    "application/pdf",
]

DATASET_UPLOAD_DIR = os.path.join(config.UPLOAD_DIR, "datasets")
TESTFILE_UPLOAD_DIR = os.path.join(config.UPLOAD_DIR, "tests")

if not os.path.exists(DATASET_UPLOAD_DIR):
    os.makedirs(DATASET_UPLOAD_DIR, exist_ok=True)
if not os.path.exists(TESTFILE_UPLOAD_DIR):
    os.makedirs(TESTFILE_UPLOAD_DIR, exist_ok=True)


# 获取数据集的上传目录
def get_dataset_directory(dataset_id: int) -> str:
    """
    获取指定数据集的专用存储目录
    每个数据集有独立的目录，确保多用户数据隔离
    """
    dataset_dir = os.path.join(DATASET_UPLOAD_DIR, str(dataset_id))
    if not os.path.exists(dataset_dir):
        os.makedirs(dataset_dir, exist_ok=True)
    return dataset_dir


async def save_dataset_file(file: UploadFile = File(...), dataset_id: str = None):
    """
    保存数据集
    """
    if file.content_type not in allowed_file_types:
        return False, f"不支持的文件类型: {file.filename}", ""
    # 获取数据集目录
    dataset_dir = get_dataset_directory(dataset_id)
    # 生成唯一的文件名
    unique_id = uuid.uuid4().hex
    file_ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{unique_id}{file_ext}"
    file_path = os.path.join(dataset_dir, filename)
    # 保存文件同时计算MD5哈希值
    md5_hash = hashlib.md5()
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(5*1024*1024)
            if not chunk:
                break
            f.write(chunk)
            md5_hash.update(chunk)
    return True, file_path, md5_hash.hexdigest()


async def save_test_file(file: UploadFile = File(...)):
    """
    保存测试数据文件
    """
    if file.content_type not in allowed_file_types:
        return False, f"不支持的文件类型: {file.filename}", ""
    # 获取数据集目录
    test_file_dir = TESTFILE_UPLOAD_DIR
    # 生成唯一的文件名
    unique_id = uuid.uuid4().hex
    file_ext = os.path.splitext(file.filename)[1].lower()
    filename = f"{unique_id}{file_ext}"
    file_path = os.path.join(test_file_dir, filename)
    # 保存文件同时计算MD5哈希值
    md5_hash = hashlib.md5()
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(5*1024*1024)
            if not chunk:
                break
            f.write(chunk)
            md5_hash.update(chunk)
    return True, file_path, md5_hash.hexdigest()


async def save_dataset_zip(file: UploadFile = File(...), dataset_id: str = None):
    """
    Save dataset import zip file.
    """
    zip_types = {"application/zip", "application/x-zip-compressed"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file.content_type not in zip_types and file_ext != ".zip":
        return False, f"unsupported zip file type: {file.filename}", ""

    dataset_dir = get_dataset_directory(dataset_id)
    import_dir = os.path.join(dataset_dir, "_imports")
    if not os.path.exists(import_dir):
        os.makedirs(import_dir, exist_ok=True)

    unique_id = uuid.uuid4().hex
    filename = f"{unique_id}.zip"
    file_path = os.path.join(import_dir, filename)

    md5_hash = hashlib.md5()
    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(5*1024*1024)
            if not chunk:
                break
            f.write(chunk)
            md5_hash.update(chunk)
    return True, file_path, md5_hash.hexdigest()
