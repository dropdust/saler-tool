<template>
  <el-dialog
    v-model="visible"
    :title="editing ? `编辑通道 · ${editing.name}` : '添加发送通道'"
    width="620px"
    @closed="reset"
  >
    <el-form label-width="130px">
      <el-form-item v-if="!editing" label="通道类型">
        <el-radio-group v-model="form.channel_type" @change="onChannelTypeChange">
          <el-radio-button value="email">邮件（P0）</el-radio-button>
          <el-radio-button value="sms">短信</el-radio-button>
          <el-radio-button value="social" disabled>社媒（二期）</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="!editing && manifests.length > 1" label="服务提供方">
        <el-select v-model="form.type_key" style="width: 100%">
          <el-option
            v-for="manifest in manifests"
            :key="manifest.type_key"
            :value="manifest.type_key"
            :label="manifest.display_name"
          />
        </el-select>
      </el-form-item>
      <el-form-item label="通道名称" required>
        <el-input v-model="form.name" placeholder="如：主发件箱-Alice / 短信-阿里云" />
      </el-form-item>

      <template v-if="presets.length">
        <el-form-item label="服务商模板">
          <el-select v-model="form.presetKey" style="width: 100%" @change="applyPreset">
            <el-option
              v-for="(preset, key) in presets"
              :key="key"
              :value="key"
              :label="String(preset.display ?? key)"
            />
          </el-select>
          <div v-if="presetNote" class="hint">{{ presetNote }}</div>
        </el-form-item>
      </template>

      <el-form-item
        v-for="(prop, key) in configProps"
        :key="key"
        :label="prop.title || String(key)"
        :required="(configSchema.required || []).includes(String(key)) && key !== 'secret'"
      >
        <el-input
          v-if="String(key) === 'secret'"
          v-model="form.secret"
          type="password"
          show-password
          :placeholder="editing ? '留空则保持原密钥不变' : '授权码/密钥（加密存储，不回显）'"
        />
        <el-select v-else-if="prop.enum" v-model="form.config[String(key)]" style="width: 100%">
          <el-option v-for="option in prop.enum" :key="option" :value="option" :label="option" />
        </el-select>
        <el-switch v-else-if="prop.type === 'boolean'" v-model="form.config[String(key)]" />
        <el-input-number
          v-else-if="prop.type === 'integer' || prop.type === 'number'"
          v-model="form.config[String(key)]"
          :min="0"
        />
        <el-input
          v-else
          v-model="form.config[String(key)]"
          :placeholder="prop.examples?.[0] || prop.description || ''"
        />
        <div v-if="prop.description && String(key) !== 'secret'" class="hint">{{ prop.description }}</div>
      </el-form-item>

      <el-divider content-position="left">发送身份</el-divider>
      <el-form-item v-if="form.channel_type === 'email'" label="发件人名称">
        <el-input v-model="form.identity.from_name" placeholder="如：Alice（外贸一部）" />
      </el-form-item>
      <el-form-item v-if="form.channel_type === 'email'" label="发件地址">
        <el-input v-model="form.identity.from_addr" placeholder="alice@example.com" />
      </el-form-item>
      <el-form-item v-if="form.channel_type === 'email'" label="回复地址">
        <el-input v-model="form.identity.reply_to" placeholder="留空则同发件地址" />
      </el-form-item>
      <el-form-item label="签名">
        <el-input v-model="form.identity.signature" placeholder="短信签名需服务商报备；邮件用于落款变量 {{signature}}" />
      </el-form-item>

      <el-divider content-position="left">发送限制</el-divider>
      <!-- 数值参数：三列并排时列内放不下「左 label + 150px 控件」，label 置顶并让控件撑满列宽，
           否则 el-input-number 被 flex 压缩后内部输入区塌缩到不可读、不可键入 -->
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="每日上限" label-position="top">
            <el-input-number v-model="form.daily_limit" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="条/分钟" label-position="top">
            <el-input-number v-model="form.rate_per_minute" :min="1" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="并发" label-position="top">
            <el-input-number v-model="form.concurrency" :min="1" :max="10" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="密钥仅加密保存在本机数据目录，界面、日志与导出均不回显明文（FR-006）。"
      />
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { ChannelManifest, ChannelRow, SchemaProperty } from '../../api/types'

const visible = ref(false)
const saving = ref(false)
const editing = ref<ChannelRow | null>(null)
const manifests = ref<ChannelManifest[]>([])
const emit = defineEmits<{ saved: [] }>()

const form = ref({
  channel_type: 'email' as 'email' | 'sms',
  type_key: 'smtp',
  name: '',
  presetKey: '',
  config: {} as Record<string, any>,
  secret: '',
  identity: { from_name: '', from_addr: '', reply_to: '', signature: '' },
  daily_limit: 200,
  rate_per_minute: 20,
  concurrency: 1,
})

const activeManifest = computed(
  () => manifests.value.find((item) => item.type_key === form.value.type_key) ?? null,
)
const configSchema = computed(() => activeManifest.value?.config_schema ?? {})
const presets = computed(() => activeManifest.value?.presets ?? {})
const presetNote = computed(() => {
  const preset = presets.value[form.value.presetKey]
  return preset ? String(preset.note ?? '') : ''
})
const configProps = computed(() => {
  const props = configSchema.value.properties ?? {}
  const out: Record<string, SchemaProperty> = {}
  for (const [key, prop] of Object.entries(props)) {
    if (key === 'provider' || key === 'preset') continue // 内部字段
    out[key] = prop
  }
  return out
})

function manifestFor(channelType: string): ChannelManifest[] {
  return manifests.value.filter((item) => item.kind === (channelType === 'email' ? 'mail' : 'sms'))
}

function onChannelTypeChange(value: string | number | boolean | undefined) {
  const list = manifestFor(String(value))
  if (list.length) form.value.type_key = list[0].type_key
  form.value.config = {}
  form.value.presetKey = list[0] ? (Object.keys(list[0].presets)[0] ?? '') : ''
  applyPreset()
}

function applyPreset() {
  const preset = presets.value[form.value.presetKey]
  if (!preset) return
  for (const [key, value] of Object.entries(preset)) {
    if (key === 'display' || key === 'note') continue
    form.value.config[key] = value
  }
}

function open(channel: ChannelRow | null, allManifests: ChannelManifest[]) {
  manifests.value = allManifests
  editing.value = channel
  if (channel) {
    const typeKey = String((channel.config?.provider as string) || 'smtp')
    form.value = {
      channel_type: channel.channel_type,
      type_key: typeKey,
      name: channel.name,
      presetKey: String((channel.config?.preset as string) || ''),
      config: { ...channel.config },
      secret: '',
      identity: {
        from_name: (channel.identity?.from_name as string) || '',
        from_addr: (channel.identity?.from_addr as string) || '',
        reply_to: (channel.identity?.reply_to as string) || '',
        signature: (channel.identity?.signature as string) || '',
      },
      daily_limit: channel.daily_limit,
      rate_per_minute: channel.rate_per_minute,
      concurrency: channel.concurrency,
    }
  } else {
    form.value = {
      channel_type: 'email',
      type_key: manifestFor('email')[0]?.type_key ?? 'smtp',
      name: '',
      presetKey: '',
      config: {},
      secret: '',
      identity: { from_name: '', from_addr: '', reply_to: '', signature: '' },
      daily_limit: 200,
      rate_per_minute: 20,
      concurrency: 1,
    }
    onChannelTypeChange('email')
  }
  visible.value = true
}

function reset() {
  saving.value = false
}

async function submit() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请填写通道名称')
    return
  }
  const config: Record<string, unknown> = { provider: form.value.type_key }
  for (const [key, value] of Object.entries(form.value.config)) {
    if (key === 'provider' || key === 'preset') continue
    if (value !== '' && value !== null && value !== undefined) config[key] = value
  }
  if (form.value.presetKey) config.preset = form.value.presetKey
  const identity: Record<string, string> = {}
  for (const [key, value] of Object.entries(form.value.identity)) {
    if (value) identity[key] = value
  }
  const payload: Record<string, unknown> = {
    name: form.value.name,
    config,
    identity,
    daily_limit: form.value.daily_limit,
    rate_per_minute: form.value.rate_per_minute,
    concurrency: form.value.concurrency,
  }
  if (form.value.secret) payload.secret = form.value.secret
  saving.value = true
  try {
    if (editing.value) {
      await api.put(`/channels/${editing.value.id}`, payload)
    } else {
      await api.post('/channels', { ...payload, channel_type: form.value.channel_type })
    }
    ElMessage.success('已保存（建议立即运行「测试」验证凭据）')
    visible.value = false
    emit('saved')
  } finally {
    saving.value = false
  }
}

defineExpose({ open })
</script>

<style scoped>
.hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
