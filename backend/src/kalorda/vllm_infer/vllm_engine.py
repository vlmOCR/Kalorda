from .deepseek_ocr.vlm_offline_infer import DeepseekOCRInfer
from .deepseek_ocr2.vlm_offline_infer import DeepseekOCR2Infer
from .dolphin.vlm_offline_infer import DolphinInfer
from .dotsocr.vlm_offline_infer import DotsOCRInfer
from .got_ocr.vlm_offline_infer import GotOCRInfer
from .hunyuan_ocr.vlm_offline_infer import HunyuanOCRInfer
from .paddleocr_vl.vlm_offline_infer import PaddleOCRVLInfer


def get_vllm_engine(model_code: str, model_weights_dir: str, lora_weights_dir: str = None):
    if model_code == "dolphin":
        return DolphinInfer(model_weights_dir, lora_weights_dir)
    elif model_code == "dotsocr":
        return DotsOCRInfer(model_weights_dir, lora_weights_dir)
    elif model_code == "got_ocr":
        return GotOCRInfer(model_weights_dir, lora_weights_dir)
    elif model_code == "deepseek_ocr":
        return DeepseekOCRInfer(model_weights_dir, lora_weights_dir)
    elif model_code == "deepseek_ocr2":
        return DeepseekOCR2Infer(model_weights_dir, lora_weights_dir)
    elif model_code == "paddleocr_vl":
        return PaddleOCRVLInfer(model_weights_dir, lora_weights_dir)
    elif model_code == "hunyuan_ocr":
        return HunyuanOCRInfer(model_weights_dir, lora_weights_dir)
    else:
        raise ValueError(f"不支持的模型代码: {model_code}")
