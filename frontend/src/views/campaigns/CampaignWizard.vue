<template>
  <el-dialog v-model="visible" title="新建营销计划" width="720px" top="4vh" @closed="reset">
    <el-steps :active="step" finish-status="success" simple class="steps">
      <el-step title="人群" />
      <el-step title="内容与语言" />
      <el-step title="通道" />
      <el-step title="节奏" />
      <el-step title="预估确认" />
    </el-steps>

    <!-- 步骤 1：人群 -->
    <el-form v-show="step === 0" label-width="130px">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="mb"
        title="圈选说明：留空表示不限；已排除客户、已回复/已成交/已拒绝客户与退订对象默认不进人群。"
      />
      <el-form-item label="国家（逗号分隔）">
        <el-input v-model="audience.countryText" placeholder="如：KE,NG,TZ（公司国家码）" />
      </el-form-item>
      <el-form-item label="语言（逗号分隔）">
        <el-input v-model="audience.languageText" placeholder="如：en,sw（公司使用语言）" />
      </el-form-item>
      <el-form-item label="公司状态">
        <el-select v-model="audience.status" multiple style="width: 100%">
          <el-option value="new" label="新客户" />
          <el-option value="contacted" label="已触达" />
        </el-select>
        <div class="hint">已回复/已成交/已拒绝/无效 一律排除（跟进与排除逻辑即时生效）</div>
      </el-form-item>
      <el-form-item label="标签（逗号分隔）">
        <el-input v-model="audience.tagsText" placeholder="如：vip,distributor" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="目标数量上限" label-width="130px">
            <el-input-number v-model="audience.max_count" :min="0" :step="10" />
            <div class="hint">0 或留空 = 不限</div>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="允许重发" label-width="100px">
            <el-switch v-model="audience.allow_resend" />
            <div class="hint">默认跳过所有已触达客户（防重复打扰）</div>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <!-- 步骤 2：内容与语言 -->
    <el-form v-show="step === 1" label-width="130px">
      <el-form-item label="内容主题" required>
        <el-select v-model="form.content_theme_id" style="width: 100%" placeholder="仅可选择已发布内容的主题">
          <el-option
            v-for="theme in publishedThemes"
            :key="theme.theme_id"
            :value="theme.theme_id"
            :label="`${theme.theme_name}（${theme.langs.map((l) => langLabel(l)).join('/')}）`"
          />
        </el-select>
        <div v-if="!publishedThemes.length" class="hint warn">
          尚无已发布内容：请先在「营销内容」中创建主题并发布至少一个语言版本（先审后发）
        </div>
      </el-form-item>
      <el-form-item label="语言策略">
        <el-radio-group v-model="form.lang_strategy">
          <el-radio-button value="auto">自动匹配客户语言</el-radio-button>
          <el-radio-button value="fixed">固定语言</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item v-if="form.lang_strategy === 'fixed'" label="固定语言">
        <el-select v-model="form.fixed_lang" style="width: 100%">
          <el-option v-for="lang in LANGS" :key="lang.code" :value="lang.code" :label="`${lang.label}（${lang.code}）`" />
        </el-select>
      </el-form-item>
      <el-form-item label="缺失回退语言">
        <el-select v-model="form.fallback_lang" clearable style="width: 100%" placeholder="默认 en（回退时台账标注）">
          <el-option v-for="lang in LANGS" :key="lang.code" :value="lang.code" :label="`${lang.label}（${lang.code}）`" />
        </el-select>
      </el-form-item>
    </el-form>

    <!-- 步骤 3：通道 -->
    <el-form v-show="step === 2" label-width="130px">
      <el-form-item label="发送通道" required>
        <el-select v-model="form.channel_ids" multiple style="width: 100%">
          <el-option
            v-for="channel in channels"
            :key="channel.id"
            :value="channel.id"
            :label="`${channel.name}（${channel.channel_type === 'email' ? '邮件' : '短信'}，${healthLabel(channel.health)}）`"
            :disabled="channel.status !== 'active'"
          />
        </el-select>
        <div class="hint">选择顺序即优先级：第一个为主通道，其余作为失败切换的备用通道</div>
      </el-form-item>
      <el-alert
        v-if="!channels.length"
        type="warning"
        :closable="false"
        show-icon
        title="尚未配置发送通道：请先到「营销通道」完成配置并测试连通"
      />
    </el-form>

    <!-- 步骤 4：节奏 -->
    <el-form v-show="step === 3" label-width="130px">
      <el-form-item label="开始方式">
        <el-radio-group v-model="form.mode">
          <el-radio-button value="immediate">立即开始（确认后启动）</el-radio-button>
          <el-radio-button value="manual" disabled>定时（后续版本）</el-radio-button>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="每日计划上限">
        <el-input-number v-model="form.daily_max" :min="0" :step="50" />
        <div class="hint">0 = 不限（仍受各通道自身限额约束）；跨日自动续发</div>
      </el-form-item>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="发送按通道限额节流；任何时候可暂停/恢复/中止，台账记录每条去向。"
      />
    </el-form>

    <!-- 步骤 5：预估确认 -->
    <div v-show="step === 4">
      <p v-if="!estimate" class="hint">点击下方「创建并预估」查看影响范围。</p>
      <template v-else>
        <el-descriptions :column="3" border>
          <el-descriptions-item label="覆盖客户">{{ estimate.audience_count }}</el-descriptions-item>
          <el-descriptions-item label="消息条数">{{ estimate.message_count }}</el-descriptions-item>
          <el-descriptions-item label="预计时长">
            {{ estimate.eta_minutes >= 1440 ? `${Math.ceil(estimate.eta_minutes / 1440)} 天（按每日容量）` : `${estimate.eta_minutes} 分钟` }}
          </el-descriptions-item>
          <el-descriptions-item label="语言分布">
            {{ formatCounts(estimate.by_lang) || '—' }}
          </el-descriptions-item>
          <el-descriptions-item label="回退标注">{{ estimate.fallback_count }} 条</el-descriptions-item>
          <el-descriptions-item label="将被排除">
            退订 {{ estimate.suppressed }} · 已触达 {{ estimate.skipped }}
          </el-descriptions-item>
        </el-descriptions>
        <el-alert
          v-if="createdId"
          type="success"
          :closable="false"
          show-icon
          class="mb"
          title="计划已创建（草稿）。可先试发 2 封验证，再启动正式发送。"
        />
      </template>
    </div>

    <template #footer>
      <el-button v-if="step > 0" @click="step--">上一步</el-button>
      <el-button v-if="step < 4" type="primary" @click="next">下一步</el-button>
      <el-button v-else type="primary" :loading="working" @click="createAndEstimate">
        {{ createdId ? '重新预估' : '创建并预估' }}
      </el-button>
      <el-button v-if="createdId" type="success" :loading="working" @click="startNow">创建并启动</el-button>
      <el-button @click="visible = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { CampaignRow, ChannelRow, EstimateRow, PublishedVariantRow } from '../../api/types'
import { LANGS, langLabel } from '../../constants'

interface ThemeOption {
  theme_id: number
  theme_name: string
  langs: string[]
}

const visible = ref(false)
const step = ref(0)
const working = ref(false)
const emit = defineEmits<{ done: [] }>()

const channels = ref<ChannelRow[]>([])
const published = ref<PublishedVariantRow[]>([])
const estimate = ref<EstimateRow | null>(null)
const createdId = ref<number | null>(null)

const audience = ref({
  countryText: '',
  languageText: '',
  status: ['new', 'contacted'] as string[],
  tagsText: '',
  max_count: 0,
  allow_resend: false,
})
const form = ref({
  content_theme_id: null as number | null,
  lang_strategy: 'auto' as 'auto' | 'fixed',
  fixed_lang: '',
  fallback_lang: '',
  channel_ids: [] as number[],
  mode: 'immediate',
  daily_max: 0,
})

const publishedThemes = computed<ThemeOption[]>(() => {
  const map = new Map<number, ThemeOption>()
  for (const row of published.value) {
    const item = map.get(row.theme_id) ?? { theme_id: row.theme_id, theme_name: row.theme_name, langs: [] }
    item.langs.push(row.lang)
    map.set(row.theme_id, item)
  }
  return [...map.values()]
})

function healthLabel(health: string): string {
  return { healthy: '健康', failing: '异常', unknown: '未测' }[health] ?? health
}

function formatCounts(counts: Record<string, number>): string {
  return Object.entries(counts || {})
    .map(([key, value]) => `${langLabel(key)} ${value}`)
    .join(' · ')
}

function splitList(text: string): string[] {
  return text
    .split(/[,，;\s]+/)
    .map((item) => item.trim())
    .filter(Boolean)
}

function buildPayload() {
  const filters: Record<string, unknown> = { status: audience.value.status }
  const country = splitList(audience.value.countryText)
  const language = splitList(audience.value.languageText)
  const tags = splitList(audience.value.tagsText)
  if (country.length) filters.country = country.map((c) => c.toUpperCase())
  if (language.length) filters.language = language
  if (tags.length) filters.tags = tags
  const audiencePayload: Record<string, unknown> = { filters, allow_resend: audience.value.allow_resend }
  if (audience.value.max_count > 0) audiencePayload.max_count = audience.value.max_count
  return {
    name: `${publishedThemes.value.find((t) => t.theme_id === form.value.content_theme_id)?.theme_name ?? '计划'} · ${new Date().toLocaleDateString()}`,
    content_theme_id: form.value.content_theme_id,
    channel_ids: form.value.channel_ids,
    audience: audiencePayload,
    lang_strategy: form.value.lang_strategy,
    fixed_lang: form.value.lang_strategy === 'fixed' ? form.value.fixed_lang : null,
    fallback_lang: form.value.fallback_lang || null,
    schedule: { mode: 'immediate', daily_max: form.value.daily_max || null },
  }
}

function validateStep(): string | null {
  if (step.value === 1 && !form.value.content_theme_id) return '请选择内容主题'
  if (step.value === 1 && form.value.lang_strategy === 'fixed' && !form.value.fixed_lang) return '请选择固定语言'
  if (step.value === 2 && !form.value.channel_ids.length) return '请选择至少一个发送通道'
  return null
}

function next() {
  const error = validateStep()
  if (error) {
    ElMessage.warning(error)
    return
  }
  step.value++
}

async function createAndEstimate() {
  working.value = true
  try {
    const payload = buildPayload()
    if (createdId.value === null) {
      const campaign = await api.post<CampaignRow>('/campaigns', payload)
      createdId.value = campaign.id
    } else {
      await api.put(`/campaigns/${createdId.value}`, payload)
    }
    estimate.value = await api.post<EstimateRow>(`/campaigns/${createdId.value}/estimate`)
    ElMessage.success('预估完成')
    emit('done')
  } catch {
    /* 客户端已提示 */
  } finally {
    working.value = false
  }
}

async function startNow() {
  if (createdId.value === null) {
    ElMessage.warning('请先创建并预估')
    return
  }
  working.value = true
  try {
    await api.post(`/campaigns/${createdId.value}/start`)
    ElMessage.success('计划已启动：可到监控页查看进度')
    visible.value = false
    emit('done')
  } finally {
    working.value = false
  }
}

function reset() {
  step.value = 0
  estimate.value = null
  createdId.value = null
  working.value = false
  audience.value = {
    countryText: '', languageText: '', status: ['new', 'contacted'], tagsText: '', max_count: 0, allow_resend: false,
  }
  form.value = {
    content_theme_id: null, lang_strategy: 'auto', fixed_lang: '', fallback_lang: '',
    channel_ids: [], mode: 'immediate', daily_max: 0,
  }
}

async function open() {
  visible.value = true
  const [channelRows, publishedRows] = await Promise.all([
    api.get<ChannelRow[]>('/channels'),
    api.get<PublishedVariantRow[]>('/content/published'),
  ])
  channels.value = channelRows
  published.value = publishedRows
  if (!published.value.length) step.value = 1
}

defineExpose({ open })
</script>

<style scoped>
.steps {
  margin-bottom: 16px;
}
.hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.hint.warn {
  color: var(--el-color-warning);
}
.mb {
  margin-bottom: 12px;
}
</style>
