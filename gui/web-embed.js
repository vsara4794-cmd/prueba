/* ViriaRevive — shim para modo navegador (FastAPI + web_server.py).
 * Emula pywebview.api vía fetch y reproduce la cola JS del backend.
 */
(function () {
    if (typeof pywebview !== 'undefined') return;

    const BASE = '';

    async function rpc(method, args) {
        const res = await fetch(BASE + '/api/rpc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ method, args }),
        });
        const text = await res.text();
        let data;
        try {
            data = JSON.parse(text);
        } catch {
            throw new Error(text || res.statusText);
        }
        if (!res.ok) throw new Error(data.error || res.statusText);
        if (data.error) throw new Error(data.error);
        return data.result;
    }

    function runScripts(scripts) {
        if (!scripts || !scripts.length) return;
        for (const code of scripts) {
            try {
                (0, eval)(code);
            } catch (e) {
                console.error('pending-js eval:', e);
            }
        }
    }

    async function pollPending() {
        try {
            const res = await fetch(BASE + '/api/pending-js');
            const j = await res.json();
            runScripts(j.scripts);
        } catch (_) { /* offline / server stopped */ }
    }

    const api = new Proxy(
        {},
        {
            get(_, method) {
                if (method === 'flush_pending_js') {
                    return async () => {
                        const res = await fetch(BASE + '/api/pending-js');
                        const j = await res.json();
                        runScripts(j.scripts);
                        return { flushed: (j.scripts && j.scripts.length) || 0 };
                    };
                }
                return (...args) => rpc(method, args);
            },
        }
    );

    window.pywebview = { api };

    function boot() {
        window.dispatchEvent(new Event('pywebviewready'));
        setInterval(pollPending, 200);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => setTimeout(boot, 0));
    } else {
        setTimeout(boot, 0);
    }
})();
