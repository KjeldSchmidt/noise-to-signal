# theme_analysis

Async worker that exports article embeddings via the internal API, computes
theme–embedding alignment metrics (within/between cosine, centroid heatmap,
neighborhood purity, UMAP 2D), and writes JSON artifacts to S3 for the Django
admin theme-analysis page.

Triggered by Event invoke from web admin (no schedule).

## Lambda notes

UMAP pulls in Numba with function caching enabled. Lambda's
`/var/lang/.../site-packages` is read-only, so Numba must cache under `/tmp`
(`NUMBA_CACHE_DIR`, set in code and Terraform).
