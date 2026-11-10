// Số chương bằng chữ Hán (一, 十二, 一百零五…), chỉ để trang trí; luôn kèm số thường.
const D = ['零', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
const U = ['', '十', '百', '千'];

export function hanNumber(n: number): string {
	if (n <= 0 || n >= 10000 || !Number.isInteger(n)) return String(n);
	const digits = String(n).split('').map(Number);
	let out = '';
	let zero = false;
	digits.forEach((d, i) => {
		const unit = U[digits.length - 1 - i];
		if (d === 0) {
			zero = true;
			return;
		}
		if (zero && out) out += '零';
		zero = false;
		out += (d === 1 && unit === '十' && i === 0 ? '' : D[d]) + unit;
	});
	return out;
}
