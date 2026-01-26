<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { DatasetService } from '@/services/DatasetService';
import { promise2 } from '@/utils/Common';
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil';
import { useI18n } from 'vue-i18n';
const { t } = useI18n();

const props = defineProps<{
    visible: boolean;
    datasetId: number;
    datasetName?: string;
}>();

const emit = defineEmits<{
    (e: 'update:visible', value: boolean): void;
    (e: 'imported'): void;
}>();

const dialogVisible = computed({
    get: () => props.visible,
    set: (value: boolean) => emit('update:visible', value)
});

const zipInput = ref();
const zipInputKey = ref(Date.now());
const zipFile = ref<File | null>(null);
const trainRatio = ref('100');
const isImporting = ref(false);

watch(
    () => props.visible,
    (value) => {
        if (value) {
            zipFile.value = null;
            trainRatio.value = '100';
        }
    }
);

const clearZipInput = () => {
    zipInput.value = '';
    zipInputKey.value = Date.now();
};

const chooseZip = () => {
    let zipInputElement: any = document.getElementById('zipInput');
    zipInputElement?.click();
};

const onZipChange = (event: any) => {
    const files = event.target.files;
    if (!files || files.length === 0) {
        return;
    }
    const file = files[0];
    const fileName = file.name.toLowerCase();
    if (!fileName.endsWith('.zip')) {
        showToast('error', 'Error', 'Please choose a .zip file', true);
        clearZipInput();
        return;
    }
    zipFile.value = file;
    clearZipInput();
};

const importZip = async () => {
    if (!props.datasetId) {
        showToast('error', 'Error', 'Please choose a dataset first', true);
        return;
    }
    if (!zipFile.value) {
        showToast('error', 'Error', 'Please choose a zip file', true);
        return;
    }
    const ratio = Number(trainRatio.value);
    if (Number.isNaN(ratio) || ratio < 0 || ratio > 100) {
        showToast('error', 'Error', 'Train ratio must be between 0 and 100', true);
        return;
    }

    isImporting.value = true;
    showLoading();
    const [err, res] = await promise2(DatasetService.importDatasetZip(props.datasetId, zipFile.value, ratio));
    hideLoading();
    isImporting.value = false;

    if (err || !res || res.code !== 2000) {
        return;
    }

    const summary = res.data?.summary;
    const errorCount = Array.isArray(res.data?.errors) ? res.data.errors.length : 0;
    let message = 'Import completed';
    if (summary) {
        message = `Imported ${summary.total} files (train ${summary.train}, val ${summary.val}).`;
        if (errorCount > 0) {
            message += ` ${errorCount} skipped.`;
        }
    }
    showToast('success', 'Success', message, true);
    zipFile.value = null;
    emit('imported');
    dialogVisible.value = false;
};
</script>

<template>
    <Dialog v-model:visible="dialogVisible" modal :header="t('page.zipimport.title')" :style="{ width: '26rem' }">
        <div class="flex flex-col gap-2">
            <div class="text-sm text-surface-500">{{ t('page.zipimport.targetdataset') }} {{ datasetName || '-' }}</div>
            <div class="flex flex-col">
                <label class="text-sm text-surface-500 my-1">{{ t('page.zipimport.traindataradio') }}</label>
                <InputText v-model="trainRatio" type="number" min="0" max="100" class="w-28" />
            </div>
            <div class="flex flex-col">
                <label class="text-sm text-surface-500 my-1">{{ t('page.zipimport.zipfile') }}</label>
                <div class="flex items-center gap-2">
                    <input id="zipInput" ref="zipInput" :key="zipInputKey" type="file" @change="onZipChange" accept=".zip" style="visibility: hidden; width: 0; height: 0" />
                    <Button :label="t('page.zipimport.zipselect')" icon="pi pi-folder-open" severity="secondary" @click="chooseZip" :disabled="isImporting" />
                    <span class="text-sm text-surface-500">{{ zipFile ? zipFile.name : t('page.zipimport.noselect') }}</span>
                </div>
            </div>
            <div class="text-xs text-surface-500" v-html="t('page.zipimport.zipnote')"></div>
        </div>
        <template #footer>
            <div class="flex justify-end gap-2">
                <Button :label="t('page.common.cancel')" severity="secondary" @click="dialogVisible = false" />
                <Button :label="t('page.common.submit')" icon="pi pi-cloud-upload" severity="info" @click="importZip" :disabled="!zipFile || isImporting" />
            </div>
        </template>
    </Dialog>
</template>
