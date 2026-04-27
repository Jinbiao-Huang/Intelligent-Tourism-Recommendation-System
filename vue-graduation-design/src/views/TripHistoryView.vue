<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { useTripHistoryStore } from '@/stores/tripHistory'

const router = useRouter()
const userStore = useUserStore()
const tripHistoryStore = useTripHistoryStore()

const records = computed(() => tripHistoryStore.records)

const loadHistory = () => {
  tripHistoryStore.loadRecords(userStore.user?.id)
}

const formatTime = (createdAt: string) => {
  const date = new Date(createdAt)
  if (Number.isNaN(date.getTime())) {
    return createdAt
  }
  return date.toLocaleString('zh-CN', { hour12: false })
}

const handleClear = async () => {
  if (!records.value.length) {
    ElMessage.info('当前没有可清空的记录')
    return
  }

  try {
    await ElMessageBox.confirm('确认清空全部行程记录吗？', '提示', {
      type: 'warning',
      confirmButtonText: '确认清空',
      cancelButtonText: '取消'
    })
    tripHistoryStore.clearRecords(userStore.user?.id)
    ElMessage.success('行程记录已清空')
  } catch {
    // 用户取消
  }
}

onMounted(loadHistory)
watch(() => userStore.user?.id, loadHistory)
</script>

<template>
  <div class="history-page">
    <el-card class="history-header" shadow="never">
      <div class="header-main">
        <div>
          <h2>我的旅游行程记录</h2>
        </div>
        <div class="header-actions">
          <el-button @click="router.push('/')">返回首页</el-button>
          <el-button type="danger" plain @click="handleClear">清空记录</el-button>
        </div>
      </div>
    </el-card>

    <div v-if="records.length" class="history-list">
      <el-timeline>
        <el-timeline-item
          v-for="record in records"
          :key="record.id"
          :timestamp="formatTime(record.createdAt)"
          placement="top"
          type="primary"
        >
          <el-card class="history-item">
            <div class="record-head">
              <h3>{{ record.destination }} · {{ record.days }} 天</h3>
              <span>{{ record.places.length }} 个目的地</span>
            </div>
            <div class="places-wrap">
              <el-tag
                v-for="(place, idx) in record.places"
                :key="record.id + '-' + idx"
                size="small"
                class="place-tag"
              >
                {{ place }}
              </el-tag>
            </div>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </div>

    <el-empty v-else description="暂无行程记录，先去首页生成一次吧">
      <el-button type="primary" @click="router.push('/')">去生成行程</el-button>
    </el-empty>
  </div>
</template>

<style scoped>
.history-page {
  padding: 16px;
}

.history-header {
  margin-bottom: 20px;
  border-radius: 12px;
}

.header-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.header-main h2 {
  margin: 0 0 8px;
  font-size: 24px;
  color: #303133;
}

.header-main p {
  margin: 0;
  color: #606266;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.history-list {
  margin-top: 12px;
}

.history-item {
  border-radius: 10px;
}

.record-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.record-head h3 {
  margin: 0;
  font-size: 17px;
  color: #303133;
}

.record-head span {
  font-size: 13px;
  color: #909399;
}

.places-wrap {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.place-tag {
  margin: 0;
}

@media (max-width: 768px) {
  .header-main {
    flex-direction: column;
  }

  .header-actions {
    width: 100%;
  }

  .header-actions .el-button {
    flex: 1;
  }

  .record-head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
