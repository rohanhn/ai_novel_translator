// "Tu vi": cảnh giới theo tỉ lệ chương đã dịch. Luôn hiển thị kèm số chương (nhãn rõ nghĩa).
const REALMS: [number, string][] = [
	[0, 'Phàm nhân'],
	[0.2, 'Luyện Khí'],
	[0.4, 'Trúc Cơ'],
	[0.6, 'Kim Đan'],
	[0.8, 'Nguyên Anh'],
	[1, 'Hóa Thần']
];

export function realm(translated: number, total: number): string {
	if (total > 0 && translated >= total) return 'Đại Thừa';
	if (translated === 0) return 'Phàm nhân';
	const ratio = total ? translated / total : 0;
	return REALMS.find(([limit]) => ratio < limit)?.[1] ?? 'Hóa Thần';
}

export function percent(part: number, total: number): number {
	return total ? Math.round((part / total) * 100) : 0;
}

export function formatBytes(n: number): string {
	return `${(n / 1024 / 1024).toLocaleString('vi-VN', { maximumFractionDigits: 1 })} MB`;
}
