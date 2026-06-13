import React, { useEffect, useState } from 'react';
import {
  Boxes,
  ClipboardList,
  Inbox,
  LogOut,
  Map,
  ReceiptText,
  ShoppingCart,
  Tag,
} from 'lucide-react';
import { Navigate, Route, Routes, useNavigate, useSearchParams } from 'react-router-dom';

import { ProtectedRoute } from './auth/ProtectedRoute';
import { useAuth } from './auth/AuthContext';
import StoreMap from './components/StoreMap';
import { ReceivingPanel } from './components/ReceivingPanel';
import { TaskControlCenter } from './components/TaskControlCenter';
import { MapEditModeProvider } from './map/MapEditModeContext';
import { MapModeToolbar } from './components/MapModeToolbar';
import { EmployeeDashboard } from './pages/EmployeeDashboard';
import { InventoryDashboard } from './pages/InventoryDashboard';
import { ProductCatalogPage } from './pages/ProductCatalogPage';
import { SupplyOrdersPage } from './pages/SupplyOrdersPage';
import { LoginPage } from './pages/LoginPage';
import { NoAccess } from './pages/NoAccess';

type AdminTab = 'orders' | 'catalog' | 'map' | 'receiving' | 'tasks' | 'inventory';

const VALID_ADMIN_TABS: AdminTab[] = [
  'orders',
  'catalog',
  'map',
  'receiving',
  'tasks',
  'inventory',
];

function App() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = (): void => {
    logout();
    navigate('/login', { replace: true });
  };
  const HomeRedirect = (): React.ReactElement => {
    if (!user) {
      return <Navigate to="/login" replace />;
    }
    return <Navigate to={user.role === 'admin' ? '/admin' : '/employee'} replace />;
  };

  const AdminShellInner = (): React.ReactElement => {
    const [searchParams, setSearchParams] = useSearchParams();
    const tabParam = searchParams.get('tab');
    const initialTab: AdminTab = VALID_ADMIN_TABS.includes(tabParam as AdminTab) ? (tabParam as AdminTab) : 'orders';
    const [activeTab, setActiveTabState] = useState<AdminTab>(initialTab);

    useEffect(() => {
      const t = searchParams.get('tab');
      if (t && VALID_ADMIN_TABS.includes(t as AdminTab)) {
        setActiveTabState(t as AdminTab);
      }
    }, [searchParams]);

    const setTab = (tab: AdminTab): void => {
      setActiveTabState(tab);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set('tab', tab);
          if (tab !== 'map') {
            next.delete('equipmentId');
          }
          return next;
        },
        { replace: true },
      );
    };

    const equipmentRaw = searchParams.get('equipmentId');
    const parsedEquipment = equipmentRaw ? Number(equipmentRaw) : NaN;
    const mapHighlightId =
      activeTab === 'map' && Number.isFinite(parsedEquipment) ? parsedEquipment : null;

    const clearMapHighlight = (): void => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.delete('equipmentId');
          return next;
        },
        { replace: true },
      );
    };

    return (
    <div className="min-h-screen bg-slate-950 px-4 py-8 font-sans text-slate-200 sm:px-6 lg:px-8">
      <header className="mx-auto mb-8 flex w-full max-w-7xl flex-wrap items-center justify-between gap-4 border-b border-slate-800 pb-6">
        <div className="flex items-center gap-3">
          <ShoppingCart className="h-8 w-8 text-emerald-400" />
          <h1 className="text-2xl font-bold tracking-tight text-white">
            ShopHelper UI
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {user ? (
            <span className="hidden text-sm text-slate-400 sm:inline">
              {user.username}
            </span>
          ) : null}
          <a
            href="/employee"
            target="_blank"
            rel="noreferrer"
            className="hidden rounded-full border border-sky-600/60 bg-sky-950/40 px-3 py-1.5 text-sm text-sky-100 hover:bg-sky-900/50 sm:inline-flex"
            title="Откроется только для пользователя с ролью employee"
          >
            PWA сотрудника
          </a>
          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex items-center gap-2 rounded-full border border-slate-600 bg-slate-900 px-3 py-1.5 text-sm text-slate-200 transition hover:border-rose-500/50 hover:bg-rose-950/30 hover:text-rose-100"
          >
            <LogOut className="h-4 w-4" />
            Выйти
          </button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl">
        <div className="mb-5 flex flex-wrap items-center gap-2 rounded-2xl border border-slate-800 bg-slate-900 p-2">
          <button
            type="button"
            onClick={() => setTab('orders')}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
              activeTab === 'orders'
                ? 'bg-emerald-500/20 text-emerald-200'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
          >
            <ReceiptText className="h-4 w-4" />
            Список заказов
          </button>
          <button
            type="button"
            onClick={() => setTab('catalog')}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
              activeTab === 'catalog'
                ? 'bg-violet-500/20 text-violet-200'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
          >
            <Tag className="h-4 w-4" />
            Номенклатура
          </button>
          <button
            type="button"
            onClick={() => setTab('map')}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
              activeTab === 'map'
                ? 'bg-indigo-500/20 text-indigo-200'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
          >
            <Map className="h-4 w-4" />
            Карта зала
          </button>
          <button
            type="button"
            onClick={() => setTab('receiving')}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
              activeTab === 'receiving'
                ? 'bg-emerald-500/20 text-emerald-200'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
          >
            <Inbox className="h-4 w-4" />
            Приемка
          </button>
          <button
            type="button"
            onClick={() => setTab('tasks')}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
              activeTab === 'tasks'
                ? 'bg-amber-500/20 text-amber-200'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
          >
            <ClipboardList className="h-4 w-4" />
            Центр задач
          </button>
          <button
            type="button"
            onClick={() => setTab('inventory')}
            className={`inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition ${
              activeTab === 'inventory'
                ? 'bg-sky-500/20 text-sky-200'
                : 'text-slate-300 hover:bg-slate-800'
            }`}
          >
            <Boxes className="h-4 w-4" />
            Учёт товаров
          </button>
        </div>

        {activeTab === 'orders' ? (
          <SupplyOrdersPage />
        ) : activeTab === 'catalog' ? (
          <ProductCatalogPage />
        ) : activeTab === 'map' ? (
          <div className="rounded-3xl border border-slate-800 bg-slate-900/40 p-4 shadow-2xl">
            <MapModeToolbar className="mb-4" />
            <StoreMap
              highlightEquipmentId={mapHighlightId}
              onHighlightConsumed={clearMapHighlight}
            />
          </div>
        ) : activeTab === 'receiving' ? (
          <ReceivingPanel />
        ) : activeTab === 'inventory' ? (
          <InventoryDashboard />
        ) : (
          <TaskControlCenter />
        )}
      </main>
    </div>
    );
  };

  const AdminShell = (): React.ReactElement => (
    <MapEditModeProvider>
      <AdminShellInner />
    </MapEditModeProvider>
  );

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/no-access" element={<NoAccess />} />
      <Route path="/" element={<HomeRedirect />} />

      <Route element={<ProtectedRoute allowedRoles={['admin']} />}>
        <Route path="/admin" element={<AdminShell />} />
      </Route>

      <Route element={<ProtectedRoute allowedRoles={['employee']} />}>
        <Route path="/employee" element={<EmployeeDashboard />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default App;