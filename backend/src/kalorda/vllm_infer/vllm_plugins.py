from kalorda.vllm_infer.got_ocr.got_vllm_plugin import register as register_got_ocr
from kalorda.vllm_infer.deepseek_ocr2.modeling_plugin import register as register_deepseek_ocr2

# Register custom architectures for vLLM worker processes.
register_got_ocr()
register_deepseek_ocr2()
