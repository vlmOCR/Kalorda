from typing import List

from kalorda.utils.i18n import _


class SysRole:
    admin = {"code": "Admin", "name": _("管理员"), "desc": _("可进行所有操作")}
    annotator = {"code": "Annotator", "name": _("标注员"), "desc": _("可对数据集标注")}
    reviewer = {"code": "Reviewer", "name": _("审核员"), "desc": _("可审核标注数据")}
    trainer = {"code": "Trainer", "name": _("训练员"), "desc": _("可启动微调任务")}

    def get_all_roles():
        return [SysRole.admin, SysRole.annotator, SysRole.reviewer, SysRole.trainer]

    def get_role_by_code(code):
        for role in SysRole.get_all_roles():
            if role["code"] == code:
                return role
        return None

    def check_role_permission(user_role: str, required_roles: List[dict]):
        if not user_role:
            return False
        user_role = user_role.split(",")
        for role in required_roles:
            if role["code"] in user_role:
                return True
        return False


class OcrModel:
    got_ocr = {
        "hf_id": "stepfun-ai/GOT-OCR2_0",
        "ms_id": "stepfun-ai/GOT-OCR2_0",
        "code": "got_ocr",
        "name": "GOT_OCR",
        "desc": "stepfun-ai/0.6B",
        "url": "https://github.com/Ucas-HaoranWei/GOT-OCR2.0",
    }
    dotsocr = {
        "hf_id": "rednote-hilab/dots.ocr",
        "ms_id": "rednote-hilab/dots.ocr",
        "code": "dotsocr",
        "name": "dotsOCR",
        "desc": "rednote-hilab/3B",
        "url": "https://github.com/rednote-hilab/dots.ocr",
    }
    dolphin = {
        "hf_id": "ByteDance/Dolphin-v2",
        "ms_id": "ByteDance/Dolphin-v2",
        "code": "dolphin",
        "name": "Dolphin_v2",
        "desc": "ByteDance/3B",
        "url": "https://github.com/bytedance/Dolphin",
    }
    deepseek_ocr = {
        "hf_id": "deepseek-ai/DeepSeek-OCR",
        "ms_id": "deepseek-ai/DeepSeek-OCR",
        "code": "deepseek_ocr",
        "name": "Deepseek_OCR",
        "desc": "deepseek-ai/3B",
        "url": "https://github.com/deepseek-ai/DeepSeek-OCR",
    }
    paddleocr_vl = {
        "hf_id": "PaddlePaddle/PaddleOCR-VL",
        "ms_id": "PaddlePaddle/PaddleOCR-VL",
        "code": "paddleocr_vl",
        "name": "PaddleOCR_VL",
        "desc": "Baidu/0.9B",
        "url": "https://github.com/PaddlePaddle/PaddleOCR",
    }
    hunyuan_ocr = {
        "hf_id": "Tencent-Hunyuan/HunyuanOCR",
        "ms_id": "Tencent-Hunyuan/HunyuanOCR",
        "code": "hunyuan_ocr",
        "name": "HunyuanOCR",
        "desc": "Tencent/1B",
        "url": "https://github.com/Tencent-Hunyuan/HunyuanOCR",
    }
    deepseek_ocr2 = {
        "hf_id": "deepseek-ai/DeepSeek-OCR-2",
        "ms_id": "deepseek-ai/DeepSeek-OCR-2",
        "code": "deepseek_ocr2",
        "name": "Deepseek_OCR2",
        "desc": "deepseek-ai/3B",
        "url": "https://github.com/deepseek-ai/DeepSeek-OCR-2",
    }

    def get_all_models():
        return [
            OcrModel.got_ocr,
            OcrModel.dotsocr,
            OcrModel.dolphin,
            OcrModel.deepseek_ocr,
            OcrModel.paddleocr_vl,
            OcrModel.hunyuan_ocr,
            OcrModel.deepseek_ocr2,
        ]


# 数据集预识别状态，从1开始编号存储到数据中
class PreOCRStatus:
    # status = 1
    not_start = {
        "code": "not_start",
        "value": 1,
        "name": _("未开始"),
        "desc": _("预处理尚未开始"),
    }
    # status = 2
    waiting = {
        "code": "waiting",
        "value": 2,
        "name": _("等待中"),
        "desc": _("等待预处理中"),
    }
    # status = 3
    preprocessing = {
        "code": "preprocessing",
        "value": 3,
        "name": _("处理中"),
        "desc": _("数据集正在预处理中"),
    }
    # status = 4
    completed = {
        "code": "completed",
        "value": 4,
        "name": _("已完成"),
        "desc": _("数据集预处理已完成"),
    }
    # status = 5
    failed = {
        "code": "failed",
        "value": 5,
        "name": _("失败"),
        "desc": _("数据集预处理失败"),
    }
    # status = 6
    cancelled = {
        "code": "cancelled",
        "value": 6,
        "name": _("已取消"),
        "desc": _("数据集预处理已取消"),
    }

    def get_all_status():
        return [
            PreOCRStatus.not_start,
            PreOCRStatus.waiting,
            PreOCRStatus.preprocessing,
            PreOCRStatus.completed,
            PreOCRStatus.failed,
        ]


class CombineDataStatus:
    not_combined = {
        "code": "not_combined",
        "value": 1,
        "name": _("未合并"),
        "desc": _("数据集尚未合并"),
    }
    combining = {
        "code": "combining",
        "value": 2,
        "name": _("合并中"),
        "desc": _("数据集正在合并中"),
    }
    combined = {
        "code": "combined",
        "value": 3,
        "name": _("合并完成"),
        "desc": _("数据集合并完成"),
    }


class TrainingStatus:
    not_start = {
        "code": "not_start",
        "value": 1,
        "name": _("未开始"),
        "desc": _("训练尚未开始"),
    }
    waiting = {
        "code": "waiting",
        "value": 2,
        "name": _("等待中"),
        "desc": _("排队等待中"),
    }
    starting = {
        "code": "starting",
        "value": 3,
        "name": _("启动中"),
        "desc": _("启动中"),
    }
    running = {
        "code": "running",
        "value": 4,
        "name": _("运行中"),
        "desc": _("运行中"),
    }
    saving = {
        "code": "saving",
        "value": 5,
        "name": _("保存中"),
        "desc": _("保存中"),
    }
    completed = {
        "code": "completed",
        "value": 6,
        "name": _("已完成"),
        "desc": _("已完成"),
    }
    failed1 = {
        "code": "failed1",
        "value": 13,
        "name": _("已失败"),
        "desc": _("启动时失败"),
    }
    failed2 = {
        "code": "failed2",
        "value": 14,
        "name": _("已失败"),
        "desc": _("训练时失败"),
    }
    failed3 = {
        "code": "failed3",
        "value": 15,
        "name": _("已失败"),
        "desc": _("保存时失败"),
    }
    cancelled1 = {
        "code": "cancelled1",
        "value": 23,
        "name": _("已中止"),
        "desc": _("启动时中止"),
    }
    cancelled2 = {
        "code": "cancelled2",
        "value": 24,
        "name": _("已中止"),
        "desc": _("训练时中止"),
    }
    cancelled3 = {
        "code": "cancelled3",
        "value": 25,
        "name": _("已中止"),
        "desc": _("保存时中止"),
    }

    def get_all_status():
        return [
            TrainingStatus.not_start,
            TrainingStatus.waiting,
            TrainingStatus.starting,
            TrainingStatus.running,
            TrainingStatus.saving,
            TrainingStatus.completed,
            TrainingStatus.failed1,
            TrainingStatus.failed2,
            TrainingStatus.failed3,
            TrainingStatus.cancelled1,
            TrainingStatus.cancelled2,
            TrainingStatus.cancelled3,
        ]


class TestOCRStatus:
    not_start = {
        "code": "not_start",
        "value": 1,
        "name": _("未测试"),
        "desc": _("测试尚未开始"),
    }
    completed = {
        "code": "completed",
        "value": 2,
        "name": _("已完成"),
        "desc": _("测试已完成"),
    }
    failed = {
        "code": "failed",
        "value": 3,
        "name": _("失败"),
        "desc": _("测试失败"),
    }

    def get_all_status():
        return [
            TestOCRStatus.not_start,
            TestOCRStatus.completed,
            TestOCRStatus.failed,
        ]


class OCRBaseCategory:
    Text = 101  # 普通文本
    MixText = 102  # 混合文本
    Table = 103  # 表格
    MixTable = 104  # 混合表格
    Formula = 105  # 公式
    Molecular_formula = 106  # 化学分子式
    Musical_score = 107  # 乐谱
    Graphic = 108  # 图形图象
    Chart = 109  # 图表
    Title = 202  # 标题
    Subtitle = 203  # 子标题
    Chapter = 204  # 章节标题
    List_item = 201  # 列表
    Page_footer = 205  # 文档页脚
    Page_header = 206  # 文档页头
    Footnote = 207  # 脚注
    Caption = 208  # 说明文字
    Figure = 900  # 插图插画


# got_ocr区块类别划分（本来该模型是没有layout划分的，但是为了后续的处理方便，这里将普通文本和插图插画分别划分）
class GotOCRCategory:
    MixText = {
        "code": "MixText",
        "value": OCRBaseCategory.MixText,
        "name": _("混合文本"),
        "desc": _("混合文本"),
        "is_figure": False,
    }
    Figure = {
        "code": "Figure",
        "value": OCRBaseCategory.Figure,
        "name": _("插图插画"),
        "desc": _("插图插画"),
        "is_figure": True,
    }

    def get_all_categories():
        return [GotOCRCategory.MixText, GotOCRCategory.Figure]


# dotsOCR区块类别划分
class DotsOCRCategory:
    Text = {
        "code": "Text",
        "value": OCRBaseCategory.Text,
        "name": _("文本"),
        "desc": _("文本"),
        "is_figure": False,
    }
    Formula = {
        "code": "Formula",
        "value": OCRBaseCategory.Formula,
        "name": _("公式"),
        "desc": _("数学公式"),
        "is_figure": False,
    }
    Table = {
        "code": "Table",
        "value": OCRBaseCategory.Table,
        "name": _("表格"),
        "desc": _("表格"),
        "is_figure": False,
    }
    List_item = {
        "code": "List-item",
        "value": OCRBaseCategory.List_item,
        "name": _("列表"),
        "desc": _("列表"),
        "is_figure": False,
    }
    Title = {
        "code": "Title",
        "value": OCRBaseCategory.Title,
        "name": _("标题"),
        "desc": _("标题"),
        "is_figure": False,
    }
    Section_header = {
        "code": "Section-header",
        "value": OCRBaseCategory.Chapter,
        "name": _("章节标题"),
        "desc": _("章节标题"),
        "is_figure": False,
    }
    Page_footer = {
        "code": "Page-footer",
        "value": OCRBaseCategory.Page_footer,
        "name": _("文档页脚"),
        "desc": _("文档页脚"),
        "is_figure": False,
    }
    Page_header = {
        "code": "Page-header",
        "value": OCRBaseCategory.Page_header,
        "name": _("文档页头"),
        "desc": _("文档页头"),
        "is_figure": False,
    }
    Caption = {
        "code": "Caption",
        "value": OCRBaseCategory.Caption,
        "name": _("说明文字"),
        "desc": _("说明文字"),
        "is_figure": False,
    }
    Footnote = {
        "code": "Footnote",
        "value": OCRBaseCategory.Footnote,
        "name": _("文档脚注"),
        "desc": _("文档脚注"),
        "is_figure": False,
    }
    Picture = {
        "code": "Picture",
        "value": OCRBaseCategory.Figure,
        "name": _("插图插画"),
        "desc": _("插图插画"),
        "is_figure": True,
    }

    def get_all_categories():
        return [
            DotsOCRCategory.Text,
            DotsOCRCategory.Formula,
            DotsOCRCategory.Table,
            DotsOCRCategory.List_item,
            DotsOCRCategory.Title,
            DotsOCRCategory.Section_header,
            DotsOCRCategory.Page_footer,
            DotsOCRCategory.Page_header,
            DotsOCRCategory.Caption,
            DotsOCRCategory.Footnote,
            DotsOCRCategory.Picture,
        ]


class DolphinCategory:
    Para = {
        "code": "para",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    HalfPara = {
        "code": "half_para",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Sec0 = {
        "code": "sec_0",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Sec1 = {
        "code": "sec_1",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Sec2 = {
        "code": "sec_2",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Sec3 = {
        "code": "sec_3",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Sec4 = {
        "code": "sec_4",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Sec5 = {
        "code": "sec_5",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Formula = {
        "code": "equ",
        "value": OCRBaseCategory.Formula,
        "name": _("公式"),
        "desc": _("数学公式"),
        "is_figure": False,
    }
    Table = {
        "code": "tab",
        "value": OCRBaseCategory.Table,
        "name": _("表格"),
        "desc": _("表格"),
        "is_figure": False,
    }
    List_item = {
        "code": "list",
        "value": OCRBaseCategory.List_item,
        "name": _("列表项"),
        "desc": _("列表项"),
        "is_figure": False,
    }
    Code = {
        "code": "code",
        "value": OCRBaseCategory.Text,
        "name": _("代码"),
        "desc": _("代码"),
        "is_figure": False,
    }
    Caption = {
        "code": "cap",
        "value": OCRBaseCategory.Caption,
        "name": _("说明文字"),
        "desc": _("说明文字"),
        "is_figure": False,
    }
    Catalogue = {
        "code": "catalogue",
        "value": OCRBaseCategory.Chapter,
        "name": _("目录"),
        "desc": _("目录"),
        "is_figure": False,
    }
    Header = {
        "code": "header",
        "value": OCRBaseCategory.Page_header,
        "name": _("页头"),
        "desc": _("页头"),
        "is_figure": False,
    }
    Foot = {
        "code": "foot",
        "value": OCRBaseCategory.Page_footer,
        "name": _("页脚"),
        "desc": _("页脚"),
        "is_figure": False,
    }
    Footnote = {
        "code": "fnote",
        "value": OCRBaseCategory.Footnote,
        "name": _("脚注"),
        "desc": _("脚注"),
        "is_figure": False,
    }
    Reference = {
        "code": "reference",
        "value": OCRBaseCategory.Text,
        "name": _("引用"),
        "desc": _("引用"),
        "is_figure": False,
    }
    Watermark = {
        "code": "watermark",
        "value": OCRBaseCategory.Text,
        "name": _("水印"),
        "desc": _("水印"),
        "is_figure": False,
    }
    Annotation = {
        "code": "anno",
        "value": OCRBaseCategory.Text,
        "name": _("注释"),
        "desc": _("注释"),
        "is_figure": False,
    }
    Picture = {
        "code": "fig",
        "value": OCRBaseCategory.Figure,
        "name": _("插图插画"),
        "desc": _("插图插画"),
        "is_figure": True,
    }

    def get_all_categories():
        return [
            DolphinCategory.Para,
            DolphinCategory.HalfPara,
            DolphinCategory.Sec0,
            DolphinCategory.Sec1,
            DolphinCategory.Sec2,
            DolphinCategory.Sec3,
            DolphinCategory.Sec4,
            DolphinCategory.Sec5,
            DolphinCategory.Formula,
            DolphinCategory.Table,
            DolphinCategory.List_item,
            DolphinCategory.Code,
            DolphinCategory.Caption,
            DolphinCategory.Catalogue,
            DolphinCategory.Header,
            DolphinCategory.Foot,
            DolphinCategory.Footnote,
            DolphinCategory.Reference,
            DolphinCategory.Watermark,
            DolphinCategory.Annotation,
            DolphinCategory.Picture,
        ]


class DeepseekOCRCategory:
    Text = {
        "code": "Text",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Formula = {
        "code": "Formula",
        "value": OCRBaseCategory.Formula,
        "name": _("公式"),
        "desc": _("数学公式"),
        "is_figure": False,
    }
    Table = {
        "code": "Table",
        "value": OCRBaseCategory.Table,
        "name": _("表格"),
        "desc": _("表格"),
        "is_figure": False,
    }
    List_item = {
        "code": "List_item",
        "value": OCRBaseCategory.List_item,
        "name": _("列表项"),
        "desc": _("列表项"),
        "is_figure": False,
    }
    Title = {
        "code": "Title",
        "value": OCRBaseCategory.Title,
        "name": _("标题"),
        "desc": _("标题"),
        "is_figure": False,
    }
    Sub_title = {
        "code": "Sub_title",
        "value": OCRBaseCategory.Subtitle,
        "name": _("子标题"),
        "desc": _("子标题"),
        "is_figure": False,
    }
    Page_footer = {
        "code": "Page_footer",
        "value": OCRBaseCategory.Page_footer,
        "name": _("页脚"),
        "desc": _("页脚"),
        "is_figure": False,
    }
    Page_header = {
        "code": "Page_header",
        "value": OCRBaseCategory.Page_header,
        "name": _("页头"),
        "desc": _("页头"),
        "is_figure": False,
    }
    Caption = {
        "code": "Caption",
        "value": OCRBaseCategory.Caption,
        "name": _("说明文字"),
        "desc": _("说明文字"),
        "is_figure": False,
    }
    Footnote = {
        "code": "Footnote",
        "value": OCRBaseCategory.Footnote,
        "name": _("脚注"),
        "desc": _("脚注"),
        "is_figure": False,
    }
    Image = {
        "code": "Image",
        "value": OCRBaseCategory.Figure,
        "name": _("插图插画"),
        "desc": _("插图插画"),
        "is_figure": True,
    }

    def get_all_categories():
        return [
            DeepseekOCRCategory.Text,
            DeepseekOCRCategory.Formula,
            DeepseekOCRCategory.Table,
            DeepseekOCRCategory.List_item,
            DeepseekOCRCategory.Title,
            DeepseekOCRCategory.Sub_title,
            DeepseekOCRCategory.Page_footer,
            DeepseekOCRCategory.Page_header,
            DeepseekOCRCategory.Caption,
            DeepseekOCRCategory.Footnote,
            DeepseekOCRCategory.Image,
        ]


class DeepseekOCR2Category:
    Text = {
        "code": "Text",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Formula = {
        "code": "Formula",
        "value": OCRBaseCategory.Formula,
        "name": _("公式"),
        "desc": _("数学公式"),
        "is_figure": False,
    }
    Table = {
        "code": "Table",
        "value": OCRBaseCategory.Table,
        "name": _("表格"),
        "desc": _("表格"),
        "is_figure": False,
    }
    List_item = {
        "code": "List_item",
        "value": OCRBaseCategory.List_item,
        "name": _("列表项"),
        "desc": _("列表项"),
        "is_figure": False,
    }
    Title = {
        "code": "Title",
        "value": OCRBaseCategory.Title,
        "name": _("标题"),
        "desc": _("标题"),
        "is_figure": False,
    }
    Sub_title = {
        "code": "Sub_title",
        "value": OCRBaseCategory.Subtitle,
        "name": _("子标题"),
        "desc": _("子标题"),
        "is_figure": False,
    }
    Page_footer = {
        "code": "Page_footer",
        "value": OCRBaseCategory.Page_footer,
        "name": _("页脚"),
        "desc": _("页脚"),
        "is_figure": False,
    }
    Page_header = {
        "code": "Page_header",
        "value": OCRBaseCategory.Page_header,
        "name": _("页头"),
        "desc": _("页头"),
        "is_figure": False,
    }
    Caption = {
        "code": "Caption",
        "value": OCRBaseCategory.Caption,
        "name": _("说明文字"),
        "desc": _("说明文字"),
        "is_figure": False,
    }
    Footnote = {
        "code": "Footnote",
        "value": OCRBaseCategory.Footnote,
        "name": _("脚注"),
        "desc": _("脚注"),
        "is_figure": False,
    }
    Image = {
        "code": "Image",
        "value": OCRBaseCategory.Figure,
        "name": _("插图插画"),
        "desc": _("插图插画"),
        "is_figure": True,
    }

    def get_all_categories():
        return [
            DeepseekOCR2Category.Text,
            DeepseekOCR2Category.Formula,
            DeepseekOCR2Category.Table,
            DeepseekOCR2Category.List_item,
            DeepseekOCR2Category.Title,
            DeepseekOCR2Category.Sub_title,
            DeepseekOCR2Category.Page_footer,
            DeepseekOCR2Category.Page_header,
            DeepseekOCR2Category.Caption,
            DeepseekOCR2Category.Footnote,
            DeepseekOCR2Category.Image,
        ]


class PaddleOCRVLCategory:
    Text = {
        "code": "Text",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Formula = {
        "code": "Formula",
        "value": OCRBaseCategory.Formula,
        "name": _("公式"),
        "desc": _("数学公式"),
        "is_figure": False,
    }
    Table = {
        "code": "Table",
        "value": OCRBaseCategory.Table,
        "name": _("表格"),
        "desc": _("表格"),
        "is_figure": False,
    }
    Image = {
        "code": "Image",
        "value": OCRBaseCategory.Figure,
        "name": _("插图插画"),
        "desc": _("插图插画"),
        "is_figure": True,
    }

    def get_all_categories():
        return [
            PaddleOCRVLCategory.Text,
            PaddleOCRVLCategory.Formula,
            PaddleOCRVLCategory.Table,
            PaddleOCRVLCategory.Image,
        ]


class HunyuanOCRCategory:
    Text = {
        "code": "Text",
        "value": OCRBaseCategory.Text,
        "name": _("普通文本"),
        "desc": _("普通文本"),
        "is_figure": False,
    }
    Formula = {
        "code": "Formula",
        "value": OCRBaseCategory.Formula,
        "name": _("公式"),
        "desc": _("数学公式"),
        "is_figure": False,
    }
    Table = {
        "code": "Table",
        "value": OCRBaseCategory.Table,
        "name": _("表格"),
        "desc": _("表格"),
        "is_figure": False,
    }
    Image = {
        "code": "Image",
        "value": OCRBaseCategory.Figure,
        "name": _("插图插画"),
        "desc": _("插图插画"),
        "is_figure": True,
    }

    def get_all_categories():
        return [
            HunyuanOCRCategory.Text,
            HunyuanOCRCategory.Formula,
            HunyuanOCRCategory.Table,
            HunyuanOCRCategory.Image,
        ]
