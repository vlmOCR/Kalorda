<script lang="ts">
import { RouteMeta } from '@/router/MetaType';
export const routeMeta: RouteMeta = {
    title: 'label',
    icon: 'pi pi-database',
    displayMenu: 'hidden'
};
</script>
<script setup lang="ts">
import { Canvas, Group, FabricImage, controlsUtils, Rect, Point, Textbox, Control, filters } from 'fabric';
import { localStorageUtil } from '@/utils/LocalStorageUtil';
import { useLayout } from '@/layout/composables/layout';
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil';
import { DatasetService } from '@/services/DatasetService';
import { promise2, routeBack, $dom, queryParamValue, aesDecode, arraySwap, fileSizeStr } from '@/utils/Common';
// import { useConfirm } from "primevue/useconfirm";
import { useI18n } from 'vue-i18n';
import { getLanguage } from '@/assets/lang/language';
import QuillEditor from '@/components/editor/QuillEditor.vue';
// const confirm = useConfirm();
const { t } = useI18n();
const base = import.meta.env.VITE_APP_BASE;
const server_url = import.meta.env.VITE_API_SERVER_URL;
const aes_key = import.meta.env.VITE_APP_AES_KEY;

const { virtualSetActiveMenu, isDarkTheme } = useLayout(); //isDarkTheme
const parentRoute = base + '/train/dataset';

const tikzJaxJsUrl = base + '/static/tikz/tikzjax.js';
const tikzJaxJsId = 'tikzjax';

const getQuery = () => {
    let query = String(queryParamValue(window.location.href, 'query') || '');
    if (query) {
        query = decodeURIComponent(query);
        query = aesDecode(query, aes_key);
    }

    if (query) {
        try {
            return JSON.parse(query);
        } catch (error) {
            console.log(error);
            return {};
        }
    }
};

// 数据类型选择
let dataType0 = ref({
    name: t('page.dataview.nosetdatatype'),
    value: 0
});
let dataType1 = ref({
    name: t('page.dataview.datatype1'),
    value: 1
});
let dataType2 = ref({
    name: t('page.dataview.datatype2'),
    value: 2
});
const dataTypeItems = ref<any>([dataType0.value, dataType1.value, dataType2.value]);

const dataType = ref(dataType0);

const labelImageList = ref<any[]>([]); //{id: '', url: '', train_data_type: ''}
const currentLabelImage = ref();
const query = ref(getQuery());
const labelCategories = ref<any[]>([]);
const dataset = ref<any>();
// 1、获取图片序列id
const getLabelImageIdList = async () => {
    showLoading();
    let [err, res] = await promise2(DatasetService.getLabelImageIdList(query.value));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let _lableImageList = [];
        let image_id_list = res.data.image_id_list || [];
        for (let i = 0; i < image_id_list.length; i++) {
            _lableImageList.push({
                id: image_id_list[i],
                url: '',
                train_data_type: undefined // 0: 无标签数据，1: 训练数据，2: 验证数据
            });
        }
        labelImageList.value = _lableImageList;
        labelCategories.value = [
            {
                code: 'Not-Set',
                name: t('page.label.notset'),
                value: -1,
                is_figure: false
            },
            ...(res.data.category_list || [])
        ];
        dataset.value = res.data.dataset || {};
    }
};

let isFirstLazyLoad = true;
const loadLazyTimeout = ref();
const virtualScrollerRef = ref<any>();
const onLazyLoad = (event: any) => {
    if (loadLazyTimeout.value) {
        clearTimeout(loadLazyTimeout.value);
    }
    loadLazyTimeout.value = setTimeout(async () => {
        const { first, last } = event;
        const _lazyItems = [...labelImageList.value];

        let lazyImageList = [];
        for (let i = first; i < last; i++) {
            lazyImageList.push(_lazyItems[i]); // 收集当前实际需要懒加载的那部分数据
        }

        // console.log(_lazyItems.length, lazyImageList.length, first, last);

        let data = {
            dataset_id: query.value.dataset_id,
            image_ids: lazyImageList.map((item: any) => item.id)
        };
        let [err, res] = await promise2(DatasetService.getLabelImageUrlList(data));
        if (err) {
            // return;
        }
        if (res && res.code == 2000) {
            let image_url_list = res.data || [];
            let host = server_url.startsWith('http') ? server_url : window.location.origin;
            for (let i = first; i < last; i++) {
                let id = _lazyItems[i].id;
                let url = _lazyItems[i].url;
                let train_data_type = _lazyItems[i].train_data_type;
                if (url.length == 0) {
                    let item = image_url_list.find((item: any) => item.id == id);
                    url = host + item?.url;
                    train_data_type = item?.train_data_type;

                    _lazyItems[i].url = url;
                    _lazyItems[i].train_data_type = train_data_type;
                }
            }
        }

        labelImageList.value = _lazyItems;

        // 第一次懒加载时自动滚动到当前图片位置，只执行一次
        if (isFirstLazyLoad) {
            isFirstLazyLoad = false;
            let image_id = currentLabelImage.value.id || query.value.image_id;
            virtualScrolToImage(image_id);
        }
    }, 500);
};

// 虚拟滚动到指定图片位置
const virtualScrolToImage = (image_id: any) => {
    if (!image_id) return;
    let image_index = labelImageList.value.findIndex((item: any) => item.id == image_id);
    if (image_index < 0 || image_index >= labelImageList.value.length) return;
    setTimeout(() => {
        if (virtualScrollerRef.value) {
            virtualScrollerRef.value.scrollToIndex(image_index);
        }
    }, 0);
};

// 点击图片本身主动切换图片
const switchLabelImage = async (image_id: number | string) => {
    await getImageInfo(image_id); // 直接取图片信息
    resetInitData();
    loadImageToCanvas(currentLabelImage.value.base_64, initLabelInfo2Rect);
};

// 切换到上一张标注图片
const toPrevLabelImage = async () => {
    let result = await loadImageInfo(-1); // -1 表示切上一张
    if (!result) return;
    resetInitData();
    loadImageToCanvas(currentLabelImage.value.base_64, initLabelInfo2Rect);
    virtualScrolToImage(currentLabelImage.value.id);
};

// 切换到下一张标注图片
const toNextLabelImage = async () => {
    let result = await loadImageInfo(1); // 1 表示切下一张
    if (!result) return;
    resetInitData();
    loadImageToCanvas(currentLabelImage.value.base_64, initLabelInfo2Rect);
    virtualScrolToImage(currentLabelImage.value.id);
};

const getImageInfo = async (image_id: number | string) => {
    showLoading();
    let [err, res] = await promise2(DatasetService.getLabelImageInfo(image_id));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let image_info = res.data.image_info || {};
        let base_64 = res.data.base_64 || '';
        let host = server_url.startsWith('http') ? server_url : window.location.origin;
        currentLabelImage.value = image_info;
        currentLabelImage.value.file_path = host + currentLabelImage.value.file_path;
        currentLabelImage.value.base_64 = base_64;
        // currentLabelImage.value.base_64 = currentLabelImage.value.file_path

        // 回显数据类型：训练数据还是验证数据
        switch (image_info.train_data_type) {
            default:
            case 0:
                dataType.value = dataTypeItems.value[0];
                break;
            case 1:
                dataType.value = dataTypeItems.value[1];
                break;
            case 2:
                dataType.value = dataTypeItems.value[2];
                break;
        }
    }
};

const initLabelInfo2Rect = async () => {
    let ocr_label = currentLabelImage.value.ocr_label || '';
    let image_width = currentLabelImage.value.width;
    let image_height = currentLabelImage.value.height;

    // console.log(ocr_label);
    //got_ocr默认是整体一个文本识别结果，没有bbox的 paddlevl_ocr = 5  hunyuan_ocr = 6 firered_ocr=8
    if ((dataset.value.model_type == 1 || dataset.value.model_type == 5 || dataset.value.model_type == 6 || dataset.value.model_type == 8) && ocr_label.indexOf('"bbox"') == -1) {
        let labelInfo: LabelInfo = {
            id: `label_${Date.now()}`,
            pos1: [0, 0],
            pos2: [currentLabelImage.value.width, currentLabelImage.value.height],
            labelNumber: 1,
            labelStyle: { color: 'white', background: 'black' },
            // readIndex: 0,
            imageId: currentLabelImage.value.id,
            category: labelCategories.value[0],
            ocrText: ocr_label,
            editorValue: await markdown2Html(ocr_label),
            deleted: false
        };
        // 根据数据绘rect
        buildLableRect(labelInfo);
        imageLabelData.push(labelInfo);
        return;
    }

    //dolphin
    if (dataset.value.model_type == 3 && ocr_label.indexOf("\'label\':") != -1) {
        // dolphin 识别结果处理
        let list = eval(ocr_label); // dolphin 识别结果是一个数组，每个元素是一个对象，包含bbox、category、text
        for (let i = 0; i < list.length; i++) {
            let list_item = list[i];
            let bbox = list_item.bbox;
            let labelLabelVal = list_item.label;
            let category = labelCategories.value.find((item) => item.code == labelLabelVal) || labelCategories.value[0]; //label.category;;
            let text = list_item.text;
            let labelInfo: LabelInfo = {
                id: `label_${Date.now()}_${i}`,
                pos1: [bbox[0], bbox[1]],
                pos2: [bbox[2], bbox[3]],
                labelNumber: i + 1,
                labelStyle: { color: 'white', background: 'black' },
                // readIndex: i,
                imageId: currentLabelImage.value.id,
                category: category,
                ocrText: text,
                // 区块数量较多时如果立即执行await markdown2Html可能会感觉区块显示会有一点延迟（1-2秒），暂时先不赋值，让界面尽快显示
                editorValue: '',
                deleted: false
            };
            buildLableRect(labelInfo);
            imageLabelData.push(labelInfo);
        }

        // 界面上显示出区块后再赋值editorValue
        for (let i = 0; i < imageLabelData.length; i++) {
            let labelInfo = imageLabelData[i];
            labelInfo.editorValue = await markdown2Html(labelInfo.ocrText);
        }
        return;
    }

    //deepseek_ocr 识别结果处理
    if (dataset.value.model_type == 4 && ocr_label.includes('<|ref|>')) {
        // 解析deepseek ocr的bbox
        function parseDpseekBbox(bbox_str: string) {
            let bbox = bbox_str.replace('[[', '').replace(']]', '').split(',');
            let x1 = (parseFloat(bbox[0]) / 999) * image_width;
            let y1 = (parseFloat(bbox[1]) / 999) * image_height;
            let x2 = (parseFloat(bbox[2]) / 999) * image_width;
            let y2 = (parseFloat(bbox[3]) / 999) * image_height;
            return [x1, y1, x2, y2];
        }

        let labels = [];
        let list = ocr_label.split('<|ref|>');
        for (let i = 0; i < list.length; i++) {
            if (list[i].trim().length > 0) {
                let arr1 = list[i].split('<|/det|>');
                if (arr1.length == 2) {
                    let arr2 = arr1[0].trim().split('<|/ref|><|det|>');

                    let category = arr2[0].trim();
                    let bbox = parseDpseekBbox(arr2[1].trim());
                    let text = arr1[1].trim();
                    let label = {
                        bbox: bbox,
                        category: category,
                        text: text
                    };
                    labels.push(label);
                }
            }
        }

        for (let i = 0; i < labels.length; i++) {
            let label = labels[i] || {};
            let bbox = label.bbox;
            let category = labelCategories.value.find((item) => item.code.toLowerCase() == label.category.toLowerCase()) || labelCategories.value[0]; //label.category;
            let text = label.text;
            let labelInfo: LabelInfo = {
                id: `label_${Date.now()}_${i}`,
                pos1: [bbox[0], bbox[1]],
                pos2: [bbox[2], bbox[3]],
                labelNumber: i + 1,
                labelStyle: { color: 'white', background: 'black' },
                // readIndex: i,
                imageId: currentLabelImage.value.id,
                category: category,
                ocrText: text,
                // 区块数量较多时如果立即执行await markdown2Html可能会感觉区块显示会有一点延迟（1-2秒），暂时先不赋值，让界面尽快显示
                editorValue: '',
                deleted: false
            };
            buildLableRect(labelInfo);
            imageLabelData.push(labelInfo);
        }

        // 界面上显示出区块后再赋值editorValue
        for (let i = 0; i < imageLabelData.length; i++) {
            let labelInfo = imageLabelData[i];
            labelInfo.editorValue = await markdown2Html(labelInfo.ocrText);
        }
        return;
    }

    //deepseek_ocr2 识别结果处理
    if (dataset.value.model_type == 7 && ocr_label.includes('<|ref|>')) {
        // 解析deepseek ocr的bbox
        function parseDpseekBbox(bbox_str: string) {
            let bbox = bbox_str.replace('[[', '').replace(']]', '').split(',');
            let x1 = (parseFloat(bbox[0]) / 999) * image_width;
            let y1 = (parseFloat(bbox[1]) / 999) * image_height;
            let x2 = (parseFloat(bbox[2]) / 999) * image_width;
            let y2 = (parseFloat(bbox[3]) / 999) * image_height;
            return [x1, y1, x2, y2];
        }

        let labels = [];
        let list = ocr_label.split('<|ref|>');
        for (let i = 0; i < list.length; i++) {
            if (list[i].trim().length > 0) {
                let arr1 = list[i].split('<|/det|>');
                if (arr1.length == 2) {
                    let arr2 = arr1[0].trim().split('<|/ref|><|det|>');

                    let category = arr2[0].trim();
                    let bbox = parseDpseekBbox(arr2[1].trim());
                    let text = arr1[1].trim();
                    let label = {
                        bbox: bbox,
                        category: category,
                        text: text
                    };
                    labels.push(label);
                }
            }
        }

        for (let i = 0; i < labels.length; i++) {
            let label = labels[i] || {};
            let bbox = label.bbox;
            let category = labelCategories.value.find((item) => item.code.toLowerCase() == label.category.toLowerCase()) || labelCategories.value[0]; //label.category;
            let text = label.text;
            let labelInfo: LabelInfo = {
                id: `label_${Date.now()}_${i}`,
                pos1: [bbox[0], bbox[1]],
                pos2: [bbox[2], bbox[3]],
                labelNumber: i + 1,
                labelStyle: { color: 'white', background: 'black' },
                // readIndex: i,
                imageId: currentLabelImage.value.id,
                category: category,
                ocrText: text,
                // 区块数量较多时如果立即执行await markdown2Html可能会感觉区块显示会有一点延迟（1-2秒），暂时先不赋值，让界面尽快显示
                editorValue: '',
                deleted: false
            };
            buildLableRect(labelInfo);
            imageLabelData.push(labelInfo);
        }

        // 界面上显示出区块后再赋值editorValue
        for (let i = 0; i < imageLabelData.length; i++) {
            let labelInfo = imageLabelData[i];
            labelInfo.editorValue = await markdown2Html(labelInfo.ocrText);
        }
        return;
    }

    //dots_ocr 作为默认的标准格式
    ocr_label = ocr_label.substring(ocr_label.indexOf('[{'), ocr_label.lastIndexOf('}]') + 2);
    if (!ocr_label.startsWith('[{')) return;
    if (!ocr_label.endsWith('}]')) return;
    // console.log(ocr_label);
    let list = JSON.parse(ocr_label);
    for (let i = 0; i < list.length; i++) {
        let label = list[i] || {};

        let bbox = label.bbox;
        let category = labelCategories.value.find((item) => item.code == label.category) || labelCategories.value[0]; //label.category;
        let text = label.text;
        let labelInfo: LabelInfo = {
            id: `label_${Date.now()}_${i}`,
            pos1: [bbox[0], bbox[1]],
            pos2: [bbox[2], bbox[3]],
            labelNumber: i + 1,
            labelStyle: { color: 'white', background: 'black' },
            // readIndex: i,
            imageId: currentLabelImage.value.id,
            category: category,
            ocrText: text,
            // 区块数量较多时如果立即执行await markdown2Html可能会感觉区块显示会有一点延迟（1-2秒），暂时先不赋值，让界面尽快显示
            editorValue: '',
            deleted: false
        };
        // console.log(labelInfo.labelNumber, labelInfo.id);
        // 根据数据绘rect
        buildLableRect(labelInfo);
        imageLabelData.push(labelInfo);
    }
    // 界面上显示出区块后再赋值editorValue
    for (let i = 0; i < imageLabelData.length; i++) {
        let labelInfo = imageLabelData[i];
        labelInfo.editorValue = await markdown2Html(labelInfo.ocrText);
    }
};

// direction = 0 时，加载当前图片
// direction = 1 时，加载下一张图片
// direction = -1 时，加载上一张图片
const loadImageInfo = async (direction: number) => {
    if (labelImageList.value.length == 0) {
        return;
    }
    if (!currentLabelImage.value) {
        currentLabelImage.value = { id: query.value.image_id || 0 };
    }

    let currentImageId = currentLabelImage.value.id;
    let currentIndex = labelImageList.value.findIndex((item) => item.id == currentImageId);
    if (currentIndex == 0 && direction == -1) {
        showToast('warn', t('page.common.warn'), t('page.label.isfirstimage'), true);
        return false;
    }
    if (currentIndex == labelImageList.value.length - 1 && direction == 1) {
        showToast('warn', t('page.common.warn'), t('page.label.islastimage'), true);
        return false;
    }
    let image_id = labelImageList.value[currentIndex + direction]?.id;
    if (!image_id) {
        showToast('error', t('page.common.error'), t('page.label.isnotexistimage'), true);
        return false;
    }
    await getImageInfo(image_id);
    return true;
};

// Splitter gutter 拖动时高亮分割线
let splitterGutter: any = null;
let splitterGutterClass = 'p-splitter-gutter';
let splitterGutterHighlightClass = 'highlight_gutter';
let splitterGutterMouseOverClass = 'mouseover_gutter';
const onSplitterResizeStart = (e: any) => {
    let target = e.originalEvent.target;
    splitterGutter = target.closest('.' + splitterGutterClass); //className要加点.
    splitterGutter.classList.add(splitterGutterHighlightClass);
};
const onSplitterResizeEnd = (e: any) => {
    e;
    splitterGutter.classList.remove(splitterGutterHighlightClass);
    splitterGutter = null;
};
const splitterGutterMouseOverHandler = () => {
    $dom('.' + splitterGutterClass).classList.add(splitterGutterMouseOverClass);
};
const splitterGutterMouseOutHandler = () => {
    $dom('.' + splitterGutterClass).classList.remove(splitterGutterMouseOverClass);
};
const bindSplitterGutterMouseOver = () => {
    $dom('.' + splitterGutterClass).addEventListener('mouseover', splitterGutterMouseOverHandler);
    $dom('.' + splitterGutterClass)?.addEventListener('mouseout', splitterGutterMouseOutHandler);
};
const unbindSplitterGutterMouseOver = () => {
    $dom('.' + splitterGutterClass).removeEventListener('mouseover', splitterGutterMouseOverHandler);
    $dom('.' + splitterGutterClass)?.removeEventListener('mouseout', splitterGutterMouseOutHandler);
};
// 阻止 primeVue 按键时会聚焦panel
const onSplitterPanelFocus = (e: any) => {
    e.preventDefault();
    e.target.blur();
};
const setSplitterGutterBackgroundColor = () => {
    $dom('.' + splitterGutterClass).classList.add(isDarkTheme.value ? 'splitter-gutter-drak' : 'splitter-gutter-light');
};

const rightPanelMode = ref(1); // 1 列表显示 2 编辑 3 整体预览
const switchRightPanelMode = (mode: number) => {
    rightPanelMode.value = mode;
    let opacity = labelNumberOpacity(mode);
    fabricImageCanvas.forEachObject((o) => {
        if (o.type == 'group') {
            let rect = (o as any).mainRect;
            let label = (rect as any).labelRef;
            (label as any).set({
                opacity: opacity
            });
        }
    });
    fabricImageCanvas.requestRenderAll();

    if (selectedImageLabelData.value) {
        // 切换到编辑模式时候，更新一下editorValue
        // setTimeout(async () => {
        //     selectedImageLabelData.value.editorValue = await markdown2Html(selectedImageLabelData.value.ocrText);
        // }, 0);

        nextTick(() => {
            scrollToRowOrOcHtml(selectedImageLabelData.value.id);
        });
    }
};


const labelNumberOpacity = (rightPanelMode: number) => {
    // 第1个tab 列表显示 透明度1
    // 第2、3个tab 编辑或预览 透明度0.5
    return rightPanelMode == 1 ? 1 : 0.5;
};

// 更多操作菜单
const op = ref();

const toggleMoreMenu = (event: any) => {
    // moreMenuRef.value.toggle(event);
    op.value.toggle(event);
};

// 颜色设置
const currentSetting = ref();
const editedSetting = ref();
const defaultSetting = {
    rulerVisible: false, // 默认标尺是否显示
    gridVisible: false, // 默认网格是否显示
    crosshairColor: '00ff99', // 默认的十字线颜色
    lableRectColor: '00ff00', // 默认区块边框、高亮颜色
    labelAnchorColor: '0000ff' // 默认的区块拖拽锚点颜色
};
const localSetting = localStorageUtil.get('localConfig', 'labelSetting');
if (localSetting) {
    currentSetting.value = { ...localSetting };
} else {
    currentSetting.value = { ...defaultSetting };
}

const settingPopover = ref<any>();
const settingPopoverToggle = (event: any) => {
    editedSetting.value = { ...currentSetting.value };
    settingPopover.value.toggle(event);
};
const resetSetting = () => {
    editedSetting.value = { ...defaultSetting };
};
const saveSetting = (event: any) => {
    currentSetting.value = { ...editedSetting.value };
    localStorageUtil.set('localConfig', 'labelSetting', editedSetting.value);

    //已绘矩形边框颜色全换
    if (fabricImageCanvas) {
        const rgbTempColor = hexToRgb(editedSetting.value.lableRectColor);
        console.log(rgbTempColor);
        fabricImageCanvas.getObjects().forEach((obj: any) => {
            if (obj.type === 'group') {
                let group = obj as Group;
                let rect = (group as any).mainRect;
                rect.set('stroke', `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`);

                // 如果当前正是选中的group，更换rect填充颜色
                if (selectedLabelId.value == (group as any).labelId) {
                    rect.set({
                        fill: `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b},0.5)`
                    });
                }

                group.off('mouseover');
                group.off('mouseout');
                group.on('mouseover', () => {
                    let rect = (group as any).mainRect;
                    rect.set('fill', `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b},0.5)`);
                    fabricImageCanvas.requestRenderAll();
                });
                group.on('mouseout', () => {
                    let rect = (group as any).mainRect;
                    if (selectedLabelId.value == (rect as any).labelId) {
                        return;
                    }
                    rect.set('fill', '');
                    fabricImageCanvas.requestRenderAll();
                });
            }
        });
        fabricImageCanvas.requestRenderAll();
    }

    drawGridRulerCanvas();

    settingPopover.value.toggle(event);
};

interface LabelInfo {
    id: string;
    pos1: [number, number];
    pos2: [number, number];
    labelNumber: number;
    labelStyle: { color: string; background: string };
    // fabricGroup?: Group;
    // readIndex: number; // 阅读顺序(排序)可以调的

    imageId: number; // ocr图片id
    category: {
        code: string;
        name: string;
        value: number;
        is_figure: boolean;
    }; // 分类
    ocrText: string; // ocr识别的文本
    editorValue: string; // 编辑器回显内容（替换掉markdown得到的富html内容）
    deleted: boolean; // 增补
}
// 数据源
let imageLabelData: LabelInfo[] = reactive([]);
let selectedImageLabelData: any = ref(); // DataTable需要用到的
let editorValueSourceText = ref(''); // 源码编辑时显示的内容
let fabricImageCanvas: Canvas;

// 标签区块单独弹窗预览
const labelRectVisible = ref<boolean>(false);
const labelRect2Html = ref<string>('');

const imageCanvas = ref<HTMLCanvasElement>();
const currentMousePositionX = ref(0);
const currentMousePositionY = ref(0);
const currentZoom = ref(1); // 当前画布的缩放比例，放大缩小画布时这个值可以动态变的
const selectedLabelId = ref<string | null>(null);
const imageBrightness = ref(50); // 图片亮度
const imageContrast = ref(50); // 图片对比度
const imageSaturation = ref(50); // 图片饱和度
let init_imageCanvasRuntime = {
    isDragging: false, // 标记是否正在拖拽图像
    isDrawing: false, // 标记是否正在绘制图形
    isPanning: false, // 标记是否正在平移图像
    startX: 0, // 鼠标按下时的X坐标
    startY: 0, // 鼠标按下时的Y坐标
    lastX: 0, // 上一次鼠标X位置
    lastY: 0, // 上一次鼠标y位置
    tempRect: null, // 临时矩形框
    startPos: { x: 0, y: 0 } // 鼠标按下时的坐标
};
let imageCanvasRuntime: any = { ...init_imageCanvasRuntime };

// 切换图片时需要重置的数据
const resetInitData = () => {
    imageLabelData.length = 0; // 不能用imageLabelData = []; 会导致响应式丢失
    // fabricImageCanvas.clear();
    currentMousePositionX.value = 0;
    currentMousePositionY.value = 0;
    currentZoom.value = 0;
    selectedLabelId.value = null;
    selectedImageLabelData.value = null;
    drawingMode.value = false;
    imageCanvasRuntime = { ...init_imageCanvasRuntime };
    labelRectVisible.value = false;
    labelRect2Html.value = '';
    imageBrightness.value = 50; // 图片亮度
    imageContrast.value = 50; // 图片对比度
    imageSaturation.value = 50; // 图片饱和度
    // 重置历史记录
    resetHistory();
};

// 十字线Canvas、网格canvas以及显示开关
const crosshairCanvas = ref<HTMLCanvasElement>();
const gridRulerCanvas = ref<HTMLCanvasElement>();
const crosshairVisible = ref(true);

const createCrosshairCanvas = (container: HTMLElement) => {
    let canvas = container.querySelector<HTMLCanvasElement>('.cross-canvas');
    if (!canvas) {
        canvas = document.createElement('canvas');
        canvas.id = 'cross-canvas'; // 动态设置 id
        canvas.classList.add('cross-canvas');
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.pointerEvents = 'none'; // 事件透传到底层fabric canvas
        canvas.style.zIndex = '1999'; // 保证最上层
        container.appendChild(canvas);
    }
    // 设置canvas物理像素尺寸，防止模糊
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    return canvas;
};
// 网格标尺canvas
const createGridRulerCanvas = (container: HTMLElement) => {
    let canvas = container.querySelector<HTMLCanvasElement>('.grid-ruler-canvas');
    if (!canvas) {
        canvas = document.createElement('canvas');
        canvas.id = 'grid-ruler-canvas'; // 动态设置 id
        canvas.classList.add('grid-ruler-canvas');
        canvas.style.position = 'absolute';
        canvas.style.top = '0';
        canvas.style.left = '0';
        canvas.style.width = '100%';
        canvas.style.height = '100%';
        canvas.style.pointerEvents = 'none'; // 事件透传到底层fabric canvas
        canvas.style.zIndex = '1998'; // 保证最上层低于十字线canvas
        container.appendChild(canvas);
    }
    // 设置canvas物理像素尺寸，防止模糊
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;
    return canvas;
};

const initFabricCanvas = () => {
    if (!imageCanvas.value) return;
    const imageCanvasBoxElement = imageCanvas.value.parentElement;
    if (!imageCanvasBoxElement) return;

    fabricImageCanvas = new Canvas(imageCanvas.value, {
        width: imageCanvasBoxElement.clientWidth, // 设置Fabric的宽度为容器的宽度
        height: imageCanvasBoxElement.clientHeight, // 设置Fabric的高度为容器的高度
        // backgroundColor: "#ffff00", // 设置背景颜色为黄色
        selection: true, // 关闭选择功能
        stopContextMenu: true, // 关闭右键菜单
        preserveObjectStacking: true, // 允许对象堆栈改变
        altSelectionKey: 'altKey',
        uniformScaling: false,
        enableWebGL: true,
        enableRetinaScaling: false,
        renderingOptions: {
            preserveDrawingBuffer: true, // 对于 WebGL 很重要
            shouldCache: true // 启用缓存以优化渲染性能
        }
    });
};

// 加载图片到canvas 可重复调用，内部已做了必要判断及处理
const loadImageToCanvas = async (url: string, callback: Function) => {
    if (!fabricImageCanvas) {
        showToast('error', t('page.common.error'), t('page.label.canvaserror'), true);
        return;
    }
    // 如果有先清理之前的图片
    fabricImageCanvas.remove(...fabricImageCanvas.getObjects());
    const fabricImage = await FabricImage.fromURL(url, { crossOrigin: 'anonymous' });
    if (!fabricImage) {
        showToast('error', t('page.common.error'), t('page.label.imageerror'), true);
        return;
    }
    const fabricCanvasContainer = fabricImageCanvas.getElement().parentElement as HTMLElement;
    let imageScaleX = fabricCanvasContainer.clientHeight / fabricImage.height!;
    let imageScaleY = fabricCanvasContainer.clientWidth / fabricImage.width!;
    let imageScale = Math.min(imageScaleX, imageScaleY);
    imageScale = Math.min(1, imageScale);
    // if (imageScale > 1) {
    //     imageScale = 1;
    // }
    // fabricCanvasContainer.removeEventListener("mousemove", onMouseMove);
    // fabricCanvasContainer.removeEventListener("mouseleave", onMouseLeave);
    fabricImage.scale(imageScale); // 缩放图片以适应画布，这个值以后交互操作都不会变的，只是图片本身的缩放比例，不是画布的缩放比例zoom
    fabricImage.set({
        originX: 'center',
        originY: 'center',
        left: fabricCanvasContainer.clientWidth / 2,
        top: fabricCanvasContainer.clientHeight / 2,
        selectable: false,
        evented: false
    });
    fabricImageCanvas.setDimensions({
        width: fabricCanvasContainer.clientWidth,
        height: fabricCanvasContainer.clientHeight
    });
    fabricImageCanvas.add(fabricImage);
    // fabricImageCanvas.backgroundImage = fabricImage;
    currentZoom.value = fabricImageCanvas.getZoom();
    fabricImageCanvas.setViewportTransform([1, 0, 0, 1, 0, 0]);
    fabricImageCanvas.requestRenderAll();

    if (callback) callback();

    // 创建十字线canvas
    crosshairCanvas.value = createCrosshairCanvas(fabricCanvasContainer);
    const ctx = crosshairCanvas.value.getContext('2d')!;
    fabricCanvasContainer.removeEventListener('mousemove', onCrosshairMouseMove);
    fabricCanvasContainer.removeEventListener('mouseleave', onCrosshairMouseLeave);
    fabricCanvasContainer.addEventListener('mousemove', onCrosshairMouseMove);
    fabricCanvasContainer.addEventListener('mouseleave', onCrosshairMouseLeave);

    fabricImageCanvas.on(
        'mouse:move',
        throttle(function (opt: any) {
            // if (!opt.target || opt.target !== imgObj) return;
            // const pointer = fabricImageCanvas.getPointer(opt.e, true);
            const pointer = fabricImageCanvas.getViewportPoint(opt.e);
            // const pointer = fabricImageCanvas.getScenePoint(opt.e);
            const vpt = fabricImageCanvas.viewportTransform;
            // 将鼠标指针从canvas坐标系转换到视口坐标系
            const canvasX = (pointer.x - vpt[4]) / vpt[0];
            const canvasY = (pointer.y - vpt[5]) / vpt[3];
            // 计算图像左上角在canvas上的坐标
            const imgLeftTopX = fabricImage.left - (fabricImage.width * fabricImage.scaleX) / 2;
            const imgLeftTopY = fabricImage.top - (fabricImage.height * fabricImage.scaleY) / 2;
            // 转换为相对于图像左上角的坐标
            const relativeX = (canvasX - imgLeftTopX) / fabricImage.scaleX;
            const relativeY = (canvasY - imgLeftTopY) / fabricImage.scaleY;
            // currentMousePositionX.value = Math.round(relativeX);
            // currentMousePositionY.value = Math.round(relativeY);
            currentMousePositionX.value = Number(relativeX.toFixed(1));
            currentMousePositionY.value = Number(relativeY.toFixed(1));
        }, 50)
    );

    function onCrosshairMouseMove(e: MouseEvent) {
        let crosshairCanvaElement = crosshairCanvas.value ? crosshairCanvas.value : null;
        if (!crosshairCanvaElement) return;
        const rect: any = crosshairCanvaElement.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;
        if (!crosshairVisible.value) return;
        ctx.clearRect(0, 0, crosshairCanvaElement.width, crosshairCanvaElement.height);
        ctx.beginPath();
        ctx.strokeStyle = '#' + currentSetting.value.crosshairColor; // 十字线颜色
        ctx.lineWidth = 0.85;
        ctx.setLineDash([5, 5]);
        // 横线
        ctx.moveTo(0, y);
        ctx.lineTo(crosshairCanvaElement.width, y);
        // 纵线
        ctx.moveTo(x, 0);
        ctx.lineTo(x, crosshairCanvaElement.height);
        ctx.stroke();
    }

    function onCrosshairMouseLeave() {
        let crosshairCanvaElement = crosshairCanvas.value ? crosshairCanvas.value : null;
        if (!crosshairCanvaElement) return;
        ctx.clearRect(0, 0, crosshairCanvaElement.width, crosshairCanvaElement.height);
    }

    // 创建网格标尺线canvas
    drawGridRulerCanvas();
};

const drawGridRulerCanvas = () => {
    throttle(
        requestAnimationFrame(() => {
            _drawGridRulerCanvas();
        }),
        50
    );
    // requestAnimationFrame(() => {
    //     _drawGridRulerCanvas();
    // })
};
const _drawGridRulerCanvas = () => {
    const fabricCanvasContainer = fabricImageCanvas.getElement().parentElement as HTMLElement;
    gridRulerCanvas.value = createGridRulerCanvas(fabricCanvasContainer);
    const ctx = gridRulerCanvas.value.getContext('2d')!;
    // 清除现有的重新绘制
    ctx.clearRect(0, 0, gridRulerCanvas.value.width, gridRulerCanvas.value.height);

    // 绘制网格
    if (currentSetting.value.gridVisible) {
        ctx.beginPath();
        ctx.strokeStyle = '#777'; // 网格线颜色
        ctx.lineWidth = 0.5;
        ctx.setLineDash([1, 1]);
        let step = Math.ceil(Math.max(5, 10 * currentZoom.value)); // 网格线间距，根据缩放比例动态调整，最小5
        // 网格横线
        for (let i = 0; i < gridRulerCanvas.value.width; i += step) {
            ctx.moveTo(i, 0);
            ctx.lineTo(i, gridRulerCanvas.value.height);
        }
        // 网格纵线
        for (let i = 0; i < gridRulerCanvas.value.height; i += step) {
            ctx.moveTo(0, i);
            ctx.lineTo(gridRulerCanvas.value.width, i);
        }
        ctx.stroke();
    }

    // 绘制转90的纵向标尺刻度文字辅助函数
    const getOffsetY = (textValue: number): number => {
        let offset = 0; // 纵轴刻度文字转90显示，需要根据不同数值设置不同的偏移量
        if (textValue == 0) offset = 9;
        else if (textValue > 0 && textValue < 1000) offset = 20;
        else if (textValue >= 1000 && textValue < 10000) offset = 26;
        else if (textValue >= 10000) offset = 32;
        else if (textValue < 0 && textValue > -1000) offset = 24;
        else if (textValue < -1000 && textValue > -10000) offset = 30;
        else offset = 36;
        return offset;
    };
    const drawRotatedText = (ctx: CanvasRenderingContext2D, textValue: number, x: number, y: number, angle: number) => {
        ctx.save(); // 保存当前环境的状态
        ctx.translate(x, y + getOffsetY(textValue)); // 移动画布的原点到文本的中心点
        ctx.rotate((angle * Math.PI) / 180); // 旋转角度，转换为弧度
        ctx.fillText(textValue.toFixed(0), 0, 0); // 绘制文本，此时原点为(0,0)，即文本的中心点
        ctx.restore(); // 恢复之前保存的环境状态
    };
    const getRulerMeasure = (count: number) => {
        if (count <= 50) return 20;
        if (count <= 100) return 40;
        if (count <= 200) return 100;
        if (count <= 500) return 200;
        if (count <= 1000) return 400;
        if (count <= 2000) return 1000;
        if (count <= 5000) return 2000;
        else return 4000;
    };

    // 绘制横向和纵向标尺
    if (currentSetting.value.rulerVisible) {
        ctx.beginPath();
        ctx.fillStyle = isDarkTheme.value ? '#999' : '#333'; // 标尺文字颜色
        ctx.strokeStyle = isDarkTheme.value ? '#999' : '#333'; // 标尺刻度颜色
        ctx.lineWidth = 1;
        ctx.setLineDash([0, 0]);

        const rulerLineSizeLong = 15; // 标尺最长刻度长度
        const rulerlineSizeMiddle = rulerLineSizeLong * 0.5; // 标尺中等刻度长度
        const rulerLineSizeShort = rulerLineSizeLong * 0.3; // 标尺最短刻度长度

        const { left, top, zoom, imgScaleX, imgScaleY } = getFabricImageLeftTopOrginalPosition();
        if (zoom == 0) return;

        // 横向标尺绘制
        let step = 10 * zoom * imgScaleX; // 每一格刻度的物理像素长度,画布越缩小，step越小，刻度越小，标尺越密
        let num2 = Math.ceil((gridRulerCanvas.value.width - left) / step); // 以图片左上角为原点，计算0点右侧需要绘制多少个刻度
        let num1 = Math.ceil((left - 0) / step); // 计算0刻度左侧需要绘制多少个刻度
        let count = num1 + num2; // 总共要分成多少个刻度
        let rulerMeasure = getRulerMeasure(count);
        let startX = left - (num1 - 1) * step; // 开始绘制的起始坐标，从left开始倒推 num1-1 个刻度

        for (let i = 0; i < count; i++) {
            let x = startX + i * step; // 当前刻度的物理横坐标
            let value = Math.round(((i - num1 + 1) * step) / zoom / imgScaleX); // 该刻度代表的数值
            if (value % rulerMeasure == 0) {
                // 长刻度
                ctx.moveTo(x, 0);
                ctx.lineTo(x, rulerLineSizeLong);
                ctx.fillText(value.toFixed(0), x + 3, rulerLineSizeLong + 2); // +3 +2 是位置修正的偏移量
            } else if (value % (rulerMeasure / 2) == 0) {
                // 中刻度
                ctx.moveTo(x, 0);
                ctx.lineTo(x, rulerlineSizeMiddle);
            } else {
                // 短刻度
                ctx.moveTo(x, 0);
                ctx.lineTo(x, rulerLineSizeShort);
            }
        }

        // 纵向标尺绘制
        step = 10 * zoom * imgScaleY; // 每一格刻度的物理像素长度,画布越缩小，step越小，刻度越小，标尺越密
        num2 = Math.ceil((gridRulerCanvas.value.height - top) / step); // 计算纵轴0点下侧需要绘制多少个刻度
        num1 = Math.ceil((top - 0) / step); // 计算纵轴0刻度上侧需要绘制多少个刻度
        count = num1 + num2; // 总共要分成多少个刻度
        // rulerMeasure = getRulerMeasure(count); // 纵标尺用横轴的尺度基准，保持统一比较合适
        let startY = top - (num1 - 1) * step; // 开始绘制的起始坐标，从top开始倒推 num1-1 个刻度

        for (let i = 0; i < count; i++) {
            let y = startY + i * step; // 当前刻度的物理纵坐标
            let value = Math.round(((i - num1 + 1) * step) / zoom / imgScaleY); // 该刻度代表的数值
            if (value % rulerMeasure == 0) {
                // 长刻度
                ctx.moveTo(0, y);
                ctx.lineTo(rulerLineSizeLong, y);
                // 绘制纵轴刻度数值文字转90度显示坐标需要修正一下
                drawRotatedText(ctx, value, 16, y, -90);
            } else if (value % (rulerMeasure / 2) == 0) {
                // 中刻度
                ctx.moveTo(0, y);
                ctx.lineTo(rulerlineSizeMiddle, y);
            } else {
                // 短刻度
                ctx.moveTo(0, y);
                ctx.lineTo(rulerLineSizeShort, y);
            }
        }
        ctx.stroke();
    }
};

const throttle = (func: any, limit: number) => {
    let inThrottle: boolean = false;
    return function (this: any) {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => (inThrottle = false), limit);
        }
    };
};

const bindImageCanvasEvent = () => {
    if (!fabricImageCanvas) return;
    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    fabricImageCanvas.on('mouse:down', onImageCanvasMouseDown);
    fabricImageCanvas.on('mouse:move', onImageCanvasMouseMove);
    fabricImageCanvas.on('mouse:up', onImageCanvasMouseUp);
    fabricImageCanvas.on('mouse:wheel', onImageCanvasMouseWheel);
    fabricImageCanvas.on('mouse:dblclick', onImageCanvasMouseDblClick);
    fabricImageCanvas.on('object:added', onImageCanvasObjectAdded);
    fabricImageCanvas.on('object:modified', onImageCanvasObjectModefied);
};

const unbindImageCanvasEvent = () => {
    if (!fabricImageCanvas) return;
    window.removeEventListener('keydown', onKeyDown);
    window.removeEventListener('keyup', onKeyUp);
    fabricImageCanvas.off('mouse:down', onImageCanvasMouseDown);
    fabricImageCanvas.off('mouse:move', onImageCanvasMouseMove);
    fabricImageCanvas.off('mouse:up', onImageCanvasMouseUp);
    fabricImageCanvas.off('mouse:wheel', onImageCanvasMouseWheel);
    fabricImageCanvas.off('mouse:dblclick', onImageCanvasMouseDblClick);
    fabricImageCanvas.off('object:modified', onImageCanvasObjectModefied);
};

const onKeyDown = (e: KeyboardEvent) => {
    // console.log(e);
    let target = e.target || e.srcElement;
    // console.log(target);
    if (target && target instanceof HTMLElement) {
        console.log(target.tagName);
        if (target.tagName !== 'BODY' && target.tagName !== 'BUTTON') {
            //button是 上一个标签、下一个标签的按钮、查看区块的按钮
            return;
        }
    }

    if (e.key === 'Delete') {
        const activeObject = fabricImageCanvas.getActiveObject();
        if (activeObject) {
            if (activeObject.type == 'activeselection') {
                // 记录删除历史操作 第一处
                console.log('删除当前选中的多个对象');
                let deletedLableInfos = removeActiveObjects();
                if (deletedLableInfos.length > 0) {
                    recordHistory('del', deletedLableInfos);
                }
            } else if (selectedLabelId.value) {
                // 记录删除历史操作 第二处
                console.log('删除当前选中的单个对象');
                let deletedLabelInfos = removeObjectsByLabelId(selectedLabelId.value); //实际返回的只是含单个LabelInfo的数组
                if (deletedLabelInfos.length > 0) {
                    recordHistory('del', deletedLabelInfos);
                }
            }
        }
        return;
    }

    // 选中了rect的情况下
    if (selectedLabelId.value) {
        const activeObject = fabricImageCanvas.getActiveObject();
        if (!activeObject) return;

        //如果按了ctrl键，移动方向键表示沿对应方向增加宽高，调用相应控制点的actionHandler
        if (e.ctrlKey) {
            let step = 1;
            switch (e.key) {
                case 'ArrowUp':
                case 'ArrowDown':
                case 'ArrowLeft':
                case 'ArrowRight':
                    let rect = undefined;
                    switch (e.key) {
                        case 'ArrowUp':
                            activeObject.set({
                                height: activeObject.height + step
                            });
                            rect = (activeObject as any).mainRect;
                            rect.set({
                                height: rect.height + step,
                                top: rect.top - step / 2
                            });

                            break;
                        case 'ArrowDown':
                            activeObject.set({
                                height: activeObject.height - step
                            });
                            rect = (activeObject as any).mainRect;
                            rect.set({
                                height: rect.height - step,
                                top: rect.top + step / 2
                            });

                            break;
                        case 'ArrowLeft':
                            activeObject.set({
                                width: activeObject.width - step
                            });
                            rect = (activeObject as any).mainRect;
                            rect.set({
                                width: rect.width - step,
                                left: rect.left + step / 2
                            });
                            break;
                        case 'ArrowRight':
                            activeObject.set({
                                width: activeObject.width + step
                            });
                            rect = (activeObject as any).mainRect;
                            rect.set({
                                width: rect.width + step,
                                left: rect.left - step / 2
                            });
                            break;
                    }
                    const label = (rect as any).labelRef;
                    const boundingBox = activeObject.getBoundingRect(); // 获取绝对左上角
                    label.set({
                        left: boundingBox.left + 5,
                        top: boundingBox.top + 5
                    });
                    activeObject.setCoords();
                    fabricImageCanvas.requestRenderAll();
                    // 更新记录数据信息imageLabelData中的labelInfo对象的pos1,pos2
                    updateImageLabelPosition(activeObject);
                    return;
            }
        }

        // 没有按ctrl键，单纯按方向键仅表示移动矩形框
        let step = 1;
        switch (e.key) {
            case 'ArrowUp':
            case 'ArrowDown':
            case 'ArrowLeft':
            case 'ArrowRight':
                // 1. 移动选中的矩形框
                switch (e.key) {
                    case 'ArrowUp':
                        activeObject.top -= step;
                        break;
                    case 'ArrowDown':
                        activeObject.top += step;
                        break;
                    case 'ArrowLeft':
                        activeObject.left -= step;
                        break;
                    case 'ArrowRight':
                        activeObject.left += step;
                        break;
                }
                console.log('方向键控制');
                activeObject.setCoords();
                fabricImageCanvas.requestRenderAll();
                // 2. 移动跟随文本labelRef标签
                const rect = (activeObject as any).mainRect;
                const label = (rect as any).labelRef;
                const boundingBox = activeObject.getBoundingRect(); // 获取绝对左上角
                label.set({
                    left: boundingBox.left + 5,
                    top: boundingBox.top + 5
                });
                // 更新记录数据信息imageLabelData中的labelInfo对象的pos1,pos2
                updateImageLabelPosition(activeObject);
                return;
        }

        // 选中矩形框后，按Enter键，转到下一个矩形框
        if (e.key === 'Enter') {
            e.preventDefault(); //组织默认事件
            nextImageLabel();
            return;
        }
    }

    if (e.key === 'Control') {
        if (imageCanvasRuntime.isDrawing) {
            stopDrawRectangles();
        }
        return;
    }

    if (e.key === 'Shift') {
        if (!imageCanvasRuntime.isDrawing) {
            startDrawRectangles();
        }
    }
};

const onKeyUp = (e: KeyboardEvent) => {
    let target = e.target || e.srcElement;
    if (target && target instanceof HTMLElement) {
        if (target.tagName !== 'BODY') {
            return;
        }
    }

    // 撤销反撤销
    if (e.ctrlKey) {
        if (e.key === 'z') {
            console.log('撤销上一步操作');
            return undoHistory();
        }
        if (e.key === 'y') {
            console.log('反撤销上一步操作');
            return redoHistory();
        }
    }

    // if (e.key === "Control" || imageCanvasRuntime.isDrawing) {
    //     stopDrawRectangles();
    //     return;
    // }

    if (e.key === 'Escape') {
        console.log('取消');
    }

    if (e.key === 'Shift') {
        // imageCanvasRuntime.isDrawing = false;
        // fabricImageCanvas.selection = true;

        if (imageCanvasRuntime.isDrawing) {
            stopDrawRectangles();
        } else {
            startDrawRectangles();
        }
        return;
    }
};

// 辅助记录上一次的鼠标点击到的group的数据，用于后续鼠标抬起时onImageCanvasMouseUp方法中来判断是否需要记录历史
let lastLabelInfoClone = {};
let lastExtra = {};
const getGroupHistoryInfo = (group: Group, labelId: string) => {
    let labelInfo = imageLabelData.find((item) => item.id == labelId);
    if (!labelInfo) {
        return [{}, {}];
    }
    let labelInfoClone = {
        id: labelInfo.id,
        pos1: labelInfo.pos1,
        pos2: labelInfo.pos2
    };
    // 附加当前group的缩放比例信息
    let extra = {
        scaleX: group.scaleX,
        scaleY: group.scaleY
    };
    return [labelInfoClone, extra];
};

const onImageCanvasMouseDown = (opt: any) => {
    if (!opt.target) {
        // 用户点击画布空白处

        // console.log("点击空白处");
        unSelectRow(); // 右侧表格选中的行清除
    } else {
        const obj = opt.target as any;
        // console.log("obj=", obj);
        if (obj.labelId) {
            selectRow(obj.labelId); // 点击矩形框，选中右侧表格的行

            // 记录当前点击的矩形框的信息，用于后续鼠标抬起时onImageCanvasMouseUp方法中来判断是否需要记录历史
            let groupHistoryInfo = getGroupHistoryInfo(obj, obj.labelId);
            lastLabelInfoClone = groupHistoryInfo[0];
            lastExtra = groupHistoryInfo[1];
        }
    }

    // 获取鼠标位置
    const e = opt.e as MouseEvent;
    if (imageCanvasRuntime.isDrawing) {
        // 获取鼠标位置
        // const p = fabricImageCanvas.getPointer(e);
        const p = fabricImageCanvas.getScenePoint(e);
        // const p = fabricImageCanvas.getViewportPoint(e); // 暂时不能换成视口坐标系，不然计算逻辑需要重新改
        imageCanvasRuntime.startX = p.x;
        imageCanvasRuntime.startY = p.y;
        // 1. 复用对象，不要 remove + new
        if (!imageCanvasRuntime.tempRect) {
            // 创建矩形对象
            imageCanvasRuntime.tempRect = new Rect({
                left: imageCanvasRuntime.startX,
                top: imageCanvasRuntime.startY,
                width: 0,
                height: 0,
                subTargetCheck: true,
                borderColor: '#7BD91F', // 控制边框颜色
                cornerColor: '#7BD91F', // 控制点的颜色
                fill: 'rgba(123, 217, 31,0.05)',
                stroke: '#7BD91F',
                selectable: false,
                hasBorders: false,
                evented: false,
                strokeWidth: 1, //  描边宽度，不要除比例 1.0 / currentZoom.value
                cornerStrokeWidth: 1, // 控制点边框的宽度，不要除比例 1.0 / currentZoom.value
                strokeUniform: true, // 确保缩放时描边宽度不变
                objectCaching: false // 避免重复缓存导致性能差
            });
            fabricImageCanvas.add(imageCanvasRuntime.tempRect);
            imageCanvasRuntime.tempRect.setCoords();
            fabricImageCanvas.requestRenderAll();
        } else {
            imageCanvasRuntime.tempRect.set({ left: imageCanvasRuntime.startX, top: imageCanvasRuntime.startY });
            imageCanvasRuntime.tempRect.setCoords();
            fabricImageCanvas.requestRenderAll();
        }
    } else if (e.ctrlKey) {
        // 鼠标按下开始平移
        imageCanvasRuntime.isPanning = true;
        // 禁止选择
        fabricImageCanvas.selection = false;
        // 记录上次位置
        imageCanvasRuntime.lastX = e.clientX;
        imageCanvasRuntime.lastY = e.clientY;
        console.log('鼠标按下准备拖拽', e.clientX, e.clientY);
    }
};

const onImageCanvasMouseMove = (opt: any) => {
    const e = opt.e as MouseEvent;
    // 绘制中
    if (imageCanvasRuntime.isDrawing && imageCanvasRuntime.tempRect) {
        // console.log('move 绘制中', e.clientX, e.clientY);
        // 获取鼠标位置
        // const p = fabricImageCanvas.getPointer(e);
        const p = fabricImageCanvas.getScenePoint(e);
        // const p = fabricImageCanvas.getViewportPoint(e); // 暂时不能换成视口坐标系，不然计算逻辑需要重新改
        // 设置矩形的宽高和位置
        imageCanvasRuntime.tempRect.set({
            width: Math.abs(p.x - imageCanvasRuntime.startX),
            height: Math.abs(p.y - imageCanvasRuntime.startY),
            left: p.x < imageCanvasRuntime.startX ? p.x : imageCanvasRuntime.startX,
            top: p.y < imageCanvasRuntime.startY ? p.y : imageCanvasRuntime.startY
            // strokeDashArray: [5, 5], // 虚线样式
        });
        // 设置矩形的坐标
        imageCanvasRuntime.tempRect.setCoords();
        fabricImageCanvas.requestRenderAll();
    } else if (imageCanvasRuntime.isPanning) {
        // 拖拽移动画布中
        fabricImageCanvas.relativePan(new Point(e.clientX - imageCanvasRuntime.lastX, e.clientY - imageCanvasRuntime.lastY));
        // 记录最后位置
        imageCanvasRuntime.lastX = e.clientX;
        imageCanvasRuntime.lastY = e.clientY;

        //实时重建网格标尺
        drawGridRulerCanvas();
    } else {
        if (opt.target) {
            // 框选的方式一次选了多个对象被临时组合起来时，需要手动缝合文本textbox位置跟随rect变化
            const activeObjects = fabricImageCanvas.getActiveObjects();
            let group_list = [];
            for (const obj of activeObjects) {
                if (obj.type === 'group') {
                    const rect = (obj as any).mainRect;
                    const label = (rect as any).labelRef;
                    const boundingBox = rect.getBoundingRect(); // 获取绝对左上角
                    label.set({
                        left: boundingBox.left + 5,
                        top: boundingBox.top + 5
                    });
                    group_list.push(obj);
                    // updateImageLabelPosition(obj);
                }
            }
            // 更新lableInfo对象（右侧表格列表坐标同步变化）,防抖100ms
            throttle(updateImageLabelPosition(group_list), 100);
        } else {
            // console.log("单纯鼠标平移", e.clientX, e.clientY);
        }
    }
};
const onImageCanvasMouseUp = (opt: any) => {
    const e = opt.e as MouseEvent;
    // console.log("鼠标松开", e.clientX, e.clientY);
    imageCanvasRuntime.startPos.x = e.clientX;
    imageCanvasRuntime.startPos.y = e.clientY;
    if (imageCanvasRuntime.isDrawing && imageCanvasRuntime.tempRect) {
        // 允许选择对象
        fabricImageCanvas.selection = true;
        imageCanvasRuntime.isDrawing = false;

        // 不小心点的宽度为0的矩形
        if (imageCanvasRuntime.tempRect.width === 0 || imageCanvasRuntime.tempRect.height === 0) {
            // console.log("宽度为0的矩形改成默认最小大小");
            imageCanvasRuntime.tempRect.set({ width: 50, height: 30 });
        }

        // console.log("创建标签编辑器");
        // promptLabelEditor(imageCanvasRuntime.tempRect);
        addLabeledRect(imageCanvasRuntime.tempRect);
        // 添加后立即清空临时对象
        imageCanvasRuntime.tempRect = null;
        // 鼠标光标样式默认
        fabricImageCanvas.defaultCursor = 'default';
        fabricImageCanvas.forEachObject((o) => {
            // o.type === "rect" || o.type === "group" || o.type === "polygon"
            if (o.type === 'group') {
                o.selectable = true;
                o.evented = true;
            }
        });
        fabricImageCanvas.requestRenderAll();
        // console.log("绘制完成");
        // imageCanvasRuntime.isDrawing = false;
        drawingMode.value = false;
    } else if (imageCanvasRuntime.isPanning) {
        // 停止平移
        imageCanvasRuntime.isPanning = false;
        // 允许选择对象
        fabricImageCanvas.selection = true;
        console.log('鼠标松开拖拽结束', e.clientX, e.clientY);
    } else {
        const activeObjects = fabricImageCanvas.getActiveObjects();
        if (!activeObjects || activeObjects.length == 0) return;
        const groupObjects = activeObjects.filter((o) => o.type == 'group');
        if (groupObjects.length == 1) {
            let group = groupObjects[0] as Group;
            let labelId = (group as any).labelId;

            selectRow(labelId);

            // 记录修改历史
            let groupHistoryInfo = getGroupHistoryInfo(group, labelId);
            let labelInfoClone = groupHistoryInfo[0];
            let extra = groupHistoryInfo[1];
            if (JSON.stringify(labelInfoClone) !== JSON.stringify(lastLabelInfoClone) || JSON.stringify(extra) !== JSON.stringify(lastExtra)) {
                // 只有当数据有变化时才记录历史
                recordHistory('modify', lastLabelInfoClone as LabelInfo, lastExtra);
            }
        }
    }
};

// 区块标号字体大小设定和textbox宽度随文字长度变化
const textBoxFontSize = 12;
const textBoxWidth = (text: string) => {
    return 16 + (text.length - 3) * 8; // text前后-符号最少长度是3，如-1-
};

const onImageCanvasMouseWheel = (opt: any) => {
    const e = opt.e as WheelEvent;

    if (!e.ctrlKey) return;
    e.preventDefault();

    const delta = e.deltaY;
    const zoom = fabricImageCanvas.getZoom();
    const factor = delta > 0 ? 0.9 : 1.1; // 每次变化 10%
    let newZoom = zoom * factor;

    newZoom = Math.max(0.1, Math.min(newZoom, 10));

    currentZoom.value = newZoom;
    fabricImageCanvas.zoomToPoint(new Point(e.offsetX, e.offsetY), newZoom);

    // 调整文字大小（可选：也可随缩放变化）
    // fabricImageCanvas.getObjects("textbox").forEach((tb) => {
    //     tb.set("fontSize", 12 / newZoom); // 可选：让文字不随缩放变大变小
    // });
    fabricImageCanvas.getObjects().forEach((o: any) => {
        if (o.type === 'textbox') {
            o.fontSize = textBoxFontSize;
            o.width = textBoxWidth(o.text);
        }
    });

    fabricImageCanvas.requestRenderAll();

    // 重建标尺网格
    drawGridRulerCanvas();
};
const onImageCanvasMouseDblClick = (opt: any) => {
    if (opt.target) {
        const obj = opt.target as any;
        if (obj.type === 'group') {
            let labelId = obj.labelId;
            let labelInfo = imageLabelData.find((label: any) => label.id === labelId);
            if (labelInfo) {
                //编辑标签数据
                editLabelData(labelInfo);
            }
        }
    }
};

const onImageCanvasObjectAdded = (e: any) => {
    e;
    // console.log("onImageCanvasObjectAdded", e);
};
const onImageCanvasObjectModefied = (opt: any) => {
    // console.log("onImageCanvasObjectModefied", opt);
    const obj = opt.target as any;
    if (obj.labelId) {
        updateImageLabelPosition(obj);
    }
};

// 根据界面操作导致区块大小变化（包括拖动缩放、键盘调整大小）时
// 需要同步更新记录数据信息imageLabelData中的labelInfo对象的pos1,pos2
const updateImageLabelPosition = (o: any) => {
    // 开始单个group，也可以是多个group数组

    if (Array.isArray(o)) {
        o.forEach((obj) => updateImageLabelPosition(obj));
        return;
    }

    if (o && o.labelId) {
        const rect = (o as any).mainRect as any;
        if (!rect) return;
        const { pos1, pos2 } = calculateRectPosition(rect);
        let labelInfo = imageLabelData.find((label: any) => label.id === o.labelId);
        if (labelInfo) {
            labelInfo.pos1 = pos1;
            labelInfo.pos2 = pos2;
            // 更新标签区块预览
            updateLabelRect2Html(labelInfo);
        }
    }
};

// fabricImageCanvas 事件绑定结束

// 撤销反撤销时修改标签区块大小和位置
const modifyLabelRect = (labelInfo: LabelInfo, extra?: any) => {
    let group = fabricImageCanvas.getObjects('group').find((o: any) => o.type === 'group' && o.labelId === labelInfo.id);
    if (!group) return;
    let rect = (group as any).mainRect;
    if (!rect) return;
    let label = (rect as any).labelRef;
    if (!label) return;

    let pos = unCalculateRectPosition(labelInfo.pos1, labelInfo.pos2);
    console.log('撤销反撤销时修改标签区块大小和位置', pos, extra);
    let { left, top, width, height } = pos;
    let scaleX = extra?.scaleX || 1;
    let scaleY = extra?.scaleY || 1;
    let border = 1; // 边框宽度

    let scaleWidth = (width + border) / scaleX;
    let scaleHeight = (height + border) / scaleY;

    group.set({
        left: left + (width + border) / 2,
        top: top + (height + border) / 2,
        width: scaleWidth,
        height: scaleHeight,
        scaleX: scaleX,
        scaleY: scaleY
    });
    group.setCoords();

    const boundingBox = group.getBoundingRect(); // 获取绝对左上角
    label.set({
        left: boundingBox.left + 5,
        top: boundingBox.top + 5
    });

    fabricImageCanvas.setActiveObject(group);

    let realLabelInfo = imageLabelData.find((label: any) => label.id === labelInfo.id);
    if (realLabelInfo) {
        console.log('labelInfo2', realLabelInfo);
        realLabelInfo.pos1 = labelInfo.pos1;
        realLabelInfo.pos2 = labelInfo.pos2;

        // 选中当前区块 group《-》labelInfo
        selectedLabelId.value = realLabelInfo.id;
        selectedImageLabelData.value = realLabelInfo;

        setFabricActiveObject(realLabelInfo);
        // 更新标签区块预览
        updateLabelRect2Html(realLabelInfo);
    }
};

function hexToRgb(hex: any) {
    // 移除可能存在的#
    hex = hex.replace(/^#/, '');
    // 解析r、g、b的值
    let r: any = parseInt(hex.substring(0, 2), 16),
        g: any = parseInt(hex.substring(2, 4), 16),
        b: any = parseInt(hex.substring(4, 6), 16);
    return { r, g, b }; // 返回对象形式的RGB值
}

const stringToColour = (str: string, isRgb = true) => {
    str;
    const colour = '#' + currentSetting.value.lableRectColor;
    // 如果需要返回 RGB 格式
    if (isRgb) {
        return hexToRgb(colour);
    } else {
        return colour;
    }
};

// 给定相对图片的相对坐标，获取区块在画布中的绝对位置（不受缩放影响）
const unCalculateRectPosition = (pos1: [number, number], pos2: [number, number]): { left: number; top: number; width: number; height: number } => {
    const img = fabricImageCanvas.getObjects('image')[0] as FabricImage;
    const imgDisplayWidth = img.width! * img.scaleX;
    const imgDisplayHeight = img.height! * img.scaleY;
    const imgCenterX = img.left!;
    const imgCenterY = img.top!;
    const imgBaseLeft = imgCenterX - imgDisplayWidth / 2;
    const imgBaseTop = imgCenterY - imgDisplayHeight / 2;

    // 5. 转换为未缩放画布坐标系中的位置
    const canvasPos1 = new Point(pos1[0] * img.scaleX + imgBaseLeft, pos1[1] * img.scaleY + imgBaseTop);
    const canvasPos2 = new Point(pos2[0] * img.scaleX + imgBaseLeft, pos2[1] * img.scaleY + imgBaseTop);

    return { left: canvasPos1.x, top: canvasPos1.y, width: canvasPos2.x - canvasPos1.x - 1, height: canvasPos2.y - canvasPos1.y - 1 };
};

// 计算区块相对于图片的坐标位置（不受缩放影响）
const calculateRectPosition = (rect: any): { pos1: [number, number]; pos2: [number, number] } => {
    // const zoom = fabricImageCanvas.getZoom();
    // const vpt = fabricImageCanvas.viewportTransform || [1, 0, 0, 1, 0, 0];
    const img = fabricImageCanvas.getObjects('image')[0] as FabricImage;

    // 3. 计算图片实际显示尺寸
    const imgDisplayWidth = img.width! * img.scaleX;
    const imgDisplayHeight = img.height! * img.scaleY;

    // 4.1 获取图片中心点在画布坐标系中的位置
    const imgCenterX = img.left!;
    const imgCenterY = img.top!;

    // 4.2 计算图片左上角在画布原始坐标系（未缩放）中的位置
    const imgBaseLeft = imgCenterX - imgDisplayWidth / 2;
    const imgBaseTop = imgCenterY - imgDisplayHeight / 2;

    // 4.3 转换为未缩放画布坐标系中的位置
    // const imgLeft = (imgBaseLeft - vpt[4]) / zoom;
    // const imgTop = (imgBaseTop - vpt[5]) / zoom;

    const rectIndo = rect.getBoundingRect();
    // 6. 转换函数：画布坐标 → 图片原始坐标
    const toImageOriginalPos = (point: Point): [number, number] => {
        // 6.1 移除画布变换
        // const canvasX = (point.x - vpt[4]) / zoom;
        // const canvasY = (point.y - vpt[5]) / zoom;

        // // 6.2 转换为相对于图片左上角的坐标
        // const relativeX = canvasX - imgLeft;
        // const relativeY = canvasY - imgTop;

        // // 6.3 转换为原始图片像素坐标
        // return [(relativeX / img.scaleX) * zoom, (relativeY / img.scaleY) * zoom];

        return [(point.x - imgBaseLeft) / img.scaleX, (point.y - imgBaseTop) / img.scaleY];
    };

    // 8. 转换坐标
    const newPos1 = toImageOriginalPos(new Point(rectIndo.left, rectIndo.top));
    const newPos2 = toImageOriginalPos(new Point(rectIndo.left + rectIndo.width, rectIndo.top + rectIndo.height));
    return {
        pos1: newPos1,
        pos2: newPos2
    };
};

// 获取fabric图片的左上角相对于容器左上角的视窗坐标
const getFabricImageLeftTopOrginalPosition = (): { left: number; top: number; zoom: number; imgScaleX: number; imgScaleY: number } => {
    const zoom = fabricImageCanvas.getZoom();
    const vpt = fabricImageCanvas.viewportTransform || [1, 0, 0, 1, 0, 0];
    const img = fabricImageCanvas.getObjects('image')[0] as FabricImage;
    if (!img) return { left: 0, top: 0, zoom: 0, imgScaleX: 0, imgScaleY: 0 };
    // 获取图片在画布中的原始位置
    // console.log(img.left!, img.top!, img.width!, img.height!, img.scaleX, img.scaleY);
    // zoom 是画布的缩放比例，scaleX scaleY 是图片在画布中自身的缩放比例
    const imgBaseLeft = img.left! - (img.width! * img.scaleX) / 2;
    const imgBaseTop = img.top! - (img.height! * img.scaleY) / 2;
    const imgLeft = imgBaseLeft * zoom + vpt[4];
    const imgTop = imgBaseTop * zoom + vpt[5];

    return { left: imgLeft, top: imgTop, zoom: zoom, imgScaleX: img.scaleX, imgScaleY: img.scaleY };
};

const updateLabelRect2Html = (labelIdorLabelInfo: string | LabelInfo, zoom: number = 5) => {
    // 弹窗没打开则不用更新
    if (!labelRectVisible.value) {
        return;
    }
    if (typeof labelIdorLabelInfo == 'string') {
        let labelId = labelIdorLabelInfo;
        let labelInfo = imageLabelData.find((item) => item.id === labelId);
        if (labelInfo) {
            labelRect2Html.value = cropCanvasImage2Html(labelInfo, zoom, false);
        }
    } else {
        labelRect2Html.value = cropCanvasImage2Html(labelIdorLabelInfo as LabelInfo, zoom, false);
    }
};

const openLabelRectDialog = () => {
    if (!selectedLabelId.value) {
        return;
    }
    labelRectVisible.value = true;
    updateLabelRect2Html(selectedImageLabelData.value);
};

const closeLabelRectDialog = () => {
    labelRectVisible.value = false;
};

// 插图插画裁剪(不受缩放影响)
const cropCanvasImage2Html = (labelInfo: LabelInfo, zoom: number = 1, showImageTitle: boolean = true) => {
    let x = labelInfo.pos1[0];
    let y = labelInfo.pos1[1];
    let width = labelInfo.pos2[0] - labelInfo.pos1[0];
    let height = labelInfo.pos2[1] - labelInfo.pos1[1];

    let pos = unCalculateRectPosition(labelInfo.pos1, labelInfo.pos2);
    let canvas_width = pos.width * zoom; // zoom 放大或缩小倍数
    let canvas_height = pos.height * zoom;

    let canvas = document.createElement('canvas');
    let ctx = canvas.getContext('2d')!;
    canvas.width = canvas_width;
    canvas.height = canvas_height;
    const img = fabricImageCanvas.getObjects('image')[0] as FabricImage;
    ctx.drawImage(img._element, x, y, width, height, 0, 0, canvas_width, canvas_height);
    let cropImage = canvas.toDataURL('image/jpeg');
    canvas.remove();
    //<div class="text-sm">${labelInfo.category.name}</div>
    let title = showImageTitle ? labelInfo.category?.name || '' : '';
    return `<img src=${cropImage} title="${title}" />`;
};

// 根据LabelInfo数据生成rect
const buildLableRect = (labelInfo: LabelInfo) => {
    if (!labelInfo) return;
    labelInfo.deleted = false;
    let id = labelInfo.id;
    let labelNumber = labelInfo.labelNumber;
    let pos = unCalculateRectPosition(labelInfo.pos1, labelInfo.pos2);
    const rgbTempColor: any = stringToColour(labelNumber + '');
    const rect = new Rect({
        left: pos.left,
        top: pos.top,
        width: pos.width,
        height: pos.height,
        fill: `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b}, 0)`, // 填充颜色
        stroke: `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`, // 边框颜色
        selectable: true,
        // originX: "center",
        // originY: "center",
        evented: false,
        strokeWidth: 1, //  描边宽度，不要除比例 1.0 / currentZoom.value
        cornerStrokeWidth: 1, // 控制点边框的宽度，不要除比例 1.0 / currentZoom.value
        strokeUniform: true, // 确保缩放时描边宽度不变
        objectCaching: false // 避免重复缓存导致性能差

        // opacity: labelNumberOpacity(rightPanelMode.value),
    });

    const tb = new Textbox(`-${labelNumber}-`, {
        left: rect.left! + 5,
        top: rect.top! + 5,
        width: textBoxWidth(`-${labelNumber}-`),

        editable: false,
        fontSize: textBoxFontSize, // 12 / currentZoom.value
        fill: '#fff', // 白字
        backgroundColor: '#f00', // 蓝色底
        // fill: `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`,
        // borderColor: `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`,
        selectable: false,
        evented: false, // 不参与事件
        // backgroundColor: style.background,
        opacity: labelNumberOpacity(rightPanelMode.value)
    });
    const group = new Group([rect], {
        hasBorders: false,
        selectable: true,
        evented: true,
        subTargetCheck: true
    });
    (group as any).labelId = id; // 不要用 set，直接设置属性
    const left = group.left!;
    const top = group.top!;
    // 设置头顶的旋转点的旋转中心
    group.set({
        originX: 'center',
        originY: 'center'
    });
    // 设置 group 的位置
    group.set({
        left: left + group.width / 2,
        top: top + group.height / 2
    });
    // 更新 group 的坐标
    group.setCoords();
    // 设置操作点
    group.controls = createCustomControls();
    rect.controls = createCustomControls();
    // 添加 group 到画布
    fabricImageCanvas.add(group);
    fabricImageCanvas.add(tb);
    // 更新画布
    fabricImageCanvas.requestRenderAll();

    //--------------------------start-------------------------

    (rect as any).labelRef = labelNumber;
    (rect as any).labelId = id;
    // 拖动时同步 label 位置
    group.on('moving', () => {
        const boundingBox = group.getBoundingRect(); // 获取绝对左上角
        tb.set({
            left: boundingBox.left + 5,
            top: boundingBox.top + 5
        });
    });
    group.on('mouseover', () => {
        rect.set('fill', `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b},0.5)`);
        fabricImageCanvas.requestRenderAll();
    });
    group.on('mouseout', () => {
        if (selectedLabelId.value == (rect as any).labelId) {
            return;
        }
        rect.set('fill', '');
        fabricImageCanvas.requestRenderAll();
    });
    rect.on('mousedown', (e: any) => {
        // 选中当前 rectSmall 对象
        // fabricImageCanvas.setActiveObject(rect);
        // // 重新渲图——必要，否则选中框不会出现
        // fabricImageCanvas.requestRenderAll();
        const obj: any = e.target as any;
        if (obj && obj.labelId) {
            selectedLabelId.value = obj.labelId;
        }
        // console.log("已选中小矩形", selectedLabelId.value);
    });

    (group as any).mainRect = rect;
    (rect as any).labelRef = tb;
    (group as any).labelId = id;
    (rect as any).labelId = id;
    (tb as any).labelId = id;
    // (rect as any).labelRef = tb;
    group.on('scaling', () => {
        const rect = (group as any).mainRect;
        const label = (rect as any).labelRef;
        const boundingBox = group.getBoundingRect(); // 获取绝对左上角
        label.set({
            left: boundingBox.left + 5,
            top: boundingBox.top + 5
        });
    });

    // rect.set("fill","");
};

const addLabeledRect = (rect: any) => {
    let count = imageLabelData.length; // label总数量（包括已删除的）

    let notDeletedImageLabelData = imageLabelData.filter((item: any) => !item.deleted); // 未删除的label
    let labelNumber = notDeletedImageLabelData.length; // 新的label暂编号
    // 如果有空洞编号则补上（因为有的label被删除）
    let existNumbers: number[] = [];
    notDeletedImageLabelData.forEach((item: any) => {
        let number = item.labelNumber;
        existNumbers.push(number - 1);
    });
    for (let i = 0; i < count; i++) {
        if (!existNumbers.includes(i)) {
            labelNumber = i;
            break;
        }
    }
    labelNumber += 1; // 新label编号

    const id = `label_${Date.now()}`;
    const style = { color: '#ff00ff', background: '' };
    const rgbTempColor: any = stringToColour(labelNumber + '');
    // rect.set(
    //   "fill",
    //   `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b},0.05)`
    // );
    rect.set('stroke', `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`);
    // rect.set("strokeDashArray", 0); // 虚线样式

    const tb = new Textbox(`-${labelNumber}-`, {
        left: rect.left! + 5,
        top: rect.top! + 5,
        width: textBoxWidth(`-${labelNumber}-`),

        editable: false,
        fontSize: textBoxFontSize, // 12 / currentZoom.value,
        fill: '#fff', // 白字
        backgroundColor: '#f00', // 蓝色底
        // fill: `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`,
        // borderColor: `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`,
        selectable: false,
        evented: false, // 不参与事件
        // backgroundColor: style.background,
        opacity: labelNumberOpacity(rightPanelMode.value)
    });
    const group = new Group([rect], {
        hasBorders: false,
        selectable: true,
        evented: true,
        subTargetCheck: true
    });
    (group as any).labelId = id; // 不要用 set，直接设置属性
    const left = group.left!;
    const top = group.top!;
    // 设置头顶的旋转点的旋转中心
    group.set({
        originX: 'center',
        originY: 'center'
    });
    // 设置 group 的位置
    group.set({
        left: left + group.width / 2,
        top: top + group.height / 2
    });
    // 更新 group 的坐标
    group.setCoords();
    // 设置操作点
    group.controls = createCustomControls();
    rect.controls = createCustomControls();
    // 添加 group 到画布
    fabricImageCanvas.add(group);
    fabricImageCanvas.add(tb);
    // 更新画布
    fabricImageCanvas.requestRenderAll();

    //--------------------------start-------------------------
    // 2. 获取画布变换参数
    const { pos1, pos2 } = calculateRectPosition(rect);
    console.log('newPos1,newPos2', pos1, pos2);
    //--------------------------end---------------------------
    // 创建标签数据
    let labelInfo: LabelInfo = {
        id,
        pos1: pos1, // 左上角坐标
        pos2: pos2, // 右下角坐标
        labelNumber: labelNumber,
        labelStyle: style,
        // fabricGroup: group,
        // readIndex: count, // 按总数标记（删除不删除的都算）
        imageId: currentLabelImage.value.id,
        category: labelCategories.value[0],
        ocrText: '',
        editorValue: '',
        deleted: false
    };
    imageLabelData.push(labelInfo);

    (rect as any).labelRef = labelNumber;
    (rect as any).labelId = id;
    // 拖动时同步 label 位置
    group.on('moving', () => {
        const boundingBox = group.getBoundingRect(); // 获取绝对左上角
        tb.set({
            left: boundingBox.left + 5,
            top: boundingBox.top + 5
        });
    });
    group.on('mouseover', () => {
        rect.set('fill', `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b},0.5)`);
        fabricImageCanvas.requestRenderAll();
    });
    group.on('mouseout', () => {
        if (selectedLabelId.value == (rect as any).labelId) {
            return;
        }
        rect.set('fill', '');
        fabricImageCanvas.requestRenderAll();
    });
    rect.on('mousedown', (e: any) => {
        // 选中当前 rectSmall 对象
        // fabricImageCanvas.setActiveObject(rect);
        // // 重新渲图——必要，否则选中框不会出现
        // fabricImageCanvas.requestRenderAll();
        const obj: any = e.target as any;
        if (obj && obj.labelId) {
            selectedLabelId.value = obj.labelId;
        }
        // console.log("已选中小矩形", selectedLabelId.value);
    });

    (group as any).mainRect = rect;
    (rect as any).labelRef = tb;
    (group as any).labelId = id;
    (rect as any).labelId = id;
    (tb as any).labelId = id;
    (rect as any).labelRef = tb;
    group.on('scaling', () => {
        const rect = (group as any).mainRect;
        const label = (rect as any).labelRef;
        const boundingBox = group.getBoundingRect(); // 获取绝对左上角
        label.set({
            left: boundingBox.left + 5,
            top: boundingBox.top + 5
        });
    });

    rect.set('fill', '');
    // 记录添加操作 只有这个地方一处
    recordHistory('add', labelInfo);

    // 右侧表格滚动到对应的行
    nextTick(() => {
        scrollToRowOrOcHtml(id);
    });
};

// 绘制实心绿色圆形【控制锚点绘制】
const renderSolidGreenCircle = (ctx: CanvasRenderingContext2D, left: number, top: number) => {
    const size = 10;
    ctx.save();
    ctx.fillStyle = '#' + currentSetting.value.labelAnchorColor; // 拖拽锚点填充色
    ctx.beginPath();
    ctx.arc(left, top, size / 2, 0, 2 * Math.PI);
    ctx.fill();
    ctx.restore();
};

const createCustomControls = () => {
    const commonOpts = {
        cursorStyle: 'pointer', // 鼠标样式
        withConnection: false, // 是否连接
        render: renderSolidGreenCircle, // 绘制圆形
        cornerSize: 10 // 控制点大小
    };

    return {
        // 左上角
        tl: new Control({
            ...commonOpts,
            x: -0.5,
            y: -0.5,
            cursorStyle: 'nw-resize',
            actionHandler: controlsUtils.scalingEqually
        }),
        // 右上角
        tr: new Control({
            ...commonOpts,
            x: 0.5,
            y: -0.5,
            cursorStyle: 'ne-resize',
            actionHandler: controlsUtils.scalingEqually
        }),
        // 左下角
        bl: new Control({
            ...commonOpts,
            x: -0.5,
            y: 0.5,
            cursorStyle: 'sw-resize',
            actionHandler: controlsUtils.scalingEqually
        }),
        // 右下角
        br: new Control({
            ...commonOpts,
            x: 0.5,
            y: 0.5,
            cursorStyle: 'se-resize',
            actionHandler: controlsUtils.scalingEqually
        }),

        // // 左边中点 - 横向缩放
        ml: new Control({
            ...commonOpts,
            x: -0.5,
            y: 0,

            cursorStyle: 'w-resize',
            actionHandler: controlsUtils.scalingX
        }),
        // 右边中点 - 横向缩放
        mr: new Control({
            ...commonOpts,
            x: 0.5,
            y: 0,
            cursorStyle: 'e-resize',
            actionHandler: controlsUtils.scalingX
        }),
        // 上边中点 - 纵向缩放
        mt: new Control({
            ...commonOpts,
            x: 0,
            y: -0.5,
            cursorStyle: 'n-resize',
            actionHandler: controlsUtils.scalingY
        }),
        // 下边中点 - 纵向缩放
        mb: new Control({
            ...commonOpts,
            x: 0,
            y: 0.5,
            cursorStyle: 's-resize',
            actionHandler: controlsUtils.scalingY
        })
    };
};

// 帮助弹窗是否可见
const helpVisible = ref(false);

const drawingMode = ref(imageCanvasRuntime.isDragging);
const startDrawRectangles = () => {
    // 点菜单按钮就清空选中的label（如果有选中的对象）

    selectedLabelId.value = null;
    selectedImageLabelData.value = null;

    imageCanvasRuntime.isPanning = false;
    fabricImageCanvas.selection = false;

    fabricImageCanvas.forEachObject((o) => {
        if (o.type === 'group') {
            let rect = (o as any).mainRect;
            rect.set({
                fill: ''
            });
        }
    });
    // fabricImageCanvas.requestRenderAll();

    selectedLabelId.value = null;
    selectedImageLabelData.value = null;
    fabricImageCanvas.discardActiveObject();
    fabricImageCanvas.requestRenderAll();
    // 取消区块预览弹窗
    closeLabelRectDialog();
    // 已选中的表格行取消高亮
    selectedImageLabelData.value = null;

    if (!imageCanvasRuntime.isDrawing) {
        drawingMode.value = true;
        imageCanvasRuntime.isDrawing = true;
        // 禁止选择
        fabricImageCanvas.selection = false;
        fabricImageCanvas.defaultCursor = 'crosshair';
        fabricImageCanvas.forEachObject((o) => {
            o.selectable = false;
            o.evented = false;
        });
        $dom('#imageCanvasBox').click();
    }
};

const stopDrawRectangles = () => {
    if (imageCanvasRuntime.isDrawing) {
        // 允许选择
        drawingMode.value = false;
        imageCanvasRuntime.isDrawing = false;
        fabricImageCanvas.selection = true;
        fabricImageCanvas.defaultCursor = 'default';
        fabricImageCanvas.forEachObject((o) => {
            if (o.type != 'image' && o.type != 'textbox') {
                o.selectable = true;
                o.evented = true;
            }
        });
        $dom('#imageCanvasBox').click();
    }
};

// 按照id删除矩形框
const removeObjectsByLabelId = (labelId: string) => {
    // 删除绑定了labelId的Group
    const targets = fabricImageCanvas.getObjects().filter((o) => (o as any).labelId === labelId);
    targets.forEach((o) => {
        fabricImageCanvas.remove(o);
    });
    // 删除可能残留的未绑定labelId的矩形
    fabricImageCanvas.getObjects('rect').forEach((o) => {
        if (!(o as any).labelId) {
            fabricImageCanvas.remove(o);
        }
    });
    fabricImageCanvas.discardActiveObject();
    // 取消区块预览弹窗
    closeLabelRectDialog();
    fabricImageCanvas.calcOffset();
    fabricImageCanvas.requestRenderAll();

    let result = []; // 返回被删除的LabelInfo对象
    for (let i = 0; i < imageLabelData.length; i++) {
        if (imageLabelData[i].id === labelId) {
            imageLabelData[i].deleted = true;
            result.push(imageLabelData[i]);

            selectedLabelId.value = null;
            selectedImageLabelData.value = null;
        }
    }
    return result;
};

const removeActiveObjects = () => {
    let activeObjects = fabricImageCanvas.getActiveObjects();
    let delLabelIds: any[] = [];
    activeObjects.forEach((o: any) => {
        if (o.labelId) {
            if (delLabelIds.indexOf(o.labelId) === -1) {
                delLabelIds.push(o.labelId);
            }
        } else {
            fabricImageCanvas.remove(o);
        }
    });
    const delObjects = fabricImageCanvas.getObjects().filter((o) => delLabelIds.indexOf((o as any).labelId) >= 0);
    delObjects.forEach((o) => {
        fabricImageCanvas.remove(o);
    });
    fabricImageCanvas.discardActiveObject();
    // 取消区块预览弹窗
    closeLabelRectDialog();
    fabricImageCanvas.calcOffset();
    fabricImageCanvas.requestRenderAll();

    let result = []; // 返回被删除的LabelInfo对象
    for (let i = 0; i < imageLabelData.length; i++) {
        if (delLabelIds.indexOf(imageLabelData[i].id) >= 0) {
            imageLabelData[i].deleted = true;
            result.push(imageLabelData[i]);
        }
    }
    return result;
};

// 放大
const zoomIn = () => {
    const zoom = fabricImageCanvas.getZoom();
    let newZoom = Math.min(zoom * 1.1, 10); // 限制最大倍数
    fabricImageCanvas.zoomToPoint(new Point(fabricImageCanvas.getWidth() / 2, fabricImageCanvas.getHeight() / 2), newZoom);

    fabricImageCanvas.getObjects().forEach((o: any) => {
        if (o.type === 'textbox') {
            o.fontSize = textBoxFontSize;
            o.width = textBoxWidth(o.text);
        }
    });

    fabricImageCanvas.requestRenderAll();
    currentZoom.value = newZoom;
    // 重建标尺网格
    drawGridRulerCanvas();
};

// 缩小
const zoomOut = () => {
    const zoom = fabricImageCanvas.getZoom();
    let newZoom = Math.max(zoom * 0.9, 0.1); // 限制最小倍数
    fabricImageCanvas.zoomToPoint(new Point(fabricImageCanvas.getWidth() / 2, fabricImageCanvas.getHeight() / 2), newZoom);
    console.log(fabricImageCanvas.getObjects());
    fabricImageCanvas.getObjects().forEach((o: any) => {
        if (o.type === 'textbox') {
            o.fontSize = textBoxFontSize;
            o.width = textBoxWidth(o.text);
        }
    });
    fabricImageCanvas.requestRenderAll();
    currentZoom.value = newZoom;
    // 重建标尺网格
    drawGridRulerCanvas();
};

// 还原
const resetZoom = () => {
    fabricImageCanvas.setViewportTransform([1, 0, 0, 1, 0, 0]); // 重置缩放和平移
    fabricImageCanvas.setZoom(1); // 清空缩放比例
    fabricImageCanvas.requestRenderAll();
    currentZoom.value = 1;
    // 重建标尺网格
    drawGridRulerCanvas();
};

const resetImage = () => {
    resetZoom();
};

const isFullscreen = ref(false);
// 页面最大化最小化
const toggleFullscreen = () => {
    $dom('#fullscreen-btn').click();
};

//fabric-history
interface HistoryItem {
    action: number; // add = 1 -> LabelInfo or del = 2 -> LabelInfo or modify = 3 -> Group
    target: LabelInfo[];
    extra?: any;
}
const max_history = 200;
const historyUndo = ref<HistoryItem[]>([]);
const historyRedo = ref<HistoryItem[]>([]);

// 记录历史操作
const recordHistory = (action: string, target: LabelInfo[] | LabelInfo, extra?: any) => {
    if (!target) return;
    // 限制历史记录数量
    if (historyUndo.value.length >= max_history) {
        historyUndo.value.shift();
    }
    let historyItem = {
        action: action === 'add' ? 1 : action === 'del' ? 2 : 3,
        target: Array.isArray(target) ? target : [target],
        extra: extra
    };

    //合并相同的操作
    if (historyUndo.value.length > 0) {
        let lastItem = historyUndo.value[historyUndo.value.length - 1];
        if (lastItem.action === historyItem.action && JSON.stringify(lastItem.target) === JSON.stringify(historyItem.target) && JSON.stringify(lastItem.extra || {}) === JSON.stringify(historyItem.extra || {})) {
            return;
        }
    }
    historyUndo.value.push(historyItem);
};
// 撤销历史操作
const undoHistory = () => {
    if (historyUndo.value.length <= 0) return;
    let item = historyUndo.value.pop();
    if (!item) return;
    historyRedo.value.push(item);
    if (item.action === 1) {
        // 添加操作，撤销时则删除
        for (let i = 0; i < item.target.length; i++) {
            let labelInfo = item.target[i];
            removeObjectsByLabelId(labelInfo.id);
        }
    } else if (item.action === 2) {
        // 删除操作，撤销时则添加
        for (let i = 0; i < item.target.length; i++) {
            let labelInfo = item.target[i];
            buildLableRect(labelInfo);
            selectedImageLabelData.value = labelInfo;
        }
    } else if (item.action === 3) {
        // 修改操作，撤销修改
        for (let i = 0; i < item.target.length; i++) {
            let labelInfo = item.target[i];
            let extra = item.extra;
            modifyLabelRect(labelInfo, extra);
        }
    }
    fabricImageCanvas.requestRenderAll();
};
// 重做历史操作
const redoHistory = () => {
    if (historyRedo.value.length <= 0) return;
    let item = historyRedo.value.pop();
    if (!item) return;
    historyUndo.value.push(item);
    if (item.action === 1) {
        // 添加操作，重做时则添加
        for (let i = 0; i < item.target.length; i++) {
            let labelInfo = item.target[i];
            buildLableRect(labelInfo);
            selectedImageLabelData.value = labelInfo;
        }
    } else if (item.action === 2) {
        // 删除操作，重做时则删除
        for (let i = 0; i < item.target.length; i++) {
            let labelInfo = item.target[i];
            removeObjectsByLabelId(labelInfo.id);
        }
    } else if (item.action === 3) {
        // 修改操作，重做修改
        for (let i = 0; i < item.target.length; i++) {
            let labelInfo = item.target[i];
            let extra = item.extra;
            modifyLabelRect(labelInfo, extra);
        }
    }
    fabricImageCanvas.requestRenderAll();
};
// 重置历史记录
const resetHistory = () => {
    historyUndo.value = [];
    historyRedo.value = [];
};

// 图片旋转
const labelImageRotate = (angle: number) => {
    let fabricImage = fabricImageCanvas.getObjects().find((o: any) => o.type == 'image') as FabricImage;
    if (!fabricImage) return;

    let newAngle = 0;
    newAngle = fabricImage.angle + angle;
    if (newAngle >= 360 || newAngle <= -360) {
        newAngle = 0;
    }
    fabricImage.rotate(newAngle);
    fabricImageCanvas.requestRenderAll();
    // let labelImage = $dom('#label_image_' + currentLabelImage.value.id);
    // (labelImage as HTMLImageElement).style.transform = `rotate(${newAngle}deg)`;
};

const labelImageChange = async (type: string) => {
    if (!type) return;
    let fabricImage = fabricImageCanvas.getObjects().find((o: any) => o.type == 'image') as FabricImage;
    if (!fabricImage) return;
    fabricImage.filters = fabricImage.filters || [];
    // fabricImage.filters.push(new filters.BlackWhite());
    console.log(fabricImage.filters);
    switch (type.toLowerCase()) {
        default:
            return;
        case 'brightness':
            fabricImage.filters = fabricImage.filters.filter((f: any) => f.type !== 'Brightness');
            fabricImage.filters.push(new filters.Brightness({ brightness: (imageBrightness.value - 50) / 100 }));
            break;
        case 'contrast':
            fabricImage.filters = fabricImage.filters.filter((f: any) => f.type !== 'Contrast');
            fabricImage.filters.push(new filters.Contrast({ contrast: (imageContrast.value - 50) / 100 }));
            break;
        case 'saturation':
            fabricImage.filters = fabricImage.filters.filter((f: any) => f.type !== 'Saturation');
            fabricImage.filters.push(new filters.Saturation({ saturation: (imageSaturation.value - 50) / 10 }));
            break;
    }
    await fabricImage.applyFilters();
    fabricImageCanvas.requestRenderAll();
};

// 图片重置
const labelImageReset = () => {
    let fabricImage = fabricImageCanvas.getObjects().find((o: any) => o.type == 'image') as FabricImage;
    if (!fabricImage) return;

    fabricImage.rotate(0);
    fabricImage.filters = [];
    fabricImage.applyFilters();
    fabricImageCanvas.requestRenderAll();

    imageBrightness.value = 50;
    imageContrast.value = 50;
    imageSaturation.value = 50;
};

const onRowReorder = (e: any) => {
    console.log(e);
    let dragIndex = e.dragIndex;
    let dropIndex = e.dropIndex;

    let notDeletedImageLabelData = imageLabelData.filter((item) => !item.deleted);
    let dragLabelInfo = notDeletedImageLabelData[dragIndex];
    let dropLabelInfo = notDeletedImageLabelData[dropIndex];

    let index1 = imageLabelData.indexOf(dragLabelInfo);
    let index2 = imageLabelData.indexOf(dropLabelInfo);
    arraySwap(imageLabelData, index1, index2);
    reOrderAllLableNumber();
};

//重新排序所有区块的编号
const reOrderAllLableNumber = () => {
    let labelNumber = 0;
    for (let i = 0; i < imageLabelData.length; i++) {
        let labelInfo = imageLabelData[i];
        if (!labelInfo.deleted) {
            labelNumber++;
            let labelId = labelInfo.id;
            labelInfo.labelNumber = labelNumber;
            let group = fabricImageCanvas.getObjects().find((o: any) => o.type == 'group' && o.labelId === labelId);
            if (group) {
                console.log(group);
                let rect = (group as any).mainRect;
                let label = (rect as any).labelRef;
                label.set('text', `-${labelNumber}-`);
            }
        }
    }
    fabricImageCanvas.requestRenderAll();
};

// DataTable 行选择事件
const onRowSelect = (e: any) => {
    // let labelId = e.data.id;
    setFabricActiveObject(e.data);
    // 更新预览内容(如果区块预览弹窗打开)
    updateLabelRect2Html(e.data);
};

const setFabricActiveObject = (labelInfo: LabelInfo) => {
    fabricImageCanvas.forEachObject((o) => {
        if (o.type == 'group') {
            let rect = (o as any).mainRect;
            const rgbTempColor: any = stringToColour(labelInfo.labelNumber + '');
            if ((o as any).labelId == labelInfo.id) {
                rect.set({
                    fill: `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b},0.5)`
                });
                fabricImageCanvas.setActiveObject(o);
                fabricImageCanvas.bringObjectToFront(o); // 移动该对象到前层
                selectedLabelId.value = labelInfo.id;
                // 切换到 调整 模式
                stopDrawRectangles();
            } else {
                // 其他区块 取消高亮
                rect.set({
                    fill: ''
                });
            }
        }
    });
    fabricImageCanvas.requestRenderAll();
};

const onRowUnSelect = () => {
    fabricImageCanvas.forEachObject((o) => {
        if (o.type == 'group') {
            let rect = (o as any).mainRect;
            rect.set({
                fill: ''
            });
        }
    });
    // fabricImageCanvas.requestRenderAll();

    selectedLabelId.value = null;
    selectedImageLabelData.value = null;
    fabricImageCanvas.discardActiveObject();
    fabricImageCanvas.requestRenderAll();
    stopDrawRectangles();
    // 取消区块预览弹窗
    closeLabelRectDialog();
};

// 左侧点击矩形框 使得右侧表格行自动选中高亮
const selectRow = async (lableId: string) => {
    let row = imageLabelData.find((item) => item.id === lableId);
    if (!row) {
        return;
    }
    setFabricActiveObject(row);
    selectedLabelId.value = lableId;
    selectedImageLabelData.value = row;
    // setTimeout(async () => {
    //     selectedImageLabelData.value.editorValue = await markdown2Html(selectedImageLabelData.value.ocrText);
    // }, 0);
    // 滚动到选中行
    scrollToRowOrOcHtml(lableId);
    // 更新预览内容(如果区块预览弹窗打开)
    updateLabelRect2Html(row);
};

const scrollToRowOrOcHtml = (lableId: string) => {
    const rowElement = document.getElementById(`dt_label_${lableId}`); // 分区列表-row
    const divElement = document.getElementById(`ocr-html-${lableId}`); // 整体预览-div
    if (rowElement) {
        rowElement.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
    if (divElement) {
        divElement.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
};

const unSelectRow = () => {
    if (selectedImageLabelData.value) {
        let labelId = selectedLabelId.value;
        let group = fabricImageCanvas.getObjects().find((o) => o.type == 'group' && (o as any).labelId == labelId);
        if (group) {
            let rect = (group as any).mainRect;
            rect.set({
                fill: ''
            });
            fabricImageCanvas.requestRenderAll();
        }
    }

    selectedLabelId.value = null;
    selectedImageLabelData.value = null;
    fabricImageCanvas.discardActiveObject();

    // 取消区块预览弹窗
    closeLabelRectDialog();
};

const onRowMouseMove = (e: any) => {
    let target = e.target || e.srcElement;
    let tr = target.closest('tr');
    let tbody = target.closest('tbody');
    if (tbody) {
        let trs = [...tbody.children]; // querySelectorAll('tr') 替换为 children
        let index = trs.indexOf(tr);
        if (index >= 0) {
            let labelInfo = imageLabelData.filter((item: any) => !item.deleted)[index];
            onOcrHtmlMouseMove(labelInfo); // 与 onOcrHtmlMouseMove(labelInfo);逻辑一样 group高亮效果
        }
    }
};

const onRowMouseOut = (e: any) => {
    let target = e.target || e.srcElement;
    let tr = target.closest('tr');
    let tbody = target.closest('tbody');
    if (tbody) {
        let trs = [...tbody.children]; // querySelectorAll('tr') 替换为 children
        let index = trs.indexOf(tr);
        if (index >= 0) {
            let labelInfo = imageLabelData.filter((item: any) => !item.deleted)[index];
            onOcrHtmlMouseOut(labelInfo); // 与 onOcrHtmlMouseOut(labelInfo);逻辑一样 取消group高亮效果
        }
    }
};

const onOcrHtmlClick = (labelInfo: LabelInfo) => {
    if (!labelInfo) {
        return;
    }
    let labelId = labelInfo.id;
    if (selectedLabelId.value == labelId) {
        fabricImageCanvas.forEachObject((o) => {
            if (o.type == 'group') {
                let rect = (o as any).mainRect;
                rect.set({
                    fill: ''
                });
            }
        });
        // fabricImageCanvas.requestRenderAll();

        selectedLabelId.value = null;
        selectedImageLabelData.value = null;
        fabricImageCanvas.discardActiveObject();
        fabricImageCanvas.requestRenderAll();
        stopDrawRectangles();
        // 取消区块预览弹窗
        closeLabelRectDialog();
    } else {
        selectedLabelId.value = labelId;
        selectedImageLabelData.value = labelInfo;
        setFabricActiveObject(labelInfo);
        // 更新预览内容(如果区块预览弹窗打开)
        updateLabelRect2Html(labelInfo);
    }
};

const onOcrHtmlMouseMove = (labelInfo: LabelInfo) => {
    if (!labelInfo) {
        return;
    }
    let labelId = labelInfo.id;
    let group = fabricImageCanvas.getObjects().find((o) => o.type == 'group' && (o as any).labelId == labelId);
    const rgbTempColor: any = stringToColour(labelInfo.labelNumber + '');
    if (group) {
        let rect = (group as any).mainRect;
        rect.set({
            fill: `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b},0.5)`
        });
    }
    fabricImageCanvas.requestRenderAll();
};

const onOcrHtmlMouseOut = (labelInfo: LabelInfo) => {
    if (!labelInfo) {
        return;
    }
    if (selectedLabelId.value == labelInfo.id) {
        return;
    }
    let labelId = labelInfo.id;
    let group = fabricImageCanvas.getObjects().find((o) => o.type == 'group' && (o as any).labelId == labelId);
    if (group) {
        let rect = (group as any).mainRect;
        rect.set({
            fill: ''
        });
    }
    fabricImageCanvas.requestRenderAll();
};

// 编辑标签数据
const editLabelData = (labelInfo: any) => {
    if (labelInfo && labelInfo.id) {
        let labelId = labelInfo.id;
        setFabricActiveObject(labelInfo);
        selectedLabelId.value = labelId;
        selectedImageLabelData.value = labelInfo;
        // rightPanelMode.value = 2;//切到labeInfo数据编辑模式
        switchRightPanelMode(2);
        // 更新预览内容(如果区块预览弹窗打开)
        updateLabelRect2Html(labelInfo);
    }
};

const dblEditLabelData = (e: any) => {
    editLabelData(e.data);
};

const deleteLabel = (label: any) => {
    console.log(label);
    removeObjectsByLabelId(label.id);
    // 记录删除历史操作 第三处 从区块表格列表中点删除的
    recordHistory('del', label);
};

// 编辑标签数据
// 转到上一个标签数据
const prevImageLabel = () => {
    let labelId = selectedLabelId.value;
    if (!labelId) {
        return;
    }
    let notDeletedImageLabelData = imageLabelData.filter((item) => !item.deleted);
    let index = notDeletedImageLabelData.findIndex((item) => item.id === labelId);
    if (index <= 0) {
        // 已经是第一个了，转到最后一个
        index = notDeletedImageLabelData.length - 1;
    }
    let labelInfo = notDeletedImageLabelData[index - 1];
    editLabelData(labelInfo);
};
// 转到下一个标签数据
const nextImageLabel = () => {
    let labelId = selectedLabelId.value;
    if (!labelId) {
        return;
    }
    let notDeletedImageLabelData = imageLabelData.filter((item) => !item.deleted);
    let index = notDeletedImageLabelData.findIndex((item) => item.id === labelId);
    if (index >= notDeletedImageLabelData.length - 1) {
        // 已经是最后一个了，转到第一个
        index = -1;
    }
    let labelInfo = notDeletedImageLabelData[index + 1];
    editLabelData(labelInfo);
};

// 重新编号
const changeLabelNumber = (dirc: number) => {
    let oldNumber = selectedImageLabelData.value.labelNumber;
    let newNumber = oldNumber;
    while (true) {
        newNumber = newNumber + dirc;
        if (newNumber <= 0) return;
        let filter = imageLabelData.filter((item) => !item.deleted);
        let find = filter.find((item) => item.labelNumber === newNumber);
        if (find) continue;
        break;
    }
    selectedImageLabelData.value.labelNumber = newNumber;
    fabricImageCanvas.forEachObject((o) => {
        if (o.type == 'group' && (o as any).labelId == selectedLabelId.value) {
            let rect = (o as any).mainRect;
            let label = (rect as any).labelRef;
            (label as any).set({
                text: `-${newNumber}-`
            });
            fabricImageCanvas.requestRenderAll();
        }
    });
};

// 切换标签类别
const changeLabelCategory = (dirc: number) => {
    let oldCategory = selectedImageLabelData.value.category;
    let oldIndex = -1;
    labelCategories.value.forEach((item: any, index: number) => {
        if (item.value == oldCategory.value) {
            oldIndex = index;
        }
    });
    let newIndex = oldIndex + dirc;
    if (newIndex < 0 || newIndex > labelCategories.value.length - 1) return;
    let newCategory = labelCategories.value[newIndex];
    if (!newCategory) return;
    selectedImageLabelData.value.category = newCategory;
};

let longPressFlag = false;
const startLongPress = (index: number, dirc: number) => {
    longPressFlag = true;
    updateLabelPosition(index, dirc);
    setTimeout(() => {
        if (longPressFlag) {
            startLongPress(index, dirc);
        }
    }, 100);
};
const endLongPress = () => {
    longPressFlag = false;
};

const updateLabelPosition = (index: number, dirc: number) => {
    let step = dirc * 1.0;
    switch (index) {
        case 0:
            selectedImageLabelData.value.pos1[0] += 2 * step;
            break;
        case 1:
            selectedImageLabelData.value.pos1[1] += 2 * step;
            break;
        case 2:
            selectedImageLabelData.value.pos2[0] += 2 * step;
            break;
        case 3:
            selectedImageLabelData.value.pos2[1] += 2 * step;
            break;
    }

    const activeObject = fabricImageCanvas.getActiveObject();
    if (!activeObject || activeObject.type !== 'group') {
        return;
    }

    const rect = (activeObject as any).mainRect;
    switch (index) {
        case 0:
            activeObject.set({
                width: activeObject.width - (2 * step) / activeObject.scaleX,
                left: activeObject.left + step
            });
            rect.set({
                width: rect.width - (2 * step) / activeObject.scaleX,
                left: (-1 * activeObject.width) / 2
            });
            break;
        case 1:
            activeObject.set({
                height: activeObject.height - (2 * step) / activeObject.scaleY,
                top: activeObject.top + step
            });
            rect.set({
                height: rect.height - (2 * step) / activeObject.scaleY,
                top: (-1 * activeObject.height) / 2
            });
            break;
        case 2:
            activeObject.set({
                width: activeObject.width + (2 * step) / activeObject.scaleX,
                left: activeObject.left + step
            });
            rect.set({
                width: rect.width + (2 * step) / activeObject.scaleX,
                left: (-1 * activeObject.width) / 2
            });
            break;
        case 3:
            activeObject.set({
                height: activeObject.height + (2 * step) / activeObject.scaleY,
                top: activeObject.top + step
            });
            rect.set({
                height: rect.height + (2 * step) / activeObject.scaleY,
                top: (-1 * activeObject.height) / 2
            });
            break;
    }
    activeObject.setCoords();
    const label = (rect as any).labelRef;

    const boundingBox = activeObject.getBoundingRect(); // 获取绝对左上角
    label.set({
        left: boundingBox.left + 5,
        top: boundingBox.top + 5
    });
    activeObject.setCoords();
    fabricImageCanvas.requestRenderAll();

    // 更新标签区块预览
    updateLabelRect2Html(selectedImageLabelData.value);
};

const onImageCanvasBoxResize = () => {
    const imageCanvasBoxElement = $dom('#imageCanvasBox');
    const crosshairCanvas: any = $dom('#cross-canvas');
    const fabricCanvasContainer = fabricImageCanvas.getElement().parentElement as HTMLElement;
    const fabricImage: any = fabricImageCanvas.getObjects().find((o) => o.type == 'image');

    if (!fabricCanvasContainer) return;
    if (!crosshairCanvas) return;
    if (!fabricImage) return;

    //这里重置宽高信息要与初始化时一致
    fabricCanvasContainer.style.width = imageCanvasBoxElement.clientWidth + 'px';
    fabricCanvasContainer.style.height = imageCanvasBoxElement.clientHeight + 'px';
    fabricImageCanvas.setWidth(imageCanvasBoxElement.clientWidth);
    fabricImageCanvas.setHeight(imageCanvasBoxElement.clientHeight);

    crosshairCanvas.style.width = '100%';
    crosshairCanvas.style.height = '100%';
    crosshairCanvas.width = imageCanvasBoxElement.clientWidth;
    crosshairCanvas.height = imageCanvasBoxElement.clientHeight;

    drawGridRulerCanvas();

    // let heightScale = fabricCanvasContainer.clientHeight / fabricImage.height!;
    // let widthScale = fabricCanvasContainer.clientWidth / fabricImage.width!;
    // let scale = Math.min(heightScale, widthScale);
    // if (scale > 1) {
    //     scale = 1;
    // }

    // fabricImage.scale(scale);
    // fabricImage.set({
    //     originX: "center",
    //     originY: "center",
    //     left: fabricCanvasContainer.clientWidth / 2,
    //     top: fabricCanvasContainer.clientHeight / 2,
    //     selectable: false,
    //     evented: false,
    // });
    // fabricImageCanvas.requestRenderAll();

    changeQuillEditorHeight();
};

let resizeOnceTimer: any = null;
// 监听容器大小变化
let observer1: ResizeObserver | null = null;
const bindImageCanvasBoxResize = () => {
    observer1 = new ResizeObserver((entries, resizeOb) => {
        for (const entry of entries) {
            /* Firefox 实现的 contentBoxSize 是一个单项值, 并非数组 **/
            // const contentBoxSize = Array.isArray(entry.contentBoxSize)
            //     ? entry.contentBoxSize[0]
            //     : entry.contentBoxSize;
            // 判断是否是处于全屏状态
            if (resizeOnceTimer) clearTimeout(resizeOnceTimer);
            resizeOnceTimer = setTimeout(() => {
                console.log(`onImageCanvasBoxResize执行一次${Date.now()}`);
                isFullscreen.value = document.fullscreenElement ? true : false;
                onImageCanvasBoxResize();
            }, 50);
            entry;
            resizeOb;
        }
    });
    observer1.observe($dom('#imageCanvasBox'));
};
const unBindImageCanvasBoxResize = () => {
    if (observer1) {
        observer1.unobserve($dom('#imageCanvasBox'));
        observer1.disconnect();
    }
};

//====================================编辑器相关====================================
const editorHeight = ref(200);
const sourceToggle = ref(false);
// tikz 图形初始化
const colorSVGinDarkMode = (svg: string) => {
    //判断是否是暗黑模式，不同项目需要修改暗黑样式名称app-dark--p-surface-950
    // svg = svg.replaceAll(/("#000"|"black")/g, `"currentColor"`).replaceAll(/("#fff"|"white")/g, `"var(--primary-color)"`);
    svg = svg.replaceAll(/("#000"|"black")/g, `"currentColor"`).replaceAll(/("#fff"|"white")/g, `"var(--p-surface-950)"`);
    return svg;
};
const postProcessSvg = (e: Event) => {
    const containerElement = e.target as HTMLElement;
    let svg = containerElement.outerHTML;
    //判断是否是暗黑模式，不同项目需要修改暗黑样式名称app-dark
    let isDrakMode = document.documentElement.classList.contains('app-dark');
    if (isDrakMode) {
        svg = colorSVGinDarkMode(svg);
    }
    containerElement.outerHTML = svg;
};
const loadTikZJax = () => {
    if ($dom('#' + tikzJaxJsId)) {
        return;
    }
    const script = document.createElement('script');
    script.type = 'text/javascript';
    script.id = tikzJaxJsId;
    script.src = tikzJaxJsUrl;
    document.body.appendChild(script);
    document.addEventListener('tikzjax-load-finished', postProcessSvg);
};

const unloadTikZJax = () => {
    const script = $dom('#' + tikzJaxJsId);
    if (script) {
        script.remove();
        document.removeEventListener('tikzjax-load-finished', postProcessSvg);
    }
};
const tikz2svg = (latex: string): Promise<string> => {
    return new Promise((resolve, reject) => {
        if (!latex || latex.length == 0) {
            reject('tikz latex is empty');
        }
        let containerId = `tikz-container`; //`tikz-temp-container-${Date.now()}`;
        // let sdiv = document.createElement('div');
        // sdiv.id = containerId;
        // document.body.appendChild(sdiv);

        let tikzDocument = '';
        // tikzDocument += `\\usepackage{tikz}\\n`;
        tikzDocument += `\\begin{document}${latex}\\end{document}`;
        if (!$dom('#' + containerId)) {
            let div = document.createElement('div');
            div.id = containerId;
            div.style = 'position: absolute; top: -1000px; left: 0';
            document.body.appendChild(div);
        }
        console.log('$dom', $dom('#' + containerId));
        $dom('#' + containerId).innerHTML = `<script type='text/tikz'>${tikzDocument}<\/script>`; // data-show-console='true'

        let counter = 0;
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                counter += 1;
                if (counter > 1) {
                    observer.disconnect();
                    // 监听到div内容变化的处理逻辑
                    // console.log('div内容变化了！', $dom('#' + containerId).innerHTML);
                    console.log('tikz view div内容变化了！mutation=', mutation);
                    let svg = $dom('#' + containerId).innerHTML;
                    resolve(svg);
                }
            });
        });
        // 配置对象
        const observerConfig = {
            childList: true, // 监听子节点的变化
            subtree: false, // 监听所有后代节点的变化
            characterData: false // 监听文本节点内容的变化
        };
        // 开始监听
        observer.observe($dom('#' + containerId), observerConfig);
    });
};

// 生成uuid
const uuid = () => {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        const r = (Math.random() * 16) | 0,
            v = c === 'x' ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
};
const replaceN = (str: string) => {
    return str.trim().replace(/\n/g, '\v\t');
};
// const unReplaceN = (str: string) => {
//     return str.trim().replace(/\v\t/g, '\n');
// };


// 这里markdown2Html主要是为了编辑器内web显示
const markdown2Html = async (markdown: string) => {
    let text = markdown;
    // console.log('markdown', text);

    if (!text || text.length == 0) {
        return '';
    }

    let reg;
    let res;

    // 化学分子式 latex
    reg = /```smiles([\s\S]*?)```/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<smiles>${replaceN(content)}</smiles>`);
    }

    // 代码块 markdown
    reg = /```([\s\S]*?)```/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<div class="ql-code-block-container" spellcheck="false"><div class="ql-code-block">${replaceN(content)}</div></div>`);
    }

    // hr分割线
    text = text.replace(/---/gi, '<hr/>'); //markdown
    text = text.replace(/\\hrulefill/gi, '<hr/>'); //latex

    // 普通文本 latex
    reg = /\\text\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `${replaceN(content)}`);
    }

    // 斜体 latex
    reg = /\\textit\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<i>${replaceN(content)}</i>`);
    }

    // 粗体 latex
    reg = /\\textbf\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<b>${replaceN(content)}</b>`);
    }

    // 标题 latex
    reg = /\\title\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<h1>${replaceN(content)}</h1>`);
    }
    reg = /\\section\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<h2>${replaceN(content)}</h2>`);
    }
    reg = /\\subsection\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<h3>${replaceN(content)}</h3>`);
    }
    reg = /\\subsubsection\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<h4>${replaceN(content)}</h4>`);
    }

    // 下划线 latex
    reg = /\\uline\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<u class="ql-normal-underline">${replaceN(content)}</u>`);
    }
    reg = /\\uuline\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<u class="ql-double-underline">${replaceN(content)}</u>`);
    }
    reg = /\\dashuline\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<u class="ql-dashed-underline">${replaceN(content)}</u>`);
    }
    reg = /\\dotuline\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<u class="ql-dot-underline">${replaceN(content)}</u>`);
    }
    reg = /\\xout\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<u class="ql-hatching-underline">${replaceN(content)}</u>`);
    }
    reg = /\\uwave\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<u class="ql-wavy-underline">${replaceN(content)}</u>`);
    }
    // 删除线 latex
    reg = /\\sout\{([^}]*)\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<s>${replaceN(content)}</s>`);
    }

    // 无序列表 latex
    reg = /\\begin\{itemize\}([\s\S]*?)\\end\{itemize\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let arr = res[1].split('\\item');
        let list = '<ol>';
        for (let i = 0; i < arr.length; i++) {
            if (arr[i].trim().length > 0) {
                list += `<li>${replaceN(arr[i])}</li>`;
            }
        }
        list += '</ol>';
        text = text.replace(find, list);
    }

    // 有序列表 latex
    reg = /\\begin\{enumerate\}([\s\S]*?)\\end\{enumerate\}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let arr = res[1].split('\\item');
        let list = '<ul>';
        for (let i = 0; i < arr.length; i++) {
            if (arr[i].trim().length > 0) {
                list += `<li>${replaceN(arr[i])}</li>`;
            }
        }
        list += '</ul>';
        text = text.replace(find, list);
    }

    // 插图插画的处理
    reg = /\\begin{figure}\\includegraphics\[position=([\d,]*?)\]{}\\end{figure}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let position = res[1];
        let caption = ``;
        let figure = `<div id="illus-${uuid()}" data-src="${currentLabelImage.value.file_path}" data-position="${position}" class="ql-illustrate"><label></label><div></div><span>${caption}</span></div>`;
        text = text.replace(find, figure);
    }

    // 几何图形 tikz/latex 转成Quill编辑器自定义<tikz-jax>元素
    reg = /\\usetikzlibrary([\s\S]*?)\\end{tikzpicture}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        const [err, svg] = await promise2(tikz2svg(find));
        if (err) {
            console.log(err);
            continue;
        }
        let caption = ``;
        //encodeURIComponent避免中间过程因特殊字符造成的问题（后面再解码）
        let tikz = `<tikz-jax class="ql-tikzjax" id="tikzjax-${uuid()}" data-latex="${encodeURIComponent(find)}" data-svg="${encodeURIComponent(svg)}" data-caption="${encodeURIComponent(caption)}"></tikz-jax>`;
        text = text.replace(find, tikz);
    }
    reg = /\\begin{tikzpicture}([\s\S]*?)\\end{tikzpicture}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        const [err, svg] = await promise2(tikz2svg(find));
        if (err) {
            console.log(err);
            continue;
        }
        let caption = ``;
        //encodeURIComponent避免中间过程因特殊字符造成的问题（后面再解码）
        let tikz = `<tikz-jax class="ql-tikzjax" id="tikzjax-${uuid()}" data-latex="${encodeURIComponent(find)}"  data-svg="${encodeURIComponent(svg)}" data-caption="${encodeURIComponent(caption)}"></tikz-jax>`;
        text = text.replace(find, tikz);
    }

    // 公式 latex
    // text = text.replace(/\\begin\{[equation|align|aligned|split|gather]+[\*]{0,1}\}([\s\S]*?)\\end\{[equation|align|aligned|split|gather]+[\*]{0,1}\}/gi, '\\[$1\\]');
    text = text.replace(/\$\$([\s\S]*?)\$\$/gi, '\\[$1\\]');
    text = text.replace(/\$([\s\S]*?)\$/gi, '\\($1\\)');
    reg = /\\\[([\s\S]*?)\\\]/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let latexContent = res[1].replace(/\\tag\{[\s\S]*?\}/gi, '').replace(/\\label\{[\s\S]*?\}/gi, ''); // 删除latex公式中可能的tag和label标签
        let mathField = `<math-field mode="only-read" id="mathfield-${uuid()}" class="ql-math-field view">${replaceN(latexContent)}</math-field>`;
        text = text.replace(find, mathField);
    }
    reg = /\\\(([\s\S]*?)\\\)/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let latexContent = res[1].replace(/\\tag\{[\s\S]*?\}/gi, '').replace(/\\label\{[\s\S]*?\}/gi, ''); // 删除latex公式中可能的tag和label标签
        let mathField = `<math-field mode="only-read" id="mathfield-${uuid()}" class="ql-math-field view">${replaceN(latexContent)}</math-field>`;
        text = text.replace(find, mathField);
    }
    
    // TODO latex table 转 html table

    // 普通html表格添加table-better属性
    reg = /<table([^>]*?)>([\s\S]*?)<\/table>/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let table_attr = res[1];
        let table_content = res[2];
        if (table_attr.indexOf('table-better') == -1) {
            let temporary = `<temporary class="ql-table-temporary" style="width: 100%" data-class="ql-table-better"></temporary>`;
            text = text.replace(find, `<table width="100%" class="table-better">${temporary}${table_content}</table>`);
        }
    }

    // 文本格式 markdown
    reg = /~~([\s\S]*)~~/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<s>${replaceN(content)}</s>`);
    }
    reg = /==([\s\S]*)==/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<b><i>${replaceN(content)}</i></b>`);
    }
    reg = /\*\*([\s\S]*)\*\*/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<b>${replaceN(content)}</b>`);
    }
    reg = /__([\s\S]*)__/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<b>${replaceN(content)}</b>`);
    }
    reg = /\*([\s\S]*)\*/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let content = res[1];
        text = text.replace(find, `<i>${replaceN(content)}</i>`);
    }

    // reg = /_([\s\S]*)_/gi;
    // while ((res = reg.exec(text))) {
    //     let find = res[0];
    //     let content = res[1];
    //     text = text.replace(find, `<i>${replaceN(content)}</i>`);
    // }

    // let paragraphs = text.split('\n'); // 对余下的\n分割成段落
    // for (let i = 0; i < paragraphs.length; i++) {
    //     paragraphs[i] = `<p>${unReplaceN(paragraphs[i])}</p>`; // 去除段落前后的空格
    // }
    // text = paragraphs.join('');

    // let html = text.replace(/<p([^>]*?)>([\s\S]*?)<\/p>/gi, '<div$1>$2</div>');
    // return html;
    let html = text;
    return html;
};

// 编辑器输出的html转换为markdown
const html2Markdown = (html: string) => {

    // 代码块
    html = html.replace(/<pre data-language="plain">([\s\S]*?)<\/pre>/gi, '```$1```');
    // hr分割线
    html = html.replace(/<hr([^>]*?)>/gi, '\\hrulefill');

    // 文本
    html = html.replace(/<i([^>]*?)>([\s\S]*?)<\/i>/gi, '\\textit{$2}'); //斜体
    html = html.replace(/<b([^>]*?)>([\s\S]*?)<\/b>/gi, '\\textbf{$2}'); //粗体
    html = html.replace(/<em([^>]*?)>([\s\S]*?)<\/em>/gi, '\\textit{$2}'); //斜体
    html = html.replace(/<strong([^>]*?)>([\s\S]*?)<\/strong>/gi, '\\textbf{$2}'); //粗体
    html = html.replace(/<s([^>]*?)>([\s\S]*?)<\/s>/gi, '\\sout{$2}'); //中间删除线
    html = html.replace(/<strike([^>]*?)>([\s\S]*?)<\/strike>/gi, '\\sout{$2}'); //中间删除线
    html = html.replace(/<del([^>]*?)>([\s\S]*?)<\/del>/gi, '\\sout{$2}'); //中间删除线

    // 标题
    html = html.replace(/<h1([^>]*?)>([\s\S]*?)<\/h1>/gi, '\\title{$2}');
    html = html.replace(/<h2([^>]*?)>([\s\S]*?)<\/h2>/gi, '\\section{$2}');
    html = html.replace(/<h3([^>]*?)>([\s\S]*?)<\/h3>/gi, '\\subsection{$2}');
    html = html.replace(/<h4([^>]*?)>([\s\S]*?)<\/h3>/gi, '\\subsubsection{$2}');

    let reg;
    let res;

    // 无序列表
    reg = /<ol([^>]*?)>([\s\S]*?)<\/ol>/gi;
    while ((res = reg.exec(html))) {
        let ol = res[0];
        let arr = res[2].split('</li>');
        let latex = `\\begin{itemize}`;
        for (let i = 0; i < arr.length; i++) {
            arr[i] = arr[i].replace(/<li>/gi, '');
            if (arr[i].trim().length > 0) {
                latex += ` \\item ${arr[i].trim()}`;
            }
        }
        latex += ` \\end{itemize}`;
        html = html.replace(ol, latex);
    }
    // 有序列表
    reg = /<ul([^>]*?)>([\s\S]*?)<\/ul>/gi;
    while ((res = reg.exec(html))) {
        let ul = res[0];
        let arr = res[2].split('</li>');
        let latex = `\\begin{enumerate}`;
        for (let i = 0; i < arr.length; i++) {
            arr[i] = arr[i].replace(/<li>/gi, '');
            if (arr[i].trim().length > 0) {
                latex += ` \\item ${arr[i].trim()}`;
            }
        }
        latex += ` \\end{enumerate}`;
        html = html.replace(ul, latex);
    }

    // 引用
    html = html.replace(/<blockquote([^>]*?)>([\s\S]*?)<\/blockquote>/gi, '> $2\\n');

    // 下划线
    html = html.replace(/<u class="ql-normal-underline"([\s\S]*?)>([\s\S]*?)<\/u>/gi, '\\uline{$2}');
    html = html.replace(/<u class="ql-double-underline"([\s\S]*?)>([\s\S]*?)<\/u>/gi, '\\uuline{$2}');
    html = html.replace(/<u class="ql-dashed-underline"([\s\S]*?)>([\s\S]*?)<\/u>/gi, '\\dashuline{$2}');
    html = html.replace(/<u class="ql-dot-underline"([\s\S]*?)>([\s\S]*?)<\/u>/gi, '\\dotuline{$2}');
    html = html.replace(/<u class="ql-hatching-underline"([\s\S]*?)>([\s\S]*?)<\/u>/gi, '\\xout{$2}');
    html = html.replace(/<u class="ql-wavy-underline"([\s\S]*?)>([\s\S]*?)<\/u>/gi, '\\uwave{$2}');
    // html = html.replace(/<s([\s\S]*?)>([\s\S]*?)<\/s>/gi, '\\sout{$2}');

    // 上下标
    // html = html.replace(/<sup>([\s\S]*?)<\/sup>/gi, '\\textsuperscript{$1}');
    // html = html.replace(/<sub>([\s\S]*?)<\/sub>/gi, '\\textsubscript{$1}');

    // 插图插画

    // 公式
    reg = /<math-field([\s\S]*?)>([\s\S]*?)<\/math-field>/gi;
    while ((res = reg.exec(html))) {
        let find = res[0];
        let latex = res[2];
        if (latex.indexOf('\\') == -1 && latex.indexOf('\n') == -1 && latex.indexOf('\r') == -1) {
            latex = '$ ' + latex + ' $'; // 行内公式
        } else {
            latex = '$$ ' + latex + ' $$'; // 行间公式
        }
        html = html.replace(find, latex);
    }

    // tikz 图形只留latex 参见TikZJaxBlot.ts
    reg = /<tikz-jax class="ql-tikzjax" id="([\s\S]*?)" data-latex="([\s\S]*?)" data-svg="([\s\S]*?)" data-caption="([\s\S]*?)"><\/tikz-jax>/gi;
    while ((res = reg.exec(html))) {
        let find = res[0];
        let latex = decodeURIComponent(res[2]);
        console.log('latex', latex);
        html = html.replace(find, latex);
    }

    // html = html.replace('<p', '\n<p');
    // html = html.replace(/<p([^>]*?)>([\s\S]*?)<\/p>/gi, '$2 \n');
    // html = html.replace(/<div([^>]*?)>([\s\S]*?)<\/div>/gi, '$2 \n');

    // // 多个连续的\n合并为一个
    // html = html.replace(/[\\n|\s]{2,}/g, '\n');

    //移除开头或者结尾多余空行的<p></p>
    html = html.replace(/^(<p><\/p>)+/gi, '');
    html = html.replace(/(<p><\/p>)+$/gi, '');

    return html;
};

const editorValue2Preview = (editorValue: string) => {
    let reg: RegExp;
    let res: RegExpExecArray | null;
    let html = editorValue;

    // 处理tikz-jax图形非编辑器模式下预览：直接显示svg
    reg = /<tikz-jax([\s\S]*?)data-svg="([\s\S]*?)" data-caption="([\s\S]*?)"><\/tikz-jax>/gi;
    while ((res = reg.exec(html))) {
        let find = res[0];
        let svgContent = decodeURIComponent(res[2]);
        let caption = decodeURIComponent(res[3]);
        svgContent = `<span style="display: inline-block;">${svgContent}${caption}</span>`
        html = html.replace(find, svgContent);
    }

    return html;
}

// 编辑器源码编辑切换
const editorSourceToggle = (isSource: boolean) => {
    sourceToggle.value = isSource;
    if (isSource) {
        editorValueSourceText.value = selectedImageLabelData.value.editorValue;
    } else {
        // 切换为非源码编辑模式时，需要对标注结果进行格式化
        selectedImageLabelData.value.editorValue = editorValueSourceText.value;
    }
}



const changeQuillEditorHeight = () => {
    let cropHeight = 400;
    let windowHeight = window.innerHeight;
    if (windowHeight > cropHeight) {
        editorHeight.value = windowHeight - cropHeight;
    }
};

// 格式化标注结果
const format_label_text = (lableInfo: LabelInfo) => {
    let text = html2Markdown(lableInfo.editorValue);
    lableInfo.ocrText = text;
    console.log('ocrText', text);
    // 统一按 dotsOCR 格式保存 {"bbox": [x1, y1, x2, y2], "category": "category", "text": "text"}
    let result = { bbox: [lableInfo.pos1[0], lableInfo.pos1[1], lableInfo.pos2[0], lableInfo.pos2[1]], category: lableInfo.category.code, text: text };
    return result;
};

// 保存标注结果到服务器

const saveLabelData = async () => {
    throttle(_saveLabelData(), 500);
};

const _saveLabelData = async () => {
    let ocr_labels = [];
    for (let i = 0; i < imageLabelData.length; i++) {
        let labelInfo = imageLabelData[i];
        ocr_labels.push(format_label_text(labelInfo));
    }
    if (ocr_labels.length == 0) {
        showToast('error', t('page.common.error'), t('page.label.save_error1'), true);
        return;
    }
    let ocr_label = JSON.stringify(ocr_labels);
    let image_id = currentLabelImage.value.id;
    let data_type = dataType.value.value;

    if (data_type == 0) {
        showToast('error', t('page.common.error'), t('page.label.save_error2'), true);
        return;
    }

    let data = {
        image_id: image_id,
        data_type: data_type,
        ocr_label: ocr_label
    };
    showLoading();
    let [err, res] = await promise2(DatasetService.saveLabelData(data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        showToast('success', t('page.common.success'), res.data.message, true);
        // 刷新当前图片的标注数据
        let index = labelImageList.value.findIndex((item: any) => item.id == image_id);
        if (index != -1) {
            labelImageList.value[index].train_data_type = data_type;
        }
    }
};

onMounted(async () => {
    document.body.style.overflow = 'hidden';
    virtualSetActiveMenu(parentRoute);
    setSplitterGutterBackgroundColor();
    bindSplitterGutterMouseOver();
    bindImageCanvasBoxResize(); // 先于initFabricCanvas()绑定好Canvas大小变化观察者，可避免画布第一次初始化时会触发多余的一次执行
    initFabricCanvas(); // 初始化fabric画布
    await getLabelImageIdList(); // 获取全部图片的id列表
    await loadImageInfo(0); // 加载默认图片的信息
    loadImageToCanvas(currentLabelImage.value.base_64, initLabelInfo2Rect);
    bindImageCanvasEvent();
    // startDrawRectangles();
    changeQuillEditorHeight();
    loadTikZJax();
    // setTimeout(() => {
    //     initLabelInfo2Rect();
    // }, 200);
});

onBeforeUnmount(() => {
    unbindSplitterGutterMouseOver();
    unbindImageCanvasEvent();
    unBindImageCanvasBoxResize();
    unloadTikZJax();
    if (fabricImageCanvas) {
        fabricImageCanvas.dispose();
    }
    // 重置历史记录 = 清空历史记录
    resetHistory();
});
</script>
<template>
    <div id="page_container" style="position: absolute; left: 0; top: 0; z-index: 1000"
        class="w-full h-full bg-surface-100 dark:bg-surface-900 overflow-hidden">
        <div class="flex flex-col md:flex-row gap-8 h-full">
            <div class="w-[18rem] min-w-[18rem] h-full">
                <div class="w-full flex items-center m-4 ml-8">
                    <div class="flex gap-2"><Button icon="pi pi-reply" :size="'small'" rounded class="mr-2"
                            @click="routeBack()" style="transform: rotateY(180deg)" /></div>
                    <div class="font-semibold text-xl"><i class="pi pi-longPressFlag-fill" /> {{ t('page.label.title')
                    }}</div>
                </div>
                <div class="w-full ml-8 bg-white dark:bg-surface-800 rounded-md" style="height: calc(100vh - 70px)">
                    <div class="w-full h-full select-none">
                        <!-- 图片列表 showLoader :loading="lazyLoading" -->
                        <VirtualScroller v-if="currentLabelImage" ref="virtualScrollerRef" :items="labelImageList"
                            :itemSize="100" lazy @lazy-load="onLazyLoad"
                            class="w-full h-full border border-surface-200 dark:border-surface-700 rounded-md"
                            style="scroll-behavior: smooth; overflow-x: hidden; height: 100%">
                            <template v-slot:item="{ item, options }">
                                <div :class="{
                                    'bg-primary-300 dark:bg-primary-900 border-6 rounded-md border-primary-300 dark:border-primary-900': item.id == currentLabelImage.id,
                                    'bg-surface-200 dark:bg-surface-900 border-6 rounded-md border-surface-200 dark:border-surface-900 opacity-60': item.id != currentLabelImage.id
                                }" class="label-image h-[86px] flex items-center justify-center m-4 gap-2 overflow-hidden cursor-pointer relative"
                                    @click="switchLabelImage(item.id)"
                                    :title="t('page.label.imagetitle', [item.id, options.index + 1])">
                                    <div class="text-gray-500 absolute text-md font-bold"
                                        style="width: 100px; height: 30px; left: -35px; top: 20px; transform: rotate(-90deg); text-align: center">
                                        {{ options.index + 1 }}
                                    </div>
                                    <div class="w-full h-full flex items-center justify-center position-relative">
                                        <Image :src="item.url" v-if="item.url.length > 0" width="150" />
                                        <Skeleton v-else width="10rem" height="4rem"></Skeleton>
                                        <!-- 未分类、训练数据、验证数据加上提醒标记 -->
                                        <div class="absolute h-full flex items-center justify-center bottom-0 right-1">
                                            <Badge severity="contrast" v-if="item.train_data_type == 0"></Badge>
                                            <Badge severity="primary" v-if="item.train_data_type == 1"></Badge>
                                            <Badge severity="info" v-if="item.train_data_type == 2"></Badge>
                                        </div>
                                    </div>
                                </div>
                            </template>
                        </VirtualScroller>
                    </div>
                </div>
            </div>
            <div class="h-full" style="width: calc(100% - 20rem)">
                <div class="w-full" style="height: 100vh; padding: 10px">
                    <Splitter class="w-full h-full" @resizestart="onSplitterResizeStart"
                        @resizeend="onSplitterResizeEnd">
                        <SplitterPanel :size="60" :minSize="30" class="flex items-center justify-center"
                            @focus="onSplitterPanelFocus">
                            <div class="w-full">
                                <div class="w-full rounded-t-xs flex items-center bg-surface-200 dark:bg-surface-600"
                                    style="height: 38px">
                                    <!-- 菜单栏 -->
                                    <div class="w-full flex items-center justify-between gap-2 ml-2 mr-2">
                                        <div class="flex items-center justify-start w-[12rem] min-w-[9rem]">
                                            <div class="text-sm text-surface-500 dark:text-surface-400">{{
                                                t('page.label.labelmode',
                                                    [drawingMode ? t('page.label.drawmode') : t('page.label.adjustmode')])
                                            }}</div>
                                            <div class="pl-1 text-surface-500 dark:text-surface-400 cursor-pointer"><i
                                                    class="pi pi-question-circle" style="font-size: 11px"
                                                    @click="helpVisible = true" /></div>
                                            <Drawer v-model:visible="helpVisible" :header="t('page.label.help')">
                                                <div class="w-full h-full"><iframe
                                                        :src="`${base}/static/${getLanguage().code}/help.html`"
                                                        class="w-full h-full rounded-md text-sm"
                                                        frameborder="0"></iframe></div>
                                            </Drawer>
                                        </div>

                                        <div class="flex items-center gap-2">
                                            <ButtonGroup>
                                                <Button :size="'small'" v-tooltip.bottom="t('page.label.drawnotice')"
                                                    @click="startDrawRectangles"
                                                    :severity="drawingMode ? 'primary' : 'secondary'"
                                                    icon="pi pi-stop" />
                                                <!-- <Button icon="pi pi-circle" :size="'small'" v-tooltip.bottom="'圆形框'"/> -->
                                                <Button icon="pi pi-arrows-alt" :size="'small'"
                                                    v-tooltip.bottom="t('page.label.adjustnotice')"
                                                    @click="stopDrawRectangles"
                                                    :severity="drawingMode ? 'secondary' : 'primary'" />
                                            </ButtonGroup>
                                            <Button icon="pi pi-eye" :size="'small'"
                                                v-tooltip.bottom="t('page.label.preview')" @click="openLabelRectDialog"
                                                :severity="selectedLabelId ? 'primary' : 'secondary'" />
                                            <Button icon="pi pi-search-plus" :size="'small'"
                                                v-tooltip.bottom="t('page.label.zoomin')" @click="zoomIn" />
                                            <Button icon="pi pi-search-minus" :size="'small'"
                                                v-tooltip.bottom="t('page.label.zoomout')" @click="zoomOut" />
                                            <Button icon="pi pi-replay" :size="'small'"
                                                v-tooltip.bottom="t('page.label.undo')" @click="undoHistory"
                                                :disabled="historyUndo.length == 0" />
                                            <Button icon="pi pi-refresh" :size="'small'"
                                                v-tooltip.bottom="t('page.label.redo')" @click="redoHistory"
                                                :disabled="historyRedo.length == 0" />
                                            <Button icon="pi pi-bullseye" :size="'small'"
                                                v-tooltip.bottom="t('page.label.reset')" @click="resetImage" />
                                            <Button icon="pi pi-ellipsis-v" :size="'small'"
                                                v-tooltip.bottom="t('page.label.moremenu')" @click="toggleMoreMenu" />
                                            <Button
                                                :icon="isFullscreen ? 'pi pi-window-minimize' : 'pi pi-window-maximize'"
                                                :size="'small'"
                                                v-tooltip.bottom="isFullscreen ? t('page.label.exitfullscreen') : t('page.label.fullscreen')"
                                                @click="toggleFullscreen" />
                                            <!-- <Button icon="pi pi-question" :size="'small'" v-tooltip.bottom="'帮助'"/> -->
                                            <!-- <Menu ref="moreMenuRef" :model="moreMenuItems" :popup="true" /> -->
                                            <Popover ref="op">
                                                <div class="flex flex-col gap-2 w-[20rem] select-none">
                                                    <div
                                                        class="text-sm font-medium text-surface-500 dark:text-surface-400">
                                                        {{ t('page.label.moreoperation') }}
                                                    </div>
                                                    <div
                                                        class="flex items-center gap-2 text-surface-700 dark:text-surface-300">
                                                        <div>
                                                            <i class="pi pi-hammer" />
                                                        </div>
                                                        <div>
                                                            {{ t('page.label.imagesetting') }}
                                                        </div>
                                                    </div>
                                                    <div class="ml-6">
                                                        <div class="flex items-center gap-4 mt-1">
                                                            <div class="w-30 cursor-pointer text-surface-700 dark:text-surface-300 hover:text-primary-500"
                                                                @click="labelImageRotate(-90)">
                                                                <i class="pi pi-directions-alt" />
                                                                {{ t('page.label.rotateleft') }}
                                                            </div>
                                                            <div class="cursor-pointer text-surface-700 dark:text-surface-300 hover:text-primary-500"
                                                                @click="labelImageRotate(90)">
                                                                <i class="pi pi-directions" />
                                                                {{ t('page.label.rotateright') }}
                                                            </div>
                                                        </div>
                                                        <div class="flex items-center gap-4 mt-4">
                                                            <div class="w-30 text-surface-700 dark:text-surface-300"><i
                                                                    class="pi pi-sun" /> {{ t('page.label.brightness')
                                                                    }}</div>
                                                            <div>
                                                                <Slider v-model="imageBrightness" :min="0" :max="100"
                                                                    :step="1" class="w-26"
                                                                    @slideend="labelImageChange('brightness')" />
                                                            </div>
                                                            <div>
                                                                {{ imageBrightness }}
                                                            </div>
                                                        </div>
                                                        <div class="flex items-center gap-4 mt-4">
                                                            <div class="w-30 text-surface-700 dark:text-surface-300"><i
                                                                    class="pi pi-star-half" /> {{
                                                                        t('page.label.contrast') }}</div>
                                                            <div>
                                                                <Slider v-model="imageContrast" :min="0" :max="100"
                                                                    :step="1" class="w-26"
                                                                    @slideend="labelImageChange('contrast')" />
                                                            </div>
                                                            <div>
                                                                {{ imageContrast }}
                                                            </div>
                                                        </div>
                                                        <div class="flex items-center gap-4 mt-4 mb-2">
                                                            <div class="w-30 text-surface-700 dark:text-surface-300"><i
                                                                    class="pi pi-sparkles" /> {{
                                                                        t('page.label.saturation') }}</div>
                                                            <div>
                                                                <Slider v-model="imageSaturation" :min="0" :max="100"
                                                                    :step="1" class="w-26"
                                                                    @slideend="labelImageChange('saturation')" />
                                                            </div>
                                                            <div>
                                                                {{ imageSaturation }}
                                                            </div>
                                                        </div>
                                                        <div class="flex items-center gap-4 mt-4 mb-2">
                                                            <div class="w-30 cursor-pointer text-surface-700 dark:text-surface-300 hover:text-primary-500"
                                                                @click="labelImageReset"><i class="pi pi-sync" /> {{
                                                                    t('page.label.imagereset') }}</div>
                                                        </div>
                                                    </div>
                                                </div>
                                            </Popover>
                                        </div>
                                        <div class="flex items-center justify-end gap-1 w-[12rem] min-w-[8rem]">
                                            <div class="text-sm">
                                                <span
                                                    :style="{ color: crosshairVisible ? 'var(--p-primary-500)' : 'var(--p-surface-400)' }">{{
                                                        t('page.label.crosshair') }}</span>
                                            </div>
                                            <ToggleSwitch v-model="crosshairVisible" />
                                            <Button icon="pi pi-cog" :size="'small'" severity="secondary" variant="text"
                                                rounded @click="settingPopoverToggle" />
                                            <Popover ref="settingPopover">
                                                <div class="flex flex-col w-[12rem] text-sm">
                                                    <div class="flex items-center justify-between gap-4 mr-1">
                                                        <div>{{ t('page.label.ruler') }}</div>
                                                        <div>
                                                            <Checkbox v-model="editedSetting.rulerVisible" binary />
                                                        </div>
                                                    </div>
                                                    <div class="flex items-center justify-between gap-4 mt-2 mb-2 mr-1">
                                                        <div>{{ t('page.label.grid') }}</div>
                                                        <div>
                                                            <Checkbox v-model="editedSetting.gridVisible" binary />
                                                        </div>
                                                    </div>
                                                    <div class="flex items-center justify-between gap-4">
                                                        <div>{{ t('page.label.crosshaircolor') }}</div>
                                                        <div>
                                                            <ColorPicker v-model="editedSetting.crosshairColor" />
                                                        </div>
                                                    </div>
                                                    <div class="flex items-center justify-between gap-4 mt-2 mb-2">
                                                        <div>{{ t('page.label.bboxbordercolor') }}</div>
                                                        <div>
                                                            <ColorPicker v-model="editedSetting.lableRectColor" />
                                                        </div>
                                                    </div>
                                                    <div class="flex items-center justify-between gap-4">
                                                        <div>{{ t('page.label.bboxanchorcolor') }}</div>
                                                        <div>
                                                            <ColorPicker v-model="editedSetting.labelAnchorColor" />
                                                        </div>
                                                    </div>
                                                    <Divider />
                                                    <div class="flex items-center justify-between">
                                                        <div>
                                                            <Button severity="secondary" size="small" icon="pi pi-times"
                                                                rounded @click="settingPopoverToggle" />
                                                        </div>
                                                        <div class="flex items-center justify-end gap-2">
                                                            <Button severity="secondary" size="small"
                                                                :label="t('page.common.reset')" @click="resetSetting" />
                                                            <Button severity="primary" size="small"
                                                                :label="t('page.common.submit')" @click="saveSetting" />
                                                        </div>
                                                    </div>
                                                </div>
                                            </Popover>
                                        </div>
                                    </div>
                                </div>
                                <div class="w-full bg-surface-400 dark:bg-surface-800"
                                    style="height: calc(100vh - 100px)">
                                    <!-- 图片 canvas 区 -->
                                    <div class="w-full h-full relative">
                                        <div id="imageCanvasBox"
                                            class="w-full h-full absolute top-0 left-0 overflow-hidden">
                                            <canvas ref="imageCanvas" id="imageCanvas" />
                                        </div>
                                    </div>
                                </div>
                                <div class="w-full rounded-b-xs flex items-center bg-surface-200 dark:bg-surface-600"
                                    style="height: 38px">
                                    <!-- 鼠标坐标信息展示栏 -->
                                    <div class="w-full flex items-center justify-between">
                                        <div
                                            class="flex items-center text-surface-500 dark:text-surface-400 gap-2 ml-2 mr-2">
                                            <div class="text-sm">
                                                {{ t('page.label.currentzoom') }}<span id="current_zoom">{{
                                                    currentZoom.toFixed(2)
                                                }}</span>
                                            </div>
                                            <div class="text-sm">
                                                {{ t('page.label.mouseposition') }}(x=<span id="cursor_postion_x">{{
                                                    currentMousePositionX }}</span>, y=<span id="cursor_postion_y"
                                                    class="w-5">{{
                                                        currentMousePositionY }}</span>)
                                            </div>
                                        </div>
                                        <div class="flex items-center gap-2 ml-2 mr-2">
                                            <div class="flex items-center text-sm text-surface-500 dark:text-surface-400 gap-2"
                                                v-if="currentLabelImage">
                                                <div class="flex items-center gap-2">
                                                    <i class="pi pi-image"></i>
                                                    {{ currentLabelImage.width ?? 0 }} x {{ currentLabelImage.height ??
                                                        0 }} {{
                                                        t('page.label.pixel') }}
                                                </div>
                                                <div class="flex items-center gap-2"><i class="pi pi-server"
                                                        style="font-size: 0.95rem"></i> {{
                                                            fileSizeStr(currentLabelImage.file_size
                                                                ?? 0) }}</div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </SplitterPanel>
                        <SplitterPanel :size="40" :minSize="30" class="flex items-center justify-center"
                            @focus="onSplitterPanelFocus">
                            <div class="w-full">
                                <div class="w-full rounded-t-xs flex items-center bg-surface-200 dark:bg-surface-600"
                                    style="height: 38px">
                                    <div class="w-full flex items-center justify-between gap-2 ml-2 mr-2">
                                        <div class="w-full flex items-center justify-center gap-2">
                                            <ButtonGroup>
                                                <Button :label="t('page.label.bboxlist')"
                                                    :severity="rightPanelMode === 1 ? 'primary' : 'secondary'"
                                                    size="small" icon="pi pi-clone" @click="switchRightPanelMode(1)" />
                                                <Button :label="t('page.label.bboxedit')"
                                                    :severity="rightPanelMode === 2 ? 'primary' : 'secondary'"
                                                    size="small" icon="pi pi-file-edit"
                                                    @click="switchRightPanelMode(2)" />
                                                <Button :label="t('page.label.labelpreview')"
                                                    :severity="rightPanelMode === 3 ? 'primary' : 'secondary'"
                                                    size="small" icon="pi pi-book" @click="switchRightPanelMode(3)" />
                                            </ButtonGroup>
                                        </div>
                                    </div>
                                </div>
                                <div class="w-full bg-surface-400 dark:bg-surface-800"
                                    style="height: calc(100vh - 100px); overflow: hidden">
                                    <!-- Datatable container -->
                                    <div class="p-2" style="height: 100%; overflow-x: hidden; position: relative">
                                        <div v-if="rightPanelMode === 1">
                                            <DataTable :value="imageLabelData.filter((o) => !o.deleted)"
                                                v-model:selection="selectedImageLabelData" selectionMode="single"
                                                :scrollable="false" showGridlines @row-select="onRowSelect"
                                                @row-unselect="onRowUnSelect" @row-dblclick="dblEditLabelData"
                                                @row-reorder="onRowReorder" @mousemove="onRowMouseMove"
                                                @mouseout="onRowMouseOut">
                                                <Column rowReorder :reorderableColumn="false" />
                                                <Column field="id" :header="t('page.label.bbox')">
                                                    <template #body="slotProps">
                                                        <div :id="`dt_label_${slotProps.data.id}`" class="min-w-[2rem]">
                                                            {{ slotProps.data.labelNumber }}
                                                        </div>
                                                    </template>
                                                </Column>
                                                <Column :header="t('page.label.coordinate')">
                                                    <template #body="slotProps">
                                                        <div class="text-sm min-w-[10rem]">
                                                            <div class="flex items-center w-full">
                                                                <div class="w-1/2">(x<sub>1</sub>={{
                                                                    slotProps.data.pos1[0].toFixed(1) }}</div>
                                                                <div class="pl-2">y<sub>1</sub>={{
                                                                    slotProps.data.pos1[1].toFixed(1) }})</div>
                                                            </div>
                                                            <div class="flex items-center w-full">
                                                                <div class="w-1/2">(x<sub>2</sub>={{
                                                                    slotProps.data.pos2[0].toFixed(1) }}</div>
                                                                <div class="pl-2">y<sub>2</sub>={{
                                                                    slotProps.data.pos2[1].toFixed(1) }})</div>
                                                            </div>
                                                        </div>
                                                    </template>
                                                </Column>
                                                <Column field="category" :header="t('page.label.category')">
                                                    <template #body="slotProps">
                                                        <div class="text-sm w-20">{{ slotProps.data.category.name }}
                                                        </div>
                                                    </template>
                                                </Column>
                                                <Column :header="t('page.label.operation')">
                                                    <template #body="slotProps">
                                                        <div class="flex items-center gap-2">
                                                            <i class="pi pi-pen-to-square"
                                                                @click="editLabelData(slotProps.data)"></i>
                                                            <i class="pi pi-times"
                                                                @click="deleteLabel(slotProps.data)"></i>
                                                        </div>
                                                    </template>
                                                </Column>
                                            </DataTable>
                                        </div>
                                        <div v-if="rightPanelMode === 2">
                                            <div v-if="imageLabelData.filter((item) => !item.deleted).length === 0">
                                                <div
                                                    class="text-center text-sm text-gray-600 dark:text-gray-400 bg-surface-300 dark:bg-surface-700 p-4 pt-2 pb-2 rounded-md">
                                                    <div>{{ t('page.label.noLabel') }}</div>
                                                </div>
                                            </div>
                                            <div v-else-if="!selectedImageLabelData">
                                                <div
                                                    class="text-center text-sm text-gray-600 dark:text-gray-400 bg-surface-300 dark:bg-surface-700 p-4 pt-2 pb-2 rounded-md">
                                                    <div>{{ t('page.label.selectbbox') }}</div>
                                                </div>
                                            </div>
                                            <div v-if="selectedImageLabelData"
                                                class="text-sm text-gray-300 dark:text-gray-400 bg-surface-500 dark:bg-surface-700 p-4 pt-2 pb-2 rounded-md">
                                                <div class="w-full flex items-center justify-between mb-2">
                                                    <div class="min-w-[6rem]">{{ t('page.label.labelnumbercategory') }}
                                                    </div>
                                                    <div class="flex justify-between gap-2">
                                                        <div class="w-[10rem]">
                                                            <InputGroup style="zoom: 0.85">
                                                                <Button size="small" @mousedown="changeLabelNumber(-1)"
                                                                    @mouseup="endLongPress"
                                                                    icon="pi pi-angle-left"></Button>
                                                                <InputNumber
                                                                    v-model="selectedImageLabelData.labelNumber"
                                                                    size="small" placeholder="x1" readonly integeronly
                                                                    :min="1" :max="999" />
                                                                <Button size="small" @mousedown="changeLabelNumber(1)"
                                                                    @mouseup="endLongPress"
                                                                    icon="pi pi-angle-right"></Button>
                                                            </InputGroup>
                                                        </div>
                                                        <div class="w-[10rem]">
                                                            <InputGroup style="zoom: 0.85">
                                                                <Button size="small"
                                                                    @mousedown="changeLabelCategory(-1)"
                                                                    @mouseup="endLongPress"
                                                                    icon="pi pi-angle-left"></Button>
                                                                <Select v-model="selectedImageLabelData.category"
                                                                    :options="labelCategories" optionLabel="name"
                                                                    size="small" fluid>
                                                                    <template #option="slotProps">
                                                                        <div class="flex items-center">
                                                                            <div class="text-sm">
                                                                                {{ slotProps.option.code }}
                                                                                <!-- {{slotProps.option.name }} -->
                                                                            </div>
                                                                        </div>
                                                                    </template>
                                                                </Select>
                                                                <Button size="small" @mousedown="changeLabelCategory(1)"
                                                                    @mouseup="endLongPress"
                                                                    icon="pi pi-angle-right"></Button>
                                                            </InputGroup>
                                                        </div>
                                                    </div>
                                                </div>

                                                <div class="w-full flex items-center justify-between mb-2">
                                                    <div class="min-w-[6rem]">{{ t('page.label.leftcoordinate') }}</div>
                                                    <div class="flex justify-between gap-2">
                                                        <div class="w-[10rem]">
                                                            <InputGroup style="zoom: 0.85">
                                                                <Button size="small" @mousedown="startLongPress(0, -1)"
                                                                    @mouseup="endLongPress" icon="pi pi-minus"></Button>
                                                                <InputNumber v-model="selectedImageLabelData.pos1[0]"
                                                                    size="small" placeholder="x1" readonly
                                                                    inputId="withoutgrouping" :useGrouping="false"
                                                                    :minFractionDigits="1" :maxFractionDigits="1" />
                                                                <Button size="small" @mousedown="startLongPress(0, 1)"
                                                                    @mouseup="endLongPress" icon="pi pi-plus"></Button>
                                                            </InputGroup>
                                                        </div>
                                                        <div class="w-[10rem]">
                                                            <InputGroup style="zoom: 0.85">
                                                                <Button size="small" @mousedown="startLongPress(1, -1)"
                                                                    @mouseup="endLongPress" icon="pi pi-minus"></Button>
                                                                <InputNumber v-model="selectedImageLabelData.pos1[1]"
                                                                    size="small" placeholder="y1" readonly
                                                                    inputId="withoutgrouping" :useGrouping="false"
                                                                    :minFractionDigits="1" :maxFractionDigits="1" />
                                                                <Button size="small" @mousedown="startLongPress(1, 1)"
                                                                    @mouseup="endLongPress" icon="pi pi-plus"></Button>
                                                            </InputGroup>
                                                        </div>
                                                    </div>
                                                </div>
                                                <div class="w-full flex items-center justify-between mb-2">
                                                    <div class="min-w-[6rem]">{{ t('page.label.rightcoordinate') }}
                                                    </div>
                                                    <div class="flex justify-between gap-2">
                                                        <div class="w-[10rem]">
                                                            <InputGroup style="zoom: 0.85">
                                                                <Button size="small" @mousedown="startLongPress(2, -1)"
                                                                    @mouseup="endLongPress" icon="pi pi-minus"></Button>
                                                                <InputNumber v-model="selectedImageLabelData.pos2[0]"
                                                                    size="small" placeholder="x2" readonly
                                                                    inputId="withoutgrouping" :useGrouping="false"
                                                                    :minFractionDigits="1" :maxFractionDigits="1" />
                                                                <Button size="small" @mousedown="startLongPress(2, 1)"
                                                                    @mouseup="endLongPress" icon="pi pi-plus"></Button>
                                                            </InputGroup>
                                                        </div>
                                                        <div class="w-[10rem]">
                                                            <InputGroup style="zoom: 0.85">
                                                                <Button size="small" @mousedown="startLongPress(3, -1)"
                                                                    @mouseup="endLongPress" icon="pi pi-minus"></Button>
                                                                <InputNumber v-model="selectedImageLabelData.pos2[1]"
                                                                    size="small" placeholder="y2" readonly
                                                                    inputId="withoutgrouping" :useGrouping="false"
                                                                    :minFractionDigits="1" :maxFractionDigits="1" />
                                                                <Button size="small" @mousedown="startLongPress(3, 1)"
                                                                    @mouseup="endLongPress" icon="pi pi-plus"></Button>
                                                            </InputGroup>
                                                        </div>
                                                    </div>
                                                </div>

                                                <div class="w-full mb-2">
                                                    <div class="flex items-center justify-between mt-2 mb-2">
                                                        <div class="min-w-[6rem]">{{ t('page.label.ocrtext') }}</div>
                                                        <div class="text-gray-800 dark:text-gray-500">
                                                            {{ t('page.label.ocrtexttip') }}
                                                        </div>
                                                    </div>
                                                    <!-- 富文本编辑 -->
                                                    <div class="w-full overflow-hidden pb-1"
                                                        :class="sourceToggle ? 'hidden' : 'block'">
                                                        <QuillEditor
                                                            v-model:editorOutput="selectedImageLabelData.editorValue"
                                                            :editorValue="selectedImageLabelData.editorValue"
                                                            :toolbarHeight="40" :editorHeight="editorHeight">
                                                        </QuillEditor>
                                                    </div>
                                                    <!-- 源码编辑 -->
                                                    <div class="w-full overflow-hidden"
                                                        :class="sourceToggle ? 'block' : 'hidden'">
                                                        <Textarea v-model="editorValueSourceText"
                                                            class="w-full border border-gray-300 rounded-md resize-none"
                                                            :style="{ height: editorHeight + 40 + 'px', lineHeight: '24px' }"
                                                            spellcheck="false"></Textarea>
                                                    </div>
                                                </div>

                                                <div class="w-full flex items-center justify-between mb-2">
                                                    <div>
                                                        <Button severity="primary" icon="pi pi-angle-left" rounded
                                                            size="small" @click="prevImageLabel"
                                                            :disabled="imageLabelData.filter((item) => !item.deleted).findIndex((item) => item.id === selectedLabelId) <= 0" />
                                                    </div>
                                                    <div>
                                                        <ButtonGroup>
                                                            <Button :severity="!sourceToggle ? 'primary' : 'secondary'"
                                                                :label="t('page.label.richedit')" rounded size="small"
                                                                @click="editorSourceToggle(false)"
                                                                style="font-size: 12px; line-height: 12px" />
                                                            <Button :severity="sourceToggle ? 'primary' : 'secondary'"
                                                                :label="t('page.label.rawtextedit')" rounded
                                                                size="small" @click="editorSourceToggle(true)"
                                                                style="font-size: 12px; line-height: 12px" />
                                                        </ButtonGroup>
                                                    </div>
                                                    <div>
                                                        <Button severity="primary" icon="pi pi-angle-right" rounded
                                                            size="small" @click="nextImageLabel"
                                                            :disabled="imageLabelData.filter((item) => !item.deleted).findIndex((item) => item.id === selectedLabelId) >= imageLabelData.filter((item) => !item.deleted).length - 1" />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                        <div v-if="rightPanelMode === 3">
                                            <div class="w-full h-full flex flex-col items-center justify-center">
                                                <div class="w-full">
                                                    <div
                                                        v-if="imageLabelData.filter((item) => !item.deleted).length === 0">
                                                        <div
                                                            class="text-center text-sm text-gray-600 dark:text-gray-400 bg-surface-300 dark:bg-surface-700 p-4 pt-2 pb-2 rounded-md">
                                                            <div>{{ t('page.label.nolabel') }}</div>
                                                        </div>
                                                    </div>
                                                    <div class="w-full overflow-hidden"
                                                        v-for="lableInfo in imageLabelData.filter((item) => !item.deleted)"
                                                        :key="lableInfo.id">
                                                        <div class="ocr-html m-1 p-2 overflow-hidden rounded text-surface-900 bg-surface-300 dark:text-surface-100 dark:bg-surface-900"
                                                            :class="{ 'ocr-html-active': lableInfo.id === selectedLabelId }"
                                                            v-html="lableInfo.category.is_figure ? cropCanvasImage2Html(lableInfo) : lableInfo.editorValue ? editorValue2Preview(lableInfo.editorValue) : '=该区块尚未标注内容='"
                                                            :id="'ocr-html-' + lableInfo.id"
                                                            @click="onOcrHtmlClick(lableInfo)"
                                                            @dblclick="editLabelData(lableInfo)"
                                                            @mousemove="onOcrHtmlMouseMove(lableInfo)"
                                                            @mouseout="onOcrHtmlMouseOut(lableInfo)"></div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                                <div class="w-full rounded-b-xs flex items-center bg-surface-200 dark:bg-surface-600"
                                    style="height: 38px">
                                    <!-- 保存栏 -->
                                    <div class="w-full flex items-center justify-between px-2">
                                        <div class="flex items-center gap-2">
                                            <ButtonGroup class="min-w-[12rem]">
                                                <Button :label="t('page.label.previmage')" severity="secondary"
                                                    size="small" icon="pi pi-arrow-left" @click="toPrevLabelImage" />
                                                <Button :label="t('page.label.nextimage')" severity="secondary"
                                                    size="small" icon="pi pi-arrow-right" @click="toNextLabelImage"
                                                    iconPos="right" />
                                            </ButtonGroup>
                                        </div>
                                        <div class="flex items-center gap-2">
                                            <Select v-model="dataType" :options="dataTypeItems" optionLabel="name"
                                                class="w-[8rem]" size="small">
                                                <template #option="slotProps">
                                                    <div class="flex items-center">
                                                        <div class="text-sm">{{ slotProps.option.name }}</div>
                                                    </div>
                                                </template>
                                            </Select>
                                            <Button class="min-w-[6rem]" :label="t('page.common.save')"
                                                severity="primary" size="small" icon="pi pi-save"
                                                @click="saveLabelData" />
                                            <Button class="min-w-[6rem]" :label="t('page.common.reset')"
                                                severity="secondary" size="small" icon="pi pi-hashtag" />
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </SplitterPanel>
                    </Splitter>
                    <Dialog v-model:visible="labelRectVisible" :keepInViewport="false"
                        :style="{ maxWidth: '50vw', paddingBottom: '2rem' }" :closable="false">
                        <template #header>
                            <div class="w-full flex items-center justify-between gap-2 pb-2">
                                <div class="flex items-center gap-4">
                                    <div class="flex items-center gap-2 text-lg font-bold">
                                        <i class="pi pi-eye"></i>
                                        <span>{{ t('page.label.preview') }}</span>
                                    </div>
                                    <div class="flex items-center gap-2">
                                        <ButtonGroup>
                                            <Button icon="pi pi-angle-left" size="small" rounded
                                                @click="prevImageLabel"></Button>
                                            <Button size="small">
                                                {{ selectedImageLabelData.labelNumber }}
                                            </Button>
                                            <Button icon="pi pi-angle-right" size="small" rounded
                                                @click="nextImageLabel"></Button>
                                        </ButtonGroup>
                                    </div>
                                </div>
                                <div class="flex items-center gap-2">
                                    <Button icon="pi pi-times" size="small" rounded severity="secondary"
                                        @click="labelRectVisible = false"></Button>
                                </div>
                            </div>
                        </template>
                        <div class="flex items-center justify-between select-none min-h-[10rem]">
                            <div v-html="labelRect2Html"></div>
                        </div>
                    </Dialog>
                </div>
            </div>
        </div>
    </div>
</template>
<style scoped>
:deep(.p-splitter) {
    border-width: 3px;
    user-select: none;
    /* border-color:var(--p-surface-500); */
    /* border-color: var(--p-surface-300); */
}

:deep(.p-splitter-gutter) {
    width: 5px;
    user-select: none;
    /* background-color: var(--p-surface-700); */
    /* background-color: var(--p-primary-600); */
}

:deep(.splitter-gutter-light) {
    background-color: var(--p-surface-300);
}

:deep(.splitter-gutter-drak) {
    background-color: '';
}

:deep(.mouseover_gutter) {
    background-color: var(--p-primary-500) !important;
}

:deep(.highlight_gutter) {
    background-color: var(--p-primary-400) !important;
}

:deep(.p-datatable-table-container) {
    /* scrollbar-width: thin; */
}

:deep(.p-datatable-row-selected) {
    /* background-color: var(--p-primary-500) !important; */
    /* color: var(--p-surface-900) !important; */
}

canvas {
    transform: translateZ(0);
}

div.label-image {
    &:hover {
        opacity: 90;
    }
}

div.ocr-html {
    font-size: 0.9rem;
    line-height: 1.5;
    /* color: var(--p-surface-100); */
    /* background-color: var(--p-surface-900); */
    border: 1px dashed var(--p-surface-700);
    cursor: pointer;
    overflow-x: auto;
    scrollbar-width: thin;

    &:hover {
        border-color: var(--p-primary-600);
    }
}

div.ocr-html-active {
    /* border-color: var(--p-primary-500); */
    background-color: var(--p-datatable-row-selected-background);
    border-style: solid;
    /* border-width: 2px; */
}

/* 表格边框可见 */
:deep(.p-editor-content table td) {
    border: 1px solid var(--p-surface-400);
}

:deep(div.ocr-html table td) {
    border: 1px solid var(--p-surface-400);
}

:deep(div.ocr-html math-field) {
    background: transparent;
    border: none;
    cursor: default;
    font-size: 14px;

    /* 保证公式双击事件能触发 */
    user-select: none;
    -webkit-user-select: none;
    /* Safari */
    -ms-user-select: none;
    /* IE 10 and IE 11 */
    pointer-events: none;

    /* 保证公式每次点击事件都能触发 */
    &::part(container) {
        pointer-events: none;
    }

    &::part(virtual-keyboard-toggle) {
        height: unset;
        display: none;
    }

    &.view::part(menu-toggle) {
        display: none;
    }
}
</style>
