// API client: cookie session (same-origin) + header chống CSRF; 401 → chuyển sang /login.
import { goto } from '$app/navigation';

export const CSRF_HEADER = 'X-Requested-With';

export class ApiError extends Error {
	constructor(
		public status: number,
		public body: Record<string, unknown>
	) {
		super(typeof body.detail === 'string' ? body.detail : `HTTP ${status}`);
	}

	/** Loại lỗi provider (502) hoặc quota (429), nếu có. */
	get category(): string | undefined {
		return typeof this.body.category === 'string' ? this.body.category : undefined;
	}

	/** Mã lỗi nghiệp vụ, vd. `confirmation_required` (409). */
	get code(): string | undefined {
		return typeof this.body.code === 'string' ? this.body.code : undefined;
	}

	/** Thời điểm reset quota (429). */
	get resetAt(): Date | undefined {
		return typeof this.body.reset_at === 'string' ? new Date(this.body.reset_at) : undefined;
	}
}

let redirecting = false;

export function loginUrl(): string {
	const here = location.pathname + location.search;
	return here.startsWith('/login') ? '/login' : `/login?next=${encodeURIComponent(here)}`;
}

type Body = BodyInit | Record<string, unknown> | unknown[] | null | undefined;

export async function api<T = unknown>(
	path: string,
	init: Omit<RequestInit, 'body'> & { body?: Body } = {}
): Promise<T> {
	const headers = new Headers(init.headers);
	headers.set(CSRF_HEADER, 'fetch');
	let body = init.body as BodyInit | null | undefined;
	if (body != null && !(body instanceof FormData) && typeof body !== 'string') {
		headers.set('Content-Type', 'application/json');
		body = JSON.stringify(init.body);
	}
	const res = await fetch(path, { ...init, body, headers, credentials: 'same-origin' });
	if (res.status === 401 && !path.startsWith('/api/auth/login')) {
		if (!redirecting) {
			redirecting = true;
			await goto(loginUrl(), { replaceState: true });
			redirecting = false;
		}
		throw new ApiError(401, { detail: 'Chưa đăng nhập.' });
	}
	const text = res.status === 204 ? '' : await res.text();
	const data = text ? safeJson(text) : null;
	if (!res.ok) throw new ApiError(res.status, (data as Record<string, unknown>) ?? {});
	return data as T;
}

function safeJson(text: string): unknown {
	try {
		return JSON.parse(text);
	} catch {
		return { detail: text };
	}
}

export const get = <T>(path: string) => api<T>(path);
export const post = <T>(path: string, body?: Body) => api<T>(path, { method: 'POST', body });
export const put = <T>(path: string, body?: Body) => api<T>(path, { method: 'PUT', body });
export const patch = <T>(path: string, body?: Body) => api<T>(path, { method: 'PATCH', body });
export const del = <T>(path: string) => api<T>(path, { method: 'DELETE' });

export async function login(password: string): Promise<void> {
	await post('/api/auth/login', { password });
}

export async function logout(): Promise<void> {
	await post('/api/auth/logout');
	await goto('/login', { replaceState: true });
}
