# Kiến trúc Novel Translator

Kiến trúc hexagonal (ports & adapters): lõi nghiệp vụ không biết gì về CLI, HTTP, SQLite hay SDK của LLM. Nhờ vậy thêm provider, định dạng file, hay giao diện mới chỉ cần thêm adapter.

```
                ┌──────────────┐     ┌──────────────┐
                │  CLI (Typer) │     │ API (FastAPI)│      interfaces/
                └──────┬───────┘     └──────┬───────┘
                       └────────┬───────────┘
                                ▼
                  ┌───────────────────────────┐
                  │  application/services.py  │   use case: import, dịch, glossary, export
                  └─────┬───────────┬─────────┘
                        │           ▼
                        │   ┌────────────────┐
                        │   │   pipeline/    │   tách đoạn → prompt + glossary → gọi LLM → ghép
                        │   └───────┬────────┘
                        ▼           ▼
                  ┌───────────────────────────┐
                  │ domain/ (models + ports)  │   entity + interface, không phụ thuộc gì
                  └───────────────────────────┘
                        ▲           ▲            ▲              ▲
             storage/sqlite   providers/*   ingest/txt    export/txt       adapters
                        └───────────┴────────────┴──────────────┘
                                 nối trong container.py
```

## Các lớp

| Thư mục | Vai trò | Được import |
|---|---|---|
| `domain/` | `Novel`, `Chapter`, `GlossaryEntry`; port `LLMProvider`, `NovelRepository`, `SourceLoader`, `Exporter` | không gì cả |
| `pipeline/` | `segmenter` (chia đoạn), `prompts` (system prompt + glossary), `translator` (dịch 1 chương) | domain |
| `application/` | `LibraryService`, `GlossaryService`, `TranslationService`, `ExportService` | domain, pipeline |
| `providers/` | `anthropic` (Claude), `openai`/`ollama` (OpenAI-compatible), `echo` (test) + `registry` | domain |
| `storage/` | SQLite (`novels`, `chapters`, `glossary`) | domain |
| `ingest/`, `export/` | đọc TXT (tách `第X章`), xuất TXT | domain |
| `container.py` | composition root: nơi duy nhất chọn adapter cụ thể | tất cả |
| `interfaces/` | CLI + API, chỉ parse input / format output | application, container |

## Điểm mở rộng thường gặp

- **Provider LLM mới** (Gemini, DeepSeek...): viết class có `name`, `default_model`, `complete()` trong `providers/`, gọi `register_provider()` trong `registry.py`. Nếu API tương thích OpenAI thì chỉ cần factory dùng `OpenAICompatProvider` với `base_url`.
- **Định dạng nhập** (EPUB, crawl web): hiện thực `SourceLoader`, nối trong `container.py`.
- **Định dạng xuất** (EPUB, DOCX): hiện thực `Exporter`, thêm vào dict `exporters`.
- **Storage khác** (Postgres): hiện thực `NovelRepository`.

## Quyết định thiết kế

- **Claude là provider mặc định** (`claude-opus-5-5`, effort `medium`, streaming). System prompt (chứa glossary) giống hệt giữa các đoạn → prompt caching giảm chi phí. Bật server-side fallback (`fallbacks: "default"`) để đoạn bị model từ chối được dịch lại bởi model dự phòng thay vì fail.
- **Dịch đồng bộ** trong request API: đơn giản cho giai đoạn đầu. Dịch hàng loạt dài nên chuyển sang job nền (xem backlog).
- **SQLite**: một file, không cần server; đủ cho dùng cá nhân.

## Backlog gợi ý (đẩy qua `/opsx:propose`)

- Job nền + tiến độ cho dịch hàng loạt (API trả job id, polling/SSE)
- Tự trích xuất glossary từ các chương đầu bằng LLM
- Dịch song song nhiều đoạn, giới hạn rate
- Ngữ cảnh chương trước (tóm tắt) để giữ mạch truyện
- Import EPUB / crawl web; export EPUB
- Web UI đọc song ngữ, sửa bản dịch tay
- Theo dõi token/chi phí theo chương
