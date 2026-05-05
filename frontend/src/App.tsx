import React, { useEffect, useMemo, useState } from 'react';
import { CalendarDays, Factory, ReceiptText, ShoppingCart, Tag } from 'lucide-react';

import api from './api';

type Supplier = {
  id: number;
  name: string;
};

type SupplyOrder = {
  id: number;
  status: string;
  created_at: string;
  supplier: number | null;
  supplier_detail?: Supplier | null;
};

const STATUS_LABELS: Record<string, string> = {
  draft: 'Черновик',
  sent: 'Отправлен',
  received: 'Принят',
  cancelled: 'Отменен',
};

const STATUS_STYLES: Record<string, string> = {
  draft: 'bg-slate-700/60 text-slate-200 border-slate-600',
  sent: 'bg-blue-900/40 text-blue-200 border-blue-700/50',
  received: 'bg-emerald-900/40 text-emerald-200 border-emerald-700/50',
  cancelled: 'bg-rose-900/40 text-rose-200 border-rose-700/50',
};

function App() {
  const [orders, setOrders] = useState<SupplyOrder[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    const fetchOrders = async (): Promise<void> => {
      try {
        const response = await api.get<SupplyOrder[]>('/supply-orders/');
        setOrders(response.data);
      } catch (error) {
        console.error('Не удалось загрузить список заказов:', error);
        setOrders([]);
      } finally {
        setLoading(false);
      }
    };

    fetchOrders();
  }, []);

  const hasOrders = useMemo(() => orders.length > 0, [orders]);

  const formatDate = (dateString: string): string => {
    if (!dateString) {
      return '—';
    }
    const parsedDate = new Date(dateString);
    if (Number.isNaN(parsedDate.getTime())) {
      return dateString;
    }
    return new Intl.DateTimeFormat('ru-RU', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(parsedDate);
  };

  const getSupplierName = (order: SupplyOrder): string => {
    if (order.supplier_detail?.name) {
      return order.supplier_detail.name;
    }
    if (order.supplier !== null) {
      return `Поставщик #${order.supplier}`;
    }
    return 'Не указан';
  };

  const getStatusLabel = (status: string): string => STATUS_LABELS[status] ?? status;

  const getStatusStyle = (status: string): string =>
    STATUS_STYLES[status] ?? 'bg-slate-700/60 text-slate-200 border-slate-600';

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-8 font-sans text-slate-200 sm:px-6 lg:px-8">
      <header className="mx-auto mb-8 flex w-full max-w-5xl items-center justify-between border-b border-slate-800 pb-6">
        <div className="flex items-center gap-3">
          <ShoppingCart className="h-8 w-8 text-emerald-400" />
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Список заказов
          </h1>
        </div>
        <div className="rounded-full border border-slate-700 bg-slate-900 px-3 py-1 text-sm text-slate-400">
          API: /supply-orders/
        </div>
      </header>

      <main className="mx-auto w-full max-w-5xl">
        {loading ? (
          <div className="rounded-3xl border border-slate-800 bg-slate-900 p-10 text-center text-lg text-slate-300 shadow-2xl">
            Loading...
          </div>
        ) : !hasOrders ? (
          <div className="rounded-3xl border border-slate-800 bg-slate-900 p-10 text-center text-lg text-slate-300 shadow-2xl">
            Заказы не найдены
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
            {orders.map((order) => (
              <article
                key={order.id}
                className="group rounded-2xl border border-slate-800 bg-slate-900 p-6 shadow-xl transition hover:border-emerald-500/40"
              >
                <div className="mb-5 flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <ReceiptText className="h-5 w-5 text-emerald-400" />
                    <h2 className="text-lg font-semibold text-white">
                      Заказ #{order.id}
                    </h2>
                  </div>
                  <span
                    className={`rounded-full border px-3 py-1 text-xs font-medium uppercase tracking-wide ${getStatusStyle(order.status)}`}
                  >
                    {getStatusLabel(order.status)}
                  </span>
                </div>

                <div className="space-y-3 text-sm text-slate-300">
                  <div className="flex items-center gap-3">
                    <Factory className="h-4 w-4 text-blue-300" />
                    <span>
                      Поставщик: <strong className="text-slate-100">{getSupplierName(order)}</strong>
                    </span>
                  </div>

                  <div className="flex items-center gap-3">
                    <Tag className="h-4 w-4 text-amber-300" />
                    <span>
                      Статус: <strong className="text-slate-100">{getStatusLabel(order.status)}</strong>
                    </span>
                  </div>

                  <div className="flex items-center gap-3">
                    <CalendarDays className="h-4 w-4 text-indigo-300" />
                    <span>
                      Дата создания: <strong className="text-slate-100">{formatDate(order.created_at)}</strong>
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;