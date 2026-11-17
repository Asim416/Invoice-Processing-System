# Groq vision invoice reader

The live reader now sends rendered invoice-page images to a multimodal model. It does not depend on the PDF's embedded
text layer, so it can process scanned/image-only PDFs as well as ordinary digital PDFs.

## 1. Install the updated dependencies

From the project root:

```bash
pip install -r requirements.txt
```

`PyMuPDF` is used to render PDF pages into JPEG images. `pdfplumber` remains installed for the existing text-based
mock/test path and optional text diagnostics; the live vision reader uses the page images as its extraction source.

## 2. Update `.env`

Keep your existing API key, Sheets and Slack settings. Change only these LLM settings:

```env
EXTRACTION_MODE=live
LLM_PROVIDER=groq
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=qwen/qwen3.8-27b
LLM_MAX_TOKENS=2000
LLM_TIMEOUT_SECONDS=60
LLM_TOKENS_PER_MINUTE=6000
```

Do not paste your API key into source code or commit `.env`.

## 3. Restart the app

Stop Streamlit with `Ctrl+C`, then start it again using your existing `run.bat` / `run.sh` command.
The sidebar should show the live model as `qwen/qwen3.8-27b`.

## How the reader works

1. Each PDF page is rendered to a JPEG at 144 DPI.
2. Images are sent to Groq using the OpenAI-compatible Chat Completions API and strict JSON Schema output.
3. The reader sends up to two pages per request to leave room under common token-per-minute limits. Longer invoices are processed in page groups and merged conservatively.
4. If different page groups report conflicting values for the same scalar field, that field is set to null rather than guessed.
5. Python validates the returned schema and checks line arithmetic and invoice-level subtotal/tax/total arithmetic.
6. Vision-only results are marked **medium confidence** and require human review. They are not eligible for an automatic approval recommendation.

## Important limitations

- Groq documents support for up to three images per request for `qwen/qwen3.8-27b`; this implementation deliberately sends at most two pages per request to reduce token-rate-limit pressure.
- The model can still misread low-resolution, rotated, faint or unusually formatted documents. Review the vendor, invoice number,
  subtotal, tax and total before recording a decision.
- The reader does not calculate a missing VAT amount or grand total. Missing printed values remain null and are flagged by validation.
- Test with representative invoices before using the output in a real accounts-payable process.
