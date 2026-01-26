<script lang="ts">
import { RouteMeta } from '@/router/MetaType';
export const routeMeta: RouteMeta = {
    title: 'dataview',
    icon: 'pi pi-images',
    displayMenu: 'hidden',
    keepAlive: true
};
</script>
<script setup lang="ts">
import { useLayout } from '@/layout/composables/layout';
import { showLoading, hideLoading, showToast, delCache, getCache } from '@/utils/GlobalUtil';
import { DatasetService } from '@/services/DatasetService';
import { $dom, promise2, gotoRoute, routeBack, queryParamValue, formatTime, aesEncode } from '@/utils/Common'; //  gotoRoute,
import { useConfirm } from 'primevue/useconfirm';
import { useI18n } from 'vue-i18n';
import ZipDataSetImport from './ZipDataSetImport.vue';
const confirm = useConfirm();
const { t } = useI18n();
const base = import.meta.env.VITE_APP_BASE;
const server_url = import.meta.env.VITE_API_SERVER_URL;
const aes_key = import.meta.env.VITE_APP_AES_KEY;

const { virtualSetActiveMenu } = useLayout();
const parentRoute = base + '/train/dataset';

const getUrlDatasetId = () => {
    return Number(queryParamValue(window.location.href, 'dataset_id') || '0');
};

let datasetId: number = 0;
const dataset = ref<any>();
const datasetImages = ref<any>();
const selectedImages = ref<any>([]);
const total = ref(0);
const first = ref(0); //page=first.value+1
const tableRows = ref(10); // pageSize=tableRows.value
const dataType = ref();
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
const dataTypeItems = ref<any>([
    {
        name: t('page.dataview.alldatatype'),
        value: undefined
    },
    dataType1.value,
    dataType2.value,
    dataType0.value
]);

// 数据分类统计
const dataTypeCount = ref([
    { label: dataType1.value.name, color: '#60a5fa', value: 0 },
    { label: dataType2.value.name, color: '#fbbf24', value: 0 },
    { label: dataType0.value.name, color: '#666666', value: 0 }
]);

const keyword = ref();
const dateRanges = ref<any>([]);
const datasetInfoPopover = ref<any>();
const moveImagesPopover = ref<any>();
const datasetInfo = (event: any) => {
    datasetInfoPopover.value.toggle(event);
};

const closeDatasetInfoPopover = () => {
    datasetInfoPopover.value.toggle();
};

const importVisible = ref(false);
const openImport = () => {
    importVisible.value = true;
};
const onImportDone = async () => {
    await getDataset();
    searchImages(false);
};

const clearKeyword = () => {
    keyword.value = '';
    searchImages(true);
};

const clearDateRanges = () => {
    dateRanges.value = [];
    searchImages(true);
};

const upload = () => {
    gotoRoute('/train/upload', { dataset_id: datasetId });
};

const getDataset = async () => {
    showLoading();
    let [err, res] = await promise2(DatasetService.getDataset(datasetId));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code === 2000) {
        let allOcrModels = res.data.ocr_models || [];
        dataset.value = res.data.dataset ? res.data.dataset : {};
        let datasetOcrModel = allOcrModels[dataset.value.model_type - 1];
        dataset.value.model_name = datasetOcrModel ? datasetOcrModel.name : t('page.dataview.nodatasetmodel');
        dataset.value.description = dataset.value.description ? dataset.value.description : t('page.dataview.nodatasetdesc');
        // dataset.value.ocr = dataset.value.ocr.replace('');
        dataset.value.create_at2 = dataset.value.created_at.split('T')[0];
        dataset.value.create_at = dataset.value.created_at.split('.')[0].replace('T', ' ');

        if (dataset.value.last_upload_time) {
            dataset.value.last_upload_time2 = dataset.value.last_upload_time.split('T')[0];
            dataset.value.last_upload_time = dataset.value.last_upload_time.split('.')[0].replace('T', ' ');
        } else {
            dataset.value.last_upload_time2 = '';
            dataset.value.last_upload_time = '';
        }
        // dataset.value.last_upload_time2 = dataset.value.last_upload_time.split("T")[0];
        // dataset.value.last_upload_time = dataset.value.last_upload_time.split(".")[0].replace('T', ' ');

        let dataTypeTotal = dataset.value.total_images;
        let dataType1Count = dataset.value.train_images;
        let dataType2Count = dataset.value.val_images;
        // let dataType0Count = dataTypeTotal - dataType1Count - dataType2Count;

        let value1 = 0;
        let value2 = 0;
        let value0 = 0;
        if (dataTypeTotal > 0) {
            value1 = (dataType1Count * 100.0) / dataTypeTotal;
            value2 = (dataType2Count * 100.0) / dataTypeTotal;
            // 保留两位小数
            value1 = Number(value1.toFixed(2));
            value2 = Number(value2.toFixed(2));
            value0 = 100 - (value1 + value2);
        }

        dataTypeCount.value[0].value = value1; // 注意顺序：第一个是微调数据量
        dataTypeCount.value[1].value = value2; // 第二个是验证数据量
        dataTypeCount.value[2].value = value0; // 第三个是未分类数据量
    }
};

const getDatasetImages = async (dataType: number | undefined, keyword: string | undefined, rangeDate: string | undefined, page: number = 1, pageSize: number = 10) => {
    let data: any = {
        page: page,
        page_size: pageSize
    };
    if (dataType !== undefined) {
        data.data_type = dataType;
    }
    if (keyword !== undefined && keyword.trim().length > 0) {
        data.keyword = keyword.trim();
    }
    if (rangeDate !== undefined && rangeDate.length > 0) {
        data.date_ranges = rangeDate;
    }
    showLoading();
    let [err, res] = await promise2(DatasetService.getDatasetImages(datasetId, data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code === 2000) {
        let totalVal = res.data.total;
        let images = res.data.images;
        images = res.data.images;
        let host = server_url.startsWith('http') ? server_url : window.location.origin;
        images.forEach((item: any) => {
            item.create_at2 = item.created_at.split('T')[0];
            item.create_at = item.created_at.split('.')[0].replace('T', ' ');
            item.image_url = host + item.file_path;
        });

        first.value = totalVal > 0 ? (page - 1) * pageSize : 0;

        let total_images = [];
        if (totalVal > 0) {
            total_images = new Array(totalVal).fill({});
            for (let i = 0; i < images.length; i++) {
                total_images[first.value + i] = images[i];
            }
        }

        total.value = totalVal;
        datasetImages.value = total_images;
        selectedImages.value = [];
    }
};

const searchImages = (toFirstPage: boolean) => {
    if (toFirstPage) {
        first.value = 0;
    }
    let page = first.value / tableRows.value + 1; //后端page从1开始
    let pageSize = tableRows.value;

    let dataTypeVal = dataType.value ? dataType.value.value : undefined;
    let searchVal = keyword.value ? keyword.value.trim() : undefined;
    let rangeDataVal = undefined;
    if (dateRanges.value && dateRanges.value.length > 0) {
        let startDatetime = dateRanges.value[0];
        let endDatetime = dateRanges.value[1] == null ? startDatetime : dateRanges.value[1];
        endDatetime = new Date(endDatetime.getTime() + 24 * 60 * 60 * 1000); //结束日期+1天，后端不用处理
        let start = formatTime(startDatetime).split(' ')[0];
        let end = formatTime(endDatetime).split(' ')[0];
        rangeDataVal = start + ',' + end;
    }
    getDatasetImages(dataTypeVal, searchVal, rangeDataVal, page, pageSize);
};

const onWheelEvent = (e: any) => {
    e = e || window.event;
    let flag = e.wheelDelta || e.detail;

    // 是否处于图片预览状态
    let imagePreviewToolbar = $dom('.p-image-toolbar');
    if (!imagePreviewToolbar) {
        return;
    }
    // 调用对应处理函数
    if (flag < 0) {
        // 向下滚动
        console.log('滚轮向下滚动');
        $dom('.p-image-zoom-out-button').click();
    } else {
        // 向上滚动
        console.log('滚轮向上滚动');
        $dom('.p-image-zoom-in-button').click();
    }
};

// primevue默认选全选的是所有数据，这里缩小范围，只删除当前分页中选中的数据
const get_current_selected_images = () => {
    let images = selectedImages.value;
    let current_page_images = datasetImages.value.filter((item: any) => !!item.id); //先过滤掉其他页的占位空数据
    let current_page_selected_images = current_page_images.filter((item: any) => images.indexOf(item) >= 0);
    return current_page_selected_images;
};

// 批量删除
const deleteImageBatch = async (event: any) => {
    deleteImageConfirm(get_current_selected_images(), event);
};

const deleteImageConfirm = async (images: any, event: any) => {
    let ask_message_with_number = true;
    if (!(images instanceof Array)) {
        images = [images];
        ask_message_with_number = false;
    }
    confirm.require({
        target: event.currentTarget,
        message: ask_message_with_number ? t('page.dataview.askdelete', [images.length]) : t('page.dataview.askdelete2'),
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
            delImage(images);
        },
        reject: () => {
            // toast.add({ severity: 'error', summary: 'Rejected', detail: 'You have rejected', life: 3000 });
        }
    });
};

const delImage = async (images: any) => {
    let image_ids = images.map((item: any) => item.id);

    showLoading();
    let [err, res] = await promise2(DatasetService.deleteDatasetImage(datasetId, image_ids));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code === 2000) {
        // dataset参数后端重新返回更新
        dataset.value = res.data.dataset;
        showToast('success', t('page.common.success'), t('page.dataview.delsuccess', [images.length]), true);
        searchImages(false);
    }
};

const allTargetDatasets = ref([]);
const moveTargetDataset = ref();
const movedImagesCount = ref(0);
const moveImagesToOtherDataset = async (event: any) => {
    movedImagesCount.value = get_current_selected_images().length;
    moveImagesPopover.value.toggle(event);
    let [err, res] = await promise2(DatasetService.allDatasets({ model_type: dataset.value.model_type }));
    if (err) {
        return;
    }
    if (res && res.code === 2000) {
        // dataset参数后端重新返回更新
        let datasetList = res.data.dataset_list ? res.data.dataset_list : [];
        let targetDatasets = datasetList.map((item: any) => {
            return {
                label: item.name,
                value: item.id
            };
        });
        // 过滤掉当前数据集
        targetDatasets = targetDatasets.filter((item: any) => item.value != datasetId);
        allTargetDatasets.value = targetDatasets;
    }
};

const closeMoveImagesPopover = () => {
    moveImagesPopover.value.toggle();
};

const moveSelectedImages = async () => {
    let target_dataset_id = moveTargetDataset.value;
    if (!target_dataset_id) {
        showToast('error', t('page.common.error'), t('page.dataview.notargetdataset'), true);
        return;
    }
    if (target_dataset_id == datasetId) {
        showToast('error', t('page.common.error'), t('page.dataview.notmovetoself'), true);
        return;
    }

    let images = get_current_selected_images();
    let image_ids = images.map((item: any) => item.id);
    let data = {
        target_dataset_id: target_dataset_id,
        image_ids: image_ids
    };
    showLoading();
    let [err, res] = await promise2(DatasetService.moveDatasetImage(datasetId, data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code === 2000) {
        // dataset参数后端重新返回更新
        dataset.value = res.data.dataset;
        showToast('success', t('page.common.success'), t('page.dataview.movesuccess', [images.length]), true);
        moveImagesPopover.value.toggle();
        searchImages(false);
    }
};

// 数据显示表格的翻页触发事件
const onTablePageChange = (e: any) => {
    // let toFirstVal = e.first;
    // let toPage = e.page;
    // let toRows = e.rows;
    datasetImages.value = undefined;
    tableRows.value = e.rows;
    searchImages(false);
};

// 滚动条位置记忆
const scrollY = ref(0);
// 转到图片标注页
const labelImage = (image: any) => {
    document.body.style.overflow = 'hidden';
    scrollY.value = window.scrollY;
    let query_data = {
        dataset_id: datasetId,
        image_id: image.id,
        data_type: dataType.value,
        keyword: keyword.value,
        dateRanges: dateRanges.value
    };
    let query = encodeURIComponent(aesEncode(JSON.stringify(query_data), aes_key));
    gotoRoute('/train/label', { query: query });
};

// onMounted(async () => {
//     virtualSetActiveMenu(parentRoute);
//     await getDataset();
//     await getDatasetImages(undefined, undefined, undefined, 1, tableRows.value);
//     window.addEventListener('wheel', onWheelEvent);
// });

onActivated(async () => {
    document.body.style.overflow = ''; // 不要设为auto
    virtualSetActiveMenu(parentRoute);
    // 附属数据每次都重置
    allTargetDatasets.value = [];
    moveTargetDataset.value = undefined;
    movedImagesCount.value = 0;
    selectedImages.value = [];

    // 更新一下，避免keepalive缓存
    let _datasetId = getUrlDatasetId();
    let refresh = datasetId != _datasetId;
    if (refresh) {
        first.value = 0;
    }
    // 检查是否有上传页面预埋的刷新标记
    let key = 'refresh-dataset-' + _datasetId;
    let refreshTime = getCache(key);
    if (refreshTime) {
        refresh = true;
        first.value = 0; // 上传后刷新，强制显示第一页看到最新上传的数据
        delCache(key);
    }
    if (refresh) {
        // 数据集id改变了，需要重新获取数据
        datasetId = _datasetId;
        // 滚动条位置重置
        scrollY.value = 0;
        dataset.value = undefined;
        datasetImages.value = undefined;
        let page = first.value / tableRows.value + 1;
        console.log('强制刷新页面page=', page);
        await getDataset();
        await getDatasetImages(undefined, undefined, undefined, page, tableRows.value);
    }

    window.addEventListener('wheel', onWheelEvent);
    if (scrollY.value) {
        window.scrollTo(0, scrollY.value);
        // window.scrollTo({
        //     top: scrollY.value,
        //     behavior: 'smooth'
        // });
    }
});

// 页面开启keepalive时，弹出类组件都要手动关闭防止残留到下一个页面，非keepalive页面不用
onDeactivated(() => {
    window.removeEventListener('wheel', onWheelEvent);
    selectedImages.value = [];
    confirm.close();
    $dom('body')?.click(); // 关闭popover可以用这个途径
    $dom('.p-image-mask')?.click(); // 关闭图片预览
});

// onUnmounted(() => {
//     window.removeEventListener('wheel', onWheelEvent);
// });
</script>
<template>
    <div>
        <div class="card h-full" v-if="dataset">
            <div class="flex justify-between mb-1">
                <div class="flex items-center">
                    <div class="flex gap-2"><Button icon="pi pi-reply" :size="'small'" rounded class="mr-2" @click="routeBack()" style="transform: rotateY(180deg)" /></div>
                    <div class="font-semibold text-xl">
                        <i class="pi pi-database" /> {{ t('route.title.dataset') }} <i class="pi pi-chevron-right" /> {{ t('page.dataview.title') }} "{{ dataset.name.length > 20 ? dataset.name.substring(0, 20) + '...' : dataset.name }}"
                        <span v-tooltip.top="t('page.dataview.datasetinfo')" @click="datasetInfo">&nbsp;&nbsp;<i class="pi pi-chevron-circle-down cursor-pointer"></i></span>
                    </div>
                </div>
                <div class="flex items-center gap-2"></div>
            </div>

            <!-- 查看数据集信息 弹出Popover -->
            <Popover ref="datasetInfoPopover" :style="{ 'box-shadow': '5px 10px 10px rgba(0,0,0,0.5)' }">
                <div class="flex flex-col gap-4 w-[30rem]">
                    <div>
                        <div class="flex justify-between items-center">
                            <div>
                                <h5 class="font-medium block pt-2">{{ dataset.name }}</h5>
                            </div>
                            <div class="pb-3"><Button icon="pi pi-times" :size="'small'" severity="secondary" variant="text" rounded class="mr-2" @click="closeDatasetInfoPopover" /></div>
                        </div>
                        <Textarea v-model="dataset.description" rows="5" class="w-full" readonly style="resize: none" />
                    </div>
                    <div>
                        <MeterGroup :value="dataTypeCount" />
                    </div>
                    <div class="text-sm text-surface-500 flex gap-2 justify-left">
                        <Tag severity="info" :value="t('page.dataview.datacount') + '：' + dataset.total_images"></Tag>
                        <Tag severity="danger" :value="t('page.dataview.tokencount') + '：' + dataset.total_tokens"> </Tag>
                        <Tag severity="warn" :value="dataset.model_name"></Tag>
                    </div>
                    <div class="text-sm text-surface-500 flex gap-2 justify-left">
                        <Tag severity="secondary" :value="t('page.dataview.createtime') + '：' + dataset.create_at2" v-tooltip.top="dataset.create_at"> </Tag>
                        <Tag severity="secondary" :value="t('page.dataview.lastuploadtime') + '：' + dataset.last_upload_time2" v-tooltip.top="dataset.last_upload_time"></Tag>
                    </div>
                </div>
            </Popover>

            <!-- 移动数据到其他数据集 显示全部数据集 弹出Popover -->
            <Popover ref="moveImagesPopover">
                <div class="flex flex-col w-[26rem]">
                    <div class="flex justify-between items-center">
                        <div class="font-medium block text-lg">
                            <b><i class="pi pi-arrow-right-arrow-left"></i> {{ t('page.dataview.moveimagestitle') }}</b>
                        </div>
                        <div><Button icon="pi pi-times" :size="'small'" severity="secondary" variant="text" rounded @click="closeMoveImagesPopover" /></div>
                    </div>
                    <div class="text-sm text-surface-500 mt-2 mb-2">{{ t('page.dataview.moveimagenote', [movedImagesCount]) }}</div>
                    <div>
                        <Select
                            v-model="moveTargetDataset"
                            :options="allTargetDatasets"
                            optionLabel="label"
                            optionValue="value"
                            :virtualScrollerOptions="{ itemSize: 40 }"
                            :emptyMessage="t('page.dataview.emptydataset')"
                            :placeholder="t('page.dataview.targetdatasetholder')"
                            class="w-full"
                        >
                            <template #dropdownicon>
                                <i class="pi pi-database" />
                            </template>
                        </Select>
                    </div>
                    <div class="flex gap-2 justify-end mt-4">
                        <Button severity="secondary" size="small" :label="t('page.common.cancel')" @click="closeMoveImagesPopover" />
                        <Button severity="primary" size="small" :label="t('page.common.submit')" @click="moveSelectedImages" />
                    </div>
                </div>
            </Popover>

            <div v-if="datasetImages">
                <DataTable
                    ref="dt"
                    v-model:selection="selectedImages"
                    :value="datasetImages"
                    dataKey="id"
                    :paginator="true"
                    v-model:first="first"
                    :rows="tableRows"
                    @page="onTablePageChange($event)"
                    selectionMode="multiple"
                    paginatorTemplate="FirstPageLink PrevPageLink PageLinks NextPageLink LastPageLink CurrentPageReport RowsPerPageDropdown"
                    :rowsPerPageOptions="[5, 10, 25, 50]"
                    currentPageReportTemplate="Showing {first} to {last} of {totalRecords} products"
                >
                    <template #header>
                        <div class="flex flex-wrap gap-2 items-center justify-between select-none">
                            <div class="flex gap-2 w-[60%]">
                                <Select v-model="dataType" name="roles" :options="dataTypeItems" optionLabel="name" :placeholder="t('page.dataview.datatypefilter')" fluid @change="searchImages(true)" style="width: 180px" />
                                <InputGroup style="width: 280px">
                                    <InputText :placeholder="t('page.dataview.searchdata')" v-model="keyword" @keydown.enter="searchImages(true)" showClear />
                                    <InputGroupAddon v-if="keyword && keyword.length > 0">
                                        <Button icon="pi pi-times" severity="secondary" variant="text" @click="clearKeyword" />
                                    </InputGroupAddon>
                                    <InputGroupAddon>
                                        <Button icon="pi pi-search" severity="secondary" variant="text" @click="searchImages(true)" />
                                    </InputGroupAddon>
                                </InputGroup>
                                <InputGroup style="width: 280px">
                                    <DatePicker :placeholder="t('page.dataview.searchrangdate')" v-model="dateRanges" selectionMode="range" :manualInput="false" dateFormat="yy/mm/dd" />

                                    <InputGroupAddon v-if="dateRanges && dateRanges.length > 0">
                                        <Button icon="pi pi-times" severity="secondary" variant="text" @click="clearDateRanges" />
                                    </InputGroupAddon>

                                    <InputGroupAddon>
                                        <Button icon="pi pi-calendar" severity="secondary" variant="text" @click="searchImages(true)" />
                                    </InputGroupAddon>
                                </InputGroup>
                            </div>
                            <div class="flex gap-2">
                                <Button type="button" severity="secondary" icon="pi pi-cloud-upload" :label="t('page.common.upload')" @click="upload()" />
                                <Button type="button" severity="secondary" icon="pi pi-file-arrow-up" :label="t('page.common.import')" @click="openImport()" />
                                <Button type="button" severity="warn" icon="pi pi-arrow-right-arrow-left" :label="t('page.common.move')" v-if="selectedImages.length > 0" @click="moveImagesToOtherDataset($event)" />
                                <Button type="button" severity="danger" icon="pi pi-times" :label="t('page.common.delete')" v-if="selectedImages.length > 0" @click="deleteImageBatch($event)" />
                            </div>
                        </div>
                    </template>

                    <Column field="id" :header="t('page.common.index')" style="width: 80px" sortable>
                        <template #body="slotProps"># {{ slotProps.data.id }}</template>
                    </Column>
                    <Column :header="t('page.dataview.image')" class="select-none w-[16%]">
                        <template #body="slotProps">
                            <Image :preview="true" role="presentation" :alt="slotProps.data.file_name" :src="slotProps.data.image_url" width="160" class="max-h-64" />
                        </template>
                    </Column>
                    <Column header="" style="width: 10px"></Column>
                    <Column :header="t('page.dataview.ocr_label')" class="select-none">
                        <template #body="slotProps">
                            <Textarea :value="slotProps.data.is_preocr_completed ? slotProps.data.ocr_label : ''" :placeholder="slotProps.data.is_preocr_completed ? '' : '预处理尚未完成，请耐心等待...'" rows="10" class="w-full ocr_label" readonly />
                        </template>
                    </Column>
                    <Column header="" style="width: 10px"></Column>
                    <Column :header="t('page.dataview.data_info')" style="width: 10%; min-width: 100px" class="select-none">
                        <template #body="slotProps">
                            <div class="text-sm text-surface-500">{{ t('page.dataview.data_type') }}：</div>
                            <div class="mt-1">
                                <Tag :severity="'secondary'" :value="dataType0.name" v-if="slotProps.data.train_data_type === dataType0.value"></Tag>
                                <Tag :severity="'primary'" :value="dataType1.name" v-if="slotProps.data.train_data_type === dataType1.value"></Tag>
                                <Tag :severity="'info'" :value="dataType2.name" v-if="slotProps.data.train_data_type === dataType2.value"></Tag>
                            </div>
                            <div class="mt-2">
                                <div class="text-sm text-surface-500">{{ t('page.dataview.tokens') }}：</div>
                                <div class="mt-1" style="font-size: 0.9rem">{{ slotProps.data.tokens }} tokens</div>
                            </div>
                            <!-- v-tooltip.top="fileSizeStr(slotProps.data.file_size)"  -->
                            <div class="mt-2">
                                <div class="text-sm text-surface-500">{{ t('page.dataview.image_size') }}：</div>
                                <div class="mt-1" style="font-size: 0.9rem">{{ slotProps.data.width }} x {{ slotProps.data.height }}</div>
                            </div>
                            <!-- v-tooltip.top="slotProps.data.create_at"  -->
                            <div class="mt-2">
                                <div class="text-sm text-surface-500">{{ t('page.dataview.upload_date') }}：</div>
                                <div class="mt-1" style="font-size: 0.9rem">{{ slotProps.data.create_at2 }}</div>
                            </div>
                        </template>
                    </Column>
                    <Column header="" :exportable="false" style="width: 8%">
                        <template #body="slotProps">
                            <div class="flex">
                                <!-- 预处理完成的才可以点击进去标注 -->
                                <Button v-if="slotProps.data.is_preocr_completed" icon="pi pi-pencil" :size="'small'" variant="outlined" rounded class="mr-2" @click="labelImage(slotProps.data)" />
                                <Button v-else icon="pi pi-pencil" :size="'small'" variant="outlined" rounded class="mr-2" disabled />
                                <Button icon="pi pi-times" :size="'small'" variant="outlined" rounded severity="danger" @click="deleteImageConfirm(slotProps.data, $event)" />
                            </div>
                        </template>
                    </Column>
                    <Column selectionMode="multiple" style="width: 1rem" :exportable="false"></Column>
                    <!-- <template #paginatorstart>
                        <Button type="button" icon="pi pi-refresh" text />
                    </template>
                    <template #paginatorend>
                        <Button type="button" icon="pi pi-download" text />
                    </template> -->
                </DataTable>
                <ConfirmPopup></ConfirmPopup>
                <ScrollTop />
            </div>
        </div>
        <ZipDataSetImport v-model:visible="importVisible" :datasetId="datasetId" :datasetName="dataset?.name" @imported="onImportDone" />
    </div>
</template>
<style scoped>
.ocr_label {
    font-size: 0.9rem;
    line-height: 1.5rem;
    scrollbar-width: thin;
    overflow-x: hidden;
    background-color: var(--p-surface-color);
    resize: none;
    border: 2px dashed var(--p-surface-400);
    /* border-radius: 0.75rem; */
}
</style>
