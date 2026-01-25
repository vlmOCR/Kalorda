<script lang="ts">
import { RouteMeta } from '@/router/MetaType';
export const routeMeta: RouteMeta = {
    title: 'home',
    icon: 'pi pi-home'
};
</script>
<script setup lang="ts">
import { HomeService } from '@/services/HomeService';
import { showLoading, hideLoading } from '@/utils/GlobalUtil';
import { promise2, gotoRoute, windowOpen } from '@/utils/Common';
import { useI18n } from 'vue-i18n';
const { t } = useI18n();

// 首页数据
const homeData = ref<any>({});
const noModelConfigMsg = ref<boolean>(false);
const closeNoModelConfigMsg = () => {
    noModelConfigMsg.value = false;
};

onMounted(async () => {
    showLoading();
    let [err, res] = await promise2(HomeService.getHomeData());
    hideLoading();
    if (err) {
        return;
    }
    if (res && res.code === 2000) {
        homeData.value = res.data;
        let availableModelCount = 0;
        for (let item of homeData.value.base_model_infos) {
            if (item.available === true) {
                availableModelCount++;
            }
        }
        // 是否需要提示模型权重配置
        noModelConfigMsg.value = availableModelCount === 0;
    }
});
</script>
<template>
    <div>
        <div class="w-full">
            <div class="w-full flex flex-col justify-center items-center my-4">
                <div class="relative">
                    <div class="text-2xl font-bold">{{ t('page.home.title1') }}</div>
                    <div class="absolute top-[-20px] left-[60px]">
                        <Badge value="≤3B" severity="danger"></Badge>
                    </div>
                </div>
                <div class="mt-2 text-sm text-gray-400">{{ t('page.home.title1note') }}</div>
            </div>

            <div class="flex flex-wrap justify-center gap-12">
                <div
                    @click="gotoRoute('/train/dataset')"
                    v-animateonscroll="{ enterClass: 'animate-enter fade-in-10 zoom-in-50 animate-duration-1000' }"
                    class="flex flex-col bg-purple-500 text-white border-purple-500 shadow-lg justify-center items-center max-w-80 rounded-2xl p-8 gap-4 cursor-pointer"
                >
                    <div class="rounded-xl border-2 border-white w-12 h-12 flex items-center justify-center">
                        <i class="pi pi-database !text-2xl"></i>
                    </div>
                    <span class="text-2xl font-bold">{{ t('page.home.datalabel') }}</span>
                    <span class="text-center">{{ t('page.home.dataset_count', [homeData.dataset_count || 0, homeData.dataset_image_count || 0]) }}</span>
                </div>
                <div
                    @click="gotoRoute('/train/finetune')"
                    v-animateonscroll="{ enterClass: 'animate-enter fade-in-10 zoom-in-75 animate-duration-1000' }"
                    class="flex flex-col bg-teal-500 text-white border-teal-500 shadow-lg justify-center items-center max-w-80 rounded-2xl p-8 gap-4 cursor-pointer"
                >
                    <div class="rounded-xl border-2 border-white w-12 h-12 flex items-center justify-center">
                        <i class="pi pi-objects-column !text-2xl"></i>
                    </div>
                    <span class="text-2xl font-bold">{{ t('page.home.finetune') }}</span>
                    <span class="text-center">{{ t('page.home.finetune_count', [homeData.fine_tune_task_count || 0, homeData.training_run_count || 0]) }}</span>
                </div>
                <div
                    @click="gotoRoute('/train/modeltest')"
                    v-animateonscroll="{ enterClass: 'animate-enter fade-in-10 zoom-in-50 animate-duration-1000' }"
                    class="flex flex-col bg-indigo-500 text-white border-indigo-500 shadow-lg justify-center items-center max-w-80 rounded-2xl p-8 gap-4 cursor-pointer"
                >
                    <div class="rounded-xl border-2 border-white w-12 h-12 flex items-center justify-center">
                        <i class="pi pi-map !text-2xl"></i>
                    </div>
                    <span class="text-2xl font-bold">{{ t('page.home.modeltest') }}</span>
                    <span class="text-center">{{ t('page.home.modeltest_count', [homeData.test_ocr_result_count || 0]) }}</span>
                </div>
            </div>
        </div>

        <div class="w-full mt-16">
            <div class="w-full flex flex-col justify-center items-center mb-4">
                <div class="text-2xl font-bold">{{ t('page.home.title2') }}</div>
            </div>

            <div class="flex flex-wrap justify-center gap-8">
                <div
                    v-for="item in homeData.base_model_infos"
                    :key="item.id"
                    v-animateonscroll="{ enterClass: 'animate-enter fade-in-10 zoom-in-50 animate-duration-1000' }"
                    :class="{ 'text-white bg-primary-500 border-primary-500 ': item.available === true, 'text-gray-700 bg-gray-500 border-gray-500': item.available === false }"
                    class="flex flex-col shadow-lg justify-center items-center w-45 min-w-45 rounded-2xl px-2 py-4 gap-4 cursor-pointer"
                    @click="windowOpen(item.url)"
                    v-tooltip="item.available === false ? t('page.home.model_not_config') : ''"
                >
                    <div :class="{ 'border-white': item.available === true, 'border-gray-700': item.available === false }" class="rounded-full border-2 w-12 h-12 flex items-center justify-center">
                        <i class="pi pi-box !text-2xl"></i>
                    </div>
                    <span class="text-xl">{{ item.name }}</span>
                    <span class="text-center">{{ item.desc }}</span>
                </div>
            </div>

            <div class="w-full flex justify-center items-center mt-4" v-if="noModelConfigMsg">
                <div class="w-100 flex justify-center items-center rounded-full bg-primary-900 text-center px-4 py-2 text-primary text-sm gap-2">
                    <div class="cursor-pointer hover:text-primary-100" @click="gotoRoute('/admin/systemsetting')">
                        {{ t('page.home.all_model_not_config') }}
                    </div>
                    <div class="cursor-pointer hover:text-primary-100" @click="closeNoModelConfigMsg"><i class="pi pi-minus-circle pt-1"></i></div>
                </div>
            </div>
        </div>
    </div>
</template>
<style scoped></style>
