def register():
    import vllm
    from vllm import ModelRegistry

    if "Qwen2GotForCausalLM" not in ModelRegistry.get_supported_archs():
        if vllm.__version__ >= "0.16.0":
            from .got_vllm_modeling_v16_0 import Qwen2GotForCausalLM
        elif vllm.__version__ >= "0.14.0":
            from .got_vllm_modeling_v14_0 import Qwen2GotForCausalLM
        elif vllm.__version__ >= "0.13.0":
            from .got_vllm_modeling_v13_0 import Qwen2GotForCausalLM
        elif vllm.__version__ == "0.12.0":
            from .got_vllm_modeling_v12_0 import Qwen2GotForCausalLM
        elif vllm.__version__ == "0.11.2":
            from .got_vllm_modeling_v11_2 import Qwen2GotForCausalLM
        elif vllm.__version__ < "0.11.2":
            from .got_vllm_modeling_v10_1 import Qwen2GotForCausalLM
        ModelRegistry.register_model("Qwen2GotForCausalLM", Qwen2GotForCausalLM)
