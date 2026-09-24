<script setup lang="ts">
/** 登录页：左骨灰白品牌区（印章记忆点 + 墨色大字）+ 右纯白表单，移动端单列。 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { ApiError } from '@/api/client'
import { sealBrand } from '@/design/theme'

const auth = useAuthStore()
const router = useRouter()


const username = ref('')
const password = ref('')
const submitting = ref(false)

/** 提交登录；失败展示后端返回的可读错误。 */
async function handleSubmit(): Promise<void> {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  submitting.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    router.push({ name: 'home' })
  } catch (error) {
    const text = error instanceof ApiError ? error.message : '登录失败，请稍后再试'
    ElMessage.error(text)
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <section class="brand-pane">
      <div class="brand-lockup crm-rise">
        <span class="brand-seal">{{ sealBrand.text }}</span>
        <h1 class="brand-title crm-display">个人名册</h1>
        <p class="brand-motto">把重要的人，认真记住。</p>
      </div>
    </section>
    <section class="form-pane">
      <form class="login-form crm-rise" @submit.prevent="handleSubmit">
        <h2 class="form-title crm-display">登录</h2>
        <label class="field">
          <span class="field-label">用户名</span>
          <el-input v-model="username" size="large" placeholder="用户名" :input-props="{ autocomplete: 'username' }" />
        </label>
        <label class="field">
          <span class="field-label">密码</span>
          <el-input
            v-model="password"
            size="large"
            type="password"
            show-password
            placeholder="密码"
            :input-props="{ autocomplete: 'current-password' }"
          />
        </label>
        <el-button native-type="submit" type="primary" class="submit-btn" size="large" :loading="submitting">登 录</el-button>
      </form>
    </section>
  </div>
</template>

<style scoped>
.login-page {
  display: flex;
  min-height: 100vh;
}
.brand-pane {
  flex: 1.1;
  background: var(--crm-bone);
  border-right: 1px solid var(--crm-line);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
}
.brand-lockup {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 20px;
}
.brand-seal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 72px;
  height: 72px;
  background: var(--crm-seal);
  color: #fff;
  font-family: var(--crm-font-seal);
  font-size: 44px;
  border-radius: var(--crm-radius-control);
}
.brand-title {
  margin: 0;
  font-size: 40px;
  color: var(--crm-ink);
}
.brand-motto {
  margin: 0;
  color: var(--crm-muted);
  font-size: 16px;
  letter-spacing: 0.08em;
}
.form-pane {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--crm-canvas);
  padding: 48px;
}
.submit-btn {
  width: 100%;
}
.login-form {
  width: 100%;
  max-width: 340px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.form-title {
  margin: 0 0 4px;
  font-size: 30px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.field-label {
  font-size: 14px;
  color: var(--crm-muted);
}
@media (max-width: 720px) {
  .login-page {
    flex-direction: column;
  }
  .brand-pane {
    flex: none;
    padding: 36px 24px;
  }
  .form-pane {
    flex: 1;
    padding: 32px 24px;
  }
}
</style>
