// Theo dõi job dịch qua SSE (design D5). Server phát lại mọi sự kiện cho client vào muộn, nên
// khi EventSource tự kết nối lại thì xoá các đoạn đã nhận và nhận lại từ đầu.

export type StreamHandlers = {
	onReset: () => void;
	onTitle: (text: string) => void;
	onParagraph: (text: string) => void;
	onWaiting: (delay: number | null, step: number) => void;
	onFallback: (step: number, model: string) => void;
	onCompleted: () => void;
	onFailed: (category: string, message: string) => void;
	onQuota: (resetAt: string | null) => void;
	onCancelled: () => void;
};

export function followTranslation(url: string, h: StreamHandlers): () => void {
	const es = new EventSource(url, { withCredentials: true });
	let done = false;
	const data = (e: Event) => JSON.parse((e as MessageEvent).data);
	const finish = () => {
		done = true;
		es.close();
	};
	es.addEventListener('open', () => h.onReset());
	es.addEventListener('title', (e) => h.onTitle(data(e).text));
	es.addEventListener('paragraph', (e) => h.onParagraph(data(e).text));
	es.addEventListener('waiting_for_quota', (e) => {
		const d = data(e);
		h.onWaiting(d.delay, d.step);
	});
	es.addEventListener('fallback_step', (e) => {
		const d = data(e);
		h.onFallback(d.step, d.model);
	});
	es.addEventListener('completed', () => {
		finish();
		h.onCompleted();
	});
	es.addEventListener('failed', (e) => {
		finish();
		const d = data(e);
		h.onFailed(d.category, d.message);
	});
	es.addEventListener('quota_exhausted', (e) => {
		finish();
		h.onQuota(data(e).reset_at);
	});
	es.addEventListener('cancelled', () => {
		finish();
		h.onCancelled();
	});
	es.addEventListener('error', () => {
		// 404 (không còn job) hoặc mất mạng: EventSource tự thử lại; nếu đã đóng hẳn thì báo lỗi.
		if (!done && es.readyState === EventSource.CLOSED) h.onFailed('network', 'Mất kết nối tới máy chủ.');
	});
	return () => {
		done = true;
		es.close();
	};
}

/** Lý do lỗi bằng lời thường (spec "Plain-language labels"). */
export function failureReason(category: string, message: string): string {
	switch (category) {
		case 'refusal':
			return 'Model từ chối dịch nội dung chương này.';
		case 'truncated':
			return 'Bản dịch bị cắt ngang vì quá dài.';
		case 'malformed':
			return 'Model trả về sai định dạng, không đọc được bản dịch.';
		case 'rate_quota':
			return 'Model tạm hết lượt theo phút và thử lại nhiều lần vẫn không được.';
		case 'config':
			return `Cấu hình model chưa đúng: ${message}`;
		case 'network':
			return message;
		default:
			return `Lỗi khi gọi model: ${message}`;
	}
}

export function formatReset(iso: string | null | undefined): string {
	if (!iso) return 'nửa đêm theo giờ Thái Bình Dương';
	const d = new Date(iso);
	const sameDay = d.toDateString() === new Date().toDateString();
	const time = d.toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
	return sameDay ? time : `${time} ngày ${d.toLocaleDateString('vi-VN')}`;
}
