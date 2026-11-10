// Bản build không được tải tài nguyên từ bên thứ ba (font, CSS, script): app private + noindex.
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = new URL('../build/', import.meta.url).pathname;
const EXTERNAL = /(?:url\(\s*['"]?|(?:src|href)=["']|@import\s+['"]?)(?:https?:)?\/\/[^)"'\s]+/gi;
const bad = [];
let fonts = 0;

function walk(dir) {
	for (const name of readdirSync(dir)) {
		const p = join(dir, name);
		if (statSync(p).isDirectory()) walk(p);
		else if (/\.(woff2?|ttf|otf)$/.test(name)) fonts++;
		else if (/\.(css|html|js)$/.test(name)) {
			const text = readFileSync(p, 'utf8');
			for (const m of text.matchAll(EXTERNAL)) {
				// liên kết thường (vd. href tới docs) trong JS không phải tài nguyên tải tự động
				if (name.endsWith('.js') && /href=/.test(m[0])) continue;
				bad.push(`${p.slice(root.length)}: ${m[0]}`);
			}
		}
	}
}

walk(root);
if (bad.length) {
	console.error('Tài nguyên bên ngoài trong build:\n' + bad.join('\n'));
	process.exit(1);
}
if (!fonts) {
	console.error('Không thấy file font nào trong build (font phải tự host).');
	process.exit(1);
}
console.log(`OK: không có tài nguyên bên ngoài; ${fonts} file font tự host.`);
