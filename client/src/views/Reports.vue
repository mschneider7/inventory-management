<template>
  <div class="reports">
    <div class="page-header">
      <h2>{{ t('reports.title') }}</h2>
      <p>{{ t('reports.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Summary Stats -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.totalRevenue') }}</div>
          <div class="stat-value">{{ money(totalRevenue) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.avgMonthlyRevenue') }}</div>
          <div class="stat-value">{{ money(avgMonthlyRevenue) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.totalOrders') }}</div>
          <div class="stat-value">{{ totalOrders.toLocaleString(numberLocale) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('reports.stats.bestQuarter') }}</div>
          <div class="stat-value">{{ bestQuarterLabel }}</div>
        </div>
      </div>

      <!-- Quarterly Performance -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.quarterlyPerformance') }}</h3>
        </div>
        <div v-if="quarterlyData.length === 0" class="empty-state">{{ t('common.noData') }}</div>
        <div v-else class="table-container">
          <table class="reports-table">
            <thead>
              <tr>
                <th>{{ t('reports.table.quarter') }}</th>
                <th>{{ t('reports.table.totalOrders') }}</th>
                <th>{{ t('reports.table.totalRevenue') }}</th>
                <th>{{ t('reports.table.avgOrderValue') }}</th>
                <th>{{ t('reports.table.fulfillmentRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="q in quarterlyData" :key="q.quarter">
                <td><strong>{{ formatQuarter(q.quarter) }}</strong></td>
                <td>{{ q.total_orders.toLocaleString(numberLocale) }}</td>
                <td>{{ money(q.total_revenue) }}</td>
                <td>{{ money(q.avg_order_value, 2) }}</td>
                <td>
                  <span :class="['badge', getFulfillmentClass(q.fulfillment_rate)]">
                    {{ q.fulfillment_rate }}%
                  </span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Monthly Trends Chart -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.monthlyRevenueTrend') }}</h3>
        </div>
        <div v-if="monthlyData.length === 0" class="empty-state">{{ t('common.noData') }}</div>
        <div v-else class="chart-container">
          <div class="bar-chart" role="list">
            <div v-for="m in monthlyRows" :key="m.month" class="bar-wrapper" role="listitem">
              <div class="bar-container">
                <div
                  class="bar"
                  role="img"
                  tabindex="0"
                  :style="{ height: m.barHeight + 'px' }"
                  :title="m.barText"
                  :aria-label="m.barText"
                ></div>
              </div>
              <div class="bar-label">{{ m.label }}</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Month-over-Month Comparison -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('reports.monthOverMonth') }}</h3>
        </div>
        <div v-if="monthlyData.length === 0" class="empty-state">{{ t('common.noData') }}</div>
        <div v-else class="table-container">
          <table class="reports-table">
            <thead>
              <tr>
                <th>{{ t('reports.table.month') }}</th>
                <th>{{ t('reports.table.orders') }}</th>
                <th>{{ t('reports.table.revenue') }}</th>
                <th>{{ t('reports.table.change') }}</th>
                <th>{{ t('reports.table.growthRate') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in monthlyRows" :key="m.month">
                <td><strong>{{ m.label }}</strong></td>
                <td>{{ m.order_count.toLocaleString(numberLocale) }}</td>
                <td>{{ money(m.revenue) }}</td>
                <td>
                  <span v-if="m.hasPrevious" :class="m.changeClass">{{ m.changeText }}</span>
                  <span v-else>-</span>
                </td>
                <td>
                  <span v-if="m.hasPrevious" :class="m.changeClass">{{ m.growthText }}</span>
                  <span v-else>-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted, watch } from 'vue'
import { api } from '../api'
import { useFilters } from '../composables/useFilters'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

// Max bar height in px; must match .bar-container height in the styles below
const MAX_BAR_HEIGHT = 200
const MONTH_KEYS = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']

export default {
  name: 'Reports',
  setup() {
    const { t, currentLocale, currentCurrency } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const quarterlyData = ref([])
    const monthlyData = ref([])

    const {
      selectedPeriod,
      selectedLocation,
      selectedCategory,
      selectedStatus,
      getCurrentFilters
    } = useFilters()

    // Incremented per request so a slow, older response cannot overwrite a newer one
    let latestRequestId = 0

    const loadData = async () => {
      const requestId = ++latestRequestId
      try {
        loading.value = true
        error.value = null
        const filters = getCurrentFilters()
        const [quarterly, monthly] = await Promise.all([
          api.getQuarterlyReports(filters),
          api.getMonthlyTrends(filters)
        ])
        if (requestId !== latestRequestId) return
        quarterlyData.value = quarterly
        monthlyData.value = monthly
      } catch (err) {
        if (requestId !== latestRequestId) return
        console.error('Failed to load reports:', err)
        error.value = `${t('reports.loadError')}: ${err.message}`
      } finally {
        // Only the latest request controls the loading flag
        if (requestId === latestRequestId) loading.value = false
      }
    }

    watch([selectedPeriod, selectedLocation, selectedCategory, selectedStatus], () => {
      loadData()
    })

    onMounted(() => {
      loadData()
    })

    const numberLocale = computed(() => (currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'))

    // Money formatting; amounts from the API are USD and converted for JPY in utils/currency
    const money = (amount, decimals = 0) => {
      const value = Number.isFinite(amount) ? amount : 0
      return decimals > 0
        ? formatCurrencyWithDecimals(value, currentCurrency.value, decimals)
        : formatCurrency(value, currentCurrency.value)
    }

    // Quarter strings arrive as "Q1-2025"; fall back to the raw string if malformed
    const formatQuarter = (quarterStr) => {
      const match = /^Q([1-4])-(\d{4})$/.exec(String(quarterStr))
      if (!match) return quarterStr || '-'
      return t('reports.quarterLabel', { quarter: match[1], year: match[2] })
    }

    // Month strings arrive as "YYYY-MM"; fall back to the raw string if invalid
    const formatMonth = (monthStr) => {
      const match = /^(\d{4})-(\d{2})$/.exec(String(monthStr))
      const key = match ? MONTH_KEYS[parseInt(match[2], 10) - 1] : null
      if (!key) return monthStr || '-'
      return t('reports.monthLabel', { month: t(`months.${key}`), year: match[1] })
    }

    const getFulfillmentClass = (rate) => {
      if (rate >= 90) return 'success'
      if (rate >= 75) return 'warning'
      return 'danger'
    }

    // Summary stats derived from the data (never mutated directly)
    const totalRevenue = computed(() =>
      monthlyData.value.reduce((sum, m) => sum + m.revenue, 0)
    )
    const avgMonthlyRevenue = computed(() =>
      monthlyData.value.length > 0 ? totalRevenue.value / monthlyData.value.length : 0
    )
    const totalOrders = computed(() =>
      monthlyData.value.reduce((sum, m) => sum + m.order_count, 0)
    )
    const bestQuarterLabel = computed(() => {
      let best = null
      for (const q of quarterlyData.value) {
        if (q.total_revenue > 0 && (!best || q.total_revenue > best.total_revenue)) best = q
      }
      return best ? formatQuarter(best.quarter) : '-'
    })

    // Computed once per data change, not once per bar per render
    const maxRevenue = computed(() =>
      monthlyData.value.reduce((max, m) => Math.max(max, m.revenue), 0)
    )

    // Per-month display rows, including comparison against the preceding month
    const monthlyRows = computed(() => {
      return monthlyData.value.map((m, i) => {
        const hasPrevious = i > 0
        const previous = hasPrevious ? monthlyData.value[i - 1].revenue : 0
        const change = m.revenue - previous
        const sign = change > 0 ? '+' : change < 0 ? '-' : ''
        const label = formatMonth(m.month)
        let growthText = t('reports.notAvailable')
        if (previous !== 0) {
          const rate = (change / previous) * 100
          growthText = `${rate > 0 ? '+' : ''}${rate.toLocaleString(numberLocale.value, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`
        }
        return {
          ...m,
          hasPrevious,
          label,
          barHeight: maxRevenue.value > 0 ? (m.revenue / maxRevenue.value) * MAX_BAR_HEIGHT : 0,
          barText: t('reports.barLabel', { month: label, revenue: money(m.revenue) }),
          changeText: `${sign}${money(Math.abs(change))}`,
          // Positive/negative colouring; zero change stays neutral
          changeClass: change > 0 ? 'positive-change' : change < 0 ? 'negative-change' : '',
          growthText
        }
      })
    })

    return {
      t,
      loading,
      error,
      quarterlyData,
      monthlyData,
      monthlyRows,
      numberLocale,
      money,
      formatQuarter,
      getFulfillmentClass,
      totalRevenue,
      avgMonthlyRevenue,
      totalOrders,
      bestQuarterLabel
    }
  }
}
</script>

<style scoped>
/* card, stats-grid, stat-card, badge, loading and error come from the global styles in App.vue */
.reports-table {
  width: 100%;
  border-collapse: collapse;
}

.empty-state {
  padding: 1.5rem;
  text-align: center;
  color: #64748b;
}

.chart-container {
  padding: 2rem 1rem;
  min-height: 300px;
}

.bar-chart {
  display: flex;
  align-items: flex-end;
  justify-content: space-around;
  height: 250px;
  gap: 0.5rem;
}

.bar-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  max-width: 80px;
}

/* Height must match MAX_BAR_HEIGHT in the script */
.bar-container {
  height: 200px;
  display: flex;
  align-items: flex-end;
  width: 100%;
}

.bar {
  width: 100%;
  background: linear-gradient(to top, #3b82f6, #60a5fa);
  border-radius: 4px 4px 0 0;
  transition: all 0.3s;
  cursor: pointer;
}

.bar:hover,
.bar:focus-visible {
  background: linear-gradient(to top, #2563eb, #3b82f6);
  outline: none;
}

.bar-label {
  font-size: 0.75rem;
  color: #64748b;
  text-align: center;
  transform: rotate(-45deg);
  white-space: nowrap;
  margin-top: 1.5rem;
}

.positive-change {
  color: #16a34a;
  font-weight: 600;
}

.negative-change {
  color: #dc2626;
  font-weight: 600;
}
</style>
