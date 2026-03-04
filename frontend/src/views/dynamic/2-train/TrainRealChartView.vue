<script setup lang="ts">
import { shallowRef, triggerRef } from 'vue';
import { delayDebounce } from '@/utils/Common';
import { useI18n } from 'vue-i18n';
const { t } = useI18n();
const VueChartJSLineXY = defineAsyncComponent(() => import('./VueChartJSLineXY.vue'));
const VueDataUIWheel = defineAsyncComponent(() => import('./VueDataUIWheel.vue'));

const props = defineProps({
    logs: {
        type: Array<object>,
        default: () => []
    },
    useAnimation: {
        type: Boolean,
        default: false
    }
});

interface TrainEpoch {
    id: string;
    loss: number;
    token_acc: number;
    grad_norm: number;
    learning_rate: number;
    epoch: number;
    global_step: number;
    train_speed: number;
}
interface EvalEpoch {
    id: string;
    eval_loss: number;
    eval_token_acc: number;
    epoch: number;
    global_step: number;
    train_speed: number;
}

interface Summary {
    train_runtime: number;
    train_samples_per_second: number;
    train_steps_per_second: number;
    train_loss: number;
    total_epoch: number;
    max_steps: number;
    percentage: number;
    elapsed_time: string;
    remaining_time: string;
}

const trainEpochsRaw: Array<TrainEpoch> = [];
const evalEpochsRaw: Array<EvalEpoch> = [];
const train_epochs = shallowRef<Array<TrainEpoch>>(trainEpochsRaw);
const eval_epochs = shallowRef<Array<EvalEpoch>>(evalEpochsRaw);
// 训练的总结性日志
const summary = ref<Summary>({
    train_runtime: 0,
    train_samples_per_second: 0,
    train_steps_per_second: 0,
    train_loss: 0,
    total_epoch: 0,
    max_steps: 0,
    percentage: 0,
    elapsed_time: '',
    remaining_time: ''
});

// 评估的总结性日志和普通的eval日志格式是一样的
const eval_summary = ref<EvalEpoch>({
    id: '',
    eval_loss: 0,
    eval_token_acc: 0,
    epoch: 0,
    global_step: 0,
    train_speed: 0
});

const lastLogsRef = ref<Array<any> | null>(null);
const lastProcessedIndex = ref(0);
const seenTrainMsgIds = new Set<string>();
const seenEvalMsgIds = new Set<string>();
const evalGlobalStepSet = new Set<number>();
const latestGlobalStep = ref(0);

const trainLossSeriesRaw: number[] = [0];
const trainGnormSeriesRaw: number[] = [0];
const trainLrateSeriesRaw: number[] = [0];
const trainTokenAccSeriesRaw: number[] = [0];
const trainTrainSpeedSeriesRaw: number[] = [0];

const evalLossSeriesRaw: number[] = [0];
const evalTokenAccSeriesRaw: number[] = [0];
const evalTrainSpeedSeriesRaw: number[] = [0];
const xAxisRaw: number[] = [];

const train_loss_series = shallowRef<number[]>(trainLossSeriesRaw); // ????loss
const train_gnorm_series = shallowRef<number[]>(trainGnormSeriesRaw); // ????grad_norm
const train_lrate_series = shallowRef<number[]>(trainLrateSeriesRaw); // ????learning_rate
const train_token_acc_series = shallowRef<number[]>(trainTokenAccSeriesRaw); // ????token_acc
const train_train_speed_series = shallowRef<number[]>(trainTrainSpeedSeriesRaw); // ????train_speed

const eval_loss_series = shallowRef<number[]>(evalLossSeriesRaw); // ????loss
const eval_token_acc_series = shallowRef<number[]>(evalTokenAccSeriesRaw); // ????token_acc
const eval_train_speed_series = shallowRef<number[]>(evalTrainSpeedSeriesRaw); // ????train_speed
// x???
const xAxis = shallowRef<number[]>(xAxisRaw);

const notifySeries = () => {
    train_epochs.value = trainEpochsRaw;
    eval_epochs.value = evalEpochsRaw;
    train_loss_series.value = trainLossSeriesRaw;
    train_gnorm_series.value = trainGnormSeriesRaw;
    train_lrate_series.value = trainLrateSeriesRaw;
    train_token_acc_series.value = trainTokenAccSeriesRaw;
    train_train_speed_series.value = trainTrainSpeedSeriesRaw;
    eval_loss_series.value = evalLossSeriesRaw;
    eval_token_acc_series.value = evalTokenAccSeriesRaw;
    eval_train_speed_series.value = evalTrainSpeedSeriesRaw;
    xAxis.value = xAxisRaw;

    triggerRef(train_epochs);
    triggerRef(eval_epochs);
    triggerRef(train_loss_series);
    triggerRef(train_gnorm_series);
    triggerRef(train_lrate_series);
    triggerRef(train_token_acc_series);
    triggerRef(train_train_speed_series);
    triggerRef(eval_loss_series);
    triggerRef(eval_token_acc_series);
    triggerRef(eval_train_speed_series);
    triggerRef(xAxis);
};


const resetChart = () => {
    trainEpochsRaw.length = 0;
    evalEpochsRaw.length = 0;
    trainLossSeriesRaw.length = 0;
    trainGnormSeriesRaw.length = 0;
    trainLrateSeriesRaw.length = 0;
    trainTokenAccSeriesRaw.length = 0;
    trainTrainSpeedSeriesRaw.length = 0;
    evalLossSeriesRaw.length = 0;
    evalTokenAccSeriesRaw.length = 0;
    evalTrainSpeedSeriesRaw.length = 0;
    xAxisRaw.length = 0;

    summary.value = {
        train_runtime: 0,
        train_samples_per_second: 0,
        train_steps_per_second: 0,
        train_loss: 0,
        total_epoch: 0,
        max_steps: 0,
        percentage: 0,
        elapsed_time: '',
        remaining_time: ''
    };

    eval_summary.value = {
        id: '',
        eval_loss: 0,
        eval_token_acc: 0,
        epoch: 0,
        global_step: 0,
        train_speed: 0
    };

    lastProcessedIndex.value = 0;
    latestGlobalStep.value = 0;
    seenTrainMsgIds.clear();
    seenEvalMsgIds.clear();
    evalGlobalStepSet.clear();

    notifySeries();
};

const parseJSON = (str: string) => {
    str = str.replace(/'/g, '"');
    str = str.replace(/nan/gi, '0');
    return JSON.parse(str);
};

const parseLogs = (logs: Array<any>) => {
    delayDebounce(() => {
        _parseLogs(logs);
    }, 400);
};

const rebuildFromLogs = (logs: Array<any>) => {
    resetChart();
    let summary_obj: any = {};
    let eval_summary_obj: any = {};
    let latest_global_step = 0;

    seenTrainMsgIds.clear();
    seenEvalMsgIds.clear();
    evalGlobalStepSet.clear();

    for (let i = 0; i < logs.length; i++) {
        let msg_id = logs[i].msg_id;
        let log = logs[i].data.log;
        if (log.startsWith("{'loss':")) {
            if (seenTrainMsgIds.has(msg_id)) {
                continue;
            }
            seenTrainMsgIds.add(msg_id);
            let data = parseJSON(log);
            let global_step = Number(data['global_step/max_steps'].split('/')[0]);
            let max_steps = Number(data['global_step/max_steps'].split('/')[1]);
            let train_epoch = {
                id: msg_id,
                loss: data['loss'],
                grad_norm: data['grad_norm'],
                learning_rate: data['learning_rate'],
                token_acc: data['token_acc'],
                epoch: data['epoch'],
                global_step: global_step,
                train_speed: data['train_speed(iter/s)'] || data['train_speed(s/it)']
            };
            trainEpochsRaw.push(train_epoch);
            trainLossSeriesRaw.push(train_epoch.loss);
            trainGnormSeriesRaw.push(train_epoch.grad_norm);
            trainLrateSeriesRaw.push(train_epoch.learning_rate);
            trainTokenAccSeriesRaw.push(train_epoch.token_acc);
            trainTrainSpeedSeriesRaw.push(train_epoch.train_speed);
            xAxisRaw.push(train_epoch.global_step || xAxisRaw.length + 1);

            if (!summary_obj.max_steps && max_steps > 0) {
                summary_obj.max_steps = max_steps;
            }
            if (global_step > latest_global_step) {
                latest_global_step = global_step;
            }
            if (typeof data['percentage'] === 'string') {
                summary_obj.percentage = Number(data['percentage'].replace('%', ''));
            }
            summary_obj.elapsed_time = data['elapsed_time'];
            summary_obj.remaining_time = data['remaining_time'];
        }

        if (log.startsWith("{'eval_loss':")) {
            if (seenEvalMsgIds.has(msg_id)) {
                continue;
            }
            seenEvalMsgIds.add(msg_id);
            let data = parseJSON(log);
            let global_step = Number(data['global_step/max_steps'].split('/')[0]);
            let max_steps = Number(data['global_step/max_steps'].split('/')[1]);
            let eval_epoch = {
                id: msg_id,
                eval_loss: data['eval_loss'],
                eval_token_acc: data['eval_token_acc'],
                eval_train_speed: data['train_speed(iter/s)'] || data['train_speed(s/it)'],
                epoch: data['epoch'],
                global_step: global_step,
                train_speed: data['train_speed(iter/s)'] || data['train_speed(s/it)']
            };
            if (!summary_obj.max_steps && max_steps > 0) {
                summary_obj.max_steps = max_steps;
            }
            if (global_step > latest_global_step) {
                latest_global_step = global_step;
            }
            if (!evalGlobalStepSet.has(eval_epoch.global_step)) {
                evalGlobalStepSet.add(eval_epoch.global_step);
                evalEpochsRaw.push(eval_epoch);
                evalLossSeriesRaw.push(eval_epoch.eval_loss);
                evalTokenAccSeriesRaw.push(eval_epoch.eval_token_acc);
                evalTrainSpeedSeriesRaw.push(eval_epoch.train_speed);
            } else {
                eval_summary_obj = eval_epoch;
            }
        }

        if (log.startsWith("{'train_runtime':")) {
            let data = parseJSON(log);
            summary_obj.train_runtime = Number(data['train_runtime']);
            summary_obj.train_samples_per_second = Number(data['train_samples_per_second']);
            summary_obj.train_steps_per_second = Number(data['train_steps_per_second']);
            summary_obj.train_loss = Number(data['train_loss']);
            summary_obj.total_epoch = Number(data['epoch']);
        }
    }

    if (summary_obj.max_steps && latest_global_step) {
        let computed_percentage = Math.min(100, (latest_global_step / summary_obj.max_steps) * 100);
        if (!summary_obj.percentage || computed_percentage > summary_obj.percentage) {
            summary_obj.percentage = Number(computed_percentage.toFixed(2));
        }
    }
    if (summary_obj.train_runtime) {
        summary_obj.percentage = 100;
    }

    summary.value = summary_obj;
    eval_summary.value = eval_summary_obj;
    latestGlobalStep.value = latest_global_step;
    lastProcessedIndex.value = logs.length;

    notifySeries();
};

const _parseLogs = (logs: Array<any>) => {
    if (logs.length == 0) {
        resetChart();
        lastLogsRef.value = logs;
        return;
    }

    if (lastLogsRef.value !== logs || logs.length < lastProcessedIndex.value) {
        lastLogsRef.value = logs;
        rebuildFromLogs(logs);
        return;
    }

    let summary_obj: any = { ...summary.value };
    let eval_summary_obj: any = { ...eval_summary.value };
    let latest_global_step = latestGlobalStep.value;

    for (let i = lastProcessedIndex.value; i < logs.length; i++) {
        let msg_id = logs[i].msg_id;
        let log = logs[i].data.log;
        if (log.startsWith("{'loss':")) {
            if (seenTrainMsgIds.has(msg_id)) {
                continue;
            }
            seenTrainMsgIds.add(msg_id);
            let data = parseJSON(log);
            let global_step = Number(data['global_step/max_steps'].split('/')[0]);
            let max_steps = Number(data['global_step/max_steps'].split('/')[1]);
            let train_epoch = {
                id: msg_id,
                loss: data['loss'],
                grad_norm: data['grad_norm'],
                learning_rate: data['learning_rate'],
                token_acc: data['token_acc'],
                epoch: data['epoch'],
                global_step: global_step,
                train_speed: data['train_speed(iter/s)'] || data['train_speed(s/it)']
            };
            trainEpochsRaw.push(train_epoch);
            trainLossSeriesRaw.push(train_epoch.loss);
            trainGnormSeriesRaw.push(train_epoch.grad_norm);
            trainLrateSeriesRaw.push(train_epoch.learning_rate);
            trainTokenAccSeriesRaw.push(train_epoch.token_acc);
            trainTrainSpeedSeriesRaw.push(train_epoch.train_speed);
            xAxisRaw.push(train_epoch.global_step || xAxisRaw.length + 1);

            if (!summary_obj.max_steps && max_steps > 0) {
                summary_obj.max_steps = max_steps;
            }
            if (global_step > latest_global_step) {
                latest_global_step = global_step;
            }
            if (typeof data['percentage'] === 'string') {
                summary_obj.percentage = Number(data['percentage'].replace('%', ''));
            }
            summary_obj.elapsed_time = data['elapsed_time'];
            summary_obj.remaining_time = data['remaining_time'];
        }

        if (log.startsWith("{'eval_loss':")) {
            if (seenEvalMsgIds.has(msg_id)) {
                continue;
            }
            seenEvalMsgIds.add(msg_id);
            let data = parseJSON(log);
            let global_step = Number(data['global_step/max_steps'].split('/')[0]);
            let max_steps = Number(data['global_step/max_steps'].split('/')[1]);
            let eval_epoch = {
                id: msg_id,
                eval_loss: data['eval_loss'],
                eval_token_acc: data['eval_token_acc'],
                eval_train_speed: data['train_speed(iter/s)'] || data['train_speed(s/it)'],
                epoch: data['epoch'],
                global_step: global_step,
                train_speed: data['train_speed(iter/s)'] || data['train_speed(s/it)']
            };
            if (!summary_obj.max_steps && max_steps > 0) {
                summary_obj.max_steps = max_steps;
            }
            if (global_step > latest_global_step) {
                latest_global_step = global_step;
            }
            if (!evalGlobalStepSet.has(eval_epoch.global_step)) {
                evalGlobalStepSet.add(eval_epoch.global_step);
                evalEpochsRaw.push(eval_epoch);
                evalLossSeriesRaw.push(eval_epoch.eval_loss);
                evalTokenAccSeriesRaw.push(eval_epoch.eval_token_acc);
                evalTrainSpeedSeriesRaw.push(eval_epoch.train_speed);
            } else {
                eval_summary_obj = eval_epoch;
            }
        }

        if (log.startsWith("{'train_runtime':")) {
            let data = parseJSON(log);
            summary_obj.train_runtime = Number(data['train_runtime']);
            summary_obj.train_samples_per_second = Number(data['train_samples_per_second']);
            summary_obj.train_steps_per_second = Number(data['train_steps_per_second']);
            summary_obj.train_loss = Number(data['train_loss']);
            summary_obj.total_epoch = Number(data['epoch']);
        }
    }

    if (summary_obj.max_steps && latest_global_step) {
        let computed_percentage = Math.min(100, (latest_global_step / summary_obj.max_steps) * 100);
        if (!summary_obj.percentage || computed_percentage > summary_obj.percentage) {
            summary_obj.percentage = Number(computed_percentage.toFixed(2));
        }
    }
    if (summary_obj.train_runtime) {
        summary_obj.percentage = 100;
    }

    summary.value = summary_obj;
    eval_summary.value = eval_summary_obj;
    latestGlobalStep.value = latest_global_step;
    lastProcessedIndex.value = logs.length;
    notifySeries();
};

const resizeObserver = new ResizeObserver((entries) => {
    for (let entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
            document.querySelectorAll('.chart').forEach((item: any) => {
                item.style.width = (width - 40) / 3 + 'px';
            });
        }
    }
});

const watchChartContainerResize = () => {
    const target = document.querySelector('#train-chart-container');
    if (!target) {
        return;
    }
    resizeObserver.observe(target);
};

const unwatchChartContainerResize = () => {
    const target = document.querySelector('#train-chart-container');
    if (!target) {
        return;
    }
    resizeObserver.unobserve(target);
    resizeObserver.disconnect();
};

watch(
    () => props.logs.length,
    () => {
        parseLogs(props.logs as Array<any>);
    }
);

onMounted(() => {
    parseLogs(props.logs);
    watchChartContainerResize();
});
onUnmounted(() => {
    unwatchChartContainerResize();
});
</script>

<template>
    <div id="train-chart-container" class="w-[100%] h-full p-2 overflow-y-auto overflow-x-hidden select-none">
        <div class="w-[100%] flex gap-4 h-[20rem]">
            <div class="flex-1 rounded-lg border border-gray-200 dark:border-gray-900 bg-white dark:bg-gray-800">
                <VueDataUIWheel :title="t('page.trainchart.progress')" :summary="summary" :useAnimation="useAnimation" />
            </div>
            <div class="flex-1 rounded-lg border border-gray-200 dark:border-gray-900 bg-white dark:bg-gray-800">
                <VueChartJSLineXY
                    :title="t('page.trainchart.loss')"
                    :data="[
                        { name: 'train_loss', series: train_loss_series, color: '#ea1a1a' },
                        { name: 'eval_loss', series: eval_loss_series, color: '#0f8feb' }
                    ]"
                    :xAxis="xAxis"
                    :yFormatter="'format1'"
                    class="chart"
                />
            </div>
            <div class="flex-1 rounded-lg border border-gray-200 dark:border-gray-900 bg-white dark:bg-gray-800">
                <VueChartJSLineXY :title="t('page.trainchart.lrate')" :data="[{ name: 'train_lrate', series: train_lrate_series, color: '#ea1a1a' }]" :xAxis="xAxis" :yFormatter="'format2'" class="chart" />
            </div>
        </div>
        <div class="w-[100%] flex gap-4 h-[20rem] mt-4">
            <div class="flex-1 rounded-lg border border-gray-200 dark:border-gray-900 bg-white dark:bg-gray-800">
                <VueChartJSLineXY :title="t('page.trainchart.gnorm')" :data="[{ name: 'train_gnorm', series: train_gnorm_series, color: '#ea1a1a' }]" :xAxis="xAxis" :yFormatter="'format1'" class="chart" />
            </div>
            <div class="flex-1 rounded-lg border border-gray-200 dark:border-gray-900 bg-white dark:bg-gray-800">
                <VueChartJSLineXY
                    :title="'token_acc'"
                    :data="[
                        { name: 'train_token_acc', series: train_token_acc_series, color: '#ea1a1a' },
                        { name: 'eval_token_acc', series: eval_token_acc_series, color: '#0f8feb' }
                    ]"
                    :xAxis="xAxis"
                    :yFormatter="'format3'"
                    class="chart"
                />
            </div>
            <div class="flex-1 rounded-lg border border-gray-200 dark:border-gray-900 bg-white dark:bg-gray-800">
                <VueChartJSLineXY
                    :title="t('page.trainchart.train_speed')"
                    :data="[
                        { name: 'train_speed', series: train_train_speed_series, color: '#ea1a1a' },
                        { name: 'eval_speed', series: eval_train_speed_series, color: '#0f8feb' }
                    ]"
                    :xAxis="xAxis"
                    :yFormatter="'format1'"
                    class="chart"
                />
            </div>
        </div>
    </div>
</template>

<style scoped></style>
