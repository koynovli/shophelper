import React from 'react';
import { LayoutGrid, ShoppingCart, Info } from 'lucide-react';

function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 font-sans p-6">
      {/* Шапка */}
      <header className="max-w-4xl mx-auto flex justify-between items-center mb-12 border-b border-slate-800 pb-6">
        <div className="flex items-center gap-2">
          <ShoppingCart className="text-emerald-400 w-8 h-8" />
          <h1 className="text-2xl font-bold tracking-tight text-white">ShopHelper <span className="text-emerald-500">UI</span></h1>
        </div>
        <div className="text-sm text-slate-500 font-mono">v1.0.0-beta</div>
      </header>

      {/* Основной контент */}
      <main className="max-w-4xl mx-auto">
        <div className="bg-slate-900 border border-slate-800 rounded-3xl p-8 shadow-2xl">
          <h2 className="text-3xl font-bold text-white mb-4">Добро пожаловать</h2>
          <p className="text-slate-400 text-lg mb-8">
            Фронтенд успешно связан с Tailwind CSS. Это интерфейс мерчандайзера для работы с цифровым двойником магазина.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="group p-6 bg-slate-800/50 border border-slate-700 rounded-2xl hover:border-emerald-500/50 transition-all cursor-pointer">
              <LayoutGrid className="text-emerald-400 mb-4 group-hover:scale-110 transition-transform" />
              <h3 className="text-xl font-bold text-white mb-2">Карта зала</h3>
              <p className="text-sm text-slate-500">Визуализация стеллажей и полок в реальном времени.</p>
            </div>
            
            <div className="group p-6 bg-slate-800/50 border border-slate-700 rounded-2xl hover:border-blue-500/50 transition-all cursor-pointer">
              <Info className="text-blue-400 mb-4 group-hover:scale-110 transition-transform" />
              <h3 className="text-xl font-bold text-white mb-2">Аналитика FEFO</h3>
              <p className="text-sm text-slate-500">Проверка сроков годности и подсказки по ротации.</p>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;