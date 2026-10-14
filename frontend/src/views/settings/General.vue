<template>
  <div>
    <PageHeader
      title="通用设置"
      description="界面语言、网络代理、抓取与发送默认值；数据资产保存在本机，可在此迁移目录。"
    />
    <el-row :gutter="16">
      <el-col :span="14">
        <el-card v-loading="loading" shadow="never">
          <template #header>基础设置</template>
          <el-form label-width="140px">
            <el-form-item label="界面语言">
              <el-select v-model="form.ui_lang" style="width: 200px">
                <el-option label="中文" value="zh-CN" />
              </el-select>
            </el-form-item>
            <el-form-item label="内容回退语言">
              <el-select v-model="form.content_fallback_lang" style="width: 200px">
                <el-option v-for="lang in LANGS" :key="lang.code" :value="lang.code" :label="`${lang.label}（${lang.code}）`" />
              </el-select>
              <span class="hint">客户语言缺少对应内容版本时使用</span>
            </el-form-item>
            <el-form-item label="网络代理">
              <el-input
                v-model="form.proxy"
                style="width: 320px"
                placeholder="http://127.0.0.1:7897（访问海外站点用，可留空）"
              />
            </el-form-item>

            <el-divider content-position="left">抓取默认值</el-divider>
            <el-form-item label="并发数">
              <el-input-number v-model="form.crawl.concurrency" :min="1" :max="20" />
            </el-form-item>
            <el-form-item label="单站间隔（秒）">
              <el-input-number v-model="form.crawl.per_host_delay_s" :min="0.2" :max="10" :step="0.2" />
            </el-form-item>
            <el-form-item label="单站页数上限">
              <el-input-number v-model="form.crawl.max_pages_per_site" :min="1" :max="50" />
            </el-form-item>
            <el-form-item label="遵循 robots.txt">
              <el-switch v-model="form.crawl.respect_robots" />
              <span class="hint">关闭后抓取的合规责任由用户自行承担</span>
            </el-form-item>
            <el-form-item label="请求超时（秒）">
              <el-input-number v-model="form.crawl.timeout_s" :min="5" :max="120" />
            </el-form-item>

            <el-divider content-position="left">发送默认值</el-divider>
            <el-form-item label="每分钟上限">
              <el-input-number v-model="form.send.rate_per_minute" :min="1" :max="600" />
            </el-form-item>
            <el-form-item label="每日上限">
              <el-input-number v-model="form.send.daily_max" :min="1" :max="5000" />
            </el-form-item>
          </el-form>
          <el-button type="primary" :loading="saving" @click="save">保存设置</el-button>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="never">
          <template #header>数据目录（数据资产保存在本机）</template>
          <p>
            当前目录：<code>{{ currentDir || '…' }}</code>
          </p>
          <el-alert
            v-if="dirStatus"
            class="mb"
            :type="dirOk ? 'success' : 'error'"
            :title="dirStatus"
            :closable="false"
          />
          <el-form label-width="90px">
            <el-form-item label="迁移到">
              <el-input v-model="newDir" placeholder="新目录绝对路径（须为空目录）" />
            </el-form-item>
          </el-form>
          <el-button @click="validateDir">校验目录</el-button>
          <el-button type="warning" :loading="moving" @click="moveDir">迁移数据</el-button>
          <p class="hint">迁移 = 复制 → 核对 → 切换指针；旧数据保留在原位置，重启应用后生效。</p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '../../api/client'
import { useJobCenterStore } from '../../stores/jobCenter'
import PageHeader from '../../components/common/PageHeader.vue'
import { LANGS } from '../../constants'

const loading = ref(false)
const jobCenter = useJobCenterStore()
const saving = ref(false)
const form = ref({
  ui_lang: 'zh-CN',
  content_fallback_lang: 'en',
  proxy: '',
  crawl: {
    concurrency: 5,
    per_host_delay_s: 1,
    max_pages_per_site: 6,
    respect_robots: true,
    timeout_s: 20,
  },
  send: { rate_per_minute: 20, daily_max: 200 },
})

const currentDir = ref('')
const newDir = ref('')
const dirStatus = ref('')
const dirOk = ref(false)
const moving = ref(false)

async function load() {
  loading.value = true
  try {
    const settings = await api.get<Record<string, unknown>>('/settings')
    form.value.ui_lang = String(settings.ui_lang ?? 'zh-CN')
    form.value.content_fallback_lang = String(settings.content_fallback_lang ?? 'en')
    form.value.proxy = String(settings.proxy ?? '')
    form.value.crawl = { ...form.value.crawl, ...(settings.crawl_defaults as object) }
    form.value.send = { ...form.value.send, ...(settings.send_defaults as object) }
    const dir = await api.get<{ data_dir: string }>('/settings/data-dir')
    currentDir.value = dir.data_dir
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await api.put('/settings', {
      values: {
        ui_lang: form.value.ui_lang,
        content_fallback_lang: form.value.content_fallback_lang,
        proxy: form.value.proxy,
        crawl_defaults: form.value.crawl,
        send_defaults: form.value.send,
      },
    })
    ElMessage.success('设置已保存')
  } finally {
    saving.value = false
  }
}

async function validateDir() {
  if (!newDir.value.trim()) {
    ElMessage.warning('请填写目标目录')
    return
  }
  const body = await api.post<{ ok: boolean; message: string }>('/settings/data-dir/validate', {
    path: newDir.value.trim(),
  })
  dirOk.value = body.ok
  dirStatus.value = body.ok ? '目录可用' : body.message
}

async function moveDir() {
  if (!newDir.value.trim()) {
    ElMessage.warning('请填写目标目录')
    return
  }
  await ElMessageBox.confirm(
    `将把数据目录迁移到：${newDir.value.trim()}\n旧数据会保留在原位置，重启应用后生效。`,
    '确认迁移',
    { type: 'warning' },
  )
  moving.value = true
  try {
    const { job_id } = await api.post<{ job_id: number }>('/settings/data-dir/move', {
      path: newDir.value.trim(),
    })
    const job = await jobCenter.waitFor(job_id)
    if (job.status === 'completed') {
      dirOk.value = true
      dirStatus.value = `迁移完成（${job.result?.files_copied ?? '?'} 个文件已核对）：重启应用后生效`
      ElMessage.success('迁移完成，重启后生效')
    } else {
      ElMessage.error(job.error ?? '迁移失败')
    }
  } finally {
    moving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hint {
  margin-left: 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.mb {
  margin-bottom: 12px;
}
</style>
