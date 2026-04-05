from collections.abc import Mapping
from typing import (
    Any,
    ClassVar,
    List,
    Literal,
    Optional,
    Protocol,
    TypedDict,
    TypeVar,
    Union,
)

import torch
import torch.nn as nn
from transformers import BatchFeature
from typing_extensions import TypeAlias
from vllm.config import MultiModalConfig, VllmConfig
from vllm.config.multimodal import BaseDummyOptions
from vllm.distributed import get_pp_group
from vllm.inputs import ModalityData, MultiModalDataDict
from vllm.model_executor.layers.vocab_parallel_embedding import ParallelLMHead
from vllm.model_executor.models.interfaces import (
    MultiModalEmbeddings,
    SupportsMultiModal,
)
from vllm.model_executor.models.qwen2 import Qwen2ForCausalLM, Qwen2Model
from vllm.model_executor.models.utils import _merge_multimodal_embeddings  # 相比 v0.11.2 名称多个了_，入参也有小修改
from vllm.model_executor.models.utils import (
    PPMissingLayer,
    maybe_prefix,
)
from vllm.multimodal import MULTIMODAL_REGISTRY
from vllm.multimodal.inputs import (
    ImageItem,
    MultiModalFieldConfig,
    MultiModalKwargsItems,
    NestedTensors,
)
from vllm.multimodal.parse import (
    ModalityDataItems,
    MultiModalDataItems,
    MultiModalDataParser,
)
from vllm.multimodal.processing import (
    BaseMultiModalProcessor,
    BaseProcessingInfo,
    PromptReplacement,
    PromptUpdate,
)
try:
    from vllm.multimodal.profiling import BaseDummyInputsBuilder
except Exception:
    from vllm.multimodal.processing import BaseDummyInputsBuilder
from vllm.sequence import IntermediateTensors

from .blip_process import BlipImageEvalProcessor
from .vary_b import build_vary_vit_b as build_GOT_vit_b

# v1 engine support
# yapf: enable

_IMAGE_TOKEN_STR = "<imgpad>"
_IMAGE_TOKEN_ID = 151859
_IMAGE_TOKEN_LEN = 256
_IMAGE_SIZE = 1024


class Qwen2GotModel(Qwen2Model):
    def __init__(self, *, vllm_config: VllmConfig, prefix: str = ""):
        super().__init__(vllm_config=vllm_config, prefix=prefix)
        self.vision_tower_high = build_GOT_vit_b()
        self.mm_projector_vary = nn.Linear(_IMAGE_SIZE, _IMAGE_SIZE)

    def forward(
        self,
        input_ids: torch.Tensor,
        positions: torch.Tensor,
        intermediate_tensors: Optional[IntermediateTensors] = None,
        inputs_embeds: Optional[torch.Tensor] = None,
    ) -> Union[torch.Tensor, IntermediateTensors]:
        hidden_states = super(Qwen2GotModel, self).forward(
            input_ids=None,
            positions=positions,
            intermediate_tensors=intermediate_tensors,
            inputs_embeds=inputs_embeds,
        )

        return hidden_states


T = TypeVar("T")

MultiModalData: TypeAlias = Union[T, List[T]]


class SupportsMultiModal(Protocol):
    supports_multimodal: ClassVar[Literal[True]] = True

    def __init__(self, *, multimodal_config: "MultiModalConfig") -> None: ...


class Qwen2GotProcessingInfo(BaseProcessingInfo):
    def get_supported_mm_limits(self) -> Mapping[str, Optional[int]]:
        return {"image": None}

    def get_mm_max_tokens_per_item(
        self,
        seq_len: int,
        mm_counts: Mapping[str, int],
    ) -> Mapping[str, int]:
        return {"image": _IMAGE_TOKEN_LEN}

    # vLLM v0.16 moved parser construction away from
    # BaseMultiModalProcessor._get_data_parser.
    def build_data_parser(self) -> MultiModalDataParser:
        return Qwen2GotMultiModalDataParser(
            expected_hidden_size=self._get_expected_hidden_size(),
        )

    # Keep compatibility with v0.16 implementations that call get_data_parser().
    def get_data_parser(self) -> MultiModalDataParser:
        return self.build_data_parser()


class Qwen2GotImageInputs(TypedDict):
    type: Literal["image_embeds"]
    image_embeds: torch.Tensor


class Qwen2GotMultiModalDataParser(MultiModalDataParser):
    def _parse_image_data(
        self,
        data: Union[dict[str, torch.Tensor], ModalityData[ImageItem]],
    ) -> ModalityDataItems[Any, Any]:
        return super()._parse_image_data(data)


class Qwen2GotDummyInputsBuilder(BaseDummyInputsBuilder[Qwen2GotProcessingInfo]):
    # v0.9.0 之后 get_dummy_processor_inputs 拆分为 get_dummy_text 和 get_dummy_mm_data 两个方法
    def get_dummy_text(self, mm_counts: Mapping[str, int]) -> str:
        num_images = mm_counts.get("image", 0)
        return _IMAGE_TOKEN_STR * num_images

    def get_dummy_mm_data(
        self,
        seq_len: int,
        mm_counts: Mapping[str, int],
        mm_options: Mapping[str, BaseDummyOptions] | None = None,
    ) -> MultiModalDataDict:
        num_images = mm_counts.get("image", 0)
        # target_width, target_height = self.info.get_image_size_with_most_features()
        image_overrides = mm_options.get("image") if mm_options else None
        return {
            "image": self._get_dummy_images(
                width=_IMAGE_SIZE,
                height=_IMAGE_SIZE,
                num_images=num_images,
                overrides=image_overrides,
            ),
        }


BLIP_IMAGE_EVAL_PROCESSOR = BlipImageEvalProcessor(image_size=_IMAGE_SIZE)


# 多模态模型联合处理器
class Qwen2GotMultiModalProcessor(BaseMultiModalProcessor[Qwen2GotProcessingInfo]):
    def _call_hf_processor(
        self,
        prompt: str,
        mm_data: Mapping[str, object],
        mm_kwargs: Mapping[str, object],
        tok_kwargs: Mapping[str, object],
    ) -> BatchFeature:
        tokenizer = self.info.get_tokenizer()
        processed_outputs = tokenizer(prompt, add_special_tokens=False, return_tensors="pt")
        images = mm_data.get("images")
        if images is None:
            images = mm_data.get("image")
        if images:
            image_tensors = []
            if not isinstance(images, list):
                images = [images]
            else:
                flat_images = []
                for image in images:
                    if isinstance(image, list):
                        flat_images.extend(image)
                    else:
                        flat_images.append(image)
                images = flat_images
            for image in images:
                image_tensor = BLIP_IMAGE_EVAL_PROCESSOR(image)
                image_tensors.append(image_tensor)
            processed_outputs["image_embeds"] = image_tensors
        return processed_outputs

    def _hf_processor_applies_updates(
        self,
        prompt_text: str,
        mm_items: MultiModalDataItems,
        hf_processor_mm_kwargs: Mapping[str, object],
        tokenization_kwargs: Mapping[str, object],
    ) -> bool:
        return False

    def _get_mm_fields_config(
        self,
        hf_inputs: BatchFeature,
        hf_processor_mm_kwargs: Mapping[str, object],
    ) -> Mapping[str, MultiModalFieldConfig]:
        return dict(
            image_embeds=MultiModalFieldConfig.batched("image"),
        )

    def _get_prompt_updates(
        self,
        mm_items: MultiModalDataItems,
        hf_processor_mm_kwargs: Mapping[str, Any],
        out_mm_kwargs: MultiModalKwargsItems,
    ) -> list[PromptUpdate]:
        def get_replacement(item_idx: int):
            return [_IMAGE_TOKEN_ID] * _IMAGE_TOKEN_LEN

        prompt_updates = [PromptReplacement(modality="image", target=[_IMAGE_TOKEN_ID], replacement=get_replacement)]
        return prompt_updates


@MULTIMODAL_REGISTRY.register_processor(
    Qwen2GotMultiModalProcessor,
    info=Qwen2GotProcessingInfo,
    dummy_inputs=Qwen2GotDummyInputsBuilder,
)
class Qwen2GotForCausalLM(Qwen2ForCausalLM, SupportsMultiModal):
    # edit by sanjer
    # vllm 0.13.0 下又不能要了，变来变去的
    # merge_by_field_config = False
    # multimodal_cpu_fields = {}
    requires_raw_input_tokens: ClassVar[bool] = True

    def __init__(
        self,
        *,
        vllm_config: VllmConfig,
        prefix: str = "",
        multimodal_config: Optional[MultiModalConfig] = {},
    ):
        super(Qwen2GotForCausalLM, self).__init__(vllm_config=vllm_config, prefix=prefix)

        config = vllm_config.model_config.hf_config
        quant_config = vllm_config.quant_config

        self.model = Qwen2GotModel(vllm_config=vllm_config, prefix=prefix)
        self.multimodal_config = multimodal_config

        if get_pp_group().is_last_rank:
            if config.tie_word_embeddings:
                self.lm_head = self.model.embed_tokens
            else:
                self.lm_head = ParallelLMHead(
                    config.vocab_size,
                    config.hidden_size,
                    quant_config=quant_config,
                    prefix=maybe_prefix(prefix, "lm_head"),
                )
        else:
            self.lm_head = PPMissingLayer()

        forward_context = {}
        for (
            name,
            layer,
        ) in vllm_config.compilation_config.static_forward_context.items():
            # print(f'layer name = {name}')
            if not name.startswith("model."):  # 过滤掉model.开头的重复layer
                forward_context[name] = layer
        vllm_config.compilation_config.static_forward_context = forward_context

    def _parse_and_validate_image_input(self, **kwargs: object) -> Qwen2GotImageInputs | None:
        image_embeds = kwargs.pop("image_embeds", None)
        if image_embeds is None:
            return None

        image_tensors: list[torch.Tensor] = []
        if isinstance(image_embeds, torch.Tensor):
            if image_embeds.numel() == 0:
                return None
            if image_embeds.dim() == 3:
                image_tensors = [image_embeds]
            else:
                image_tensors = [image_embeds[i] for i in range(image_embeds.size(0))]
        elif isinstance(image_embeds, list):
            for item in image_embeds:
                if isinstance(item, list):
                    image_tensors.extend(item)
                else:
                    image_tensors.append(item)

        if not image_tensors:
            return None

        image_features = []
        for image in image_tensors:
            image = image.to(dtype=torch.bfloat16)
            if image.dim() == 3:
                images_to_process = [image.unsqueeze(0)]
            elif image.dim() == 4 and image.size(0) > 1:
                images_to_process = [image[i].unsqueeze(0) for i in range(image.size(0))]
            else:
                images_to_process = [image]

            for image_item in images_to_process:
                cnn_feature = self.model.vision_tower_high(image_item)
                cnn_feature = cnn_feature.flatten(2).permute(0, 2, 1)
                image_feature = self.model.mm_projector_vary(cnn_feature).reshape(-1, _IMAGE_SIZE)
                image_features.append(image_feature)

        return Qwen2GotImageInputs(
            type="image_embeds",
            image_embeds=image_features,
        )

    def _process_image_input(self, image_input: Qwen2GotImageInputs) -> list[torch.Tensor]:
        return image_input["image_embeds"]

    def embed_multimodal(self, **kwargs: object) -> MultiModalEmbeddings:
        image_input = self._parse_and_validate_image_input(**kwargs)
        if image_input is None:
            return []
        vision_embeddings = self._process_image_input(image_input)
        return vision_embeddings

    def embed_input_ids(
        self,
        input_ids: torch.Tensor,
        multimodal_embeddings: Optional[NestedTensors] = None,
        is_multimodal: bool = True,
    ) -> torch.Tensor:
        inputs_embeds = self.model.embed_tokens(input_ids)

        if multimodal_embeddings is not None and len(multimodal_embeddings) != 0:
            inputs_embeds = _merge_multimodal_embeddings(
                inputs_embeds=inputs_embeds,
                multimodal_embeddings=multimodal_embeddings,
                is_multimodal=is_multimodal,
            )

        return inputs_embeds

    def forward(
        self,
        input_ids: torch.Tensor,
        positions: torch.Tensor,
        intermediate_tensors: IntermediateTensors | None = None,
        inputs_embeds: torch.Tensor | None = None,
        **kwargs: object,
    ) -> torch.Tensor | IntermediateTensors:
        if intermediate_tensors is not None:
            inputs_embeds = None
        elif inputs_embeds is None:
            vision_embeddings = self.embed_multimodal(**kwargs)
            inputs_embeds = self.embed_input_ids(
                input_ids,
                vision_embeddings,
                is_multimodal=True,
            )
            input_ids = None

        hidden_states = self.model(input_ids, positions, intermediate_tensors, inputs_embeds)

        return hidden_states
