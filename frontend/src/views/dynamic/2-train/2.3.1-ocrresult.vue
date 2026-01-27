<script lang="ts">
import { RouteMeta } from '@/router/MetaType';
export const routeMeta: RouteMeta = {
    title: 'ocrresult',
    icon: 'pi pi-map',
    displayMenu: 'hidden'
};
</script>
<script setup lang="ts">
import { Canvas, Group, FabricImage, Rect, Line, Point, Textbox } from 'fabric';
import { localStorageUtil } from '@/utils/LocalStorageUtil';
import { useLayout } from '@/layout/composables/layout';
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil'; // , showToast
import { ModeltestService } from '@/services/ModeltestService';
import { promise2, routeBack, $dom, delayDebounce, fileSizeStr, fileNameLimit, gotoRoute } from '@/utils/Common';
import { useConfirm } from 'primevue/useconfirm';
import { getUserId } from '@/utils/Token';
import { SSEClient } from '@/utils/SSEUtil';
import { useI18n } from 'vue-i18n';
// import { getLanguage } from '@/assets/lang/language';
import { VirtList } from 'vue-virt-list';
const ScanLoadingAnimate = defineAsyncComponent(() => import('./ScanLoadingAnimate.vue'));
const confirm = useConfirm();

const { t } = useI18n();
const base = import.meta.env.VITE_APP_BASE;
const server_url = import.meta.env.VITE_API_SERVER_URL;
const tikzJaxJsUrl = base + '/static/tikz/tikzjax.js';
const tikzJaxJsId = 'tikzjax';

const { virtualSetActiveMenu, isDarkTheme } = useLayout(); //isDarkTheme
const parentRoute = base + '/train/modeltest';

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

const file_id_list = localStorageUtil.get('modeltest', 'file_id_list') || [];
const model_list = localStorageUtil.get('modeltest', 'model_list') || [];

const ocrConstants = ref<any>({});
const getOCRConstants = async () => {
    let [err, res] = await promise2(ModeltestService.getOCRConstants());
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        ocrConstants.value = res.data;
    }
};

interface TestModelInfo {
    model_name: string;
    model_code: string;
    training_type: string;
    model_type: number; // 当前模型所对应的其基础模型的类别
    category_list: object[]; // 当前模型对应的其基础模型的标签分类
}

const currentModelName = ref<any>(model_list[0].model_name); // 当前模型的model_name
const currentModelInfo = computed((): TestModelInfo => {
    let model = model_list.find((item: any) => item.model_name === currentModelName.value);
    let model_name = model.model_name;
    let model_code = model.model_code;

    let training_type = model.training_type;
    let base_model_code = '';
    if (training_type == 'base') {
        base_model_code = model.model_code;
    } else {
        base_model_code = model.model_code.split(':')[0]; // 训练模型code前缀是其基础模型的code {base_code}:{training_run_id}:{后缀}
    }
    // 基础模型的类别（数值型，从1开始）
    let base_model_index = ocrConstants.value.base_model_list.findIndex((item: any) => item.model_code === base_model_code);
    let model_type = base_model_index + 1;
    let category_list = ocrConstants.value.base_model_list[base_model_index].category_list;
    let model_info = {
        model_name,
        model_code,
        training_type,
        model_type,
        category_list
    };
    return model_info;
});

const ocrFileList = ref<any[]>([]);
const currentOcrFile = ref<any>(null);
const currentImageOcrList = ref<any>(null);
let getFabricImageUrlObjectsLockSet = new Set();
let getImageOcrLabelInfoListLockSet = new Set();

// currentImageOcrList中的全部lableInfo扁平化存储方便虚拟组件预览
let allLabelHtmlIndexMap = new Map();
const allLabelHtmlList = shallowRef<any[]>([]);
const allOcrResultList = shallowRef<any[]>([]);

const currentFilePageIndex = ref<number>(0);
const currentFilePageDisplayIndex = ref<number>(0); // =currentFilePageIndex 专用页面上显示的（避免和currentFilePageIndex冲突）
const currentFilePageCount = ref<number>(1);
const filePagePopover = ref<any>(null);
const pageOffsets = ref<number[]>([]);

const filePageSlider = (e: any) => {
    if (currentFilePageCount.value > 1) {
        filePagePopover.value.toggle(e);
    }
};

const initOcrFileList = () => {
    ocrFileList.value = file_id_list.map((item: any) => ({
        id: item,
        images_info: [],
        file_name: '',
        file_size: 0,

        total_count: 0, // 总图片数x总模型数
        completed_count: 0, // 已完成识别的数量
        failed_count: 0, // 识别失败的数量
        waiting: true, // 全部模型识别是否有未完成等待的

        model_ocr_count: {} // 各个模型的识别结果
    }));
};

let isFirstLazyLoad = true;
const loadLazyTimeout = ref();
const virtualScrollerRef = ref<any>();

// const onLazyLoad = (event: any) => {
//     delayDebounce(() => {
//         _onLazyLoad(event);
//     }, 100);
// }

const onLazyLoad = (event: any) => {
    if (loadLazyTimeout.value) {
        console.log('clear lazy load timeout....');
        clearTimeout(loadLazyTimeout.value);
    }
    loadLazyTimeout.value = setTimeout(async () => {
        const { first, last } = event;
        const _lazyItems = [...ocrFileList.value];
        console.log('first', first, 'last', last);

        let lazyOcrFileList = [];
        for (let i = first; i < last; i++) {
            lazyOcrFileList.push(_lazyItems[i]); // 收集当前实际需要懒加载的那部分数据
        }

        let lazy_file_id_list = lazyOcrFileList.map((item: any) => item.id);
        let data = {
            lazy_file_id_list,
            model_list
        };
        let [err, res] = await promise2(ModeltestService.getTestOCRFileList(data));
        if (err) {
            // return;
        }
        if (res && res.code == 2000) {
            let ocr_file_list = res.data || [];
            for (let i = first; i < last; i++) {
                let id = _lazyItems[i].id;
                let item = ocr_file_list.find((item: any) => item.id == id);
                if (item) {
                    _lazyItems[i].images_info = item.images_info || '';
                    _lazyItems[i].file_name = item.file_name || '';
                    _lazyItems[i].file_size = item.file_size;

                    _lazyItems[i].total_count = item.total_count;
                    _lazyItems[i].completed_count = item.completed_count;
                    _lazyItems[i].failed_count = item.failed_count;
                    _lazyItems[i].waiting = item.waiting;

                    // 各个模型的识别结果
                    _lazyItems[i].model_ocr_count = item.model_ocr_count || {};
                }
            }
        }

        ocrFileList.value = _lazyItems;
        // 第一次懒加载时，设置第一个文件为当前文件
        if (isFirstLazyLoad) {
            isFirstLazyLoad = false;
            currentOcrFile.value = _lazyItems[first];
        }
    }, 500);
};

// 放大
const zoomIn = () => {
    const zoom = fabricImageCanvas.getZoom();
    let newZoom = Math.min(zoom * 1.1, 10); // 限制最大倍数
    fabricImageCanvas.zoomToPoint(new Point(fabricImageCanvas.getWidth() / 2, fabricImageCanvas.getHeight() / 2), newZoom);

    // fabricImageCanvas.getObjects().forEach((o: any) => {
    //     if (o.type === "textbox") {
    //         o.fontSize = textBoxFontSize;
    //         o.width = textBoxWidth(o.text);
    //     }
    // });

    // fabricImageCanvas.requestRenderAll();
    currentZoom.value = newZoom;
    // 重建标尺网格
    refreshDrawCanvas();
};

// 缩小
const zoomOut = () => {
    const zoom = fabricImageCanvas.getZoom();
    let newZoom = Math.max(zoom * 0.9, 0.1); // 限制最小倍数
    fabricImageCanvas.zoomToPoint(new Point(fabricImageCanvas.getWidth() / 2, fabricImageCanvas.getHeight() / 2), newZoom);
    // console.log(fabricImageCanvas.getObjects());
    // fabricImageCanvas.getObjects().forEach((o: any) => {
    //     if (o.type === "textbox") {
    //         o.fontSize = textBoxFontSize;
    //         o.width = textBoxWidth(o.text);
    //     }
    // });
    // fabricImageCanvas.requestRenderAll();
    currentZoom.value = newZoom;
    // 重建标尺网格
    refreshDrawCanvas();
};

// 还原
const resetZoom = () => {
    fabricImageCanvas.setViewportTransform([1, 0, 0, 1, 0, 0]); // 重置缩放和平移
    fabricImageCanvas.setZoom(1); // 清空缩放比例
    // fabricImageCanvas.requestRenderAll();
    currentZoom.value = 1;
    // 重建标尺网格
    refreshDrawCanvas();
};

const resetImage = () => {
    resetZoom();
};

const isFullscreen = ref(false);
// 页面最大化最小化
const toggleFullscreen = () => {
    $dom('#fullscreen-btn').click();
};

const onImageCanvasBoxResize = async () => {
    // const last_vpt = fabricImageCanvas.viewportTransform || [1, 0, 0, 1, 0, 0];
    // const last_zoomY = last_vpt[3];
    // const last_targetY = last_vpt[5];
    // (virtualScrollerRef.value as HTMLElement).style.height = '';

    const imageCanvasBoxElement = $dom('#imageCanvasBox');
    const fabricCanvasContainer = fabricImageCanvas.getElement().parentElement as HTMLElement;
    const fabricImage: any = fabricImageCanvas.getObjects('image')[0];
    if (!fabricCanvasContainer) return;
    if (!fabricImage) return;

    //这里重置宽高信息要与初始化时一致
    fabricCanvasContainer.style.width = imageCanvasBoxElement.clientWidth + 'px';
    fabricCanvasContainer.style.height = imageCanvasBoxElement.clientHeight + 'px';
    // fabricImageCanvas.setWidth(imageCanvasBoxElement.clientWidth);
    // fabricImageCanvas.setHeight(imageCanvasBoxElement.clientHeight);
    let currentPageIndex = currentFilePageIndex.value;
    await initLoadPageToCanvas(currentOcrFile.value);
    // 页码保持
    if (currentPageIndex > 0) {
        currentFilePageIndex.value = 0;
        changeFilePage(currentPageIndex);
    }

    // let transform = fabricImageCanvas.viewportTransform || [1, 0, 0, 1, 0, 0];
    // // 获取y方向的缩放比例
    // transform[3] = last_zoomY;
    // transform[5] = last_targetY;
    // fabricImageCanvas.setViewportTransform(transform);
    // imageCanvasRuntime.lastY = last_targetY;
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

let fabricImageCanvas: Canvas;
const imageCanvas = ref<HTMLCanvasElement>();
// const currentMousePositionX = ref(0);
// const currentMousePositionY = ref(0);
const currentZoom = ref(1); // 当前画布的缩放比例，放大缩小画布时这个值可以动态变的

let init_imageCanvasRuntime = {
    isDragging: false, // 标记是否正在拖拽图像
    // isDrawing: false, // 标记是否正在绘制图形
    isPanning: false, // 标记是否正在平移图像
    startX: 0, // 鼠标按下时的X坐标
    startY: 0, // 鼠标按下时的Y坐标
    lastX: 0, // 上一次鼠标X位置
    lastY: 0, // 上一次鼠标y位置
    tempRect: null, // 临时矩形框
    startPos: { x: 0, y: 0 }, // 鼠标按下时的坐标

    page_split_height: 12 // 分页线高度
};
let imageCanvasRuntime: any = { ...init_imageCanvasRuntime };

const currentSetting = ref({
    rulerVisible: true, // 默认标尺是否显示
    gridVisible: false, // 默认网格是否显示
    topBufferPageNum: 2, // 顶部缓冲页图数量 >=1
    bottomBufferPageNum: 2 // 底部缓冲页图数量 >=1
});
// 标尺canvas以及显示开关
const gridRulerCanvas = ref<HTMLCanvasElement>();
const bboxHighlightVisible = ref(true); // 默认识别框是否显示
const bboxHightlightOpacity = ref(0.2);
const bboxMouseOverOpacity = ref(0.1);

// 点击右侧识别预览区时，对应的识别框高亮动画
let requestAnimationFrameId: number | null = null; // 当前正在高亮的group 动画id
let requestAnimationLabelId: string | null = null; // 当前正在高亮的group labelId
const cancelRequestAnimation = () => {
    if (requestAnimationFrameId) {
        cancelAnimationFrame(requestAnimationFrameId);
        let group: any = fabricImageCanvas.getObjects('group').filter((group: any) => group.labelId == requestAnimationLabelId)[0];
        if (group) {
            let rect = group.mainRect;
            let fill = rect.get('fill');
            let fillArray = fill.replace('rgba(', '').replace(')', '').split(',');
            fillArray[3] = bboxHighlightVisible.value ? bboxHightlightOpacity.value.toString() : '0';
            rect.set('fill', `rgba(${fillArray.join(',')})`);
        }
        requestAnimationFrameId = null;
        requestAnimationLabelId = null;
    }
};

const changebboxHighlightVisible = (event: any) => {
    console.log(event);
    // 如果当前有高亮动画，先取消
    cancelRequestAnimation();
    fabricImageCanvas.getObjects('group').forEach((group: any) => {
        let rect = group.mainRect;
        let fill = rect.get('fill');
        let fillArray = fill.replace('rgba(', '').replace(')', '').split(',');
        fillArray[3] = bboxHighlightVisible.value ? bboxHightlightOpacity.value.toString() : '0';
        rect.set('fill', `rgba(${fillArray.join(',')})`);
    });
    fabricImageCanvas.requestRenderAll();
};

const bboxHightLightAnimation = (labelId: string) => {
    cancelRequestAnimation();
    let group: any = fabricImageCanvas.getObjects('group').filter((group: any) => group.labelId == labelId)[0];
    if (!group) return;
    let rect = group.mainRect;
    let fill = rect.get('fill');
    let fillArray = fill.replace('rgba(', '').replace(')', '').split(',');
    let orignalOpacity = Number(fillArray[3]);
    let currentOpacity = bboxHighlightVisible.value ? 0.8 : 0.6;
    fillArray[3] = currentOpacity.toString();
    rect.set('fill', `rgba(${fillArray.join(',')})`);
    fabricImageCanvas.requestRenderAll();

    const animationFrame = () => {
        currentOpacity -= 0.008;
        fillArray[3] = currentOpacity.toString();
        rect.set('fill', `rgba(${fillArray.join(',')})`);
        fabricImageCanvas.requestRenderAll();
        if (currentOpacity > orignalOpacity) {
            requestAnimationFrameId = requestAnimationFrame(() => {
                animationFrame();
            });
        }
    };

    requestAnimationLabelId = labelId;
    requestAnimationFrameId = requestAnimationFrame(() => {
        animationFrame();
    });
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
        skipOffscreen: true,
        enableRetinaScaling: false,
        renderingOptions: {
            preserveDrawingBuffer: true, // 对于 WebGL 很重要
            shouldCache: true // 启用缓存以优化渲染性能
        }
    });
    fabricImageCanvas.defaultCursor = 'grab';
};

// core
const computedPagePostion = async () => {
    throttle(
        requestAnimationFrame(() => {
            _computedPagePostion(); // 计算页面位置、动态处理视图内外页面的重建和销毁
        }),
        50
    );
};

// core
const _computedPagePostion = async () => {
    // if (currentFilePageCount.value <= 1) return; // 只有1页时不用处理页面计算

    const zoom = fabricImageCanvas.getZoom();
    const vpt = fabricImageCanvas.viewportTransform || [1, 0, 0, 1, 0, 0];
    //视窗宽高
    // const vptWidth = fabricImageCanvas.width;
    const vptHeight = fabricImageCanvas.height;
    // 视窗偏移量
    // const vptX = vpt[4];
    const vptY = vpt[5];
    const pageSplitLines = fabricImageCanvas.getObjects('line');
    // if (pageSplitLines.length == 0) return;
    let firstPageIndexInVpt = -1;
    let lastPageIndexInVpt = currentFilePageCount.value;
    // console.log(`pageSplitLines.length=${pageSplitLines.length},currentFilePageCount.value=${currentFilePageCount.value}`);
    for (let i = 0; i < currentFilePageCount.value; i++) {
        // const pageLine = pageSplitLines.find((item: any) => item.id == `page_split_line_${i}`) as Line;
        const pageLine = pageSplitLines[i] as Line;
        if (!pageLine) {
            continue;
        }
        const pageLineTop = pageLine.top!;
        if (pageLineTop + vptY / zoom > 0) {
            if (firstPageIndexInVpt == -1) {
                firstPageIndexInVpt = i;
            }
        }
        if (pageLineTop + vptY / zoom > vptHeight / zoom) {
            if (lastPageIndexInVpt == currentFilePageCount.value) {
                // console.log(`i=${i},pageLine.id=${(pageLine as any).id},pageLineTop=${pageLineTop}, vptY=${vptY}, vptHeight=${vptHeight}, zoom=${zoom}`);
                lastPageIndexInVpt = i;
                break;
            }
        }

        // if (firstPageIndexInVpt != -1 && lastPageIndexInVpt != -1) {
        //     break;
        // }
    }

    if (firstPageIndexInVpt == -1) {
        firstPageIndexInVpt = currentFilePageCount.value - 1;
    }

    // 鼠标滚轮连续滚动时候，如果页码没有变化不需要后续执行避免无谓的性能消耗
    if (currentFilePageIndex.value == firstPageIndexInVpt && firstPageIndexInVpt > 0) {
        return;
    }

    currentFilePageIndex.value = firstPageIndexInVpt;
    currentFilePageDisplayIndex.value = firstPageIndexInVpt;

    let topBufferPageNum = currentSetting.value.topBufferPageNum; // 上部缓冲区页数
    let bottomBufferPageNum = currentSetting.value.bottomBufferPageNum; // 下部缓冲区页数

    // clearAllLabelRect();
    for (let i = 0; i < currentFilePageCount.value; i++) {
        if (i < firstPageIndexInVpt - topBufferPageNum || i > lastPageIndexInVpt + bottomBufferPageNum) {
            // console.log('视窗内第', i, (i + 1), '页在视窗外--');
            if (i < firstPageIndexInVpt - 2 * topBufferPageNum || i > lastPageIndexInVpt + 2 * bottomBufferPageNum) {
                continue;
            }
            removePageFromCanvas(i);
            clearImageLabelRect(i);
        } else {
            // console.log('视窗内第', i, (i + 1), '页在视窗内');
            rebuildPageToCanvas(i, () => {
                // 构建第i页的标签矩形
                // console.log(`构建第${i}页的标签矩形>>>`);
                buildImageLableRect(i);
            });
        }
    }
    // fabricImageCanvas.requestRenderAll();

    // markdown预览区同步滚动
    virlist1ScrollToLable(currentFilePageIndex.value);
    // console.log(`fabricImageCanvas.getObjects("image").length=${fabricImageCanvas.getObjects("image").length}`);
};

//获取某图片（即page页）的某个识别框的索引
const getImageLabelIndex = (image_index: number, lable_number?: number) => {
    let labelId = `image_${image_index}_label_${lable_number || 0}`;
    let index = allLabelHtmlIndexMap.get(labelId);
    return index >= 0 ? index : -1;
};

const changeFilePageSlideend = (event: any) => {
    changeFilePage(event.value);
};

// 切换页码--》画布平移到对应页码位置
const changeFilePage = (pageIndex: number) => {
    let targetY = 0; // 第1页 targetY=0
    if (pageIndex > 0) {
        const page_split_height = imageCanvasRuntime.page_split_height;
        const pageSplitLine = fabricImageCanvas.getObjects('line')[pageIndex - 1] as Line; // 第2个页面的位置 通过 第一个分页线 得到
        if (!pageSplitLine) {
            console.error(`page_split_line_${pageIndex - 1} 不存在===================================fabricImageCanvas.getObjects("line").length=${fabricImageCanvas.getObjects('line').length}`);
            return;
        }
        targetY = -1 * pageSplitLine.top! - page_split_height;
    }

    let transform = fabricImageCanvas.viewportTransform || [1, 0, 0, 1, 0, 0];
    // 获取y方向的缩放比例
    const zoomY = transform[3];
    transform[5] = targetY * zoomY;
    fabricImageCanvas.setViewportTransform(transform);
    imageCanvasRuntime.lastY = targetY;
    // currentFilePageIndex.value = pageIndex;
    refreshDrawCanvas();
};

const nextPage = () => {
    if (currentFilePageIndex.value < fabricImageCanvas.getObjects('line').length - 1) {
        changeFilePage(currentFilePageIndex.value + 1);
    }
};
const prevPage = () => {
    if (currentFilePageIndex.value > 0) {
        changeFilePage(currentFilePageIndex.value - 1);
    }
};

// 给定相对图片的相对坐标，获取区块在画布中的绝对位置（不受缩放影响）
const unCalculateRectPosition = (pos1: [number, number], pos2: [number, number], image_index: number): { left: number; top: number; width: number; height: number } => {
    // const img = fabricImageCanvas.getObjects("image")[image_index] as FabricImage;
    const imgs = fabricImageCanvas.getObjects('image');
    const img = imgs.find((item: any) => item.id == `page_image_${image_index}`) as FabricImage;
    if (!img) {
        return { left: 0, top: 0, width: 0, height: 0 };
    }

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

console.log('calculateRectPosition', calculateRectPosition);

// 获取第一个fabric图片的左上角相对于容器左上角的视窗坐标
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

const refreshDrawCanvas = () => {
    drawGridRulerCanvas();
    computedPagePostion();
};

const drawGridRulerCanvas = () => {
    throttle(
        requestAnimationFrame(() => {
            _drawGridRulerCanvas(); // 绘制网格标尺画布
        }),
        50
    );
};

const _drawGridRulerCanvas = async () => {
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
    console.log('键盘按下', e.key);
};

const onKeyUp = (e: KeyboardEvent) => {
    console.log('键盘松开', e.key);
};

const onImageCanvasMouseDown = (opt: any) => {
    if (opt.target) {
        // console.log("点击了画布上的对象", opt.target);
        // return;
    }
    // console.log("点击了画布空白区域");
    const e = opt.e as MouseEvent;
    imageCanvasRuntime.isPanning = true;
    // 禁止选择
    fabricImageCanvas.selection = false;
    imageCanvasRuntime.lastX = e.clientX;
    imageCanvasRuntime.lastY = e.clientY;
};

const onImageCanvasMouseMove = (opt: any) => {
    const e = opt.e as MouseEvent;
    if (!imageCanvasRuntime.isPanning) return;
    // 拖拽移动画布中
    fabricImageCanvas.relativePan(new Point(e.clientX - imageCanvasRuntime.lastX, e.clientY - imageCanvasRuntime.lastY));
    // 记录最后位置
    imageCanvasRuntime.lastX = e.clientX;
    imageCanvasRuntime.lastY = e.clientY;

    //实时重建网格标尺、计算页面位置
    refreshDrawCanvas();
};
const onImageCanvasMouseUp = (opt: any) => {
    opt;
    // const e = opt.e as MouseEvent;
    // 停止平移
    imageCanvasRuntime.isPanning = false;
    // 允许选择对象
    fabricImageCanvas.selection = true;
    // console.log("鼠标松开拖拽结束", e.clientX, e.clientY);
};

const onImageCanvasMouseWheel = (opt: any) => {
    const e = opt.e as WheelEvent;
    e.preventDefault(); // 阻止默认滚轮事件（防止触发浏览器的整个页面缩放）
    throttle(
        requestAnimationFrame(() => {
            _onImageCanvasMouseWheel(opt);
        }),
        200
    );
};

const _onImageCanvasMouseWheel = (opt: any) => {
    const e = opt.e as WheelEvent;
    // e.preventDefault(); // 阻止默认滚轮事件（防止触发浏览器的整个页面缩放）
    const delta = e.deltaY;
    if (e.ctrlKey) {
        // 按住ctrl滚轮时，放大缩小画布
        const zoom = fabricImageCanvas.getZoom();
        const factor = delta > 0 ? 0.9 : 1.1; // 每次变化 10%
        let newZoom = zoom * factor;
        newZoom = Math.max(0.1, Math.min(newZoom, 10));
        currentZoom.value = newZoom;
        fabricImageCanvas.zoomToPoint(new Point(e.offsetX, e.offsetY), newZoom);

        if (opt.target) {
            // 鼠标放在group对象上缩放时，lable文字大小也要缩放处理
            const obj = opt.target as any;
            if (obj.type === 'group') {
                let group = obj as Group;
                let rect = (group as any).mainRect;
                let tb = (rect as any).labelRef;
                const boundingBox = group.getBoundingRect();
                tb.set({
                    opacity: 1,
                    fontSize: Math.ceil(currentZoom.value > 1 ? 18 / currentZoom.value : currentZoom.value < 1 ? 14 / currentZoom.value : 16),
                    width: ''
                });
                tb.set({
                    top: boundingBox.top - tb.height!
                });
            }
        }
    } else {
        // 普通滚轮事件，向上向下移动画布
        // console.log("普通滚轮事件", delta);
        fabricImageCanvas.relativePan(new Point(0, -1 * delta));
    }
    // fabricImageCanvas.requestRenderAll();
    //实时重建网格标尺、计算页面位置
    refreshDrawCanvas();
};

// 图片宽度匹配到画布宽度
const imageFitCanvasWidth = (image: any) => {
    if (!image) return;
    let image_index = Number(image.id.replace('page_image_', ''));

    let canvasWidth = fabricImageCanvas.getElement().clientWidth;
    let canvasHeight = fabricImageCanvas.getElement().clientHeight;
    console.log('canvas宽高', canvasWidth, canvasHeight);

    // 获取图片的宽高和位置信息
    const fabricCanvasContainer = fabricImageCanvas.getElement().parentElement as HTMLElement;
    let image_width = image.width;
    let image_height = image.height;
    let imageScaleX = fabricCanvasContainer.clientWidth / image_width;
    let imageScaleY = fabricCanvasContainer.clientHeight / image_height;
    let imageScale = Math.min(imageScaleX, imageScaleY);
    imageScale = Math.min(1, imageScale);
    let imageDisplayWidth = image_width * imageScale!;
    let imageDisplayHeight = image_height * imageScale!;
    const page_split_height = imageCanvasRuntime.page_split_height;
    let newZoom = canvasWidth / imageDisplayWidth;
    newZoom = Math.max(0.1, Math.min(newZoom, 10));

    fabricImageCanvas.zoomToPoint(new Point(0, 0), 1); // 先重置为不缩放
    const vpt = fabricImageCanvas.viewportTransform; // 再获取画布偏移信息
    // 平移画布至让点击的图片的左上角与视窗左上角对齐位置
    let panToX = -1 * vpt[4] - (canvasWidth - imageDisplayWidth) / 2;
    const pageOffset = pageOffsets.value[image_index] ?? image_index * (imageDisplayHeight + page_split_height);
    let panToY = -1 * vpt[5] - (canvasHeight - imageDisplayHeight) / 2 - pageOffset;
    fabricImageCanvas.relativePan(new Point(panToX, panToY));
    fabricImageCanvas.zoomToPoint(new Point(0, 0), newZoom); //画布放大
    currentZoom.value = newZoom; // 记录画布缩放比例，使得图片与视窗窗口居顶且宽度一样

    // 实时重建网格标尺
    drawGridRulerCanvas();
};

// 双击group对象，预览区同步滚动到对应label位置
const onCanvasGroupDblClick = (group: any) => {
    let labelId = group.labelId;
    if (labelId) {
        let index = allLabelHtmlIndexMap.get(labelId);
        let color = group.mainRect?.get('stroke') || 'yellow'; // group>rect边框颜色
        let { image_index, label_number } = parseLabelId(labelId);
        console.log('image_index', image_index, 'label_number', label_number);
        if (index == null || index < 0) return;
        if (prviewFormat.value == 'markdown') {
            let reactiveData = virlist1.value?.getReactiveData();
            if (!reactiveData) return;
            let beginIndex = reactiveData.inViewBegin;
            let endIndex = reactiveData.inViewEnd;
            let virListConatiner = $dom('#virListContainer');
            if (!virListConatiner) return;
            let containerHeight = virListConatiner.offsetHeight;
            if (!allLabelHtmlList.value.length || beginIndex >= allLabelHtmlList.value.length) return;
            endIndex = Math.min(endIndex, allLabelHtmlList.value.length - 1);
            let height = 0;
            for (let i = beginIndex; i <= endIndex; i++) {
                let itemLabelId = allLabelHtmlList.value[i].id;
                let itemDivEle = virListConatiner.querySelector(`[data-id="${itemLabelId}"]`) as HTMLElement;
                if (itemDivEle) {
                    height += itemDivEle.offsetHeight || 0;
                    if (height >= containerHeight) {
                        endIndex = i;
                        break;
                    }
                }
            }
            console.log('index', index, 'beginIndex', beginIndex, 'endIndex', endIndex);
            if (index < beginIndex || index >= endIndex) {
                console.log('不在可视区需要滚动');
                isDragVirList1Scrollbar.value = true; // 阻止virList1滚动回调
                virlist1.value?.scrollToIndex(index);
            }

            // 添加简易预览区块高亮效果
            let itemDivEle = virListConatiner.querySelector(`[data-id="${labelId}"]`) as HTMLElement;
            if (itemDivEle) {
                let ocrHtmlEle = itemDivEle.querySelector('div.ocr-html') as HTMLElement;
                ocrHtmlEle.style.position = 'relative';
                let div = document.createElement('div');
                div.id = `ocr-html-highlight`;
                div.style = `width:100%;height:100%;left:0;top:0;position:absolute;opacity:0.3;background:${color};border:1px dashed #fff;`;
                ocrHtmlEle.appendChild(div);
                setTimeout(() => {
                    ocrHtmlEle.removeChild(div);
                }, 500);
            }
        } else {
            virlist2.value?.scrollToIndex(image_index);
        }
    }
};

const onImageCanvasMouseDblClick = (opt: any) => {
    // const e = opt.e as MouseEvent;
    // canvas宽高
    // let canvasWidth = fabricImageCanvas.getElement().clientWidth;
    // let canvasHeight = fabricImageCanvas.getElement().clientHeight;
    // console.log("canvas宽高", canvasWidth, canvasHeight);
    if (opt.target) {
        let obj = opt.target as any;
        if (obj.type === 'image') {
            // 双击了image对象
            // console.log("双击了image对象", obj);
            imageFitCanvasWidth(obj);
        } else if (obj.type === 'group') {
            // 双击了group对象
            console.log('双击了group对象', obj);
            // 双击了group对象，需要同步高亮（必要时滚动）预览区到对应位置
            onCanvasGroupDblClick(obj);
        }
    } else {
        console.log('双击了画布背景区域');
        let image_index = currentFilePageIndex.value;
        let image = fabricImageCanvas.getObjects('image').find((item: any) => item.id == `page_image_${image_index}`);
        if (image) {
            imageFitCanvasWidth(image);
        }
    }
};

const onImageCanvasObjectAdded = (opt: any) => {
    opt;
};

const onImageCanvasObjectModefied = (opt: any) => {
    opt;
};

// 动态重建页
const rebuildPageToCanvas = async (image_index: number, callback?: Function) => {
    if (!currentOcrFile.value) return;
    let id = `page_image_${image_index}`;
    let find_index = fabricImageCanvas.getObjects('image').findIndex((item: any) => item.id == id);
    if (find_index >= 0) {
        if (callback) {
            setTimeout(() => {
                callback(image_index);
            }, 0);
        }
        return;
    }

    if (getFabricImageUrlObjectsLockSet.has(image_index)) {
        return;
    }
    getFabricImageUrlObjectsLockSet.add(image_index); // 添加获取图片url时的锁

    let image_info = currentOcrFile.value.images_info[image_index] || {};
    let image_path = image_info.image_path;
    let image_width = image_info.image_width;
    let image_height = image_info.image_height;
    if (!image_path || !image_width || !image_height) return;

    const fabricCanvasContainer = fabricImageCanvas.getElement().parentElement as HTMLElement;
    let imageScaleX = fabricCanvasContainer.clientWidth / image_width;
    let imageScaleY = fabricCanvasContainer.clientHeight / image_height;
    let imageScale = Math.min(imageScaleX, imageScaleY);
    imageScale = Math.min(1, imageScale);

    let page_split_height = imageCanvasRuntime.page_split_height;

    // let imageDisplayWidth = image_width * imageScale!;
    let imageDisplayHeight = image_height * imageScale!;

    // let pageWidth = imageDisplayWidth;
    let pageHeight = imageDisplayHeight + page_split_height;

    let left = fabricCanvasContainer.clientWidth / 2;
    const pageOffset = pageOffsets.value[image_index] ?? image_index * pageHeight;
    let top = fabricCanvasContainer.clientHeight / 2 + pageOffset;
    let host = server_url.startsWith('http') ? server_url : window.location.origin;
    const url = `${host}${image_path}`;
    const fabricImage = await FabricImage.fromURL(url, { crossOrigin: 'anonymous' });
    // console.log("fabricImage", image_index, "重新加载");
    if (!fabricImage) {
        return;
    }

    fabricImage.scale(imageScale); // 缩放图片以适应画布，这个值以后交互操作都不会变的，只是图片本身的缩放比例，不是画布的缩放比例zoom
    fabricImage.set({
        originX: 'center',
        originY: 'center',
        left: left,
        top: top,
        id: id,
        selectable: false,
        evented: true, // 图片触发点击等事件
        hoverCursor: 'grab'
    });
    fabricImageCanvas.add(fabricImage);
    // console.log("fabricImage", image_index, "重新加载");
    // fabricImageCanvas.renderAll();

    if (callback) {
        setTimeout(() => {
            callback(image_index);
            getFabricImageUrlObjectsLockSet.delete(image_index); // 移除获取图片url时的锁
        }, 0);
    }
    // console.log(`动态加载fabricImage图片成功===============image_index=${image_index}, url=${url}`);
};

// 动态移除页
const removePageFromCanvas = (image_index: number) => {
    if (image_index == 0) return; // 第一页不移除 （标尺的绘制是根据第一页image计算的）
    let id = `page_image_${image_index}`;
    let find_index = fabricImageCanvas.getObjects('image').findIndex((item: any) => item.id == id);
    if (find_index >= 0) {
        fabricImageCanvas.remove(fabricImageCanvas.getObjects('image')[find_index]);
    }
};

const initLoadPageToCanvas = async (ocrFile: any) => {
    if (!fabricImageCanvas) return;
    // 如果有先清理之前的图片
    // fabricImageCanvas.remove(...fabricImageCanvas.getObjects());
    fabricImageCanvas.clear();
    imageCanvasRuntime = { ...init_imageCanvasRuntime };
    currentZoom.value = 1;

    const fabricCanvasContainer = fabricImageCanvas.getElement().parentElement as HTMLElement;
    fabricImageCanvas.setViewportTransform([1, 0, 0, 1, 0, 0]);
    fabricImageCanvas.setDimensions({
        width: fabricCanvasContainer.clientWidth,
        height: fabricCanvasContainer.clientHeight
    });

    // let is_pdf = ocrFile.file_name?.endsWith(".pdf") || false;
    let page_split_height = imageCanvasRuntime.page_split_height;

    const images_info = ocrFile.images_info || [];
    const image_count = images_info.length || 0;

    // currentFilePageIndex.value = 0;
    // currentFilePageDisplayIndex.value = 0;

    currentFilePageCount.value = image_count;
    pageOffsets.value = [];
    let offsetY = 0;

    // let last_image_top = 0;
    for (let i = 0; i < image_count; i++) {
        const image_info = images_info[i] || {};
        const image_path = image_info.image_path;
        const image_width = image_info.image_width;
        const image_height = image_info.image_height;
        if (!image_path || !image_width || !image_height) {
            pageOffsets.value[i] = offsetY;
            continue;
        }

        let imageScaleX = fabricCanvasContainer.clientWidth / image_width;
        let imageScaleY = fabricCanvasContainer.clientHeight / image_height;
        let imageScale = Math.min(imageScaleX, imageScaleY);
        imageScale = Math.min(1, imageScale);

        let imageDisplayWidth = image_width * imageScale!;
        let imageDisplayHeight = image_height * imageScale!;
        pageOffsets.value[i] = offsetY;

        let pageWidth = imageDisplayWidth;
        let pageHeight = imageDisplayHeight + page_split_height;

        let left = fabricCanvasContainer.clientWidth / 2;
        let top = fabricCanvasContainer.clientHeight / 2 + offsetY;

        const image_placeholder = new Rect({
            originX: 'center',
            originY: 'center',
            left: left,
            top: top,
            width: imageDisplayWidth,
            height: imageDisplayHeight,
            fill: 'rgba(128, 128, 128, 0.1)',
            id: `page_placehold_${i}`,
            selectable: false,
            evented: false
        });
        fabricImageCanvas.add(image_placeholder);
        if (image_count > 1) {
            let lineX1 = left - pageWidth / 2;
            let lineX2 = left + pageWidth / 2;
            // let lineY = pageHeight * (i + 1) - page_split_height / 2;
            let lineY = fabricCanvasContainer.clientHeight / 2 + offsetY + imageDisplayHeight / 2 + page_split_height / 2;
            let lineColor = 'rgba(128, 128, 128, ' + (i < image_count - 1 ? 0.75 : 0) + ')'; // 线的颜色，最后一个Line纯透明不用看见
            let pageLine = new Line([lineX1, lineY, lineX2, lineY], {
                stroke: lineColor,
                strokeWidth: page_split_height, // 线宽
                id: `page_split_line_${i}`,
                selectable: false, // 是否可选
                evented: false
            });
            fabricImageCanvas.add(pageLine);
        }
        offsetY += pageHeight;
        let host = server_url.startsWith('http') ? server_url : window.location.origin;
        // 首次缓冲图片加载显示
        if (i <= currentSetting.value.bottomBufferPageNum) {
            const url = `${host}${image_path}`;
            const fabricImage = await FabricImage.fromURL(url, { crossOrigin: 'anonymous' });
            if (!fabricImage) continue;
            fabricImage.scale(imageScale); // 缩放图片以适应画布，这个值以后交互操作都不会变的，只是图片本身的缩放比例，不是画布的缩放比例zoom
            fabricImage.set({
                originX: 'center',
                originY: 'center',
                left: left,
                top: top,
                id: `page_image_${i}`,
                selectable: false,
                evented: true,
                hoverCursor: 'grab' // 图片触发点击等事件
            });
            fabricImageCanvas.add(fabricImage);
        }
        // fabricImageCanvas.backgroundImage = fabricImage;
        currentZoom.value = fabricImageCanvas.getZoom();
    }

    // if (callback) callback();

    fabricImageCanvas.defaultCursor = 'grab';
    // fabricImageCanvas.requestRenderAll();

    // 创建网格标尺线canvas
    refreshDrawCanvas();
};

const changeModel = (direction: 'next' | 'prev') => {
    const currentIndex = model_list.findIndex((item: any) => item.model_name === currentModelName.value);
    let newIndex = currentIndex;
    if (direction === 'next') {
        newIndex = currentIndex + 1;
        if (newIndex >= model_list.length) newIndex = 0;
    } else if (direction === 'prev') {
        newIndex = currentIndex - 1;
        if (newIndex < 0) newIndex = model_list.length - 1;
    }
    currentModelName.value = model_list[newIndex].model_name;
};

const parseJSON = (str: string) => {
    str = str.replace(/nan/gi, '0');
    str = str.replace(/\n/gi, '\\n');
    return JSON.parse(str);
};

let sseClientId = '';
const sseClient = ref<SSEClient>();
const sseInit = () => {
    let host = server_url.startsWith('http') ? server_url : window.location.origin;
    sseClientId = `client_${getUserId()}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    let sseUrl = `${host}/api/stream/modeltest/${sseClientId}`;
    sseClient.value = new SSEClient({
        clientId: sseClientId,
        url: sseUrl,
        reconnectAttempts: 5,
        reconnectInterval: 3000,
        onMessage: (message: any) => {
            // console.log('收到SSE消息:', message);
            // sse途径获取的图片识别结果处理
            if (message.type && message.type == 'modeltest') {
                let data = parseJSON(message.data);
                console.log('模型测试单张图片结果:', data);
                let file_id = data.file_id;
                let model_code = data.model_code;
                let status = data.status;
                let file_index = ocrFileList.value.findIndex((item: any) => item.id == file_id);
                console.log('file_index=', file_index);
                if (file_index < 0) return;
                let completed_count = ocrFileList.value[file_index].completed_count;
                let failed_count = ocrFileList.value[file_index].failed_count;
                let total_count = ocrFileList.value[file_index].total_count;
                if (status == 2) {
                    // 1=未开始 2=成功 3=失败
                    completed_count += 1;
                    // 单个模型的识别结果
                    ocrFileList.value[file_index].model_ocr_count[model_code].completed_count += 1;
                } else {
                    // 失败
                    failed_count += 1;
                    // 单个模型的识别结果
                    ocrFileList.value[file_index].model_ocr_count[model_code].failed_count += 1;
                }
                let waiting = completed_count + failed_count < total_count;
                ocrFileList.value[file_index].completed_count = completed_count;
                ocrFileList.value[file_index].failed_count = failed_count;
                ocrFileList.value[file_index].waiting = waiting;

                // 单个模型的识别结果
                let model_complete_count = ocrFileList.value[file_index].model_ocr_count[model_code].completed_count;
                let model_failed_count = ocrFileList.value[file_index].model_ocr_count[model_code].failed_count;
                let model_total_count = ocrFileList.value[file_index].model_ocr_count[model_code].total_count;
                let model_waiting = model_complete_count + model_failed_count < model_total_count;
                ocrFileList.value[file_index].model_ocr_count[model_code].waiting = model_waiting;

                // 如果当前文件当前模型
                if (currentOcrFile.value) {
                    let isCurrentFileAndMode = currentOcrFile.value.id == file_id && currentModelInfo.value.model_code == model_code;
                    if (isCurrentFileAndMode && !model_waiting) {
                        setTimeout(async () => {
                            await getModelOcrResult();
                            await initLoadPageToCanvas(currentOcrFile.value);
                        }, 0);
                    }
                }
            }
        },
        onError: (error: Event) => {
            console.error('SSE错误:', error);
        },
        onClose: () => {
            console.log('SSE连接关闭');
        },
        onOpen: () => {
            console.log('SSE连接打开');
        }
    });
    sseClient.value.connect();
};

const sseClose = () => {
    sseClient.value?.disconnect();
};

//===============================识别框相关
interface LabelCategory {
    code: string;
    name: string;
    value: number;
    is_figure: boolean;
}

interface LabelInfo {
    id: string;
    pos1: [number, number];
    pos2: [number, number];
    labelNumber: number;
    labelStyle: { color: string; background: string };
    imageId: number; // ocr图片id
    category: LabelCategory; // 分类
    ocrText: string; // ocr识别的文本
    editorValue: string; // 编辑器回显内容（替换掉markdown得到的富html内容）
    imageIndex: number; // 增补 图片索引
}

const duration_sum = ref(0); // 总耗时
const token_usage_sum = ref(0); // 总token消耗

const getModelOcrResult = async (callback?: Function) => {
    if (!currentOcrFile.value) return;

    currentImageOcrList.value = [];
    getFabricImageUrlObjectsLockSet.clear(); // 清空获取图片url时的锁
    getImageOcrLabelInfoListLockSet.clear(); // 清空获取页面（page=image）LableInfo时的锁

    allLabelHtmlIndexMap = new Map(); // 重置所有识别框索引映射
    // allLabelHtmlIndexMap.clear(); // 重置所有识别框索引映射
    allLabelHtmlList.value = []; // 重置所有识别框数据
    allOcrResultList.value = []; // 重置所有识别框数据

    duration_sum.value = 0;
    token_usage_sum.value = 0;
    let model_waiting = currentOcrFile.value.model_ocr_count[currentModelInfo.value.model_code].waiting;
    if (model_waiting) return;
    let [err, res] = await promise2(
        ModeltestService.getModelOcrResult({
            file_id: currentOcrFile.value.id,
            model_code: currentModelInfo.value.model_code
        })
    );
    if (err) {
        return;
    }
    if (res && res.code === 2000) {
        let file_id = res.data.file_id;
        let model_code = res.data.model_code;

        if (file_id != currentOcrFile.value.id) return;
        if (model_code != currentModelInfo.value.model_code) return;
        let image_ocr_list = res.data.image_ocr_list;

        let allLabelInfoIndex = 0;
        let allLabelHtmlListVal = [];
        let allOcrResultListVal = [];

        let host = server_url.startsWith('http') ? server_url : window.location.origin;

        for (let i = 0; i < image_ocr_list.length; i++) {
            let item = image_ocr_list[i];
            // console.log(item.ocr_result);
            let bboxLength = 0; // 快速获取识别框的数量，不同模型判断需要不同处理
            switch (currentModelInfo.value.model_type) {
                case 1: //got_ocr
                    bboxLength = item.ocr_result.length > 0 ? 1 : 0; // got_ocr部分区块，整体算一个区块
                    break;
                case 2: // dotsOCR
                    bboxLength = item.ocr_result.split('bbox').length - 1;
                    break;
                case 3: // dolphin
                    bboxLength = item.ocr_result.split('bbox').length - 1;
                    break;
                case 4: // deepseek_ocr
                    bboxLength = item.ocr_result.split('<|det|>').length - 1;
                    break;
                case 5: //paddleocr_vl
                    bboxLength = item.ocr_result.length > 0 ? 1 : 0;
                    break;
                case 6: //hunyuan_ocr
                    bboxLength = item.ocr_result.length > 0 ? 1 : 0;
                    break;
            }
            // 先填充占位
            image_ocr_list[i].labelInfoList = Array(bboxLength);
            for (let j = 0; j < bboxLength; j++) {
                let labelId = `image_${i}_label_${j}`;
                image_ocr_list[i].labelInfoList[j] = {}; // 填充空的占位对象

                allLabelHtmlListVal.push({
                    id: labelId,
                    image_index: i, // 图片索引+1=页码
                    label_index: j, // 图片内识别框索引
                    label_count: bboxLength, // 图片内识别框总数
                    label_html: '' // 识别框html内容
                });
                allLabelHtmlIndexMap.set(labelId, allLabelInfoIndex);
                allLabelInfoIndex += 1;
            }
            let image_path = image_ocr_list[i].image_path;
            const url = `${host}${image_path}`;
            image_ocr_list[i].image_path = url;
            allOcrResultListVal.push({
                id: item.image_uuid,
                image_index: i, // 图片索引+1=页码
                ocr_result: item.ocr_result // 每整页的ocr识别的原始结果
            });
        }

        currentImageOcrList.value = image_ocr_list;
        allLabelHtmlList.value = allLabelHtmlListVal;
        allOcrResultList.value = allOcrResultListVal;
        // console.log(allLabelHtmlIndexMap);
        // console.log(allLabelHtmlList.value);
        // console.log(allOcrResultList.value);

        duration_sum.value = res.data.duration_sum;
        token_usage_sum.value = res.data.token_usage_sum;

        await ensurePreviewContent();
        callback?.();
    }
};

// 按页码清除标签
const clearImageLabelRect = (image_index: number) => {
    if (!fabricImageCanvas) return;
    // console.log(`清除第${image_index}页的标签矩形`);
    fabricImageCanvas.getObjects().forEach((obj: any) => {
        if ((obj.type === 'group' || obj.type === 'textbox') && obj.labelId.indexOf(`image_${image_index}_label_`) >= 0) {
            fabricImageCanvas.remove(obj);
        }
    });
    // fabricImageCanvas.requestRenderAll();
};

// 清除所有标签
const clearAllLabelRect = () => {
    if (!fabricImageCanvas) return;
    fabricImageCanvas.getObjects().forEach((obj: any) => {
        if (obj.type === 'group' || obj.type === 'textbox') {
            fabricImageCanvas.remove(obj);
        }
    });
    // fabricImageCanvas.requestRenderAll();
};
console.log('clearAllLabelRect', clearAllLabelRect);

let categoryColorMap: Map<number, string> = new Map();
categoryColorMap.set(101, '#ff0000');
categoryColorMap.set(102, '#ff9900');
categoryColorMap.set(103, '#00ff00');
categoryColorMap.set(104, '#ffff00');
categoryColorMap.set(105, '#ff00ff');
categoryColorMap.set(106, '#00ffff');
categoryColorMap.set(107, '#000000');
categoryColorMap.set(108, '#800000');
categoryColorMap.set(109, '#008000');
categoryColorMap.set(201, '#808000');
categoryColorMap.set(202, '#000080');
categoryColorMap.set(203, '#800080');
categoryColorMap.set(204, '#0099ff');
categoryColorMap.set(205, '#996633');
categoryColorMap.set(206, '#808080');
categoryColorMap.set(207, '#404040');
categoryColorMap.set(208, '#202020');
categoryColorMap.set(900, '#33dd33');

function hexToRgb(hex: any) {
    // 移除可能存在的#
    hex = hex.replace(/^#/, '');
    // 解析r、g、b的值
    let r: any = parseInt(hex.substring(0, 2), 16),
        g: any = parseInt(hex.substring(2, 4), 16),
        b: any = parseInt(hex.substring(4, 6), 16);
    return { r, g, b }; // 返回对象形式的RGB值
}

const buildImageLableRect = async (image_index: number) => {
    let exist = fabricImageCanvas.getObjects().find((obj: any) => obj.labelId?.indexOf(`image_${image_index}_label_`) >= 0);
    if (exist) return;
    // 绘制单个页面的全部矩形标签
    let labelInfoList: LabelInfo[] = await getImageOcrLabelInfoList(image_index);
    // console.log(`11111构建第${image_index}页的标签矩形，共${labelInfoList.length}个`);
    let drawObjList: any[] = [];
    for (let i = 0; i < labelInfoList.length; i++) {
        let labelInfo = labelInfoList[i];
        let [group, tb] = buildLableRect(labelInfo);
        if (group && tb) {
            drawObjList.push(group);
            drawObjList.push(tb);
        }
    }
    fabricImageCanvas.add(...drawObjList);
};

// 创建单个标签矩形
const buildLableRect = (labelInfo: LabelInfo): [Group | null, Textbox | null] => {
    let id = labelInfo.id;
    let pos = unCalculateRectPosition(labelInfo.pos1, labelInfo.pos2, labelInfo.imageIndex);
    if (pos.width == 0 && pos.height == 0) {
        return [null, null];
    }
    let categoryColor = categoryColorMap.get(labelInfo.category.value) || '#ff0000';
    const rgbTempColor = hexToRgb(categoryColor);

    const rect = new Rect({
        left: pos.left,
        top: pos.top,
        width: pos.width,
        height: pos.height,
        fill: `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b}, ${bboxHighlightVisible.value ? bboxHightlightOpacity.value : 0})`, // 填充颜色
        stroke: categoryColor, // 边框颜色
        selectable: false,
        // originX: "center",
        // originY: "center",
        evented: false,
        strokeWidth: 1, //  描边宽度，不要除比例 1.0 / currentZoom.value
        cornerStrokeWidth: 1, // 控制点边框的宽度，不要除比例 1.0 / currentZoom.value
        strokeUniform: true, // 确保缩放时描边宽度不变
        objectCaching: false // 避免重复缓存导致性能差
        // opacity: labelNumberOpacity(rightPanelMode.value),
    });
    const left = rect.left!;
    const top = rect.top!;

    //${labelInfo.category.name}
    const tb = new Textbox(`${labelInfo.labelNumber}.${labelInfo.category.code}`, {
        left: rect.left!,
        top: rect.top! - 18,
        // width: 100,
        editable: false,
        fontSize: 16, // 12 / currentZoom.value
        fill: '#ffffff', // 文字白色
        backgroundColor: categoryColor, // 背景底颜色
        // fill: `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`,
        // borderColor: `rgb(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b})`,
        selectable: false,
        evented: false, // 不参与事件
        // backgroundColor: style.background,
        opacity: 0
    });
    const group = new Group([rect], {
        hasBorders: false,
        selectable: false,
        evented: true,
        subTargetCheck: true,
        hoverCursor: 'default',
        originX: 'center',
        originY: 'center',
        left: left + rect.width / 2,
        top: top + rect.height / 2
    });

    (group as any).mainRect = rect;
    (rect as any).labelRef = tb;
    (group as any).labelId = id;
    (rect as any).labelId = id;
    (tb as any).labelId = id;

    //--------------------------start-------------------------
    group.on('mouseover', () => {
        const boundingBox = group.getBoundingRect();

        tb.set({
            opacity: 1,
            fontSize: Math.ceil(currentZoom.value > 1 ? 18 / currentZoom.value : currentZoom.value < 1 ? 14 / currentZoom.value : 16),
            width: ''
        });
        tb.set({
            top: boundingBox.top - tb.height!
        });
        rect.set('fill', `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b}, ${bboxMouseOverOpacity.value})`);
        fabricImageCanvas.requestRenderAll();
    });

    // group.on("mousemove", () => {
    // });
    group.on('mouseout', (opt: any) => {
        // console.log(opt);
        opt;
        tb.set({
            opacity: 0
        });
        rect.set('fill', `rgba(${rgbTempColor.r}, ${rgbTempColor.g}, ${rgbTempColor.b}, ${bboxHighlightVisible.value ? bboxHightlightOpacity.value : 0})`);
        fabricImageCanvas.requestRenderAll();
    });

    // 添加 group 到画布
    //fabricImageCanvas.add(group);
    //fabricImageCanvas.add(tb);
    return [group, tb];
};

const getImageOcrLabelInfoList = async (image_index: number): Promise<LabelInfo[]> => {
    if (!currentImageOcrList.value || !currentImageOcrList.value[image_index]) return [];
    let labelInfoList = currentImageOcrList.value[image_index].labelInfoList; // 先尝试从缓存中获取，提前有生成占位，但无实际数据
    if (!labelInfoList || labelInfoList.length == 0) return [];
    // 检查是否有锁，如果有则等待锁释放
    if (getImageOcrLabelInfoListLockSet.has(image_index)) {
        return [];
    }
    getImageOcrLabelInfoListLockSet.add(image_index);
    if (!labelInfoList[0].id) {
        // 没有实际数据需要实际计算得到然后存入对应缓存位置
        labelInfoList = await _getImageOcrLabelInfoList(image_index);
        if (!currentImageOcrList.value || !currentImageOcrList.value[image_index]) return [];
        currentImageOcrList.value[image_index].labelInfoList = labelInfoList;

        // 同步更新 allLabelHtmlList
        if (labelInfoList.length > 0) {
            let labelIndex = allLabelHtmlIndexMap.get(labelInfoList[0].id);
            let htmlList = [];
            for (let i = 0; i < labelInfoList.length; i++) {
                htmlList.push({
                    id: labelInfoList[i].id,
                    image_index: image_index,
                    label_index: i,
                    label_count: labelInfoList.length,
                    label_html: labelInfoList[i].editorValue
                });
            }
            allLabelHtmlList.value.splice(labelIndex, labelInfoList.length, ...htmlList);
            virlist1.value?.forceUpdate(); // 强制更新virlist1，确保渲染最新数据
        }
    }
    getImageOcrLabelInfoListLockSet.delete(image_index);
    return labelInfoList;
};

const ensurePreviewContent = async () => {
    if (prviewFormat.value !== 'markdown') return;
    if (!currentImageOcrList.value) return;
    if (!allLabelHtmlList.value.length) return;
    const currentLabels = currentImageOcrList.value[currentFilePageIndex.value]?.labelInfoList?.length || 0;
    if (currentLabels > 0) {
        await getImageOcrLabelInfoList(currentFilePageIndex.value);
        return;
    }
    const nextIndex = currentImageOcrList.value.findIndex((item: any) => (item?.labelInfoList?.length || 0) > 0);
    if (nextIndex < 0) return;
    await getImageOcrLabelInfoList(nextIndex);
    const labelIndex = getImageLabelIndex(nextIndex, 0);
    if (labelIndex < 0) return;
    isDragVirList1Scrollbar.value = true;
    virlist1.value?.scrollIntoView(labelIndex);
    setTimeout(() => {
        isDragVirList1Scrollbar.value = false;
    }, 200);
};

const getLabelInfoHtml = async (imageInfo: any, labelInfo: LabelInfo) => {
    let editorValue = labelInfo.category.is_figure ? await cropCanvasImage2Html(imageInfo.image_path, labelInfo) : await markdown2Html(labelInfo.ocrText, imageInfo);
    return editorValue;
};

const _getImageOcrLabelInfoList = async (image_index: number): Promise<LabelInfo[]> => {
    if (!currentImageOcrList.value) return [];
    let image_ocr = currentImageOcrList.value[image_index];
    if (!image_ocr) return [];
    let ocr_label = image_ocr.ocr_result;
    let images_info = currentOcrFile.value.images_info;
    let image_info = images_info[image_index];
    let image_width = image_info.image_width;
    let image_height = image_info.image_height;

    if ((currentModelInfo.value.model_type == 1 || currentModelInfo.value.model_type == 5 || currentModelInfo.value.model_type == 6) && ocr_label.indexOf('"bbox"') == -1) {
        let category = currentModelInfo.value.category_list[0] as LabelCategory;
        let labelInfo: LabelInfo = {
            id: `image_${image_index}_label_0`,
            pos1: [0, 0],
            pos2: [image_width, image_height],
            labelNumber: 1,
            labelStyle: { color: 'white', background: 'black' }, // 这里不需要了
            imageId: image_info.image_uuid,
            category: category,
            ocrText: ocr_label,
            editorValue: '', //await markdown2Html(ocr_label)
            imageIndex: image_index
        };
        labelInfo.editorValue = await getLabelInfoHtml(image_info, labelInfo);
        return [labelInfo];
    }

    //dolphin
    if (currentModelInfo.value.model_type == 3) {
        console.log(ocr_label);
        let list = eval(ocr_label); // dolphin 识别结果是一个数组，每个元素是一个对象，包含bbox、category、text
        let labelInfoList = [];
        for (let i = 0; i < list.length; i++) {
            let label = list[i];
            // console.log(label);
            let bbox = label.bbox;
            let labelLabelVal = label.label;
            console.log(labelLabelVal);
            let category = (currentModelInfo.value.category_list.find((item: any) => item.code.toLowerCase() == labelLabelVal.toLowerCase()) || currentModelInfo.value.category_list[0]) as LabelCategory; //item.category;
            let text = label.text;
            // 如果是插图
            if (category.is_figure) {
                text = `\\begin{figure}\\includegraphics\[position=${bbox.join(',')}\]{}\\end{figure}`;
            }
            let labelInfo: LabelInfo = {
                id: `image_${image_index}_label_${i}`,
                pos1: [bbox[0], bbox[1]],
                pos2: [bbox[2], bbox[3]],
                labelNumber: i + 1,
                labelStyle: { color: 'white', background: 'black' },
                // readIndex: i,
                imageId: image_info.image_uuid,
                category: category,
                ocrText: text,
                // 区块数量较多时如果立即执行await markdown2Html可能会感觉区块显示会有一点延迟（1-2秒），暂时先不赋值，让界面尽快显示
                editorValue: '',
                imageIndex: image_index
            };
            // console.log(labelInfo.labelNumber, labelInfo.id);
            // 根据数据绘rect
            labelInfo.editorValue = await getLabelInfoHtml(image_info, labelInfo);
            labelInfoList.push(labelInfo);
        }
        return labelInfoList;
    }

    //deepseek_ocr 识别结果处理
    if (currentModelInfo.value.model_type == 4 && ocr_label.includes('<|ref|>')) {
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

        let labelInfoList = [];
        for (let i = 0; i < labels.length; i++) {
            let label = labels[i] || {};
            let bbox = label.bbox;
            let category = (currentModelInfo.value.category_list.find((item: any) => item.code.toLowerCase() == label.category.toLowerCase()) || currentModelInfo.value.category_list[0]) as LabelCategory; //label.category;
            let text = label.text;
            // 如果是插图
            if (category.is_figure) {
                text = `\\begin{figure}\\includegraphics\[position=${bbox.join(',')}\]{}\\end{figure}`;
            }
            let labelInfo: LabelInfo = {
                id: `image_${image_index}_label_${i}`,
                pos1: [bbox[0], bbox[1]],
                pos2: [bbox[2], bbox[3]],
                labelNumber: i + 1,
                labelStyle: { color: 'white', background: 'black' },
                imageId: image_info.image_uuid,
                category: category,
                ocrText: text,
                // 区块数量较多时如果立即执行await markdown2Html可能会感觉区块显示会有一点延迟（1-2秒），暂时先不赋值，让界面尽快显示
                editorValue: '',
                imageIndex: image_index
            };
            labelInfo.editorValue = await getLabelInfoHtml(image_info, labelInfo);
            labelInfoList.push(labelInfo);
        }
        return labelInfoList;
    }

    // paddleocr_vl 识别结果处理
    // if (currentModelInfo.value.model_type == 5) {
    //     let category = currentModelInfo.value.category_list[0] as LabelCategory;
    //     let labelInfo: LabelInfo = {
    //         id: `image_${image_index}_label_0`,
    //         pos1: [0, 0],
    //         pos2: [image_width, image_height],
    //         labelNumber: 1,
    //         labelStyle: { color: "white", background: "black" },  // 这里不需要了
    //         imageId: image_info.image_uuid,
    //         category: category,
    //         ocrText: ocr_label,
    //         editorValue: '', //await markdown2Html(ocr_label)
    //         imageIndex: image_index,
    //     }
    //     labelInfo.editorValue = await getLabelInfoHtml(image_info, labelInfo);
    //     return [labelInfo];

    // }

    // dotsOCR
    if (currentModelInfo.value.model_type == 2) {
        ocr_label = ocr_label.substring(ocr_label.indexOf('[{'), ocr_label.lastIndexOf('}]') + 2);
        if (!ocr_label.startsWith('[{')) return [];
        if (!ocr_label.endsWith('}]')) return [];
        // 清理JSON字符串，移除或转义不合法的字符
        console.log(ocr_label,"image_index=",image_index);
        let list = parseJSON(ocr_label);
        let labelInfoList = [];
        for (let i = 0; i < list.length; i++) {
            let label = list[i] || {};

            let bbox = label.bbox;
            let category = (currentModelInfo.value.category_list.find((item: any) => item.code.toLowerCase() == label.category.toLowerCase()) || currentModelInfo.value.category_list[0]) as LabelCategory; //label.category;
            let text = label.text;
            // 如果是插图
            if (category.is_figure) {
                text = `\\begin{figure}\\includegraphics\[position=${bbox.join(',')}\]{}\\end{figure}`;
            }
            let labelInfo: LabelInfo = {
                id: `image_${image_index}_label_${i}`,
                pos1: [bbox[0], bbox[1]],
                pos2: [bbox[2], bbox[3]],
                labelNumber: i + 1,
                labelStyle: { color: 'white', background: 'black' },
                // readIndex: i,
                imageId: image_info.image_uuid,
                category: category,
                ocrText: text,
                // 区块数量较多时如果立即执行await markdown2Html可能会感觉区块显示会有一点延迟（1-2秒），暂时先不赋值，让界面尽快显示
                editorValue: '',
                imageIndex: image_index
            };
            // console.log(labelInfo.labelNumber, labelInfo.id);
            // 根据数据绘rect
            labelInfo.editorValue = await getLabelInfoHtml(image_info, labelInfo);
            labelInfoList.push(labelInfo);
        }
        return labelInfoList;
    }
    return [];
};

const setCurrentOcrFile = (item: any, event: any) => {
    if (event.target?.tagName == 'I') return; // 点击删除图标时不切换当前文件
    currentOcrFile.value = item;
};

const removeOcrResult = async (file_id: number, event: any) => {
    confirm.require({
        target: event.currentTarget,
        message: t('page.ocrresult.removefileocr'),
        icon: 'pi pi-exclamation-triangle',
        rejectProps: {
            label: t('page.common.cancel'),
            severity: 'secondary',
            outlined: true
        },
        acceptProps: {
            label: t('page.common.confirm'),
            severity: 'danger'
        },
        accept: () => {
            _removeOcrResult(file_id);
        },
        reject: () => {}
    });
};

const _removeOcrResult = async (file_id: number) => {
    if (!file_id) return;
    showLoading();
    let [err, res] = await promise2(ModeltestService.removeOcrResult({ file_id: file_id, model_code: '' }));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let index = ocrFileList.value.findIndex((item: any) => item.id == file_id);
        if (index == -1) return;
        ocrFileList.value.splice(index, 1);
        let newCurrentOcrFile = ocrFileList.value[index - 1] || ocrFileList.value[index];
        if (newCurrentOcrFile) {
            currentOcrFile.value = newCurrentOcrFile;
        } else {
            setTimeout(() => {
                gotoRoute('/train/modeltest');
            }, 100);
        }
    }
};

//=============================================识别预览相关===============================================

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

const loadImageAsync = (url: string): Promise<any> => {
    if (!url) {
        return Promise.reject(new Error('URL不能为空'));
    }
    let host = server_url.startsWith('http') ? server_url : window.location.origin;
    url = url.startsWith('http') ? url : `${host}${url}`;
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.crossOrigin = 'Anonymous';
        img.src = url;
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error(`图片加载失败: ${url}`));
    });
};

// 插图插画裁剪(不受缩放影响)
const cropCanvasImage2Html = async (imagePath: string, labelInfo: any, zoom: number = 1, showImageTitle: boolean = true) => {
    let x = labelInfo.pos1[0];
    let y = labelInfo.pos1[1];
    let width = labelInfo.pos2[0] - labelInfo.pos1[0];
    let height = labelInfo.pos2[1] - labelInfo.pos1[1];

    let pos = unCalculateRectPosition(labelInfo.pos1, labelInfo.pos2, 0); // 暂时固定按第一页图片来计算位置
    let canvas_width = pos.width * zoom; // zoom 放大或缩小倍数
    let canvas_height = pos.height * zoom;

    let canvas = document.createElement('canvas');
    let ctx = canvas.getContext('2d')!;
    canvas.width = canvas_width;
    canvas.height = canvas_height;
    const img = await loadImageAsync(imagePath);
    ctx.drawImage(img, x, y, width, height, 0, 0, canvas_width, canvas_height);
    let cropImage = canvas.toDataURL('image/jpeg');
    canvas.remove();
    //<div class="text-sm">${labelInfo.category.name}</div>
    let title = showImageTitle ? labelInfo.category?.name || '' : '';
    return `<img src=${cropImage} title="${title}" width="${canvas_width}" height="${canvas_height}"/>`;
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

// 这里markdown2Html主要是为了纯web显示
const markdown2Html = async (markdown: string, imageInfo: any) => {
    let text = markdown;

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

    // 插图插画的处理 和label页面的处理不同
    reg = /\\begin{figure}\\includegraphics\[position=([\d,]*?)\]{}\\end{figure}/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let position = res[1].split(',');
        // let caption = ``;
        //data-src="${currentLabelImage.value.file_path}"
        //let figure = `<div id="illus-${uuid()}" data-src="${orginalImagePath}"  data-position="${position}" class="ql-illustrate"><label></label><div></div><span>${caption}</span></div>`;
        let tmp_labelInfo = {
            pos1: [position[0], position[1]],
            pos2: [position[2], position[3]]
        };
        let figure = await cropCanvasImage2Html(imageInfo.image_path, tmp_labelInfo);
        text = text.replace(find, figure);
    }

    // 混元模型输出的插图坐标(x1,y1),(x2,y2)处理
    // console.log(currentModelInfo.value);
    reg = /\(([\d]+),([\d]+)\),\(([\d]+),([\d]+)\)/gi;
    while ((res = reg.exec(text))) {
        let find = res[0];
        let x1 = (Number(res[1]) * imageInfo.image_width) / 1000; // 该逻辑参照混元github项目代码
        let y1 = (Number(res[2]) * imageInfo.image_height) / 1000;
        let x2 = (Number(res[3]) * imageInfo.image_width) / 1000;
        let y2 = (Number(res[4]) * imageInfo.image_height) / 1000;
        x1 = parseInt(x1.toString());
        y1 = parseInt(y1.toString());
        x2 = parseInt(x2.toString()) - 2; // 特殊处理防止后面裁剪时可能会超出图片范围
        y2 = parseInt(y2.toString()) - 2; // 特殊处理防止后面裁剪时可能会超出图片范围
        if (x2 <= x1 || y2 <= y1) continue;
        let tmp_labelInfo = {
            pos1: [x1, y1],
            pos2: [x2, y2]
        };
        let figure = await cropCanvasImage2Html(imageInfo.image_path, tmp_labelInfo);
        text = text.replace(find, figure);
    }

    // 几何图形 tikz/latex 直接svg预览
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
        // let tikz = `<tikz-jax class="ql-tikzjax" id="tikzjax-${uuid()}" data-latex="${encodeURIComponent(find)}" data-svg="${encodeURIComponent(svg)}" data-caption="${encodeURIComponent(caption)}"></tikz-jax>`;
        // 这里因直接预览，不需要tikz-jax标签，直接显示svg
        let svgContent = `<span style="display: inline-block;">${svg}${caption}</span>`
        text = text.replace(find, svgContent);
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
        // let tikz = `<tikz-jax class="ql-tikzjax" id="tikzjax-${uuid()}" data-latex="${encodeURIComponent(find)}" data-svg="${encodeURIComponent(svg)}" data-caption="${encodeURIComponent(caption)}"></tikz-jax>`;
        // 这里因直接预览，不需要tikz-jax标签，直接显示svg
        let svgContent = `<span style="display: inline-block;">${svg}${caption}</span>`
        text = text.replace(find, svgContent);
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

const virlist1 = ref();
const virlist2 = ref();

const isDragVirList1Scrollbar = ref(false); // 是否主动拖动左侧虚拟组件1的滚动条进行滚动的
// const isDragVirList2Scrollbar = ref(false); // 是否主动拖动右侧虚拟组件2的滚动条进行滚动的

const parseLabelId = (labelId: string) => {
    let image_index = Number(labelId.split('_')[1]);
    let label_number = Number(labelId.split('_')[3]);
    return {
        image_index,
        label_number
    };
};

// 预览格式切换
const prviewFormat = ref('markdown'); // text or markdown
const changePreviewFormat = (newFormat: string) => {
    prviewFormat.value = newFormat;
    if (newFormat === 'markdown') {
        void ensurePreviewContent();
    }
};
const currentPageHasLabels = computed(() => {
    if (!currentImageOcrList.value || !currentImageOcrList.value[currentFilePageIndex.value]) return false;
    return (currentImageOcrList.value[currentFilePageIndex.value].labelInfoList?.length || 0) > 0;
});

//双击json/text虚拟列表时，滚动到对应的canvas页
const onPreviewList2DblClick = (e: any) => {
    let ele = e.target.closest('div.ocr-html');
    if (!ele) return;
    let image_uuid = ele.id; // div.id是图片的uuid
    if (!image_uuid) return;
    let image_index = currentImageOcrList.value.findIndex((item: any) => item.image_uuid === image_uuid);
    if (image_index >= 0) {
        changeFilePage(image_index);
    }
};

const onPreviewScroll2 = (e: any) => {
    e;
    // console.log('onPreviewScroll2', e);
};

//双击markdown/html虚拟列表时，滚动并动画闪亮右侧group识别框
const onPreviewList1DblClick = (e: any) => {
    let ele = e.target.closest('div.ocr-html');
    if (!ele) return;
    let labelId = ele.id;
    let { image_index, label_number } = parseLabelId(labelId);
    console.log(labelId, image_index, label_number);
    if (!currentImageOcrList.value || !currentImageOcrList.value[image_index]) return;
    if (currentFilePageIndex.value !== image_index) {
        isDragVirList1Scrollbar.value = true; // 禁止触发virList二次滚动
        changeFilePage(image_index);
        bboxHightLightAnimation(labelId);
        setTimeout(() => {
            isDragVirList1Scrollbar.value = false;
        }, 1000);
    } else {
        bboxHightLightAnimation(labelId);
    }
    // isDragVirList1Scrollbar.value = true; // 禁止触发virList二次滚动
};

const virlist1ScrollToLable = (image_index: number, label_number?: number) => {
    delayDebounce(() => {
        let index = getImageLabelIndex(image_index, label_number || 0);
        if (index >= 0) {
            if (!isDragVirList1Scrollbar.value) {
                virlist1.value?.scrollIntoView(index);
            }
            // console.log(`virlist1.value.scrollToIndex(${index})`);
        }
    }, 200);
};

//virList1虚拟组件不论主动还是被动滚动时都会触发的回调事件
const onPreviewScroll1 = () => {
    if (isDragVirList1Scrollbar.value) {
        isDragVirList1Scrollbar.value = false;
        return;
    }
    delayDebounce(() => {
        _onPreviewScroll1();
    }, 50);
};

const _onPreviewScroll1 = () => {
    let reactiveData = virlist1.value?.getReactiveData();
    if (reactiveData) {
        let beginIndex = reactiveData.inViewBegin; // renderBegin
        let endIndex = reactiveData.inViewEnd; // renderEnd

        if (!currentImageOcrList.value || !currentImageOcrList.value[currentFilePageIndex.value]) {
            return;
        }
        if (!allLabelHtmlList.value.length || beginIndex >= allLabelHtmlList.value.length) {
            return;
        }

        let index1 = getImageLabelIndex(currentFilePageIndex.value);
        let pageLabelCount = currentImageOcrList.value[currentFilePageIndex.value].labelInfoList?.length || 0;
        let index2 = index1 + pageLabelCount;

        if (index1 < 0 || pageLabelCount === 0) {
            return;
        }

        if (index2 < beginIndex || index1 > endIndex) {
            isDragVirList1Scrollbar.value = true;
            // console.log("主动拖动右侧虚拟组件的滚动条", beginIndex, endIndex, index1, index2);
            let labelId = allLabelHtmlList.value[beginIndex].id;
            let { image_index, label_number } = parseLabelId(labelId);
            console.log(labelId, image_index, label_number);
            changeFilePage(image_index);
            requestAnimationFrame(() => {
                virlist1.value?.scrollIntoView(beginIndex);
            });
        }
    }
};

//=============================================识别预览结束===============================================
const getAllOcrContent = async (isPlainText: boolean = true) => {
    if (!currentImageOcrList.value) {
        return '';
    }
    if (!currentOcrFile.value) {
        return '';
    }

    if (currentOcrFile.value.model_ocr_count[currentModelInfo.value.model_code].waiting == true) {
        showToast('warn', t('page.common.warn'), t('page.ocrresult.pleasewait'), true);
        return '';
    }

    let ocrContent = '';
    for (let image_index = 0; image_index < currentImageOcrList.value.length; image_index++) {
        let labelInfoList = await _getImageOcrLabelInfoList(image_index);
        labelInfoList.forEach((labelInfo: any) => {
            ocrContent += isPlainText ? labelInfo.ocrText : labelInfo.editorValue + '\n\n';
        });
    }
    return ocrContent;
};

const copyToClipboard = async () => {
    showLoading();
    let ocrContent = await getAllOcrContent(true);
    hideLoading();
    if (!ocrContent) {
        return;
    }
    // 复制到剪贴板
    await navigator.clipboard.writeText(ocrContent);
    // 提示复制成功
    showToast('success', t('page.common.success'), t('page.ocrresult.copysuccess'), true);
};

const exportTxtFile = async () => {
    showLoading();
    let ocrContent = await getAllOcrContent(true);
    hideLoading();
    if (!ocrContent) {
        return;
    }
    // 导出为文本文件
    let file_name = currentOcrFile.value.file_name.split('.')[0] + '-' + currentModelName.value + '.txt';
    let blob = new Blob([ocrContent], { type: 'text/plain' });
    let url = URL.createObjectURL(blob);
    let a = document.createElement('a');
    a.href = url;
    a.download = file_name;
    a.click();
    URL.revokeObjectURL(url);
    // 提示导出成功
    showToast('success', t('page.common.success'), t('page.ocrresult.exporttxtcompleted'), true);
};

const exportHtmlFile = async () => {
    showLoading();
    let ocrContent = await getAllOcrContent(false);
    hideLoading();
    if (!ocrContent) {
        return;
    }
    // 导出为HTML文件
    let file_name = currentOcrFile.value.file_name.split('.')[0] + '-' + currentModelName.value + '.html';
    let blob = new Blob([ocrContent], { type: 'text/html' });
    let url = URL.createObjectURL(blob);
    let a = document.createElement('a');
    a.href = url;
    a.download = file_name;
    a.click();
    URL.revokeObjectURL(url);
    // 提示导出成功
    showToast('success', t('page.common.success'), t('page.ocrresult.exporthtmlcompleted'), true);
};

const sendEmail = async () => {
    showLoading();
    let ocrContent = await getAllOcrContent(false);
    hideLoading();
    if (!ocrContent) {
        return;
    }
    // 发送识别结果到邮箱
    let email = prompt(t('page.ocrresult.sendemailnote'));
    if (!email) {
        return;
    }

    let file_name = currentOcrFile.value.file_name.split('.')[0] + '-' + currentModelName.value + '.html';
    let data = {
        email: email,
        email_subject: `Kalorda OCR Result ${file_name}`,
        email_content: ocrContent
    };
    showLoading();
    let [err, res] = await promise2(ModeltestService.sendOcrResultToEmail(data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        showToast('success', t('page.common.success'), t('page.ocrresult.sendemailsuccess'), true);
    }
};

watch(
    () => currentOcrFile.value,
    async (newVal) => {
        if (newVal) {
            await getModelOcrResult(); // 先获取识别结果
            await initLoadPageToCanvas(newVal);
        }
    }
);
watch(
    () => currentModelName.value,
    async (newVal) => {
        if (newVal) {
            await getModelOcrResult();
            await initLoadPageToCanvas(currentOcrFile.value);
        }
    }
);

const clearDataList = () => {
    currentImageOcrList.value = [];
    allLabelHtmlList.value = [];
    allLabelHtmlIndexMap.clear();
    allOcrResultList.value = [];
    currentOcrFile.value = null;
    ocrFileList.value = [];
    if (fabricImageCanvas) {
        fabricImageCanvas.dispose();
    }
    if (virlist1.value) {
        virlist1.value = null;
    }
    if (virlist2.value) {
        virlist2.value = null;
    }
};

onMounted(async () => {
    document.body.style.overflow = 'hidden';
    virtualSetActiveMenu(parentRoute);
    setSplitterGutterBackgroundColor();
    bindSplitterGutterMouseOver();
    loadTikZJax();
    await getOCRConstants();
    bindImageCanvasBoxResize();
    initFabricCanvas(); // 初始化fabric画布
    initOcrFileList();
    bindImageCanvasEvent();
    sseInit();
});

onBeforeUnmount(() => {
    unbindSplitterGutterMouseOver();
    unbindImageCanvasEvent();
    unBindImageCanvasBoxResize();
    unloadTikZJax();
    sseClose();
    clearDataList();
});

onUnmounted(() => {});
</script>
<template>
    <div id="page_container" style="position: absolute; left: 0; top: 0; z-index: 1000" class="w-full h-full bg-surface-100 dark:bg-surface-900 overflow-hidden">
        <div class="flex flex-col md:flex-row gap-8 h-full">
            <div class="w-[18rem] min-w-[18rem] h-full">
                <div class="w-full flex items-center m-4 ml-8">
                    <div class="flex gap-2"><Button icon="pi pi-reply" :size="'small'" rounded class="mr-2" @click="routeBack" style="transform: rotateY(180deg)" /></div>
                    <div class="font-semibold text-xl"><i class="pi pi-longPressFlag-fill" /> {{ t('route.title.ocrresult') }}</div>
                </div>
                <div class="w-full ml-8 bg-white dark:bg-surface-800 rounded-md" style="height: calc(100vh - 70px)">
                    <div class="w-full h-full select-none">
                        <VirtualScroller
                            ref="virtualScrollerRef"
                            :items="ocrFileList"
                            :itemSize="70"
                            lazy
                            @lazy-load="onLazyLoad"
                            class="w-full h-full border border-surface-200 dark:border-surface-700 rounded-md"
                            style="scroll-behavior: smooth; overflow-x: hidden; height: 100%"
                        >
                            <template v-slot:item="{ item }">
                                <div v-if="item.file_size == 0" class="w-full h-[70px] flex items-center justify-center">
                                    <Skeleton width="90%" height="50px"></Skeleton>
                                </div>
                                <div
                                    v-if="item.file_size > 0"
                                    class="border-b cursor-pointer border-surface-200 dark:border-surface-700 h-[70px]"
                                    :class="{ 'bg-primary-300 dark:bg-primary-900': item === currentOcrFile, 'hover:bg-surface-100 dark:hover:bg-surface-700': item !== currentOcrFile }"
                                >
                                    <div class="flex gap-2 p-4" @click="setCurrentOcrFile(item, $event)">
                                        <div class="flex flex-col items-start">
                                            <!-- <img src="../../../assets/image/pdf.svg" width="32" alt="pdf"
                                                v-if="item.file_name.endsWith('.pdf')">
                                            <img src="../../../assets/image/image.svg" width="32" alt="image" v-else> -->
                                            <i class="pi pi-file-pdf pt-1" style="font-size: 1.25rem" v-if="item.file_name.endsWith('.pdf')"></i>
                                            <i class="pi pi-image pt-1" style="font-size: 1.25rem" v-else></i>
                                        </div>
                                        <div class="flex items-center justify-between w-full">
                                            <div class="flex flex-col gap-2">
                                                <div class="text-ellipsis overflow-hidden h-[18px]">
                                                    <div v-if="item.file_name.length > 20" style="word-break: break-word" v-tooltip.right="item.file_name">{{ fileNameLimit(item.file_name, 20) }}</div>
                                                    <div v-else style="word-break: break-word">{{ fileNameLimit(item.file_name, 20) }}</div>
                                                </div>
                                                <div class="flex items-center text-surface-500 dark:text-surface-400 gap-2">
                                                    <div class="flex items-center gap-2" style="font-size: 13px">
                                                        <div>{{ fileSizeStr(item.file_size) }}</div>
                                                        <div v-if="item.images_info.length > 1">{{ item.images_info.length }} pages</div>
                                                    </div>
                                                    <div class="flex items-center justify-center" v-if="item.waiting">
                                                        <i class="pi pi-spin pi-box" style="color: var(--p-primary-500)"></i>
                                                    </div>
                                                </div>
                                            </div>
                                            <div class="flex items-center justify-end text-surface-400 dark:text-surface-500 hover:text-surface-700 dark:hover:text-surface-300 pl-2">
                                                <i class="pi pi-trash" @click="removeOcrResult(item.id, $event)"></i>
                                            </div>
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
                    <Splitter class="w-full h-full" @resizestart="onSplitterResizeStart" @resizeend="onSplitterResizeEnd">
                        <SplitterPanel :size="55" :minSize="30" class="flex items-center justify-center" @focus="onSplitterPanelFocus">
                            <div class="w-full">
                                <div class="w-full rounded-t-xs flex items-center bg-surface-200 dark:bg-surface-600" style="height: 38px">
                                    <!-- 上：菜单栏 -->
                                    <div class="w-full flex items-center justify-between gap-2 ml-2 mr-2">
                                        <div class="flex-1 flex items-center justify-start text-gray-600 dark:text-gray-300">
                                            <div class="text-sm">
                                                {{ t('page.ocrresult.currentzoom') }}<span id="current_zoom">{{ currentZoom.toFixed(2) }}</span>
                                            </div>
                                        </div>
                                        <div class="flex-1 flex items-center justify-center gap-2">
                                            <div class="flex-1 flex items-center justify-center gap-2"></div>
                                            <div class="flex-1 flex items-center justify-center pr-[0.1rem]">
                                                <Popover ref="filePagePopover">
                                                    <div class="flex items-center justify-center gap-4 text-sm text-surface-500">
                                                        <div class="cursor-pointer hover:text-surface-700 dark:hover:text-surface-300" @click="changeFilePage(0)">{{ t('page.ocrresult.pagenumber', [1]) }}</div>
                                                        <div>
                                                            <Slider v-model="currentFilePageDisplayIndex" class="w-56" :min="0" :max="currentFilePageCount - 1" @slideend="changeFilePageSlideend" />
                                                            <!-- @change="changeFilePage(currentFilePageIndex)" @slideend="changeFilePageSlideend"  -->
                                                        </div>
                                                        <div class="cursor-pointer hover:text-surface-700 dark:hover:text-surface-300" @click="changeFilePage(currentFilePageCount - 1)">
                                                            {{ t('page.ocrresult.pagenumber', [currentFilePageCount]) }}
                                                        </div>
                                                    </div>
                                                </Popover>
                                                <ButtonGroup>
                                                    <Button icon="pi pi-chevron-left" :size="'small'" @click="prevPage" />
                                                    <Button :size="'small'" @click="filePageSlider">
                                                        <div style="padding-bottom: 1px; width: 60px" :style="{ 'min-width': currentFilePageCount < 10 ? '60px' : currentFilePageCount < 100 ? '70px' : currentFilePageCount < 1000 ? '80px' : '90px' }">
                                                            {{ t('page.ocrresult.pagenumber', [`${currentFilePageDisplayIndex + 1}/${currentFilePageCount}`]) }}
                                                        </div>
                                                    </Button>
                                                    <Button icon="pi pi-chevron-right" :size="'small'" @click="nextPage" />
                                                </ButtonGroup>
                                            </div>
                                            <div class="flex-1 flex items-center justify-center gap-2">
                                                <Button icon="pi pi-search-plus" :size="'small'" v-tooltip.bottom="t('page.ocrresult.zoomin')" @click="zoomIn" />
                                                <Button icon="pi pi-search-minus" :size="'small'" v-tooltip.bottom="t('page.ocrresult.zoomout')" @click="zoomOut" />
                                                <!-- <Button icon="pi pi-replay" :size="'small'" />
                                                <Button icon="pi pi-refresh" :size="'small'" /> -->
                                                <Button icon="pi pi-bullseye" :size="'small'" v-tooltip.bottom="t('page.ocrresult.reset')" @click="resetImage" />
                                                <Button
                                                    :icon="isFullscreen ? 'pi pi-window-minimize' : 'pi pi-window-maximize'"
                                                    :size="'small'"
                                                    v-tooltip.bottom="isFullscreen ? t('page.ocrresult.exitfullscreen') : t('page.ocrresult.fullscreen')"
                                                    @click="toggleFullscreen"
                                                />
                                            </div>
                                        </div>
                                        <div class="flex-1 flex items-center justify-end gap-1">
                                            <!-- right -->
                                            <div class="text-sm">
                                                <span :style="{ color: bboxHighlightVisible ? 'var(--p-primary-500)' : 'var(--p-surface-400)' }">{{ t('page.ocrresult.bboxhightlight') }}</span>
                                            </div>
                                            <ToggleSwitch v-model="bboxHighlightVisible" @change="changebboxHighlightVisible" />
                                        </div>
                                    </div>
                                </div>

                                <div class="w-full bg-surface-400 dark:bg-surface-800 relative" style="height: calc(100vh - 100px)">
                                    <!-- 中：图片 canvas 区 -->
                                    <ScanLoadingAnimate v-if="currentOcrFile" :targetFile="currentOcrFile" :targetModel="currentModelInfo" class="w-full" style="height: calc(100vh - 100px); position: absolute; top: 0; left: 0"> </ScanLoadingAnimate>
                                    <div class="w-full h-full relative">
                                        <div id="imageCanvasBox" class="w-full h-full absolute top-0 left-0 overflow-hidden">
                                            <canvas ref="imageCanvas" id="imageCanvas" />
                                        </div>
                                    </div>
                                </div>

                                <div class="w-full rounded-b-xs flex items-center bg-surface-200 dark:bg-surface-600" style="height: 38px">
                                    <!-- 下：信息栏 -->
                                    <div class="w-full flex items-center justify-between mx-2 gap-2">
                                        <!-- <div class="flex items-center text-surface-500 dark:text-surface-400">
                                            <div class="text-sm">当前缩放比例：<span id="current_zoom">{{
                                                currentZoom.toFixed(2) }}</span></div>
                                                
                                        </div> -->
                                        <div class="flex items-center justify-center flex gap-1">
                                            <div class="text-gray-600 dark:text-gray-300 text-sm mr-1">
                                                <div>{{ t('page.ocrresult.currentmodel') }}</div>
                                            </div>
                                            <div class="cursor-pointer" @click="changeModel('prev')" v-tooltip.bottom="t('page.ocrresult.prevmodel')" v-if="model_list.length > 1">
                                                <i class="pi pi-chevron-circle-left text-sm text-gray-600 dark:text-gray-300"></i>
                                            </div>
                                            <div>
                                                <Select v-if="model_list.length > 1" v-model="currentModelName" :options="model_list.map((item: any) => item.model_name)" class="w-full md:w-56" size="small">
                                                    <template #option="slotProps">
                                                        <div class="flex items-center justify-between w-full">
                                                            <div>{{ slotProps.option }}</div>
                                                            <div>
                                                                <i class="pi pi-box" :class="{ 'pi-spin': currentOcrFile && currentOcrFile.model_ocr_count[model_list[slotProps.index].model_code].waiting }" style="color: var(--p-primary-500)"></i>
                                                            </div>
                                                        </div>
                                                    </template>
                                                    <template #dropdownicon>
                                                        <i class="pi pi-box" :class="{ 'pi-spin': currentOcrFile && currentOcrFile.model_ocr_count[currentModelInfo.model_code].waiting }" style="color: var(--p-primary-500)" />
                                                    </template>
                                                </Select>

                                                <Button v-else :size="'small'" severity="secondary" v-tooltip.bottom="currentModelName">
                                                    <div class="flex items-center gap-2">
                                                        <div class="flex items-center">
                                                            <i class="pi pi-box" :class="{ 'pi-spin': currentOcrFile && currentOcrFile.model_ocr_count[currentModelInfo.model_code].waiting }" style="color: var(--p-primary-500)"></i>
                                                        </div>
                                                        <div class="flex items-center">{{ currentModelName.substring(0, 20) }}</div>
                                                    </div>
                                                </Button>
                                            </div>
                                            <div class="cursor-pointer" @click="changeModel('next')" v-tooltip.bottom="t('page.ocrresult.nextmodel')" v-if="model_list.length > 1">
                                                <i class="pi pi-chevron-circle-right text-sm text-gray-600 dark:text-gray-300"></i>
                                            </div>
                                        </div>
                                        <div class="flex items-center justify-center flex gap-4" v-if="currentOcrFile && currentOcrFile.model_ocr_count[currentModelInfo.model_code].waiting == true">
                                            <div class="text-gray-600 dark:text-gray-300 text-sm">
                                                {{ t('page.ocrresult.ocrprocess')
                                                }}<span class="font-bold text-primary">{{ currentOcrFile.model_ocr_count[currentModelInfo.model_code].completed_count + currentOcrFile.model_ocr_count[currentModelInfo.model_code].failed_count }}</span
                                                >/<span>{{ currentOcrFile.model_ocr_count[currentModelInfo.model_code].total_count }}</span> {{ t('page.ocrresult.ocrprocessunit') }}
                                            </div>
                                        </div>
                                        <div class="flex items-center justify-center flex gap-4" v-else-if="currentOcrFile && currentOcrFile.model_ocr_count[currentModelInfo.model_code].waiting == false">
                                            <div class="text-gray-600 dark:text-gray-300 text-sm" v-tooltip.top="t('page.ocrresult.durationnote')">
                                                {{ t('page.ocrresult.duration') }}<span>{{ duration_sum == 0 ? '--' : duration_sum.toFixed(2) }}</span> s
                                            </div>
                                            <div class="text-gray-600 dark:text-gray-300 text-sm">
                                                {{ t('page.ocrresult.tokenusage') }}<span>{{ token_usage_sum == 0 ? '--' : token_usage_sum }}</span> tokens
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </SplitterPanel>
                        <SplitterPanel :size="45" :minSize="30" class="flex items-center justify-center" @focus="onSplitterPanelFocus">
                            <div class="w-full">
                                <div class="w-full rounded-t-xs flex items-center bg-surface-200 dark:bg-surface-600" style="height: 38px">
                                    <!-- 上 -->
                                    <div class="w-full mx-2 flex items-center justify-center gap-2">
                                        <Button severity="primary" size="small" :icon="'pi pi-copy'" @click="copyToClipboard" v-tooltip.top="t('page.ocrresult.copytoclipboard')"> </Button>
                                        <Button severity="primary" size="small" :icon="'pi pi-file'" @click="exportTxtFile" v-tooltip.top="t('page.ocrresult.exporttxt')"> </Button>
                                        <Button severity="primary" size="small" :icon="'pi pi-file-plus'" @click="exportHtmlFile" v-tooltip.top="t('page.ocrresult.exporthtml')"> </Button>
                                        <Button severity="primary" size="small" :icon="'pi pi-envelope'" @click="sendEmail" v-tooltip.top="t('page.ocrresult.sendemail')"> </Button>
                                    </div>
                                </div>
                                <div class="w-full bg-surface-400 dark:bg-surface-800" style="height: calc(100vh - 100px); overflow: hidden">
                                    <!-- 中 -->
                                    <!-- 识别预览区 -->
                                    <div id="virListContainer" class="w-full h-[100%] overflow-x-hidden overflow-y-auto">
                                        <div class="w-full h-[100%] relative" v-if="prviewFormat === 'markdown'">
                                            <div
                                                v-if="allLabelHtmlList.length === 0"
                                                class="w-full h-[100%] flex items-center justify-center text-sm text-surface-500"
                                            >
                                            
                                            </div>
                                            <div v-else class="w-full h-[100%]">
                                                <VirtList
                                                    itemKey="id"
                                                    :list="allLabelHtmlList"
                                                    ref="virlist1"
                                                    @scroll="onPreviewScroll1"
                                                    class="w-full dark:border-surface-700 overflow-x-hidden h-[100%] p-1"
                                                    :min-size="20"
                                                    @dblclick="onPreviewList1DblClick"
                                                >
                                                    <template #default="{ itemData }">
                                                        <div class="w-full m-0 p-0 min-h-[50px]">
                                                            <div class="p-1">
                                                                <div class="ocr-html leading-6 p-2 min-h-[50px]" :id="itemData.id">
                                                                    <div class="whitespace-pre-wrap" v-html="itemData.label_html"></div>
                                                                    <div v-if="currentImageOcrList && currentImageOcrList.length > 1 && itemData.label_html" class="absolute bottom-1 right-1 p-1 text-sm text-surface-500 z-1 overflow-hidden">
                                                                        <div v-tooltip.top="t('page.ocrresult.previewpage', [itemData.image_index + 1])" v-if="itemData.label_index == 0 || itemData.label_index == itemData.label_count - 1">
                                                                            {{ t('page.ocrresult.previewpage', [itemData.image_index + 1]) }}
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </template>
                                                </VirtList>
                                            </div>
                                        </div>
                                        <div class="w-full h-[100%]" v-if="prviewFormat === 'text' && allOcrResultList.length > 0">
                                            <VirtList
                                                itemKey="id"
                                                :list="allOcrResultList"
                                                ref="virlist2"
                                                @scroll="onPreviewScroll2"
                                                class="w-full dark:border-surface-700 overflow-x-hidden h-[100%] p-1"
                                                :min-size="20"
                                                @dblclick="onPreviewList2DblClick"
                                            >
                                                <template #default="{ itemData }">
                                                    <div class="w-full m-0 p-0 min-h-[50px]">
                                                        <div class="p-1">
                                                            <div class="ocr-html leading-6 p-2 min-h-[50px]" :id="itemData.id">
                                                                <pre class="whitespace-pre-wrap" v-text="itemData.ocr_result"></pre>
                                                                <div v-if="currentImageOcrList && currentImageOcrList.length > 1 && itemData.ocr_result" class="absolute bottom-1 right-1 p-1 text-sm text-surface-500 z-1 overflow-hidden">
                                                                    <div v-tooltip.top="t('page.ocrresult.previewpage', [itemData.image_index + 1])">
                                                                        {{ t('page.ocrresult.previewpage', [itemData.image_index + 1]) }}
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        </div>
                                                    </div>
                                                </template>
                                            </VirtList>
                                        </div>
                                    </div>
                                    <!-- 识别预览区 -->
                                </div>

                                <div class="w-full rounded-b-xs flex items-center bg-surface-200 dark:bg-surface-600" style="height: 38px">
                                    <div class="w-full mx-2 flex items-center justify-center">
                                        <ButtonGroup>
                                            <Button :severity="prviewFormat === 'markdown' ? 'primary' : 'secondary'" size="small" @click="changePreviewFormat('markdown')">
                                                {{ t('page.ocrresult.markdownpreview') }}
                                            </Button>
                                            <Button :severity="prviewFormat === 'text' ? 'primary' : 'secondary'" size="small" @click="changePreviewFormat('text')">
                                                {{ t('page.ocrresult.jsonpreview') }}
                                            </Button>
                                        </ButtonGroup>
                                    </div>
                                </div>
                            </div>
                        </SplitterPanel>
                    </Splitter>
                </div>
            </div>
        </div>
        <ConfirmPopup></ConfirmPopup>
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

:deep(input) {
    margin-top: 1px;
    font-size: 13px;
    height: 2rem;
    line-height: 1rem;
    width: 2.5rem;
    background-color: var(--p-surface-500);
}

canvas {
    transform: translateZ(0);
}

/* 识别预览区样式 */
div.ocr-text {
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

div.ocr-html {
    font-size: 0.95rem;
    line-height: 1.5;
    /* color: var(--p-surface-100); */
    /* background-color: var(--p-surface-900); */
    border: 1px dashed var(--p-surface-700);
    cursor: pointer;
    overflow-x: auto;
    scrollbar-width: thin;
    position: relative;

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
