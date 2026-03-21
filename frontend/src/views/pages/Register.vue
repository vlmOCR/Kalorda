<script setup lang="ts">
import ICPInformation from '@/components/ICPInformation.vue';
import FloatingConfigurator from '@/components/FloatingConfigurator.vue';
import AppGlobal from '@/layout/AppGlobal.vue';
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil';
import { useLayout } from '@/layout/composables/layout';
import { AuthService } from '@/services/AuthService';
import { gotoRoute, promise2, debounce } from '@/utils/Common';
import { useI18n } from 'vue-i18n';
import { getLanguage } from '@/assets/lang/language';
const { isDarkTheme } = useLayout();
const { t } = useI18n();

// 检查是否可以外部注册
const freeRegist = ref(false);
const getFreeRegist = async () => {
    const [err, res] = await promise2(AuthService.freeRegist());
    if (err && err.message) {
        return;
    }
    if (res && res.code == 2000) {
        freeRegist.value = res.data;
    }
};

const base = import.meta.env.VITE_APP_BASE;
const loginPath = import.meta.env.VITE_LOGIN_PATH;

const registerEmail = ref('');
const userName = ref('');
const password1 = ref('');
const password2 = ref('');
const agree = ref(false);
const agreeChange = () => {
    agree.value = !agree.value;
};

const register = (e: any) => {
    debounce(
        async () => {
            if (!freeRegist.value) {
                showToast('error', t('page.common.error'), t('page.register.notallowregist'));
                return;
            }
            if (!agree.value) {
                showToast('warn', t('page.common.warn'), t('page.register.hasnoagree'));
                return;
            }
            // 前端不验了，后端验证
            let data = {
                username: userName.value,
                email: registerEmail.value,
                password: password1.value
            };
            showLoading();
            const [err, res] = await promise2(AuthService.userRegister(data));
            hideLoading();
            if (err && err.message) {
                showToast('error', t('page.common.error'), err.message);
                return;
            }
            if (res && res.code == 2000) {
                showToast('success', t('page.common.success'), t('page.register.registersuccess'), false);
                setTimeout(() => {
                    gotoRoute(loginPath, { email: registerEmail.value });
                }, 2000);
            }
        },
        1000,
        e
    );
};

onMounted(async () => {
    await getFreeRegist();
});
</script>

<template>
    <div>
        <!-- 页面背景 -->
        <div style="position: absolute; top: 0; left: 0; z-index: 0">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 800" class="fixed left-0 top-0 min-h-screen min-w-[100vw]" preserveAspectRatio="none">
                <rect :fill="'var(--p-' + (isDarkTheme ? 'surface' : 'primary') + '-600)'" width="1600" height="800"></rect>
                <path
                    :fill="'var(--p-' + (isDarkTheme ? 'surface' : 'primary') + '-800)'"
                    d="M478.4 581c3.2 0.8 6.4 1.7 9.5 2.5c196.2 52.5 388.7 133.5 593.5 176.6c174.2 36.6 349.5 29.2 518.6-10.2V0H0v574.9c52.3-17.6 106.5-27.7 161.1-30.9C268.4 537.4 375.7 554.2
        478.4 581z"
                ></path>
                <path
                    :fill="'var(--p-' + (isDarkTheme ? 'surface' : 'primary') + '-300)'"
                    d="M181.8 259.4c98.2 6 191.9 35.2 281.3 72.1c2.8 1.1 5.5 2.3 8.3 3.4c171 71.6 342.7 158.5 531.3 207.7c198.8 51.8 403.4 40.8 597.3-14.8V0H0v283.2C59 263.6 120.6 255.7 181.8 259.4z"
                ></path>
                <path
                    :fill="'var(--p-' + (isDarkTheme ? 'surface' : 'primary') + '-200)'"
                    d="M454.9 86.3C600.7 177 751.6 269.3 924.1 325c208.6 67.4 431.3 60.8 637.9-5.3c12.8-4.1 25.4-8.4 38.1-12.9V0H288.1c56 21.3 108.7 50.6 159.7 82C450.2 83.4 452.5 84.9 454.9 86.3z"
                ></path>
                <path
                    :fill="'var(--p-' + (isDarkTheme ? 'surface' : 'primary') + '-50)'"
                    d="M1397.5 154.8c47.2-10.6 93.6-25.3 138.6-43.8c21.7-8.9 43-18.8 63.9-29.5V0H643.4c62.9 41.7 129.7 78.2 202.1 107.4C1020.4 178.1 1214.2 196.1 1397.5 154.8z"
                ></path>
            </svg>
        </div>
        <FloatingConfigurator style="z-index: 2" />
        <div class="flex items-center justify-center min-h-screen min-w-[100vw] overflow-hidden">
            <div class="flex flex-col items-center justify-center" style="z-index: 1">
                <div style="border-radius: 56px; padding: 0.3rem; background: linear-gradient(180deg, var(--primary-color) 10%, rgba(33, 150, 243, 0) 30%)">
                    <div class="bg-surface-100 dark:bg-surface-900 w-full py-5 px-8 sm:px-20" style="border-radius: 53px; opacity: 0.95">
                        <div class="text-center mb-8">
                            <div style="display: flex; justify-content: center; align-items: center">
                                <img src="/logo.svg" width="58" height="58" class="py-5" />
                            </div>
                            <div class="text-3xl font-medium mb-4">{{ t('page.register.welcome') }}</div>
                            <span class="text-muted-color font-medium">{{ t('page.login.slogan') }}</span>
                        </div>

                        <div>
                            <div style="display: flex; justify-content: space-between; padding: 0">
                                <label for="email" class="block text-xl font-medium mb-2">{{ t('page.login.email') }}</label>
                                <label for="userName" class="block text-xl font-medium mb-2">{{ t('page.register.username') }}</label>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 0">
                                <InputText
                                    id="email"
                                    v-tooltip.bottom="t('page.register.emailtooltip', ['@'])"
                                    type="text"
                                    :placeholder="t('page.login.emailaddress')"
                                    class="w-full md:w-[15rem] mb-8"
                                    v-model="registerEmail"
                                    :disabled="!freeRegist"
                                    maxLength="50"
                                />
                                <InputText
                                    id="username"
                                    v-tooltip.bottom="t('page.register.usenametooltip')"
                                    type="text"
                                    :placeholder="t('page.register.username')"
                                    class="w-full md:w-[15rem] mb-8"
                                    v-model="userName"
                                    autocomplete="off"
                                    :disabled="!freeRegist"
                                    maxLength="20"
                                />
                            </div>

                            <div style="display: flex; justify-content: space-between; padding: 0">
                                <label for="password1" class="block font-medium text-xl mb-2">{{ t('page.register.setpassword') }}</label>
                                <label for="password2" class="block font-medium text-xl mb-2">{{ t('page.register.confirmpassword') }}</label>
                            </div>
                            <div style="display: flex; justify-content: space-between; padding: 0">
                                <InputText
                                    id="password1"
                                    v-tooltip.bottom="t('page.register.passwordtooltip')"
                                    v-model="password1"
                                    :placeholder="t('page.register.yourpassword')"
                                    :toggleMask="true"
                                    class="md:w-[15rem] mb-4"
                                    fluid
                                    :feedback="false"
                                    autocomplete="off"
                                    :disabled="!freeRegist"
                                    maxLength="50"
                                ></InputText>
                                <InputText
                                    id="password2"
                                    v-model="password2"
                                    :placeholder="t('page.register.yourconfirmpassword')"
                                    :toggleMask="true"
                                    class="md:w-[15rem] mb-4"
                                    fluid
                                    :feedback="false"
                                    autocomplete="off"
                                    :disabled="!freeRegist"
                                    maxLength="50"
                                ></InputText>
                            </div>

                            <div class="flex items-center justify-between mb-8 gap-8">
                                <div class="flex items-center">
                                    <Checkbox v-model="agree" id="rememberme1" binary class="mr-2"></Checkbox>
                                    <label for="rememberme1" class="block"
                                        ><span @click="agreeChange">{{ t('page.register.agree') }}</span
                                        ><a :href="`${base}/static/${getLanguage().code}/terms.html`" target="_blank" class="text-primary">{{ t('page.register.terms') }}</a
                                        >{{ t('page.register.and') }}<a :href="`${base}/static/${getLanguage().code}/privacy.html`" target="_blank" class="text-primary">{{ t('page.register.privacy') }}</a></label
                                    >
                                </div>
                            </div>
                            <Button :label="t('page.register.register')" class="w-full" as="router-link" to="" @click="register"></Button>
                            <div class="text-center py-5">
                                {{ t('page.register.haveaccount') }} <a :href="`${base}${loginPath}`" class="text-primary">{{ t('page.register.loginlink') }}</a>
                            </div>
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
.pi-eye {
    transform: scale(1.6);
    margin-right: 1rem;
}

.pi-eye-slash {
    transform: scale(1.6);
    margin-right: 1rem;
}

#password1,
#password2 {
    text-security: disc;
    -webkit-text-security: disc;
}
</style>
