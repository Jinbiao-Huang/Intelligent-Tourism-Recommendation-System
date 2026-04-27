<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance } from 'element-plus'
import { Calendar, Connection, Loading, MapLocation, Opportunity, Wallet } from '@element-plus/icons-vue'

const tourFormRef = ref<FormInstance>()

const form = ref({
  destination: '',
  dateRange: [] as Date[],
  budget: 1200,
})

const rules = {
  destination: [{ required: true, message: '请输入目的地', trigger: 'blur' }],
  dateRange: [{ type: 'array', required: true, message: '请选择出行时间', trigger: 'change' }],
  budget: [{ type: 'number', required: true, message: '请输入预算', trigger: 'change' }],
}

const loading = ref(false)

const collaborators = [
  { name: '林夏', role: '路线主理人', status: '在线' },
  { name: '阿哲', role: '交通与预算', status: '已加入' },
  { name: 'Mia', role: '城市摄影点位', status: '已同步' },
]

const popularRoutes = ['滨海慢行 3 天', '古城文化 2 天', '山谷徒步 4 天', '夜市与美食 1 天']

const tripDays = computed(() => {
  if (!form.value.dateRange || form.value.dateRange.length !== 2) {
    return 0
  }
  const [startDate, endDate] = form.value.dateRange
  if (!startDate || !endDate) {
    return 0
  }
  const start = new Date(startDate).getTime()
  const end = new Date(endDate).getTime()
  const diff = end - start
  if (Number.isNaN(diff) || diff < 0) {
    return 0
  }
  return Math.floor(diff / 86400000) + 1
})

const submitForm = async () => {
  if (!tourFormRef.value) {
    return
  }

  try {
    await tourFormRef.value.validate()
  } catch {
    ElMessage.warning('请先完善行程信息')
    return
  }

  loading.value = true
  window.setTimeout(() => {
    loading.value = false
    ElMessage.success(`已生成 ${form.value.destination} 的协作攻略草案`)
  }, 1100)
}
</script>

<template>
  <section class="planner-page">
    <div class="map-atmosphere" aria-hidden="true">
      <span class="orb orb-sea"></span>
      <span class="orb orb-sun"></span>
      <span class="orb orb-leaf"></span>
    </div>

    <div class="planner-shell">
      <aside class="story-panel reveal reveal-1">
        <p class="eyebrow">Collaborative Travel Studio</p>
        <h2>把灵感拉进同一个地图画布</h2>
        <p class="subtitle">
          把目的地、时间和预算一次输入，系统会生成可共享的初版路线，方便小组成员边聊边改，快速达成一致。
        </p>

        <div class="feature-grid">
          <article class="feature-card">
            <el-icon><MapLocation /></el-icon>
            <div>
              <h3>目的地聚焦</h3>
              <p>智能识别热门片区，优先串联高评分点位。</p>
            </div>
          </article>
          <article class="feature-card">
            <el-icon><Connection /></el-icon>
            <div>
              <h3>协作同步</h3>
              <p>多人实时编辑，意见与路线版本自动追踪。</p>
            </div>
          </article>
          <article class="feature-card">
            <el-icon><Opportunity /></el-icon>
            <div>
              <h3>节奏平衡</h3>
              <p>根据天数控制密度，避免过度赶路。</p>
            </div>
          </article>
        </div>

        <div class="collab-panel reveal reveal-2">
          <div class="panel-head">
            <h3>协作状态</h3>
            <span>实时在线</span>
          </div>
          <ul>
            <li v-for="member in collaborators" :key="member.name">
              <strong>{{ member.name }}</strong>
              <span>{{ member.role }}</span>
              <em>{{ member.status }}</em>
            </li>
          </ul>
        </div>
      </aside>

      <el-card class="tour-form-card reveal reveal-3" shadow="never">
        <div class="card-head">
          <div>
            <p class="eyebrow">Plan Builder</p>
            <h3>生成你的协作行程</h3>
          </div>
          <el-tag class="sync-tag" effect="dark" type="warning">多人共创</el-tag>
        </div>

        <div class="route-tags">
          <button
            v-for="route in popularRoutes"
            :key="route"
            type="button"
            @click="form.destination = route.split(' ')[0] ?? route"
          >
            {{ route }}
          </button>
        </div>

        <el-form ref="tourFormRef" :model="form" :rules="rules" label-position="top" class="planner-form">
          <el-form-item label="目的地" prop="destination">
            <el-input v-model="form.destination" placeholder="例如：厦门、成都、青岛" size="large" />
          </el-form-item>

          <el-form-item label="出行时间" prop="dateRange">
            <el-date-picker
              v-model="form.dateRange"
              type="daterange"
              start-placeholder="开始日期"
              end-placeholder="结束日期"
              format="YYYY-MM-DD"
              size="large"
              style="width: 100%"
            />
          </el-form-item>

          <el-form-item label="人均预算（元）" prop="budget">
            <el-input-number v-model="form.budget" :min="0" :step="100" controls-position="right" size="large" style="width: 100%" />
          </el-form-item>

          <div class="meta-grid">
            <div class="meta-item">
              <el-icon><Calendar /></el-icon>
              <span>{{ tripDays ? `${tripDays} 天` : '待选择日期' }}</span>
            </div>
            <div class="meta-item">
              <el-icon><Wallet /></el-icon>
              <span>预算 {{ form.budget }} 元/人</span>
            </div>
          </div>

          <el-button class="generate-btn" type="primary" size="large" :loading="loading" @click="submitForm">
            生成协作攻略
          </el-button>
        </el-form>

        <transition name="fade-up">
          <div v-if="loading" class="loading-panel">
            <el-icon class="is-loading"><Loading /></el-icon>
            <p>正在聚合路线与兴趣点，请稍候...</p>
          </div>
        </transition>
      </el-card>
    </div>
  </section>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Noto+Sans+SC:wght@400;500;700;900&display=swap');

.planner-page {
  position: relative;
  min-height: calc(100dvh - 140px);
  padding: 30px;
  overflow: hidden;
  background:
    radial-gradient(circle at 18% 20%, rgba(35, 110, 240, 0.26), transparent 48%),
    radial-gradient(circle at 80% 15%, rgba(249, 115, 22, 0.22), transparent 38%),
    linear-gradient(145deg, #f5fbff 0%, #eaf2ff 45%, #f9fdf7 100%);
}

.map-atmosphere {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(4px);
  animation: float 9s ease-in-out infinite;
}

.orb-sea {
  width: 220px;
  height: 220px;
  top: -58px;
  left: -55px;
  background: rgba(37, 99, 235, 0.2);
}

.orb-sun {
  width: 180px;
  height: 180px;
  right: 8%;
  top: 2%;
  background: rgba(249, 115, 22, 0.22);
  animation-delay: 1.3s;
}

.orb-leaf {
  width: 250px;
  height: 250px;
  right: -90px;
  bottom: -95px;
  background: rgba(34, 197, 94, 0.15);
  animation-delay: 2s;
}

.planner-shell {
  position: relative;
  z-index: 1;
  width: min(1200px, 100%);
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 26px;
}

.story-panel,
.tour-form-card {
  border-radius: 28px;
  border: 1px solid rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(14px);
  box-shadow: 0 18px 40px rgba(22, 65, 148, 0.12);
}

.story-panel {
  background: rgba(255, 255, 255, 0.74);
  padding: 34px;
  font-family: 'Manrope', 'Noto Sans SC', sans-serif;
}

.eyebrow {
  display: inline-block;
  margin-bottom: 12px;
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #2563eb;
  font-weight: 700;
}

.story-panel h2 {
  margin: 0;
  font-size: clamp(30px, 4vw, 44px);
  line-height: 1.15;
  color: #0f294f;
  font-weight: 800;
}

.subtitle {
  margin-top: 18px;
  color: #385376;
  font-size: 15px;
  max-width: 92%;
}

.feature-grid {
  margin-top: 24px;
  display: grid;
  gap: 12px;
}

.feature-card {
  display: grid;
  grid-template-columns: 38px 1fr;
  gap: 12px;
  align-items: start;
  padding: 14px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.66);
  border: 1px solid rgba(37, 99, 235, 0.09);
}

.feature-card .el-icon {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #2563eb;
  font-size: 18px;
  background: rgba(37, 99, 235, 0.12);
}

.feature-card h3 {
  font-size: 15px;
  font-weight: 700;
  color: #173760;
}

.feature-card p {
  margin-top: 5px;
  font-size: 13px;
  color: #4d6788;
}

.collab-panel {
  margin-top: 24px;
  padding: 18px;
  border-radius: 18px;
  border: 1px solid rgba(22, 95, 227, 0.12);
  background: linear-gradient(140deg, rgba(255, 255, 255, 0.82), rgba(240, 247, 255, 0.72));
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.panel-head h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: #12355f;
}

.panel-head span {
  font-size: 12px;
  font-weight: 700;
  color: #17803d;
}

.collab-panel ul {
  list-style: none;
  display: grid;
  gap: 8px;
  padding: 0;
  margin: 0;
}

.collab-panel li {
  display: grid;
  grid-template-columns: 72px 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 10px 12px;
  background: #ffffff;
  border-radius: 12px;
}

.collab-panel strong {
  color: #1a4673;
  font-weight: 700;
}

.collab-panel span {
  font-size: 13px;
  color: #516e8f;
}

.collab-panel em {
  font-style: normal;
  color: #eb7b18;
  font-size: 12px;
  font-weight: 700;
}

.tour-form-card {
  margin: 0;
  background: rgba(255, 255, 255, 0.9);
  padding: 28px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.card-head h3 {
  margin: 0;
  color: #0f2f5e;
  font-size: 26px;
  font-family: 'Manrope', 'Noto Sans SC', sans-serif;
  font-weight: 800;
}

.sync-tag {
  margin-top: 4px;
  border-radius: 999px;
  padding: 0 10px;
  font-weight: 700;
}

.route-tags {
  margin-top: 18px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.route-tags button {
  border: 0;
  border-radius: 999px;
  padding: 8px 13px;
  font-size: 12px;
  font-weight: 700;
  background: rgba(37, 99, 235, 0.1);
  color: #194a86;
  cursor: pointer;
  transition: all 0.22s ease;
}

.route-tags button:hover {
  background: #2563eb;
  color: #fff;
}

.planner-form {
  margin-top: 18px;
}

.meta-grid {
  margin: 6px 0 18px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border-radius: 12px;
  padding: 10px 12px;
  background: #f2f7ff;
  color: #194374;
  font-size: 13px;
  font-weight: 600;
}

.meta-item .el-icon {
  color: #2563eb;
}

.generate-btn {
  width: 100%;
  border: 0;
  height: 48px;
  border-radius: 14px;
  font-weight: 700;
  letter-spacing: 0.03em;
  background: linear-gradient(120deg, #2563eb, #1d4ed8 54%, #f97316 130%);
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.24);
}

.loading-panel {
  margin-top: 16px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #1c4e8d;
  font-size: 13px;
  font-weight: 600;
}

:deep(.tour-form-card .el-card__body) {
  padding: 0;
}

:deep(.planner-form .el-form-item__label) {
  color: #2b4a71;
  font-weight: 700;
}

:deep(.planner-form .el-input__wrapper),
:deep(.planner-form .el-input-number),
:deep(.planner-form .el-date-editor.el-input__wrapper) {
  border-radius: 12px;
}

.reveal {
  opacity: 0;
  transform: translateY(16px);
  animation: reveal 0.7s ease forwards;
}

.reveal-2 {
  animation-delay: 0.16s;
}

.reveal-3 {
  animation-delay: 0.28s;
}

.fade-up-enter-active,
.fade-up-leave-active {
  transition: all 0.25s ease;
}

.fade-up-enter-from,
.fade-up-leave-to {
  opacity: 0;
  transform: translateY(7px);
}

@keyframes reveal {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-12px);
  }
}

@media (max-width: 1080px) {
  .planner-shell {
    grid-template-columns: 1fr;
  }

  .subtitle {
    max-width: 100%;
  }
}

@media (max-width: 768px) {
  .planner-page {
    min-height: calc(100dvh - 120px);
    padding: 16px;
  }

  .story-panel,
  .tour-form-card {
    border-radius: 20px;
    padding: 20px;
  }

  .story-panel h2 {
    font-size: 30px;
  }

  .collab-panel li {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .meta-grid {
    grid-template-columns: 1fr;
  }
}

@media (prefers-reduced-motion: reduce) {
  .reveal,
  .orb,
  .fade-up-enter-active,
  .fade-up-leave-active {
    animation: none;
    transition: none;
  }
}
</style>
