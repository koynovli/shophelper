export type TaskPoolItem = {
  task_type: 'placement' | 'staff' | 'receiving';
  id: string;
  title: string;
  status: string;
  assigned_to: { id: number; username: string } | null;
  created_at: string;
  destination?: string;
  product?: { id: number; name: string; sku: string };
  equipment?: { id: number; name: string } | null;
  quantity?: number;
  slot_verified?: boolean;
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
  if ((taskType === 'staff' || taskType === 'receiving') && status === 'CREATED') {
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
  return 'Поручение';
}
