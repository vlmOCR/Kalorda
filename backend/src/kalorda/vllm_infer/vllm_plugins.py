def _patch_transformers_autoconfig_for_deepseek_ocr() -> None:
    """
    transformers >= 5.4 narrowed exception handling in AutoTokenizer, so
    AutoConfig ImportError from DeepSeek OCR remote code no longer falls back.
    Restore a targeted fallback for DeepSeek OCR/OCR-2 only.
    """
    try:
        from packaging import version as pkg_version
        import transformers
        from transformers import AutoConfig, PreTrainedConfig
    except Exception:
        return

    if pkg_version.parse(transformers.__version__) < pkg_version.parse("5.4.0"):
        return

    if getattr(AutoConfig, "_kalorda_patched_for_deepseek_ocr", False):
        return

    orig_from_pretrained = AutoConfig.from_pretrained.__func__

    @classmethod
    def patched_from_pretrained(cls, pretrained_model_name_or_path, *model_args, **kwargs):
        trust_remote_code = kwargs.get("trust_remote_code", False)
        try:
            return orig_from_pretrained(cls, pretrained_model_name_or_path, *model_args, **kwargs)
        except ImportError as exc:
            model_name = str(pretrained_model_name_or_path).lower()
            # Restrict fallback scope to DeepSeek OCR style repos and this known API break.
            should_fallback = (
                trust_remote_code
                and "deepseek" in model_name
                and "ocr" in model_name
                and "LlamaFlashAttention2" in str(exc)
            )
            if not should_fallback:
                raise

            fallback_kwargs = dict(kwargs)
            fallback_kwargs.pop("trust_remote_code", None)
            return PreTrainedConfig.from_pretrained(
                pretrained_model_name_or_path,
                *model_args,
                **fallback_kwargs,
            )

    AutoConfig.from_pretrained = patched_from_pretrained
    AutoConfig._kalorda_patched_for_deepseek_ocr = True


_patch_transformers_autoconfig_for_deepseek_ocr()

from kalorda.vllm_infer.got_ocr.got_vllm_plugin import register as register_got_ocr
from kalorda.vllm_infer.deepseek_ocr2.modeling_plugin import register as register_deepseek_ocr2

# Register custom architectures for vLLM worker processes.
register_got_ocr()
register_deepseek_ocr2()
