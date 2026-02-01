<script setup lang="ts">
import { VirtList } from 'vue-virt-list';
import { delayDebounce } from '@/utils/Common';
import { useI18n } from 'vue-i18n';
const { t } = useI18n();

const props = defineProps({
    logs: {
        type: Array<object>,
        default: () => []
    },
    loading: {
        type: Boolean,
        default: false
    }
});

const virtualScrollerRef = ref();
const virtualLogs = shallowRef<Array<object>>([]); // shallowRef

// 搜索相关变量
const logSearchVisible = ref(false);
const logSearchText = ref('');
const caseSensitive = ref(false); // 默认不区分大小写搜索
const searchedCount = ref(0);
const searchedIndex = ref(0);
const searchPrefixCounts = ref<number[]>([]);
const lastSearchBuildLength = ref(0);
const searchRegExp = computed(() => {
    if (!logSearchVisible.value || !logSearchText.value) {
        return null;
    }
    try {
        return caseSensitive.value ? new RegExp(logSearchText.value) : new RegExp(logSearchText.value, 'ig');
    } catch {
        return null;
    }
});

const scrollToBottom = () => {
    virtualScrollerRef.value.scrollToBottom();
};

// 搜索条显示与关闭，该方法暴露给上级组件调用
const logSearch = (show: boolean) => {
    logSearchVisible.value = show;
    if (show && logSearchText.value.length > 0) {
        buildSearchIndexData();
    }
};
defineExpose({
    logSearch,
    scrollToBottom
});

// 日志编号条宽度
const idxBarWidth = computed(() => {
    let length = virtualLogs.value.length.toString().length;
    if (length == 1) return 26;
    if (length == 2) return 34;
    if (length == 3) return 42;
    if (length == 4) return 50;
    return 58;
});

// 日志数据结构示意 log is the message data type
// item = {
//     msg_id: '',
//     data: { log:''}
// }
let pendingLogs: Array<any> | null = null;
let scheduleLogsFlush = false;
const setVirtualLogs = (newLogs: Array<any>) => {
    pendingLogs = newLogs;
    if (scheduleLogsFlush) {
        return;
    }
    scheduleLogsFlush = true;
    requestAnimationFrame(() => {
        scheduleLogsFlush = false;
        const nextLogs = pendingLogs || [];
        pendingLogs = null;
        if (nextLogs.length == 0) {
            logSearch(false);
        }
        // newLogs.forEach((item) => item.msg_id += `_${Math.random()}`); // avoid duplicate msg_id from external input
        virtualLogs.value = nextLogs;
        setTimeout(() => {
            scrollToBottom();
        }, 0);
    });
};

const markGloablStepLog = (html_log: string, orginal_log: string, log_index: number) => {
    if (orginal_log.startsWith("{'loss':")) {
        //提取 'global_step/max_steps': '12/30' 中的12
        let step_info = orginal_log.split("'global_step/max_steps':")[1].split(',')[0].replaceAll("'", '');
        let global_step = step_info.split('/')[0].trim();
        // let max_steps = step_info.split('/')[1].trim();
        html_log = `<span style="font-weight:bold;color:#ff0000;">${html_log}</span><span style="width:3px;display:inline-block;"></span><span style="font-size:12px;display:inline-block;background-color:red;color:white;border-radius: 6px;padding-right:1px;min-width:12px;display:inline-block;text-align:center;">${global_step}</span>`;
    }

    if (orginal_log.startsWith("{'eval_loss':")) {
        //提取 'global_step/max_steps': '12/30' 中的12
        let step_info = orginal_log.split("'global_step/max_steps':")[1].split(',')[0].replaceAll("'", '');
        let global_step = step_info.split('/')[0].trim();
        let max_steps = step_info.split('/')[1].trim();
        let is_val_summary_log = false; // eval最后的总结日志和普通的eval日志格式一样的，区分逻辑是看上一条日志是什么内容
        if (global_step == max_steps) {
            let prev_log = virtualLogs.value[log_index - 1];
            if (prev_log) {
                let prev_orginal_log = (prev_log as any).data.log;
                if (prev_orginal_log.indexOf('End time of running main:') >= 0) {
                    // 如果上一条日志包含End time of running main:的内容，那么这一条日志就是val总结性日志
                    is_val_summary_log = true;
                }
            }
        }
        if (!is_val_summary_log) {
            html_log = `<span style="font-weight:bold;color:#0f8feb;">${html_log}</span><span style="width:3px;display:inline-block;"></span><span style="font-size:12px;display:inline-block;background-color:#0f8feb;;color:white;border-radius: 6px;padding-right:1px;min-width:12px;display:inline-block;text-align:center;">${global_step}</span>`;
        }
    }
    return html_log;
};

const htmlParse = (orginal_log: string, log_index: number) => {
    // 特殊字符处理
    let html_log = orginal_log.replaceAll(/&/g, '&amp;').replaceAll(/</g, '&lt;').replaceAll(/>/g, '&gt;');
    if (html_log.startsWith('  ')) {
        html_log = html_log.replaceAll(/ /g, '&nbsp;');
    }

    const reg = searchRegExp.value;
    if (!reg) {
        return markGloablStepLog(html_log, orginal_log, log_index);
    }
    // 搜索高亮处理
    let sub_index = 0;
    const baseIndex = getSearchBaseIndex(log_index);
    if (reg.global) {
        reg.lastIndex = 0;
    }
    html_log = html_log.replace(reg, (match) => {
        let is_active = searchedIndex.value == baseIndex + sub_index;
        let highlight_log = `<span class="text-hightlight${is_active ? ' text-hightlight-active' : ''}" data-index="${log_index}-${sub_index}">${match}</span>`;
        sub_index += 1;
        return highlight_log;
    });
    return markGloablStepLog(html_log, orginal_log, log_index);
};

// 搜索索引移动到第一个或最后一个 相互切换
const searchIndexMoveFirstOrLast = () => {
    if (searchedCount.value == 0) {
        return;
    }
    if (searchedIndex.value == searchedCount.value - 1) {
        searchedIndex.value = 0;
    } else {
        searchedIndex.value = searchedCount.value - 1;
    }
    scrollToSearchText(searchedIndex.value);
};

const searchIndexMove = (direction: number) => {
    const reg = searchRegExp.value;
    if (!reg) {
        return;
    }
    let index = searchedIndex.value + direction;
    if (index < 0 || index >= searchedCount.value) {
        return;
    }
    scrollToSearchText(index);
};

const getSearchBaseIndex = (logIndex: number) => {
    if (logIndex <= 0) {
        return 0;
    }
    return searchPrefixCounts.value[logIndex - 1] || 0;
};

const findLogIndexBySearchIndex = (index: number) => {
    let left = 0;
    let right = searchPrefixCounts.value.length - 1;
    while (left <= right) {
        const mid = Math.floor((left + right) / 2);
        const value = searchPrefixCounts.value[mid];
        if (value > index) {
            right = mid - 1;
        } else {
            left = mid + 1;
        }
    }
    return left;
};

const scrollToSearchText = (index: number) => {
    searchedIndex.value = index;
    let target_log_index = findLogIndexBySearchIndex(index);
    if (target_log_index < 0) {
        target_log_index = 0;
    }
    virtualScrollerRef.value.scrollToIndex(target_log_index);
};

const buildSearchIndexData = () => {
    const reg = searchRegExp.value;
    if (!reg) {
        searchedCount.value = 0;
        searchedIndex.value = 0;
        searchPrefixCounts.value = [];
        lastSearchBuildLength.value = 0;
        return;
    }
    let serachCount = 0;

    const prefixCounts: number[] = [];
    for (let log_index = 0; log_index < virtualLogs.value.length; log_index++) {
        if (reg.global) {
            reg.lastIndex = 0;
        }
        let count = (virtualLogs.value[log_index] as any).data.log.match(reg)?.length || 0; // match count in a single log line
        if (count > 0) {
            serachCount += count; // accumulate match count
        }
        prefixCounts.push(serachCount);
    }
    searchedCount.value = serachCount;
    searchPrefixCounts.value = prefixCounts;
    lastSearchBuildLength.value = virtualLogs.value.length;
    searchedIndex.value = 0;
};

const appendSearchIndexData = (startIndex: number) => {
    const reg = searchRegExp.value;
    if (!reg) {
        return;
    }
    let total = searchPrefixCounts.value.length ? searchPrefixCounts.value[searchPrefixCounts.value.length - 1] : 0;
    for (let log_index = startIndex; log_index < virtualLogs.value.length; log_index++) {
        if (reg.global) {
            reg.lastIndex = 0;
        }
        let count = (virtualLogs.value[log_index] as any).data.log.match(reg)?.length || 0;
        total += count;
        searchPrefixCounts.value.push(total);
    }
    searchedCount.value = total;
    lastSearchBuildLength.value = virtualLogs.value.length;
};

watch(
    () => logSearchText.value + caseSensitive.value,
    () => {
        delayDebounce(buildSearchIndexData, 500);
    }
);

watch(
    () => props.logs.length,
    () => {
        setVirtualLogs(props.logs as Array<any>);
        if (logSearchVisible.value && searchRegExp.value) {
            if (lastSearchBuildLength.value == 0) {
                buildSearchIndexData();
            } else if (props.logs.length > lastSearchBuildLength.value) {
                appendSearchIndexData(lastSearchBuildLength.value);
            }
        }
    }
);

onMounted(() => {
    setVirtualLogs(props.logs);
});

onBeforeUnmount(() => {
    virtualLogs.value.length = 0;
    virtualScrollerRef.value = null;
    searchPrefixCounts.value = [];
    lastSearchBuildLength.value = 0;
});
</script>

<template>
    <div class="w-full h-[100%]">
        <div class="w-full h-[100%] relative overflow-hidden">
            <VirtList itemKey="msg_id" :list="virtualLogs" ref="virtualScrollerRef" class="w-full border border-surface-200 dark:border-surface-700 overflow-x-hidden h-[100%] log">
                <template #default="{ itemData, index }">
                    <div :class="['flex items-top w-full m-0 gap-1 min-h-[32px]']">
                        <div class="pt-2 z-2 text-center text-surface-400 dark:text-surface-500 bg-surface-200 dark:bg-surface-800 select-none" :style="{ width: idxBarWidth + 'px', fontSize: '12px' }">{{ index + 1 }}</div>
                        <!-- whitespace-nowrap text-overflow-ellipsis cursor-pointer -->
                        <div class="w-full p-2 text-surface-900 dark:text-surface-400">
                            <span style="word-break: break-all" v-html="htmlParse(itemData.data.log, index)"></span>
                        </div>
                    </div>
                    <!-- 最末行显示loading标记 -->
                    <div :class="['flex items-top w-full m-0 gap-1 min-h-[32px]']" v-if="props.loading && index == virtualLogs.length - 1">
                        <div class="pt-2 z-2 text-center text-surface-400 dark:text-surface-500 bg-surface-200 dark:bg-surface-800 select-none" :style="{ width: idxBarWidth + 'px', fontSize: '12px' }">{{ index + 2 }}</div>
                        <div class="w-full p-2 text-surface-500 dark:text-surface-400">
                            <span class="log-loading">
                                <span class="loading-dots flex gap-1">
                                    <span class="dot">.</span>
                                    <span class="dot">.</span>
                                    <span class="dot">.</span>
                                </span>
                            </span>
                        </div>
                    </div>
                </template>
            </VirtList>
            <div class="absolute h-full top-0 left-0 z-1 text-center text-surface-200 dark:text-surface-800 bg-surface-200 dark:bg-surface-800" :style="{ width: idxBarWidth + 1 + 'px' }"></div>
        </div>

        <Dialog v-model:visible="logSearchVisible" :style="{ width: '35rem' }">
            <template #header>
                <div class="flex items-center justify-end gap-2 cursor-default">
                    <div class="text-lg font-bold">{{ t('page.trainlog.searchlog') }}</div>
                    <div class="text-sm text-surface-300 dark:text-surface-700">
                        {{ caseSensitive ? t('page.trainlog.casesensitive') : t('page.trainlog.nocasesensitive') }}
                    </div>
                </div>
            </template>
            <div class="flex items-center gap-4 mb-4">
                <InputGroup>
                    <InputGroupAddon @click="searchIndexMove(-1)">
                        <i class="iconfont icon-daxiaoxiezhuanhuan cursor-pointer" :class="{ 'text-primary': caseSensitive }" @click="caseSensitive = !caseSensitive"></i>
                    </InputGroupAddon>

                    <InputText v-model="logSearchText" :placeholder="t('page.trainlog.inputkeyword')" class="w-full" spellcheck="false" fluid />

                    <InputGroupAddon v-if="logSearchText.length > 0" @click="searchIndexMove(-1)"><i class="pi pi-angle-up cursor-pointer"></i> </InputGroupAddon>
                    <InputGroupAddon v-if="logSearchText.length > 0">
                        <div class="flex items-center gap-1 text-sm cursor-pointer select-none" @click="searchIndexMoveFirstOrLast">
                            <span>{{ searchedCount > 0 ? searchedIndex + 1 : 0 }}</span
                            >/<span>{{ searchedCount }}</span>
                        </div>
                    </InputGroupAddon>
                    <InputGroupAddon v-if="logSearchText.length > 0" @click="searchIndexMove(1)"><i class="pi pi-angle-down cursor-pointer"></i> </InputGroupAddon>
                </InputGroup>
            </div>
        </Dialog>
    </div>
</template>

<style scoped>
:deep(.log) {
    font-size: 16px;
    font-family: 'Courier New', Courier, monospace;
}

:deep(.text-hightlight) {
    /* color: rgb(204, 63, 63); */
    color: #ea4a4a;
    background-color: rgb(220, 220, 23);
}

:deep(.text-hightlight-active) {
    /* color: var(--primary-color); */
    color: rgb(220, 220, 23);
    background-color: red;
    /* border-top: 1px solid red; */
    /* border-bottom: 1px solid red; */
}

/* loading动画关键帧定义在顶级作用域 */
@keyframes blink {
    0% {
        opacity: 0.2;
    }

    20% {
        opacity: 1;
    }

    100% {
        opacity: 0.2;
    }
}

/* 简化:deep()选择器的使用 */
:deep(.log-loading .loading-dots .dot) {
    animation: blink 0.5s infinite both;
    margin-left: -1px;
    margin-top: -4px;
    font-weight: bold;
}

:deep(.log-loading .loading-dots .dot:first-child) {
    margin-left: 0;
}

:deep(.log-loading .loading-dots .dot:nth-child(2)) {
    animation-delay: 0.2s;
}

:deep(.log-loading .loading-dots .dot:nth-child(3)) {
    animation-delay: 0.4s;
}
</style>
