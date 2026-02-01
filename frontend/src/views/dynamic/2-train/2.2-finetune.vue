<script lang="ts">
import { RouteMeta } from '@/router/MetaType';
export const routeMeta: RouteMeta = {
    title: 'finetune',
    icon: 'pi pi-objects-column',
    keepAlive: true
};
</script>
<script setup lang="ts">
import { ref, onMounted, onActivated, onDeactivated } from 'vue';
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil';
import { FinetuneService } from '@/services/FinetuneService';
import { DatasetService } from '@/services/DatasetService';
import { promise2, objectClone, gotoRoute } from '@/utils/Common';
import { useConfirm } from 'primevue/useconfirm';
import { useI18n } from 'vue-i18n';
const confirm = useConfirm();
const { t } = useI18n();

const finetuneTaskList = ref<any[]>([]);
const first = ref(0);
const keyword = ref<any>();
const filterModelType = ref<any>();
const ocrModels = ref<any[]>([]);
const availableDatasets = ref<any[]>([]); // 存储可用的数据集列表

// 获取所有微调任务
const getAllFinetuneTasks = async (target_model: any, keyword: any, toFirstPage: boolean) => {
    let data = {
        target_model: ocrModels.value.indexOf(target_model),
        keyword: keyword,
        page: toFirstPage ? 1 : Math.floor(first.value / 10) + 1,
        page_size: 10
    };
    showLoading();
    let [err, res] = await promise2(FinetuneService.allFinetuneTasks(data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        finetuneTaskList.value = res.data.task_list || [];
        // 保存模型列表
        if (res.data.ocr_models) {
            ocrModels.value = res.data.ocr_models;
            ocrModels.value.unshift({
                code: undefined,
                name: t('page.dataset.allmodeltype'),
                desc: t('page.dataset.allmodeltype')
            });
        }

        // 为每个任务添加状态名称和样式
        finetuneTaskList.value.forEach((item: any) => {
            console.log(item);
        });

        if (toFirstPage) {
            first.value = 0;
        }
    }
};

// 清除关键词
const clearKeyword = () => {
    keyword.value = '';
    searchFinetuneTasks(true);
};

// 搜索微调任务
const searchFinetuneTasks = (toFirstPage: boolean) => {
    getAllFinetuneTasks(filterModelType.value, keyword.value, toFirstPage);
};

// 确认是否合并/刷新训练数据
const refreshTrainDataConfirm = async (task: any, event: any) => {
    confirm.require({
        target: event.currentTarget,
        message: t('page.finetune.combine_refresh_confirm'),
        icon: 'pi pi-refresh',
        rejectProps: {
            label: t('page.common.cancel'),
            severity: 'secondary',
            outlined: true
        },
        acceptProps: {
            label: t('page.common.confirm'),
            severity: 'primary'
        },
        accept: () => {
            combineData(task);
        },
        reject: () => {
            // toast.add({ severity: 'error', summary: 'Rejected', detail: 'You have rejected', life: 3000 });
        }
    });
};

const onRowSelect = (e: any) => {
    // console.log(e.originalEvent.target);
    gotoTrainingRun(e.data, e.originalEvent);
};

// 查看训练实例列表
const gotoTrainingRun = async (task: any, event: any) => {
    let train_data_path = (task && task.train_data_path) || '';
    if (!train_data_path) {
        refreshTrainDataConfirm(task, event);
        return;
    }

    gotoRoute('trainingrun', { task_id: task.id });
};

// 合并数据
const combineData = async (task: any) => {
    const previousStatus = task.data_combine_status;
    task.data_combine_status = 2;

    showLoading();
    let [err, res] = await promise2(FinetuneService.combineFinetuneData(task.id));
    hideLoading();
    if (err || !res) {
        task.data_combine_status = previousStatus;
        return;
    }
    if (res.code == 2000) {
        if (res.data?.status == 'combining') {
            showToast('info', t('page.common.success'), res.message, true);
            return;
        }
        showToast('success', t('page.common.success'), res.message || t('page.finetune.combine_success'), true);
        searchFinetuneTasks(false);
        return;
    }
    task.data_combine_status = previousStatus;
    showToast('error', t('page.common.error'), res.message || t('page.common.error'), true);
};


// 更多操作菜单
const moreMenu = ref<any>();
const moreTargetTask = ref<any>();
const more = (data: any, event: any) => {
    moreTargetTask.value = data;
    moreMenu.value.show(event);
};

const moreMenuItems = ref<any>([
    {
        label: t('page.common.edit2'),
        icon: 'pi pi-pencil',
        command: (event: any) => {
            event;
            editTask(moreTargetTask.value);
        }
    },
    {
        label: t('page.common.delete'),
        icon: 'pi pi-times',
        command: (event: any) => {
            event;
            deleteTaskConfirm();
        }
    }
]);

// 抽屉组件相关
const drawerVisible = ref(false);
const drawerHeader = ref<string>();
const drawerShowTask = ref<any>({});

// 根据模型类型获取数据集列表
const getDatasetsByModelType = async (modelType: any) => {
    if (!modelType) {
        availableDatasets.value = [];
        return;
    }

    // 查找对应的model_type数值
    let modelTypeValue = -1;
    ocrModels.value.find((item: any, index: number) => {
        if (item.code == modelType) {
            modelTypeValue = index; // model_type从1开始
        }
    });

    if (modelTypeValue === -1) {
        availableDatasets.value = [];
        return;
    }

    let data = {
        skip: 0,
        limit: 5000,
        model_type: modelTypeValue,
        keyword: ''
    };

    showLoading();
    let [err, res] = await promise2(DatasetService.allDatasets(data));
    hideLoading();

    if (err || !res || res.code !== 2000) {
        availableDatasets.value = [];
        showToast('error', t('page.common.error'), t('page.finetune.getdatasets_error'), true);
        return;
    }

    availableDatasets.value = res.data.dataset_list || [];
    drawerShowTask.value.selected_datasets = [];
    drawerShowTask.value.datasets?.forEach((item: any) => {
        if (availableDatasets.value.some((dataset: any) => dataset.id == item.id)) {
            drawerShowTask.value.selected_datasets.push(item.id);
        }
    });
};

// 添加新任务
const addNewTask = () => {
    drawerVisible.value = true;
    drawerShowTask.value = {};
    availableDatasets.value = [];
    drawerHeader.value = t('page.finetune.addtask');
};

// 编辑任务
const editTask = async (task: any) => {
    drawerVisible.value = true;
    drawerShowTask.value = objectClone(task);
    // 确保模型类型字段存在
    drawerShowTask.value.model_type = ocrModels.value[drawerShowTask.value.target_model].code;
    // 如果有模型类型，获取对应的数据集列表
    if (drawerShowTask.value.model_type) {
        await getDatasetsByModelType(drawerShowTask.value.model_type);
    }
    drawerHeader.value = t('page.finetune.edittask');
};

// 保存任务
const saveTask = async () => {
    let id = drawerShowTask.value.id;
    if (!id || id == '') {
        createTask();
    } else {
        updateTask();
    }
};

// 创建任务
const createTask = async () => {
    // 添加更多验证
    if (!drawerShowTask.value.name) {
        showToast('error', t('page.common.error'), t('page.finetune.name_required'), true);
        return;
    }

    if (!drawerShowTask.value.model_type) {
        showToast('error', t('page.common.error'), t('page.finetune.model_type_required'), true);
        return;
    }

    if (!drawerShowTask.value.selected_datasets || drawerShowTask.value.selected_datasets.length === 0) {
        showToast('error', t('page.common.error'), t('page.finetune.datasets_required'), true);
        return;
    }

    // 查找对应的model_type数值
    let target_model = -1;
    ocrModels.value.find((item: any, index: number) => {
        if (item.code == drawerShowTask.value.model_type) {
            target_model = index;
        }
    });

    let data = {
        name: drawerShowTask.value.name,
        description: drawerShowTask.value.description || '',
        target_model: target_model,
        data_format: 'Alpaca', // 默认使用Alpaca格式
        dataset_ids: drawerShowTask.value.selected_datasets || []
    };

    showLoading();
    let [err, res] = await promise2(FinetuneService.createFinetuneTask(data));
    hideLoading();

    if (err) {
        return;
    }

    if (res && res.code == 2000) {
        showToast('success', t('page.common.success'), t('page.finetune.create_success'), true);
        drawerVisible.value = false;
        getAllFinetuneTasks(undefined, undefined, true);
    } else {
        showToast('error', t('page.common.error'), res?.message || t('page.finetune.create_error'), true);
    }
};

// 更新任务
const updateTask = async () => {
    // 添加更多验证
    if (!drawerShowTask.value.name) {
        showToast('error', t('page.common.error'), t('page.finetune.name_required'), true);
        return;
    }

    if (!drawerShowTask.value.model_type) {
        showToast('error', t('page.common.error'), t('page.finetune.model_type_required'), true);
        return;
    }

    if (!drawerShowTask.value.selected_datasets || drawerShowTask.value.selected_datasets.length === 0) {
        showToast('error', t('page.common.error'), t('page.finetune.datasets_required'), true);
        return;
    }

    // 查找对应的model_type数值
    let modelTypeValue = -1;
    ocrModels.value.find((item: any, index: number) => {
        if (item.code == drawerShowTask.value.model_type) {
            modelTypeValue = index;
        }
    });

    let data = {
        id: drawerShowTask.value.id,
        name: drawerShowTask.value.name,
        description: drawerShowTask.value.description || '',
        target_model: modelTypeValue,
        data_format: 'Alpaca', // 默认使用Alpaca格式
        dataset_ids: drawerShowTask.value.selected_datasets || []
    };

    showLoading();
    let [err, res] = await promise2(FinetuneService.updateFinetuneTask(data));
    hideLoading();

    if (err) {
        return;
    }

    if (res && res.code == 2000) {
        showToast('success', t('page.common.success'), t('page.finetune.update_success'), true);
        drawerVisible.value = false;
        getAllFinetuneTasks(undefined, undefined, false);
    } else {
        showToast('error', t('page.common.error'), res?.message || t('page.finetune.update_error'), true);
    }
};

// 删除确认相关
const deleteConfirmVisible = ref(false);
const deleteConfirmText = ref('');
const deleteTaskConfirm = () => {
    deleteConfirmVisible.value = true;
};

// 删除任务
const delTask = async () => {
    if (deleteConfirmText.value != moreTargetTask.value.name.substring(0, 1)) {
        showToast('error', t('page.common.error'), t('page.finetune.del_input_error'), true);
        return false;
    }

    showLoading();
    let [err, res] = await promise2(FinetuneService.delFinetuneTask(moreTargetTask.value.id));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        showToast('success', t('page.common.success'), t('page.finetune.delete_success'), true);
        searchFinetuneTasks(false);
        deleteConfirmText.value = '';
        deleteConfirmVisible.value = false;
    }
};

const gotoDatasetPage = () => {
    gotoRoute('/train/dataset');
};

// 生命周期钩子
onMounted(async () => {
    // 页面加载时可以加载初始化数据
});

onActivated(async () => {
    await getAllFinetuneTasks(undefined, undefined, false);
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
                <div class="font-semibold text-xl"><i class="pi pi-objects-column" /> {{ t('route.title.finetune') }}</div>
                <div class="flex gap-2"></div>
            </div>

            <div>
                <DataTable @row-select="onRowSelect" v-model:first="first" :value="finetuneTaskList" dataKey="id" :paginator="true" :rows="10" :rowsPerPageOptions="[5, 10, 25]" selectionMode="single" @page="searchFinetuneTasks(false)">
                    <template #header>
                        <div class="flex flex-wrap gap-2 items-center justify-between select-none">
                            <div class="flex gap-2 w-[60%]">
                                <Select v-model="filterModelType" name="roles" :options="ocrModels" optionLabel="name" :placeholder="t('page.finetune.modeltypefilter')" fluid @change="searchFinetuneTasks(true)" style="width: 180px" />
                                <!-- <Select v-model="filterStatus" :options="statusOptions" optionLabel="label"
                                    :placeholder="t('page.finetune.filter_status')" fluid
                                    @change="searchFinetuneTasks(true)" style="width:180px" /> -->
                                <InputGroup style="width: 220px">
                                    <InputText :placeholder="t('page.finetune.search_task')" v-model="keyword" @keydown.enter="searchFinetuneTasks(true)" />
                                    <InputGroupAddon v-if="keyword && keyword.length > 0">
                                        <Button icon="pi pi-times" severity="secondary" variant="text" @click="clearKeyword" />
                                    </InputGroupAddon>
                                    <InputGroupAddon>
                                        <Button icon="pi pi-search" severity="secondary" variant="text" @click="searchFinetuneTasks(true)" />
                                    </InputGroupAddon>
                                </InputGroup>
                            </div>
                            <div class="flex gap-2">
                                <Button type="button" icon="pi pi-plus" :label="t('page.common.create')" @click="addNewTask()" />
                            </div>
                        </div>
                    </template>
                    <Column field="id" :header="t('page.common.index')" style="width: 10%">
                        <template #body="slotProps">
                            <div># {{ slotProps.data.id }}</div>
                        </template>
                    </Column>
                    <Column field="name" :header="t('page.finetune.task_name')" style="width: 20%">
                        <template #body="slotProps">
                            <div class="text-auto-ellipsis" v-tooltip.left="slotProps.data.name">{{ slotProps.data.name }}</div>
                        </template>
                    </Column>
                    <Column field="target_model" :header="t('page.finetune.target_model')">
                        <template #body="slotProps">
                            <div class="text-auto-ellipsis">
                                <Tag :value="ocrModels[slotProps.data.target_model]?.name || '--'" severity="secondary"> </Tag>
                            </div>
                        </template>
                    </Column>

                    <Column field="dataset_count" :header="t('page.finetune.dataset_count')" sortable>
                        <template #body="slotProps">
                            {{ slotProps.data.datasets.length || 0 }}
                        </template>
                    </Column>

                    <Column field="data_count" :header="t('page.finetune.data_count')" sortable>
                        <template #body="slotProps">
                            {{ (slotProps.data.train_data_count || 0) + (slotProps.data.val_data_count || 0) }}
                            <span v-if="slotProps.data.data_combine_status == 2"><i class="pi pi-spin pi-sync"></i></span>
                        </template>
                    </Column>

                    <!-- <Column field="train_data_count" :header="t('page.finetune.train_data_count')" sortable>
                        <template #body="slotProps">
                            {{ slotProps.data.train_data_count || 0 }}
                        </template>
                    </Column> -->
                    <!-- <Column field="val_data_count" :header="t('page.finetune.val_data_count')" sortable>
                        <template #body="slotProps">
                            {{ slotProps.data.val_data_count || 0 }}
                        </template>
                    </Column> -->
                    <Column field="created_at" :header="t('page.finetune.create_time')" sortable>
                        <template #body="slotProps">
                            {{ slotProps.data.created_at ? slotProps.data.created_at.split('T')[0] : '--' }}
                        </template>
                    </Column>
                    <Column field="data_last_combined" :header="t('page.finetune.update_time')" sortable>
                        <template #body="slotProps">
                            {{ slotProps.data.data_last_combined ? slotProps.data.data_last_combined.split('T')[0] : '--' }}
                        </template>
                    </Column>
                    <Column :exportable="false" style="width: 10%">
                        <template #body="slotProps">
                            <div class="w-full flex justify-end">
                                <Button
                                    icon="pi pi-send"
                                    :size="'small'"
                                    variant="outlined"
                                    rounded
                                    class="mr-2"
                                    @click="gotoTrainingRun(slotProps.data, $event)"
                                    v-tooltip.top="t('page.finetune.gototrain')"
                                    :disabled="slotProps.data.data_combine_status == 2"
                                />
                                <Button
                                    icon="pi pi-refresh"
                                    :size="'small'"
                                    variant="outlined"
                                    rounded
                                    severity="info"
                                    class="mr-2"
                                    @click="combineData(slotProps.data)"
                                    v-tooltip.top="t('page.finetune.combinedata')"
                                    :disabled="slotProps.data.data_combine_status == 2"
                                />
                                <Button
                                    icon="pi pi-ellipsis-h"
                                    :size="'small'"
                                    variant="outlined"
                                    rounded
                                    severity="secondary"
                                    @click="more(slotProps.data, $event)"
                                    v-tooltip.top="t('page.common.more')"
                                    :disabled="slotProps.data.data_combine_status == 2"
                                />
                            </div>
                        </template>
                    </Column>
                </DataTable>
                <Menu ref="moreMenu" :model="moreMenuItems" :popup="true" style="min-width: 6rem" />
                <ConfirmPopup></ConfirmPopup>
                <Dialog v-model:visible="deleteConfirmVisible" modal :header="t('page.finetune.delete_dialog_title')" :style="{ width: '25rem' }">
                    <div class="flex justify-center text-center">
                        <icon class="pi pi-exclamation-triangle" style="font-size: 3rem; color: red"></icon>
                    </div>
                    <div class="flex justify-center text-center mt-4">
                        {{ t('page.finetune.confirm_delete', [moreTargetTask.name.length > 10 ? moreTargetTask.name.substring(0, 10) + '...' : moreTargetTask.name]) }}
                    </div>
                    <div class="flex justify-center text-center mt-4 text-red-500 font-bold">
                        {{ t('page.finetune.delete_note') }}
                    </div>
                    <div class="flex items-center justify-center text-center gap-4 mt-2 mb-4">
                        {{ t('page.finetune.delete_confirm') }}
                        <InputText v-model="deleteConfirmText" name="deleteConfirmText" autocomplete="off" class="md:w-[5rem] text-lg text-center" />
                    </div>
                    <Divider />
                    <div class="flex justify-end gap-2">
                        <Button type="button" :label="t('page.common.cancel')" severity="secondary" @click="deleteConfirmVisible = false"></Button>
                        <Button type="button" :label="t('page.common.submit')" severity="danger" @click="delTask()"></Button>
                    </div>
                </Dialog>
                <Drawer v-model:visible="drawerVisible" position="right" :header="drawerHeader" class="w-full md:!w-[35%] lg:!w-[35%]">
                    <!-- 添加或编辑微调任务 -->
                    <div class="w-full">
                        <div class="pt-2 pb-2">
                            <div class="flex justify-between pb-4">
                                <label for="name" class="mr-2">{{ t('page.finetune.task_name') }}：</label>
                                <div class="text-sm text-gray-500">{{ t('page.finetune.name_limit') }}</div>
                            </div>
                            <InputText id="name" v-model="drawerShowTask.name" class="w-full" maxLength="50" spellcheck="false" />
                        </div>
                        <div class="pt-2 pb-2">
                            <div class="flex justify-between pb-4">
                                <label for="description" class="mr-2">{{ t('page.finetune.description') }}：</label>
                                <div class="text-sm text-gray-500">{{ t('page.finetune.description_note') }}</div>
                            </div>
                            <Textarea id="description" v-model="drawerShowTask.description" class="w-full leading-6" rows="5" maxlength="500" spellcheck="false" />
                        </div>

                        <div class="pt-2 pb-2">
                            <div class="flex justify-between pb-4">
                                <label for="model_type" class="mr-2">{{ t('page.finetune.model_type') }}：</label>
                                <div class="text-sm text-gray-500">{{ t('page.finetune.model_type_note') }}</div>
                            </div>
                            <Select
                                id="model_type"
                                v-model="drawerShowTask.model_type"
                                :options="ocrModels.slice(1)"
                                optionLabel="name"
                                optionValue="code"
                                :placeholder="t('page.finetune.select_model_type')"
                                fluid
                                @change="getDatasetsByModelType(drawerShowTask.model_type)"
                            >
                                <template #option="slotProps">
                                    <div class="flex items-center">
                                        <div>{{ slotProps.option.name }}（{{ slotProps.option.desc }}）</div>
                                    </div>
                                </template>
                            </Select>
                        </div>

                        <div class="pt-2 pb-2">
                            <div class="flex justify-between pb-4">
                                <label for="selected_datasets" class="mr-2">{{ t('page.finetune.select_datasets') }}：</label>
                                <div class="text-sm text-gray-500">{{ t('page.finetune.select_datasets_note') }}</div>
                            </div>
                            <MultiSelect
                                id="selected_datasets"
                                v-model="drawerShowTask.selected_datasets"
                                :options="availableDatasets"
                                :placeholder="t('page.finetune.select_datasets_placeholder')"
                                fluid
                                optionLabel="name"
                                optionValue="id"
                                :maxSelectedLabels="2"
                                :show-toggle-all="false"
                            />
                            <div v-if="availableDatasets.length === 0 && drawerShowTask.model_type" class="mt-2 text-sm">
                                <span class="text-amber-600">{{ t('page.finetune.no_model_dataset') }}</span
                                >，<span @click="gotoDatasetPage" class="cursor-pointer">{{ t('page.finetune.to_add_dataset') }}</span>
                            </div>
                        </div>

                        <div class="pt-2 pb-2">
                            <div class="flex justify-end">
                                <Button :label="t('page.common.submit')" severity="success" @click="saveTask" />
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
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
}
</style>
