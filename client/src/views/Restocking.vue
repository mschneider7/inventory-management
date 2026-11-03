<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.subtitle') }}</p>
    </div>

    <div v-if="initializing" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="initError" class="error">{{ initError }}</div>
    <div v-else>
      <div class="card budget-card">
        <div class="budget-header">
          <label for="budget-slider" class="budget-label">{{ t('restocking.budgetLabel') }}</label>
          <span class="budget-value">{{ formatMoney(budget) }}</span>
        </div>
        <input
          id="budget-slider"
          v-model.number="budget"
          type="range"
          class="budget-slider"
          min="0"
          :max="maxBudget"
          :step="BUDGET_STEP"
        />
        <div class="budget-scale">
          <span>{{ formatMoney(0) }}</span>
          <span>{{ formatMoney(maxBudget) }}</span>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.plannedSpend') }}</div>
          <div class="stat-value">{{ formatMoney(totalCost) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ formatMoney(remainingBudget) }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.itemsCount') }}</div>
          <div class="stat-value">{{ items.length }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.longestLeadTime') }}</div>
          <div class="stat-value">{{ t('restocking.days', { days: maxLeadTime }) }}</div>
        </div>
      </div>

      <div v-if="orderConfirmation" class="card confirmation" role="status">
        <p>
          {{ t('restocking.success', {
            orderNumber: orderConfirmation.order_number,
            days: orderConfirmation.lead_time_days,
            date: formatDate(orderConfirmation.expected_delivery)
          }) }}
        </p>
        <router-link to="/orders">{{ t('restocking.viewOrders') }}</router-link>
      </div>
      <div v-if="submitError" class="error" role="alert">{{ submitError }}</div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ items.length }})</h3>
          <button
            type="button"
            class="place-order-btn"
            :disabled="items.length === 0 || submitting || loading"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="error" class="error">{{ error }}</div>
        <div v-else-if="loading && items.length === 0" class="loading">{{ t('common.loading') }}</div>
        <div v-else-if="items.length === 0" class="empty-state">{{ t('restocking.empty') }}</div>
        <div v-else class="table-container" :class="{ stale: loading }">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.product') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th>{{ t('restocking.table.quantity') }}</th>
                <th>{{ t('restocking.table.unitCost') }}</th>
                <th>{{ t('restocking.table.lineCost') }}</th>
                <th>{{ t('restocking.table.supplier') }}</th>
                <th>{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.sku">
                <td><strong>{{ item.sku }}</strong></td>
                <td>{{ translateProductName(item.name) }}</td>
                <td>
                  <span :class="['badge', trendClass(item.trend)]">{{ trendLabel(item.trend) }}</span>
                </td>
                <td>{{ item.quantity.toLocaleString() }}</td>
                <td>{{ formatMoney(item.unit_cost, true) }}</td>
                <td><strong>{{ formatMoney(item.line_cost, true) }}</strong></td>
                <td>{{ item.supplier }}</td>
                <td>{{ t('restocking.days', { days: item.lead_time_days }) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const BUDGET_STEP = 500
const DEBOUNCE_MS = 250
// Large enough to include every eligible item; used once to find the slider max.
const UNBOUNDED_BUDGET = 10000000

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, currentLocale, translateProductName } = useI18n()

    const currencySymbol = computed(() => (currentCurrency.value === 'JPY' ? '¥' : '$'))

    const initializing = ref(true)
    const initError = ref(null)
    const loading = ref(false)
    const error = ref(null)

    const maxBudget = ref(0)
    const budget = ref(0)

    const items = ref([])
    const totalCost = ref(0)
    const remainingBudget = ref(0)
    const maxLeadTime = ref(0)

    const submitting = ref(false)
    const submitError = ref(null)
    const orderConfirmation = ref(null)

    let debounceTimer = null
    // Monotonic counter: only the latest request may write results (ignores stale responses).
    let requestSeq = 0

    const applyRecommendations = (data) => {
      items.value = data.items
      totalCost.value = data.total_cost
      remainingBudget.value = data.remaining_budget
      maxLeadTime.value = data.max_lead_time_days
    }

    const loadRecommendations = async () => {
      const seq = ++requestSeq
      loading.value = true
      error.value = null
      try {
        const data = await api.getRestockRecommendations(budget.value)
        if (seq !== requestSeq) return
        applyRecommendations(data)
      } catch (err) {
        if (seq !== requestSeq) return
        error.value = t('restocking.loadError') + ': ' + err.message
        console.error('Restocking load error:', err)
      } finally {
        if (seq === requestSeq) loading.value = false
      }
    }

    // Debounced refetch as the slider moves.
    watch(budget, () => {
      // A new budget invalidates any previous confirmation/error.
      orderConfirmation.value = null
      submitError.value = null
      clearTimeout(debounceTimer)
      debounceTimer = setTimeout(loadRecommendations, DEBOUNCE_MS)
    })

    const init = async () => {
      try {
        // Max slider value = cost of recommending every eligible item, rounded up to the step.
        const all = await api.getRestockRecommendations(UNBOUNDED_BUDGET)
        maxBudget.value = Math.max(BUDGET_STEP, Math.ceil(all.total_cost / BUDGET_STEP) * BUDGET_STEP)
        // Start at half the range, snapped to the step. Setting budget triggers the debounced watch.
        budget.value = Math.round(maxBudget.value / 2 / BUDGET_STEP) * BUDGET_STEP
      } catch (err) {
        initError.value = t('restocking.loadError') + ': ' + err.message
        console.error('Restocking init error:', err)
      } finally {
        initializing.value = false
      }
    }

    const placeOrder = async () => {
      if (items.value.length === 0 || submitting.value) return
      submitting.value = true
      submitError.value = null
      orderConfirmation.value = null
      try {
        // Send only sku + quantity; the server looks up prices.
        const payload = items.value.map(({ sku, quantity }) => ({ sku, quantity }))
        orderConfirmation.value = await api.createRestockOrder(payload)
      } catch (err) {
        const detail = err.response?.data?.detail
        submitError.value = t('restocking.submitError') + ': ' + (typeof detail === 'string' ? detail : err.message)
        console.error('Restocking submit error:', err)
      } finally {
        submitting.value = false
      }
    }

    const formatMoney = (value, cents = false) => {
      const locale = currentLocale.value === 'ja' ? 'ja-JP' : 'en-US'
      const num = Number(value) || 0
      return currencySymbol.value + num.toLocaleString(locale, {
        minimumFractionDigits: cents ? 2 : 0,
        maximumFractionDigits: cents ? 2 : 0
      })
    }

    const formatDate = (dateString) => {
      const date = new Date(dateString)
      if (isNaN(date.getTime())) return dateString
      return date.toLocaleDateString(currentLocale.value === 'ja' ? 'ja-JP' : 'en-US', {
        year: 'numeric', month: 'short', day: 'numeric'
      })
    }

    // Trend values match the badge classes used in Demand.vue (increasing/stable/decreasing).
    const trendClass = (trend) => (['increasing', 'stable', 'decreasing'].includes(trend) ? trend : 'stable')
    const trendLabel = (trend) => (['increasing', 'stable', 'decreasing'].includes(trend) ? t(`trends.${trend}`) : trend)

    onMounted(init)
    onBeforeUnmount(() => {
      clearTimeout(debounceTimer)
      requestSeq++ // drop any in-flight response
    })

    return {
      t, BUDGET_STEP, initializing, initError, loading, error, budget, maxBudget,
      items, totalCost, remainingBudget, maxLeadTime,
      submitting, submitError, orderConfirmation,
      placeOrder, formatMoney, formatDate, trendClass, trendLabel, translateProductName
    }
  }
}
</script>

<style scoped>
.budget-card {
  padding: 1.25rem 1.5rem;
  margin-bottom: 1.5rem;
}

.budget-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 0.75rem;
}

.budget-label {
  font-weight: 600;
  color: #0f172a;
}

.budget-value {
  font-size: 1.5rem;
  font-weight: 700;
  color: #0f172a;
}

.budget-slider {
  width: 100%;
  height: 6px;
  accent-color: #3b82f6;
  cursor: pointer;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 0.5rem;
  font-size: 0.813rem;
  color: #64748b;
}

.place-order-btn {
  padding: 0.5rem 1.25rem;
  background: #0f172a;
  color: white;
  border: none;
  border-radius: 6px;
  font-weight: 500;
  cursor: pointer;
}

.place-order-btn:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.confirmation {
  padding: 1rem 1.5rem;
  margin-bottom: 1rem;
  border-left: 4px solid #22c55e;
}

.confirmation p {
  margin: 0 0 0.5rem;
  color: #0f172a;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
}

.stale {
  opacity: 0.6;
  transition: opacity 0.15s;
}
</style>
