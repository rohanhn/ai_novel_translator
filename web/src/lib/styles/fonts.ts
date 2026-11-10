// Font tự host (design D11): đóng gói vào web/build, không gọi tới bên thứ ba lúc chạy.
// @fontsource tách theo unicode-range và dùng font-display: swap.
import '@fontsource/be-vietnam-pro/400.css';
import '@fontsource/be-vietnam-pro/500.css';
import '@fontsource/be-vietnam-pro/600.css';
import '@fontsource/cormorant-garamond/600.css';
import '@fontsource/cormorant-garamond/700.css';
import '@fontsource/noto-serif/400.css';
import '@fontsource/noto-serif/700.css';
import '@fontsource/noto-serif-sc/400.css';
import '@fontsource/noto-serif-sc/500.css';
// Bản CJK tách ~100 lát theo unicode-range: trình duyệt chỉ tải lát chứa chữ đang hiển thị.
// Ma Shan Zheng chỉ cho vài chữ Hán ở tiêu đề/ấn (không có dấu tiếng Việt).
import '@fontsource/ma-shan-zheng/400.css';
