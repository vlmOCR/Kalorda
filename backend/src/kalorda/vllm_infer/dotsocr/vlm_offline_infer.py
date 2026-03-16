from io import BytesIO
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
    image_factor = 28
    min_pixels = 3136
    max_pixels = 11289600
    preprocess_target_dpi = 200
    use_pdf_preprocess = True
    bbox_pattern = re.compile(
        r'((?:"bbox"|\'bbox\'|bbox)\s*:\s*\[\s*)'
        r'([-+]?\d+(?:\.\d+)?)\s*,\s*'
        r'([-+]?\d+(?:\.\d+)?)\s*,\s*'
        r'([-+]?\d+(?:\.\d+)?)\s*,\s*'
        r'([-+]?\d+(?:\.\d+)?)\s*(\])'
    )

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
        origin_image = self.get_image(image_file)
        image = self.preprocess_image_for_vllm(origin_image)
        inputs = [
            {
                "prompt": self.prompt,
                "multi_modal_data": {"image": [image]},
            }
        ]
        response = self.engine.generate(inputs, self.sampling_params, lora_request=self.lora_request)
        ocr_result = response[0].outputs[0].text
        ocr_result = self.post_process_bbox_text(
            ocr_result,
            original_width=origin_image.width,
            original_height=origin_image.height,
            processed_width=image.width,
            processed_height=image.height,
        )
        tokens_count = len(response[0].outputs[0].token_ids)
        return ocr_result, tokens_count

    def get_image(self, image_file: str, adjust: bool = False):
        image = Image.open(image_file).convert("RGB")
        return image

    def preprocess_image_for_vllm(self, image: Image.Image) -> Image.Image:
        if not self.use_pdf_preprocess:
            return self.to_rgb(image)

        try:
            return self.render_image_via_pdfium(image, target_dpi=self.preprocess_target_dpi)
        except Exception as exc:
            logger.warning(f"dotsocr pdf preprocess skipped: {exc}")
            return self.to_rgb(image)

    @staticmethod
    def to_rgb(image: Image.Image) -> Image.Image:
        if image.mode == "RGBA":
            rgb_image = Image.new("RGB", image.size, (255, 255, 255))
            rgb_image.paste(image, mask=image.split()[3])
            return rgb_image
        return image.convert("RGB")

    def render_image_via_pdfium(self, image: Image.Image, target_dpi: int = 200) -> Image.Image:
        import pypdfium2 as pdfium

        image = self.to_rgb(image)
        image_bytes = BytesIO()
        image.save(image_bytes, format="PDF")
        document = pdfium.PdfDocument(image_bytes.getvalue())
        page = document[0]

        scale = target_dpi / 72
        rendered = page.render(scale=scale)
        rendered_image = rendered.to_pil()
        if rendered_image.width > 4500 or rendered_image.height > 4500:
            rendered_image = page.render(scale=1).to_pil()

        return rendered_image.convert("RGB")

    @classmethod
    def round_by_factor(cls, number: int, factor: int) -> int:
        return round(number / factor) * factor

    @classmethod
    def ceil_by_factor(cls, number: int, factor: int) -> int:
        return math.ceil(number / factor) * factor

    @classmethod
    def floor_by_factor(cls, number: int, factor: int) -> int:
        return math.floor(number / factor) * factor

    @classmethod
    def smart_resize(
        cls,
        height: int,
        width: int,
        factor: int = None,
        min_pixels: int = None,
        max_pixels: int = None,
    ):
        factor = factor or cls.image_factor
        min_pixels = min_pixels or cls.min_pixels
        max_pixels = max_pixels or cls.max_pixels

        if max(height, width) / min(height, width) > 200:
            raise ValueError(f"absolute aspect ratio must be smaller than 200, got {max(height, width) / min(height, width)}")

        h_bar = max(factor, cls.round_by_factor(height, factor))
        w_bar = max(factor, cls.round_by_factor(width, factor))
        if h_bar * w_bar > max_pixels:
            beta = math.sqrt((height * width) / max_pixels)
            h_bar = max(factor, cls.floor_by_factor(height / beta, factor))
            w_bar = max(factor, cls.floor_by_factor(width / beta, factor))
        elif h_bar * w_bar < min_pixels:
            beta = math.sqrt(min_pixels / (height * width))
            h_bar = cls.ceil_by_factor(height * beta, factor)
            w_bar = cls.ceil_by_factor(width * beta, factor)
            if h_bar * w_bar > max_pixels:
                beta = math.sqrt((h_bar * w_bar) / max_pixels)
                h_bar = max(factor, cls.floor_by_factor(h_bar / beta, factor))
                w_bar = max(factor, cls.floor_by_factor(w_bar / beta, factor))
        return h_bar, w_bar

    def post_process_bbox_text(
        self,
        ocr_result: str,
        original_width: int,
        original_height: int,
        processed_width: int,
        processed_height: int,
    ) -> str:
        if (
            not ocr_result
            or original_width <= 0
            or original_height <= 0
            or processed_width <= 0
            or processed_height <= 0
        ):
            return ocr_result

        try:
            input_height, input_width = self.smart_resize(processed_height, processed_width)
            scale_x = input_width / original_width
            scale_y = input_height / original_height
        except Exception as exc:
            logger.warning(f"dotsocr bbox post process skipped: {exc}")
            return ocr_result

        def replace_bbox(match: re.Match) -> str:
            try:
                bbox = [float(match.group(index)) for index in range(2, 6)]
            except ValueError:
                return match.group(0)

            bbox_resized = [
                int(bbox[0] / scale_x),
                int(bbox[1] / scale_y),
                int(bbox[2] / scale_x),
                int(bbox[3] / scale_y),
            ]
            return f"{match.group(1)}{bbox_resized[0]}, {bbox_resized[1]}, {bbox_resized[2]}, {bbox_resized[3]}{match.group(6)}"

        return self.bbox_pattern.sub(replace_bbox, ocr_result)

