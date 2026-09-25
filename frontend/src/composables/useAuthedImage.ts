/**
 * 鉴权图片加载：图片端点要求登录态，而 <img src> 无法携带 Authorization 头，
 * 因此统一用 fetch 取 blob 再转 objectURL。
 *
 * 生命周期跟随调用方组件作用域：source 变化时换图并释放旧 objectURL，
 * 组件卸载时一并释放，避免长时间浏览造成内存堆积。
 */
import { onScopeDispose, ref, watch, type Ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const API_BASE = '/api/v1'

export function useAuthedImage(source: () => string | null | undefined): {
  /** 可直接喂给 <img src> 的 blob 地址；加载中或失败时为 null */
  blobUrl: Ref<string | null>
  loading: Ref<boolean>
  failed: Ref<boolean>
} {
  const blobUrl = ref<string | null>(null)
  const loading = ref(false)
  const failed = ref(false)
  let currentObjectUrl: string | null = null

  /** 释放当前 objectURL（换图与卸载都必须走这里，否则内存泄漏）。 */
  function release(): void {
    if (currentObjectUrl) {
      URL.revokeObjectURL(currentObjectUrl)
      currentObjectUrl = null
    }
  }

  watch(
    source,
    async (path) => {
      release()
      blobUrl.value = null
      failed.value = false
      if (!path) return

      loading.value = true
      const auth = useAuthStore()
      try {
        const response = await fetch(`${API_BASE}${path}`, {
          headers: auth.token ? { Authorization: `Bearer ${auth.token}` } : {},
        })
        if (!response.ok) {
          failed.value = true
          return
        }
        const blob = await response.blob()
        // 快速切换时旧请求可能后到：只在仍指向同一 path 时采用结果
        if (source() !== path) return
        currentObjectUrl = URL.createObjectURL(blob)
        blobUrl.value = currentObjectUrl
      } catch {
        failed.value = true
      } finally {
        loading.value = false
      }
    },
    { immediate: true },
  )

  onScopeDispose(release)

  return { blobUrl, loading, failed }
}
