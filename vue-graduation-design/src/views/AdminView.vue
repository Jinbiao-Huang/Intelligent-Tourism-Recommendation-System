<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { adminAPI, type AdminUser } from '@/api/admin'

const loading = ref(false)
const users = ref<AdminUser[]>([])

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

const refreshUsers = async () => {
  await fetchUsers()
}

onMounted(() => {
  refreshUsers()
})
</script>

<template>
  <div class="admin-page">
    <el-card class="admin-card">
      <div class="admin-header">
        <h2>用户管理</h2>
        <el-button :loading="loading" @click="refreshUsers">刷新</el-button>
      </div>

      <el-table :data="users" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="created_at" label="创建时间" />
        <el-table-column prop="updated_at" label="更新时间" />
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

</style>
