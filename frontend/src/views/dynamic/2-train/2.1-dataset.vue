<script lang="ts">
import { RouteMeta } from '@/router/MetaType';
export const routeMeta: RouteMeta = {
    title: 'dataset',
    icon: 'pi pi-database',
    keepAlive: true
};
</script>
<script setup lang="ts">
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil';
import { DatasetService } from '@/services/DatasetService';
import { promise2, objectClone, gotoRoute } from '@/utils/Common';
// import { useConfirm } from "primevue/useconfirm";
import { useI18n } from 'vue-i18n';
// const confirm = useConfirm();
const { t } = useI18n();

const datasetList = ref<any>();
const first = ref(0);
const ocrModels = ref<any>();
const preOcrStatus = ref<any>();
const keyword = ref<any>();
const filterModelType = ref<any>();

const getAllDatasets = async (modelType: any, keyword: any, toFirstPage: boolean) => {
    let data = {
        model_type: modelType,
        keyword: keyword
    };
    showLoading();
    let [err, res] = await promise2(DatasetService.allDatasets(data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        datasetList.value = res.data.dataset_list ? res.data.dataset_list : [];
        ocrModels.value = res.data.ocr_models ? res.data.ocr_models : [];
        ocrModels.value.unshift({
            code: undefined,
            name: t('page.dataset.allmodeltype'),
            desc: t('page.dataset.allmodeltype')
        });
        preOcrStatus.value = res.data.pre_ocr_status ? res.data.pre_ocr_status : [];
        datasetList.value.forEach((item: any) => {
            let model = ocrModels.value[item.model_type];
            item.model_type_name = model ? model.name : '-';
            let preOcrStatu = preOcrStatus.value[item.pre_ocr_status - 1];
            item.pre_ocr_status_name = preOcrStatu ? preOcrStatu.name : '-';
            switch (preOcrStatu?.code) {
                case 'not_start':
                    item.pre_ocr_status_icon = 'pi pi-pause-circle';
                    item.pre_ocr_status_severity = 'secondary';
                    break;
                case 'preprocessing':
                    item.pre_ocr_status_icon = 'pi pi-spin pi-spinner';
                    item.pre_ocr_status_severity = 'info';
                    break;
                case 'completed':
                    item.pre_ocr_status_icon = 'pi pi-check';
                    item.pre_ocr_status_severity = 'success';
                    break;
                case 'failed':
                    item.pre_ocr_status_icon = 'pi pi-times';
                    item.pre_ocr_status_severity = 'danger';
                    break;
            }
            if (toFirstPage) {
                first.value = 0;
            }
        });
    }
};

const clearKeyword = () => {
    keyword.value = '';
    searchDatasets(true);
};

const searchDatasets = (toFirstPage: boolean) => {
    let model_type = undefined;
    if (filterModelType.value) {
        ocrModels.value.find((item: any, index: number) => {
            if (item.code == filterModelType.value.code) {
                model_type = index;
            }
        });
    }
    getAllDatasets(model_type, keyword.value, toFirstPage);
};

const onRowSelect = (e: any) => {
    dataView(e.data);
    // gotoRoute('dataview', { dataset_id: e.data.id });
};

// 页面详情
const dataView = (dataset: any) => {
    gotoRoute('dataview', { dataset_id: dataset.id });
};

// 上传页面
const upload = (dataset: any) => {
    gotoRoute('upload', { dataset_id: dataset.id });
};

const moreMenu = ref<any>();
const moreTargetDataset = ref<any>();
const more = (data: any, event: any) => {
    moreTargetDataset.value = data;
    moreMenu.value.show(event);
};
const moreMenuItems = ref<any>([
    {
        label: t('page.common.edit2'),
        icon: 'pi pi-pencil',
        command: (event: any) => {
            console.log(event);
            editDataset(moreTargetDataset.value);
        }
    },
    {
        label: t('page.common.delete'),
        icon: 'pi pi-times',
        command: (event: any) => {
            console.log(event);
            deleteDatasetConfirm();
        }
    }
]);

const drawerVisible = ref(false);
const drawerHeader = ref<string>();
const drawerShowDataset = ref<any>();

const addNewDataset = () => {
    drawerVisible.value = true;
    drawerShowDataset.value = {};
    drawerHeader.value = t('page.dataset.adddataset');
};

const editDataset = (dataset: any) => {
    drawerVisible.value = true;
    drawerShowDataset.value = objectClone(dataset);
    drawerShowDataset.value.model_type2 = ocrModels.value[drawerShowDataset.value.model_type]; //重新建一个字段出来给select赋值
    drawerHeader.value = t('page.dataset.editdataset');
};

const saveDataset = async () => {
    let id = drawerShowDataset.value.id;
    if (!id || id == '') {
        createDataset();
    } else {
        updateDataset();
    }
};

const createDataset = async () => {
    if (!drawerShowDataset.value.model_type2) {
        showToast('error', t('page.common.error'), t('page.dataset.modeltypeerror'), true);
        return;
    }

    let data = {
        name: drawerShowDataset.value.name,
        description: drawerShowDataset.value.description,
        model_type: ocrModels.value.indexOf(drawerShowDataset.value.model_type2) // 这里传给后端的是返数字
    };
    showLoading();
    let [err, res] = await promise2(DatasetService.createDataset(data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        drawerVisible.value = false;
        getAllDatasets(undefined, undefined, true);
    }
};

const updateDataset = async () => {
    let data = {
        id: drawerShowDataset.value.id,
        name: drawerShowDataset.value.name,
        description: drawerShowDataset.value.description
    };
    showLoading();
    let [err, res] = await promise2(DatasetService.updateDataset(data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        drawerVisible.value = false;
        getAllDatasets(undefined, undefined, false);
    }
};

const deleteConfirmVisible = ref(false);
const deleteConfirmText = ref('');
const deleteDatasetConfirm = () => {
    deleteConfirmVisible.value = true;
};
const delDataset = async (dataset: any) => {
    if (deleteConfirmText.value != moreTargetDataset.value.name.substring(0, 1)) {
        showToast('error', t('page.common.error'), t('page.dataset.delinputerror'), true);
        return false;
    }

    showLoading();
    let [err, res] = await promise2(DatasetService.delDataset(dataset.id));
    if (err) {
        hideLoading();
        return;
    }
    if (res && res.code == 2000) {
        showToast('success', t('page.common.success'), t('page.dataset.delsuccess'), true);
        searchDatasets(false);
        deleteConfirmText.value = '';
        deleteConfirmVisible.value = false;
    }
    hideLoading();
};

onMounted(async () => {
    // await getAllDatasets(undefined, undefined, 0);
});

onActivated(async () => {
    await getAllDatasets(undefined, undefined, false);
});

onDeactivated(() => {
    drawerVisible.value = false;
    deleteConfirmVisible.value = false;
});
</script>
<template>
    <div>
        <div class="card h-full">
            <div class="flex justify-between mb-1">
                <div class="font-semibold text-xl"><i class="pi pi-database" /> {{ t('route.title.dataset') }}</div>
                <div class="flex gap-2"></div>
            </div>

            <div>
                <DataTable @row-select="onRowSelect" v-model:first="first" ref="dt" :value="datasetList" dataKey="id" :paginator="true" :rows="10" :rowsPerPageOptions="[5, 10, 25]" selectionMode="single">
                    <template #header>
                        <div class="flex flex-wrap gap-2 items-center justify-between select-none">
                            <div class="flex gap-2 w-[60%]">
                                <Select v-model="filterModelType" name="roles" :options="ocrModels" optionLabel="name" :placeholder="t('page.dataset.modeltypefilter')" fluid @change="searchDatasets(true)" style="width: 180px" />
                                <InputGroup style="width: 220px">
                                    <InputText :placeholder="t('page.dataset.searchdataset')" v-model="keyword" @keydown.enter="searchDatasets(true)" />
                                    <InputGroupAddon v-if="keyword && keyword.length > 0">
                                        <Button icon="pi pi-times" severity="secondary" variant="text" @click="clearKeyword" />
                                    </InputGroupAddon>
                                    <InputGroupAddon>
                                        <Button icon="pi pi-search" severity="secondary" variant="text" @click="searchDatasets(true)" />
                                    </InputGroupAddon>
                                </InputGroup>
                            </div>
                            <div class="flex gap-2">
                                <Button type="button" icon="pi pi-plus" :label="t('page.common.create')" @click="addNewDataset()" />
                            </div>
                        </div>
                    </template>
                    <Column field="id" :header="t('page.common.index')" style="width: 10%">
                        <template #body="slotProps">
                            <div># {{ slotProps.data.id }}</div>
                        </template>
                    </Column>
                    <Column field="name" :header="t('page.dataset.name')" style="width: 20%">
                        <template #body="slotProps">
                            <div class="text-auto-ellipsis" v-tooltip.left="slotProps.data.name">{{ slotProps.data.name }}</div>
                        </template>
                    </Column>
                    <Column field="model_type" :header="t('page.dataset.modeltype')">
                        <template #body="slotProps">
                            <Tag :value="slotProps.data.model_type_name" severity="secondary"></Tag>
                        </template>
                    </Column>
                    <Column field="pre_ocr_status" :header="t('page.dataset.preocrstatus')">
                        <template #body="slotProps">
                            <Tag :value="slotProps.data.pre_ocr_status_name" :icon="slotProps.data.pre_ocr_status_icon" :severity="slotProps.data.pre_ocr_status_severity"></Tag>
                        </template>
                    </Column>
                    <Column field="total_images" :header="t('page.dataset.totalimages')" sortable>
                        <template #body="slotProps">
                            {{ slotProps.data.total_images }}
                        </template>
                    </Column>

                    <Column field="created_at" :header="t('page.dataset.createtime')" sortable>
                        <template #body="slotProps">
                            {{ slotProps.data.created_at.split('T')[0] }}
                        </template>
                    </Column>
                    <Column field="login_count" :header="t('page.dataset.lastuploadtime')" sortable>
                        <template #body="slotProps">
                            {{ slotProps.data.last_upload_time ? slotProps.data.last_upload_time.split('T')[0] : '--' }}
                        </template>
                    </Column>
                    <Column :exportable="false" style="width: 10%">
                        <template #body="slotProps">
                            <div class="w-full flex justify-end">
                                <Button icon="pi pi-eye" :size="'small'" variant="outlined" rounded class="mr-2" v-tooltip.top="t('page.dataset.viewdata')" @click="dataView(slotProps.data)" />
                                <Button icon="pi pi-cloud-upload" :size="'small'" variant="outlined" rounded v-tooltip.top="t('page.dataset.upload')" severity="info" class="mr-2" @click="upload(slotProps.data)" />
                                <Button icon="pi pi-ellipsis-h" :size="'small'" variant="outlined" rounded v-tooltip.top="t('page.common.more')" severity="secondary" @click="more(slotProps.data, $event)" />
                            </div>
                        </template>
                    </Column>
                </DataTable>
                <Menu ref="moreMenu" :model="moreMenuItems" :popup="true" style="min-width: 6rem" />
                <Dialog v-model:visible="deleteConfirmVisible" modal :header="t('page.dataset.deldialogheader')" :style="{ width: '25rem' }">
                    <div class="flex justify-center text-center">
                        <icon class="pi pi-exclamation-triangle" style="font-size: 3rem; color: red"></icon>
                    </div>
                    <div class="flex justify-center text-center mt-4">
                        {{ t('page.dataset.askdelete', [moreTargetDataset.name.length > 10 ? moreTargetDataset.name.substring(0, 10) + '...' : moreTargetDataset.name]) }}
                    </div>
                    <div class="flex justify-center text-center mt-4 text-red-500 font-bold">
                        {{ t('page.dataset.deletenote') }}
                    </div>
                    <div class="flex items-center justify-center text-center gap-4 mt-2 mb-4">
                        {{ t('page.dataset.delconfirm') }}
                        <InputText v-model="deleteConfirmText" name="deleteConfirmText" autocomplete="off" class="md:w-[5rem] text-lg text-center" />
                    </div>
                    <Divider />
                    <div class="flex justify-end gap-2">
                        <Button type="button" :label="t('page.common.cancel')" severity="secondary" @click="deleteConfirmVisible = false"></Button>
                        <Button type="button" :label="t('page.common.submit')" severity="danger" @click="delDataset(moreTargetDataset)"></Button>
                    </div>
                </Dialog>
                <Drawer v-model:visible="drawerVisible" position="right" :header="drawerHeader" class="w-full md:!w-[35%] lg:!w-[35%]">
                    <!-- 添加新数据集或修改数据集 -->
                    <div class="w-full">
                        <div class="pt-2 pb-2">
                            <div class="flex justify-between pb-4">
                                <label for="title_input" class="mr-2">{{ t('page.dataset.name') }}：</label>
                                <div class="text-sm text-gray-500">{{ t('page.dataset.namelimit') }}</div>
                            </div>
                            <InputText id="name" v-model="drawerShowDataset.name" class="w-full" maxLength="50" spellcheck="false" />
                        </div>
                        <div class="pt-2 pb-2">
                            <div class="flex justify-between pb-4">
                                <label for="title_input" class="mr-2">{{ t('page.dataset.desc') }}：</label>
                                <div class="text-sm text-gray-500">{{ t('page.dataset.descnote') }}</div>
                            </div>
                            <Textarea id="desc" v-model="drawerShowDataset.description" class="w-full leading-6" rows="5" maxlength="500" spellcheck="false" />
                        </div>
                        <div class="pt-2 pb-2">
                            <div class="flex justify-between pb-4">
                                <label for="title_input" class="mr-2">{{ t('page.dataset.modeltype') }}：</label>
                                <div class="text-sm text-gray-500">{{ t('page.dataset.modeltypenote') }}</div>
                            </div>
                            <Select v-model="drawerShowDataset.model_type2" :options="ocrModels.slice(1)" :disabled="drawerShowDataset.id" optionLabel="name" :placeholder="t('page.dataset.selectmodeltype')" class="w-full">
                                <template #option="slotProps">
                                    <div class="flex items-center">
                                        <div>{{ slotProps.option.name }}（{{ slotProps.option.desc }}）</div>
                                    </div>
                                </template>
                            </Select>
                        </div>

                        <div class="pt-2 pb-2">
                            <div class="flex justify-end">
                                <Button :label="t('page.common.submit')" severity="success" @click="saveDataset" />
                            </div>
                        </div>
                    </div>
                </Drawer>
            </div>
        </div>
    </div>
</template>
<style scoped>
.text-auto-ellipsis {
    white-space: nowrap;
    /* 不换行 */
    overflow: hidden;
    /* 隐藏超出的内容 */
    text-overflow: ellipsis;
    /* 用省略号表示被隐藏的部分 */
    max-width: 200px;
    /* 设置最大宽度以限制文本的显示长度 */
}
</style>
