<template>
  <DashboardViewport
    :mode="mode"
    :tier="tier"
    :scale="scale"
  >
    <main class="dashboard-page">
      <DashboardHeader
        :state="states.globalStatus"
        :refreshing="refreshing"
        @refresh="bootstrap"
      />

      <section class="kpi-strip">
        <template v-if="states.overview.status === 'success'">
          <div v-if="states.overview.refreshError || states.overview.meta?.partial" class="kpi-strip__notices">
            <span v-if="states.overview.refreshError" class="kpi-strip__notice" :title="states.overview.refreshError">KPI 更新失败 · 沿用上次数据</span>
            <span v-if="states.overview.meta?.partial" class="kpi-strip__notice">KPI 为部分数据</span>
          </div>
          <KpiCard
            v-for="item in orderedKpis"
            :key="item.metricCode"
            :item="item"
            :tone="kpiToneMap[item.metricCode] ?? 'blue'"
          />
        </template>
        <div v-else class="panel kpi-loading-wrap">
          <PanelState :status="states.overview.status" :error="states.overview.error" />
        </div>
      </section>

      <section class="dashboard-grid">
        <div class="dashboard-column dashboard-column--left">
          <PlatformDonut :state="states.platformDistribution" />
          <ChargeDurationChart :state="states.durationDistribution" />
          <WeekdayWeekendRadar :state="states.weekdayWeekendProfile" />
        </div>

        <div class="dashboard-column dashboard-column--center">
          <LoadForecastChart :state="states.loadPrediction" :compact="narrow" />
          <StationHourHeatmap :state="states.stationHourHeatmap" :compact="narrow" />
        </div>

        <div class="dashboard-column dashboard-column--right">
          <StationRanking :state="states.stationRanking" />
          <FeeEnergyTrend :state="states.feeEnergyTrend" :compact="narrow" />
          <ProcessStatusOverview :state="states.processSummary" />
          <OperationInsights :insights="insights" />
        </div>
      </section>

      <!-- Batch D-4：页脚是**页面级**元素，放在 dashboard-grid 之外 ——
           放进三列 grid 会参与行分配与高度预算，让已校准的面板高度重新漂移。 -->
      <DashboardFooter />

      <div v-if="bootstrapError || batchWarning" class="dashboard-global-warning">
        <span v-if="bootstrapError">启动元数据加载异常：{{ bootstrapError }}</span>
        <span v-if="bootstrapError && batchWarning">；</span>
        <span v-if="batchWarning">{{ batchWarning }}</span>
      </div>
    </main>
  </DashboardViewport>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useDashboard } from '../composables/useDashboard.js'
import { useDashboardLayout } from '../composables/useDashboardLayout.js'
import DashboardViewport from '../components/layout/DashboardViewport.vue'
import DashboardHeader from '../components/dashboard/DashboardHeader.vue'
import DashboardFooter from '../components/dashboard/DashboardFooter.vue'
import KpiCard from '../components/dashboard/KpiCard.vue'
import PanelState from '../components/dashboard/PanelState.vue'
import PlatformDonut from '../components/dashboard/PlatformDonut.vue'
import ChargeDurationChart from '../components/dashboard/ChargeDurationChart.vue'
import WeekdayWeekendRadar from '../components/dashboard/WeekdayWeekendRadar.vue'
import LoadForecastChart from '../components/dashboard/LoadForecastChart.vue'
import StationHourHeatmap from '../components/dashboard/StationHourHeatmap.vue'
import StationRanking from '../components/dashboard/StationRanking.vue'
import FeeEnergyTrend from '../components/dashboard/FeeEnergyTrend.vue'
import ProcessStatusOverview from '../components/dashboard/ProcessStatusOverview.vue'
import OperationInsights from '../components/dashboard/OperationInsights.vue'

const { states, insights, bootstrapError, batchWarning, refreshing, bootstrap } = useDashboard()

// 布局状态唯一来源：模式 / 缩放比由 DashboardViewport 消费，
// compact 通透给图表组件供 Batch C 精简 label 用（本轮组件尚不消费）。
const { mode, tier, scale, isCompact, isMobile } = useDashboardLayout()
const narrow = computed(() => isCompact.value || isMobile.value)

const kpiOrder = [
  'total_order_count',
  'total_charging_energy',
  'total_charging_fee',
  'total_user_count',
  'active_station_count'
]
// 配色按 metricCode 显式映射，不依赖排序后的数组下标，避免视图层隐式依赖 kpiOrder 的顺序。
const kpiToneMap = {
  total_order_count: 'blue',
  total_charging_energy: 'teal',
  total_charging_fee: 'orange',
  total_user_count: 'purple',
  active_station_count: 'green'
}

const orderedKpis = computed(() => {
  const items = states.overview.data?.items || []
  return [...items].sort((a, b) => kpiOrder.indexOf(a.metricCode) - kpiOrder.indexOf(b.metricCode))
})

onMounted(bootstrap)
</script>
