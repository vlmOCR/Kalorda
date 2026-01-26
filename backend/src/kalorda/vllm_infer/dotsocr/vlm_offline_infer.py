import io
import math
import re

from PIL import Image
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest

from kalorda.utils.logger import logger
from kalorda.vllm_infer.dotsocr.prompts import dict_promptmode_to_prompt


class DotsOCRInfer:
    max_tokens = 20480
    max_model_len = 20480
    max_num_batched_tokens = 20480
    gpu_memory_utilization = 0.8

    def __init__(self, model_weights_dir: str, lora_weights_dir: str = None):
        self.engine = LLM(
            model=model_weights_dir,
            trust_remote_code=True,
            gpu_memory_utilization=self.gpu_memory_utilization,
            max_model_len=self.max_model_len,
            max_num_batched_tokens=self.max_num_batched_tokens,
            limit_mm_per_prompt={"image": 1},
            enable_lora=lora_weights_dir is not None,
        )
        self.sampling_params = SamplingParams(
            temperature=0.0,
            top_p=0.9,
            logprobs=0,
            max_tokens=self.max_tokens,
            prompt_logprobs=None,
            skip_special_tokens=False,
        )
        self.prompt = f"<|img|><|imgpad|><|endofimg|>{dict_promptmode_to_prompt['prompt_layout_all_en']}"
        if lora_weights_dir is not None:
            self.lora_request = LoRARequest("dotsocr_lora", 1, lora_local_path=lora_weights_dir)
        else:
            self.lora_request = None

    def generate(self, image_file: str):
        image, scaledX, scaledY = self.get_image(image_file)
        inputs = [
            {
                "prompt": self.prompt,
                "multi_modal_data": {"image": [image]},
            }
        ]
        response = self.engine.generate(inputs, self.sampling_params, lora_request=self.lora_request)
        ocr_result = response[0].outputs[0].text
        tokens_count = len(response[0].outputs[0].token_ids)
        # 如果有缩放处理，需要解析OCR结果进行坐标还原
        if scaledX != 1.0 or scaledY != 1.0:
            ocr_result = self.parse_ocr_result(ocr_result, scaledX, scaledY)
        return ocr_result, tokens_count

    # def get_image(self, image_file: str, adjust: bool = True):
    #     scaledX = 1.0
    #     scaledY = 1.0
    #     image = Image.open(image_file).convert("RGB")
    #     if not adjust:
    #         return image, scaledX, scaledY

    #     original_width, original_height = image.width, image.height
    #     data_bytes = io.BytesIO()
    #     image.save(data_bytes, format="PNG")

    #     # fiz
    #     import fitz
    #     pdf_bytes = fitz.open(stream=data_bytes).convert_to_pdf()
    #     doc = fitz.open("pdf", pdf_bytes)[0]

    #     mat = fitz.Matrix(200 / 72.0, 200 / 72.0)
    #     pm = doc.get_pixmap(matrix=mat, alpha=False)
    #     if pm.width > 4500 or pm.height > 4500:
    #         mat = fitz.Matrix(72 / 72, 72 / 72)  # use fitz default dpi
    #         pm = doc.get_pixmap(matrix=mat, alpha=False)
    #     image = Image.frombytes("RGB", (pm.width, pm.height), pm.samples)
    #     # 以上使用fiz代码

    #     resized_height, resized_width = self.smart_resize(image.width, image.height)
    #     image = image.resize(
    #         (
    #             resized_width,
    #             resized_height,
    #         )
    #     )
    #     # 计算缩放比例
    #     scaledX = resized_width / original_width
    #     scaledY = resized_height / original_height

    #     return image, scaledX, scaledY

    def get_image(self, image_file: str, adjust: bool = False):
        scaledX = 1.0
        scaledY = 1.0
        image = Image.open(image_file).convert("RGB")
        original_width, original_height = image.width, image.height
        if adjust:  # 使用自动调整图片
            # 官方采用的是fitz组件，但因其开源协议的问题，采用spire.pdf.free + pdf2image组件替换，但效果不是完全一致
            image = self.adjust_image(image_file)
            # 计算缩放比例
            scaledX = image.width / original_width
            scaledY = image.height / original_height

        logger.info(
            f"dotsOCR adjust image -> width: {image.width}, height: {image.height},scaledX: {scaledX}, scaledY: {scaledY}"
        )
        return image, scaledX, scaledY

    def parse_ocr_result(self, ocr_result: str, scaledX: float, scaledY: float):
        """
        解析OCR结果，提取坐标后进行缩放还原处理
        """
        pattern = re.compile(r"\"bbox\": \[(\d+), (\d+), (\d+), (\d+)\]")  # 匹配一个或多个数字
        return pattern.sub(
            lambda match: f'"bbox": [{int(int(match.group(1)) / scaledX)}, {int(int(match.group(2)) / scaledY)}, {int(int(match.group(3)) / scaledX)}, {int(int(match.group(4)) / scaledY)}]',
            ocr_result,
        )

    def adjust_image(self, image_file: str):
        import os
        import tempfile
        import uuid

        import pdf2image
        from spire.pdf import PdfDocument, PdfImage
        from spire.pdf.common import SizeF

        # 生成随机文件名
        tmp_pdf_name = f"dots_ocr_{uuid.uuid4().hex}.pdf"
        tmp_pdf_file = os.path.join(tempfile.gettempdir(), tmp_pdf_name)

        # 原始图片先转成单页pdf，采用spire.pdf.free组件
        doc = PdfDocument()
        doc.PageSettings.SetMargins(0.0)
        image = PdfImage.FromFile(image_file)
        width = image.PhysicalDimension.Width
        height = image.PhysicalDimension.Height
        page = doc.Pages.Add(SizeF(width, height))
        page.Canvas.DrawImage(image, 0.0, 0.0, width, height)
        doc.SaveToFile(tmp_pdf_file)
        doc.Close()

        # 再将pdf转成图片，采用pdf2image组件，指定dpi为200
        images = pdf2image.convert_from_path(tmp_pdf_file, dpi=200, size=(2048, None))
        image = images[0]

        # 最后智能计算应该合适尺寸并修改，确保像素数在3136-11289600之间
        resized_height, resized_width = self.smart_resize(image.width, image.height)
        image = image.resize(
            (
                resized_width,
                resized_height,
            )
        )

        return image

    def smart_resize(
        self,
        height: int,
        width: int,
        factor: int = 28,
        min_pixels: int = 3136,
        max_pixels: int = 11289600,
    ):
        if max(height, width) / min(height, width) > 200:
            raise ValueError(
                f"absolute aspect ratio must be smaller than 200, got {max(height, width) / min(height, width)}"
            )
        h_bar = max(factor, self.round_by_factor(height, factor))
        w_bar = max(factor, self.round_by_factor(width, factor))
        if h_bar * w_bar > max_pixels:
            beta = math.sqrt((height * width) / max_pixels)
            h_bar = max(factor, self.floor_by_factor(height / beta, factor))
            w_bar = max(factor, self.floor_by_factor(width / beta, factor))
        elif h_bar * w_bar < min_pixels:
            beta = math.sqrt(min_pixels / (height * width))
            h_bar = self.ceil_by_factor(height * beta, factor)
            w_bar = self.ceil_by_factor(width * beta, factor)
            if h_bar * w_bar > max_pixels:  # max_pixels first to control the token length
                beta = math.sqrt((h_bar * w_bar) / max_pixels)
                h_bar = max(factor, self.floor_by_factor(h_bar / beta, factor))
                w_bar = max(factor, self.floor_by_factor(w_bar / beta, factor))
        return h_bar, w_bar

    def round_by_factor(self, number: int, factor: int) -> int:
        return round(number / factor) * factor

    def ceil_by_factor(self, number: int, factor: int) -> int:
        return math.ceil(number / factor) * factor

    def floor_by_factor(self, number: int, factor: int) -> int:
        return math.floor(number / factor) * factor
