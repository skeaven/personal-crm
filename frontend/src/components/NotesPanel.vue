<script setup lang="ts">
/**
 * 备注面板：联系人详情页「往来」区的备注 Tab。
 * 备注是轻量文本（不同于活动/资金的表单弹窗），用行内新增与行内编辑的形态；
 * 家人可读，仅记录人本人可改删（按钮级隐藏，服务端仍兜底校验）。
 */
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { notesApi } from '@/api/records'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { NoteOut } from '@/api/types'

const props = defineProps<{ contactId: number }>()

const auth = useAuthStore()
const notes = ref<NoteOut[]>([])
const loading = ref(false)
const draft = ref('')
const saving = ref(false)
/** 正在行内编辑的备注 id（同一时刻至多一条）；编辑草稿单独存，取消即弃。 */
const editingId = ref<number | null>(null)
const editDraft = ref('')

/** 拉取备注列表（新→旧由后端保证）。 */
async function load(): Promise<void> {
  loading.value = true
  try {
    notes.value = await notesApi.list(props.contactId)
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 401)) ElMessage.error('备注加载失败')
  } finally {
    loading.value = false
  }
}

/** 新增一条备注，成功后清空输入框并刷新。 */
async function submitNew(): Promise<void> {
  const content = draft.value.trim()
  if (!content) return
  saving.value = true
  try {
    await notesApi.create({ contact_id: props.contactId, content })
    draft.value = ''
    ElMessage.success('已记下')
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  } finally {
    saving.value = false
  }
}

/** 进入行内编辑态。 */
function startEdit(note: NoteOut): void {
  editingId.value = note.id
  editDraft.value = note.content
}

/** 退出编辑态并丢弃草稿。 */
function cancelEdit(): void {
  editingId.value = null
  editDraft.value = ''
}

/** 保存行内编辑，成功后退出编辑态并刷新。 */
async function submitEdit(note: NoteOut): Promise<void> {
  const content = editDraft.value.trim()
  if (!content) return
  try {
    await notesApi.update(note.id, { content })
    cancelEdit()
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '保存失败')
  }
}

/** 删除备注（el-popconfirm 确认后调用；仅按钮可见者能触发，服务端兜底）。 */
async function removeNote(note: NoteOut): Promise<void> {
  try {
    await notesApi.remove(note.id)
    ElMessage.success('已删除')
    await load()
  } catch (error) {
    ElMessage.error(error instanceof ApiError ? error.message : '删除失败')
  }
}

/** 备注展示只取日期（创建时刻的时分没有信息量）。 */
function formatDate(value: string): string {
  return value.slice(0, 10)
}

onMounted(load)
watch(() => props.contactId, load)
</script>

<template>
  <div class="notes-panel">
    <div class="composer">
      <el-input
        v-model="draft"
        data-test="note-input"
        type="textarea"
        :rows="2"
        :maxlength="2000"
        show-word-limit
        placeholder="记一条备注：聊到了什么、答应过什么、留个线索…"
      />
      <div class="composer-actions">
        <el-button
          data-test="note-submit"
          type="primary"
          size="small"
          :loading="saving"
          :disabled="!draft.trim()"
          @click="submitNew"
        >
          记下
        </el-button>
      </div>
    </div>

    <el-timeline v-if="notes.length" class="note-list">
      <el-timeline-item
        v-for="note in notes"
        :key="note.id"
        :timestamp="formatDate(note.created_at)"
        placement="top"
      >
        <el-card shadow="always" data-test="note-item" class="note-card" :body-style="{ padding: '12px 16px' }">
          <template v-if="editingId === note.id">
            <el-input
              v-model="editDraft"
              data-test="note-edit-input"
              type="textarea"
              :rows="2"
              :maxlength="2000"
            />
            <div class="note-actions">
              <el-button size="small" @click="cancelEdit">取消</el-button>
              <el-button
                data-test="note-edit-save"
                type="primary"
                size="small"
                :disabled="!editDraft.trim()"
                @click="submitEdit(note)"
              >
                保存
              </el-button>
            </div>
          </template>
          <template v-else>
            <p class="note-content">{{ note.content }}</p>
            <div class="note-meta">
              <span>{{ note.owner_display_name }} 记于 {{ formatDate(note.created_at) }}</span>
              <span v-if="auth.user && note.owner_user_id === auth.user.id" class="note-ops">
                <el-button data-test="note-edit" text size="small" @click="startEdit(note)">
                  编辑
                </el-button>
                <el-popconfirm
                  title="删除这条备注？"
                  confirm-button-text="删除"
                  cancel-button-text="取消"
                  @confirm="removeNote(note)"
                >
                  <template #reference>
                    <el-button data-test="note-delete" text size="small" type="danger">
                      删除
                    </el-button>
                  </template>
                </el-popconfirm>
              </span>
            </div>
          </template>
        </el-card>
      </el-timeline-item>
    </el-timeline>
    <p v-else-if="!loading" class="empty">还没有备注，记下第一条吧</p>
  </div>
</template>

<style scoped>
.composer {
  margin-bottom: 16px;
}
.composer-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 8px;
}
.note-card {
  background: var(--crm-canvas);
  border: 1px solid var(--crm-line);
  border-radius: var(--crm-radius-float);
}
.note-content {
  margin: 0;
  color: var(--crm-ink);
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
.note-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
  color: var(--crm-muted);
  font-size: 13px;
}
.note-ops {
  display: inline-flex;
  gap: 4px;
}
.empty {
  margin: 0;
  padding: 12px 0;
  color: var(--crm-muted);
  font-size: 13px;
}
</style>
