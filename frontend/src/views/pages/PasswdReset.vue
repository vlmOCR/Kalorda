<script setup lang="ts">
import ICPInformation from '@/components/ICPInformation.vue';
import AppGlobal from '@/layout/AppGlobal.vue';
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil';
import { AuthService } from '@/services/AuthService';
import { debounce, promise2, gotoRoute } from '@/utils/Common'; //, gotoRoute
import { useI18n } from 'vue-i18n';
const { t } = useI18n();
const base = import.meta.env.VITE_APP_BASE;
const loginPath = import.meta.env.VITE_LOGIN_PATH;
// const env = import.meta.env;
// const email: any = queryParamValue(window.location.href, 'email');
const resetCode = ref('');
const password1 = ref('');
const password2 = ref('');

const resetPasswd = (e: any) => {
    debounce(
        async () => {
            let data = {
                resetCode: resetCode.value,
                password1: password1.value,
                password2: password2.value
            };
            showLoading();
            let [err, res] = await promise2(AuthService.resetPassword(data));
            hideLoading();
            if (err) {
                return;
            }
            if (res && res.code == 2000) {
                showToast('success', t('page.common.success'), t('page.password_reset.resetsuccess'));
                password1.value = '';
                password2.value = '';
                resetCode.value = '';
                setTimeout(() => {
                    gotoRoute(loginPath);
                }, 1500);
            }
        },
        1000,
        e
    );
};

onMounted(() => {});
</script>

<template>
    <div>
        <div class="p-4">
            <div class="flex justify-center">
                <div class="w-full max-w-sm">
                    <div class="flex flex-col items-center justify-center">
                        <div class="text-center my-8">
                            <div class="flex justify-center">
                                <img src="/logo.svg" width="58" height="58" />
                            </div>
                            <h1 class="font-bold">{{ t('page.password_reset.title') }}</h1>
                            <p class="text-gray-500 text-50">{{ t('page.password_reset.note') }}</p>
                        </div>
                        <div class="text-center">
                            <input type="password" style="position: absolute; top: -1000px" />
                            <!-- 放一个看不到的password input可以阻断浏览器的自动填充 -->
                            <InputText id="resetCode" v-model="resetCode" autocomplete="off" :placeholder="t('page.password_reset.yourresetcode')" class="md:w-[30rem] text-lg text-center" fluid :feedback="false" />
                            <Password id="password1" v-model="password1" :placeholder="t('page.password_reset.yourpassword')" :toggleMask="true" class="md:w-[30rem] my-3 text-lg text-center" fluid :feedback="false" maxLength="50"></Password>
                            <Password id="password2" v-model="password2" :placeholder="t('page.password_reset.yourconfirmpassword')" :toggleMask="true" class="md:w-[30rem] mb-3 text-lg text-center" fluid :feedback="false" maxLength="50"></Password>
                            <Button :label="t('page.password_reset.button')" class="md:w-[30rem] text-lg" @click="resetPasswd" :style="{ padding: '10px', cursor: 'pointer' }" />
                        </div>
                        <div class="text-center my-2">
                            <a :href="`${base}${loginPath}`" class="text-gray-400">{{ t('page.password_reset.tologin') }}</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <ICPInformation />
        <AppGlobal />
    </div>
</template>

<style scoped>
:deep(input) {
    text-align: center !important;
    padding: 10px !important;
}

/* :deep(input::placeholder) {
    color: #ccc;
} */
</style>
