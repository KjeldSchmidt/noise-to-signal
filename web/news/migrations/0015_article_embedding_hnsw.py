# pgvector HNSW index for chat article ANN search (Postgres only).

from django.db import migrations


def create_hnsw_index(apps, schema_editor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(
        """
        CREATE INDEX IF NOT EXISTS news_article_embedding_hnsw
        ON news_article
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )


def drop_hnsw_index(apps, schema_editor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute("DROP INDEX IF EXISTS news_article_embedding_hnsw;")


class Migration(migrations.Migration):
    dependencies = [
        ("news", "0014_chat_rate_limit_bucket"),
    ]

    operations = [
        migrations.RunPython(create_hnsw_index, drop_hnsw_index),
    ]
