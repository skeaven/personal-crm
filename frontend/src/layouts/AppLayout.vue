<script setup lang="ts">
/** 应用主布局：侧边导航 + 内容区。助理为导航中的独立页面。 */
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatbubbleEllipsesOutline,
  GitNetworkOutline,
  LocationOutline,
  MenuOutline,
  GiftOutline,
  HeartOutline,
  HomeOutline,
  PeopleOutline,
  SettingsOutline,
  Sparkles,
  SwapHorizontalOutline,
  TerminalOutline,
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import { sealBrand } from '@/design/theme'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

/** 导航配置数组：新功能页在此登记，不改布局结构（扩展性约定 4）。 */
const navItems = [
  { key: 'home', label: '主页', icon: HomeOutline, to: '/home' },
  { key: 'assistant', label: '助理', icon: Sparkles, to: '/assistant' },
  { key: 'contacts', label: '名册', icon: PeopleOutline, to: '/contacts' },
  { key: 'graph', label: '图谱', icon: GitNetworkOutline, to: '/graph' },
  { key: 'map', label: '地图', icon: LocationOutline, to: '/map' },
  { key: 'activities', label: '活动', icon: ChatbubbleEllipsesOutline, to: '/activities' },
  { key: 'tasks', label: '待办', icon: TerminalOutline, to: '/tasks' },
  { key: 'gifts', label: '礼物', icon: GiftOutline, to: '/gifts' },
  { key: 'wishlist', label: '心愿', icon: HeartOutline, to: '/wishlist' },
  { key: 'funds', label: '资金', icon: SwapHorizontalOutline, to: '/funds' },
]

/** 官方 el-menu 按 path 匹配激活态；详情页归属名册。 */
const activeMenu = computed(() => {
  if (route.name === 'contact-detail') return '/contacts'
  return route.path
})

/** 窄屏（<768px，iPad 宽度）抽屉式导航：侧栏隐藏，菜单按钮唤起覆盖层。 */
const menuOpen = ref(false)

/** 退出登录并回到登录页。 */
function handleLogout(): void {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<template>
  <div class="app-shell">
    <aside class="app-sidebar">
      <div class="brand">
        <span class="brand-seal">{{ sealBrand.text }}</span>
        <span class="brand-name crm-display">个人名册</span>
      </div>
      <el-menu :default-active="activeMenu" class="side-menu" router>
        <el-menu-item v-for="item in navItems" :key="item.key" :index="item.to">
          <component :is="item.icon" class="nav-icon" />
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>
      <div class="sidebar-footer">
        <el-menu :default-active="'/settings'" class="side-menu" router>
          <el-menu-item index="/settings">
            <component :is="SettingsOutline" class="nav-icon" />
            <template #title>设置</template>
          </el-menu-item>
        </el-menu>
        <div class="user-name">{{ auth.user?.display_name }}</div>
        <el-button text class="logout-btn" @click="handleLogout">
          退出登录
        </el-button>
      </div>
    </aside>
    <main class="app-content">
      <router-view v-slot="{ Component }">
        <component :is="Component" class="crm-rise" />
      </router-view>
    </main>

    <!-- 窄屏菜单按钮：仅 <768px 显示（样式控制），点击唤起覆盖式抽屉导航 -->
    <el-button class="menu-toggle" :icon="MenuOutline" circle aria-label="打开菜单" @click="menuOpen = true" />
    <el-drawer v-model="menuOpen" direction="ltr" size="220px" :with-header="false" class="menu-drawer">
      <div class="drawer-brand">
        <span class="brand-seal">{{ sealBrand.text }}</span>
        <span class="brand-name crm-display">个人名册</span>
      </div>
      <el-menu :default-active="activeMenu" class="side-menu" router @select="menuOpen = false">
        <el-menu-item v-for="item in navItems" :key="item.key" :index="item.to">
          <component :is="item.icon" class="nav-icon" />
          <template #title>{{ item.label }}</template>
        </el-menu-item>
        <el-menu-item index="/settings">
          <component :is="SettingsOutline" class="nav-icon" />
          <template #title>设置</template>
        </el-menu-item>
      </el-menu>
      <div class="drawer-footer">
        <div class="user-name">{{ auth.user?.display_name }}</div>
        <el-button text class="logout-btn" @click="handleLogout">退出登录</el-button>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
}
.app-sidebar {
  width: var(--crm-sidebar-width, 148px);
  flex-shrink: 0;
  background: var(--crm-bone);
  border-right: 1px solid var(--crm-line);
  display: flex;
  flex-direction: column;
  padding: 22px 12px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 6px 26px;
}
.brand-seal {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  background: var(--crm-seal);
  color: #fff;
  font-family: var(--crm-font-seal);
  font-size: 20px;
  border-radius: var(--crm-radius-control);
  flex-shrink: 0;
}
.brand-name {
  font-size: 17px;
  color: var(--crm-ink);
  white-space: nowrap;
}
.nav-icon {
  width: 17px;
  height: 17px;
  font-size: 17px;
  flex-shrink: 0;
}
.nav-label {
  white-space: nowrap;
}
.sidebar-footer {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 6px 8px;
}
.user-name {
  font-size: 14px;
  color: var(--crm-ink);
  padding: 0 6px;
}
.logout-btn {
  justify-content: flex-start;
  padding: 0 6px;
}
.app-content {
  flex: 1;
  min-width: 0;
  padding: 44px 52px;
}
.drawer-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 6px 22px;
}
.drawer-footer {
  margin-top: auto;
  padding: 8px 6px 4px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.menu-drawer .el-drawer__body {
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
}

/* 窄屏（<iPad 宽度 768px）：侧栏收起，只留菜单按钮，导航走覆盖抽屉 */
.menu-toggle {
  display: none;
  position: fixed;
  top: 14px;
  left: 14px;
  z-index: 2001;
  box-shadow: var(--crm-shadow-hover);
}
@media (max-width: 768px) {
  .app-sidebar {
    display: none;
  }
  .menu-toggle {
    display: inline-flex;
  }
}
@media (max-width: 768px) {
  .app-content {
    padding: 64px 16px 20px; /* 顶部给悬浮菜单按钮留位，避免遮挡页内返回链接 */
  }
}
</style>
