<script setup lang="ts">
import ICPInformation from '@/components/ICPInformation.vue';
import AppGlobal from '@/layout/AppGlobal.vue';
import { showLoading, hideLoading, showToast } from '@/utils/GlobalUtil';
import { AuthService } from '@/services/AuthService';
import { promise2, debounce, validEmail, gotoRoute } from '@/utils/Common';
import { useI18n } from 'vue-i18n';
const { t } = useI18n();
const registerEmail = ref('');
const contactUsVisible = ref(false);
const createResetPasswdLink = (e: any) => {
    debounce(
        async () => {
            let email = registerEmail.value;
            if (!email || email.trim().length == 0) {
                showToast('warn', t('page.common.warn'), t('page.register.inputemail'));
                return;
            }

            if (!validEmail(email)) {
                showToast('error', t('page.common.error'), t('page.register.emailerror'));
                return;
            }

            showLoading();
            let data = { email: email.trim() };
            const [err, res] = await promise2(AuthService.createResetPasswdCode(data));
            hideLoading();
            if (err && err.message) {
                return;
            }
            if (res && res.code == 2000) {
                showToast('success', t('page.common.success'), t('page.password_forgot.linksuccess'), false);
                setTimeout(() => {
                    gotoRoute('/password-reset');
                }, 1500);
            }
        },
        1000,
        e
    );
};

const showContact = () => {
    contactUsVisible.value = true;
};
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
                            <h1 class="font-bold">{{ t('page.password_forgot.title') }}</h1>
                            <p class="text-gray-500 text-50">{{ t('page.password_forgot.note') }}</p>
                        </div>
                        <div class="text-center">
                            <InputText v-model="registerEmail" id="email1" type="text" :placeholder="t('page.password_forgot.input')" class="md:w-[30rem] text-lg text-center" style="padding: 10px" maxLength="50" />
                            <Button
                                :label="t('page.password_forgot.button')"
                                class="md:w-[30rem] my-3 text-lg"
                                @click="createResetPasswdLink"
                                :style="{ padding: '10px', cursor: validEmail(registerEmail) ? 'pointer' : 'not-allowed' }"
                                :disabled="!validEmail(registerEmail)"
                            />
                        </div>
                        <div class="text-center text-gray-500 text-50 my-10" style="width: 500px">
                            {{ t('page.password_forgot.contact1') }}<a href="#" class="text-primary" @click="showContact">{{ t('page.password_forgot.contact2') }}</a
                            >{{ t('page.password_forgot.contact3') }}
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <Drawer v-model:visible="contactUsVisible" :header="t('page.password_forgot.contact_header')">
            <div v-html="t('page.password_forgot.contact_content')" class="text-gray-500 leading-8"></div>
        </Drawer>
        <ICPInformation />
        <AppGlobal />
    </div>
</template>

<style scoped>
/* :deep(input::placeholder) {
    color: #ccc;
} */
</style>
