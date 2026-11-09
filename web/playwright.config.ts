import { defineConfig } from '@playwright/test';

// Kiểm tra giao diện trên bản build thật + backend với dữ liệu mẫu (e2e/server.py, DB test).
// Chạy: npm run build && npm run test:e2e
const PORT = 8765;

export default defineConfig({
	testDir: 'e2e',
	workers: 1, // dùng chung một database
	fullyParallel: false,
	reporter: 'list',
	// Backend chạy echo có độ trễ trong cùng máy: cho phép chậm khi máy đang tải nặng.
	expect: { timeout: 15_000 },
	use: { baseURL: `http://127.0.0.1:${PORT}`, locale: 'vi-VN', timezoneId: 'Asia/Ho_Chi_Minh' },
	projects: [
		{ name: 'mobile', use: { viewport: { width: 360, height: 740 }, hasTouch: true, isMobile: true } },
		{ name: 'desktop', use: { viewport: { width: 1280, height: 800 } } }
	],
	webServer: {
		command: `cd .. && .venv/bin/python web/e2e/server.py ${PORT}`,
		url: `http://127.0.0.1:${PORT}/health`,
		reuseExistingServer: false,
		timeout: 60_000
	}
});
