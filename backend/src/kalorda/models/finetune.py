from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# 训练类型枚举
class TrainingType(str, Enum):
    LORA = "lora"
    FULL = "full"
    CUSTOM = "custom"


# 模型类型枚举
class ModelType(int, Enum):
    GOT_OCR = 1
    DOTS_OCR = 2
    DOLPHIN = 3
    DEEPSEEK_OCR = 4
    PADDLEOCR_VL = 5
    HUNYUAN_OCR = 6
    DEEPSEEK_OCR2 = 7


# 数据格式枚举
class DataFormat(str, Enum):
    ALPACA = "Alpaca"
    SHAREGPT = "ShareGPT"
    CHATML = "ChatML"
    QUERY_RESPONSE = "QueryResponse"


# 微调任务创建请求
class FineTuneTaskCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    target_model: ModelType = Field(..., description="目标模型类型")
    data_format: DataFormat = Field(DataFormat.ALPACA, description="数据格式")
    dataset_ids: List[int] = Field(..., description="关联的数据集ID列表")


# 微调任务更新请求
class FineTuneTaskUpdateRequest(BaseModel):
    id: int = Field(..., description="要更新的任务ID")
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    target_model: Optional[ModelType] = Field(None, description="目标模型类型")
    data_format: Optional[DataFormat] = Field(None, description="数据格式")
    dataset_ids: Optional[List[int]] = Field(None, description="关联的数据集ID列表")


# 微调任务查询请求
class FineTuneTaskQueryRequest(BaseModel):
    name: Optional[str] = Field(None, description="任务名称关键词搜索")
    target_model: Optional[ModelType] = Field(None, description="目标模型类型")
    data_format: Optional[DataFormat] = Field(None, description="数据格式")
    created_by: Optional[int] = Field(None, description="创建者用户ID")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(10, ge=1, le=100, description="每页大小")


# 数据集简要信息（用于响应中的关联数据）
class DatasetBrief(BaseModel):
    id: int = Field(..., description="数据集ID")
    name: str = Field(..., description="数据集名称")
    model_type: int = Field(..., description="模型类型")
    total_images: int = Field(..., description="总图片数量")
    train_images: int = Field(..., description="训练图片数量")
    val_images: int = Field(..., description="验证图片数量")

    model_config = {
        "from_attributes": True,
    }


# 训练运行简要信息（用于响应中的关联数据）
class TrainingRunBrief(BaseModel):
    id: int = Field(..., description="训练运行ID")
    run_name: str = Field(..., description="运行名称")
    training_type: str = Field(..., description="训练类型")
    status: int = Field(..., description="训练状态")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    duration: Optional[float] = Field(None, description="持续时间(秒)")
    train_data_count: Optional[int] = Field(None, description="实际参与训练数据数量")
    val_data_count: Optional[int] = Field(None, description="实际参与验证数据数量")
    metrics: Optional[Dict[str, Any]] = Field(None, description="训练指标")
    model_code_suffix: Optional[str] = Field(None, description="生成的模型编码后缀")
    model_name: Optional[str] = Field(None, description="微调后模型的名称")

    model_config = {
        "from_attributes": True,
    }


# 微调任务响应
class FineTuneTaskResponse(BaseModel):
    id: int = Field(..., description="任务ID")
    name: str = Field(..., description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    target_model: int = Field(..., description="目标模型类型")
    data_format: str = Field(..., description="数据格式")
    train_data_path: Optional[str] = Field(None, description="训练数据jsonl文件路径")
    val_data_path: Optional[str] = Field(None, description="验证数据json文件路径")
    total_runs: int = Field(..., description="总训练次数")
    created_by: Optional[int] = Field(None, description="创建者用户ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    data_last_combined: Optional[datetime] = Field(None, description="数据最后合成的时间")
    data_combine_status: int = Field(0, description="数据合成状态: 0=未合成, 1=合成中, 2=合成完成, 3=合成失败")
    train_data_count: int = Field(0, description="训练数据数量")
    val_data_count: int = Field(0, description="验证数据数量")
    latest_run_id: Optional[int] = Field(None, description="最新训练实例ID")
    latest_run_status: Optional[int] = Field(None, description="最新训练状态")
    latest_run_metrics: Optional[Dict[str, Any]] = Field(None, description="最新训练指标")
    latest_model_path: Optional[str] = Field(None, description="最新模型保存路径")
    datasets: Optional[List[DatasetBrief]] = Field(None, description="关联的数据集列表")
    latest_run: Optional[TrainingRunBrief] = Field(None, description="最新训练运行信息")

    @field_validator("latest_run_metrics", mode="before")
    @classmethod
    def parse_latest_run_metrics(cls, v):
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v

    model_config = {
        "from_attributes": True,
    }


# 微调任务分页响应
class FineTuneTaskPageResponse(BaseModel):
    items: List[FineTuneTaskResponse] = Field(..., description="任务列表")
    total: int = Field(..., description="总条数")
    page: int = Field(..., description="页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")


# 训练参数请求
class TrainingRunParamsRequest(BaseModel):
    task_id: int = Field(..., description="微调任务ID")
    training_type: TrainingType = Field(..., description="训练类型")
    custom_params: Optional[str] = Field(None, description="自定义ms-swift训练参数")
    num_epochs: int = Field(3, ge=1, le=100, description="训练轮数")
    learning_rate: float = Field(1e-5, ge=1e-7, le=1e-3, description="学习率")
    target_modules: Optional[List[str]] = Field(None, description="目标模块列表")
    lora_rank: Optional[int] = Field(8, ge=4, le=64, description="LoRA秩")
    lora_alpha: Optional[int] = Field(16, ge=4, le=128, description="LoRA alpha")
    batch_size: int = Field(8, ge=1, le=128, description="批次大小")
    gradient_accumulation_steps: int = Field(1, ge=1, le=32, description="梯度累积步数")
    logging_steps: int = Field(1, ge=1, description="日志保存间隔步数")
    eval_steps: int = Field(1, ge=1, description="评估间隔步数")
    warmup_ratio: float = Field(0.1, ge=0.0, le=1.0, description="预热比例")
    weight_decay: float = Field(0.01, ge=0.0, le=0.1, description="权重衰减")
    max_seq_len: int = Field(512, ge=128, le=40960, description="最大序列长度")
    max_grad_norm: float = Field(1.0, ge=0.0, le=100.0, description="最大梯度范数")
    split_dataset_ratio: float = Field(0.1, ge=0.0, le=1, description="数据集划分比例")
    lr_warmup_iters_ratio: float = Field(0.001, ge=0.0, le=1, description="学习率预热迭代比例")
    do_early_stop: bool = Field(True, description="是否启用早停")
    early_stop_patience: int = Field(3, ge=1, le=20, description="早停耐心值")
    seed: Optional[int] = Field(None, ge=0, description="随机种子")
    model_name: Optional[str] = Field(None, description="微调后模型的名称")

    @field_validator("target_modules", mode="before")
    @classmethod
    def validate_target_modules(cls, v, values):
        if "training_type" in values.data and values.data["training_type"] == TrainingType.LORA:
            if not v or len(v) == 0:
                raise ValueError("使用LoRA训练类型时，必须指定target_modules")
        return v


# 训练运行响应
class TrainingRunResponse(BaseModel):
    id: int = Field(..., description="训练运行ID")
    task_id: int = Field(..., description="微调任务ID")
    training_type: str = Field(..., description="训练类型")
    custom_params: Optional[str] = Field(None, description="自定义ms-swift训练参数")
    num_epochs: int = Field(..., description="训练轮数")
    learning_rate: float = Field(..., description="学习率")
    target_modules: Optional[List[str]] = Field(None, description="目标模块列表")
    lora_rank: Optional[int] = Field(None, description="LoRA秩")
    lora_alpha: Optional[int] = Field(None, description="LoRA alpha")
    batch_size: int = Field(..., description="批次大小")
    gradient_accumulation_steps: int = Field(..., description="梯度累积步数")
    logging_steps: int = Field(..., description="日志保存间隔步数")
    eval_steps: int = Field(..., description="评估间隔步数")
    warmup_ratio: float = Field(..., description="预热比例")
    weight_decay: float = Field(..., description="权重衰减")
    max_seq_len: int = Field(..., description="最大序列长度")
    max_grad_norm: float = Field(..., description="最大梯度范数")
    split_dataset_ratio: float = Field(..., description="数据集划分比例")
    lr_warmup_iters_ratio: float = Field(..., description="学习率预热迭代比例")
    do_early_stop: bool = Field(..., description="是否启用早停")
    early_stop_patience: int = Field(..., description="早停耐心值")
    seed: Optional[int] = Field(None, description="随机种子")
    run_name: str = Field(..., description="运行名称")
    model_output_path: Optional[str] = Field(None, description="模型保存路径")
    log_path: Optional[str] = Field(None, description="日志路径")
    status: int = Field(..., description="训练状态")
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    duration: Optional[float] = Field(None, description="持续时间(秒)")
    train_data_count: Optional[int] = Field(None, description="实际参与训练数据数量")
    val_data_count: Optional[int] = Field(None, description="实际参与验证数据数量")
    error_message: Optional[str] = Field(None, description="错误信息")
    metrics: Optional[Dict[str, Any]] = Field(None, description="训练指标")
    best_model_path: Optional[str] = Field(None, description="最佳模型路径")
    model_code_suffix: Optional[str] = Field(None, description="生成的模型编码后缀")
    model_name: Optional[str] = Field(None, description="微调后模型的名称")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @field_validator("target_modules", mode="before")
    @classmethod
    def parse_target_modules(cls, v):
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return []
        return v

    @field_validator("metrics", mode="before")
    @classmethod
    def parse_metrics(cls, v):
        if isinstance(v, str):
            import json

            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v

    model_config = {
        "from_attributes": True,
    }


# 训练运行分页响应
class TrainingRunPageResponse(BaseModel):
    items: List[TrainingRunResponse] = Field(..., description="训练运行列表")
    total: int = Field(..., description="总条数")
    page: int = Field(..., description="页码")
    page_size: int = Field(..., description="每页大小")
    total_pages: int = Field(..., description="总页数")


# 训练指标统计响应
class TrainingMetricsResponse(BaseModel):
    training_run_id: int = Field(..., description="训练运行ID")
    train_loss_history: List[Dict[str, float]] = Field(..., description="训练损失历史")
    eval_metrics_history: List[Dict[str, Any]] = Field(..., description="评估指标历史")
    learning_rate_history: List[Dict[str, float]] = Field(..., description="学习率历史")
    best_metrics: Optional[Dict[str, Any]] = Field(None, description="最佳指标")
    best_epoch: Optional[int] = Field(None, description="最佳轮次")


# 中止训练请求
class AbortTrainingRequest(BaseModel):
    training_run_id: int = Field(..., description="训练运行ID")


# 模型评估结果响应
class ModelEvaluationResponse(BaseModel):
    training_run_id: int = Field(..., description="训练运行ID")
    model_path: str = Field(..., description="模型路径")
    accuracy: float = Field(..., description="准确率")
    precision: float = Field(..., description="精确率")
    recall: float = Field(..., description="召回率")
    f1_score: float = Field(..., description="F1分数")
    bleu_score: float = Field(..., description="BLEU分数")
    char_error_rate: float = Field(..., description="字符错误率")
    word_error_rate: float = Field(..., description="词错误率")
    evaluation_time: datetime = Field(..., description="评估时间")
    evaluated_samples: int = Field(..., description="评估样本数")
    evaluation_details: Optional[Dict[str, Any]] = Field(None, description="评估详细信息")
