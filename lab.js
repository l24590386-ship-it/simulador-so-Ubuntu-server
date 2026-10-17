/* Núcleo compartido: todas las pestañas leen y escriben el MISMO estado del servidor. */
const Lab = (() => {
  const subs = []; let E = null;
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const COLORS = ['#00d4ff','#ff6b35','#00ff88','#fbbf24','#c084fc','#fb7185','#38bdf8','#a3e635'];
  const color = pid => COLORS[(pid - 1) % COLORS.length];

  function toast(m, ok) {
    const t = document.getElementById('toast'); t.textContent = m; t.style.display = 'block'; t.style.background = ok ? '#065f46' : '#7f1d1d';
    clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = 'none', 3200);
  }
  async function api(url, method = 'GET', body) {
    try {
      const r = await fetch(url, { method, headers: {'Content-Type': 'application/json'}, body: body ? JSON.stringify(body) : undefined });
      const d = await r.json();
      if (!r.ok) { toast(d.error || 'Error'); return null; }
      return d;
    } catch (e) { toast('Sin conexión con el servidor'); return null; }
  }
  function paint(d) {
    const m = d.maquina, pill = document.getElementById('sPill');
    pill.className = 'pill ' + m.fase;
    pill.textContent = m.fase === 'apagada' ? '⏻ APAGADA' : m.fase === 'arrancando' ? `◔ ARRANCANDO ${m.paso}/${m.total}` : '● ENCENDIDA';
    document.getElementById('sReloj').textContent = d.reloj;
    document.getElementById('sCpu').textContent = d.cpu ? `P${d.cpu.pid} ${d.cpu.nombre}` : (m.fase === 'encendida' ? 'ocioso' : '—');
    document.querySelectorAll('nav [data-nav]').forEach(a => {
      a.classList.toggle('on', a.dataset.nav === document.body.dataset.page);
      const lock = m.fase !== 'encendida' && a.dataset.nav !== 'arranque';
      a.querySelector('i').textContent = lock ? '🔒' : '';
    });
    document.getElementById('lock').classList.toggle('hidden', !(document.body.dataset.lock && m.fase !== 'encendida'));
  }
  function publish(d) { if (!d) return null; E = d; paint(d); subs.forEach(f => f(d)); return d; }
  const refresh = async () => publish(await api('/api/estado'));
  const post = async (u, b) => { const d = await api(u, 'POST', b); if (d && d.mensaje) toast(d.mensaje, true); return publish(d); };
  setInterval(() => !document.hidden && refresh(), 2500);   // mantiene sincronizadas las pestañas
  document.addEventListener('DOMContentLoaded', refresh);
  return { api, post, refresh, esc, color, toast, on: f => { subs.push(f); if (E) f(E); }, get state() { return E; } };
})();
