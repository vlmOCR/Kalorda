import kalorda.vllm_infer.dotsocr.prompts as dotsocr_prompts
from kalorda.vllm_infer.deepseek_ocr.config import PROMPT as deepseek_ocr_prompt
from kalorda.vllm_infer.deepseek_ocr2.config import PROMPT as deepseek_ocr2_prompt
from kalorda.vllm_infer.dolphin.prompts import dolphin_prompt
from kalorda.vllm_infer.hunyuan_ocr.prompts import hunyuan_prompt
from kalorda.vllm_infer.firered_ocr.prompt import PROMPT as firered_ocr_prompt


def get_sft_prompt(model_code: str):
    """
    获取模型训练的prompt
    """
    prompt = ""
    if model_code.lower() == "got_ocr":  # GOT_OCR
        prompt = "\nOCR with format: "
    if model_code.lower() == "dotsocr":  # dotsOCR
        prompt = dotsocr_prompts.dict_promptmode_to_prompt["prompt_layout_all_en"]
    if model_code.lower() == "dolphin":  # Dolphin
        prompt = dolphin_prompt["text"]
    if model_code.lower() == "deepseek_ocr":  # DeepseekOCR
        prompt = deepseek_ocr_prompt
    if model_code.lower() == "deepseek_ocr2":  # DeepseekOCR2
        prompt = deepseek_ocr2_prompt
    if model_code.lower() == "paddleocr_vl":  # PaddleOCRVL
        prompt = "Parse the reading order of this document."
    if model_code.lower() == "hunyuan_ocr":  # HunyuanOCR
        prompt = hunyuan_prompt["Document_Parsing"]
    if model_code.lower() == "firered_ocr":  # FireRedOCR
        prompt = firered_ocr_prompt
    return prompt
