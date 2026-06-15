export type MapTaskHighlight = {
  equipmentId: number;
  slotId?: number | null;
  taskId?: string | null;
};

export type TaskPoolItem = {
  task_type: 'placement' | 'staff' | 'receiving' | 'shelf_clearing' | 'write_off';
  id: string;
  title: string;
  status: string;
  assigned_to: { id: number; username: string } | null;
  created_at: string;
  destination?: string;
  location?: 'WAREHOUSE' | 'SHELF' | string;
  trigger?: string;
  reason?: string;
  batch_id?: number | null;
  batch_expiration?: string | null;
  product?: {
    id: number;
    name: string;
    sku: string;
    gtin?: string | null;
    is_marked?: boolean;
    sale_unit?: 'piece' | 'weight';
  };
  equipment?: { id: number; name: string } | null;
  quantity?: number;
  slot_info?: { id: number; row_index: number; col_index: number } | null;
  scans_done?: number;
  scans_required?: number;
  scans_done_display?: string;
  scans_required_display?: string;
  quantity_display?: string;
  photo_url?: string | null;
  description?: string;
  zone?: string | null;
  requires_photo?: boolean;
  has_chat?: boolean;
  supply_order_id?: number;
  supplier_name?: string | null;
  items_count?: number;
  planned_receiving_date?: string | null;
};

export function poolStatusLabel(status: string, taskType: TaskPoolItem['task_type']): string {
  if (
    (taskType === 'staff' ||
      taskType === 'receiving' ||
      taskType === 'shelf_clearing' ||
      taskType === 'write_off') &&
    status === 'CREATED'
  ) {
    return 'Ожидает';
  }
  const map: Record<string, string> = {
    PENDING: 'Ожидает',
    CREATED: 'Создана',
    IN_PROGRESS: 'Выполняется',
    COMPLETED: 'Завершено',
    FAILED: 'Проблема',
    CANCELLED: 'Отменено',
  };
  return map[status] ?? status;
}

export function taskTypeLabel(taskType: TaskPoolItem['task_type']): string {
  if (taskType === 'placement') {
    return 'Выкладка';
  }
  if (taskType === 'receiving') {
    return 'Приёмка';
  }
  if (taskType === 'shelf_clearing') {
    return 'Уборка';
  }
  if (taskType === 'write_off') {
    return 'Списание';
  }
  return 'Поручение';
}
