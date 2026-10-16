<template>
  <div>
    <PageHeader
      title="关于与联系"
      description="加入交流群或直接联系作者；源码、版本与问题反馈见 GitHub 仓库。"
    />
    <el-row :gutter="16">
      <el-col :span="14">
        <el-card shadow="never">
          <template #header>联系方式</template>
          <el-row :gutter="16">
            <el-col :span="12">
              <div class="channel-title">QQ 群 · 外贸获客工具</div>
              <img
                class="qr"
                data-test="qq-qr"
                :src="qqGroupQr"
                alt="QQ 群二维码：外贸获客工具（1128098127）"
              >
              <div class="channel-row">
                <span>群号 <code>{{ QQ_GROUP_NUMBER }}</code></span>
                <el-button
                  data-test="copy-qq-group"
                  size="small"
                  text
                  type="primary"
                  @click="copy(QQ_GROUP_NUMBER)"
                >
                  复制群号
                </el-button>
              </div>
              <p class="hint">手机 QQ 扫码加群，或搜索群号加入</p>
            </el-col>
            <el-col :span="12">
              <div class="channel-title">微信 · 码工李葛</div>
              <img
                class="qr"
                data-test="wx-qr"
                :src="wechatQr"
                alt="微信二维码：码工李葛"
              >
              <p class="hint">扫二维码，添加我为朋友</p>
            </el-col>
          </el-row>
        </el-card>
      </el-col>

      <el-col :span="10">
        <el-card shadow="never">
          <template #header>关于</template>
          <el-form label-width="90px">
            <el-form-item label="应用版本">
              <span data-test="app-version">{{ versionText }}</span>
            </el-form-item>
            <el-form-item label="开源仓库">
              <el-link
                data-test="github-link"
                type="primary"
                :href="REPO_URL"
                target="_blank"
              >
                {{ REPO_URL }}
              </el-link>
              <el-button
                class="copy-btn"
                data-test="copy-repo"
                size="small"
                text
                type="primary"
                @click="copy(REPO_URL)"
              >
                复制地址
              </el-button>
            </el-form-item>
            <el-form-item label="问题反馈">
              <el-link data-test="issues-link" type="primary" :href="ISSUES_URL" target="_blank">
                GitHub Issues
              </el-link>
            </el-form-item>
            <el-form-item label="开源许可">
              <span>Apache License 2.0</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../../components/common/PageHeader.vue'
import { useAppStore } from '../../stores/app'
import qqGroupQr from '../../assets/qqgroup.jpg'
import wechatQr from '../../assets/wx.png'

const QQ_GROUP_NUMBER = '1128098127'
const REPO_URL = 'https://github.com/dropdust/saler-tool'
const ISSUES_URL = `${REPO_URL}/issues`

const appStore = useAppStore()
const versionText = computed(() =>
  appStore.health?.version ? `v${appStore.health.version}` : '—',
)

async function copy(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制')
  } catch {
    // 剪贴板不可用（无权限 / 非安全上下文）：把明文显示出来供手动复制
    ElMessage.info(text)
  }
}
</script>

<style scoped>
.channel-title {
  font-weight: 600;
  margin-bottom: 8px;
}
.qr {
  display: block;
  width: 100%;
  max-width: 260px;
  height: auto;
  /* 二维码本体是深色点阵且 wx.png 带透明通道：固定白底，深色主题下仍可扫 */
  background: #fff;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
}
.channel-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.hint {
  margin: 8px 0 0;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.copy-btn {
  margin-left: 8px;
}
</style>
