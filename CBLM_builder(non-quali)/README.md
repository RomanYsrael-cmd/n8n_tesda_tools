# CBLM Builder (Non-Qualification)

This is a separate local TESDA tool that shares the Module Builder launcher and saved OpenAI-compatible provider settings.

## Use it

1. Double-click the existing Module Builder launcher and wait for the browser.
2. Open `http://localhost:8080/` and choose **CBLM Builder**.
3. Upload a DOCX syllabus.
4. Review the detected course, learning outcomes, topics, duration, location, and laboratory/workshop values.
5. Choose 1–4 simultaneous LLM calls, approve, then start automatic generation.
6. Download the ZIP or each CBLM DOCX.

Each syllabus learning outcome becomes one CBLM. Templates 00, 10, and 20 occur once per learning outcome. Templates 30, 40, and 50 occur once per topic. Prompts are loaded verbatim from `Prompts.xlsx`; only `{{placeholders}}` are substituted. Invalid Self-Check or Task Sheet responses are normalized by Python when safe, otherwise the same complete original prompt is resent up to two times. No correction prompt or manual ChatGPT mode is used.

Markdown headings, paragraphs, numbered lists, bullets, bold, italic, and bold-italic content are converted into Word structure while preserving the supplied templates.
