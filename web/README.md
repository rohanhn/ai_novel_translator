# Web app (SvelteKit SPA)

Giao diện đọc truyện. Build tĩnh ra `web/build`; `novel serve` phục vụ ở `/` (fallback deep link
về `index.html`), API ở `/api` cùng origin.

- Cài: `npm install`
- Dev: chạy `novel serve` (cổng 8000) rồi `npm run dev`; Vite proxy `/api` sang
  `NT_API_URL` (mặc định `http://127.0.0.1:8000`).
- Kiểm tra kiểu: `npm run check`
- Build: `npm run build`
