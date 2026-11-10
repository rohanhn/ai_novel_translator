import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

// SPA tĩnh (design D8): build ra web/build, FastAPI phục vụ ở `/` với fallback index.html.
const API_TARGET = process.env.NT_API_URL ?? 'http://127.0.0.1:8000';

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			adapter: adapter({ pages: 'build', assets: 'build', fallback: 'index.html', strict: true })
		})
	],
	server: {
		// Dev: cùng origin với API để cookie session hoạt động.
		proxy: {
			'/api': { target: API_TARGET, changeOrigin: false },
			'/health': API_TARGET
		}
	}
});
