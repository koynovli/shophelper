export type TaskPoolItem = {
  task_type: 'placement' | 'staff';
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
};

export function poolStatusLabel(status: string, taskType: TaskPoolItem['task_type']): string {
  if (taskType === 'staff' && status === 'CREATED') {
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
  return taskType === 'placement' ? 'Выкладка' : 'Поручение';
}
