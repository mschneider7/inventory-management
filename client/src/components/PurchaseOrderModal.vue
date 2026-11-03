<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="isOpen && backlogItem" class="modal-overlay" @click="close">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h3 class="modal-title">{{ mode === 'view' ? 'Purchase Order' : 'Create Purchase Order' }}</h3>
            <button class="close-button" aria-label="Close" @click="close">
              <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
            </button>
          </div>

          <div class="modal-body">
            <div class="item-header">
              <h4 class="item-name">{{ translateProductName(backlogItem.item_name) }}</h4>
              <div class="item-meta">
                <span class="item-sku">SKU: {{ backlogItem.item_sku }}</span>
                <span class="item-shortage">Shortage: {{ shortage }} units</span>
              </div>
            </div>

            <!-- View mode -->
            <template v-if="mode === 'view'">
              <div v-if="viewLoading" class="state-message">Loading purchase order...</div>
              <div v-else-if="viewError" class="error-message">{{ viewError }}</div>
              <div v-else-if="po" class="info-grid">
                <div class="info-item">
                  <div class="info-label">PO Number</div>
                  <div class="info-value mono">{{ po.id }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Status</div>
                  <div class="info-value"><span class="badge">{{ po.status }}</span></div>
                </div>
                <div class="info-item">
                  <div class="info-label">Supplier</div>
                  <div class="info-value">{{ po.supplier_name }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Quantity</div>
                  <div class="info-value">{{ po.quantity }} units</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Unit Cost</div>
                  <div class="info-value">{{ formatMoney(po.unit_cost) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Total</div>
                  <div class="info-value">{{ formatMoney(po.quantity * po.unit_cost) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Expected Delivery</div>
                  <div class="info-value">{{ formatDate(po.expected_delivery_date) }}</div>
                </div>
                <div class="info-item">
                  <div class="info-label">Created</div>
                  <div class="info-value">{{ formatDate(po.created_date) }}</div>
                </div>
                <div class="info-item full">
                  <div class="info-label">Notes</div>
                  <div class="info-value">{{ po.notes || 'None' }}</div>
                </div>
              </div>
            </template>

            <!-- Create mode -->
            <form v-else id="po-form" class="po-form" @submit.prevent="submit">
              <div class="form-field full">
                <label for="po-supplier">Supplier name</label>
                <input id="po-supplier" v-model="form.supplier_name" type="text" required />
              </div>
              <div class="form-field">
                <label for="po-quantity">Quantity</label>
                <input id="po-quantity" v-model.number="form.quantity" type="number" min="1" step="1" required />
              </div>
              <div class="form-field">
                <label for="po-cost">Unit cost</label>
                <input id="po-cost" v-model.number="form.unit_cost" type="number" min="0" step="0.01" required />
              </div>
              <div class="form-field full">
                <label for="po-date">Expected delivery date</label>
                <input id="po-date" v-model="form.expected_delivery_date" type="date" required />
              </div>
              <div class="form-field full">
                <label for="po-notes">Notes (optional)</label>
                <textarea id="po-notes" v-model="form.notes" rows="3"></textarea>
              </div>
              <div v-if="submitError" class="error-message full">{{ submitError }}</div>
            </form>
          </div>

          <div class="modal-footer">
            <button type="button" class="btn-secondary" @click="close">
              {{ mode === 'view' ? 'Close' : 'Cancel' }}
            </button>
            <button
              v-if="mode !== 'view'"
              type="submit"
              form="po-form"
              class="btn-primary"
              :disabled="submitting || !isValid"
            >
              {{ submitting ? 'Creating...' : 'Create Purchase Order' }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, reactive, computed, watch } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

const { translateProductName } = useI18n()

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  backlogItem: { type: Object, default: null },
  // 'create' or 'view'
  mode: { type: String, default: 'create' }
})

const emit = defineEmits(['close', 'po-created'])

const form = reactive({
  supplier_name: '',
  quantity: 1,
  unit_cost: 0,
  expected_delivery_date: '',
  notes: ''
})
const submitting = ref(false)
const submitError = ref(null)

const po = ref(null)
const viewLoading = ref(false)
const viewError = ref(null)

const shortage = computed(() => {
  if (!props.backlogItem) return 0
  return Math.max(0, props.backlogItem.quantity_needed - props.backlogItem.quantity_available)
})

// Mirrors backend constraints (quantity > 0, unit_cost >= 0); number inputs yield '' when empty
const isValid = computed(() => {
  const qty = Number(form.quantity)
  const cost = form.unit_cost
  return (
    form.supplier_name.trim().length > 0 &&
    form.quantity !== '' && Number.isFinite(qty) && qty > 0 &&
    cost !== '' && Number.isFinite(Number(cost)) && Number(cost) >= 0 &&
    !!form.expected_delivery_date
  )
})

const resetForm = () => {
  form.supplier_name = ''
  form.quantity = shortage.value > 0 ? shortage.value : 1
  form.unit_cost = 0
  form.expected_delivery_date = ''
  form.notes = ''
  submitError.value = null
  submitting.value = false
}

const loadPO = async () => {
  po.value = null
  viewError.value = null
  viewLoading.value = true
  const requestedId = props.backlogItem.id
  try {
    const result = await api.getPurchaseOrderByBacklogItem(requestedId)
    // Ignore stale responses if the modal was closed/reopened for another item meanwhile
    if (props.backlogItem?.id !== requestedId) return
    po.value = result
  } catch (err) {
    if (props.backlogItem?.id !== requestedId) return
    viewError.value = err.response?.status === 404
      ? 'No purchase order found for this item.'
      : 'Failed to load purchase order.'
    console.error('Failed to load purchase order:', err)
  } finally {
    if (props.backlogItem?.id === requestedId) viewLoading.value = false
  }
}

// Initialise state each time the modal opens (or the item/mode changes while open)
watch(
  () => [props.isOpen, props.backlogItem?.id, props.mode],
  () => {
    if (!props.isOpen || !props.backlogItem) return
    if (props.mode === 'view') {
      loadPO()
    } else {
      resetForm()
    }
  },
  { immediate: true }
)

const submit = async () => {
  if (submitting.value || !isValid.value) return
  submitting.value = true
  submitError.value = null
  const payload = {
    backlog_item_id: props.backlogItem.id,
    supplier_name: form.supplier_name.trim(),
    quantity: Number(form.quantity),
    unit_cost: Number(form.unit_cost),
    expected_delivery_date: form.expected_delivery_date,
    notes: form.notes.trim() || null
  }
  try {
    const created = await api.createPurchaseOrder(payload)
    emit('po-created', created)
  } catch (err) {
    if (err.response?.status === 409) {
      submitError.value = 'A purchase order already exists for this item.'
    } else {
      submitError.value = err.response?.data?.detail && typeof err.response.data.detail === 'string'
        ? err.response.data.detail
        : 'Failed to create purchase order. Please try again.'
    }
    console.error('Failed to create purchase order:', err)
  } finally {
    submitting.value = false
  }
}

const close = () => emit('close')

const formatMoney = (value) => {
  const n = Number(value)
  if (!Number.isFinite(n)) return 'N/A'
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

const formatDate = (dateString) => {
  if (!dateString) return 'N/A'
  const date = new Date(dateString)
  if (isNaN(date.getTime())) return 'N/A'
  return date.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  padding: 1rem;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15);
  max-width: 600px;
  width: 100%;
  max-height: 90vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e2e8f0;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.15s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 2rem;
}

.item-header {
  padding-bottom: 1.25rem;
  border-bottom: 1px solid #e2e8f0;
  margin-bottom: 1.5rem;
}

.item-name {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 0.5rem 0;
}

.item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  font-size: 0.875rem;
  color: #64748b;
}

.item-sku {
  font-family: 'Monaco', 'Courier New', monospace;
}

.item-shortage {
  color: #dc2626;
  font-weight: 600;
}

.po-form,
.info-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.25rem;
}

.full {
  grid-column: 1 / -1;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.form-field label,
.info-label {
  font-size: 0.813rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}

.form-field input,
.form-field textarea {
  padding: 0.625rem 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.938rem;
  font-family: inherit;
  color: #0f172a;
  background: white;
}

.form-field input:focus,
.form-field textarea:focus {
  outline: none;
  border-color: #64748b;
  box-shadow: 0 0 0 3px rgba(100, 116, 139, 0.15);
}

.form-field textarea {
  resize: vertical;
}

.info-item {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.info-value {
  font-size: 0.938rem;
  color: #0f172a;
  font-weight: 500;
}

.info-value.mono {
  font-family: 'Monaco', 'Courier New', monospace;
  color: #2563eb;
}

.badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 6px;
  background: #dbeafe;
  color: #1e40af;
  font-size: 0.813rem;
  font-weight: 600;
}

.state-message {
  color: #64748b;
  text-align: center;
  padding: 1.5rem 0;
}

.error-message {
  padding: 0.75rem 1rem;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 8px;
  color: #991b1b;
  font-size: 0.875rem;
}

.modal-footer {
  padding: 1.5rem;
  border-top: 1px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
}

.btn-secondary,
.btn-primary {
  padding: 0.625rem 1.25rem;
  border-radius: 8px;
  font-weight: 500;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.15s ease;
  font-family: inherit;
}

.btn-secondary {
  background: #f1f5f9;
  border: 1px solid #e2e8f0;
  color: #334155;
}

.btn-secondary:hover {
  background: #e2e8f0;
  border-color: #cbd5e1;
}

.btn-primary {
  background: #0f172a;
  border: 1px solid #0f172a;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1e293b;
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Modal transition animations */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s ease;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
}
</style>
