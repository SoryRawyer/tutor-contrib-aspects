"""
add additional fields to course_names_dict and and course_names
"""
from alembic import op


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        DROP TABLE IF EXISTS {{ ASPECTS_EVENT_SINK_DATABASE }}.course_names;
    """
    )
    op.execute(
        """
        DROP DICTIONARY IF EXISTS {{ ASPECTS_EVENT_SINK_DATABASE }}.course_names_dict;
    """
    )

    op.execute(
        """
        CREATE DICTIONARY {{ ASPECTS_EVENT_SINK_DATABASE }}.course_names_dict (
            course_key String,
            course_name String,
            course_run String,
            org String
        )
        PRIMARY KEY course_key
        SOURCE(CLICKHOUSE(
            user '{{ CLICKHOUSE_ADMIN_USER }}'
            password '{{ CLICKHOUSE_ADMIN_PASSWORD }}'
            db 'event_sink'
            query 'with most_recent_overviews as (
                    select org, course_key, max(modified) as last_modified
                    from event_sink.course_overviews
                    group by org, course_key
            )
            select
                course_key,
                display_name,
                splitByString(\\'+\\', course_key)[-1] as course_run,
                org
            from event_sink.course_overviews co
            inner join most_recent_overviews mro on
                co.org = mro.org and
                co.course_key = mro.course_key and
                co.modified = mro.last_modified
            '
        ))
        LAYOUT(COMPLEX_KEY_HASHED())
        LIFETIME(120);
        """
    )
    op.execute(
        """
        CREATE OR REPLACE TABLE {{ ASPECTS_EVENT_SINK_DATABASE }}.course_names
        (
            course_key String,
            course_name String,
            course_run String,
            org String
        ) engine = Dictionary({{ ASPECTS_EVENT_SINK_DATABASE }}.course_names_dict);
        """
    )


def downgrade():
    op.execute(
        """
        DROP TABLE IF EXISTS {{ ASPECTS_EVENT_SINK_DATABASE }}.course_names;
    """
    )
    op.execute(
        """
        DROP DICTIONARY IF EXISTS {{ ASPECTS_EVENT_SINK_DATABASE }}.course_names_dict;
    """
    )

    op.execute(
        """
        CREATE DICTIONARY {{ ASPECTS_EVENT_SINK_DATABASE }}.course_names_dict (
            course_key String,
            course_name String
        )
        PRIMARY KEY course_key
        SOURCE(CLICKHOUSE(
            user '{{ CLICKHOUSE_ADMIN_USER }}'
            password '{{ CLICKHOUSE_ADMIN_PASSWORD }}'
            db 'event_sink'
            query 'with most_recent_overviews as (
                    select org, course_key, max(modified) as last_modified
                    from event_sink.course_overviews
                    group by org, course_key
            )
            select
                course_key,
                display_name
            from event_sink.course_overviews co
            inner join most_recent_overviews mro on
                co.org = mro.org and
                co.course_key = mro.course_key and
                co.modified = mro.last_modified
            '
        ))
        LAYOUT(COMPLEX_KEY_HASHED())
        LIFETIME(120);
        """
    )
    op.execute(
        """
        CREATE OR REPLACE TABLE {{ ASPECTS_EVENT_SINK_DATABASE }}.course_names
        (
            course_key String,
            course_name String
        ) engine = Dictionary({{ ASPECTS_EVENT_SINK_DATABASE }}.course_names_dict);
        """
    )