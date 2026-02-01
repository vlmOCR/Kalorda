<script lang="ts">
import { RouteMeta } from '@/router/MetaType';
export const routeMeta: RouteMeta = {
    title: 'trainingrun',
    icon: 'pi pi-box',
    displayMenu: 'hidden'
};
</script>
<script setup lang="ts">
import { useLayout } from '@/layout/composables/layout';
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil';
import { FinetuneService } from '@/services/FinetuneService';
import { $dom, promise2, gotoRoute, downloadFile, routeBack, queryParamValue, debounce } from '@/utils/Common'; //  gotoRoute, , formatTime, aesEncode
import { useConfirm } from 'primevue/useconfirm';
import { useI18n } from 'vue-i18n';
import { getUserId } from '@/utils/Token';
import { SSEClient } from '@/utils/SSEUtil';
const confirm = useConfirm();
const TrainParamsView = defineAsyncComponent(() => import('./TrainParamsView.vue'));
const TrainStatusView = defineAsyncComponent(() => import('./TrainStatusView.vue'));
const TrainRealLogView = defineAsyncComponent(() => import('./TrainRealLogView.vue'));
const TrainRealChartView = defineAsyncComponent(() => import('./TrainRealChartView.vue'));
const TrainSummaryView = defineAsyncComponent(() => import('./TrainSummaryView.vue'));
const { t } = useI18n();
const base = import.meta.env.VITE_APP_BASE;
const server_url = import.meta.env.VITE_API_SERVER_URL;
// const aes_key = import.meta.env.VITE_APP_AES_KEY;

const { virtualSetActiveMenu } = useLayout();
const parentRoute = base + '/train/finetune';

const getTaskId = () => {
    return Number(queryParamValue(window.location.href, 'task_id') || '0');
};
const getRunId = () => {
    return Number(queryParamValue(window.location.href, 'run_id') || '0');
};
const getTabValue = () => {
    return Number(queryParamValue(window.location.href, 'tab') || '0');
};

const ocrModels = ref<any>([]);
const trainingStatuses = ref<any>([]);
const currentTask = ref<any>();
const trainingRunList = ref<any>([]);
let not_start_status = 1;
let running_status = 4;
let completed_status = 6;
const currentTrainingRun = ref<any>();
const curTrainingRunLogs = ref<any>([]);
let logIdSet = new Set<string>();

// 当前的Tab组件值
const tabValue = ref('0'); // 超参数设置=0 训练日志=1 数据图表=2 结果模型=3

// 任务详情弹窗
const taskInfoPopover = ref<any>();
const taskInfo = (event: any) => {
    taskInfoPopover.value.toggle(event);
};
const closeTaskInfoPopover = () => {
    taskInfoPopover.value.toggle();
};

// 跳转数据集详情
const gotoDataset = (dataset_id: number) => {
    gotoRoute('/train/dataview', { dataset_id: dataset_id });
};

// http途径获取的日志处理 注：日志分两部分加载1、已经生成的日志通过http请求一次性获取，2、刚刚生成的日志通过sse推送实时获取append
const getTrainingRunLog = async () => {
    let task_id = getTaskId();
    let run_id = currentTrainingRun.value.id;
    if (task_id <= 0 || run_id <= 0) {
        return;
    }

    // 未到运行状态直接返无日志，不需要发请求获取
    if (currentTrainingRun.value.status < running_status) {
        curTrainingRunLogs.value = [];
        logIdSet = new Set();
        return;
    }

    showLoading();
    let [err, res] = await promise2(FinetuneService.getTrainingRunLog(task_id, run_id));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let task_id = res.data.task_id;
        let run_id = res.data.run_id;
        // 防止回来点击不同的训练实例，返回时不是当前的训练实例的日志不添加
        if (task_id != currentTask.value.id || run_id != currentTrainingRun.value.id) {
            return;
        }
        let logs = parseJSON(res.data.log_content);
        logIdSet = new Set(logs.map((item: any) => item.msg_id));
        const mergedLogs = [...logs];
        for (const item of curTrainingRunLogs.value) {
            if (!logIdSet.has(item.msg_id)) {
                mergedLogs.push(item);
                logIdSet.add(item.msg_id);
            }
        }
        curTrainingRunLogs.value = mergedLogs;
    }
};

// 获取全部训练实例
const initLoad = async () => {
    let task_id = getTaskId(); // 任务id
    let run_id = getRunId(); // 初始需要选中的训练实例id
    if (task_id > 0) {
        let data1 = {
            task_ids: [task_id],
            page: 1,
            page_size: 1
        };
        let data2 = {
            page: 1,
            page_size: 100
        };
        showLoading();
        let [err1, res1] = await promise2(FinetuneService.allFinetuneTasks(data1));
        let [err2, res2] = await promise2(FinetuneService.allTrainingRuns(task_id, data2));
        hideLoading();
        if (err1 || err2) {
            return;
        }
        if (res1 && res1.code == 2000 && res2 && res2.code == 2000) {
            ocrModels.value = res1.data.ocr_models;
            trainingStatuses.value = res2.data.training_statuses;
            not_start_status = trainingStatuses.value.find((item: any) => item.code == 'not_start')?.value || 1;
            currentTask.value = res1.data.task_list?.[0] || {};
            currentTask.value.description = currentTask.value.description ? currentTask.value.description : t('page.trainingrun.notaskdesc');
            trainingRunList.value = res2.data.run_list || [];

            if (trainingRunList.value.length > 0) {
                let last_item = trainingRunList.value[trainingRunList.value.length - 1];
                let select_item = last_item; // 设置默认的训练实例
                if (run_id > 0) {
                    select_item = trainingRunList.value.find((item: any) => item.id == run_id) || last_item;
                    console.log('select_item=', select_item);
                }
                switchTrainingRun(select_item);
                nextTick(() => {
                    $dom(`#training-run-list-container`).scrollTop = $dom(`#training-run-item-${select_item.id}`).offsetTop - 6;
                });
                // 默认显示的tab视图
                if (getTabValue() > 0) {
                    tabValue.value = getTabValue().toString();
                }
            }
        }
    }
};

const trainChartViewRef = ref<any>(); // 图表显示组件
const trainLogViewRef = ref<any>(); // 日志显示组件
const trainParamsViewRef1 = ref<any>(); // add
const trainParamsViewRef2 = ref<any>(); // edit
const paramsDialogVisible = ref(false);
const logSearch = (show: boolean) => {
    if (trainLogViewRef.value) {
        trainLogViewRef.value.logSearch(show);
    }
};

// 添加训练实例超参数设置
const addTrainingRun = () => {
    paramsDialogVisible.value = true;
};

// 添加训练实例超参数设置提交
const createTrainingRun = async () => {
    let task_id = getTaskId();
    if (task_id <= 0) {
        return;
    }
    // 校验参数
    let params = trainParamsViewRef1.value.getTrainParams();
    if (!params) {
        return;
    }
    let data = {
        task_id: task_id,
        ...params
    };

    console.log('createTrainingRun=', data);

    showLoading();
    let [err, res] = await promise2(FinetuneService.createTrainingRun(data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        paramsDialogVisible.value = false;
        await initLoad();
    }
};

const forceScrollLogToBottom = ref(true);
// 切换训练实例时
const switchTrainingRun = (item: any) => {
    // 阻止双击
    if (currentTrainingRun.value && currentTrainingRun.value.id == item.id) {
        return;
    }
    forceScrollLogToBottom.value = true;
    currentTrainingRun.value = item;
    curTrainingRunLogs.value = [];
    logIdSet = new Set();
    logSearch(false);
    getTrainingRunLog();
};

const onTabChanged = (value: any) => {
    logSearch(false); // 切换到非日志tab时，日志搜索框都隐藏
    // 切换到日志视图时
    if (value == '1') {
        // 切换实例后查看日志需要滚动到最底部
        if (forceScrollLogToBottom.value) {
            trainLogViewRef.value.scrollToBottom();
            forceScrollLogToBottom.value = false;
        } else if (currentTrainingRun.value.status != completed_status) {
            // 已完成状态下不用每次都滚动到最底部，不然对比查看图表和日志会不方便
            trainLogViewRef.value.scrollToBottom();
        }
    }
};

const deleteTrainingRun = async (item: any, e: any) => {
    e.stopPropagation();
    confirm.require({
        message: t('page.trainingrun.confirmdelete', [item.run_name]),
        header: t('page.common.confirm'),
        icon: 'pi pi-exclamation-triangle',
        rejectProps: {
            label: t('page.common.cancel'),
            severity: 'secondary',
            outlined: true
        },
        acceptProps: {
            label: t('page.common.delete'),
            severity: 'danger'
        },
        accept: async () => {
            showLoading();
            let [err, res] = await promise2(FinetuneService.delTrainingRun(item.id));
            hideLoading();
            if (err) {
                return;
            }
            if (res && res.code == 2000) {
                if (currentTrainingRun.value.id == item.id) {
                    // 删除的是当前选中的实例
                    let index = trainingRunList.value.findIndex((i: any) => i.id == item.id);
                    let nextTrainingRun = trainingRunList.value[index + 1] || trainingRunList.value[index - 1];
                    // 自动切换到最近的一个实例
                    if (nextTrainingRun) {
                        switchTrainingRun(nextTrainingRun);
                    } else {
                        currentTrainingRun.value = undefined;
                        curTrainingRunLogs.value = [];
                        logIdSet = new Set();
                    }
                }
                trainingRunList.value = trainingRunList.value.filter((i: any) => i.id != item.id);
                showToast('success', t('page.common.success'), t('page.trainingrun.deletesuccess'), true);
            }
        },
        reject: () => {}
    });

    hidePopupDialog();
};

// 抑制多余弹窗不能关闭这里手动隐藏它（貌似confirmDialog用的方式不对导致）
const hidePopupDialog = () => {
    setTimeout(() => {
        document.querySelectorAll('div.p-confirmpopup').forEach((item: any) => {
            item.style.display = 'none';
        });
    }, 10);
};

// 保存修改的超参数
const saveHyperparameters = async () => {
    // 还需要判断是否可以修改
    // 如果已开始且没有结束，则不允许修改当前超参数
    if (currentTrainingRun.value.status > not_start_status) {
        showToast('warn', t('page.common.warn'), t('page.trainingrun.cantedit'), true);
        return;
    }
    let task_id = getTaskId();
    if (task_id <= 0) {
        return;
    }
    // 校验参数
    let params = trainParamsViewRef2.value.getTrainParams();
    if (!params) {
        return;
    }
    let data = {
        task_id: task_id,
        ...params
    };
    showLoading();
    let [err, res] = await promise2(FinetuneService.updateTrainingRun(currentTrainingRun.value.id, data));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let result = res.data || {};
        trainingRunList.value = trainingRunList.value.map((item: any) => {
            if (item.id == result.id) {
                currentTrainingRun.value = result;
                return result;
            }
            return item;
        });
        showToast('success', t('page.common.success'), t('page.trainingrun.editsuccess'), true);
    }
};

// 切换大视图
const bigViewMode = ref(false);
const toggleBigView = () => {
    let pageContainer = document.getElementById('page_container') as HTMLDivElement;
    bigViewMode.value = !bigViewMode.value;
    if (bigViewMode.value) {
        pageContainer.setAttribute('style', 'display:none;position:absolute;left:0;top:0;z-index:1000;');
    } else {
        pageContainer.setAttribute('style', 'display:none;position:flex;');
    }
    setTimeout(() => {
        pageContainer.style.display = 'block';
    }, 100);
};

// 下载模型
const downloadModel = async (e: any) => {
    debounce(_downloadModel, e, 1000);
};

const _downloadModel = async () => {
    if (!currentTrainingRun.value) {
        return;
    }
    let run_id = currentTrainingRun.value.id;
    if (run_id <= 0) {
        return;
    }
    if (!currentTrainingRun.value.model_output_path) {
        showToast('warn', t('page.common.warn'), t('page.trainingrun.nomodeldownload'), true);
        return;
    }
    showLoading();
    FinetuneService.downloadCheckpointFile(
        run_id,
        (blob: any) => {
            let filename = currentTask.value.name + '-' + currentTrainingRun.value.run_name + '.zip';
            downloadFile(filename, blob);
            hideLoading();
        },
        () => {
            showToast('warn', t('page.common.error'), t('page.trainingrun.modeldownloaderror'), true);
            hideLoading();
        }
    );
};

// 等待中任务获取其排队位置信息
const getWaitingRank = async () => {
    if (!currentTrainingRun.value) {
        return;
    }
    let run_id = currentTrainingRun.value.id;
    if (run_id <= 0) {
        return;
    }
    let [err, res] = await promise2(FinetuneService.getWaitingRank(run_id));
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let result = res.data || {};
        return result;
    }
};
// 训练步骤控制
const trainingRunAction = (action: string) => {
    if (action == 'start') {
        // 启动训练
        confirm.require({
            message: t('page.trainingrun.confirmstart'),
            header: t('page.common.confirm'),
            icon: 'pi pi-question-circle',
            rejectProps: {
                label: t('page.common.cancel'),
                severity: 'secondary',
                outlined: true
            },
            acceptProps: {
                label: t('page.common.submit'),
                severity: 'info'
            },
            accept: () => {
                startTrainingRun();
            },
            reject: () => {}
        });
    } else if (action == 'reset') {
        // 重置为未开始训练的状态

        confirm.require({
            message: t('page.trainingrun.confirmreset'),
            header: t('page.common.confirm'),
            icon: 'pi pi-question-circle',
            rejectProps: {
                label: t('page.common.cancel'),
                severity: 'secondary',
                outlined: true
            },
            acceptProps: {
                label: t('page.common.submit'),
                severity: 'info'
            },
            accept: () => {
                resetTrainingRun();
            },
            reject: () => {}
        });
    } else if (action == 'cancel') {
        // 中止运行中的训练

        confirm.require({
            message: t('page.trainingrun.confirmcancel'),
            header: t('page.common.confirm'),
            icon: 'pi pi-exclamation-triangle',
            rejectProps: {
                label: t('page.common.cancel'),
                severity: 'secondary',
                outlined: true
            },
            acceptProps: {
                label: t('page.common.submit'),
                severity: 'danger'
            },
            accept: () => {
                cancelTrainingRun();
            },
            reject: () => {}
        });
    }
    // 等待中 的popover提示弹窗不能关闭这里手动隐藏它
    hidePopupDialog();
};

const startTrainingRun = async () => {
    // 启动训练
    showLoading();
    let [err, res] = await promise2(FinetuneService.startTrainingRun(currentTrainingRun.value.id));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let run_id = res.data.training_run_id;
        let new_status = res.data.status;
        if (currentTrainingRun.value.id == run_id) {
            currentTrainingRun.value.status = new_status;
        }
    }
};
const resetTrainingRun = async () => {
    // 重置为未开始训练的状态
    showLoading();
    let [err, res] = await promise2(FinetuneService.resetTrainingRun(currentTrainingRun.value.id));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let run_id = res.data.training_run_id;
        let new_status = res.data.status;
        if (currentTrainingRun.value.id == run_id) {
            currentTrainingRun.value.status = new_status;
            curTrainingRunLogs.value = []; // 重置训练日志
        }
    }
};
const cancelTrainingRun = async () => {
    // 中止运行中的训练
    showLoading();
    let [err, res] = await promise2(FinetuneService.cancelTrainingRun(currentTrainingRun.value.id));
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code == 2000) {
        let run_id = res.data.training_run_id;
        let new_status = res.data.status;
        if (currentTrainingRun.value.id == run_id) {
            currentTrainingRun.value.status = new_status;
        }
    }
};

const parseJSON = (str: string) => {
    str = str.replace(/nan/gi, '0');
    return JSON.parse(str);
};

let sseClientId = '';
const sseClient = ref<SSEClient>();
const sseInit = () => {
    let host = server_url.startsWith('http') ? server_url : window.location.origin;
    sseClientId = `client_${getUserId()}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    let sseUrl = `${host}/api/stream/trainrun/${sseClientId}/${currentTask.value.id}`;
    sseClient.value = new SSEClient({
        clientId: sseClientId,
        url: sseUrl,
        reconnectAttempts: 5,
        reconnectInterval: 3000,
        onMessage: (message: any) => {
            // console.log('收到SSE消息:', message);
            // sse途径获取的日志处理
            if (message.type && message.type == 'trainlog') {
                let data = parseJSON(message.data);
                let task_id = data.task_id;
                let run_id = data.run_id;
                if (currentTask.value.id == task_id && currentTrainingRun.value.id == run_id) {
                    let recv_log = { msg_id: message.msg_id, data: data };
                    if (logIdSet.has(recv_log.msg_id)) {
                        // http????????????????????????sse???????????????????????????????????????
                        return;
                    }
                    logIdSet.add(recv_log.msg_id);
                    // curTrainingRunLogs.value = [...curTrainingRunLogs.value, recv_log];
                    curTrainingRunLogs.value.push(recv_log);
                }
            }

            // 训练状态变化处理
            if (message.type && message.type == 'trainstatus') {
                let data = parseJSON(message.data);
                let run_id = data.run_id;
                let new_status = data.status;
                trainingRunList.value.forEach((item: any) => {
                    if (item.id == run_id) {
                        item.status = new_status;
                    }
                });
                if (currentTrainingRun.value.id == run_id) {
                    currentTrainingRun.value.status = new_status;
                }
            }

            // 训练结束处理
            if (message.type && message.type == 'trainend') {
                let data = parseJSON(message.data);
                let run_id = data.id;
                let index = trainingRunList.value.findIndex((item: any) => item.id == run_id);
                if (index != -1) {
                    trainingRunList.value[index] = data;
                    currentTrainingRun.value = data;
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

onMounted(async () => {
    virtualSetActiveMenu(parentRoute);
    await initLoad();
    sseInit();
});

onBeforeUnmount(() => {
    sseClose();
    if (bigViewMode.value) {
        // 退出返回时如果是大视图模式，需要将页面容器的position设置恢复为flex，避免回退后列表页面看起来不完整
        let pageContainer = document.getElementById('page_container') as HTMLDivElement;
        pageContainer.setAttribute('style', 'position:flex;');
        // toggleBigView(); // 该方法里面有个定时器可能会不及执行完
    }
});

const test = () => {
    FinetuneService.sendMessageToClient(Number(getUserId()), {
        data: 'test'
    });
};
</script>
<template>
    <div id="page_container" class="w-full h-full">
        <div class="card h-full" v-if="currentTask">
            <div class="flex justify-between select-none">
                <div class="flex items-center">
                    <div class="flex gap-2"><Button icon="pi pi-reply" :size="'small'" rounded class="mr-2" @click="routeBack()" style="transform: rotateY(180deg)" /></div>
                    <div class="font-semibold text-xl">
                        <i class="pi pi-objects-column" /> {{ t('route.title.finetune') }} <i class="pi pi-chevron-right" /> {{ t('page.trainingrun.title') }} "{{
                            currentTask.name.length > 20 ? currentTask.name.substring(0, 20) + '...' : currentTask.name
                        }}" <span v-tooltip.top="t('page.trainingrun.taskinfo')" @click="taskInfo">&nbsp;&nbsp;<i class="pi pi-chevron-circle-down cursor-pointer"></i></span>
                    </div>
                </div>
                <div class="flex items-center gap-2 text-sm text-gray-500">
                    {{ t('page.trainingrun.targetmodel') }} <Button :label="ocrModels[currentTask.target_model - 1].name" :severity="'secondary'" :size="'small'" rounded class="mr-2" @click="test" />
                </div>
            </div>

            <Popover ref="taskInfoPopover" :style="{ 'box-shadow': '5px 10px 10px rgba(0,0,0,0.5)' }">
                <div class="flex flex-col gap-4 w-[30rem]">
                    <div>
                        <div class="flex justify-between items-center">
                            <div>
                                <h5 class="font-medium block pt-2">{{ currentTask.name }}</h5>
                            </div>
                            <div class="pb-3"><Button icon="pi pi-times" :size="'small'" severity="secondary" variant="text" rounded class="mr-2" @click="closeTaskInfoPopover" /></div>
                        </div>
                        <Textarea v-model="currentTask.description" rows="5" class="w-full" readonly style="resize: none" />
                    </div>
                    <div class="text-sm text-surface-500 flex gap-2 justify-left">
                        <Tag severity="info" :value="t('page.trainingrun.dataset_count') + '：' + currentTask.datasets.length"></Tag>
                        <Tag severity="info" :value="t('page.trainingrun.train_data_count') + '：' + currentTask.train_data_count"></Tag>
                        <Tag severity="info" :value="t('page.trainingrun.val_data_count') + '：' + currentTask.val_data_count"></Tag>
                    </div>

                    <div class="m-2 max-h-[100px] overflow-x-hidden" style="scrollbar-width: thin">
                        <div v-for="(dataset, index) in currentTask.datasets" :key="index">
                            <div class="flex items-center gap-2" :class="{ 'pt-4': parseInt(index.toString()) > 0 }">
                                <div>
                                    <i class="pi pi-database" />
                                </div>
                                <div class="overflow-ellipsis overflow-hidden whitespace-nowrap cursor-pointer" @click="gotoDataset(dataset.id)">
                                    {{ dataset.name }}
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </Popover>
            <Dialog v-model:visible="paramsDialogVisible" modal :style="{ width: '60rem' }">
                <template #header>
                    <div class="flex items-center justify-between">
                        <div class="text-lg font-bold">{{ t('page.trainingrun.addtrainrun') }} / <i class="pi pi-cog"></i> {{ t('page.trainingrun.hyperparams') }}</div>
                    </div>
                </template>
                <TrainParamsView ref="trainParamsViewRef1" :training_run="{}" :new_model_name="ocrModels[currentTask.target_model - 1].name + '_sft_model_' + (trainingRunList ? trainingRunList.length + 1 : 1)" />
                <div class="flex justify-end gap-2">
                    <Button type="button" label="Cancel" severity="secondary" @click="paramsDialogVisible = false"></Button>
                    <Button type="button" label="Save" @click="createTrainingRun"></Button>
                </div>
            </Dialog>
            <ConfirmDialog></ConfirmDialog>

            <div class="h-[1rem]"></div>

            <Splitter :class="{ 'h-[calc(70vh)]': !bigViewMode, 'h-[calc(85vh)]': bigViewMode }">
                <SplitterPanel class="flex flex-col p-2" :size="22" :minSize="16">
                    <div class="mt-2 mb-0 ml-4 h-[2rem] flex items-center justify-between">
                        <div class="flex items-center gap-1 text-surface-400">
                            {{ t('page.trainingrun.trainruncount', [trainingRunList.length]) }}
                        </div>
                        <div class="min-w-[5rem]">
                            <Button :label="t('page.common.add')" icon="pi pi-plus" severity="primary" size="small" rounded class="mr-2" @click="addTrainingRun()" />
                        </div>
                    </div>
                    <Divider />
                    <div id="training-run-list-container" class="overflow-auto px-2 relative" :class="{ 'h-[calc(70vh-6rem)]': !bigViewMode, 'h-[calc(85vh)]': bigViewMode }">
                        <div class="h-full">
                            <PanelMenu :model="trainingRunList" class="w-full h-full">
                                <template #item="{ item }">
                                    <div
                                        v-ripple
                                        class="flex items-center justify-between cursor-pointer group p-3 rounded text-md select-none"
                                        :class="{ 'bg-primary-500 text-surface-100': item === currentTrainingRun, 'text-surface-400': item !== currentTrainingRun }"
                                        @click="switchTrainingRun(item)"
                                        :id="`training-run-item-${item.id}`"
                                    >
                                        <div class="flex items-center">
                                            <Badge severity="primary" v-if="item === currentTrainingRun"></Badge>
                                            <Badge severity="secondary" v-else></Badge>
                                            <div class="pl-2">{{ item.run_name }}</div>
                                        </div>
                                        <div class="flex items-center gap-2">
                                            <div class="text-sm min-w-[3rem]">{{ trainingStatuses.find((status: any) => status.value === item.status)?.name }}</div>
                                            <i class="pi pi-times-circle text-surface-500 group-hover:text-inherit" @click="deleteTrainingRun(item, $event)" v-tooltip.right="t('page.common.delete') + ' ' + item.run_name"></i>
                                        </div>
                                    </div>
                                </template>
                            </PanelMenu>
                        </div>
                    </div>
                </SplitterPanel>
                <SplitterPanel class="flex flex-col p-2" :size="78" :minSize="68">
                    <div v-if="!currentTrainingRun">
                        <div class="flex items-center justify-center">
                            <div class="text-center mt-4" v-if="trainingRunList.length === 0">
                                <i class="pi pi-info-circle text-surface-500 mb-2" />
                                <p class="text-md font-medium text-surface-500">
                                    {{ t('page.trainingrun.notrainrun') }} <a href="#" @click="addTrainingRun()" class="text-primary">{{ t('page.common.add') }}</a> {{ t('page.trainingrun.addnow') }}
                                </p>
                            </div>
                            <div class="text-center mt-4" v-else>
                                <i class="pi pi-info-circle text-surface-500 mb-2" />
                                <p class="text-md font-medium text-surface-500">{{ t('page.trainingrun.selecttrainrun') }}</p>
                            </div>
                        </div>
                    </div>
                    <div v-if="currentTrainingRun">
                        <div>
                            <div class="mt-2 mb-0 ml-4 h-[2rem]">
                                <TrainStatusView :trainingStatuses="trainingStatuses" :status="currentTrainingRun.status" :getWaitingRank="getWaitingRank" @trainingRunAction="trainingRunAction" />
                            </div>
                            <Divider />
                        </div>
                        <div class="relative">
                            <!-- tabs侧边菜单 -->
                            <div class="absolute top-3 right-2 z-100">
                                <div class="flex items-center gap-2">
                                    <div class="text-sm text-surface-500">{{ t('page.trainingrun.current') }} {{ currentTrainingRun.run_name }}</div>
                                    <div class="flex gap-2">
                                        <!-- 超参数设置修改保存 -->
                                        <button class="bg-transparent border-0 inline-flex flex-col gap-2 cursor-pointer" v-if="tabValue === '0'" @click="saveHyperparameters()">
                                            <span
                                                :class="[
                                                    'rounded-full border-2 w-7 h-7 inline-flex items-center justify-center ',
                                                    {
                                                        'bg-primary text-primary-contrast border-primary': currentTrainingRun.status === not_start_status,
                                                        'text-surface-400  bg-surface-300 border-surface-300 dark:text-surface-400 dark:bg-surface-500 dark:border-surface-500': currentTrainingRun.status !== not_start_status
                                                    }
                                                ]"
                                                v-tooltip.left="t('page.trainingrun.hyperparamssave') + (currentTrainingRun.status === not_start_status ? '' : t('page.trainingrun.hyperparamssave_note'))"
                                            >
                                                <i class="pi pi-save" size="small" style="font-size: 0.9rem" />
                                            </span>
                                        </button>

                                        <!-- 日志搜索 -->
                                        <button class="bg-transparent border-0 inline-flex flex-col gap-2 cursor-pointer" v-if="tabValue === '1'" @click="logSearch(true)">
                                            <span
                                                :class="[
                                                    'rounded-full border-2 w-7 h-7 inline-flex items-center justify-center ',
                                                    {
                                                        'bg-primary text-primary-contrast border-primary': curTrainingRunLogs.length > 0,
                                                        'bg-surface-500 text-surface-400 border-surface-500': curTrainingRunLogs.length == 0
                                                    }
                                                ]"
                                                v-tooltip.left="t('page.trainingrun.logsearch')"
                                            >
                                                <i class="pi pi-search" size="small" style="font-size: 0.85rem" />
                                            </span>
                                        </button>

                                        <!-- 下载模型 -->
                                        <button class="bg-transparent border-0 inline-flex flex-col gap-2 cursor-pointer" v-if="tabValue == '3'" @click="downloadModel($event)">
                                            <span :class="['rounded-full border-2 w-7 h-7 inline-flex items-center justify-center bg-primary text-primary-contrast border-primary']" v-tooltip.left="t('page.trainingrun.modeldownload')">
                                                <i class="pi pi-download" size="small" style="font-size: 0.9rem" />
                                            </span>
                                        </button>
                                        <!-- 大窗口查看 -->
                                        <button class="bg-transparent border-0 inline-flex flex-col gap-2 cursor-pointer" @click="toggleBigView">
                                            <span
                                                :class="['rounded-full border-2 w-7 h-7 inline-flex items-center justify-center bg-primary text-primary-contrast border-primary']"
                                                v-tooltip.left="!bigViewMode ? t('page.trainingrun.bigviewmode') : t('page.trainingrun.defaultviewmode')"
                                            >
                                                <i
                                                    :class="['pi', { ' pi-arrow-up-right-and-arrow-down-left-from-center': !bigViewMode, 'pi-arrow-down-left-and-arrow-up-right-to-center': bigViewMode }]"
                                                    size="small"
                                                    style="font-size: 0.9rem; transform: rotate(90deg)"
                                                />
                                            </span>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <Tabs v-model:value="tabValue" @update:value="onTabChanged">
                                <TabList>
                                    <Tab value="0"><i class="pi pi-cog"></i> {{ t('page.trainingrun.hyperparams') }} </Tab>
                                    <Tab value="1"><i class="pi pi-print"></i> {{ t('page.trainingrun.trainlog') }} </Tab>
                                    <Tab value="2"><i class="pi pi-chart-line"></i> {{ t('page.trainingrun.datachart') }}</Tab>
                                    <Tab value="3"><i class="pi pi-box"></i> {{ t('page.trainingrun.modelfile') }}</Tab>
                                </TabList>
                                <TabPanels style="margin: 0; padding: 0">
                                    <TabPanel value="0" class="m-4 p-0">
                                        <TrainParamsView ref="trainParamsViewRef2" :training_run="currentTrainingRun" />
                                    </TabPanel>
                                    <TabPanel value="1" class="m-1 mx-0 p-0" :class="{ 'h-[calc(70vh-9rem)]': !bigViewMode, 'h-[calc(70vh-1.4rem)]': bigViewMode }">
                                        <TrainRealLogView ref="trainLogViewRef" :logs="curTrainingRunLogs" :loading="currentTrainingRun.status == running_status" />
                                    </TabPanel>
                                    <TabPanel value="2" class="m-1 mx-0 p-0" :class="{ 'h-[calc(70vh-9rem)]': !bigViewMode, 'h-[calc(70vh-1.4rem)]': bigViewMode }">
                                        <TrainRealChartView ref="trainChartViewRef" :logs="curTrainingRunLogs" :useAnimation="currentTrainingRun.status == running_status" />
                                    </TabPanel>
                                    <TabPanel value="3" class="m-1 mx-0 p-0" :class="{ 'h-[calc(70vh-9rem)]': !bigViewMode, 'h-[calc(70vh-1.4rem)]': bigViewMode }">
                                        <TrainSummaryView ref="trainSummaryViewRef" :training_run="currentTrainingRun" :completed="currentTrainingRun.status == completed_status" />
                                    </TabPanel>
                                </TabPanels>
                            </Tabs>
                        </div>
                    </div>
                </SplitterPanel>
            </Splitter>
        </div>
    </div>
</template>
<style scoped></style>
