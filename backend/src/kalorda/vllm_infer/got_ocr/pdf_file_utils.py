import os

# import fitz  # PyMuPDF
# from PIL import Image
import tempfile
import uuid
from typing import List

import requests

# from datetime import datetime
from pdf2image import convert_from_path


# 将pdf文件转换为图片，并保存到临时目录
def pdf_to_image(pdf_file_path: str, dpi: int = 200, fmt: str = "png") -> List[str]:
    # 如果是网络文件，则下载到本地
    file_name = f"{uuid.uuid4().hex}"
    if pdf_file_path.startswith("http"):
        pdf_file_path, file_name = __download_pdf_file(pdf_file_path)
    pdf_image_list = convert_from_path(pdf_file_path, dpi=dpi, fmt=fmt, size=(2048, None))
    image_files = []
    for j, pdf_image in enumerate(pdf_image_list):
        pdf_image_save_file = f"{file_name}_page_{j}.{fmt}"
        pdf_image_save_path = os.path.join(tempfile.gettempdir(), pdf_image_save_file)
        pdf_image.save(pdf_image_save_path, fmt)
        image_files.append(pdf_image_save_path)
    return image_files


def __download_pdf_file(url: str) -> str:
    file_name = f"{uuid.uuid4().hex}"
    temp_save_file_path = os.path.join(tempfile.gettempdir(), f"{file_name}.pdf")
    response = requests.get(url, stream=True, timeout=30)
    with open(temp_save_file_path, "wb") as file:
        for chunk in response.iter_content(chunk_size=16384):  # 可调整块大小以优化性能
            file.write(chunk)
    return temp_save_file_path, file_name
