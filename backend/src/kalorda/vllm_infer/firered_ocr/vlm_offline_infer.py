from PIL import Image
from vllm import LLM, SamplingParams
from vllm.lora.request import LoRARequest
from transformers import AutoProcessor
# from kalorda.utils.logger import logger
from .prompt import PROMPT


class FireRedOCRInfer:
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
            top_p=0.95,
            seed=1234,
            max_tokens=self.max_tokens,
        )
        self.processor = AutoProcessor.from_pretrained(model_weights_dir)
        self.lora_request = (
            LoRARequest("hunyuan_ocr", 1, lora_local_path=lora_weights_dir) if lora_weights_dir is not None else None
        )

    def generate(self, image_file: str):
        image_path_dict = {
            "image_path": image_file
        }
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image_path_dict},
                    {"type": "text", "text": PROMPT},
                ],
            },
        ]
        prompt_inputs = self.processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        image = Image.open(image_file).convert("RGB")
        inputs = [
            {
                "prompt": prompt_inputs,
                "multi_modal_data": {"image": [image]},
            }
        ]
        response = self.engine.generate(inputs, self.sampling_params, lora_request=self.lora_request)
        ocr_result = response[0].outputs[0].text
        tokens_count = len(response[0].outputs[0].token_ids)
        return ocr_result, tokens_count
