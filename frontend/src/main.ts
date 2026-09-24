/** 应用入口：pinia + router + Element Plus 全量注册（中文 locale）+ tokens 样式。
 * 样式装载顺序：Element Plus 官方样式 → tokens 映射层（--el-* 覆写）→ 全局样式。 */
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import 'element-plus/dist/index.css'
import './design/element-plus.css'
import App from './App.vue'
import router from './router'
import './design/style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(ElementPlus, { locale: zhCn })
app.mount('#app')
