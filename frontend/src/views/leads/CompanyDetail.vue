<template>
  <div v-if="company">
    <PageHeader :title="company.name || '(未命名公司)'" :description="company.domain || '（无域名）'">
      <template #actions>
        <el-button @click="router.push('/leads')">返回列表</el-button>
        <el-button type="primary" :loading="saving" @click="saveCompany">保存</el-button>
      </template>
    </PageHeader>

    <el-row :gutter="16">
      <el-col :span="9">
        <el-card shadow="never">
          <template #header>公司信息</template>
          <el-form label-width="90px">
            <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width: 100%">
                <el-option label="新线索" value="new" />
                <el-option label="已联系" value="contacted" />
                <el-option label="已回复" value="replied" />
                <el-option label="已成交" value="won" />
                <el-option label="未成交" value="lost" />
                <el-option label="无效" value="invalid" />
              </el-select>
            </el-form-item>
            <el-form-item label="标签">
              <el-select v-model="form.tags" multiple filterable allow-create default-first-option style="width: 100%" placeholder="回车创建标签" />
            </el-form-item>
            <el-form-item label="国家/语言">
              <span>{{ company.country || '—' }} / {{ company.language || '—' }}</span>
            </el-form-item>
            <el-form-item v-if="company.is_excluded" label="排除">
              <el-tag type="danger" size="small">{{ company.exclusion_reason || '已排除' }}</el-tag>
            </el-form-item>
            <el-form-item label="备注"><el-input v-model="form.note" type="textarea" :rows="3" /></el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <el-col :span="15">
        <el-card shadow="never">
          <template #header>
            联系方式（{{ contacts.length }}）
            <span class="tip">同公司同类型同值唯一；分类与有效标记会用于发送与排除判断</span>
          </template>
          <el-table :data="contacts" size="small">
            <el-table-column label="类型" width="90">
              <template #default="{ row }">
                <el-tag size="small">{{ TYPE_LABELS[row.type] || row.type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="value" label="值" min-width="190" show-overflow-tooltip />
            <el-table-column label="分类" width="110">
              <template #default="{ row }">
                <el-select v-model="row.category" size="small" @change="updateContact(row as ContactRow)">
                  <el-option label="采购" value="procurement" />
                  <el-option label="销售" value="sales" />
                  <el-option label="通用" value="general" />
                  <el-option label="其他" value="other" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="有效性" width="110">
              <template #default="{ row }">
                <el-select v-model="row.validity" size="small" @change="updateContact(row as ContactRow)">
                  <el-option label="有效" value="valid" />
                  <el-option label="疑似无效" value="suspicious" />
                  <el-option label="无效" value="invalid" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="来源" width="70">
              <template #default="{ row }">
                <el-link v-if="row.source_url" :href="(row as ContactRow).source_url ?? undefined" target="_blank" type="primary" :underline="false">页面</el-link>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="70">
              <template #default="{ row }">
                <el-button size="small" text type="danger" @click="removeContact(row as ContactRow)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <el-divider content-position="left">补录联系方式</el-divider>
          <el-form inline>
            <el-form-item>
              <el-select v-model="newContact.type" style="width: 110px">
                <el-option v-for="(label, key) in TYPE_LABELS" :key="key" :value="key" :label="label" />
              </el-select>
            </el-form-item>
            <el-form-item>
              <el-input v-model="newContact.value" style="width: 260px" placeholder="邮箱 / 电话 / 社媒地址" />
            </el-form-item>
            <el-form-item>
              <el-select v-model="newContact.category" style="width: 100px">
                <el-option label="采购" value="procurement" />
                <el-option label="销售" value="sales" />
                <el-option label="通用" value="general" />
                <el-option label="其他" value="other" />
              </el-select>
            </el-form-item>
            <el-form-item><el-button type="primary" @click="addContact">添加</el-button></el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { api } from '../../api/client'
import type { CompanyRow, ContactRow } from '../../api/types'
import PageHeader from '../../components/common/PageHeader.vue'

const TYPE_LABELS: Record<string, string> = {
  email: '邮箱',
  phone: '电话',
  whatsapp: 'WhatsApp',
  facebook: 'Facebook',
  linkedin: 'LinkedIn',
  x: 'X',
  instagram: 'Instagram',
  wechat: '微信',
  other: '其他',
}

const route = useRoute()
const router = useRouter()
const companyId = Number(route.params.id)
const company = ref<CompanyRow | null>(null)
const contacts = ref<ContactRow[]>([])
const saving = ref(false)
const form = ref({ name: '', status: 'new', tags: [] as string[], note: '' })
const newContact = ref({ type: 'email', value: '', category: 'general' })

async function load() {
  company.value = await api.get<CompanyRow>(`/companies/${companyId}`)
  contacts.value = company.value.contacts ?? []
  form.value = {
    name: company.value.name ?? '',
    status: company.value.status,
    tags: [...(company.value.tags ?? [])],
    note: company.value.note ?? '',
  }
}

async function saveCompany() {
  saving.value = true
  try {
    await api.put(`/companies/${companyId}`, form.value)
    ElMessage.success('已保存')
    await load()
  } finally {
    saving.value = false
  }
}

async function addContact() {
  if (!newContact.value.value.trim()) {
    ElMessage.warning('请填写联系方式')
    return
  }
  await api.post(`/companies/${companyId}/contacts`, newContact.value)
  newContact.value = { ...newContact.value, value: '' }
  ElMessage.success('已添加')
  await load()
}

async function updateContact(row: ContactRow) {
  await api.put(`/companies/${companyId}/contacts/${row.id}`, {
    category: row.category,
    validity: row.validity,
  })
}

async function removeContact(row: ContactRow) {
  await api.del(`/companies/${companyId}/contacts/${row.id}`)
  await load()
}

onMounted(load)
</script>

<style scoped>
.tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
