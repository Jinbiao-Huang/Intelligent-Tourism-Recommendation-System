<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminAPI, type AdminUser, type AdminItineraryRecord } from '@/api/admin'

const loading = ref(false)
const recordLoading = ref(false)
const users = ref<AdminUser[]>([])
const itineraryRecords = ref<AdminItineraryRecord[]>([])

const fetchUsers = async () => {
  loading.value = true
  try {
    const response = await adminAPI.getUsers()
    users.value = response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '获取用户列表失败')
  } finally {
    loading.value = false
  }
}

const fetchItineraryRecords = async () => {
  recordLoading.value = true
  try {
    const response = await adminAPI.getItineraryRecords()
    itineraryRecords.value = response.data
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '获取行程记录失败')
  } finally {
    recordLoading.value = false
  }
}

const refreshAll = async () => {
  await Promise.all([fetchUsers(), fetchItineraryRecords()])
}

const isEditedDestination = (row: AdminItineraryRecord) => {
  return Boolean(row.has_edited_destination)
}

const getEditedDetail = (row: AdminItineraryRecord) => {
  if (!isEditedDestination(row)) {
    return '-'
  }
  const from = String(row.edited_from || '').trim() || '未记录'
  const to = String(row.edited_to || '').trim() || '未记录'
  return `${from} -> ${to}`
}

onMounted(() => {
  refreshAll()
})
</script>

<template>
  <div class="admin-page">
    <el-card class="admin-card">
      <div class="admin-header">
        <h2>用户管理</h2>
        <el-button :loading="loading || recordLoading" @click="refreshAll">刷新</el-button>
      </div>

      <el-table :data="users" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="created_at" label="创建时间" />
        <el-table-column prop="updated_at" label="更新时间" />
      </el-table>
    </el-card>

    <el-card class="admin-card records-card">
      <div class="admin-header">
        <h2>用户旅游行程记录</h2>
      </div>

      <el-table :data="itineraryRecords" v-loading="recordLoading" stripe style="width: 100%">
        <el-table-column prop="user_id" label="用户ID" width="100" />
        <el-table-column prop="username" label="用户名" width="140" />
        <el-table-column prop="destination" label="目的地" min-width="140" />
        <el-table-column prop="days" label="计划天数" width="100" />
        <el-table-column label="是否更改可编辑目的地" width="170">
          <template #default="scope">
            {{ isEditedDestination(scope.row) ? '是' : '否' }}
          </template>
        </el-table-column>
        <el-table-column label="可编辑目的地变更详情" min-width="280">
          <template #default="scope">
            <span class="edited-detail">{{ getEditedDetail(scope.row) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="记录时间" min-width="180" />
      </el-table>
    </el-card>
  </div>
</template>

<style scoped>
.admin-page {
  padding: 24px;
}

.admin-card {
  border-radius: 12px;
}

.records-card {
  margin-top: 18px;
}

.admin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.admin-header h2 {
  margin: 0;
  font-size: 20px;
}

.edited-detail {
  color: #606266;
  word-break: break-all;
}
</style>
