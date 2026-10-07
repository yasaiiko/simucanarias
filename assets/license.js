// Gumroad license unlock, 100% client-side.
// Gumroad's POST /v2/licenses/verify answers with `access-control-allow-origin: *`,
// so a static site can validate a buyer's key without any backend.
(function (global) {
  const API = 'https://api.gumroad.com/v2/licenses/verify';

  function createLicense({ productId, storageKey = 'pro_license_v1', onChange = () => {} }) {
    const read = () => {
      try { return JSON.parse(localStorage.getItem(storageKey) || 'null'); } catch { return null; }
    };
    const write = (v) => {
      try { v ? localStorage.setItem(storageKey, JSON.stringify(v)) : localStorage.removeItem(storageKey); } catch {}
    };

    async function verify(key, { increment = false } = {}) {
      const body = new URLSearchParams({
        product_id: productId,
        license_key: String(key || '').trim(),
        increment_uses_count: String(increment),
      });
      let json;
      try {
        const res = await fetch(API, { method: 'POST', body });
        json = await res.json();
      } catch (e) {
        return { ok: false, offline: true, message: 'Network error' };
      }
      const p = (json && json.purchase) || {};
      const ended = p.subscription_ended_at || p.subscription_cancelled_at || p.subscription_failed_at;
      const ok = !!(json && json.success) && !p.refunded && !p.chargebacked && !p.disputed && !ended;
      return { ok, message: json && json.message, email: p.email, uses: json && json.uses };
    }

    async function activate(key) {
      const r = await verify(key, { increment: true });
      if (r.ok) { write({ key: String(key).trim(), email: r.email || '', at: Date.now() }); onChange(true); }
      return r;
    }

    // Re-check a stored key at most once a day; stay unlocked if offline.
    async function restore() {
      const saved = read();
      if (!saved) { onChange(false); return false; }
      onChange(true);
      if (Date.now() - (saved.checked || 0) < 864e5) return true;
      const r = await verify(saved.key);
      if (r.offline) return true;
      if (!r.ok) { write(null); onChange(false); return false; }
      write({ ...saved, checked: Date.now() });
      return true;
    }

    function deactivate() { write(null); onChange(false); }
    const isPro = () => !!read();

    return { verify, activate, restore, deactivate, isPro };
  }

  global.createLicense = createLicense;
})(window);
