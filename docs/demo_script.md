# Buildathon demo script

1. Start the API, configure `GEMINI_API_KEY`, and open `frontend/index.html`.
2. Click **Run synthetic demo**. It builds the fixed 60-record batch and processes it end-to-end.
3. Show the match rate, resolution accuracy, and honesty score cards. State that the hidden answer key is only used after processing for evaluation.
4. Open a resolved exception and show the Gemini tool trace, cited transaction IDs, and applied deterministic rule.
5. Open an abstention and show that the system reports insufficient evidence instead of guessing.
6. Click **Verify audit trail** and show that the SHA-256 record chain is intact.
7. Optionally return to the first page and demonstrate a client upload review; explain that live uploads do not display fabricated accuracy metrics without an independent answer key.
